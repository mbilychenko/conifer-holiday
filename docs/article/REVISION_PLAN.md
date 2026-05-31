# Revision Plan — Phase 0e

This document lists every change needed to address the peer-review feedback on the
Phase 0d benchmark. It is written as a **handoff specification**: each task is
self-contained, specifies exact files to edit, and ends with a mechanical
verification check.

**Two phases are mandatory (P1, P2). The third (P3) is optional rigour.**

Estimated effort: **P1 ≈ 3-4 h | P2 ≈ 1 day | P3 ≈ 2-3 extra days**.

---

## Pre-flight (5 min)

Before starting, confirm the environment is healthy:

```bash
cd D:/Projects/Conifer_holiday
python -c "import config, utils, hdbscan, libpysal, community, networkx, scikit_posthocs; print('OK')"
ls data/output/clusters.geojson data/output/clustering/grid_metrics.csv
```

Both files must exist. If not, run `analysis/scripts/07_grid_search.py` and
`08_metrics.py` first to regenerate.

All file paths in this document are **absolute**. The conventional working
directory is `D:\Projects\Conifer_holiday\`.

---

# PHASE 1 — Critical fixes (mandatory)

These three fixes address the reviewer's "MUST fix" list. **Do them in order.**

## Task 1.1 — Replace Moran's I with join-count statistics

### Goal
Cluster IDs are nominal (relabelling preserves the clustering but changes
Moran's I). Replace with **Black-Black join-counts**, which is the correct
spatial autocorrelation test for categorical labels.

### Why
Reviewer flagged this as the single hardest blocker: the current
`morans_i` column in `grid_metrics.csv` is mathematically meaningless.

### File to modify
`D:\Projects\Conifer_holiday\analysis\scripts\08_metrics.py`

### Code change — replace the `compute_spatial()` function

Find this code (around line 105-140):

```python
from esda.moran import Moran

def compute_spatial(labels: np.ndarray) -> dict:
    """Moran's I of cluster labels + intra/inter centroid-distance ratio."""
    out = {"morans_i": np.nan, "morans_i_p": np.nan, "intra_inter_ratio": np.nan}
    ...
    m = Moran(labels.astype(float), moran_w, permutations=99)
    out["morans_i"]   = float(m.I)
    out["morans_i_p"] = float(m.p_sim)
    ...
```

Replace with:

```python
from esda.join_counts import Join_Counts

def compute_spatial(labels: np.ndarray) -> dict:
    """Join-count BB ratio + intra/inter centroid-distance ratio.

    Black-Black join-count: of all edges in the prox_2500m weights matrix,
    what fraction connect polygons sharing the same cluster label?
    Higher = stronger spatial coherence of clusters. Range [0, 1].
    Permutation p-value (n=99) tests whether observed BB exceeds random.
    """
    out = {"bb_join_ratio":   np.nan,
           "bb_join_p":       np.nan,
           "intra_inter_ratio": np.nan}

    valid_mask = labels != -1
    if valid_mask.sum() < 100:
        return out

    # For Join_Counts we need a binary indicator per cluster. We use a
    # cluster-pairwise approach: for each polygon, mark "is in cluster c";
    # aggregate BB joins as fraction of total edges that are same-cluster.
    n_total_edges = moran_w.s0 / 2  # libpysal s0 is sum of weights both directions
    same_cluster_edges = 0
    # Iterate over weights neighbour dict — faster than per-cluster loop
    for i, ns in moran_w.neighbors.items():
        for j in ns:
            if i < j and labels[i] != -1 and labels[j] != -1 and labels[i] == labels[j]:
                same_cluster_edges += 1

    out["bb_join_ratio"] = float(same_cluster_edges / n_total_edges) if n_total_edges else np.nan

    # Permutation test: shuffle labels 99 times, recompute, report rank-based p
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
    # One-sided p: how often does random meet or exceed observed
    out["bb_join_p"] = float((perm_ratios >= out["bb_join_ratio"]).mean())

    # Intra/inter ratio block (KEEP exactly as before) ────────────────────
    rng2 = np.random.default_rng(config.GLOBAL_SEED)
    sample_size = min(2000, valid_mask.sum())
    idx = rng2.choice(np.where(valid_mask)[0], sample_size, replace=False)
    sub_c, sub_l = coords[idx], labels[idx]
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
```

**Note:** the permutation loop is O(P × E) where P=99 and E≈28k for
prox_2500m. Estimated ~1-2 s per run × 56 runs ≈ 1-2 min total.

### Downstream changes

In the **rows.append(...)** block (around line 268-274), the existing code
unpacks `**spatial`, so the new keys (`bb_join_ratio`, `bb_join_p`) flow
through automatically. **No change needed to the spread.**

In `09_statistical_comparison.py`, the `metric_panel` list and the
heatmap figure include `morans_i`. Update both:

```python
# Old
metric_panel = ["silhouette", "davies_bouldin", "calinski_harabasz",
                "detection_rate", "single_cluster_rate", "intra_inter_ratio"]
