# Conifer Holiday — Project Index

## What is this?

An interactive web map of UK conifer and mixed woodland, built for people who
travel by train. You enter a London starting point, the app shows which forests
you can reach, how long it takes, and what each forest is like (reviews, photos,
species mix). A companion data science analysis produces the forest cluster
dataset that powers the map.

**Two parallel tracks:**
- `APP_PLAN.md` — building the web application
- `ANALYSIS_PLAN.md` — the geospatial clustering analysis and publication

---

## Quick Navigation

| I want to… | Go to |
|---|---|
| Understand the full project structure | This file (keep reading) |
| Start building the web app | `APP_PLAN.md` |
| Run the geospatial clustering analysis | `ANALYSIS_PLAN.md` → Phase 2 |
| Set up the data pipeline (download NFI data) | `APP_PLAN.md` → Data Pipeline |
| Understand what DBSCAN is doing | `ANALYSIS_PLAN.md` → Clustering Methodology |
| Deploy the app to Vercel | `APP_PLAN.md` → Deployment |
| Write the article / release the dataset | `ANALYSIS_PLAN.md` → Publication Strategy |

---

## Architecture at a Glance

```
Forestry Commission NFI Data (open, ~600k polygons)
          |
          v
    [Filter: conifer types, >10ha]          scripts/pipeline/
          |
          v
    [DBSCAN/HDBSCAN clustering]             scripts/analysis/
          |
          v
    Cluster GeoJSON (~100-300 clusters)     public/data/clusters.geojson
          |
          +---> Web App (Next.js + Leaflet)  [primary product]
          +---> Open Dataset (Zenodo)        [research output]
          +---> Article (Towards Data Science / journal)
```

**Key principle:** The clustering analysis produces the data the web app consumes.
The app is the interactive face of the research.

---

## Key Concepts (Glossary)

**NFI (National Forest Inventory)**
The Forestry Commission's polygon survey of all woodland in Great Britain.
~600,000 polygons covering patches ≥0.5ha. Updated regularly. Open Government Licence.
Download: https://data-forestry.opendata.arcgis.com

**IFT_IOA (Interpreted Forest Type / Interpreted Open Area)**
The NFI field that classifies each polygon by species composition.
Values used in this project:
- `Conifer` — pure or predominantly conifer
- `Mixed mainly conifer` — >50% conifer by area
- `Mixed mainly broadleaved` — mixed but has conifer presence (optional layer)

**OSGB36 / BNG (British National Grid, EPSG:27700)**
The coordinate reference system (CRS) used in UK government data.
Uses metres as units — essential for distance-based operations like DBSCAN.
Must be reprojected to WGS84 (EPSG:4326) for web display in Leaflet.

**WGS84 (EPSG:4326)**
The standard lat/lng coordinate system used by GPS, Google Maps, Leaflet.
All data must be in WGS84 before going into the web app.

**DBSCAN (Density-Based Spatial Clustering of Applications with Noise)**
A clustering algorithm that groups nearby points without requiring you to
specify the number of clusters. Key parameters:
- `epsilon` — maximum distance (in metres, when using BNG) between two points
  to be considered neighbours. Controls how far apart forest patches can be
  and still be in the same cluster. Tuning this is the core methodological decision.
- `min_samples` — minimum polygons to form a cluster (filters out isolated patches).
Points that don't belong to any cluster are labelled as noise (-1).

**HDBSCAN (Hierarchical DBSCAN)**
Extension of DBSCAN that handles variable-density data better.
Preferred when clusters vary greatly in density (e.g. dense Scottish plantations
vs. scattered English copses). Uses `min_cluster_size` instead of `epsilon`.

**Dissolve**
GIS operation that merges multiple polygons sharing the same attribute value
into a single polygon. Used to combine all NFI patches in a cluster into one
forest-block geometry.

**GeoJSON**
Standard JSON format for geographic data. Used for serving polygon layers to Leaflet.
Performance target: <15MB for the web app layer.

**OTP (OpenTripPlanner)**
Open-source Java server for public transport routing. Takes GTFS transit data
as input, builds a graph, then answers origin→destination queries.
Used for the analysis (bulk routing from London terminals to forest clusters).
Requires significant RAM (~64GB for all-GB graph — needs a cloud VM).

**GTFS (General Transit Feed Specification)**
Standard format for transit timetable data. For GB:
- Bus: Traveline National Dataset (freely available, GTFS format)
- Rail: ATOC CIF format from Rail Delivery Group → must convert to GTFS
  using the UK2GTFS R package

**Isochrone**
A polygon showing the area reachable within a given travel time from a point.
e.g. "All UK forests reachable within 2 hours by train from London Waterloo."
OTP can generate these; they are the key visualisation for the article.

**PMTiles**
A single-file format for vector tile pyramids. Alternative to serving raw GeoJSON —
the browser only loads tiles for the current viewport. Better performance than
GeoJSON for large datasets, but more complex to generate and serve.
*Use this if the processed cluster GeoJSON exceeds ~15MB.*

**Upstash Redis**
Serverless Redis (key-value cache) with a free tier. Used to cache Google API
responses (Places, Routes) server-side in Vercel, preventing repeated billing
for the same forest lookup.

---

## Technology Stack Summary

