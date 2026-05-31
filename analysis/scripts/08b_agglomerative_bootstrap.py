"""
Phase 0e: Parallel bootstrap stability for Agglomerative + connectivity.

Why separate from 08_metrics.py:
  Ward + prox_2500m connectivity costs ~14 min per iteration at n ≈ 10,747
  (the 80% subsample size). 50 iterations serial would be ~11 h.
  Parallelization requires joblib's loky (multiprocessing) backend, which on
  Windows requires the entry point to be `__main__`-safe. Rather than refactor
  the 562-line 08_metrics.py to wrap its module-level code under `if __name__
  == "__main__":`, we isolate the agglomerative bootstrap to this standalone
  script that is `__main__`-safe by design.

Pipeline:
  1. 08_metrics.py runs first; it produces grid_metrics.csv, best_per_algorithm.csv,
     and a bootstrap_stability.csv where the agglomerative row is a NaN placeholder.
  2. This script then loads the agglomerative winner config, runs 50 parallel
     bootstrap iterations with loky (~2 h wall time on 6 cores), and replaces
     the agglomerative row in bootstrap_stability.csv with the real numbers.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import config
import utils


# Top-level function (must be importable from worker processes on Windows-spawn).
# Imports inside the function so workers don't need to re-import the parent module.
def bootstrap_iter(sub_coords: np.ndarray,
                   full_labels_subset: np.ndarray,
                   n_clusters: int,
                   radius_m: int) -> float:
    """One bootstrap iteration: build prox graph on subset, fit Ward+connectivity, return ARI."""
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

    boot = AgglomerativeClustering(
        n_clusters=n_clusters,
        metric="euclidean",
        linkage="ward",
        connectivity=conn,
    ).fit_predict(sub_coords)
    return float(adjusted_rand_score(full_labels_subset, boot))


def main():
    utils.log("Loading filtered NFI...")
    gdf = utils.load_filtered_nfi()
    coords = utils.centroids_array(gdf)
    n = len(coords)
    utils.log(f"  {n:,} polygons")

    best_path = config.CLUSTERING_DIR / "best_per_algorithm.csv"
    if not best_path.exists():
        raise FileNotFoundError(f"{best_path} missing — run 08_metrics.py first")

    best = pd.read_csv(best_path)
    agg_rows = best[best["algorithm"] == "agglomerative"]
    if agg_rows.empty:
        raise RuntimeError("No agglomerative row in best_per_algorithm.csv")
    agg_row = agg_rows.iloc[0]
    params = json.loads(agg_row["params"]) if isinstance(agg_row["params"], str) else agg_row["params"]
    run_id = agg_row["run_id"]
    utils.log(f"Agglomerative winner: {run_id}")
    utils.log(f"  params:    {params}")
    utils.log(f"  full labels: {config.GRID_DIR / (run_id + '.npy')}")

    full_labels = np.load(config.GRID_DIR / f"{run_id}.npy")

    # Build the bootstrap iteration data (subset coords + reference labels)
    rng = np.random.default_rng(config.BOOTSTRAP_RANDOM_SEED)
    iter_data = []
    for _ in range(config.BOOTSTRAP_N_ITERATIONS):
        idx = rng.choice(n, int(config.BOOTSTRAP_SUBSAMPLE_FRAC * n), replace=False)
        iter_data.append((coords[idx], full_labels[idx]))

    radius_m = config.GRAPH_VARIANTS["prox_2500m"]["radius_m"]
    n_workers = 6  # 6 worker processes; each loads its own copy of sklearn etc.

    utils.log(f"\nLaunching parallel bootstrap: {n_workers} workers (loky), "
              f"{config.BOOTSTRAP_N_ITERATIONS} iterations")
    utils.log(f"  Expected runtime: ~2-2.5 h with true multiprocessing parallelism")
    t0 = time.time()
    results = Parallel(n_jobs=n_workers, verbose=10, backend="loky")(
        delayed(bootstrap_iter)(sc, fl, params["n_clusters"], radius_m)
        for sc, fl in iter_data
    )
    elapsed = time.time() - t0

    aris = [r for r in results
            if r is not None and not (isinstance(r, float) and np.isnan(r))]
    utils.log(f"\n  {len(aris)}/{config.BOOTSTRAP_N_ITERATIONS} iterations succeeded "
              f"in {elapsed:.1f}s ({elapsed/60:.1f} min)")

    if not aris:
        raise RuntimeError("All parallel bootstrap iterations failed")

    aris = np.array(aris)
    new_row = {
        "algorithm":    "agglomerative",
        "run_id":       run_id,
        "mean_ari":     round(float(aris.mean()), 4),
        "ari_lo":       round(float(np.percentile(aris, 2.5)), 4),
        "ari_hi":       round(float(np.percentile(aris, 97.5)), 4),
        "n_iterations": int(len(aris)),
        "note":         f"parallel bootstrap (joblib loky, {n_workers} workers); "
                        f"Ward + prox_2500m connectivity rebuilt per iter",
    }
    utils.log(f"\nAgglomerative bootstrap ARI: {new_row['mean_ari']:.3f} "
              f"[{new_row['ari_lo']:.3f}, {new_row['ari_hi']:.3f}], "
              f"n={new_row['n_iterations']}")

    # Replace the agglomerative row in bootstrap_stability.csv
    stab_path = config.CLUSTERING_DIR / "bootstrap_stability.csv"
    if stab_path.exists():
        stab = pd.read_csv(stab_path)
        stab = stab[stab["algorithm"] != "agglomerative"]
        stab = pd.concat([stab, pd.DataFrame([new_row])], ignore_index=True)
    else:
        stab = pd.DataFrame([new_row])
    # Preserve column order
    cols = ["algorithm", "run_id", "mean_ari", "ari_lo", "ari_hi", "n_iterations", "note"]
    stab = stab[cols]
    stab.to_csv(stab_path, index=False)
    utils.log(f"Saved: {stab_path}")


if __name__ == "__main__":
    main()