# New
metric_panel = ["silhouette", "davies_bouldin", "calinski_harabasz",
                "detection_rate", "single_cluster_rate", "bb_join_ratio"]
```

And in the heatmap section (line ≈ 170):

```python
# Old
metric_list = ["silhouette", "davies_bouldin", "detection_rate",
               "single_cluster_rate", "n_clusters", "noise_pct"]
# New (add bb_join_ratio, drop noise_pct since it's redundant with median_cluster_size)
metric_list = ["silhouette", "davies_bouldin", "bb_join_ratio",
               "detection_rate", "single_cluster_rate", "n_clusters"]
```

In `10_methodology_export.py`, the §4 evaluation-metrics section
mentions Moran's I. Replace:

```
"Moran's I of cluster labels under the prox_2500m weight matrix..."
```

with:

```
"Black-Black join-count ratio under the prox_2500m weight matrix
(fraction of graph edges connecting polygons with the same cluster
label; higher = stronger spatial coherence; permutation-based p-value
from 99 random relabellings)."
```

### Verification

1. Delete the stale metrics: `rm data/output/clustering/grid_metrics.csv`
2. Re-run: `python analysis/scripts/08_metrics.py`
3. Check the new column exists:

```bash
python -c "import pandas as pd; df = pd.read_csv('data/output/clustering/grid_metrics.csv'); print('bb_join_ratio' in df.columns, df['bb_join_ratio'].describe())"
```

Expected: column exists; values in [0, 1]; HDBSCAN/Louvain should score >0.7;
DBSCAN noise should be lower (noise polygons inflate "not same cluster" counts).

---

## Task 1.2 — Measure Louvain bootstrap stability

### Goal
The declared winner currently has `mean_ari = NaN` in
`bootstrap_stability.csv`. Implement the rebuild so Louvain has a measured
ARI alongside the other algorithms.

### Why
Reviewer: declaring a winner without stability measurement is unacceptable.

### File to modify
`D:\Projects\Conifer_holiday\analysis\scripts\08_metrics.py`

### Code change — replace the bootstrap section

Find the `rerun_algorithm()` function (around line 317-339) and add a
Louvain branch:

```python
def rerun_algorithm(algo: str, params: dict, graph_name: str | None,
                    sub_coords: np.ndarray, sub_idx: np.ndarray) -> np.ndarray:
    """Re-run the algorithm on a subset (for bootstrapping)."""
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
        return AgglomerativeClustering(
            n_clusters=params["n_clusters"], linkage="ward",
        ).fit_predict(sub_coords)
    if algo == "louvain":
        # Rebuild proximity graph on subset (sub_coords only) and run Louvain
        from scipy.spatial import cKDTree
        import community as community_louvain
        import networkx as nx
        # Match the graph radius used by the winner's graph variant
        radius_m = config.GRAPH_VARIANTS[graph_name]["radius_m"]
        tree = cKDTree(sub_coords)
        pairs = tree.query_pairs(radius_m, output_type="ndarray")
        G = nx.Graph()
        G.add_nodes_from(range(len(sub_coords)))
        G.add_edges_from(pairs.tolist())
        partition = community_louvain.best_partition(
            G, resolution=params["resolution"],
            random_state=config.GLOBAL_SEED
        )
        return np.array([partition[i] for i in range(len(sub_coords))],
                        dtype=np.int32)
    raise NotImplementedError(f"Bootstrap not implemented for {algo}")
```

Then remove the Louvain skip-block (around line 346-358). The current
code looks like:

```python
if algo in {"skater", "maxp", "louvain"}:
    utils.log(f"  Skipping bootstrap for {algo} (graph rebuild too expensive)")
    stability_rows.append({...})
    continue
