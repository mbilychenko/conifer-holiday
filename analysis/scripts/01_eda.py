"""
NFI Woodland GB 2023 — Exploratory Data Analysis
Source: NFI Woodland GB 2023, Forestry Commission via ArcGIS Hub
Accessed: 2026-05-23
Licence: Open Government Licence v3.0
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")  # non-interactive backend — saves to file
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
NFI_FILE     = PROJECT_ROOT / "data" / "raw" / "National_Forest_Inventory_GB_2023.shp"
OUTPUT_DIR   = PROJECT_ROOT / "data" / "output" / "eda"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FIGURES_DIR  = OUTPUT_DIR / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

# ── Config ─────────────────────────────────────────────────────────────────────
TYPE_FIELD    = "IFT_IOA"
CONIFER_TYPES = ["Conifer", "Mixed mainly conifer"]
AREA_MIN_HA   = 10  # minimum patch size — small patches aren't holiday destinations


def log(msg):
    print(msg, flush=True)


# ── 1. Load ────────────────────────────────────────────────────────────────────
log("Loading NFI shapefile...")
gdf = gpd.read_file(NFI_FILE)
log(f"Loaded {len(gdf):,} polygons | CRS: {gdf.crs}")

assert gdf.crs.to_epsg() == 27700, f"Expected EPSG:27700, got {gdf.crs}"
log("CRS check passed: EPSG:27700 (metres)")


# ── 2. Basic info ──────────────────────────────────────────────────────────────
log("\n--- Columns ---")
log(str(list(gdf.columns)))

log("\n--- dtypes ---")
log(str(gdf.dtypes))

log("\n--- First 3 rows ---")
log(str(gdf.drop(columns="geometry").head(3)))


# ── 3. Null / validity ─────────────────────────────────────────────────────────
null_counts = gdf.isnull().sum()
null_nonzero = null_counts[null_counts > 0]
geom_null    = int(gdf.geometry.isnull().sum())
geom_invalid = int((~gdf.geometry.is_valid).sum())

log(f"\n--- Nulls ---")
log(str(null_nonzero) if len(null_nonzero) else "No nulls in any column")
log(f"Geometry null: {geom_null} | Geometry invalid: {geom_invalid}")


# ── 4. IFT_IOA distribution ────────────────────────────────────────────────────
if TYPE_FIELD not in gdf.columns:
    log(f"ERROR: '{TYPE_FIELD}' not found. Columns: {list(gdf.columns)}")
    sys.exit(1)

type_counts = gdf[TYPE_FIELD].value_counts(dropna=False)
log(f"\n--- IFT_IOA value counts (total {len(gdf):,}) ---")
log(str(type_counts))

fig, ax = plt.subplots(figsize=(13, 5))
type_counts.plot(kind="bar", ax=ax, color="forestgreen")
ax.set_title("NFI polygon count by IFT_IOA type")
ax.set_xlabel("IFT_IOA")
ax.set_ylabel("Polygon count")
ax.tick_params(axis="x", rotation=45)
plt.tight_layout()
fig.savefig(FIGURES_DIR / "01_ift_ioa_distribution.png", dpi=150)
plt.close(fig)
log("Saved: 01_ift_ioa_distribution.png")


# ── 5. Area statistics ─────────────────────────────────────────────────────────
gdf["area_ha"] = gdf.geometry.area / 10_000  # m² → hectares

area_stats = gdf["area_ha"].describe()
log(f"\n--- Area stats (all polygons, ha) ---")
log(str(area_stats.round(3)))

above_10ha = int((gdf["area_ha"] >= AREA_MIN_HA).sum())
below_10ha = int((gdf["area_ha"] < AREA_MIN_HA).sum())
log(f"\nPolygons >= {AREA_MIN_HA}ha: {above_10ha:,} ({above_10ha/len(gdf):.1%})")
log(f"Polygons <  {AREA_MIN_HA}ha: {below_10ha:,} ({below_10ha/len(gdf):.1%})")

fig, axes = plt.subplots(1, 2, figsize=(14, 4))
gdf["area_ha"].clip(upper=gdf["area_ha"].quantile(0.99)).hist(
    bins=60, ax=axes[0], color="forestgreen", edgecolor="white"
)
axes[0].set_title("Polygon area (clipped at 99th pct)")
axes[0].set_xlabel("Area (ha)")
axes[0].set_ylabel("Count")

gdf["area_ha"].clip(upper=50).hist(bins=50, ax=axes[1], color="steelblue", edgecolor="white")
axes[1].axvline(AREA_MIN_HA, color="red", linestyle="--", label=f"{AREA_MIN_HA}ha threshold")
axes[1].set_title("Polygon area 0–50ha")
axes[1].set_xlabel("Area (ha)")
axes[1].legend()
plt.tight_layout()
fig.savefig(FIGURES_DIR / "02_area_distribution.png", dpi=150)
plt.close(fig)
log("Saved: 02_area_distribution.png")


# ── 6. Apply conifer + area filter ────────────────────────────────────────────
conifer = gdf[
    gdf[TYPE_FIELD].isin(CONIFER_TYPES) &
    (gdf["area_ha"] >= AREA_MIN_HA)
].copy()

log(f"\n--- Filter results ---")
log(f"All NFI polygons:              {len(gdf):>8,}")
log(f"Conifer types only:            {len(gdf[gdf[TYPE_FIELD].isin(CONIFER_TYPES)]):>8,}")
log(f"Conifer + >= {AREA_MIN_HA}ha:           {len(conifer):>8,}")
log(f"Reduction:                     {1 - len(conifer)/len(gdf):.1%} of polygons removed")
log(f"Total conifer area:            {conifer['area_ha'].sum():>10,.0f} ha")
log(f"Median conifer patch:          {conifer['area_ha'].median():>10.1f} ha")
log(f"Largest conifer patch:         {conifer['area_ha'].max():>10.0f} ha")
log(f"\nConifer type breakdown:")
log(str(conifer[TYPE_FIELD].value_counts()))


# ── 7. Geographic distribution ─────────────────────────────────────────────────
bounds = conifer.total_bounds
log(f"\n--- Bounding box (EPSG:27700, metres) ---")
log(f"Easting:  {bounds[0]:,.0f} – {bounds[2]:,.0f}")
log(f"Northing: {bounds[1]:,.0f} – {bounds[3]:,.0f}")

cx = conifer.geometry.centroid.x.values
cy = conifer.geometry.centroid.y.values
ca = conifer["area_ha"].values

fig, ax = plt.subplots(figsize=(7, 12))
scatter = ax.scatter(
    cx, cy,
    c=ca,
    cmap="YlGn",
    s=3,
    alpha=0.7,
    norm=mcolors.LogNorm(vmin=ca.min(), vmax=np.percentile(ca, 99))
)
plt.colorbar(scatter, ax=ax, label="Area (ha, log scale)")
ax.set_title(f"Conifer NFI centroids (n={len(conifer):,})")
ax.set_xlabel("Easting (m)")
ax.set_ylabel("Northing (m)")
ax.set_aspect("equal")
plt.tight_layout()
fig.savefig(FIGURES_DIR / "03_geographic_distribution.png", dpi=150)
plt.close(fig)
log("Saved: 03_geographic_distribution.png")


# ── 8. File size estimate ─────────────────────────────────────────────────────
log("\n--- File size estimate ---")
sample = conifer.sample(frac=0.01, random_state=42)
sample_wgs = sample.to_crs(4326)
with tempfile.NamedTemporaryFile(suffix=".geojson", delete=False) as f:
    tmp_path = f.name
sample_wgs.to_file(tmp_path, driver="GeoJSON")
sample_mb = os.path.getsize(tmp_path) / 1e6
os.unlink(tmp_path)

estimated_mb = sample_mb * 100
log(f"1% sample ({len(sample)} polygons): {sample_mb:.2f} MB")
log(f"Estimated full filtered GeoJSON: ~{estimated_mb:.0f} MB (raw, pre-cluster dissolve)")
log("Post-dissolve cluster output (~100–300 polygons) expected: <5 MB")


# ── 9. Save summary JSON for downstream analysis ──────────────────────────────
summary = {
    "source": {
        "file": "National_Forest_Inventory_GB_2023.shp",
        "release": "2023",
        "provider": "Forestry Commission via ArcGIS Hub",
        "access_date": "2026-05-23",
        "licence": "Open Government Licence v3.0"
    },
    "raw": {
        "total_polygons": len(gdf),
        "columns": list(gdf.columns),
        "crs": str(gdf.crs),
        "geometry_nulls": geom_null,
        "geometry_invalid": geom_invalid,
        "null_columns": null_nonzero.to_dict(),
        "ift_ioa_counts": type_counts.to_dict(),
        "area_ha_stats": area_stats.round(3).to_dict()
    },
    "filtered": {
        "conifer_types": CONIFER_TYPES,
        "area_min_ha": AREA_MIN_HA,
        "polygon_count": len(conifer),
        "reduction_pct": round((1 - len(conifer) / len(gdf)) * 100, 1),
        "total_area_ha": round(float(conifer["area_ha"].sum()), 0),
        "median_area_ha": round(float(conifer["area_ha"].median()), 1),
        "max_area_ha": round(float(conifer["area_ha"].max()), 0),
        "type_breakdown": conifer[TYPE_FIELD].value_counts().to_dict(),
        "bounding_box_27700": {
            "min_easting": round(float(bounds[0])),
            "min_northing": round(float(bounds[1])),
            "max_easting": round(float(bounds[2])),
            "max_northing": round(float(bounds[3]))
        }
    },
    "size_estimate": {
        "filtered_raw_geojson_mb": round(estimated_mb, 0),
        "cluster_dissolved_geojson_mb_estimate": "<5"
    }
}

summary_path = OUTPUT_DIR / "eda_summary.json"
with open(summary_path, "w") as f:
    json.dump(summary, f, indent=2)
log(f"\nSaved summary: {summary_path}")

log("\n=== EDA COMPLETE ===")
log(f"Figures: {FIGURES_DIR}")
log(f"Summary: {summary_path}")
log("\nNext: set DBSCAN success criteria, then run 02_clustering.py")
