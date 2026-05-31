"""
Phase 0d-E: Statistical comparison and final winner selection.

Steps:
  1. Load grid_metrics.csv
  2. Pick the best parameter set per (algorithm, graph) cell using composite score
  3. Rank algorithms by composite of detection_rate + silhouette + DB inverse
  4. Friedman test across algorithms × ranks on each metric
  5. Nemenyi post-hoc if Friedman significant
  6. Generate critical-difference + box-plot figures
  7. Regenerate clusters.geojson from the overall winner

Outputs:
  data/output/clustering/method_ranking.csv
  data/output/clustering/figures/11_critical_difference.png
  data/output/clustering/figures/12_metric_comparison.png
  data/output/clusters.geojson  (overwritten with winner's clustering)
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scikit_posthocs as sp
from scipy.stats import friedmanchisquare

import config
import utils

utils.log("Loading grid_metrics.csv...")
metrics_path = config.CLUSTERING_DIR / "grid_metrics.csv"
df = pd.read_csv(metrics_path)

# Merge params from grid_index.csv (grid_metrics.csv doesn't carry it)
grid_index = pd.read_csv(config.CLUSTERING_DIR / "grid_index.csv")
df = df.merge(grid_index[["run_id", "params"]], on="run_id", how="left")

utils.log(f"  {len(df)} runs")


# ── Composite score (re-using the one defined in 08) ──────────────────────────
def composite(row: pd.Series) -> float:
    if pd.isna(row.get("n_clusters")) or not (
        config.CLUSTER_COUNT_MIN <= row["n_clusters"] <= config.CLUSTER_COUNT_MAX
    ):
        return -np.inf
    silh = row.get("silhouette")
    db   = row.get("davies_bouldin")
    det  = row.get("detection_rate")
    scr  = row.get("single_cluster_rate")
    if any(pd.isna(x) for x in [silh, db, det, scr]):
        return -np.inf
    silh_n = max(float(silh), 0.0)  # clip negative to 0; no partial credit for misclustering
    db_inv = 1.0 / (1.0 + db)
    w = config.COMPOSITE_WEIGHTS
    return (w["silhouette_norm"]     * silh_n +
            w["davies_bouldin_inv"]  * db_inv +
            w["detection_rate"]      * (det / 100) +
            w["single_cluster_rate"] * (scr / 100))

df["composite"] = df.apply(composite, axis=1)
df["composite_finite"] = df["composite"].replace([np.inf, -np.inf], np.nan)


# ── Best per (algorithm, graph) cell ──────────────────────────────────────────
ranked = (df.dropna(subset=["composite_finite"])
            .sort_values("composite_finite", ascending=False))
best_cells = ranked.groupby(["algorithm", "graph"]).head(1).reset_index(drop=True)
utils.log(f"\nBest config per (algorithm, graph): {len(best_cells)} cells")

# Best per algorithm (across all graphs)
best_per_algo = best_cells.sort_values("composite_finite", ascending=False)\
                          .groupby("algorithm").head(1).reset_index(drop=True)

ranking_cols = [
    "algorithm", "graph", "run_id", "params", "n_clusters", "noise_pct",
    "silhouette", "silhouette_lo", "silhouette_hi",
    "davies_bouldin", "calinski_harabasz",
    "bb_join_ratio", "bb_join_p", "intra_inter_ratio",
    "detection_rate", "single_cluster_rate", "tight_placement_rate",
    "area_accuracy_rate", "median_area_ratio", "composite",
]
ranking_cols = [c for c in ranking_cols if c in best_per_algo.columns]
ranking = best_per_algo[ranking_cols].sort_values("composite", ascending=False)
ranking_path = config.CLUSTERING_DIR / "method_ranking.csv"
ranking.to_csv(ranking_path, index=False)
utils.log(f"Saved: {ranking_path}")
utils.log("\n--- Final ranking (by composite score) ---")
utils.log(ranking.to_string(index=False))


# ── Friedman test across algorithms on selected metrics ──────────────────────
# We use the best-per-(algorithm, graph) results: each algorithm has up to 4 graph
# variants (or 1 for non-graph), giving an unbalanced design. Friedman requires
# repeated measures, so we restrict to graph-dependent algorithms run on all 4 graphs.
metric_panel = ["silhouette", "davies_bouldin", "calinski_harabasz",
                "detection_rate", "single_cluster_rate", "bb_join_ratio"]
metric_panel = [m for m in metric_panel if m in best_cells.columns]

# Construct a wide table: rows = graphs, cols = algorithms, values = metric
graph_algos = best_cells[best_cells["graph"] != "none"]["algorithm"].unique()
density_algos = best_cells[best_cells["graph"] == "none"]["algorithm"].unique()

utils.log(f"\nGraph-dependent algorithms: {list(graph_algos)}")
utils.log(f"Density/non-graph algorithms: {list(density_algos)} (one observation each)")

friedman_results = []
for metric in metric_panel:
    # Build N×K matrix where N = #graphs (4) and K = #graph_algos
    pivot = best_cells[best_cells["algorithm"].isin(graph_algos)].pivot_table(
        index="graph", columns="algorithm", values=metric
    )
    # Drop rows / columns with missing values
    pivot = pivot.dropna()
    if pivot.shape[0] < 3 or pivot.shape[1] < 3:
        friedman_results.append({"metric": metric, "statistic": np.nan, "p_value": np.nan,
                                  "n_graphs": pivot.shape[0], "n_algorithms": pivot.shape[1],
                                  "note": "insufficient data for Friedman"})
        continue
    stat, p = friedmanchisquare(*[pivot[c].values for c in pivot.columns])
    friedman_results.append({
        "metric": metric, "statistic": round(stat, 4), "p_value": round(p, 4),
        "n_graphs": pivot.shape[0], "n_algorithms": pivot.shape[1],
        "note": "significant @ alpha=0.05" if p < 0.05 else "not significant",
    })

friedman_df = pd.DataFrame(friedman_results)
fr_path = config.CLUSTERING_DIR / "friedman_results.csv"
friedman_df.to_csv(fr_path, index=False)
utils.log(f"\nFriedman test results saved: {fr_path}")
utils.log(friedman_df.to_string(index=False))


# ── Nemenyi post-hoc for the strongest significant metric ─────────────────────
significant = friedman_df[friedman_df["p_value"] < 0.05]
if len(significant):
    target_metric = significant.iloc[0]["metric"]
    pivot = best_cells[best_cells["algorithm"].isin(graph_algos)].pivot_table(
        index="graph", columns="algorithm", values=target_metric
    ).dropna()
    nemenyi = sp.posthoc_nemenyi_friedman(pivot.values)
    nemenyi.index = pivot.columns
    nemenyi.columns = pivot.columns
    nemenyi_path = config.CLUSTERING_DIR / f"nemenyi_{target_metric}.csv"
    nemenyi.to_csv(nemenyi_path)
    utils.log(f"\nNemenyi post-hoc on {target_metric} saved: {nemenyi_path}")
else:
    utils.log("\nNo metric reached Friedman significance; skipping Nemenyi")


# ── Figure 11: critical difference equivalent (boxplots of bootstrap ARIs) ────
stab_path = config.CLUSTERING_DIR / "bootstrap_stability.csv"
if stab_path.exists():
    stab = pd.read_csv(stab_path)
    fig, ax = plt.subplots(figsize=(8, 5))
    stab_valid = stab.dropna(subset=["mean_ari"])
    if len(stab_valid):
        x = np.arange(len(stab_valid))
        ax.errorbar(x, stab_valid["mean_ari"],
                    yerr=[stab_valid["mean_ari"] - stab_valid["ari_lo"],
                          stab_valid["ari_hi"] - stab_valid["mean_ari"]],
                    fmt="o", capsize=5, color="steelblue")
        ax.set_xticks(x)
        ax.set_xticklabels(stab_valid["algorithm"], rotation=20)
        ax.set_ylabel("Bootstrap ARI vs. full clustering")
        ax.set_ylim(0, 1)
        ax.axhline(0.8, color="green", linestyle="--", linewidth=1, label="ARI=0.8 (good stability)")
        ax.set_title(f"Bootstrap stability ({config.BOOTSTRAP_N_ITERATIONS} iterations, "
                     f"{int(config.BOOTSTRAP_SUBSAMPLE_FRAC*100)}% subsample)")
        ax.legend()
        ax.grid(alpha=0.3)
    plt.tight_layout()
    fig_path = config.FIGURE_DIR / "11_critical_difference.png"
    fig.savefig(fig_path, dpi=140)
    plt.close(fig)
    utils.log(f"Saved: {fig_path}")


# ── Figure 12: metric comparison heatmap (algorithm × metric × graph) ─────────
fig, axes = plt.subplots(2, 3, figsize=(16, 9))
metric_list = ["silhouette", "davies_bouldin", "bb_join_ratio",
               "detection_rate", "single_cluster_rate", "n_clusters"]
metric_list = [m for m in metric_list if m in best_cells.columns]

for ax, metric in zip(axes.ravel(), metric_list):
    pivot = best_cells.pivot_table(index="algorithm", columns="graph", values=metric)
    im = ax.imshow(pivot.values, cmap="viridis", aspect="auto")
    ax.set_xticks(range(pivot.shape[1]))
    ax.set_xticklabels(pivot.columns, rotation=30, fontsize=8)
    ax.set_yticks(range(pivot.shape[0]))
    ax.set_yticklabels(pivot.index, fontsize=8)
    ax.set_title(metric, fontsize=10)
    plt.colorbar(im, ax=ax)
    for (i, j), v in np.ndenumerate(pivot.values):
        if not np.isnan(v):
            ax.text(j, i, f"{v:.2f}" if isinstance(v, float) else str(v),
                    ha="center", va="center", fontsize=7,
                    color="white" if v < pivot.values[~np.isnan(pivot.values)].mean() else "black")

plt.tight_layout()
fig_path = config.FIGURE_DIR / "12_metric_comparison.png"
fig.savefig(fig_path, dpi=140)
plt.close(fig)
utils.log(f"Saved: {fig_path}")


# ── Regenerate clusters.geojson from the overall winner ──────────────────────
utils.log("\n=== Final winner ===")
winner = ranking.iloc[0]
utils.log(f"Algorithm:  {winner['algorithm']}")
utils.log(f"Graph:      {winner['graph']}")
utils.log(f"Params:     {winner['params']}")
utils.log(f"Composite:  {winner['composite']:.3f}")
utils.log(f"Detection:  {winner['detection_rate']}%, single-cluster: {winner['single_cluster_rate']}%")
silh_lo = winner.get("silhouette_lo")
silh_hi = winner.get("silhouette_hi")
ci_str  = (f" [{silh_lo:.3f}, {silh_hi:.3f}]"
           if silh_lo is not None and not pd.isna(silh_lo) else "")
utils.log(f"Silhouette: {winner['silhouette']:.3f}{ci_str}, DB: {winner['davies_bouldin']:.2f}")

labels = np.load(config.GRID_DIR / f"{winner['run_id']}.npy")
utils.log(f"Labels: {len(labels)} polygons, n_clusters: {int(winner['n_clusters'])}")

# Dissolve + export — reuse utils
gdf = utils.load_filtered_nfi(verbose=False)
gdf["cluster_label"] = labels
dissolved = utils.dissolve_clusters(gdf, label_col="cluster_label")
size_mb = utils.export_clusters_geojson(dissolved, config.CLUSTERS_GEOJSON)
utils.log(f"\nNew clusters.geojson: {config.CLUSTERS_GEOJSON} ({size_mb:.2f} MB)")

# Save winner metadata
winner_meta = {
    "winner": winner.to_dict(),
    "all_best_per_algorithm": ranking.to_dict(orient="records"),
    "friedman": friedman_df.to_dict(orient="records"),
    "output_geojson": str(config.CLUSTERS_GEOJSON),
    "output_size_mb": round(size_mb, 3),
}
winner_path = config.CLUSTERING_DIR / "final_winner.json"
with open(winner_path, "w") as f:
    json.dump(winner_meta, f, indent=2, default=str)
utils.log(f"Saved: {winner_path}")

utils.log("\n=== Phase 0d-E done ===")