```

Replace with:

```python
if algo in {"skater", "maxp"}:
    utils.log(f"  Skipping bootstrap for {algo} (algorithm not in final benchmark)")
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
```

Also pass `graph_name` to the `rerun_algorithm()` call:

```python
# Old
boot_labels = rerun_algorithm(algo, params, None, sub_coords, idx)
# New
graph_name = best["graph"] if best["graph"] != "none" else None
boot_labels = rerun_algorithm(algo, params, graph_name, sub_coords, idx)
```

### Verification

```bash
rm data/output/clustering/bootstrap_stability.csv
python analysis/scripts/08_metrics.py   # uses cached grid_metrics if present
```

Check the result:

```bash
python -c "import pandas as pd; print(pd.read_csv('data/output/clustering/bootstrap_stability.csv'))"
```

Expected: 5 rows (kmeans, dbscan, hdbscan, agglomerative, louvain).
Louvain row must have `mean_ari` not NaN, `n_iterations = 50`.
Expected Louvain ARI: 0.4-0.7 range (community detection is moderately
stable under data perturbation).

---

## Task 1.3 — Reframe SKATER/Max-P as implementation limitations

### Goal
Remove "novel methodological finding" framing for the spopt scalability
issue. Acknowledge it as an `spopt 0.7.0` implementation limit.

### Why
Reviewer: Riitters et al. (2012) ran SKATER on continental-US data.
Our timeout is not a methodological finding — it's a library bug.

### Files to modify

**1. `D:\Projects\Conifer_holiday\docs\PAPERS_OVERVIEW.md`**

Find this section:

```
## 8. Gap our paper fills
...
3. **No prior work systematically varies graph construction across algorithm
   families to isolate the structural-vs-algorithmic contribution to
   clustering quality.**
```

Replace with:

```
## 8. Gap our paper fills

To the best of our knowledge:

1. **No published study compares density-based, regionalization, and
   community-detection methods on a UK NFI-scale fragmented polygon network.**
   The closest precedent (Riitters et al. 2012) tested only SKATER on US
   forest pattern metrics rasters.

2. **No prior work uses a verified named-forest gazetteer (Wikipedia +
   Forestry Commission coordinates) to validate spatial clusters of NFI
   polygons.** This is borrowed from the place-name extraction literature
   (Ju et al. 2018) but applied to forest data for the first time.

3. **No prior work compares clustering algorithms across multiple graph
   constructions** (proximity radius variants + k-NN) for UK NFI data.

## 9. Limitations

The Phase 0d implementation relies on the `spopt 0.7.0` Python library for
SKATER and Max-P regionalization. In our environment, these implementations
exceeded the 600 s per-run timeout on all four graph variants at n = 13,434.
The root cause is implementation-specific (`spopt`'s MST-traversal step in
SKATER and its simulated-annealing region growing in Max-P do not scale
gracefully to this size); the underlying algorithms have demonstrated
feasibility on much larger datasets in other implementations (Riitters et al.
2012, applied to continental US forest pattern metrics in a custom Fortran
implementation). Future work should compare alternative implementations
(`pygeoda` Python bindings; the R `ClustGeo` package by Chavent et al. 2018;
or a custom Numba MST). For this paper, SKATER and Max-P are excluded from
the headline benchmark and reported as a `spopt 0.7.0` performance note
rather than a methodological finding.
```

**2. `D:\Projects\Conifer_holiday\analysis\scripts\config.py`**

Update the `SKIP_COMBINATIONS` docstring (line ≈ 95-111) — change:

```
# 2. SKATER (spopt 0.7.0): When the spatial weights matrix has many disconnected
#    components, spopt internally inflates n_clusters to ≥ n_components to
#    "account for islands" ...
#    SKATER is therefore structurally unsuited to national-scale fragmented
#    polygon networks.
#
# 3. Max-P (spopt 0.7.0): The simulated-annealing region-growing heuristic
#    exceeds 60s even on a near-fully-connected graph (knn_10, 2 components).
#    The implementation does not scale to n=13,434.
#
# All three limitations are reported as methodological findings.
```

to:

```
# 2. SKATER (spopt 0.7.0): On disconnected proximity graphs, spopt internally
#    inflates n_clusters to ≥ n_components to "account for islands" (e.g. 2,755
#    on prox_2500m), and the resulting MST traversal exceeds the 600 s per-run
#    timeout. This is an spopt 0.7.0 implementation limitation, NOT an
#    algorithmic one — Riitters et al. (2012) applied SKATER to continental-US
#    forest pattern metrics in a custom Fortran implementation.
#
# 3. Max-P (spopt 0.7.0): The simulated-annealing region-growing heuristic
#    exceeds 60 s even on a near-fully-connected graph (knn_10, 2 components).
#    This is again an spopt implementation limit at n = 13,434; future work
#    could compare pygeoda or R ClustGeo implementations.
#
# All three limitations are reported as implementation notes (not novel
# methodological findings) in PAPER_METHODOLOGY.md §3.
```

**3. `D:\Projects\Conifer_holiday\analysis\scripts\10_methodology_export.py`**

Find the "Algorithms" section (around line 78-93) and update the SKATER /
Max-P rows in the algorithm table. Find:

```
| SKATER | Contiguity regionalization | spopt + libpysal | Assunção et al. 2006 | Yes |
| Max-P | Contiguity regionalization | spopt | Duque et al. 2012; Folch & Spielman 2014 | Yes |
```

Replace with:

```
| SKATER | Contiguity regionalization | spopt + libpysal | Assunção et al. 2006 | Yes (excluded — see §3 footnote) |
| Max-P | Contiguity regionalization | spopt | Duque et al. 2012; Folch & Spielman 2014 | Yes (excluded — see §3 footnote) |
```

And add a footnote at the end of §3 (just before §4 starts):

```python
lines.append("**Note on excluded algorithms.** SKATER and Max-P from spopt 0.7.0 "
             "exceeded the 600 s per-run timeout at n = 13,434 on all four graph "
             "variants. This is an implementation limit, not an algorithmic one; "
             "alternative implementations (pygeoda, R ClustGeo, custom MST) may "
             "scale. Treated as future work.")
