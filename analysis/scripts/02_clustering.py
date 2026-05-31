"""
NFI Woodland GB 2023 — Spatial Clustering (HDBSCAN primary, DBSCAN validation)

Success criteria (Rule 1 — set before running):
  - Thetford (E:580000–610000, N:280000–300000): 1–3 clusters
  - Kielder  (E:360000–400000, N:580000–620000): 1–3 clusters
  - Total labelled clusters: 80–400
  - Noise polygons: < 15% of input (< 2,015)
  - No single cluster: > 10% of input polygons (> 1,344)
  - Scotland (N > 550000): no single cluster > 20% of input (> 2,687)
  - Wales (E:220000–360000, N:170000–390000): >= 5 distinct clusters
  - Median polygons per cluster: 5–80

Source: NFI Woodland GB 2023, Forestry Commission via ArcGIS Hub, accessed 2026-05-23
"""

import json
import os
import sys
import time
from pathlib import Path

import geopandas as gpd
import hdbscan
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
NFI_FILE     = PROJECT_ROOT / "data" / "raw" / "National_Forest_Inventory_GB_2023.shp"
OUTPUT_DIR   = PROJECT_ROOT / "data" / "output"
CLUSTER_DIR  = OUTPUT_DIR / "clustering"
CLUSTER_DIR.mkdir(parents=True, exist_ok=True)
FIGURES_DIR  = CLUSTER_DIR / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

# ── Filter parameters (from EDA — Rule 4: documented why) ─────────────────────
TYPE_FIELD    = "IFT_IOA"
CONIFER_TYPES = ["Conifer", "Mixed mainly conifer"]
AREA_MIN_HA   = 10  # exclude patches too small to be destinations

# ── HDBSCAN parameters (primary algorithm — Rule 4) ───────────────────────────
# min_cluster_size=5: min ~50ha connected forest to form a destination cluster
# min_samples=3: generous core-point assignment; handles sparse Welsh forests
# cluster_selection_method='eom': prevents over-fragmentation of large forests (Kielder)
HDBSCAN_PARAMS = {
    "min_cluster_size": 5,
    "min_samples": 3,
    "cluster_selection_method": "eom",
    "metric": "euclidean",  # valid: EPSG:27700 units are metres
}

# ── DBSCAN parameters (validation cross-check) ────────────────────────────────
# eps=2500m: within-forest compartments typically 500–1500m apart centroid-to-centroid
# min_samples=3: consistent with HDBSCAN; rejects isolated single-patch noise
DBSCAN_PARAMS = {
    "eps": 2500,
    "min_samples": 3,
}

# ── Success criteria bounding boxes (EPSG:27700) ──────────────────────────────
THETFORD_BOX = (580_000, 280_000, 610_000, 300_000)  # minx, miny, maxx, maxy
KIELDER_BOX  = (360_000, 580_000, 400_000, 620_000)
WALES_BOX    = (220_000, 170_000, 360_000, 390_000)
SCOTLAND_MIN_NORTHING = 550_000

N_INPUT = 13_434  # from EDA — used for success-criteria thresholds


def log(msg):
    print(msg, flush=True)


def clusters_in_box(gdf, label_col, box):
    """Count distinct non-noise cluster labels whose centroids fall within a bounding box."""
    minx, miny, maxx, maxy = box
    cx = gdf.geometry.centroid.x
    cy = gdf.geometry.centroid.y
    mask = (cx >= minx) & (cx <= maxx) & (cy >= miny) & (cy <= maxy) & (gdf[label_col] != -1)
    return gdf.loc[mask, label_col].nunique()


