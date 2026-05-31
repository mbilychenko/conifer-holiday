# Analysis + Publication Plan — Conifer Holiday

## Overview and Goals

**Primary goal:** Produce a geospatial clustering of UK conifer and mixed woodland
(from the Forestry Commission NFI dataset) that groups raw survey polygons into
meaningful, human-scale forest blocks. These clusters power the web app AND form
the basis of an open dataset and data science publication.

**Secondary goal:** Enrich each cluster with accessibility data (public transport
travel time from London) and optional qualitative data (review themes via NLP).

**Publication target:** Towards Data Science (primary, for visibility) + Zenodo
dataset deposit (for citability). If the methodology is rigorous enough, a short
data paper to *Environmental Data Science* or *Data in Brief* is viable.

**Framing:**
> "From 344,000 polygons to 200 meaningful forest destinations:
>  unsupervised geospatial clustering of the UK National Forest Inventory"

---

## Data Sources

| Source | What it provides | Licence | Notes |
|---|---|---|---|
| Forestry Commission NFI GB 2023 | Forest polygon geometry + IFT_IOA species type | Open Government Licence | Download from https://data-forestry.opendata.arcgis.com |
| OS OpenNames | Place names for naming clusters (nearest named place) | Open Government Licence | Used to assign human-readable names to clusters |
| Traveline GTFS | Bus timetables for GB | OGL | https://data.bus-data.dft.gov.uk |
| ATOC CIF | Rail timetables | Requires registration | Rail Delivery Group; needs UK2GTFS conversion to GTFS |
| OTP4GB | Pre-assembled OTP graph for GB | Open | https://github.com/odileeds/OTP4GB — check if current |
| Google Places API | Reviews and editorial summaries per cluster | Google ToS | Used in app; not citeable in research methodology |
| ONS Census 2021 | Population by postcode/LSOA (optional) | OGL | For population-weighted accessibility analysis |

---

## Phase 1: Data Preparation

### 1a. Download and inspect NFI data

```bash
# After downloading and unzipping from ArcGIS Hub
ogrinfo -al -so nfi_woodland_gb.shp
```

Key columns to verify:
- `IFT_IOA` — species type (the primary filter field)
- `HECTARES` — polygon area
- Coordinate system should be OSGB36/BNG (EPSG:27700)

Check value distribution:
```python
import geopandas as gpd
gdf = gpd.read_file('nfi_woodland_gb.shp')
print(gdf['IFT_IOA'].value_counts())
print(f"Total polygons: {len(gdf)}")
print(f"Total area (ha): {gdf['HECTARES'].sum():,.0f}")
```

### 1b. Filter to conifer-relevant types

```python
# scripts/analysis/01_prepare.py
import geopandas as gpd

gdf = gpd.read_file('nfi_woodland_gb.shp')

# Primary filter: conifer-present types
conifer_types = ['Conifer', 'Mixed mainly conifer', 'Mixed mainly broadleaved']
gdf_conifer = gdf[gdf['IFT_IOA'].isin(conifer_types)].copy()

# Drop micro-patches (not visually or ecologically significant at national scale)
gdf_conifer = gdf_conifer[gdf_conifer['HECTARES'] >= 10]

# Keep only needed fields
gdf_conifer = gdf_conifer[['IFT_IOA', 'HECTARES', 'geometry']]

# Verify CRS is OSGB36 (required for DBSCAN distance in metres)
assert gdf_conifer.crs.to_epsg() == 27700, "Expected OSGB36"

gdf_conifer.to_file('filtered_conifers.gpkg', driver='GPKG')
print(f"Filtered to {len(gdf_conifer)} polygons")
print(gdf_conifer['IFT_IOA'].value_counts())
```

---

## Phase 2: Geospatial Clustering (Core Methodology)

### 2a. Algorithm choice

**DBSCAN** — use first. Conceptually simple; epsilon parameter is interpretable
as "the gap in metres that separates two distinct forest blocks."

**HDBSCAN** — try second. Handles variable-density clusters better (Scottish
dense plantations vs. scattered English copses). Uses `min_cluster_size` rather
than a fixed epsilon.

Both are in scikit-learn / hdbscan (pip-installable).

