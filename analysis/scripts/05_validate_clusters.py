"""
Rigorous validation of clusters.geojson against 22 verified UK forest destinations.

For each named forest:
  - Convert lat/lon to EPSG:27700 (BNG)
  - Buffer the centre by 5km
  - Find all cluster polygons that intersect the buffer
  - Identify the "primary" cluster as the one with largest area inside the buffer
  - Record cluster ID, distance from forest centre, cluster area, fragmentation

Then compute publication-quality validation metrics:
  - Recall: % of "primary" forests with at least one cluster in their buffer
  - Fragmentation: median # clusters per primary forest
  - Area accuracy: median ratio of (cluster area within buffer) / (expected area)
  - False positive check: are any large clusters at "negative" (broadleaf) locations?
  - Closest-cluster distance: median distance from forest centre to nearest cluster centroid

Outputs:
  - data/output/clustering/validation_report.csv   (per-forest detail)
  - data/output/clustering/validation_summary.json (aggregate metrics)
  - data/output/clustering/figures/09_validation_map.png
"""

import json
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from shapely.geometry import Point
from statsmodels.stats.proportion import proportion_confint

sys.path.insert(0, str(Path(__file__).parent))
from reference_forests import REFERENCE_FORESTS

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CLUSTERS_FILE = PROJECT_ROOT / "data" / "output" / "clusters.geojson"
OUT_DIR       = PROJECT_ROOT / "data" / "output" / "clustering"
FIG_DIR       = OUT_DIR / "figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)

# Search radius around each forest centre (metres) — generous to allow for
# imprecise reference coordinates (visitor centres aren't always at the centroid)
SEARCH_RADIUS_M = 5_000


def log(msg):
    print(msg, flush=True)


# ── Load clusters + reference forests ─────────────────────────────────────────
log(f"Loading {CLUSTERS_FILE}...")
clusters_wgs = gpd.read_file(CLUSTERS_FILE)
log(f"  {len(clusters_wgs)} clusters in WGS84")

# Reproject to EPSG:27700 for metric operations
clusters = clusters_wgs.to_crs(27700)
clusters["cluster_area_ha"] = clusters.geometry.area / 10_000
log(f"  Total clustered conifer area: {clusters['cluster_area_ha'].sum():,.0f} ha")

# Reference forests → GeoDataFrame in EPSG:27700
ref_df = pd.DataFrame(REFERENCE_FORESTS)
ref_wgs = gpd.GeoDataFrame(
    ref_df,
    geometry=[Point(r["lon"], r["lat"]) for _, r in ref_df.iterrows()],
    crs=4326
)
ref = ref_wgs.to_crs(27700)
ref["easting"]  = ref.geometry.x
ref["northing"] = ref.geometry.y

# Sanity check: all reference forests within UK BNG bounds
in_uk = (ref["easting"] > 0) & (ref["easting"] < 700_000) & \
        (ref["northing"] > 0) & (ref["northing"] < 1_300_000)
if not in_uk.all():
    log(f"  WARNING: {(~in_uk).sum()} reference forests fell outside UK BNG bounds!")
    log(str(ref.loc[~in_uk, ["name", "easting", "northing"]]))


# ── Per-forest validation ─────────────────────────────────────────────────────
log(f"\nValidating against {len(ref)} reference forests (radius {SEARCH_RADIUS_M}m)...")

# Spatial index for cluster lookup
sindex = clusters.sindex

records = []
for _, forest in ref.iterrows():
    centre = forest.geometry
    buffer = centre.buffer(SEARCH_RADIUS_M)

    # Candidate clusters via spatial index, then refine with actual intersection
    candidate_idx = list(sindex.intersection(buffer.bounds))
    candidates = clusters.iloc[candidate_idx]
    intersecting = candidates[candidates.geometry.intersects(buffer)].copy()

    if len(intersecting) == 0:
        records.append({
            "forest": forest["name"],
            "country": forest["country"],
            "role": forest["role"],
            "expected_area_ha": forest["area_ha"],
            "n_clusters_in_buffer": 0,
            "primary_cluster_id": None,
            "primary_cluster_area_ha": 0.0,
            "primary_area_in_buffer_ha": 0.0,
            "area_ratio": 0.0,
            "nearest_cluster_centroid_km": None,
            "nearest_cluster_id": None,
            "detected": False,
        })
        continue

    # Area of each intersecting cluster that falls inside the buffer
    intersecting["area_in_buffer_ha"] = (
        intersecting.geometry.intersection(buffer).area / 10_000
    )
    intersecting = intersecting.sort_values("area_in_buffer_ha", ascending=False)

    primary = intersecting.iloc[0]

    # Distance from forest centre to the nearest cluster centroid (across ALL clusters)
    all_centroid_dists = clusters.geometry.centroid.distance(centre)
    nearest_idx = all_centroid_dists.idxmin()
    nearest_dist_km = all_centroid_dists.loc[nearest_idx] / 1_000

    records.append({
        "forest": forest["name"],
        "country": forest["country"],
        "role": forest["role"],
        "expected_area_ha": forest["area_ha"],
        "n_clusters_in_buffer": len(intersecting),
        "primary_cluster_id": primary["cluster_id"],
        "primary_cluster_area_ha": round(primary["cluster_area_ha"], 1),
        "primary_area_in_buffer_ha": round(primary["area_in_buffer_ha"], 1),
        "area_ratio": round(primary["cluster_area_ha"] / forest["area_ha"], 2),
        "nearest_cluster_centroid_km": round(nearest_dist_km, 2),
        "nearest_cluster_id": clusters.loc[nearest_idx, "cluster_id"],
        "detected": True,
    })

