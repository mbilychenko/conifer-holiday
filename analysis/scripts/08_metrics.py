"""
Phase 0d-D: Compute the full metric suite for every grid run.

Metric families (per Phase 0d plan):
  Internal validity:
    - silhouette_score (subsample 5000)
    - davies_bouldin_score
    - calinski_harabasz_score

  Spatial validity:
    - bb_join_ratio: Black-Black join-count ratio (prox_2500m graph, permutation p-value)
    - intra_inter_distance_ratio (lower = better separation)

  Entity validation (vs 22 reference forests):
    - detection_rate, single_cluster_rate, tight_placement_rate,
      area_accuracy_rate, median_area_ratio, median_nearest_km

  Stability:
    - bootstrap ARI: for the best config per algorithm, resample 80% of polygons
      50 times, compute mean ARI vs. the full clustering

Outputs:
  data/output/clustering/grid_metrics.csv          — one row per grid run × all metrics
  data/output/clustering/bootstrap_stability.csv   — one row per algorithm × bootstrap stats
"""

from __future__ import annotations

import json
import time
import warnings
from pathlib import Path

import community as community_louvain
import geopandas as gpd
import hdbscan
import libpysal
import networkx as nx
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from scipy.sparse import load_npz
from sklearn.cluster import AgglomerativeClustering, DBSCAN, KMeans
from sklearn.metrics import (
    adjusted_rand_score, calinski_harabasz_score, davies_bouldin_score,
    silhouette_score,
)
from spopt.region import Skater, MaxPHeuristic

import config
import utils


# ── Top-level helper for parallel agglomerative bootstrap ─────────────────────
# Defined at module level so it's picklable for joblib's loky backend on Windows.
def _agglomerative_bootstrap_iter(sub_coords: np.ndarray,
                                  full_labels_subset: np.ndarray,
                                  n_clusters: int,
                                  radius_m: int) -> float:
    """One bootstrap iteration of Ward + prox_2500m connectivity. Returns ARI."""
    from scipy.spatial import cKDTree
    from scipy.sparse import csr_matrix
    from sklearn.cluster import AgglomerativeClustering
    from sklearn.metrics import adjusted_rand_score

    tree = cKDTree(sub_coords)
    pairs = tree.query_pairs(radius_m, output_type="ndarray")
    n_sub = len(sub_coords)
    if len(pairs):
        rows = np.concatenate([pairs[:, 0], pairs[:, 1]])
        cols = np.concatenate([pairs[:, 1], pairs[:, 0]])
        data = np.ones(len(rows), dtype=np.uint8)
        conn = csr_matrix((data, (rows, cols)), shape=(n_sub, n_sub))
    else:
        conn = None

    boot_labels = AgglomerativeClustering(
        n_clusters=n_clusters,
        metric="euclidean",
        linkage="ward",
        connectivity=conn,
    ).fit_predict(sub_coords)
    return float(adjusted_rand_score(full_labels_subset, boot_labels))

warnings.filterwarnings("ignore")

# ── Load shared inputs ────────────────────────────────────────────────────────
utils.log("Loading filtered NFI + reference forests...")
gdf      = utils.load_filtered_nfi()
coords   = utils.centroids_array(gdf)
n        = len(gdf)
ref_gdf  = utils.reference_forests_gdf()

# Pre-build libpysal weights on prox_2500m for join-count statistics (consistent across all runs)
moran_adj = load_npz(config.GRAPH_DIR / "prox_2500m.npz")
coo = moran_adj.tocoo()
moran_neighbors = {i: [] for i in range(n)}
for r, c in zip(coo.row, coo.col):
    moran_neighbors[int(r)].append(int(c))
moran_neighbors = {i: list(set(v) - {i}) for i, v in moran_neighbors.items()}
moran_w = libpysal.weights.W(moran_neighbors, silence_warnings=True)
utils.log(f"  Join-count weight matrix from prox_2500m: {moran_w.n} nodes\n")