def check_success_criteria(gdf, label_col, algo_name):
    """Evaluate all pre-declared success criteria. Returns True if all pass."""
    log(f"\n--- Success criteria check: {algo_name} ---")
    labels = gdf[label_col]
    n_total = len(gdf)
    n_noise = int((labels == -1).sum())
    noise_pct = n_noise / n_total * 100
    n_clusters = int(labels[labels != -1].nunique())
    cluster_sizes = labels[labels != -1].value_counts()
    max_cluster_pct = cluster_sizes.iloc[0] / n_total * 100 if len(cluster_sizes) else 0
    median_cluster_size = float(cluster_sizes.median()) if len(cluster_sizes) else 0

    scotland_mask = (gdf.geometry.centroid.y > SCOTLAND_MIN_NORTHING) & (labels != -1)
    scotland_sizes = labels[scotland_mask].value_counts()
    max_scotland_pct = scotland_sizes.iloc[0] / n_total * 100 if len(scotland_sizes) else 0

    thetford_n = clusters_in_box(gdf, label_col, THETFORD_BOX)
    kielder_n  = clusters_in_box(gdf, label_col, KIELDER_BOX)
    wales_n    = clusters_in_box(gdf, label_col, WALES_BOX)

    checks = [
        ("Total clusters 80–400",         80 <= n_clusters <= 400,             f"{n_clusters}"),
        ("Noise < 15%",                    noise_pct < 15,                      f"{noise_pct:.1f}%"),
        ("Max cluster < 10% of input",     max_cluster_pct < 10,                f"{max_cluster_pct:.1f}%"),
        ("Scotland max cluster < 20%",     max_scotland_pct < 20,               f"{max_scotland_pct:.1f}%"),
        ("Thetford 1–3 clusters",          1 <= thetford_n <= 3,                f"{thetford_n}"),
        ("Kielder 1–3 clusters",           1 <= kielder_n <= 3,                 f"{kielder_n}"),
        ("Wales >= 5 clusters",            wales_n >= 5,                        f"{wales_n}"),
        ("Median cluster size 5–80",       5 <= median_cluster_size <= 80,      f"{median_cluster_size:.0f}"),
    ]

    passed = 0
    for name, ok, actual in checks:
        status = "PASS" if ok else "FAIL"
        log(f"  [{status}] {name}: {actual}")
        if ok:
            passed += 1

    log(f"\n  {passed}/{len(checks)} criteria passed")
    all_pass = passed == len(checks)
    if not all_pass:
        log("  WARNING: not all criteria met — review parameters before using output")
    return all_pass, {
        "n_clusters": n_clusters,
        "noise_pct": round(noise_pct, 2),
        "max_cluster_pct": round(max_cluster_pct, 2),
        "max_scotland_pct": round(max_scotland_pct, 2),
        "thetford_clusters": thetford_n,
        "kielder_clusters": kielder_n,
        "wales_clusters": wales_n,
        "median_cluster_size": round(median_cluster_size, 1),
        "all_pass": all_pass,
    }


# ── Load + filter ──────────────────────────────────────────────────────────────
log("Loading NFI shapefile...")
gdf_raw = gpd.read_file(NFI_FILE)
log(f"Loaded {len(gdf_raw):,} polygons | CRS: {gdf_raw.crs}")
assert gdf_raw.crs.to_epsg() == 27700, "Expected EPSG:27700"

gdf_raw["area_ha"] = gdf_raw.geometry.area / 10_000

gdf = gdf_raw[
    gdf_raw[TYPE_FIELD].isin(CONIFER_TYPES) &
    (gdf_raw["area_ha"] >= AREA_MIN_HA)
].copy().reset_index(drop=True)

log(f"After filter: {len(gdf):,} polygons")

# Fix invalid geometries (332 found in EDA) — buffer(0) is the standard repair
gdf.geometry = gdf.geometry.buffer(0)
assert gdf.geometry.is_valid.all(), "Geometries still invalid after buffer(0)"
log("Geometry fix applied and validated")

# Centroid coordinates for clustering (EPSG:27700, metres)
centroids = gdf.geometry.centroid
coords = np.column_stack([centroids.x, centroids.y])
log(f"Centroid array shape: {coords.shape}")


# ── HDBSCAN (primary) ──────────────────────────────────────────────────────────
log(f"\n=== HDBSCAN (primary) — params: {HDBSCAN_PARAMS} ===")
t0 = time.time()
clusterer = hdbscan.HDBSCAN(**HDBSCAN_PARAMS)
hdb_labels = clusterer.fit_predict(coords)
log(f"HDBSCAN finished in {time.time() - t0:.1f}s")
log(f"Unique labels: {np.unique(hdb_labels).shape[0]} (including -1 noise)")

gdf["hdb_label"] = hdb_labels
hdb_pass, hdb_metrics = check_success_criteria(gdf, "hdb_label", "HDBSCAN")


# ── DBSCAN (validation cross-check) ───────────────────────────────────────────
log(f"\n=== DBSCAN (validation) — params: {DBSCAN_PARAMS} ===")
t0 = time.time()
db = DBSCAN(**DBSCAN_PARAMS)
db_labels = db.fit_predict(coords)
log(f"DBSCAN finished in {time.time() - t0:.1f}s")
log(f"Unique labels: {np.unique(db_labels).shape[0]} (including -1 noise)")

gdf["db_label"] = db_labels
db_pass, db_metrics = check_success_criteria(gdf, "db_label", "DBSCAN")


# ── Sensitivity analysis ───────────────────────────────────────────────────────
log("\n=== Sensitivity analysis ===")

