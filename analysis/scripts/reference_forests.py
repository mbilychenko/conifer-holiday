"""
Reference dataset of major UK conifer / mixed-conifer forest destinations.

Coordinates verified from Wikipedia infoboxes and Forestry England/FLS/NRW pages.
Used to validate that clustering output corresponds to forests humans recognise.

Areas are the commonly-cited public figures (often the "managed forest park" total,
NOT the conifer-only NFI area). Treat as order-of-magnitude expectations, not strict
equalities — our 10ha+ conifer filter typically captures 30–80% of a forest park's
total area depending on species mix.

`role`:
  - "primary": expected to have a substantial conifer cluster (positive control)
  - "negative": dominated by broadleaf — expected to have no/small conifer cluster
"""

REFERENCE_FORESTS = [
    # ── England — primary conifer destinations ──────────────────────────────
    {"name": "Thetford Forest",   "country": "England", "lat": 52.4643, "lon":  0.6667, "area_ha": 18730, "role": "primary"},
    {"name": "Kielder Forest",    "country": "England", "lat": 55.2081, "lon": -2.5281, "area_ha": 60000, "role": "primary"},
    {"name": "Cannock Chase",     "country": "England", "lat": 52.7460, "lon": -2.0010, "area_ha":  2222, "role": "primary"},
    {"name": "Grizedale Forest",  "country": "England", "lat": 54.3340, "lon": -3.0192, "area_ha":  2447, "role": "primary"},
    {"name": "Whinlatter Forest", "country": "England", "lat": 54.6078, "lon": -3.2300, "area_ha":  1200, "role": "primary"},
    {"name": "Hamsterley Forest", "country": "England", "lat": 54.6833, "lon": -1.9333, "area_ha":  2000, "role": "primary"},
    {"name": "Dalby Forest",      "country": "England", "lat": 54.2780, "lon": -0.6540, "area_ha":  3576, "role": "primary"},
    {"name": "Delamere Forest",   "country": "England", "lat": 53.2375, "lon": -2.6860, "area_ha":   972, "role": "primary"},
    {"name": "Wendover Woods",    "country": "England", "lat": 51.7700, "lon": -0.7500, "area_ha":   325, "role": "primary"},

    # ── Wales — primary conifer destinations ────────────────────────────────
    {"name": "Coed y Brenin",     "country": "Wales",   "lat": 52.8433, "lon": -3.9033, "area_ha":  3645, "role": "primary"},
    {"name": "Hafren Forest",     "country": "Wales",   "lat": 52.5200, "lon": -3.5833, "area_ha":  3513, "role": "primary"},
    {"name": "Brechfa Forest",    "country": "Wales",   "lat": 51.9337, "lon": -4.2371, "area_ha":  6500, "role": "primary"},
    {"name": "Afan Forest Park",  "country": "Wales",   "lat": 51.6830, "lon": -3.8000, "area_ha":  3250, "role": "primary"},

    # ── Scotland — primary conifer destinations ─────────────────────────────
    {"name": "Galloway Forest Park", "country": "Scotland", "lat": 55.0502, "lon": -4.2667, "area_ha": 78000, "role": "primary"},
    {"name": "Tay Forest Park",      "country": "Scotland", "lat": 56.6500, "lon": -3.8333, "area_ha": 33000, "role": "primary"},
    {"name": "Glentress Forest",     "country": "Scotland", "lat": 55.6581, "lon": -3.1548, "area_ha":  1667, "role": "primary"},
    {"name": "Argyll Forest Park",   "country": "Scotland", "lat": 56.1800, "lon": -4.9200, "area_ha": 24000, "role": "primary"},
    {"name": "Glenmore Forest Park", "country": "Scotland", "lat": 57.1833, "lon": -3.6167, "area_ha":  5000, "role": "primary"},
    {"name": "Loch Ard / Achray",    "country": "Scotland", "lat": 56.1800, "lon": -4.4000, "area_ha": 10000, "role": "primary"},
    {"name": "Glen Affric",          "country": "Scotland", "lat": 57.2700, "lon": -4.9500, "area_ha": 17000, "role": "primary"},

    # ── Mixed forests — historically broadleaf but with significant conifer plantations ──
    # Marked "mixed" — a conifer cluster IS expected; the area should be small-to-modest
    # relative to the named forest's total broadleaf+conifer area
    {"name": "Sherwood Forest",   "country": "England", "lat": 53.2044, "lon": -1.0728, "area_ha":   425, "role": "mixed",
     "note": "Ancient oak woodland, but adjacent Sherwood Pines is a major conifer plantation"},
    {"name": "Forest of Dean",    "country": "England", "lat": 51.7891, "lon": -2.5432, "area_ha": 22500, "role": "mixed",
     "note": "Historic oak forest with significant conifer plantation compartments"},
]