# ── Internal validity metrics ─────────────────────────────────────────────────
_N_SILHOUETTE_REPS = 10  # number of independent subsamples for silhouette mean+CI


def compute_internal(labels: np.ndarray) -> dict:
    """Silhouette (10-subsample mean + 95% CI) + Davies-Bouldin + Calinski-Harabasz.

    Running 10 independent subsamples and reporting mean ± percentile interval
    captures subsample variance — a single 5k-point draw can deviate by ±0.02–0.05.
    The mean is used as the composite-score input; lo/hi are reported for the paper.
    """
    out = {
        "silhouette": np.nan, "silhouette_lo": np.nan, "silhouette_hi": np.nan,
        "davies_bouldin": np.nan, "calinski_harabasz": np.nan,
    }
    valid_mask  = labels != -1
    valid_lbls  = labels[valid_mask]
    if valid_lbls.size < 10 or np.unique(valid_lbls).size < 2:
        return out
    valid_coords = coords[valid_mask]

    sub_size = min(config.SILHOUETTE_SUBSAMPLE_SIZE, valid_coords.shape[0])
    rng = np.random.default_rng(config.SILHOUETTE_RANDOM_SEED)
    silh_scores: list[float] = []
    for _ in range(_N_SILHOUETTE_REPS):
        idx = rng.choice(valid_coords.shape[0], size=sub_size, replace=False)
        sub_c = valid_coords[idx]
        sub_l = valid_lbls[idx]
        if np.unique(sub_l).size >= 2:
            try:
                silh_scores.append(float(silhouette_score(sub_c, sub_l)))
            except Exception:
                pass
    if silh_scores:
        arr = np.array(silh_scores)
        out["silhouette"]    = float(arr.mean())
        out["silhouette_lo"] = float(np.percentile(arr, 2.5))
        out["silhouette_hi"] = float(np.percentile(arr, 97.5))

    try:
        out["davies_bouldin"] = float(davies_bouldin_score(valid_coords, valid_lbls))
    except Exception:
        pass
    try:
        out["calinski_harabasz"] = float(calinski_harabasz_score(valid_coords, valid_lbls))
    except Exception:
        pass
    return out


# ── Spatial validity ──────────────────────────────────────────────────────────
def compute_spatial(labels: np.ndarray) -> dict:
    """Black-Black join-count ratio + intra/inter centroid-distance ratio.

    BB join-count: fraction of prox_2500m graph edges connecting polygons that share
    the same cluster label. Higher = stronger spatial coherence of clusters. Range [0, 1].
    Permutation p-value (n=99) tests whether observed BB exceeds random relabelling.

    Cluster IDs are NOMINAL — Moran's I is invalid for nominal labels (relabelling
    changes the statistic without changing the clustering). Join-count statistics are
    the correct spatial autocorrelation test for categorical variables.
    """
    out = {"bb_join_ratio": np.nan, "bb_join_p": np.nan, "intra_inter_ratio": np.nan}

    valid_mask = labels != -1
    if valid_mask.sum() < 100:
        return out

    # Count edges whose endpoints share the same cluster label
    n_total_edges = moran_w.s0 / 2  # s0 is sum of all weights (both directions)
    same_cluster_edges = 0
    for i, ns in moran_w.neighbors.items():
        for j in ns:
            if i < j and labels[i] != -1 and labels[j] != -1 and labels[i] == labels[j]:
                same_cluster_edges += 1

    if n_total_edges > 0:
        out["bb_join_ratio"] = float(same_cluster_edges / n_total_edges)

    # Permutation test: shuffle labels 99 times, compute BB ratio each time
    rng = np.random.default_rng(config.GLOBAL_SEED)
    perm_ratios = []
    for _ in range(99):
        perm = rng.permutation(labels)
        sc = 0
        for i, ns in moran_w.neighbors.items():
            for j in ns:
                if i < j and perm[i] != -1 and perm[j] != -1 and perm[i] == perm[j]:
                    sc += 1
        perm_ratios.append(sc / n_total_edges if n_total_edges else 0)
    perm_ratios = np.array(perm_ratios)
    # One-sided p: proportion of random permutations >= observed
    out["bb_join_p"] = float((perm_ratios >= out["bb_join_ratio"]).mean())

    # Intra/inter ratio (sample-based to keep tractable)
    rng2 = np.random.default_rng(config.GLOBAL_SEED)
    sample_size = min(2000, valid_mask.sum())
    idx = rng2.choice(np.where(valid_mask)[0], sample_size, replace=False)
    sub_c, sub_l = coords[idx], labels[idx]

    # Pairwise distances and label-equality mask
    diffs = sub_c[:, None, :] - sub_c[None, :, :]
    dists = np.sqrt((diffs ** 2).sum(axis=-1))
    same  = sub_l[:, None] == sub_l[None, :]
    iu    = np.triu_indices(sample_size, k=1)
    same_pair = same[iu]
    dist_pair = dists[iu]
    if same_pair.any() and (~same_pair).any():
        intra = dist_pair[same_pair].mean()
        inter = dist_pair[~same_pair].mean()
        out["intra_inter_ratio"] = float(intra / inter) if inter > 0 else np.nan
    return out