# HDBSCAN sensitivity: vary min_cluster_size and min_samples
hdb_sens_rows = []
for mcs in [3, 5, 8, 10, 15, 20]:
    for ms in [1, 3, 5]:
        params = {"min_cluster_size": mcs, "min_samples": ms,
                  "cluster_selection_method": "eom", "metric": "euclidean"}
        lbl = hdbscan.HDBSCAN(**params).fit_predict(coords)
        n_noise = int((lbl == -1).sum())
        n_clusters = int(np.unique(lbl[lbl != -1]).shape[0])
        thetford_tmp = gpd.GeoDataFrame({"lbl": lbl}, geometry=gdf.geometry)
        thetford_n   = clusters_in_box(thetford_tmp, "lbl", THETFORD_BOX)
        kielder_n    = clusters_in_box(thetford_tmp, "lbl", KIELDER_BOX)
        hdb_sens_rows.append({
            "min_cluster_size": mcs, "min_samples": ms,
            "n_clusters": n_clusters,
            "noise_pct": round(n_noise / len(gdf) * 100, 1),
            "thetford_clusters": thetford_n,
            "kielder_clusters": kielder_n,
        })
        log(f"  HDBSCAN mcs={mcs} ms={ms}: {n_clusters} clusters, {n_noise/len(gdf)*100:.1f}% noise")

hdb_sens_df = pd.DataFrame(hdb_sens_rows)
hdb_sens_df.to_csv(CLUSTER_DIR / "sensitivity_hdbscan.csv", index=False)
log("Saved: sensitivity_hdbscan.csv")

# DBSCAN sensitivity: vary eps
db_sens_rows = []
for eps in [1000, 1500, 2000, 2500, 3000, 3500, 5000]:
    lbl = DBSCAN(eps=eps, min_samples=3).fit_predict(coords)
    n_noise = int((lbl == -1).sum())
    n_clusters = int(np.unique(lbl[lbl != -1]).shape[0])
    tmp = gpd.GeoDataFrame({"lbl": lbl}, geometry=gdf.geometry)
    db_sens_rows.append({
        "eps_m": eps, "min_samples": 3,
        "n_clusters": n_clusters,
        "noise_pct": round(n_noise / len(gdf) * 100, 1),
        "thetford_clusters": clusters_in_box(tmp, "lbl", THETFORD_BOX),
        "kielder_clusters":  clusters_in_box(tmp, "lbl", KIELDER_BOX),
    })
    log(f"  DBSCAN eps={eps}m: {n_clusters} clusters, {n_noise/len(gdf)*100:.1f}% noise")

db_sens_df = pd.DataFrame(db_sens_rows)
db_sens_df.to_csv(CLUSTER_DIR / "sensitivity_dbscan.csv", index=False)
log("Saved: sensitivity_dbscan.csv")

# Sensitivity plots
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

axes[0].plot(db_sens_df["eps_m"], db_sens_df["n_clusters"], "o-", color="steelblue", label="Cluster count")
ax2 = axes[0].twinx()
ax2.plot(db_sens_df["eps_m"], db_sens_df["noise_pct"], "s--", color="tomato", label="Noise %")
axes[0].set_xlabel("eps (metres)")
axes[0].set_ylabel("Cluster count", color="steelblue")
ax2.set_ylabel("Noise %", color="tomato")
axes[0].set_title("DBSCAN sensitivity — eps vs cluster count / noise")
axes[0].axvline(DBSCAN_PARAMS["eps"], color="grey", linestyle=":", label=f"Chosen eps={DBSCAN_PARAMS['eps']}m")
axes[0].legend(loc="upper right")

for ms in [1, 3, 5]:
    sub = hdb_sens_df[hdb_sens_df["min_samples"] == ms]
    axes[1].plot(sub["min_cluster_size"], sub["n_clusters"], "o-", label=f"min_samples={ms}")
axes[1].set_xlabel("min_cluster_size")
axes[1].set_ylabel("Cluster count")
axes[1].set_title("HDBSCAN sensitivity — min_cluster_size vs cluster count")
axes[1].axvline(HDBSCAN_PARAMS["min_cluster_size"], color="grey", linestyle=":", label=f"Chosen mcs={HDBSCAN_PARAMS['min_cluster_size']}")
axes[1].legend()

plt.tight_layout()
fig.savefig(FIGURES_DIR / "04_sensitivity.png", dpi=150)
plt.close(fig)
log("Saved: 04_sensitivity.png")