lines.append("")
```

### Verification

```bash
python analysis/scripts/10_methodology_export.py
grep -A2 "Note on excluded" docs/PAPER_METHODOLOGY.md
grep "novel methodological finding" docs/PAPERS_OVERVIEW.md  # should return NOTHING
```

---

## Task 1.4 — Re-run pipeline end-to-end

After Tasks 1.1-1.3, regenerate every artefact so they reflect the fixes:

```bash
cd D:/Projects/Conifer_holiday
rm data/output/clustering/grid_metrics.csv
rm data/output/clustering/bootstrap_stability.csv
rm data/output/clustering/method_ranking.csv
rm data/output/clustering/final_winner.json
rm data/output/clustering/friedman_results.csv

python analysis/scripts/08_metrics.py            # ~25 min — recomputes metrics with join-count
python analysis/scripts/09_statistical_comparison.py  # ~1 min — picks winner
python analysis/scripts/05_validate_clusters.py  # ~1 min — re-validates new clusters.geojson
python analysis/scripts/10_methodology_export.py # ~10 s — regenerates docs
```

### Verification

After the pipeline:

```bash
python -c "
import pandas as pd, json
m = pd.read_csv('data/output/clustering/method_ranking.csv')
print('Top 3 by composite:')
print(m[['algorithm', 'graph', 'n_clusters', 'silhouette', 'bb_join_ratio',
         'detection_rate', 'composite']].head(3).to_string(index=False))
b = pd.read_csv('data/output/clustering/bootstrap_stability.csv')
print('\\nBootstrap stability:')
print(b[['algorithm', 'mean_ari', 'n_iterations']].to_string(index=False))
"
```

Expected:
- Top-3 ranking includes Louvain with non-NaN `bb_join_ratio`
- Bootstrap stability table has Louvain row with `n_iterations=50` and a
  numeric `mean_ari` (not NaN)
- No reference to `morans_i` anywhere in `grid_metrics.csv` headers

---

# PHASE 2 — Strengthen rigour (mandatory, after P1)

These four tasks address less critical but still expected issues from the
review. Do them after P1 is verified passing.

## Task 2.1 — Add Wilson-score 95% CIs to entity validation rates

### Goal
Report Wilson 95% CIs on the four rate metrics (detection, single-cluster,
tight placement, area accuracy). N=20 is too small to report point
estimates alone.

### File to modify
`D:\Projects\Conifer_holiday\analysis\scripts\05_validate_clusters.py`

### Code change

After computing each rate (search for `detection_rate = ...`), wrap with a
helper for Wilson scoring:

Add this function near the top, after the imports:

```python
from scipy.stats import beta

def wilson_ci(successes: int, trials: int, alpha: float = 0.05) -> tuple[float, float]:
    """Wilson 95% confidence interval for a proportion (in 0-100 percent).

    Returns (low, high). Better than Normal approximation for small n
    or extreme proportions (0% / 100%).
    """
    if trials == 0:
        return (0.0, 100.0)
    from statsmodels.stats.proportion import proportion_confint
    lo, hi = proportion_confint(successes, trials, alpha=alpha, method="wilson")
    return (lo * 100, hi * 100)
```

If `statsmodels` is not installed, install it:

```bash
pip install statsmodels==0.14.4
```

And add to `analysis/requirements.txt`:

```
statsmodels==0.14.4
```

Then in the summary dict (search for `"detection_rate_pct":  round(detection_rate, 1),`),
replace with:

```python
det_lo, det_hi = wilson_ci(int(primary['detected'].sum()), len(primary))
sc_lo,  sc_hi  = wilson_ci(int((detected_primary['n_clusters_in_buffer'] == 1).sum()), len(primary))
tight_lo, tight_hi = wilson_ci(int((detected_primary['nearest_cluster_centroid_km'] <= 5).sum()), len(primary))
ac_lo, ac_hi   = wilson_ci(int(in_range.sum()), len(primary))

