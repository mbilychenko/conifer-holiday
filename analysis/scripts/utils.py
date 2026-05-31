"""
Shared utilities for the conifer-forest clustering pipeline.

Each function extracted from a single-use call site in 01–05 and generalized so the
publication-grade comparison scripts (06–10) can compose them.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

import config


# ── Data loading ──────────────────────────────────────────────────────────────
def load_filtered_nfi(verbose: bool = True) -> gpd.GeoDataFrame:
    """Load NFI shapefile, filter to conifer + ≥10ha, repair geometry, return EPSG:27700.

    Reproduces the filter from 01–04 in one place. Adds an `area_ha` column.
    """
    if verbose:
        print(f"Loading {config.NFI_FILE.name}...", flush=True)
    gdf = gpd.read_file(config.NFI_FILE)
    assert gdf.crs.to_epsg() == config.CRS_OSGB36, \
        f"Expected EPSG:{config.CRS_OSGB36}, got {gdf.crs}"

    gdf["area_ha"] = gdf.geometry.area / 10_000

    filtered = gdf[
        gdf[config.TYPE_FIELD].isin(config.CONIFER_TYPES) &
        (gdf["area_ha"] >= config.AREA_MIN_HA)
    ].copy().reset_index(drop=True)

    filtered = repair_geometry(filtered)

    if verbose:
        print(f"  Filtered: {len(filtered):,} polygons", flush=True)
    return filtered


def repair_geometry(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Apply buffer(0) and assert validity. Mutates and returns the GeoDataFrame."""
    gdf = gdf.copy()
    gdf.geometry = gdf.geometry.buffer(0)
    assert gdf.geometry.is_valid.all(), \
        "Geometries still invalid after buffer(0) — investigate"
    return gdf


def centroids_array(gdf: gpd.GeoDataFrame) -> np.ndarray:
    """Return centroid coords as Nx2 float64 array in the input CRS units."""
    c = gdf.geometry.centroid
    return np.column_stack([c.x.values, c.y.values]).astype(np.float64)


# ── Clustering scoring (reused across scripts) ────────────────────────────────
def clusters_in_box(cx: np.ndarray, cy: np.ndarray, labels: np.ndarray,
                    box: tuple[float, float, float, float]) -> int:
    """Count distinct non-noise cluster labels whose centroids fall inside a box."""
    minx, miny, maxx, maxy = box
    mask = (cx >= minx) & (cx <= maxx) & (cy >= miny) & (cy <= maxy) & (labels != -1)
    if mask.sum() == 0:
        return 0
    return int(np.unique(labels[mask]).shape[0])


def cluster_size_stats(labels: np.ndarray) -> dict:
    """Return n_clusters, n_noise, noise_pct, max_pct, median_size."""
    n = len(labels)
    valid = labels[labels != -1]
    n_clusters = int(np.unique(valid).shape[0]) if valid.size else 0
    n_noise    = int((labels == -1).sum())
    noise_pct  = round(n_noise / n * 100, 3) if n else 0.0

    if n_clusters > 0:
        sizes = pd.Series(valid).value_counts()
        max_pct     = round(sizes.iloc[0] / n * 100, 3)
        median_size = round(float(sizes.median()), 1)
    else:
        max_pct, median_size = 0.0, 0.0

    return {
        "n_clusters":      n_clusters,
        "n_noise":         n_noise,
        "noise_pct":       noise_pct,
        "max_cluster_pct": max_pct,
        "median_cluster_size": median_size,
    }


# ── Dissolve + export (reused for final geojson) ──────────────────────────────
def dissolve_clusters(gdf: gpd.GeoDataFrame, label_col: str = "cluster_label",
                      type_field: str = None) -> gpd.GeoDataFrame:
    """Dissolve polygons by cluster label; aggregate area + dominant type.

    Returns a GeoDataFrame in the input CRS with columns:
    cluster_label, cluster_id, dominant_type, total_area_ha, polygon_count, geometry
    """
    type_field = type_field or config.TYPE_FIELD
    clustered = gdf[gdf[label_col] != -1].copy()

    dissolved = clustered.dissolve(
        by=label_col,
        aggfunc={type_field: lambda x: x.mode().iloc[0], "area_ha": "sum"}
    ).reset_index()

    counts = clustered.groupby(label_col).size().rename("polygon_count")
    dissolved = dissolved.join(counts, on=label_col)
    dissolved["cluster_id"]    = ["cluster_{:04d}".format(int(i)) for i in dissolved[label_col]]
    dissolved["dominant_type"] = dissolved[type_field]
    dissolved["total_area_ha"] = dissolved["area_ha"].round(1)

    return dissolved


def export_clusters_geojson(dissolved: gpd.GeoDataFrame, output_path: Path,
                            simplify_deg: float = None,
                            fallback_deg: float = None,
                            max_mb: float = None,
                            verbose: bool = True) -> float:
    """Reproject to WGS84, simplify, write GeoJSON. Returns final size in MB."""
    simplify_deg = simplify_deg if simplify_deg is not None else config.SIMPLIFY_TOLERANCE_DEG
    fallback_deg = fallback_deg if fallback_deg is not None else config.SIMPLIFY_FALLBACK_DEG
    max_mb       = max_mb       if max_mb       is not None else config.SIMPLIFY_MAX_MB

    # Centroid coords (compute in projected CRS, reproject to WGS84)
    if dissolved.crs.to_epsg() != config.CRS_OSGB36:
        raise ValueError("dissolve_clusters() expects EPSG:27700 input")

    cents_27700 = dissolved.geometry.centroid
    cents_4326  = gpd.GeoSeries(cents_27700, crs=config.CRS_OSGB36).to_crs(config.CRS_WGS84)

    out = dissolved.to_crs(epsg=config.CRS_WGS84).copy()
    out["centroid_lat"] = cents_4326.y.round(6).values
    out["centroid_lon"] = cents_4326.x.round(6).values

    keep_cols = ["cluster_id", "cluster_label", "dominant_type", "total_area_ha",
                 "polygon_count", "centroid_lat", "centroid_lon", "geometry"]
    out = out[[c for c in keep_cols if c in out.columns]]

    out.geometry = out.geometry.simplify(simplify_deg, preserve_topology=True)
    out.to_file(output_path, driver="GeoJSON")
    size_mb = os.path.getsize(output_path) / 1_048_576

    if size_mb > max_mb:
        if verbose:
            print(f"  GeoJSON > {max_mb}MB; re-simplifying at tol={fallback_deg}...", flush=True)
        out.geometry = out.geometry.simplify(fallback_deg, preserve_topology=True)
        out.to_file(output_path, driver="GeoJSON")
        size_mb = os.path.getsize(output_path) / 1_048_576

    if verbose:
        print(f"  Wrote {output_path.name}: {size_mb:.2f} MB, {len(out)} clusters", flush=True)
    return size_mb


# ── Reference-forest geometry helper ──────────────────────────────────────────
def reference_forests_gdf() -> gpd.GeoDataFrame:
    """Return REFERENCE_FORESTS as a GeoDataFrame in EPSG:27700."""
    import reference_forests
    refs = pd.DataFrame(reference_forests.REFERENCE_FORESTS)
    geoms = [Point(r["lon"], r["lat"]) for _, r in refs.iterrows()]
    gdf = gpd.GeoDataFrame(refs, geometry=geoms, crs=config.CRS_WGS84)
    return gdf.to_crs(config.CRS_OSGB36)


# ── Small convenience ──
def log(msg: str) -> None:
    print(msg, flush=True)
