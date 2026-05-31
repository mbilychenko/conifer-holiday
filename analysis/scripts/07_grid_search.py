"""
Phase 0d-C: Algorithm × graph × parameter grid search.

For every (algorithm, graph or no-graph, parameter combo) defined in config.py:
  1. Run the clustering algorithm
  2. Record runtime + cluster-size statistics
  3. Save labels as a compressed .npy under data/output/grid/

Resume capability: if the labels file already exists, the run is skipped and the
existing labels are re-used. Re-running the script after a failure or extension
of the grid is therefore cheap.

Outputs:
  data/output/grid/<run_id>.npy             — int32 cluster labels per polygon
  data/output/clustering/grid_index.csv     — index of all runs with metadata

A `run_id` looks like `hdbscan__none__mcs5_ms1_csmeom` or `skater__prox_10000m__k200`.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import itertools
import json
import os
import sys
import time
import warnings
from pathlib import Path

import community as community_louvain
import hdbscan
import libpysal
import networkx as nx
import numpy as np
import pandas as pd
from scipy.sparse import load_npz
from sklearn.cluster import AgglomerativeClustering, DBSCAN, KMeans, SpectralClustering
from spopt.region import Skater, MaxPHeuristic

import config
import utils

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)


# ── Load filtered NFI + coordinates once ──────────────────────────────────────
utils.log("Loading filtered NFI...")
gdf    = utils.load_filtered_nfi()
coords = utils.centroids_array(gdf)
n      = len(coords)
utils.log(f"  {n:,} centroids loaded\n")


# ── Load graphs lazily ────────────────────────────────────────────────────────
_graph_cache: dict[str, dict] = {}

def get_graph(name: str) -> dict:
    """Return {'adj_csr', 'w', 'G_nx', 'neighbors'} for a named graph variant.

    All four representations are useful:
      adj_csr   — for sklearn AgglomerativeClustering.connectivity
      w         — libpysal weights for spopt (SKATER, Max-P)
      G_nx      — NetworkX graph for Louvain
      neighbors — dict for libpysal.weights.W
    """
    if name in _graph_cache:
        return _graph_cache[name]

    adj = load_npz(config.GRAPH_DIR / f"{name}.npz")

    # Build neighbors dict for libpysal
    coo = adj.tocoo()
    neighbors = {i: [] for i in range(n)}
    for r, c in zip(coo.row, coo.col):
        neighbors[int(r)].append(int(c))
    # libpysal requires lists with no duplicates and self-loops removed
    neighbors = {i: list(set(v) - {i}) for i, v in neighbors.items()}

    w = libpysal.weights.W(neighbors, silence_warnings=True)
    G_nx = nx.from_scipy_sparse_array(adj)

    _graph_cache[name] = {"adj_csr": adj, "w": w, "G_nx": G_nx, "neighbors": neighbors}
    return _graph_cache[name]


# ── Algorithm runners ─────────────────────────────────────────────────────────
def run_kmeans(params: dict, graph_name: str | None) -> np.ndarray:
    km = KMeans(n_clusters=params["n_clusters"], n_init=10, random_state=config.GLOBAL_SEED)
    return km.fit_predict(coords)


def run_dbscan(params: dict, graph_name: str | None) -> np.ndarray:
    db = DBSCAN(eps=params["eps"], min_samples=params["min_samples"])
    return db.fit_predict(coords)


def run_hdbscan(params: dict, graph_name: str | None) -> np.ndarray:
    cl = hdbscan.HDBSCAN(
        min_cluster_size=params["min_cluster_size"],
        min_samples=params["min_samples"],
        cluster_selection_method=params["cluster_selection_method"],
        metric="euclidean",
    )
    return cl.fit_predict(coords)


def run_agglomerative(params: dict, graph_name: str) -> np.ndarray:
    g = get_graph(graph_name)
    # Ward requires symmetric connectivity matrix (it is, from our builder)
    ac = AgglomerativeClustering(
        n_clusters=params["n_clusters"],
        metric="euclidean",
        linkage="ward",
        connectivity=g["adj_csr"],
    )
    return ac.fit_predict(coords)


def _ensure_log_area_column():
    """Add a log_area_ha column once for spopt to use as attrs_name."""
    if "log_area_ha" not in gdf.columns:
        gdf["log_area_ha"] = np.log1p(gdf["area_ha"])


def run_skater(params: dict, graph_name: str) -> np.ndarray:
    """SKATER on log-area as the homogeneity attribute.

    spopt's Skater expects `attrs_name` to be a list of column names in the
    GeoDataFrame, not a numpy array.
    """
    _ensure_log_area_column()
    g = get_graph(graph_name)
    sk = Skater(gdf, g["w"], ["log_area_ha"], n_clusters=params["n_clusters"])
    sk.solve()
    return np.array(sk.labels_, dtype=np.int32)


def run_maxp(params: dict, graph_name: str) -> np.ndarray:
    """Max-P with area_ha as the threshold attribute, log_area_ha as the
    homogeneity attribute."""
    _ensure_log_area_column()
    g = get_graph(graph_name)
    mp = MaxPHeuristic(
        gdf, g["w"], ["log_area_ha"],
        threshold_name="area_ha",
        threshold=params["threshold_ha"],
        top_n=2,
    )
    mp.solve()
    return np.array(mp.labels_, dtype=np.int32)


def run_louvain(params: dict, graph_name: str) -> np.ndarray:
    g = get_graph(graph_name)
    partition = community_louvain.best_partition(
        g["G_nx"],
        resolution=params["resolution"],
        random_state=config.GLOBAL_SEED,
    )
    return np.array([partition[i] for i in range(n)], dtype=np.int32)


def run_spectral(params: dict, graph_name: str) -> np.ndarray:
    """Spectral clustering on the precomputed proximity/kNN adjacency matrix.

    Uses the binary adjacency CSR as the affinity matrix. The graph Laplacian
    eigenvectors are computed via ARPACK (scipy.sparse.linalg.eigsh), so this
    is memory-feasible at n=13,434 with affinity="precomputed_nearest_neighbors"
    or affinity="precomputed". We use affinity="precomputed" and pass adj_csr
    directly.
    """
    g = get_graph(graph_name)
    sc = SpectralClustering(
        n_clusters=params["n_clusters"],
        affinity="precomputed",
        n_init=10,
        assign_labels="kmeans",
        random_state=config.GLOBAL_SEED,
        n_jobs=1,
    )
    labels = sc.fit_predict(g["adj_csr"])
    return labels.astype(np.int32)


RUNNERS = {
    "kmeans":         run_kmeans,
    "dbscan":         run_dbscan,
    "hdbscan":        run_hdbscan,
    "agglomerative":  run_agglomerative,
    "skater":         run_skater,
    "maxp":           run_maxp,
    "louvain":        run_louvain,
    "spectral":       run_spectral,
}


# ── Grid generator ────────────────────────────────────────────────────────────
def param_combos(params_spec: dict):
    """Yield every dict in the Cartesian product of the parameter values."""
    keys, value_lists = zip(*params_spec.items())
    for combo in itertools.product(*value_lists):
        yield dict(zip(keys, combo))


def make_run_id(algo: str, graph_name: str | None, params: dict) -> str:
    """Stable identifier for caching results to disk."""
    param_part = "_".join(f"{k}{v}" for k, v in sorted(params.items()))
    # Remove characters that would be filesystem-unfriendly
    param_part = param_part.replace(".", "p").replace("-", "neg").replace(" ", "")
    return f"{algo}__{graph_name or 'none'}__{param_part}"


# ── Build the full grid (honour SKIP_COMBINATIONS + per-param skips) ──────────
# Agglomerative k>=250 on prox_2500m exceeds the 600s timeout on this machine.
# Yesterday's runs proved k=100/150/200 are feasible (~6-7 min each); the larger
# k values require even more merges and consistently exceed timeout. Skipped and
# documented as a Ward scalability limitation.
PER_PARAM_SKIP = {
    "agglomerative__prox_2500m__n_clusters250",
    "agglomerative__prox_2500m__n_clusters300",
}

runs = []
skipped = []
for algo, spec in config.ALGORITHM_GRIDS.items():
    graphs = list(config.GRAPH_VARIANTS.keys()) if spec["needs_graph"] else [None]
    for graph_name in graphs:
        if (algo, graph_name) in config.SKIP_COMBINATIONS:
            for params in param_combos(spec["params"]):
                skipped.append(make_run_id(algo, graph_name, params))
            continue
        for params in param_combos(spec["params"]):
            run_id = make_run_id(algo, graph_name, params)
            if run_id in PER_PARAM_SKIP:
                skipped.append(run_id)
                continue
            runs.append({
                "run_id":    run_id,
                "algorithm": algo,
                "graph":     graph_name or "none",
                "params":    params,
            })

utils.log(f"Total grid: {len(runs)} runs ({len(skipped)} skipped via SKIP_COMBINATIONS)")
if skipped:
    utils.log(f"  Skipped runs: {len(skipped)} (Agglomerative on non-prox_2500m graphs — Ward scalability)")


# ── Execute (skipping already-completed runs) ────────────────────────────────
index_path = config.CLUSTERING_DIR / "grid_index.csv"
existing_index = (
    pd.read_csv(index_path).set_index("run_id").to_dict(orient="index")
    if index_path.exists() else {}
)

index_rows = []
errors = []

for i, r in enumerate(runs, 1):
    labels_path = config.GRID_DIR / f"{r['run_id']}.npy"
    # Treat a saved .npy as sufficient cache — recompute stats inline.
    # (Earlier runs may have crashed before grid_index.csv was written, so we
    #  cannot rely on existing_index alone to detect cached results.)
    cached = labels_path.exists()

    if cached:
        labels = np.load(labels_path)
        prev = existing_index.get(r["run_id"], {})
        runtime_s = prev.get("runtime_s", 0)
        status    = "cached"
    else:
        runner = RUNNERS[r["algorithm"]]
        timeout_s = config.ALGORITHM_TIMEOUT_S.get(r["algorithm"], 600)
        graph_arg = r["graph"] if r["graph"] != "none" else None
        t0 = time.time()
        try:
            # Run in a worker thread with a hard timeout
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(runner, r["params"], graph_arg)
                labels = fut.result(timeout=timeout_s)
            runtime_s = round(time.time() - t0, 2)
            status = "ok"
            np.save(labels_path, labels.astype(np.int32))
        except concurrent.futures.TimeoutError:
            runtime_s = timeout_s
            status    = f"error: Timeout (>{timeout_s}s)"
            errors.append((r["run_id"], status))
            utils.log(f"  [{i:3d}/{len(runs)}] {r['run_id']}: TIMEOUT after {timeout_s}s")
            index_rows.append({
                "run_id":    r["run_id"],
                "algorithm": r["algorithm"],
                "graph":     r["graph"],
                "params":    json.dumps(r["params"]),
                "runtime_s": runtime_s,
                "status":    status,
                "n_clusters":          None,
                "n_noise":             None,
                "noise_pct":           None,
                "max_cluster_pct":     None,
                "median_cluster_size": None,
            })
            continue
        except Exception as e:
            runtime_s = round(time.time() - t0, 2)
            status    = f"error: {type(e).__name__}: {str(e)[:120]}"
            errors.append((r["run_id"], status))
            utils.log(f"  [{i:3d}/{len(runs)}] {r['run_id']}: FAILED ({status}) in {runtime_s}s")
            index_rows.append({
                "run_id":    r["run_id"],
                "algorithm": r["algorithm"],
                "graph":     r["graph"],
                "params":    json.dumps(r["params"]),
                "runtime_s": runtime_s,
                "status":    status,
                "n_clusters":          None,
                "n_noise":             None,
                "noise_pct":           None,
                "max_cluster_pct":     None,
                "median_cluster_size": None,
            })
            continue

    stats = utils.cluster_size_stats(labels)
    index_rows.append({
        "run_id":    r["run_id"],
        "algorithm": r["algorithm"],
        "graph":     r["graph"],
        "params":    json.dumps(r["params"]),
        "runtime_s": runtime_s,
        "status":    status,
        **stats,
    })
    utils.log(
        f"  [{i:3d}/{len(runs)}] {r['run_id']}: "
        f"n_clusters={stats['n_clusters']:>5}, "
        f"noise={stats['noise_pct']:>5.1f}%, "
        f"max%={stats['max_cluster_pct']:>5.2f} "
        f"({status}, {runtime_s}s)"
    )

# ── Save master index ─────────────────────────────────────────────────────────
df = pd.DataFrame(index_rows)
df.to_csv(index_path, index=False)
utils.log(f"\nSaved: {index_path}")
utils.log(f"Successful runs: {(df['status'].isin(['ok', 'cached'])).sum()} / {len(df)}")

if errors:
    utils.log("\nErrors:")
    for run_id, status in errors:
        utils.log(f"  {run_id}: {status}")

utils.log("\n=== Phase 0d-C done ===")
