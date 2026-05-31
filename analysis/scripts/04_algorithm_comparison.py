"""
NFI Woodland GB 2023 — Multi-Algorithm Clustering Comparison

Compares 4 approaches against the HDBSCAN baseline:
  A. Graph + Louvain community detection
  B. SKATER (Spatial K-cluster Analysis by Tree Edge Removal)
  C. Max-P Regionalization
  D. AgglomerativeClustering with spatial connectivity matrix

Key design decision: proximity graph (patches within 2,500m), NOT contiguity graph.
NFI forest patches are NOT physically touching — rides, roads, and gaps separate them.
Distance 2,500m matches the HDBSCAN baseline eps for a fair comparison.

Source: NFI Woodland GB 2023, Forestry Commission via ArcGIS Hub, accessed 2026-05-23
"""

import json
import os
import time
import warnings
from pathlib import Path

import community as community_louvain  # python-louvain
import geopandas as gpd
import hdbscan
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from scipy.sparse import csr_matrix
from sklearn.cluster import AgglomerativeClustering
from spopt.region import Skater, MaxPHeuristic
import libpysal

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
NFI_FILE     = PROJECT_ROOT / "data" / "raw" / "National_Forest_Inventory_GB_2023.shp"
OUTPUT_DIR   = PROJECT_ROOT / "data" / "output"
CLUSTER_DIR  = OUTPUT_DIR / "clustering"
FIGURES_DIR  = CLUSTER_DIR / "figures"
CLUSTER_DIR.mkdir(parents=True, exist_ok=True)
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

# ── Filter parameters ──────────────────────────────────────────────────────────
TYPE_FIELD    = "IFT_IOA"
CONIFER_TYPES = ["Conifer", "Mixed mainly conifer"]
AREA_MIN_HA   = 10

# ── Proximity graph threshold (metres, EPSG:27700) ────────────────────────────
# 2,500m matches HDBSCAN baseline eps — ensures fair comparison
PROXIMITY_M = 2500

# ── Success criteria bounding boxes (EPSG:27700) ──────────────────────────────
THETFORD_BOX = (580_000, 280_000, 610_000, 300_000)
KIELDER_BOX  = (360_000, 580_000, 400_000, 620_000)
WALES_BOX    = (220_000, 170_000, 360_000, 390_000)


def log(msg):
    print(msg, flush=True)


def clusters_in_box(cx, cy, labels, box):
    minx, miny, maxx, maxy = box
    mask = (cx >= minx) & (cx <= maxx) & (cy >= miny) & (cy <= maxy) & (labels != -1)
    return int(np.unique(labels[mask]).shape[0]) if mask.sum() > 0 else 0


def score(labels, cx, cy, name):
    """Compute all success-criteria metrics for a label array."""
    n = len(labels)
    valid = labels[labels != -1]
    n_clusters = int(np.unique(valid).shape[0]) if len(valid) else 0
    n_noise = int((labels == -1).sum())
    noise_pct = round(n_noise / n * 100, 1)

    if n_clusters > 0:
        sizes = pd.Series(labels[labels != -1]).value_counts()
        max_pct = round(sizes.iloc[0] / n * 100, 1)
        median_size = round(float(sizes.median()), 1)
    else:
        max_pct = 0.0
        median_size = 0.0

    thetford = clusters_in_box(cx, cy, labels, THETFORD_BOX)
    kielder  = clusters_in_box(cx, cy, labels, KIELDER_BOX)
    wales    = clusters_in_box(cx, cy, labels, WALES_BOX)

    passed = sum([
        80 <= n_clusters <= 400,
        noise_pct < 25,
        max_pct < 10,
        1 <= thetford <= 5,
        1 <= kielder <= 5,
        wales >= 5,
    ])

    return {
        "algorithm": name,
        "n_clusters": n_clusters,
        "noise_pct": noise_pct,
        "max_cluster_pct": max_pct,
        "median_cluster_size": median_size,
        "thetford_clusters": thetford,
        "kielder_clusters": kielder,
        "wales_clusters": wales,
        "criteria_passed": f"{passed}/6",
    }