| Layer | Choice | Reason |
|---|---|---|
| Web framework | Next.js 15 (App Router) | Server routes protect API keys; Vercel native |
| Map | Leaflet.js via react-leaflet | Free, OSM tiles, GeoJSON support |
| Styling | Tailwind CSS | Fast utility-first CSS |
| Language | TypeScript | Type safety, good autocomplete |
| Hosting | Vercel (Hobby free tier) | Auto-deploy from GitHub |
| Cache | Upstash Redis (free tier) | Persistent server-side API response cache |
| Transit routing (app) | Google Routes API v2 (transit) | Live, per-user routing, covered by $200 credit |
| Transit routing (analysis) | OpenTripPlanner + GTFS | Bulk, reproducible, publishable methodology |
| Reviews + photos | Google Places API (New) | Reviews and photos for forest POIs |
| Forest data | Forestry Commission NFI | Open Government Licence, species composition |
| Clustering | scikit-learn DBSCAN / HDBSCAN | Python, well-documented, reproducible |
| Analysis environment | Jupyter notebooks (Python) | Standard data science workflow |
| Dataset release | Zenodo (DOI) | Citable, persistent, free for open data |

---

## Folder Structure

```
Conifer_holiday/
├── app/                        ← Next.js web app (Vercel deploys from here)
│   ├── app/                    ← App Router pages + API routes
│   ├── components/
│   ├── public/data/            ← Symlink or copy from data/output/
│   └── package.json
├── analysis/
│   ├── notebooks/              ← Jupyter notebooks (EDA → clustering → accessibility)
│   ├── scripts/                ← Promoted, reusable Python scripts
│   └── requirements.txt
├── data/
│   ├── raw/                    ← gitignored — NFI shapefiles, downloaded zips
│   ├── processed/              ← gitignored — intermediate pipeline files
│   └── output/                 ← committed — clusters.geojson, travel_time_matrix.csv
├── docs/                       ← Project documentation (this folder)
│   ├── INDEX.md                ← You are here
│   ├── APP_PLAN.md
│   └── ANALYSIS_PLAN.md
└── .gitignore
```

**Data flow:** `data/raw/` → analysis notebooks → `data/processed/` → `data/output/` → `app/public/data/`

---

## Project Phases

```
Phase 0   Data pipeline          Download NFI → filter → cluster → export
Phase 1   App scaffold           Next.js + Leaflet map + OSM tiles
Phase 2   Map layer              Cluster polygons on map, filters
Phase 3   Sidebar                Click forest → info panel
Phase 4   Google Places          Reviews + photos via server proxy
Phase 5   Transit routing        Journey time from London via server proxy
Phase 6   Polish + deploy        Vercel deployment, API key restrictions
---
Analysis  Clustering notebook    DBSCAN tuning, validation, characterisation
Analysis  Accessibility          OTP setup (cloud VM), travel time matrix
Analysis  Publication            Article, Zenodo dataset, open-source repo
```

---

## Key Decisions and Why

**Why clusters instead of raw NFI polygons?**
Raw NFI has 344,000+ polygons. Even filtered to conifer types (>10ha), you get
thousands of polygons. Leaflet cannot render this on mobile. DBSCAN clustering
dissolves nearby patches into ~100–300 named forest blocks — both solving the
performance problem and producing a genuinely useful dataset as a side effect.

**Why Next.js instead of plain HTML/JS?**
Google API keys must never reach the browser (financial risk on a public app).
Next.js Route Handlers proxy all Google calls server-side. The key lives only
in Vercel environment variables.

**Why Leaflet instead of Google Maps JS?**
Google Maps JS API requires an API key loaded in the browser. Leaflet uses
free OpenStreetMap tiles with no key. Google APIs are used only server-side
for routing and Places data.

**Why OTP for analysis and Google for the app?**
Google Maps routing cannot be used in a published methodology (black box, not
reproducible). OTP + open GTFS data is fully transparent and citable.
For the live app, Google is better UX (real-time, accurate).

**Why Zenodo for dataset release?**
Zenodo assigns a DOI, making the dataset formally citable in academic papers.
HuggingFace Datasets is an alternative for ML-community visibility.

---

## External Resources

| Resource | URL / Notes |
|---|---|
| NFI data download | https://data-forestry.opendata.arcgis.com |
| NFI field definitions | Forestry Commission NFI technical documentation |
| OTP4GB project (ODI Leeds) | https://github.com/odileeds/OTP4GB — GB-specific OTP setup |
| UK2GTFS (rail CIF→GTFS) | https://itsleeds.github.io/UK2GTFS/ |
| Traveline GTFS (buses) | https://data.bus-data.dft.gov.uk |
| Mapshaper (browser simplify) | https://mapshaper.org |
| Google Cloud Console | https://console.cloud.google.com |
| Upstash (Redis free tier) | https://upstash.com |
| Zenodo (dataset release) | https://zenodo.org |
| MAGIC (DEFRA forest viewer) | https://magic.defra.gov.uk — existing government tool for reference |

---

## Status

| Document | Status |
|---|---|
| INDEX.md | Done — this file |
| APP_PLAN.md | Done — ready to implement |
| ANALYSIS_PLAN.md | Done — ready for analysis phase |
| App implementation | Not started |
| Data pipeline | Not started |
| Clustering analysis | Not started |