### 2b. DBSCAN implementation

```python
# scripts/analysis/02_cluster_dbscan.py
import geopandas as gpd
import numpy as np
from sklearn.cluster import DBSCAN

gdf = gpd.read_file('filtered_conifers.gpkg')

# Use polygon centroids for clustering (in OSGB36 — units are metres)
centroids = gdf.geometry.centroid
coords = np.column_stack([centroids.x, centroids.y])

# --- KEY PARAMETER: epsilon ---
# epsilon is the max gap in metres between two patches to be the same cluster.
# Start with 2000m (2km). Tune by visual inspection.
# Too small → many micro-clusters. Too large → unrelated forests merge.
EPSILON = 2000       # metres — the primary tuning parameter
MIN_SAMPLES = 3      # minimum polygons to form a cluster

db = DBSCAN(eps=EPSILON, min_samples=MIN_SAMPLES, metric='euclidean', n_jobs=-1)
labels = db.fit_predict(coords)

gdf['cluster_id'] = labels
noise_count = (labels == -1).sum()
cluster_count = len(set(labels)) - (1 if -1 in labels else 0)
print(f"Clusters: {cluster_count}, Noise polygons: {noise_count}")
```

### 2c. Epsilon sensitivity analysis (key for article)

Run DBSCAN across a range of epsilon values. Plot:
- Number of clusters vs. epsilon
- Largest cluster area vs. epsilon
- Noise polygon count vs. epsilon

```python
epsilons = [500, 1000, 2000, 3000, 5000, 8000, 10000]
results = []
for eps in epsilons:
    db = DBSCAN(eps=eps, min_samples=3).fit(coords)
    n_clusters = len(set(db.labels_)) - (1 if -1 in db.labels_ else 0)
    n_noise = (db.labels_ == -1).sum()
    results.append({'epsilon': eps, 'n_clusters': n_clusters, 'n_noise': n_noise})

import pandas as pd
import matplotlib.pyplot as plt
df = pd.DataFrame(results)
# Plot n_clusters vs epsilon — look for the "elbow" where adding epsilon
# stops creating useful merges and starts combining unrelated forests
```

The elbow in the cluster count curve is the recommended epsilon. This plot is
Figure 1 of the article.

### 2d. HDBSCAN alternative

```python
# scripts/analysis/02b_cluster_hdbscan.py
import hdbscan  # pip install hdbscan

clusterer = hdbscan.HDBSCAN(
    min_cluster_size=5,          # minimum NFI polygons per forest block
    min_samples=3,               # core point density
    metric='euclidean',
    cluster_selection_method='eom'  # excess of mass — better for variable density
)
labels = clusterer.fit_predict(coords)
```

Compare DBSCAN vs HDBSCAN results visually. The article should report both
and justify the final choice.

### 2e. Dissolve clusters into single polygons

```python
# scripts/analysis/03_dissolve.py
import geopandas as gpd

gdf = gpd.read_file('filtered_conifers_clustered.gpkg')

# Remove noise polygons (cluster_id == -1)
gdf_valid = gdf[gdf['cluster_id'] >= 0].copy()

# Dissolve: one polygon per cluster, aggregate stats
clusters = gdf_valid.dissolve(
    by='cluster_id',
    aggfunc={
        'HECTARES': 'sum',
        'IFT_IOA': lambda x: x.mode()[0]   # dominant type
    }
).reset_index()

# Add centroid in WGS84 for the app and for OTP routing
clusters_wgs84 = clusters.to_crs('EPSG:4326')
clusters_wgs84['centroid_lat'] = clusters_wgs84.geometry.centroid.y
clusters_wgs84['centroid_lng'] = clusters_wgs84.geometry.centroid.x

print(f"Final cluster count: {len(clusters_wgs84)}")
print(clusters_wgs84['HECTARES'].describe())

clusters_wgs84.to_file('clusters.geojson', driver='GeoJSON')
```

---

## Phase 3: Cluster Characterisation

Each cluster needs a human-readable name and descriptive statistics for the app
and the article.

### 3a. Naming clusters

Option A (recommended): Spatial join with OS OpenNames to find the nearest named
place (town, village, or landscape feature) to each cluster centroid.