# ── 1. Load + filter ───────────────────────────────────────────────────────────
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

cx = gdf.geometry.centroid.x.values
cy = gdf.geometry.centroid.y.values
coords = np.column_stack([cx, cy])
n = len(gdf)


# ── 2. Build proximity graph ───────────────────────────────────────────────────
log(f"\nBuilding proximity graph (radius={PROXIMITY_M}m)...")
t0 = time.time()
tree = cKDTree(coords)
pairs = tree.query_pairs(PROXIMITY_M, output_type="ndarray")  # shape (K, 2)
log(f"  {len(pairs):,} edges in {time.time()-t0:.1f}s")

# Sparse adjacency matrix for sklearn
rows = np.concatenate([pairs[:, 0], pairs[:, 1]])
cols = np.concatenate([pairs[:, 1], pairs[:, 0]])
data = np.ones(len(rows))
adj_sparse = csr_matrix((data, (rows, cols)), shape=(n, n))

# NetworkX graph for Louvain and SKATER
G = nx.Graph()
G.add_nodes_from(range(n))
G.add_edges_from(pairs.tolist())
n_components = nx.number_connected_components(G)
log(f"  Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, {n_components} components")


# ── Helper: isolated nodes (no neighbours within PROXIMITY_M) ─────────────────
isolated = np.array(list(nx.isolates(G)))
log(f"  Isolated patches (no neighbour within {PROXIMITY_M}m): {len(isolated)}")


results = []
all_labels = {}


# ── A. HDBSCAN baseline (re-run for fair comparison) ──────────────────────────
log("\n=== A. HDBSCAN (baseline, mcs=15, ms=3, eom) ===")
t0 = time.time()
hdb_labels = hdbscan.HDBSCAN(
    min_cluster_size=15, min_samples=3,
    cluster_selection_method="eom", metric="euclidean"
).fit_predict(coords)
log(f"  Done in {time.time()-t0:.1f}s")
all_labels["HDBSCAN"] = hdb_labels
results.append(score(hdb_labels, cx, cy, "HDBSCAN"))
log(f"  {results[-1]}")


# ── B. Graph + Louvain ─────────────────────────────────────────────────────────
log("\n=== B. Graph + Louvain community detection ===")
# Sweep resolution to find one in the 80–400 cluster range
best_louvain = None
best_louvain_res = None
for res in [0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0]:
    t0 = time.time()
    partition = community_louvain.best_partition(G, resolution=res, random_state=42)
    lbl = np.array([partition[i] for i in range(n)])
    # isolated nodes stay in their own singleton community — mark as noise (-1)
    for iso in isolated:
        lbl[iso] = -1
    n_c = int(np.unique(lbl[lbl != -1]).shape[0])
    log(f"  resolution={res}: {n_c} communities, noise={int((lbl==-1).sum())}")
    if 80 <= n_c <= 400:
        best_louvain = lbl
        best_louvain_res = res
        break

if best_louvain is None:
    # Fall back to the resolution giving closest to 200
    best_louvain = lbl
    best_louvain_res = res
    log("  WARNING: no resolution hit 80–400 range; using last")

log(f"  Chosen resolution: {best_louvain_res}")
all_labels["Louvain"] = best_louvain
results.append(score(best_louvain, cx, cy, "Louvain"))
log(f"  {results[-1]}")


# ── C. SKATER ─────────────────────────────────────────────────────────────────
log("\n=== C. SKATER (spopt) ===")
# SKATER needs a libpysal weights object built from our proximity graph
# Build from adjacency pairs
neighbors = {i: [] for i in range(n)}
for a, b in pairs.tolist():
    neighbors[a].append(b)
    neighbors[b].append(a)
w = libpysal.weights.W(neighbors, silence_warnings=True)

# Use area_ha as the attribute for homogeneity
attrs = gdf[["area_ha"]].values

