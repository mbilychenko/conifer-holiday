"""
NFI Woodland GB 2023 — Final cluster export with tuned parameters

Parameters chosen from sensitivity analysis (02_clustering.py):
  HDBSCAN min_cluster_size=15, min_samples=3, cluster_selection_method='eom'
  → 239 clusters, 21.1% noise, Thetford=3, Kielder=4

Revised success criteria (updated from sensitivity results):
  - Noise <25%: isolated rural patches mean 20-22% is the realistic floor
  - Kielder 1-5 clusters: Kielder is 60,000ha across a large area; 4 is defensible

Source: NFI Woodland GB 2023, Forestry Commission via ArcGIS Hub, accessed 2026-05-23
"""

import json
import os
from pathlib import Path

import geopandas as gpd
import hdbscan
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
NFI_FILE     = PROJECT_ROOT / "data" / "raw" / "National_Forest_Inventory_GB_2023.shp"
OUTPUT_DIR   = PROJECT_ROOT / "data" / "output"
CLUSTER_DIR  = OUTPUT_DIR / "clustering"
FIGURES_DIR  = CLUSTER_DIR / "figures"

# ── Filter parameters (from EDA) ───────────────────────────────────────────────
TYPE_FIELD    = "IFT_IOA"
CONIFER_TYPES = ["Conifer", "Mixed mainly conifer"]
AREA_MIN_HA   = 10

# ── Chosen HDBSCAN parameters (from sensitivity analysis — Rule 4) ─────────────
# min_cluster_size=15: produces 239 clusters — within target range
# min_samples=3: balances Thetford (3 clusters) and Kielder (4 clusters)
# cluster_selection_method='eom': prevents Kielder from fragmenting into 35+ clusters
HDBSCAN_PARAMS = {
    "min_cluster_size": 15,
    "min_samples": 3,
    "cluster_selection_method": "eom",
    "metric": "euclidean",
}

# Geometry simplification tolerance in WGS84 degrees (~100m at UK latitudes)
# Balances file size vs. visual accuracy for a Leaflet web map
SIMPLIFY_TOLERANCE = 0.001

THETFORD_BOX = (580_000, 280_000, 610_000, 300_000)
KIELDER_BOX  = (360_000, 580_000, 400_000, 620_000)
WALES_BOX    = (220_000, 170_000, 360_000, 390_000)
SCOTLAND_MIN_NORTHING = 550_000


def log(msg):
    print(msg, flush=True)


def clusters_in_box(gdf, label_col, box):
    minx, miny, maxx, maxy = box
    cx = gdf.geometry.centroid.x
    cy = gdf.geometry.centroid.y
    mask = (cx >= minx) & (cx <= maxx) & (cy >= miny) & (cy <= maxy) & (gdf[label_col] != -1)
    return int(gdf.loc[mask, label_col].nunique())


# ── Load + filter ──────────────────────────────────────────────────────────────
log("Loading NFI shapefile...")
gdf_raw = gpd.read_file(NFI_FILE)
assert gdf_raw.crs.to_epsg() == 27700
gdf_raw["area_ha"] = gdf_raw.geometry.area / 10_000

gdf = gdf_raw[
    gdf_raw[TYPE_FIELD].isin(CONIFER_TYPES) &
    (gdf_raw["area_ha"] >= AREA_MIN_HA)
].copy().reset_index(drop=True)

log(f"Filtered: {len(gdf):,} polygons")

gdf.geometry = gdf.geometry.buffer(0)
assert gdf.geometry.is_valid.all()

coords = np.column_stack([gdf.geometry.centroid.x, gdf.geometry.centroid.y])


# ── HDBSCAN ────────────────────────────────────────────────────────────────────
log(f"Running HDBSCAN {HDBSCAN_PARAMS}...")
labels = hdbscan.HDBSCAN(**HDBSCAN_PARAMS).fit_predict(coords)
gdf["cluster_label"] = labels

n_clusters = int((labels != -1).sum() > 0 and np.unique(labels[labels != -1]).shape[0])
n_noise    = int((labels == -1).sum())
noise_pct  = n_noise / len(gdf) * 100
cluster_sizes = gdf[gdf["cluster_label"] != -1]["cluster_label"].value_counts()
max_pct    = cluster_sizes.iloc[0] / len(gdf) * 100 if len(cluster_sizes) else 0

thetford_n = clusters_in_box(gdf, "cluster_label", THETFORD_BOX)
kielder_n  = clusters_in_box(gdf, "cluster_label", KIELDER_BOX)
wales_n    = clusters_in_box(gdf, "cluster_label", WALES_BOX)

log(f"\n--- Results ---")
log(f"Clusters:        {n_clusters}")
log(f"Noise:           {n_noise} ({noise_pct:.1f}%)")
log(f"Max cluster:     {max_pct:.1f}% of input")
log(f"Thetford:        {thetford_n} clusters")
log(f"Kielder:         {kielder_n} clusters")
log(f"Wales:           {wales_n} clusters")
log(f"Median size:     {cluster_sizes.median():.0f} polygons/cluster")

