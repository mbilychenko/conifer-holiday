"""
Phase P2: Composite-score weight sensitivity analysis.

Repeats the winner-selection step from 08_metrics.py / 09_statistical_comparison.py
across four composite-weight schemes to show that the Louvain winner is not an
artefact of the chosen weights.

Weight schemes
--------------
default       : 0.30 silhouette + 0.20 (1/1+DB) + 0.30 detection + 0.20 single_cluster
equal         : 0.25 × 4
entity_only   : 0.00 + 0.00 + 0.60 detection + 0.40 single_cluster
internal_only : 0.50 silhouette + 0.50 (1/1+DB) + 0.00 + 0.00

Outputs
-------
data/output/clustering/weight_sensitivity.csv
  One row per (scheme × algorithm) with the best run under that scheme.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config
import utils


WEIGHT_SCHEMES: dict[str, dict[str, float]] = {
    "default": {
        "silhouette_norm":     0.30,
        "davies_bouldin_inv":  0.20,
        "detection_rate":      0.30,
        "single_cluster_rate": 0.20,
    },
    "equal": {
        "silhouette_norm":     0.25,
        "davies_bouldin_inv":  0.25,
        "detection_rate":      0.25,
        "single_cluster_rate": 0.25,
    },
    "entity_only": {
        "silhouette_norm":     0.00,
        "davies_bouldin_inv":  0.00,
        "detection_rate":      0.60,
        "single_cluster_rate": 0.40,
    },
    "internal_only": {
        "silhouette_norm":     0.50,
        "davies_bouldin_inv":  0.50,
        "detection_rate":      0.00,
        "single_cluster_rate": 0.00,
    },
}


def composite_score(row: pd.Series, weights: dict[str, float]) -> float:
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
    silh_n = max(float(silh), 0.0)  # clip negative to 0; matches 08_metrics formula
    db_inv = 1.0 / (1.0 + db)
    return (weights["silhouette_norm"]     * silh_n +
            weights["davies_bouldin_inv"]  * db_inv +
            weights["detection_rate"]      * (det / 100) +
            weights["single_cluster_rate"] * (scr / 100))


def main() -> None:
    utils.log("Loading grid_metrics.csv...")
    df = pd.read_csv(config.CLUSTERING_DIR / "grid_metrics.csv")
    grid_index = pd.read_csv(config.CLUSTERING_DIR / "grid_index.csv")
    df = df.merge(grid_index[["run_id", "params"]], on="run_id", how="left")
    utils.log(f"  {len(df)} runs loaded")

    output_rows: list[dict] = []

    for scheme_name, weights in WEIGHT_SCHEMES.items():
        df[f"_score"] = df.apply(composite_score, weights=weights, axis=1)
        eligible = df[df["_score"] > -np.inf].copy()

        # Best run per algorithm (across all graph variants)
        best_per_algo = (
            eligible.sort_values("_score", ascending=False)
                    .groupby("algorithm")
                    .head(1)
                    .reset_index(drop=True)
        )

        for _, row in best_per_algo.iterrows():
            output_rows.append({
                "scheme":              scheme_name,
                "algorithm":           row["algorithm"],
                "graph":               row.get("graph", "none"),
                "run_id":              row["run_id"],
                "params":              row.get("params", ""),
                "n_clusters":          int(row["n_clusters"]),
                "composite":           round(row["_score"], 4),
                "silhouette":          round(row["silhouette"], 4) if not pd.isna(row["silhouette"]) else None,
                "davies_bouldin":      round(row["davies_bouldin"], 4) if not pd.isna(row["davies_bouldin"]) else None,
                "detection_rate":      round(row["detection_rate"], 1) if not pd.isna(row.get("detection_rate")) else None,
                "single_cluster_rate": round(row["single_cluster_rate"], 1) if not pd.isna(row.get("single_cluster_rate")) else None,
            })

    out_df = pd.DataFrame(output_rows)
    out_path = config.CLUSTERING_DIR / "weight_sensitivity.csv"
    out_df.to_csv(out_path, index=False)
    utils.log(f"\nSaved: {out_path}")

    # Summary table: overall winner per scheme
    utils.log("\n--- Overall winner per weight scheme ---")
    winners = (
        out_df.sort_values("composite", ascending=False)
              .groupby("scheme")
              .head(1)
              .reset_index(drop=True)
    )
    # Print in scheme order
    for scheme_name in WEIGHT_SCHEMES:
        row = winners[winners["scheme"] == scheme_name].iloc[0]
        utils.log(
            f"  {scheme_name:<14}: {row['algorithm']:<14} "
            f"graph={row['graph']:<12}  composite={row['composite']:.3f}  "
            f"clusters={row['n_clusters']}  det={row['detection_rate']}%"
        )

    # Pivot: which algorithm wins per scheme across the four weight variants
    utils.log("\n--- Rank 1 algorithm per scheme (robustness check) ---")
    pivot = out_df.pivot_table(
        index="algorithm", columns="scheme", values="composite", aggfunc="max"
    ).round(3)
    utils.log(pivot.to_string())


if __name__ == "__main__":
    main()
