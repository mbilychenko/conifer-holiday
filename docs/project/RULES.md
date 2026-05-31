# Project Rules — Conifer Holiday

Read this before each work session. These rules protect the project from the
three most common ways it could fail: an unpublishable methodology, a financial
or technical disaster, or never shipping at all.

The two rules most likely to bite you if ignored:
- **Rule 1** (cherry-picking) — kills the publication
- **Rule 6** (API key exposure) — kills your wallet

---

## Group 1 — Methodology integrity (protects the publication)

### Rule 1: Decide success criteria BEFORE tuning clustering parameters
Write down ahead of time: *"I'll accept the result if Thetford and Kielder
each emerge as one cluster, total clusters are between X and Y, noise is under
10%."* Then run DBSCAN.

If you tune until the map "looks nice," you've cherry-picked — and the
methodology becomes unpublishable. Set the bar before you see the results.

### Rule 2: EDA before modelling, always
Never run clustering on a dataset you haven't first counted, plotted, and
checked for nulls. The 30 minutes of EDA prevents the 3 hours of debugging
"why are there 0 clusters" or "why is the largest cluster the entire UK."

### Rule 3: Use the right coordinate system for the operation
- **DBSCAN distance calculations** → OSGB36 / EPSG:27700 (units: metres)
- **Leaflet web display** → WGS84 / EPSG:4326 (units: degrees)
- **OTP routing input** → WGS84 / EPSG:4326

Mixing these produces silently wrong results — DBSCAN with degrees treats
the London-to-Edinburgh gap (a few degrees) the same as the gap between two
adjacent forest patches. Reproject explicitly at each pipeline stage, and
assert the CRS at the top of every notebook cell that does spatial maths.

### Rule 4: Document parameter choices as you make them, not later
Every threshold (10ha filter, eps=2000m, min_samples=3) needs a one-line
comment in the notebook explaining *why*. Example:

```python
# eps=2000m — chosen via sensitivity analysis (Figure 1):
# at this value, Thetford emerges as 1 cluster, noise stays below 8%
EPSILON = 2000
```

This *is* your methodology section. Writing it now costs 30 seconds; reconstructing
it three weeks later costs an hour and the explanation will be lossy.

---

## Group 2 — Engineering hygiene (protects against rework and disasters)

### Rule 5: Never commit raw data to git
NFI shapefiles are hundreds of MB. They belong in `data/raw/` (gitignored).
Commit only `data/output/` — the small, processed artefacts. Document the
download URL and date in the notebook so anyone can re-fetch.

If you accidentally commit a large file, use `git filter-repo` to remove it
from history — committing a delete only hides it, doesn't shrink the repo.

### Rule 6: Google API keys never reach the browser
All Google calls go through Next.js route handlers in `app/app/api/`.
Restrict the key by HTTP referrer in Cloud Console BEFORE the first deploy.
Set a billing alert at $20 in Google Cloud Console.

A leaked key on a public GitHub repo is a real way to lose hundreds of
dollars overnight — bots scrape new commits looking for credentials.

### Rule 7: Pin dependency versions once analysis works
While exploring: `geopandas>=0.14.0` is fine.
When you're done: pin exactly — `geopandas==0.14.4`.

This applies to `requirements.txt` (Python), `package.json` (Node), the NFI
dataset version, GTFS data version, and OTP version. Reproducibility requires
exact versions.

### Rule 8: Sanity-check geospatial output visually, not just numerically
After every pipeline step, open the output in [geojson.io](https://geojson.io)
or plot with `geopandas.plot()`. `len(gdf) == 38,421` is meaningless; seeing
the polygons cluster around Kielder is meaningful.

Visual inspection catches CRS bugs, dissolve failures, and topology errors
that pass numerical tests.

---

## Group 3 — Shipping discipline (protects against never finishing)

### Rule 9: Time-box exploration
- EDA = 1 day max
- Clustering tuning = 2 days max
- App MVP = 6 days max

If you're still tweaking after that, you're polishing — ship and iterate.
The article is better when written about a real result than a perfect result.

### Rule 10: Ship MVP scope only, even when tempted
App MVP = map + clusters + Google Places + transit routing.

Phase 2 (do not build until MVP is shipped): NLP, accommodation, isochrones,
favourites, accounts, custom filters, social sharing.

Each "small addition" multiplies build time. The plan is the plan.

### Rule 11: Don't mock data — use a small real subset
When testing the app, use 5 real clusters from your actual analysis output,
not fake placeholders. Mocked data hides integration bugs you'll only find
in production (wrong field names, unexpected nulls, encoding issues).

### Rule 12: Cite sources with version + access date
Not "NFI data" — *"NFI Woodland GB 2023 release, accessed via Forestry
Commission ArcGIS Hub on 2026-05-23"*. Same for GTFS data (provider + date),
Google APIs (API version), and any blog posts/papers you reference.

Non-negotiable for credibility in academic or technical publication.

---

## Reference: Where the rules apply

| When you are… | Re-read rules |
|---|---|
| Starting an analysis notebook | 1, 2, 3, 4 |
| Committing code or data | 5, 6, 7 |
| Reviewing pipeline output | 8 |
| Tempted to add a feature to the app | 10 |
| Tempted to keep tuning | 9 |
| Writing the article or README | 4, 12 |
| Before deploying to Vercel | 6 |
