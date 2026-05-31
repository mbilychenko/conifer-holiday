# Clustering Pipeline Outputs

This directory contains all artefacts produced by the publication-grade comparison
defined in Phase 0d of the master plan.

## Files

| File | Producer | Description |
|---|---|---|
| `graph_stats.csv` | `06_graph_construction.py` | Summary statistics for the 4 spatial graphs |
| `grid_index.csv` | `07_grid_search.py` | One row per algorithm × graph × parameter combination |
| `grid_metrics.csv` | `08_metrics.py` | Internal + spatial + entity metrics for every grid run |
| `bootstrap_stability.csv` | `08_metrics.py` | Bootstrap ARI per algorithm |
| `method_ranking.csv` | `09_statistical_comparison.py` | Best parameters per algorithm ranked by composite |
| `friedman_results.csv` | `09_statistical_comparison.py` | Friedman test across graph variants per metric |
| `final_winner.json` | `09_statistical_comparison.py` | Selected algorithm + parameters; metadata of the deployed `clusters.geojson` |
| `validation_report.csv` | `05_validate_clusters.py` | Per-forest entity validation detail (22 rows) |
| `validation_summary.json` | `05_validate_clusters.py` | Aggregate detection / accuracy metrics |

## Figures (under `figures/`)

| File | Producer | Description |
|---|---|---|
| `10_graph_comparison.png` | `06_graph_construction.py` | Edge-length, component size, degree distributions |
| `11_critical_difference.png` | `09_statistical_comparison.py` | Bootstrap ARI per algorithm |
| `12_metric_comparison.png` | `09_statistical_comparison.py` | Heatmaps of metrics per algorithm × graph |

## Raw label files

Individual cluster label arrays from the grid search are stored as `.npy` files
under `../grid/`, keyed by `run_id`. The master index `grid_index.csv` maps each
run_id to its algorithm, graph variant, parameters, and runtime.