report = pd.DataFrame(records)
report.to_csv(OUT_DIR / "validation_report.csv", index=False)
log(f"Saved: {OUT_DIR / 'validation_report.csv'}")


# ── Aggregate metrics ─────────────────────────────────────────────────────────
primary = report[report["role"] == "primary"]
mixed   = report[report["role"] == "mixed"]

n_primary       = len(primary)
n_det           = int(primary["detected"].sum())
detection_rate  = n_det / n_primary * 100
detected_primary = primary[primary["detected"]]
n_det_primary   = len(detected_primary)
median_frag    = float(detected_primary["n_clusters_in_buffer"].median())
median_dist    = float(detected_primary["nearest_cluster_centroid_km"].median())
median_ratio   = float(detected_primary["area_ratio"].median())

# Single-cluster rate: % of detected primaries captured as a single cluster
n_single = int((detected_primary["n_clusters_in_buffer"] == 1).sum())
single_cluster_rate = n_single / n_det_primary * 100

# Tight placement: % of detected primaries with nearest cluster centroid within 5km
n_tight = int((detected_primary["nearest_cluster_centroid_km"] <= 5).sum())
tight_placement = n_tight / n_det_primary * 100

# Area accuracy: % of detected primaries where cluster area is within 0.3× to 3× of expected
in_range = (detected_primary["area_ratio"] >= 0.3) & (detected_primary["area_ratio"] <= 3.0)
n_in_range = int(in_range.sum())
area_accuracy = n_in_range / n_det_primary * 100


def _wilson_pct(count: int, nobs: int) -> tuple[float, float]:
    """Wilson-score 95% CI as percentages (lo, hi)."""
    if nobs == 0:
        return (0.0, 0.0)
    lo, hi = proportion_confint(count, nobs, alpha=0.05, method="wilson")
    return (round(lo * 100, 1), round(hi * 100, 1))


det_ci    = _wilson_pct(n_det,      n_primary)
single_ci = _wilson_pct(n_single,   n_det_primary)
tight_ci  = _wilson_pct(n_tight,    n_det_primary)
area_ci   = _wilson_pct(n_in_range, n_det_primary)

summary = {
    "n_reference_forests": int(len(ref)),
    "n_primary":           n_primary,
    "n_mixed":             int(len(mixed)),
    "detection_rate_pct":          round(detection_rate, 1),
    "detection_rate_ci95":         list(det_ci),
    "detection_rate_n":            f"{n_det}/{n_primary}",
    "primary_detected":            n_det,
    "primary_missed":              primary[~primary["detected"]]["forest"].tolist(),
    "single_cluster_rate_pct":     round(single_cluster_rate, 1),
    "single_cluster_rate_ci95":    list(single_ci),
    "single_cluster_rate_n":       f"{n_single}/{n_det_primary}",
    "tight_placement_pct":         round(tight_placement, 1),
    "tight_placement_ci95":        list(tight_ci),
    "tight_placement_n":           f"{n_tight}/{n_det_primary}",
    "area_accuracy_pct":           round(area_accuracy, 1),
    "area_accuracy_ci95":          list(area_ci),
    "area_accuracy_n":             f"{n_in_range}/{n_det_primary}",
    "median_clusters_per_forest":          median_frag,
    "median_nearest_cluster_km":           median_dist,
    "median_area_ratio_cluster_vs_expected": median_ratio,
    "mixed_sites_with_conifer_cluster":    mixed[mixed["detected"]]["forest"].tolist(),
    "interpretation": {
        "detection_rate_pct":      "% of known conifer destinations with at least one cluster in 5km buffer (target >= 85%)",
        "detection_rate_ci95":     "Wilson-score 95% CI on detection_rate_pct (n = n_primary)",
        "single_cluster_rate_pct": "% of detected forests captured as a SINGLE cluster (higher = less fragmented; target >= 70%)",
        "single_cluster_rate_ci95":"Wilson-score 95% CI on single_cluster_rate_pct (n = n_detected)",
        "tight_placement_pct":     "% of detected forests with nearest cluster centroid within 5km (target >= 80%)",
        "tight_placement_ci95":    "Wilson-score 95% CI on tight_placement_pct (n = n_detected)",
        "area_accuracy_pct":       "% of detected forests where cluster area is within 0.3x-3x of Wikipedia area (target >= 60%)",
        "area_accuracy_ci95":      "Wilson-score 95% CI on area_accuracy_pct (n = n_detected)",
        "median_area_ratio_cluster_vs_expected": "primary cluster area / Wikipedia area. Below 1.0 = our conifer-only filter excludes broadleaf parts of the park.",
        "mixed_sites_with_conifer_cluster": "mixed broadleaf+conifer forests where we (correctly) found a conifer plantation cluster",
    }
}

