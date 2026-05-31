"""
Centralized configuration for the conifer-forest clustering pipeline.

All constants used across analysis scripts (paths, CRS codes, filter thresholds,
clustering grids, evaluation thresholds, simplification tolerances) live here.

Scripts should import from this module rather than redefining constants — that way
changing a threshold updates every script consistently.
"""

from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_RAW     = PROJECT_ROOT / "data" / "raw"
DATA_OUT     = PROJECT_ROOT / "data" / "output"
NFI_FILE     = DATA_RAW / "National_Forest_Inventory_GB_2023.shp"

CLUSTERING_DIR = DATA_OUT / "clustering"
GRAPH_DIR      = DATA_OUT / "graphs"
GRID_DIR       = DATA_OUT / "grid"
FIGURE_DIR     = CLUSTERING_DIR / "figures"

# Ensure output directories exist whenever this module is imported
for _d in [CLUSTERING_DIR, GRAPH_DIR, GRID_DIR, FIGURE_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# Final web-app output
CLUSTERS_GEOJSON = DATA_OUT / "clusters.geojson"

# ── Coordinate reference systems ──────────────────────────────────────────────
CRS_OSGB36 = 27700   # British National Grid — metres (use for distance ops)
CRS_WGS84  = 4326    # Web standard — degrees (use for web display + Google APIs)

# ── NFI filter ────────────────────────────────────────────────────────────────
TYPE_FIELD    = "IFT_IOA"
CONIFER_TYPES = ["Conifer", "Mixed mainly conifer"]
AREA_MIN_HA   = 10  # smallest meaningful destination patch

# ── Source metadata (for citations + provenance) ───────────────────────────────
NFI_SOURCE = {
    "name":        "NFI Woodland GB",
    "release":     "2023",
    "provider":    "Forestry Commission via ArcGIS Hub",
    "url":         "https://data-forestry.opendata.arcgis.com",
    "access_date": "2026-05-23",
    "licence":     "Open Government Licence v3.0",
}

# ── Graph construction variants (Phase 0d-B) ──────────────────────────────────
GRAPH_VARIANTS = {
    "prox_2500m":  {"kind": "proximity", "radius_m": 2_500},
    "prox_5000m":  {"kind": "proximity", "radius_m": 5_000},
    "prox_10000m": {"kind": "proximity", "radius_m": 10_000},
    "knn_10":      {"kind": "knn",       "k": 10},
}

# ── Algorithm parameter grids (Phase 0d-C) ────────────────────────────────────
ALGORITHM_GRIDS = {
    "kmeans": {
        "needs_graph": False,
        "params": {"n_clusters": [100, 150, 200, 250, 300]},
    },
    "dbscan": {
        "needs_graph": False,
        "params": {"eps": [1500, 2500, 3500, 5000], "min_samples": [3, 5]},
    },
    "hdbscan": {
        "needs_graph": False,
        "params": {
            "min_cluster_size":          [5, 10, 15, 20],
            "min_samples":               [1, 3, 5],
            "cluster_selection_method":  ["eom"],
        },
    },
    "agglomerative": {
        "needs_graph": True,
        "params": {"n_clusters": [100, 150, 200, 250, 300]},
    },
    "skater": {
        "needs_graph": True,
        "params": {"n_clusters": [100, 150, 200, 250, 300]},
    },
    "maxp": {
        "needs_graph": True,
        "params": {"threshold_ha": [200, 500, 1000, 2000]},
    },
    "louvain": {
        "needs_graph": True,
        "params": {"resolution": [0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0]},
    },
    "spectral": {
        "needs_graph": True,
        "params": {"n_clusters": [100, 150, 200, 250, 300]},
    },
}

# ── Combinations to skip in the grid (runtime/memory constraints) ────────────
# Three documented scalability limitations:
#
# 1. Ward hierarchical clustering with connectivity is O(n²) — only feasible on
#    the most-constrained proximity graph (prox_2500m). Larger graphs add more
#    eligible neighbour merges and exceed the 600s per-run timeout.
#
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
SKIP_COMBINATIONS = {
    ("agglomerative", "prox_5000m"),
    ("agglomerative", "prox_10000m"),
    ("agglomerative", "knn_10"),
    # SKATER and Max-P — infeasible at n=13,434 (see notes above)
    ("skater",        "prox_2500m"),
    ("skater",        "prox_5000m"),
    ("skater",        "prox_10000m"),
    ("skater",        "knn_10"),
    ("maxp",          "prox_2500m"),
    ("maxp",          "prox_5000m"),
    ("maxp",          "prox_10000m"),
    ("maxp",          "knn_10"),
    # Spectral: prox_2500m has ~2700 components → trivial eigenvectors dominate;
    # prox_5000m has too many components for meaningful spectral analysis at k≤300.
    ("spectral",      "prox_2500m"),
    ("spectral",      "prox_5000m"),
}

# ── Acceptable cluster count range for the destination use case ───────────────
CLUSTER_COUNT_MIN = 80
CLUSTER_COUNT_MAX = 400

# ── Composite quality score weights (Phase 0d-D) ──────────────────────────────
COMPOSITE_WEIGHTS = {
    "silhouette_norm":     0.30,
    "davies_bouldin_inv":  0.20,
    "detection_rate":      0.30,
    "single_cluster_rate": 0.20,
}

# ── Bootstrap stability (Phase 0d-D) ──────────────────────────────────────────
BOOTSTRAP_N_ITERATIONS    = 50
BOOTSTRAP_SUBSAMPLE_FRAC  = 0.80
BOOTSTRAP_RANDOM_SEED     = 42

# ── Silhouette subsample (computational cost) ─────────────────────────────────
SILHOUETTE_SUBSAMPLE_SIZE = 5_000
SILHOUETTE_RANDOM_SEED    = 42

# ── Entity validation (reuse from 05_validate_clusters.py) ────────────────────
ENTITY_SEARCH_RADIUS_M = 5_000

# ── Geometry simplification for the final GeoJSON ─────────────────────────────
SIMPLIFY_TOLERANCE_DEG = 0.001  # ~100m at UK latitudes — fine for web display
SIMPLIFY_FALLBACK_DEG  = 0.005  # if first pass exceeds size threshold
SIMPLIFY_MAX_MB        = 15.0

# ── Per-algorithm safety timeouts (seconds) ───────────────────────────────────
ALGORITHM_TIMEOUT_S = {
    "kmeans":         60,
    "dbscan":         60,
    "hdbscan":        60,
    "agglomerative": 600,   # Ward at n=13k is slow; cap aggressively
    "skater":        600,
    "maxp":          600,
    "louvain":       180,
    "spectral":      600,
}

# ── Random seed for reproducibility ───────────────────────────────────────────
GLOBAL_SEED = 42