# ── Entity validation against 22 reference forests ────────────────────────────
def compute_entity(labels: np.ndarray) -> dict:
    """Detection / single-cluster / area-accuracy metrics for 20 primary forests."""
    out = {
        "detection_rate":      np.nan,
        "single_cluster_rate": np.nan,
        "tight_placement_rate":np.nan,
        "area_accuracy_rate":  np.nan,
        "median_area_ratio":   np.nan,
        "median_nearest_km":   np.nan,
    }

    # Skip clusters that are pure noise
    valid_clusters = np.unique(labels[labels != -1])
    if valid_clusters.size == 0:
        return out

    # Attach labels temporarily to gdf
    tmp = gdf.copy()
    tmp["cluster_label"] = labels
    tmp = tmp[tmp["cluster_label"] != -1]
    if tmp.empty:
        return out

    # Dissolve to cluster polygons (in EPSG:27700)
    dissolved = utils.dissolve_clusters(tmp, label_col="cluster_label")
    dissolved["cluster_area_ha"] = dissolved.geometry.area / 10_000
    sindex = dissolved.sindex

    primaries = ref_gdf[ref_gdf["role"] == "primary"]
    detected, single_cluster, tight, area_ok = 0, 0, 0, 0
    ratios, distances = [], []

    for _, f in primaries.iterrows():
        centre = f.geometry
        buf = centre.buffer(config.ENTITY_SEARCH_RADIUS_M)
        cand_idx = list(sindex.intersection(buf.bounds))
        cands = dissolved.iloc[cand_idx]
        intersecting = cands[cands.geometry.intersects(buf)]
        if intersecting.empty:
            continue
        # Choose primary cluster by largest intersection area
        intersecting = intersecting.copy()
        intersecting["in_buf_ha"] = (
            intersecting.geometry.intersection(buf).area / 10_000
        )
        intersecting = intersecting.sort_values("in_buf_ha", ascending=False)
        primary = intersecting.iloc[0]
        # Nearest cluster centroid (across all clusters)
        all_dists = dissolved.geometry.centroid.distance(centre)
        nearest_km = all_dists.min() / 1_000

        detected += 1
        if len(intersecting) == 1:
            single_cluster += 1
        if nearest_km <= 5:
            tight += 1
        ratio = primary["cluster_area_ha"] / f["area_ha"]
        ratios.append(ratio)
        distances.append(nearest_km)
        if 0.3 <= ratio <= 3.0:
            area_ok += 1

    n_primary = len(primaries)
    out["detection_rate"]       = round(detected / n_primary * 100, 1)
    out["single_cluster_rate"]  = round(single_cluster / n_primary * 100, 1)
    out["tight_placement_rate"] = round(tight / n_primary * 100, 1)
    out["area_accuracy_rate"]   = round(area_ok / n_primary * 100, 1)
    out["median_area_ratio"]    = round(float(np.median(ratios)), 2) if ratios else np.nan
    out["median_nearest_km"]    = round(float(np.median(distances)), 2) if distances else np.nan
    return out