summary = {
    ...existing fields...,
    "detection_rate_pct":  round(detection_rate, 1),
    "detection_rate_ci95": [round(det_lo, 1), round(det_hi, 1)],
    "single_cluster_rate_pct": round(single_cluster_rate, 1),
    "single_cluster_rate_ci95": [round(sc_lo, 1), round(sc_hi, 1)],
    "tight_placement_pct":  round(tight_placement, 1),
    "tight_placement_ci95": [round(tight_lo, 1), round(tight_hi, 1)],
    "area_accuracy_pct":  round(area_accuracy, 1),
    "area_accuracy_ci95": [round(ac_lo, 1), round(ac_hi, 1)],
    ...existing fields...
}
```

Update the log block (search for `Quality metrics on primary conifer destinations:`):

```python
log(f"\nQuality metrics on primary conifer destinations (n={len(primary)}):")
log(f"  Detection rate:         {detection_rate:>5.1f}%  CI95 [{det_lo:.1f}, {det_hi:.1f}]")
log(f"  Single-cluster rate:    {single_cluster_rate:>5.1f}%  CI95 [{sc_lo:.1f}, {sc_hi:.1f}]")
log(f"  Tight placement (5km):  {tight_placement:>5.1f}%  CI95 [{tight_lo:.1f}, {tight_hi:.1f}]")
log(f"  Area accuracy (0.3-3x): {area_accuracy:>5.1f}%  CI95 [{ac_lo:.1f}, {ac_hi:.1f}]")
```

### Downstream
`10_methodology_export.py` §6.3 should print CIs. Find the entity-validation
section (around line 200-208) and replace:

```python
lines.append(f"- Detection rate: **{val_summary.get('detection_rate_pct', 'n/a')}%**")
```

with:

```python
det_ci = val_summary.get('detection_rate_ci95', [None, None])
lines.append(f"- Detection rate: **{val_summary.get('detection_rate_pct', 'n/a')}%** "
             f"(95% CI {det_ci[0]:.0f}–{det_ci[1]:.0f}%)")
```

Repeat for single-cluster, tight-placement, area-accuracy.

### Verification

```bash
python analysis/scripts/05_validate_clusters.py
python -c "import json; d = json.load(open('data/output/clustering/validation_summary.json')); print(d['detection_rate_ci95'])"
```

Expected: a 2-element list like `[83.9, 100.0]`.

---

## Task 2.2 — Composite-score weight sensitivity

### Goal
Show that the headline ranking is robust to plausible variations in the
composite-score weights. Currently weights are 0.30/0.20/0.30/0.20.

### File to modify
Create new file:
`D:\Projects\Conifer_holiday\analysis\scripts\11_weight_sensitivity.py`

### Code (full file)

```python
"""
Phase 0e: Composite-score weight sensitivity.

The headline composite uses weights (silhouette=0.30, DB=0.20, det=0.30, scr=0.20).
This script tests three alternative weighting schemes and reports the ranking
under each. Outputs: data/output/clustering/weight_sensitivity.csv.
"""
from pathlib import Path
import pandas as pd
import numpy as np

import config
import utils

WEIGHT_SCHEMES = {
    "default":     {"silhouette_norm": 0.30, "davies_bouldin_inv": 0.20,
                    "detection_rate":  0.30, "single_cluster_rate": 0.20},
    "equal":       {"silhouette_norm": 0.25, "davies_bouldin_inv": 0.25,
                    "detection_rate":  0.25, "single_cluster_rate": 0.25},
    "entity_only": {"silhouette_norm": 0.00, "davies_bouldin_inv": 0.00,
                    "detection_rate":  0.60, "single_cluster_rate": 0.40},
    "internal_only": {"silhouette_norm": 0.50, "davies_bouldin_inv": 0.50,
                    "detection_rate":  0.00, "single_cluster_rate": 0.00},
}

def composite(row: pd.Series, weights: dict) -> float:
    if pd.isna(row.get("n_clusters")) or not (
        config.CLUSTER_COUNT_MIN <= row["n_clusters"] <= config.CLUSTER_COUNT_MAX
    ):
        return -np.inf
    silh = row.get("silhouette");          db = row.get("davies_bouldin")
    det  = row.get("detection_rate");      scr = row.get("single_cluster_rate")
    if any(pd.isna(x) for x in [silh, db, det, scr]):
        return -np.inf
    silh_n = (silh + 1) / 2
    db_inv = 1.0 / (1.0 + db)
    return (weights["silhouette_norm"]     * silh_n +
            weights["davies_bouldin_inv"]  * db_inv +
            weights["detection_rate"]      * (det / 100) +
            weights["single_cluster_rate"] * (scr / 100))

