"""
12_name_clusters.py — Assign human-readable names to the 100 K-means cluster centroids.

Priority order:
  1. Reference forest match: centroid within 20 km of a known forest
     AND cluster area >= 20% of expected area -> use the forest name.
  2. Nominatim reverse geocode (zoom=12): extract a forest/park/landscape
     feature name from OpenStreetMap.
  3. GeoNames fallback via reverse_geocoder: nearest settlement + " area".

Deduplication: if two clusters resolve to the same name, append the
country or a cardinal qualifier (North/South/East/West).

Outputs:
  data/output/clusters_named.geojson   -- clusters.geojson + name + country
  data/output/clusters_meta.json       -- app metadata (id, name, lat, lon, ha, type, country)
"""

import json
import sys
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import reverse_geocoder
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

sys.path.insert(0, str(Path(__file__).parent))
import utils

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parents[2]
INPUT_GJ    = ROOT / "data" / "output" / "clusters.geojson"
OUTPUT_GJ   = ROOT / "data" / "output" / "clusters_named.geojson"
OUTPUT_META = ROOT / "data" / "output" / "clusters_meta.json"

# ── Reference forests ──────────────────────────────────────────────────────────
from reference_forests import REFERENCE_FORESTS

# ── Nominatim OSM feature types that indicate a named forest / landscape ───────
FOREST_FEATURE_TYPES = {
    "wood", "forest", "nature_reserve", "national_park",
    "protected_area", "park", "forest_park",
}

# Keywords that strongly suggest a forest/park name (for display-name filtering)
FOREST_KEYWORDS = (
    "forest", "wood", "woods", "park", "glen", "moor", "dale",
    "chase", "pines", "plantation", "coedwig",  # coedwig = Welsh for forest
)


def _dist_km(lat1, lon1, lat2, lon2):
    """Haversine distance in km."""
    R = 6371.0
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlam = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def match_reference_forest(lat, lon, area_ha):
    """Return a reference forest name if centroid is within 20 km and area matches."""
    best_name = None
    best_dist = 20.1
    for f in REFERENCE_FORESTS:
        dist = _dist_km(lat, lon, f["lat"], f["lon"])
        if dist < 20.0:
            expected = f["area_ha"]
            # Accept if our cluster area is at least 20% of expected
            if area_ha >= 0.20 * expected and dist < best_dist:
                best_dist = dist
                best_name = f["name"]
    return best_name


def nominatim_name(lat, lon, geolocator):
    """
    Query Nominatim at two zoom levels. Prefer zoom=12 (local feature);
    fall back to zoom=8 (district/region) if no forest keyword found.
    Returns a name string or None.
    """
    for zoom in (12, 10, 8):
        try:
            loc = geolocator.reverse((lat, lon), zoom=zoom, language="en", timeout=10)
        except (GeocoderTimedOut, GeocoderServiceError):
            time.sleep(2)
            continue

        if loc is None:
            continue

        raw = loc.raw
        # Check if the OSM object itself is a forest/park type
        osm_type = raw.get("type", "")
        osm_class = raw.get("class", "")
        display = raw.get("display_name", "")
        addr = raw.get("address", {})

        # Primary: the name of the matched OSM feature
        feature_name = raw.get("name") or addr.get("leisure") or addr.get("natural")

        if osm_class in ("natural", "leisure", "landuse") and osm_type in FOREST_FEATURE_TYPES:
            if feature_name:
                return feature_name

        # Secondary: look for forest-keyword in the first component of display_name
        first_component = display.split(",")[0].strip()
        if any(kw in first_component.lower() for kw in FOREST_KEYWORDS):
            return first_component

        # For zoom 8, take the county/region name as fallback material
        if zoom == 8:
            return (addr.get("county") or addr.get("state_district")
                    or addr.get("region") or addr.get("state"))

    return None


def geonames_settlement(lat, lon):
    """Nearest settlement from offline GeoNames database."""
    results = reverse_geocoder.search((lat, lon), verbose=False)
    if results:
        return results[0].get("name", "")
    return ""