# ── Main: walk grid index, compute metrics ────────────────────────────────────
index_path = config.CLUSTERING_DIR / "grid_index.csv"
if not index_path.exists():
    raise FileNotFoundError(f"{index_path} missing — run 07_grid_search.py first")
grid = pd.read_csv(index_path)

# Cache: if grid_metrics.csv already covers every run_id, skip recomputation
out_path = config.CLUSTERING_DIR / "grid_metrics.csv"
existing_metrics = None
if out_path.exists():
    existing_metrics = pd.read_csv(out_path)
    missing = set(grid["run_id"]) - set(existing_metrics["run_id"])
    needs_silh_ci = "silhouette_lo" not in existing_metrics.columns
    if not missing and not needs_silh_ci:
        utils.log(f"grid_metrics.csv already covers all {len(grid)} runs — skipping recomputation")
        metrics_df = existing_metrics
    elif needs_silh_ci:
        utils.log(f"grid_metrics.csv lacks silhouette_lo/hi columns — recomputing all (P2.4 upgrade)")
        existing_metrics = None
    else:
        utils.log(f"grid_metrics.csv exists but missing {len(missing)} runs — recomputing all")
        existing_metrics = None

utils.log(f"Computing metrics for {len(grid)} runs...")
rows = []
t_start = time.time()

_skip_metrics = existing_metrics is not None  # skip the heavy loop when cached
for i, row in enumerate(grid.itertuples(index=False), 1):
    if _skip_metrics:
        break  # metrics_df already populated above
    labels_path = config.GRID_DIR / f"{row.run_id}.npy"
    if not labels_path.exists() or (isinstance(row.status, str) and row.status.startswith("error")):
        # Skip failed runs; record nan placeholders
        rows.append({
            "run_id":    row.run_id,
            "algorithm": row.algorithm,
            "graph":     row.graph,
            "status":    row.status,
        })
        continue

    labels = np.load(labels_path)

    t0 = time.time()
    internal = compute_internal(labels)
    spatial  = compute_spatial(labels)
    entity   = compute_entity(labels)
    metric_s = round(time.time() - t0, 2)

    rows.append({
        "run_id":    row.run_id,
        "algorithm": row.algorithm,
        "graph":     row.graph,
        "status":    row.status,
        "n_clusters":          row.n_clusters,
        "noise_pct":           row.noise_pct,
        "max_cluster_pct":     row.max_cluster_pct,
        "median_cluster_size": row.median_cluster_size,
        **internal,
        **spatial,
        **entity,
        "metrics_runtime_s":   metric_s,
    })
    if i % 5 == 0 or i == len(grid):
        lo = internal.get("silhouette_lo")
        hi = internal.get("silhouette_hi")
        ci_str = (f" [{lo:.3f},{hi:.3f}]" if lo is not None and not np.isnan(lo) else "")
        utils.log(f"  [{i:3d}/{len(grid)}] {row.run_id}: "
                  f"silh={internal['silhouette']:.3f}{ci_str}, "
                  f"det={entity['detection_rate']}, "
                  f"({metric_s}s)")

if not _skip_metrics:
    metrics_df = pd.DataFrame(rows)
    metrics_df.to_csv(out_path, index=False)
    utils.log(f"\nSaved: {out_path}")
    utils.log(f"Total metric-computation time: {round(time.time() - t_start, 1)}s")
else:
    utils.log(f"\nUsing cached metrics from {out_path} ({len(metrics_df)} rows)")


# ── Bootstrap stability for best config per algorithm ─────────────────────────
utils.log("\n=== Bootstrap stability ===")