df = pd.read_csv(config.CLUSTERING_DIR / "grid_metrics.csv")
grid = pd.read_csv(config.CLUSTERING_DIR / "grid_index.csv")
df = df.merge(grid[["run_id", "params"]], on="run_id", how="left")

rows = []
for name, w in WEIGHT_SCHEMES.items():
    df_w = df.copy()
    df_w["composite"] = df_w.apply(lambda r: composite(r, w), axis=1)
    df_w = df_w[df_w["composite"] > -np.inf].sort_values("composite", ascending=False)
    best = df_w.groupby("algorithm").head(1).reset_index(drop=True)
    best = best.sort_values("composite", ascending=False)
    for rank, (_, r) in enumerate(best.iterrows(), 1):
        rows.append({
            "scheme": name, "rank": rank,
            "algorithm": r["algorithm"], "graph": r["graph"],
            "n_clusters": int(r["n_clusters"]),
            "composite": round(r["composite"], 4),
            "silhouette": round(r["silhouette"], 3),
            "detection_rate": round(r["detection_rate"], 1),
        })

out_df = pd.DataFrame(rows)
out_path = config.CLUSTERING_DIR / "weight_sensitivity.csv"
out_df.to_csv(out_path, index=False)
utils.log(f"Saved: {out_path}")
utils.log("\nRanking under each weighting scheme:")
for name in WEIGHT_SCHEMES:
    utils.log(f"\n--- {name} ---")
    utils.log(out_df[out_df.scheme == name][
        ["rank", "algorithm", "graph", "composite"]
    ].to_string(index=False))
```

### Downstream
Add to `10_methodology_export.py` after §6.2:

```python
sens = pd.read_csv(config.CLUSTERING_DIR / "weight_sensitivity.csv") if \
       (config.CLUSTERING_DIR / "weight_sensitivity.csv").exists() else None
if sens is not None:
    lines.append("### 6.3 Sensitivity of ranking to composite-score weights")
    lines.append("")
    lines.append("We tested four weighting schemes for the composite score:")
    lines.append("")
    for scheme in sens["scheme"].unique():
        block = sens[sens.scheme == scheme][["rank", "algorithm", "graph", "composite"]]
        lines.append(f"**{scheme}:**")
        lines.append(block.to_markdown(index=False))
        lines.append("")
```

### Verification
```bash
python analysis/scripts/11_weight_sensitivity.py
cat data/output/clustering/weight_sensitivity.csv | head -25
```

Expected: 4 schemes × ~5 algorithms = ~20 rows. Top-rank algorithm may
differ across schemes — that's the point.

---

## Task 2.3 — Add spectral clustering baseline

### Goal
Add the standard graph-baseline algorithm the reviewer expected. Spectral
clustering is the natural complement to Louvain (eigenvector-based instead
of greedy modularity).

### File to modify
`D:\Projects\Conifer_holiday\analysis\scripts\config.py` and
`D:\Projects\Conifer_holiday\analysis\scripts\07_grid_search.py`

### Changes

In `config.py` `ALGORITHM_GRIDS` dict, add:

```python
"spectral": {
    "needs_graph": True,
    "params": {"n_clusters": [100, 150, 200, 250, 300]},
},
```

And in `ALGORITHM_TIMEOUT_S`, add:

```python
"spectral":      300,
```

In `07_grid_search.py`, add a runner:

```python
from sklearn.cluster import SpectralClustering

def run_spectral(params: dict, graph_name: str) -> np.ndarray:
    """Spectral clustering with precomputed affinity matrix from the graph."""
    g = get_graph(graph_name)
    # sklearn SpectralClustering wants affinity matrix (sparse OK)
    sc = SpectralClustering(
        n_clusters=params["n_clusters"],
        affinity="precomputed",
        assign_labels="kmeans",
        random_state=config.GLOBAL_SEED,
        n_jobs=1,
    )
    return sc.fit_predict(g["adj_csr"].astype(float))