best_skater = None
best_skater_k = None
for k in [150, 200, 250]:
    try:
        t0 = time.time()
        sk = Skater(gdf, w, attrs, n_clusters=k, silence_warnings=True)
        sk.solve()
        lbl = np.array(sk.labels_)
        n_c = int(np.unique(lbl).shape[0])
        log(f"  k={k}: {n_c} clusters in {time.time()-t0:.1f}s")
        if 80 <= n_c <= 400:
            best_skater = lbl
            best_skater_k = k
            break
    except Exception as e:
        log(f"  k={k}: FAILED — {e}")

if best_skater is None and 'lbl' in dir():
    best_skater = lbl
    best_skater_k = k

if best_skater is not None:
    all_labels["SKATER"] = best_skater
    results.append(score(best_skater, cx, cy, f"SKATER(k={best_skater_k})"))
    log(f"  {results[-1]}")
else:
    log("  SKATER: all attempts failed — skipping")


# ── D. Max-P ──────────────────────────────────────────────────────────────────
log("\n=== D. Max-P Regionalization (spopt) ===")
best_maxp = None
best_maxp_thresh = None
# threshold = minimum total_area_ha per cluster
for thresh in [500, 200, 100]:
    try:
        t0 = time.time()
        mp = MaxPHeuristic(gdf, w, attrs, threshold_name="area_ha",
                           threshold=thresh, top_n=2, silence_warnings=True)
        mp.solve()
        lbl = np.array(mp.labels_)
        n_c = int(np.unique(lbl).shape[0])
        elapsed = time.time() - t0
        log(f"  threshold={thresh}ha: {n_c} clusters in {elapsed:.1f}s")
        if 80 <= n_c <= 400:
            best_maxp = lbl
            best_maxp_thresh = thresh
            break
    except Exception as e:
        log(f"  threshold={thresh}ha: FAILED — {e}")

if best_maxp is None and 'lbl' in dir():
    best_maxp = lbl
    best_maxp_thresh = thresh

if best_maxp is not None:
    all_labels["MaxP"] = best_maxp
    results.append(score(best_maxp, cx, cy, f"MaxP(threshold={best_maxp_thresh}ha)"))
    log(f"  {results[-1]}")
else:
    log("  Max-P: all attempts failed — skipping")


# ── E. AgglomerativeClustering + spatial connectivity ─────────────────────────
log("\n=== E. AgglomerativeClustering (Ward + proximity connectivity) ===")
best_agg = None
best_agg_k = None
for k in [200, 150, 250]:
    try:
        t0 = time.time()
        agg = AgglomerativeClustering(
            n_clusters=k,
            metric="euclidean",
            linkage="ward",
            connectivity=adj_sparse
        )
        lbl = agg.fit_predict(coords)
        n_c = int(np.unique(lbl).shape[0])
        log(f"  k={k}: {n_c} clusters in {time.time()-t0:.1f}s")
        if 80 <= n_c <= 400:
            best_agg = lbl
            best_agg_k = k
            break
    except Exception as e:
        log(f"  k={k}: FAILED — {e}")

if best_agg is None and 'lbl' in dir():
    best_agg = lbl
    best_agg_k = k

if best_agg is not None:
    all_labels["Agglomerative"] = best_agg
    results.append(score(best_agg, cx, cy, f"Agglomerative(k={best_agg_k})"))
    log(f"  {results[-1]}")
else:
    log("  Agglomerative: all attempts failed — skipping")


# ── Comparison table ───────────────────────────────────────────────────────────
log("\n=== COMPARISON TABLE ===")
df = pd.DataFrame(results)
print(df.to_string(index=False))
df.to_csv(CLUSTER_DIR / "algorithm_comparison.csv", index=False)
log(f"\nSaved: {CLUSTER_DIR / 'algorithm_comparison.csv'}")


# ── Multi-panel map ────────────────────────────────────────────────────────────
log("\nPlotting comparison map...")
algo_names = list(all_labels.keys())
n_plots = len(algo_names)
fig, axes = plt.subplots(1, n_plots, figsize=(5 * n_plots, 14))
if n_plots == 1:
    axes = [axes]