def infer_country(lat, lon):
    """Classify centroid as England, Scotland, or Wales from bounding boxes."""
    # Scotland: north of ~55.0 and not far east (rough)
    if lat >= 55.0 and lon <= -1.5:
        return "Scotland"
    # Wales: west of -3.0, south of 53.5
    if lon <= -3.0 and lat <= 53.5:
        return "Wales"
    # Borderline Scotland east coast
    if lat >= 55.5:
        return "Scotland"
    return "England"


def deduplicate_names(rows):
    """
    If two clusters share the same name, append a country qualifier,
    then a cardinal direction based on relative latitude.
    """
    from collections import Counter
    counts = Counter(r["name"] for r in rows)
    seen = {}
    for r in rows:
        name = r["name"]
        if counts[name] <= 1:
            continue
        qualifier = r["country"]
        candidate = f"{name} ({qualifier})"
        # If still a duplicate after country, add N/S
        if candidate in seen:
            direction = "North" if r["centroid_lat"] > seen[candidate]["lat"] else "South"
            candidate = f"{name} ({direction})"
        r["name"] = candidate
        seen[candidate] = {"lat": r["centroid_lat"]}
    return rows


def main():
    utils.log("Loading clusters...")
    gdf = gpd.read_file(INPUT_GJ)
    utils.log(f"  {len(gdf)} clusters loaded")

    geolocator = Nominatim(user_agent="conifer_holiday_naming/1.0 (personal research)")

    rows = []
    for i, row in gdf.iterrows():
        lat  = float(row["centroid_lat"])
        lon  = float(row["centroid_lon"])
        area = float(row["total_area_ha"])
        cid  = row["cluster_id"]

        # 1. Reference forest match
        name = match_reference_forest(lat, lon, area)
        method = "reference"

        # 2. Nominatim
        if name is None:
            time.sleep(1.1)  # OSM usage policy: max 1 req/s
            name = nominatim_name(lat, lon, geolocator)
            method = "nominatim"

        # 3. GeoNames settlement fallback
        if not name:
            settlement = geonames_settlement(lat, lon)
            name = f"Near {settlement}" if settlement else "Unknown"
            method = "geonames"

        country = infer_country(lat, lon)
        utils.log(f"  [{i+1:3d}/100] {cid} -> '{name}'  [{method}]  {country}")

        rows.append({
            "cluster_id":    cid,
            "name":          name,
            "country":       country,
            "dominant_type": row["dominant_type"],
            "total_area_ha": round(area, 1),
            "polygon_count": int(row["polygon_count"]),
            "centroid_lat":  round(lat, 6),
            "centroid_lon":  round(lon, 6),
            "geometry":      row["geometry"],
        })

    # Deduplicate
    rows = deduplicate_names(rows)

    # Build output GeoDataFrame
    out_gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326")
    out_gdf.to_file(OUTPUT_GJ, driver="GeoJSON")
    utils.log(f"\nSaved GeoJSON: {OUTPUT_GJ}")

    # App metadata JSON (no geometry)
    meta = []
    for r in rows:
        meta.append({
            "id":           r["cluster_id"],
            "name":         r["name"],
            "country":      r["country"],
            "dominant_type": r["dominant_type"],
            "hectares":     r["total_area_ha"],
            "polygon_count": r["polygon_count"],
            "lat":          r["centroid_lat"],
            "lng":          r["centroid_lon"],
            "googlePlaceId": None,
            "description":  None,
        })
    meta.sort(key=lambda x: x["hectares"], reverse=True)

    OUTPUT_META.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    utils.log(f"Saved metadata: {OUTPUT_META}")

    # Summary
    from collections import Counter
    method_counts = Counter()
    for r in rows:
        if any(f["name"] == r["name"] for f in REFERENCE_FORESTS):
            method_counts["reference"] += 1
        elif "Near " in r["name"]:
            method_counts["geonames"] += 1
        else:
            method_counts["nominatim"] += 1

    utils.log("\nNaming method breakdown:")
    for m, c in method_counts.items():
        utils.log(f"  {m}: {c}")

    utils.log("\nTop 20 clusters by area:")
    for r in meta[:20]:
        utils.log(f"  {r['hectares']:>8,.0f} ha  {r['name']:<40}  {r['country']}")


if __name__ == "__main__":
    main()
