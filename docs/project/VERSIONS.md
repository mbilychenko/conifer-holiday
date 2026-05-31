# Version History

---

## v0.1 — Working map with DBSCAN cluster layer
**Tagged:** 2026-05-31

### What this version is
A functional Next.js web app displaying 100 spatial clusters of UK conifer/mixed
woodland on an interactive Leaflet map. The data layer is produced by a DBSCAN
clustering pipeline run over the NFI (National Forest Inventory) Woodland GB 2023
dataset. This version is a proof-of-concept for the map interface and the
geospatial clustering methodology.

### App features (app/)
- Interactive Leaflet map centred on Great Britain, zoom 5
- 100 cluster polygons from `clusters.geojson` with fill colour by forest type
- Circle markers at each cluster centroid; click to open sidebar
- Sidebar: forest name, hectares, type chip, country
- FilterBar: All / Conifer / Mixed toggle chips
- Cluster colour mode: each cluster a unique hue (golden-angle HSL spread);
  scrollable panel to hide/show individual clusters — exploration tool, to be
  removed before v1.0
- All Google API calls proxied server-side (route handlers); key never in browser
- Upstash Redis dependency present but not yet wired (deferred to transit routing)

### Data files committed
- `app/public/data/clusters.geojson` — 100 dissolved cluster polygons
- `app/public/data/clusters_meta.json` — cluster metadata (id, name, country,
  type, hectares, polygon_count, centroid lat/lng)
- `data/output/clusters.geojson` — same file, canonical location
- `data/output/clusters_meta.json` — same file, canonical location
- `data/output/clustering/` — algorithm comparison, sensitivity analysis,
  validation metrics, final winner selection logs
- `data/output/eda/` — EDA summary and figures

### Known limitations of this version
- Cluster names like "Near Newton Stewart" are geographic labels, not visitor
  destinations. Many clusters contain multiple distinct named forests that should
  each be a separate entity.
- No Google Places data wired up yet (reviews, photos, ratings).
- No transit routing.
- The cluster is the wrong atomic unit for trip planning — it is a spatial
  aggregation unit, not a visitor destination.

### Why v0.1 and not v1.0
The data model needs to change before this is a useful app. v0.2 will replace
the cluster-as-destination model with OSM-derived named forest destinations
enumerated within each cluster zone. See APP_PLAN.md for the next steps.

---

## v0.2 — OSM destination layer (planned)
- OSM Overpass query per cluster polygon → named forest destinations
- Each destination: own polygon, own Google Place (reviews, photos, rating, link)
- Car park locations from OSM `amenity=parking`
- `destinations.geojson` replaces `clusters.geojson` as the primary map layer
- Cluster polygons become background zones, not clickable entities