for ax, name in zip(axes, algo_names):
    lbl = all_labels[name]
    noise_mask = lbl == -1
    clustered_mask = ~noise_mask
    metrics = next((r for r in results if name in r["algorithm"]), {})
    ax.scatter(
        cx[clustered_mask], cy[clustered_mask],
        c=lbl[clustered_mask] % 40, cmap="tab20", s=3, alpha=0.7
    )
    if noise_mask.sum() > 0:
        ax.scatter(cx[noise_mask], cy[noise_mask], c="lightgrey", s=1, alpha=0.3)
    n_c = metrics.get("n_clusters", "?")
    noise = metrics.get("noise_pct", "?")
    passed = metrics.get("criteria_passed", "?")
    ax.set_title(f"{name}\n{n_c} clusters | {noise}% noise | {passed} criteria", fontsize=9)
    ax.set_aspect("equal")
    ax.set_xlabel("Easting (m)", fontsize=7)
    ax.set_ylabel("Northing (m)", fontsize=7)
    ax.tick_params(labelsize=6)

plt.tight_layout()
fig.savefig(FIGURES_DIR / "08_algorithm_comparison.png", dpi=130)
plt.close(fig)
log("Saved: 08_algorithm_comparison.png")


# ── Pick best and export ───────────────────────────────────────────────────────
log("\n=== Selecting best algorithm ===")
# Score: criteria_passed (primary), then lowest noise_pct (secondary)
def sort_key(r):
    passed = int(r["criteria_passed"].split("/")[0])
    return (-passed, r["noise_pct"])

ranked = sorted(results, key=sort_key)
best = ranked[0]
log(f"Best: {best['algorithm']} ({best['criteria_passed']} criteria, {best['noise_pct']}% noise)")

best_labels = all_labels[best["algorithm"].split("(")[0]]

# Dissolve and export
log("\nDissolving + exporting best result...")
gdf["cluster_label"] = best_labels
clustered_only = gdf[gdf["cluster_label"] != -1].copy()

dissolved = clustered_only.dissolve(
    by="cluster_label",
    aggfunc={TYPE_FIELD: lambda x: x.mode().iloc[0], "area_ha": "sum"}
).reset_index()

poly_counts = clustered_only.groupby("cluster_label").size().rename("polygon_count")
dissolved = dissolved.join(poly_counts, on="cluster_label")
dissolved["cluster_id"]    = ["cluster_{:04d}".format(int(i)) for i in dissolved["cluster_label"]]
dissolved["dominant_type"] = dissolved[TYPE_FIELD]
dissolved["total_area_ha"] = dissolved["area_ha"].round(1)

# Centroids in EPSG:27700, then convert
centroids_4326 = gpd.GeoSeries(dissolved.geometry.centroid, crs=27700).to_crs(4326)
dissolved["centroid_lat"] = centroids_4326.y.round(6)
dissolved["centroid_lon"] = centroids_4326.x.round(6)

dissolved_wgs = dissolved.to_crs(epsg=4326)
out = dissolved_wgs[[
    "cluster_id", "cluster_label", "dominant_type",
    "total_area_ha", "polygon_count",
    "centroid_lat", "centroid_lon", "geometry"
]].copy()

out.geometry = out.geometry.simplify(0.001, preserve_topology=True)
output_path = OUTPUT_DIR / "clusters.geojson"
out.to_file(output_path, driver="GeoJSON")
size_mb = os.path.getsize(output_path) / 1_048_576
log(f"Output: {output_path} ({size_mb:.2f} MB, {len(out)} clusters)")

# Save full summary
summary = {
    "comparison": results,
    "best_algorithm": best["algorithm"],
    "best_criteria_passed": best["criteria_passed"],
    "output_file": str(output_path),
    "output_size_mb": round(size_mb, 3),
    "n_clusters": len(out),
    "proximity_radius_m": PROXIMITY_M,
}
with open(CLUSTER_DIR / "comparison_summary.json", "w") as f:
    json.dump(summary, f, indent=2)

log(f"\n=== DONE ===")
log(f"Best algorithm: {best['algorithm']}")
log(f"Output: {output_path} ({size_mb:.2f} MB)")
log(f"Comparison: {CLUSTER_DIR / 'algorithm_comparison.csv'}")