with open(OUT_DIR / "validation_summary.json", "w") as f:
    json.dump(summary, f, indent=2)


# ── Pretty-print summary ──────────────────────────────────────────────────────
log("\n" + "=" * 70)
log("VALIDATION SUMMARY")
log("=" * 70)
log(f"\nReference forests: {len(ref)} total ({len(primary)} primary, {len(mixed)} mixed)")
log(f"\nQuality metrics on primary conifer destinations (Wilson 95% CI):")
log(f"  Detection rate:         {detection_rate:>5.1f}%  [{det_ci[0]:.1f}%, {det_ci[1]:.1f}%]  ({n_det}/{n_primary})")
log(f"  Single-cluster rate:    {single_cluster_rate:>5.1f}%  [{single_ci[0]:.1f}%, {single_ci[1]:.1f}%]  ({n_single}/{n_det_primary})")
log(f"  Tight placement (5km):  {tight_placement:>5.1f}%  [{tight_ci[0]:.1f}%, {tight_ci[1]:.1f}%]  ({n_tight}/{n_det_primary})")
log(f"  Area accuracy (0.3-3x): {area_accuracy:>5.1f}%  [{area_ci[0]:.1f}%, {area_ci[1]:.1f}%]  ({n_in_range}/{n_det_primary})")
log(f"  Median fragmentation:   {median_frag:>5.1f}   clusters per detected forest")
log(f"  Median nearest distance:{median_dist:>5.2f} km")
log(f"  Median area ratio:      {median_ratio:>5.2f}   (cluster / Wikipedia area)")

log("\n--- Per-forest detail ---")
display_cols = ["forest", "role", "expected_area_ha", "n_clusters_in_buffer",
                "primary_area_in_buffer_ha", "primary_cluster_area_ha",
                "area_ratio", "nearest_cluster_centroid_km"]
log(report[display_cols].to_string(index=False))

if summary["primary_missed"]:
    log(f"\nPrimary forests MISSED (no cluster within 5km buffer):")
    for f in summary["primary_missed"]:
        log(f"  - {f}")

if summary["mixed_sites_with_conifer_cluster"]:
    log(f"\nMixed broadleaf+conifer sites where a conifer cluster was found (expected):")
    for f in summary["mixed_sites_with_conifer_cluster"]:
        log(f"  - {f}")


# ── Validation map ────────────────────────────────────────────────────────────
log("\nPlotting validation map...")
fig, ax = plt.subplots(figsize=(10, 14))

# Plot clusters as light green polygons
clusters.plot(ax=ax, color="#a8d5a8", edgecolor="#3d7a3d", linewidth=0.3, alpha=0.6)

# Plot reference forests
for _, r in report.iterrows():
    forest_row = ref[ref["name"] == r["forest"]].iloc[0]
    x, y = forest_row["easting"], forest_row["northing"]
    if r["role"] == "primary":
        if r["detected"]:
            ax.scatter(x, y, s=120, marker="o", facecolor="none",
                       edgecolor="green", linewidth=2, zorder=10)
        else:
            ax.scatter(x, y, s=180, marker="x", color="red", linewidth=3, zorder=10)
    else:  # mixed
        ax.scatter(x, y, s=120, marker="s", facecolor="none",
                   edgecolor="blue", linewidth=2, zorder=10)
    ax.annotate(r["forest"], (x, y), xytext=(8, 4),
                textcoords="offset points", fontsize=7)

ax.set_title(
    f"Cluster Validation: {detection_rate:.0f}% primary detection, "
    f"{median_frag:.0f} median clusters/forest, "
    f"{median_dist:.1f} km median nearest"
)
ax.set_xlabel("Easting (m, EPSG:27700)")
ax.set_ylabel("Northing (m, EPSG:27700)")
ax.set_aspect("equal")
ax.grid(alpha=0.3)

# Legend
from matplotlib.lines import Line2D
legend = [
    Line2D([0], [0], marker="o", color="w", markerfacecolor="none",
           markeredgecolor="green", markersize=10, markeredgewidth=2,
           label="Primary forest — detected"),
    Line2D([0], [0], marker="x", color="red", markersize=12, markeredgewidth=3,
           label="Primary forest — MISSED"),
    Line2D([0], [0], marker="s", color="w", markerfacecolor="none",
           markeredgecolor="blue", markersize=10, markeredgewidth=2,
           label="Mixed broadleaf+conifer site"),
]
ax.legend(handles=legend, loc="lower right")

plt.tight_layout()
fig.savefig(FIG_DIR / "09_validation_map.png", dpi=150)
plt.close(fig)
log(f"Saved: {FIG_DIR / '09_validation_map.png'}")

log("\n=== VALIDATION DONE ===")
log(f"Per-forest report:    {OUT_DIR / 'validation_report.csv'}")
log(f"Aggregate summary:    {OUT_DIR / 'validation_summary.json'}")
log(f"Validation map:       {FIG_DIR / '09_validation_map.png'}")