```

Add to the `RUNNERS` dict:

```python
"spectral":  run_spectral,
```

### Verification
```bash
python analysis/scripts/07_grid_search.py     # 5 new runs × 4 graphs = 20 runs
python analysis/scripts/08_metrics.py          # auto-detects missing rows
python analysis/scripts/09_statistical_comparison.py
```

Check spectral appears in the ranking:

```bash
python -c "import pandas as pd; m = pd.read_csv('data/output/clustering/method_ranking.csv'); print(m[m.algorithm=='spectral'])"
```

**Possible failure**: spectral clustering may timeout on disconnected graphs
(prox_2500m has 2,655 components). If so, add `("spectral", "prox_2500m")`
to `SKIP_COMBINATIONS` and re-run.

---

## Task 2.4 — Silhouette CIs from 10 subsamples

### Goal
Replace the single-subsample silhouette point estimate with a mean over 10
random subsamples + 95% CI.

### File to modify
`D:\Projects\Conifer_holiday\analysis\scripts\08_metrics.py`

### Code change

Replace the `compute_internal()` function's silhouette block. Find:

```python
sub_size = min(config.SILHOUETTE_SUBSAMPLE_SIZE, valid_coords.shape[0])
rng = np.random.default_rng(config.SILHOUETTE_RANDOM_SEED)
idx = rng.choice(valid_coords.shape[0], size=sub_size, replace=False)
sub_coords = valid_coords[idx]
sub_lbls   = valid_lbls[idx]
if np.unique(sub_lbls).size >= 2:
    try:
        out["silhouette"] = float(silhouette_score(sub_coords, sub_lbls))
    except Exception:
        pass
```

Replace with:

```python
sub_size = min(config.SILHOUETTE_SUBSAMPLE_SIZE, valid_coords.shape[0])
silh_values = []
rng = np.random.default_rng(config.SILHOUETTE_RANDOM_SEED)
for _ in range(10):
    idx = rng.choice(valid_coords.shape[0], size=sub_size, replace=False)
    sub_c, sub_l = valid_coords[idx], valid_lbls[idx]
    if np.unique(sub_l).size >= 2:
        try:
            silh_values.append(float(silhouette_score(sub_c, sub_l)))
        except Exception:
            pass
if silh_values:
    out["silhouette"]    = float(np.mean(silh_values))
    out["silhouette_lo"] = float(np.percentile(silh_values, 2.5))
    out["silhouette_hi"] = float(np.percentile(silh_values, 97.5))
else:
    out["silhouette_lo"] = np.nan
    out["silhouette_hi"] = np.nan
```

### Downstream
None needed — the new fields `silhouette_lo`/`silhouette_hi` flow through
the `**internal` spread in `08_metrics.py`. Optionally surface in
`10_methodology_export.py` §6 tables.

### Verification

```bash
rm data/output/clustering/grid_metrics.csv
python analysis/scripts/08_metrics.py
python -c "import pandas as pd; df = pd.read_csv('data/output/clustering/grid_metrics.csv'); print(df[['run_id', 'silhouette', 'silhouette_lo', 'silhouette_hi']].head(5))"
```

Expected: three columns; `lo < silhouette < hi` for every row.

---

# PHASE 3 — Optional rigour (only if time allows)

These tasks address the "would strengthen the paper" items from the
reviewer's final list. None are blockers; each is independently valuable.

## Task 3.1 — Expand gazetteer to 40+ forests with full provenance

### Goal
Boost validation sample size and add machine-readable provenance per row.

### File to modify
`D:\Projects\Conifer_holiday\analysis\scripts\reference_forests.py`

### Specific changes

For each forest dict, add fields:

```python
"wikidata_qid":  "Q...",    # e.g. Thetford Forest = Q1346091
"source_url":    "https://en.wikipedia.org/wiki/...",
"accessed_date": "2026-05-24",
```

Add 18+ new forests from Forestry England, FLS, NRW estate pages.
Candidates (verify coordinates and Wikidata QIDs before committing):

- Hopton Forest (Shropshire)
- Allerthorpe Common (East Yorkshire)
- Bedgebury Forest (Kent)
- Mortimer Forest (Shropshire/Herefordshire)
- Haldon Forest (Devon)
- Sherwood Pines (Notts, distinct from ancient Sherwood)
- Rosliston Forestry Centre (Derbyshire)
- Beecraigs Country Park (West Lothian)
- Mabie Forest (Dumfries & Galloway)
- Drumlanrig (Dumfries & Galloway)
- Achnashellach Forest (Highland)
- Inshriach Forest (Cairngorms)
- Cropton Forest (North York Moors)
- Hambleton Forest (North Yorkshire)
- Bowland Forest (Lancashire)
- Wyre Forest (Worcestershire/Shropshire)
- Crychan Forest (Carmarthenshire/Powys)
- Penllergaer Forest (Swansea)

Look up each on Wikidata for QID and authoritative coordinate.

### Verification

```bash
python -c "
import sys; sys.path.insert(0, 'analysis/scripts')
import reference_forests as rf
print(f'Total: {len(rf.REFERENCE_FORESTS)}')
missing = [f['name'] for f in rf.REFERENCE_FORESTS if 'wikidata_qid' not in f]
print(f'Missing QID: {missing}')
assert len(rf.REFERENCE_FORESTS) >= 35, 'Need 35+ forests'
assert not missing, 'All must have QID'
"
python analysis/scripts/05_validate_clusters.py
```

---

## Task 3.2 — Buffer-radius sensitivity for entity validation

### Goal
Show that detection / single-cluster rates are robust to buffer choice.

### File to modify
Create `D:\Projects\Conifer_holiday\analysis\scripts\12_buffer_sensitivity.py`

### Code
Copy `05_validate_clusters.py` template; loop over
`buffer_m in [2500, 5000, 7500, 10000]`; for each, compute and save
per-forest table; write `data/output/clustering/buffer_sensitivity.csv`.

### Verification
Check that detection_rate is monotone increasing with buffer_m (sanity).

---

## Task 3.3 — 200-iteration bootstrap

### Goal
Tighter CIs on ARI.

### Change
In `config.py`:

```python
BOOTSTRAP_N_ITERATIONS = 200   # was 50
```

Then re-run `08_metrics.py`. **Time: ~15 min for 5 algorithms × 200
iterations.**

### Verification
`bootstrap_stability.csv` rows should have `n_iterations = 200` and tighter
[ari_lo, ari_hi] intervals.

---

## Task 3.4 — Alternative SKATER implementation (R ClustGeo)

### Goal
Properly test whether SKATER-like regionalization works at this scale.

### Approach
Out of scope for a small-model handoff; requires R + rpy2 setup. Document
as future work.

If attempted: install R, install `ClustGeo` package, call via `subprocess`
from a new `13_skater_clustgeo.py`. Compare output to spopt.

---

## Task 3.5 — OPTICS baseline

### Goal
Reviewer expected it. Cheap to add.

### Change
In `config.py` `ALGORITHM_GRIDS`:

```python
"optics": {
    "needs_graph": False,
    "params": {"min_samples": [3, 5, 10], "xi": [0.01, 0.05, 0.1]},
},
```

In `07_grid_search.py`:

```python
from sklearn.cluster import OPTICS