# Pick the best run per algorithm using a composite of detection_rate + (1 - DB normalized)
def composite_score(r: pd.Series) -> float:
    if pd.isna(r.get("n_clusters")) or not (config.CLUSTER_COUNT_MIN <= r["n_clusters"] <= config.CLUSTER_COUNT_MAX):
        return -np.inf
    silh = 0.0 if pd.isna(r.get("silhouette")) else float(r.get("silhouette"))
    db   = r.get("davies_bouldin")
    det  = (r.get("detection_rate") or 0) / 100
    scr  = (r.get("single_cluster_rate") or 0) / 100
    # Clip negative silhouette to 0: negative values indicate misclustering and should
    # not receive partial credit. Positive values contribute linearly; range stays [0,~1].
    silh_n = max(silh, 0.0)
    # DB lower-better; clip and invert
    db_inv = 1.0 / (1.0 + db) if db is not None and not pd.isna(db) else 0
    w = config.COMPOSITE_WEIGHTS
    return (w["silhouette_norm"] * silh_n +
            w["davies_bouldin_inv"] * db_inv +
            w["detection_rate"] * det +
            w["single_cluster_rate"] * scr)

metrics_df["composite"] = metrics_df.apply(composite_score, axis=1)
metrics_df["composite_finite"] = metrics_df["composite"].replace([np.inf, -np.inf], np.nan)

# Merge params column from grid_index.csv (needed for bootstrap re-runs)
grid_index = pd.read_csv(config.CLUSTERING_DIR / "grid_index.csv")
metrics_df = metrics_df.merge(
    grid_index[["run_id", "params"]], on="run_id", how="left"
)

best_per_algo = (
    metrics_df.dropna(subset=["composite_finite"])
              .sort_values("composite_finite", ascending=False)
              .groupby("algorithm").head(1)
              .reset_index(drop=True)
)
utils.log(f"\nBest configs by composite score:")
for _, r in best_per_algo.iterrows():
    utils.log(f"  {r['algorithm']:>14} ({r['graph']:>12}): {r['run_id']}  "
              f"clusters={int(r['n_clusters'])}, "
              f"silh={r['silhouette']:.3f}, "
              f"det={r['detection_rate']}%, "
              f"composite={r['composite']:.3f}")

# Save best-per-algorithm
best_path = config.CLUSTERING_DIR / "best_per_algorithm.csv"
best_per_algo.to_csv(best_path, index=False)
utils.log(f"\nSaved: {best_path}")