```python
# Use OS OpenNames (free download from OS website)
import geopandas as gpd
from shapely.ops import nearest_points

os_names = gpd.read_file('os_open_names.gpkg').to_crs('EPSG:4326')
clusters = gpd.read_file('clusters.geojson')

# For each cluster centroid, find nearest OS place name
# Filter OS names to relevant types: 'populatedPlace', 'landform', 'other'
# This gives cluster names like "Near Kielder", "Galloway area", etc.
```

Option B (quick): Manually name the top 50 clusters by area. The top 50 cover
the majority of UK conifer forest by hectares.

### 3b. Cluster statistics for article

Per cluster, compute:
- Total area (hectares)
- Species composition: % Conifer, % Mixed mainly conifer, % Mixed mainly broadleaved
- Number of constituent NFI polygons
- Convex hull compactness (area / convex hull area) — how compact vs. fragmented
- Isolation score: distance to nearest other cluster (metres)

```python
# Compactness
clusters['compactness'] = clusters.area / clusters.convex_hull.area

# Isolation (distance to nearest other cluster)
# Use GeoDataFrame spatial index for efficiency
```

These statistics become Table 1 and Figures 2–3 in the article.

---

## Phase 4: Accessibility Analysis

**Infrastructure requirement:** Building a GB-wide OTP graph requires ~64GB RAM.
Use a cloud VM for this phase (4–8 hours rental, ~£15–25).

See `ANALYSIS_PLAN.md` → Cloud VM Setup below.

### 4a. Cloud VM setup for OTP

Recommended provider: Hetzner (cheapest large-RAM VMs in Europe).
- Instance: `CCX53` (32 vCPU, 128GB RAM) at ~€0.50/hour
- OS: Ubuntu 22.04 LTS
- Duration needed: 4–8 hours

```bash
# On the cloud VM:
# 1. Install Java 17
sudo apt install openjdk-17-jdk -y

# 2. Download OTP jar
wget https://github.com/opentripplanner/OpenTripPlanner/releases/download/v2.5.0/otp-2.5.0-shaded.jar

# 3. Prepare GTFS data
# 3a. Buses: download from https://data.bus-data.dft.gov.uk (GTFS format, free)
# 3b. Rail: download ATOC CIF from Rail Delivery Group (requires registration)
#           convert using UK2GTFS R package (see https://itsleeds.github.io/UK2GTFS/)

# 4. Download OSM road network for GB
wget https://download.geofabrik.de/europe/great-britain-latest.osm.pbf

# 5. Build OTP graph (this takes ~2–4 hours and ~60GB RAM)
java -Xmx64G -jar otp-2.5.0-shaded.jar --build --save ./graph

# 6. Start OTP server
java -Xmx8G -jar otp-2.5.0-shaded.jar --load ./graph --serve
```

Alternatively, check if the **OTP4GB** project (ODI Leeds, GitHub) has a
pre-built graph available. If their graph is current, this skips steps 3–5.

### 4b. Compute travel time matrix

From each major London terminal to each forest cluster centroid.

**Origin stations:** Waterloo, Paddington, King's Cross/St Pancras, Liverpool
Street, Victoria, Marylebone (covers major rail directions from London).

**Destinations:** All cluster centroids (lat/lng from `clusters.geojson`).