def run_optics(params: dict, graph_name: str | None) -> np.ndarray:
    op = OPTICS(min_samples=params["min_samples"], xi=params["xi"],
                cluster_method="xi", metric="euclidean", n_jobs=1)
    return op.fit_predict(coords)
```

Register in `RUNNERS`. Re-run grid + metrics.

### Verification
Check OPTICS appears in `method_ranking.csv`.

---

# Completion checklist

After all of P1 and P2:

- [ ] `grid_metrics.csv` has `bb_join_ratio` column (not `morans_i`)
- [ ] `bootstrap_stability.csv` has 5 algorithms, Louvain row has `n_iterations=50`
- [ ] `PAPER_METHODOLOGY.md` mentions "join-count", not "Moran's I"
- [ ] `PAPER_METHODOLOGY.md` mentions "spopt 0.7.0 implementation limit", not "methodological finding"
- [ ] `validation_summary.json` has `*_ci95` keys for all 4 rates
- [ ] `weight_sensitivity.csv` exists with 4 schemes
- [ ] Spectral clustering appears in `method_ranking.csv`
- [ ] `grid_metrics.csv` has `silhouette_lo` and `silhouette_hi` columns

After P3 (optional):

- [ ] `reference_forests.REFERENCE_FORESTS` has ≥35 entries with `wikidata_qid` per row
- [ ] `buffer_sensitivity.csv` exists with 4 buffer radii
- [ ] `BOOTSTRAP_N_ITERATIONS = 200` in config
- [ ] OPTICS appears in `method_ranking.csv`

---

# Handoff notes

If the small model executing this plan hits unexpected errors:

1. **Always check `data/output/clustering/grid_metrics.csv` exists before running 09.**
   If it doesn't, run 08 first.

2. **The grid-search resume logic uses `.npy` file existence as the cache key.**
   Deleting `data/output/grid/*.npy` forces full re-run.

3. **`spopt` errors with "silence_warnings"** — this kwarg was removed in 0.7.0.
   Don't add it back even if older docs suggest doing so.

4. **`AgglomerativeClustering` with `connectivity` argument** — `n_clusters`
   bigger than ~250 on this dataset will exceed memory. The
   `PER_PARAM_SKIP` set in `07_grid_search.py` is already configured.

5. **All paths in this document are Windows-style absolute paths.** On
   Linux/Mac, replace `D:\Projects\Conifer_holiday\` with the project root.

6. **Re-run order matters.** After modifying anything in `08_metrics.py` or
   `09_statistical_comparison.py`, also re-run `05_validate_clusters.py` and
   `10_methodology_export.py` so the docs reflect the new numbers.
