"""
12b_name_clusters_cleanup.py — Post-processing pass on cluster names.

Fixes:
  1. Country misassignments: replace simple lat/lon bounding box with
     reverse_geocoder admin1 field ("Scotland", "Wales", else "England").
  2. Bare admin names (no forest keyword, no "Near"): do a Nominatim
     bounding-box search for named forest/wood features within 30 km;
     fall back to "{AdminName} area".
  3. Duplicate names: append country or N/S cardinal qualifier.

Input:  data/output/clusters_meta.json
Output: data/output/clusters_meta.json  (overwrites in place)
        data/output/clusters_named.geojson  (updated country + name columns)
"""

import json
import time
from collections import Counter
from pathlib import Path

import geopandas as gpd
import reverse_geocoder
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

ROOT        = Path(__file__).resolve().parents[2]
META_PATH   = ROOT / "data" / "output" / "clusters_meta.json"
GJ_PATH     = ROOT / "data" / "output" / "clusters_named.geojson"

FOREST_KEYWORDS = (
    "forest", "wood", "woods", "park", "glen", "moor", "dale",
    "chase", "pines", "plantation", "coedwig", "mynydd", "fforest",
)

ADMIN_NAMES = {
    # UK council / county / region names that Nominatim returns for rural areas
    "highland", "shropshire", "dumfries and galloway", "surrey", "torfaen",
    "north yorkshire", "east sussex", "wiltshire", "perth and kinross",
    "scotland", "england", "wales", "devon", "cornwall", "powys",
    "ceredigion", "conwy", "monmouthshire", "argyll and bute",
    "aberdeenshire", "angus", "stirling", "south lanarkshire",
    "east ayrshire", "north ayrshire", "south ayrshire",
}


def is_bare_admin(name: str) -> bool:
    name_lower = name.lower()
    if name_lower in ADMIN_NAMES:
        return True
    if any(kw in name_lower for kw in FOREST_KEYWORDS):
        return False
    if name_lower.startswith("near "):
        return False
    # Check if it's just a place name with no forest context
    # (single word or compound with no forest keyword — likely admin)
    words = name_lower.split()
    return len(words) <= 3 and not any(kw in name_lower for kw in FOREST_KEYWORDS)


def fix_country(lat: float, lng: float) -> str:
    """Use reverse_geocoder admin1 field — more accurate than bounding boxes."""
    results = reverse_geocoder.search((lat, lng), verbose=False)
    if not results:
        return "England"
    admin1 = results[0].get("admin1", "")
    if "Scotland" in admin1:
        return "Scotland"
    if "Wales" in admin1 or "Cymru" in admin1:
        return "Wales"
    return "England"


def search_forest_name(lat: float, lng: float, geolocator) -> str | None:
    """
    Nominatim bounded search for named forest/wood features within ~25 km.
    Returns the nearest forest name or None.
    """
    delta = 0.3  # ~25-30 km at UK latitudes
    viewbox = f"{lng - delta},{lat - delta},{lng + delta},{lat + delta}"

    for query in ("forest", "wood", "forest park", "woods"):
        try:
            results = geolocator.geocode(
                query,
                exactly_one=False,
                limit=5,
                viewbox=viewbox,
                bounded=True,
                language="en",
                timeout=10,
                country_codes="gb",
            )
        except (GeocoderTimedOut, GeocoderServiceError):
            time.sleep(2)
            continue

        if not results:
            continue

        for r in results:
            name = r.raw.get("name") or r.address.split(",")[0].strip()
            if name and any(kw in name.lower() for kw in FOREST_KEYWORDS):
                return name

        time.sleep(1.1)

    return None


def deduplicate(entries: list[dict]) -> list[dict]:
    counts = Counter(e["name"] for e in entries)
    seen: dict[str, float] = {}

    for e in entries:
        name = e["name"]
        if counts[name] <= 1:
            continue
        qualified = f"{name} ({e['country']})"
        if qualified not in seen:
            e["name"] = qualified
            seen[qualified] = e["lat"]
        else:
            direction = "North" if e["lat"] > seen[qualified] else "South"
            e["name"] = f"{name} ({direction})"

    return entries


def main():
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    geolocator = Nominatim(user_agent="conifer_holiday_cleanup/1.0 (personal research)")

    changes = []
    for entry in meta:
        lat, lng = entry["lat"], entry["lng"]
        old_name    = entry["name"]
        old_country = entry["country"]

        # 1. Fix country
        correct_country = fix_country(lat, lng)
        if correct_country != old_country:
            print(f"  country fix: {entry['id']}  {old_country} -> {correct_country}  ({old_name})")
            entry["country"] = correct_country

        # 2. Fix bare admin names
        if is_bare_admin(old_name):
            time.sleep(1.1)
            forest_name = search_forest_name(lat, lng, geolocator)
            if forest_name:
                new_name = forest_name
            else:
                # Append "area" to make it clear it's a region label
                new_name = f"{old_name} area"
            print(f"  name fix:    {entry['id']}  '{old_name}' -> '{new_name}'")
            entry["name"] = new_name
            changes.append(entry["id"])

    # 3. Deduplicate
    meta = deduplicate(meta)
    dup_names = [e["name"] for e in meta if "(" in e["name"]]
    if dup_names:
        print(f"  deduplication: {dup_names}")

    # Save meta
    META_PATH.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {META_PATH}")

    # Update GeoJSON
    gdf = gpd.read_file(GJ_PATH)
    meta_by_id = {e["id"]: e for e in meta}
    gdf["name"]    = gdf["cluster_id"].map(lambda x: meta_by_id[x]["name"])
    gdf["country"] = gdf["cluster_id"].map(lambda x: meta_by_id[x]["country"])
    gdf.to_file(GJ_PATH, driver="GeoJSON")
    print(f"Saved: {GJ_PATH}")

    # Summary
    print(f"\nTotal fixes: {len(changes)} name changes")
    print("\nFull name list (sorted by hectares):")
    for e in meta:
        print(f"  {e['hectares']:>8,.0f} ha  {e['name']:<45}  {e['country']}")


if __name__ == "__main__":
    main()