# Bootstrap: for each best config, resample 80% of polygons N times and compute ARI
def rerun_algorithm(algo: str, params: dict, graph_name: str | None,
                    sub_coords: np.ndarray, sub_idx: np.ndarray) -> np.ndarray:
    """Re-run the algorithm on a subset (for bootstrapping). Reuses grid logic."""
    if algo == "kmeans":
        return KMeans(n_clusters=params["n_clusters"], n_init=10,
                      random_state=config.GLOBAL_SEED).fit_predict(sub_coords)
    if algo == "dbscan":
        return DBSCAN(eps=params["eps"], min_samples=params["min_samples"]).fit_predict(sub_coords)
    if algo == "hdbscan":
        return hdbscan.HDBSCAN(
            min_cluster_size=params["min_cluster_size"],
            min_samples=params["min_samples"],
            cluster_selection_method=params["cluster_selection_method"],
        ).fit_predict(sub_coords)
    if algo == "agglomerative":
        from scipy.spatial import cKDTree
        from scipy.sparse import csr_matrix
        # Mirror the full-data runner (07_grid_search.run_agglomerative): Ward with
        # prox_2500m connectivity. Without this, the bootstrap measures unconstrained
        # Ward — a different algorithm than the one being benchmarked.
        radius_m = config.GRAPH_VARIANTS["prox_2500m"]["radius_m"]
        tree = cKDTree(sub_coords)
        pairs = tree.query_pairs(radius_m, output_type="ndarray")
        n_sub = len(sub_coords)
        if len(pairs):
            rows = np.concatenate([pairs[:, 0], pairs[:, 1]])
            cols = np.concatenate([pairs[:, 1], pairs[:, 0]])
            data = np.ones(len(rows), dtype=np.uint8)
            conn = csr_matrix((data, (rows, cols)), shape=(n_sub, n_sub))
        else:
            conn = None
        return AgglomerativeClustering(
            n_clusters=params["n_clusters"],
            metric="euclidean",
            linkage="ward",
            connectivity=conn,
        ).fit_predict(sub_coords)
    if algo == "louvain":
        from scipy.spatial import cKDTree
        if graph_name is None or "radius_m" not in config.GRAPH_VARIANTS.get(graph_name, {}):
            raise NotImplementedError(f"Louvain bootstrap requires a proximity graph (got {graph_name})")
        # Rebuild proximity graph on the bootstrap subset; match the winner's graph radius
        radius_m = config.GRAPH_VARIANTS[graph_name]["radius_m"]
        tree = cKDTree(sub_coords)
        pairs = tree.query_pairs(radius_m, output_type="ndarray")
        G = nx.Graph()
        G.add_nodes_from(range(len(sub_coords)))
        if len(pairs):
            G.add_edges_from(pairs.tolist())
        partition = community_louvain.best_partition(
            G, resolution=params["resolution"],
            random_state=config.GLOBAL_SEED,
        )
        return np.array([partition[i] for i in range(len(sub_coords))], dtype=np.int32)
    if algo == "spectral":
        from sklearn.cluster import SpectralClustering
        from scipy.sparse import csr_matrix
        n_sub = len(sub_coords)
        gv = config.GRAPH_VARIANTS.get(graph_name, {})
        if gv.get("kind") == "proximity":
            from scipy.spatial import cKDTree
            tree = cKDTree(sub_coords)
            pairs = tree.query_pairs(gv["radius_m"], output_type="ndarray")
            if len(pairs):
                r = np.concatenate([pairs[:, 0], pairs[:, 1]])
                c = np.concatenate([pairs[:, 1], pairs[:, 0]])
                adj = csr_matrix((np.ones(len(r), dtype=np.uint8), (r, c)), shape=(n_sub, n_sub))
            else:
                adj = csr_matrix((n_sub, n_sub))
        elif gv.get("kind") == "knn":
            from sklearn.neighbors import kneighbors_graph
            adj = kneighbors_graph(sub_coords, n_neighbors=gv["k"],
                                   mode="connectivity", include_self=False)
            adj = (adj + adj.T)
            adj.data[:] = 1
        else:
            raise NotImplementedError(f"Spectral bootstrap: unknown graph kind for {graph_name}")
        sc = SpectralClustering(n_clusters=params["n_clusters"], affinity="precomputed",
                                n_init=10, assign_labels="kmeans",
                                random_state=config.GLOBAL_SEED, n_jobs=1)
        return sc.fit_predict(adj).astype(np.int32)
    raise NotImplementedError(f"Bootstrap not implemented for {algo}")

# Load existing bootstrap results to preserve completed runs across re-runs.
# This avoids re-running expensive bootstraps (e.g. Louvain ~7 min, Spectral ~12 min)
# when only some algorithms changed or need updating.
_prev_stab_cache: dict[str, dict] = {}
_stab_path_check = config.CLUSTERING_DIR / "bootstrap_stability.csv"
if _stab_path_check.exists():
    _prev_stab_df = pd.read_csv(_stab_path_check)
    for _, _row in _prev_stab_df.iterrows():
        if pd.notna(_row.get("mean_ari")):
            _prev_stab_cache[str(_row["run_id"])] = _row.to_dict()