# ── Cluster map plots ──────────────────────────────────────────────────────────
for label_col, algo_name, fname in [
    ("hdb_label", "HDBSCAN", "05_clusters_hdbscan.png"),
    ("db_label",  "DBSCAN",  "06_clusters_dbscan.png"),
]:
    n_clusters = gdf[label_col][gdf[label_col] != -1].nunique()
    fig, ax = plt.subplots(figsize=(8, 12))
    noise = gdf[gdf[label_col] == -1]
    clustered = gdf[gdf[label_col] != -1]
    ax.scatter(
        clustered.geometry.centroid.x, clustered.geometry.centroid.y,
        c=clustered[label_col] % 40, cmap="tab20", s=3, alpha=0.7, label="clustered"
    )
    ax.scatter(
        noise.geometry.centroid.x, noise.geometry.centroid.y,
        c="lightgrey", s=1, alpha=0.3, label="noise"
    )
    ax.set_title(f"{algo_name}: {n_clusters} clusters")
    ax.set_xlabel("Easting (m)")
    ax.set_ylabel("Northing (m)")
    ax.set_aspect("equal")
    ax.legend(markerscale=3)
    plt.tight_layout()
    fig.savefig(FIGURES_DIR / fname, dpi=150)
    plt.close(fig)
    log(f"Saved: {fname}")


# ── Dissolve and export (use HDBSCAN labels as primary) ───────────────────────
log("\n=== Dissolve + export ===")

# Use HDBSCAN as primary; flag if criteria not met
LABEL_COL = "hdb_label"
if not hdb_pass:
    log("WARNING: HDBSCAN did not meet all success criteria — output saved but review needed")

clustered_gdf = gdf[gdf[LABEL_COL] != -1].copy()
log(f"Dissolving {len(clustered_gdf):,} polygons into clusters...")

dissolved = clustered_gdf.dissolve(
    by=LABEL_COL,
    aggfunc={
        TYPE_FIELD: lambda x: x.mode().iloc[0],  # dominant species type
        "area_ha": "sum",                         # total forest area
    }
).reset_index()

dissolved["polygon_count"] = clustered_gdf.groupby(LABEL_COL).size().values
dissolved["cluster_id"] = ["cluster_{:04d}".format(int(i)) for i in dissolved[LABEL_COL]]
dissolved["dominant_type"] = dissolved[TYPE_FIELD]
dissolved["total_area_ha"] = dissolved["area_ha"].round(1)

# Centroids in WGS84 for Leaflet markers
centroids_wgs = dissolved.geometry.centroid.to_crs(4326)
dissolved["centroid_lat"] = centroids_wgs.y.round(6)
dissolved["centroid_lon"] = centroids_wgs.x.round(6)

# Reproject to WGS84 — Rule 3: web display requires EPSG:4326
dissolved_wgs = dissolved.to_crs(epsg=4326)
assert dissolved_wgs.crs.to_epsg() == 4326

# Keep only the fields the web app needs
output_cols = ["cluster_id", LABEL_COL, "dominant_type", "total_area_ha",
               "polygon_count", "centroid_lat", "centroid_lon", "geometry"]
dissolved_wgs = dissolved_wgs[output_cols]

# File size check
output_path = OUTPUT_DIR / "clusters.geojson"
dissolved_wgs.to_file(output_path, driver="GeoJSON")
size_mb = os.path.getsize(output_path) / 1_048_576
log(f"Output: {output_path}")
log(f"File size: {size_mb:.2f} MB")

if size_mb > 5.0:
    log(f"File exceeds 5MB ({size_mb:.2f} MB) — applying geometry simplification")
    dissolved_wgs.geometry = dissolved_wgs.geometry.simplify(
        tolerance=0.0001,  # ~10m at UK latitudes; preserves visual accuracy
        preserve_topology=True
    )
    dissolved_wgs.to_file(output_path, driver="GeoJSON")
    size_mb = os.path.getsize(output_path) / 1_048_576
    log(f"After simplification: {size_mb:.2f} MB")

assert size_mb < 20.0, f"GeoJSON still too large ({size_mb:.2f} MB) — further simplification needed"


# ── Save full results summary ──────────────────────────────────────────────────
results = {
    "hdbscan": {
        "params": HDBSCAN_PARAMS,
        "metrics": hdb_metrics,
        "criteria_pass": hdb_pass,
    },
    "dbscan": {
        "params": DBSCAN_PARAMS,
        "metrics": db_metrics,
        "criteria_pass": db_pass,
    },
    "output": {
        "file": str(output_path),
        "size_mb": round(size_mb, 3),
        "n_clusters": len(dissolved_wgs),
        "algorithm_used": "hdbscan",
    },
    "sensitivity": {
        "hdbscan_csv": str(CLUSTER_DIR / "sensitivity_hdbscan.csv"),
        "dbscan_csv": str(CLUSTER_DIR / "sensitivity_dbscan.csv"),
    }
}

with open(CLUSTER_DIR / "clustering_results.json", "w") as f:
    json.dump(results, f, indent=2)

log(f"\nSaved: {CLUSTER_DIR / 'clustering_results.json'}")
log("\n=== CLUSTERING COMPLETE ===")
log(f"Primary output: {output_path}  ({size_mb:.2f} MB)")
log(f"Clusters:       {len(dissolved_wgs)}")
log(f"Figures:        {FIGURES_DIR}")