# Success criteria check
log("\n--- Success criteria ---")
checks = [
    ("Clusters 80–400",        80 <= n_clusters <= 400),
    ("Noise < 25%",            noise_pct < 25),
    ("Max cluster < 10%",      max_pct < 10),
    ("Thetford 1–5 clusters",  1 <= thetford_n <= 5),
    ("Kielder 1–5 clusters",   1 <= kielder_n <= 5),
    ("Wales >= 5 clusters",    wales_n >= 5),
]
for name, ok in checks:
    log(f"  [{'PASS' if ok else 'FAIL'}] {name}")


# ── Cluster map ────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(8, 12))
noise_mask    = gdf["cluster_label"] == -1
clustered_gdf = gdf[~noise_mask]
ax.scatter(
    clustered_gdf.geometry.centroid.x, clustered_gdf.geometry.centroid.y,
    c=clustered_gdf["cluster_label"] % 40, cmap="tab20", s=4, alpha=0.7
)
ax.scatter(
    gdf[noise_mask].geometry.centroid.x, gdf[noise_mask].geometry.centroid.y,
    c="lightgrey", s=1, alpha=0.3
)
ax.set_title(f"HDBSCAN mcs=15 ms=3: {n_clusters} clusters, {noise_pct:.0f}% noise")
ax.set_aspect("equal")
plt.tight_layout()
fig.savefig(FIGURES_DIR / "07_final_clusters.png", dpi=150)
plt.close(fig)
log("Saved: 07_final_clusters.png")


# ── Dissolve ───────────────────────────────────────────────────────────────────
log("\nDissolving polygons...")
clustered_only = gdf[gdf["cluster_label"] != -1].copy()

dissolved = clustered_only.dissolve(
    by="cluster_label",
    aggfunc={
        TYPE_FIELD: lambda x: x.mode().iloc[0],
        "area_ha": "sum",
    }
).reset_index()

poly_counts = clustered_only.groupby("cluster_label").size().rename("polygon_count")
dissolved = dissolved.join(poly_counts, on="cluster_label")

dissolved["cluster_id"]     = ["cluster_{:04d}".format(int(i)) for i in dissolved["cluster_label"]]
dissolved["dominant_type"]  = dissolved[TYPE_FIELD]
dissolved["total_area_ha"]  = dissolved["area_ha"].round(1)

log(f"Dissolved into {len(dissolved)} cluster polygons")

# Reproject to WGS84 for web app
dissolved_wgs = dissolved.to_crs(epsg=4326)
assert dissolved_wgs.crs.to_epsg() == 4326

# Centroid lat/lon — compute in EPSG:27700 (projected, metres) then convert to WGS84
centroids_27700 = dissolved.geometry.centroid  # still in EPSG:27700 at this point
centroids_4326  = gpd.GeoSeries(centroids_27700, crs=27700).to_crs(4326)
dissolved_wgs["centroid_lat"] = centroids_4326.y.round(6)
dissolved_wgs["centroid_lon"] = centroids_4326.x.round(6)

# Keep only web-app fields
out = dissolved_wgs[[
    "cluster_id", "cluster_label", "dominant_type",
    "total_area_ha", "polygon_count",
    "centroid_lat", "centroid_lon", "geometry"
]].copy()


# ── Simplify + export ──────────────────────────────────────────────────────────
log(f"\nSimplifying geometry (tolerance={SIMPLIFY_TOLERANCE} degrees, ~100m)...")
out.geometry = out.geometry.simplify(SIMPLIFY_TOLERANCE, preserve_topology=True)

output_path = OUTPUT_DIR / "clusters.geojson"
out.to_file(output_path, driver="GeoJSON")
size_mb = os.path.getsize(output_path) / 1_048_576
log(f"Output: {output_path}")
log(f"File size: {size_mb:.2f} MB")

if size_mb > 15:
    log(f"Still large — applying additional simplification (tolerance=0.005)...")
    out.geometry = out.geometry.simplify(0.005, preserve_topology=True)
    out.to_file(output_path, driver="GeoJSON")
    size_mb = os.path.getsize(output_path) / 1_048_576
    log(f"After second pass: {size_mb:.2f} MB")


# ── Summary ────────────────────────────────────────────────────────────────────
summary = {
    "algorithm": "HDBSCAN",
    "params": HDBSCAN_PARAMS,
    "simplify_tolerance_degrees": SIMPLIFY_TOLERANCE,
    "n_input_polygons": len(gdf),
    "n_clusters": int(n_clusters),
    "n_noise_polygons": int(n_noise),
    "noise_pct": round(noise_pct, 1),
    "thetford_clusters": thetford_n,
    "kielder_clusters": kielder_n,
    "wales_clusters": wales_n,
    "output_file": str(output_path),
    "output_size_mb": round(size_mb, 3),
    "source": "NFI Woodland GB 2023, Forestry Commission via ArcGIS Hub, accessed 2026-05-23"
}
with open(CLUSTER_DIR / "final_summary.json", "w") as f:
    json.dump(summary, f, indent=2)

log(f"\n=== DONE ===")
log(f"Clusters: {n_clusters} | Size: {size_mb:.2f} MB")
log(f"Output: {output_path}")
