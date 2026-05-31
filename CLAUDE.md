# CLAUDE.md — Conifer Holiday

## Project summary
UK conifer forest navigator: interactive web map + geospatial clustering analysis
for publication. Two parallel tracks — a Next.js app on Vercel and a Python data
science pipeline producing a clustered forest dataset.

## Folder structure
```
Conifer_holiday/
├── app/              ← Next.js web app (Vercel deploys with Root Directory = app)
├── analysis/
│   ├── notebooks/    ← Jupyter notebooks (EDA → clustering → accessibility)
│   ├── scripts/      ← Promoted reusable Python scripts
│   └── requirements.txt
├── data/
│   ├── raw/          ← gitignored (NFI shapefiles)
│   ├── processed/    ← gitignored (intermediate)
│   └── output/       ← committed (clusters.geojson, travel_time_matrix.csv)
├── docs/
│   ├── project/      ← Planning & reference (read these first)
│   │   ├── INDEX.md          ← Glossary + architecture + tech decisions
│   │   ├── APP_PLAN.md       ← App build, day by day
│   │   ├── ANALYSIS_PLAN.md  ← Clustering + accessibility + publication plan
│   │   └── RULES.md          ← Full project rules with explanations
│   ├── article/      ← Scientific paper track
│   │   ├── METHODOLOGY.md    ← Auto-generated methods + results (from 10_methodology_export.py)
│   │   ├── RELATED_WORK.md   ← Literature review + citations
│   │   └── REVISION_PLAN.md  ← Peer-review revision tasks (Phase 0e)
│   └── writing/      ← Blog / TDS writing
│       └── TDS_OUTLINE.md    ← Spatial clustering tutorial outline
└── CLAUDE.md         ← This file
```

## Stack
| Layer | Choice |
|---|---|
| Web framework | Next.js 15 (App Router) + TypeScript + Tailwind |
| Map | Leaflet via react-leaflet |
| Hosting | Vercel (free Hobby tier) |
| Server cache | Upstash Redis (free tier) |
| Analysis | Python + geopandas + scikit-learn / hdbscan + Jupyter |
| Bulk transit routing | OpenTripPlanner + GTFS (cloud VM, not local) |
| Live transit routing | Google Routes API v2 (transit mode, server-proxied) |
| Reviews/photos | Google Places API (New) (server-proxied) |
| Dataset release | Zenodo (DOI) |

## Rules — always enforce

1. **Never write client-side code that calls Google APIs.** All Google calls go
   through Next.js route handlers in `app/app/api/`. The API key lives only in
   Vercel environment variables. Refuse to write code that puts the key in the
   browser, even temporarily.

2. **Never commit raw data to git.** Raw NFI shapefiles, downloaded zips, and
   intermediate processed files go in `data/raw/` or `data/processed/` (both
   gitignored). Only `data/output/` is committed.

3. **EDA before clustering.** Don't propose or run any clustering until basic
   EDA has been done — polygon counts, IFT_IOA value distribution, area stats,
   geographic spread, visual preview. Push back if asked to skip this.

4. **Use the correct CRS for each operation.** OSGB36 / EPSG:27700 (metres)
   for distance-based operations like DBSCAN. WGS84 / EPSG:4326 (degrees) for
   web display and routing input. Assert the CRS explicitly at each stage.

5. **Document every parameter choice inline.** Each threshold (size filter,
   DBSCAN eps, min_samples) gets a one-line comment explaining why that value
   was chosen. This is the methodology section of the article.

6. **Cite sources with version + access date.** Not "NFI data" — "NFI Woodland
   GB 2023, accessed 2026-MM-DD". Today's date is in the conversation context.

7. **Stay within MVP scope unless asked.** App MVP = map + clusters + Google
   Places + transit routing. If the user asks me to add features beyond MVP
   (NLP, accommodation, accounts, isochrones, favourites), confirm they want
   Phase 2 scope before building.

8. **Don't mock data.** Use real output from the analysis pipeline. A 5-cluster
   subset of real `clusters.geojson` beats fake placeholders for app testing.

9. **Visually sanity-check geospatial output.** After any geopandas/clustering
   step, suggest opening the result in geojson.io or plotting with `.plot()`.
   Numerical counts alone do not validate spatial correctness.

10. **Pin dependency versions once a step is working.** Move from `>=` to `==`
    in `requirements.txt` and `package.json` once the user confirms a stage is
    done. Floating versions break reproducibility.

## Things to refuse or flag

- Refuse: writing Google API keys, secrets, or `.env.local` contents to any
  file that could be committed.
- Refuse: `git add data/raw/` or `git add *.shp` style commands.
- Flag: any clustering attempt without prior EDA.
- Flag: any geopandas operation without explicit CRS handling.
- Flag: any new app feature request beyond MVP — confirm scope first.

## Pointers

- For full rule rationale → `docs/project/RULES.md`
- For glossary / what is NFI / IFT_IOA / DBSCAN / OTP → `docs/project/INDEX.md`
- For app build steps → `docs/project/APP_PLAN.md`
- For analysis steps → `docs/project/ANALYSIS_PLAN.md`
- For scientific paper methodology → `docs/article/METHODOLOGY.md`
- For related work / citations → `docs/article/RELATED_WORK.md`
- For TDS blog outline → `docs/writing/TDS_OUTLINE.md`