stability_rows = []
for _, best in best_per_algo.iterrows():
    algo = best["algorithm"]
    params = json.loads(best["params"]) if isinstance(best["params"], str) else best["params"]

    if algo in {"skater", "maxp"}:
        utils.log(f"  Skipping bootstrap for {algo} (algorithm excluded from benchmark via SKIP_COMBINATIONS)")
        stability_rows.append({
            "algorithm":      algo,
            "run_id":         best["run_id"],
            "mean_ari":       np.nan,
            "ari_lo":         np.nan,
            "ari_hi":         np.nan,
            "n_iterations":   0,
            "note":           "skipped — algorithm excluded from benchmark via SKIP_COMBINATIONS",
        })
        continue

    # Use cached result for this run_id if available (avoids re-running expensive bootstraps).
    if str(best["run_id"]) in _prev_stab_cache:
        cached_stab = _prev_stab_cache[str(best["run_id"])]
        utils.log(f"  {algo}: using cached bootstrap ARI {cached_stab['mean_ari']:.3f} "
                  f"(n={cached_stab['n_iterations']})")
        stability_rows.append(cached_stab)
        continue

    # Agglomerative bootstrap is computed by a separate __main__-safe script
    # (08b_agglomerative_bootstrap.py) because Ward + connectivity is expensive
    # (~14 min/iter) and needs joblib's loky backend, which on Windows requires
    # the script to be __main__-protected.
    if algo == "agglomerative":
        _agg_stab_path = config.CLUSTERING_DIR / "bootstrap_stability.csv"
        _preserved = None
        if _agg_stab_path.exists():
            _prev = pd.read_csv(_agg_stab_path)
            _match = _prev[
                (_prev["algorithm"] == "agglomerative") &
                (_prev["run_id"] == best["run_id"]) &
                _prev["mean_ari"].notna()
            ]
            if not _match.empty:
                _preserved = _match.iloc[0].to_dict()

        if _preserved:
            utils.log(f"  {algo}: preserving existing bootstrap ARI "
                      f"(mean={_preserved['mean_ari']:.3f}) from 08b — winner unchanged")
            stability_rows.append(_preserved)
        else:
            utils.log(f"  Deferring {algo} bootstrap to 08b_agglomerative_bootstrap.py "
                      f"(computed via joblib loky in a separate __main__-safe script)")
            stability_rows.append({
                "algorithm":      algo,
                "run_id":         best["run_id"],
                "mean_ari":       np.nan,
                "ari_lo":         np.nan,
                "ari_hi":         np.nan,
                "n_iterations":   0,
                "note":           "pending — run 08b_agglomerative_bootstrap.py to fill",
            })
        continue

    # Load the full-data labels for ARI comparison
    full_labels = np.load(config.GRID_DIR / f"{best['run_id']}.npy")
    aris = []
    rng = np.random.default_rng(config.BOOTSTRAP_RANDOM_SEED)
    for it in range(config.BOOTSTRAP_N_ITERATIONS):
        idx = rng.choice(n, int(config.BOOTSTRAP_SUBSAMPLE_FRAC * n), replace=False)
        sub_coords = coords[idx]
        try:
            graph_name = best["graph"] if best["graph"] != "none" else None
            boot_labels = rerun_algorithm(algo, params, graph_name, sub_coords, idx)
            aris.append(adjusted_rand_score(full_labels[idx], boot_labels))
        except Exception as e:
            pass
    if aris:
        aris = np.array(aris)
        stability_rows.append({
            "algorithm":      algo,
            "run_id":         best["run_id"],
            "mean_ari":       round(float(aris.mean()), 4),
            "ari_lo":         round(float(np.percentile(aris, 2.5)), 4),
            "ari_hi":         round(float(np.percentile(aris, 97.5)), 4),
            "n_iterations":   int(len(aris)),
            "note":           "",
        })
        utils.log(f"  {algo}: mean ARI = {aris.mean():.3f} (n={len(aris)})")
    else:
        stability_rows.append({
            "algorithm":      algo,
            "run_id":         best["run_id"],
            "mean_ari":       np.nan,
            "ari_lo":         np.nan,
            "ari_hi":         np.nan,
            "n_iterations":   0,
            "note":           "all bootstrap iterations failed",
        })
        utils.log(f"  {algo}: all bootstrap iterations failed")

stab_path = config.CLUSTERING_DIR / "bootstrap_stability.csv"
pd.DataFrame(stability_rows).to_csv(stab_path, index=False)
utils.log(f"\nSaved: {stab_path}")

utils.log("\n=== Phase 0d-D done ===")