```python
# scripts/analysis/04_travel_times.py
import requests
import pandas as pd
import time

OTP_URL = "http://<vm-ip>:8080/otp/routers/default/plan"

origins = {
    'Waterloo': (51.5031, -0.1132),
    'Paddington': (51.5154, -0.1755),
    'Kings_Cross': (51.5308, -0.1238),
    'Liverpool_Street': (51.5178, -0.0823),
}

clusters = pd.read_json('clusters_meta.json')
results = []

for cluster in clusters.itertuples():
    for origin_name, (orig_lat, orig_lng) in origins.items():
        params = {
            'fromPlace': f"{orig_lat},{orig_lng}",
            'toPlace': f"{cluster.centroid_lat},{cluster.centroid_lng}",
            'mode': 'TRANSIT,WALK',
            'date': '2025-06-01',    # use a representative weekday
            'time': '08:00:00',
            'maxWalkDistance': 3000,
            'numItineraries': 1,
        }
        try:
            r = requests.get(OTP_URL, params=params, timeout=30)
            data = r.json()
            itinerary = data['plan']['itineraries'][0]
            duration_mins = itinerary['duration'] / 60
            results.append({
                'cluster_id': cluster.id,
                'cluster_name': cluster.name,
                'origin': origin_name,
                'duration_mins': duration_mins,
                'n_transfers': itinerary['transfers'],
            })
        except Exception as e:
            results.append({
                'cluster_id': cluster.id,
                'origin': origin_name,
                'duration_mins': None,
                'error': str(e),
            })
        time.sleep(0.5)  # be polite to OTP

pd.DataFrame(results).to_csv('travel_time_matrix.csv', index=False)
```

### 4c. Key findings to compute

From the travel time matrix:

```python
import pandas as pd
df = pd.read_csv('travel_time_matrix.csv')

# Best accessible clusters (min travel time across all origins)
best_accessible = df.groupby('cluster_id')['duration_mins'].min().sort_values()

# Unreachable clusters (no route found from any London terminal)
unreachable = df[df['duration_mins'].isna()].groupby('cluster_id').size()

# "Within 2 hours" count
within_2h = df[df['duration_mins'] <= 120].groupby('cluster_id').first()

print(f"Forests reachable within 2h from London: {len(within_2h)}")
print(f"Forests with no direct rail route: {len(unreachable)}")
```

This produces the headline finding for the article. Whatever the actual numbers
are (unknown until analysis runs) — this is the novel contribution.

### 4d. Isochrone maps (visualisation)

Generate isochrones from London Waterloo at 1h, 2h, 3h intervals using OTP:

```bash
# OTP isochrone endpoint
curl "http://<vm-ip>:8080/otp/routers/default/isochrone?fromPlace=51.5031,-0.1132&mode=TRANSIT,WALK&cutoffSec=3600&cutoffSec=7200&cutoffSec=10800&date=2025-06-01&time=08:00:00"
```

Overlay the isochrones with the cluster polygons in a map (matplotlib + geopandas
or Folium). Forest clusters that fall outside the 3-hour isochrone are shown in
a different colour — these are the "inaccessible by train" destinations.

This map is the hero image of the article.

---

## Phase 5: NLP Analysis (Optional — Adds a Second Technique)

If time allows, adds a third analytical layer to the article.

### 5a. Collect text data per cluster

Sources (in order of effort):
1. **Forestry England website** — forest pages have visitor descriptions. Scrape
   for major named forests.
2. **Google Places reviews** — retrieved via the app's `/api/places` endpoint;
   store locally in `data/reviews/`. Note: Google ToS restricts bulk storage of
   review data; use sparingly and cite the source.
3. **Wikidata/Wikipedia** — forest articles have free text. Use the Wikipedia API.

### 5b. Theme extraction

Use BERTopic or LDA to identify recurring themes in forest reviews:
- Accessibility mentions ("easy walk", "hard to reach", "no car")
- Atmosphere ("dark", "peaceful", "atmospheric", "spooky")
- Wildlife mentions ("red squirrels", "crossbills", "deer")
- Facilities ("car park", "café", "no facilities")

```python
from bertopic import BERTopic

docs = [review['text'] for review in all_reviews]
topic_model = BERTopic(language='english', calculate_probabilities=True)
topics, probs = topic_model.fit_transform(docs)
topic_model.get_topic_info()
```

### 5c. Sentiment + accessibility language correlation

Do reviews of inaccessible forests (long travel times) mention parking/driving
more than accessible ones? Correlate:
- % of reviews mentioning car/driving vs. cluster travel time
- Sentiment score vs. cluster accessibility score

This is a small but concrete finding that adds an NLP dimension to the article.

---

## Publication Strategy

### Article structure (Towards Data Science)

```
Title: From 344,000 Polygons to 200 Forest Destinations:
       Geospatial Clustering of the UK National Forest Inventory

1. The Problem
   — UK has least tree cover in Europe; forests aren't labelled as destinations
   — NFI gives survey polygons, not usable places
   — Train travellers have no tool to find forests

2. The Data
   — NFI overview: what it is, how to access it, field definitions
   — Scale: X polygons, Y hectares of conifer

3. The Methodology: Geospatial Clustering
   — Why DBSCAN for spatial data
   — Epsilon sensitivity analysis (Figure 1)
   — DBSCAN vs HDBSCAN comparison
   — Final parameter choice + justification
   — Cluster statistics (Table 1)

4. Accessibility Analysis
   — OTP setup (brief; link to GitHub for full instructions)
   — Travel time matrix methodology
   — Key finding: X forests reachable within 2h from London
   — Isochrone map (hero image)
   — Most and least accessible forests (ranked list)

5. Optional: NLP Analysis
   — Review theme extraction
   — Accessibility language correlation

6. The App
   — Interactive demo (link)
   — How the cluster output powers the app

7. Open Dataset
   — What's in the dataset
   — How to download (Zenodo DOI)
   — How to reproduce the analysis (GitHub)

8. Conclusions and Future Work
```

### Dataset release (Zenodo)

Deposit the following under CC BY 4.0:
- `clusters.geojson` — cluster polygons (WGS84)
- `clusters_meta.json` — cluster attributes (name, area, type, centroid)
- `travel_time_matrix.csv` — London terminals × clusters × travel time
- `README.md` — field definitions, methodology summary, how to reproduce

Steps:
1. Create account at zenodo.org
2. New upload → choose licence CC BY 4.0
3. Upload files → fill metadata → publish
4. Get DOI → cite in article

### GitHub repository

Make the `scripts/analysis/` folder and the data pipeline scripts public in the
main repo. Include a `scripts/analysis/README.md` explaining how to reproduce
the full analysis from the NFI download. This is the "open source contribution."

### Potential academic venue (longer term)

If the travel time matrix finding is strong (e.g. clear inequity pattern, or
comparison with car accessibility shows dramatic difference), consider submitting
a short data paper to:
- *Environmental Data Science* (Cambridge Core, open access)
- *Data in Brief* (Elsevier)
- *Scientific Data* (Nature, highest visibility)

These require a structured methodology section and a reproducibility statement —
the OTP + GTFS approach satisfies both.

---

## Timeline Estimate

| Phase | Estimated duration | Blocker |
|---|---|---|
| Phase 1: Data prep | 1–2 days | NFI download + Python setup |
| Phase 2: Clustering | 2–3 days | Epsilon tuning, visual validation |
| Phase 3: Characterisation | 1 day | OS OpenNames join |
| Phase 4: Accessibility | 3–5 days | Cloud VM setup + OTP build |
| Phase 5: NLP (optional) | 3–5 days | Data collection |
| Article writing | 3–5 days | Findings must be clear first |
| Dataset + GitHub release | 1 day | Zenodo account |
| **Total** | **~2–4 weeks** | |

App development (see `APP_PLAN.md`) can proceed in parallel with Phase 3 onwards,
once the cluster GeoJSON is ready.

---

## Infrastructure Requirements Summary

| Task | Machine | Cost | Duration |
|---|---|---|---|
| Data filtering + clustering | Local laptop | Free | 2–4 hours compute |
| OTP graph build (GB) | Cloud VM (64GB+ RAM) | ~£15–25 | 4–8 hours |
| OTP batch routing queries | Same cloud VM | Included | 1–3 hours |
| Article writing | Local laptop | Free | — |

**Recommended cloud VM:** Hetzner `CCX53` (32 vCPU, 128GB RAM, ~€0.50/hr).
Spin up, run pipeline, download results, terminate. Total cost ~£10–20.

---

## Reproducibility Checklist

- [ ] All scripts in `scripts/analysis/` committed to GitHub
- [ ] `requirements.txt` (Python) and R session info committed
- [ ] NFI data version + download date documented
- [ ] GTFS data version + download date documented
- [ ] OTP version + graph build command documented
- [ ] Epsilon / HDBSCAN parameters justified and documented
- [ ] Travel time matrix CSV committed (or on Zenodo)
- [ ] Results can be reproduced from raw NFI download by following the README
