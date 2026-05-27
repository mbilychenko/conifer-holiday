# Conifer Holiday

An interactive UK conifer forest navigator — explore 100 of the largest conifer forest clusters across Scotland, England, and Wales.

## What it does

- **Interactive map** — 100 conifer forest clusters derived from the UK National Forest Inventory (NFI), coloured by forest type
- **Forest details** — click any cluster to see its name, country, area (hectares), and forest type
- **Filter by type** — switch between All / Conifer / Mixed conifer clusters
- **Google Places reviews** — visitor reviews and photos pulled server-side via the Google Places API
- **Public transit routing** — journey times and step-by-step directions from any UK address via the Google Routes API

## Tech stack

| Layer | Choice |
|---|---|
| Framework | Next.js 15 (App Router) + TypeScript |
| Styling | Tailwind CSS |
| Map | Leaflet via react-leaflet |
| Hosting | Vercel |
| Cache | Upstash Redis (24h TTL on Google API responses) |
| Reviews | Google Places API (New) — server-side only |
| Transit | Google Routes API v2 — server-side only |

## Data

The forest clusters were produced by running K-means clustering (n=100) on ~13,000 conifer polygons from the [NFI Woodland GB 2023](https://www.forestresearch.gov.uk/tools-and-resources/national-forest-inventory/) dataset. K-means outperformed HDBSCAN, Louvain, Agglomerative, and DBSCAN on a composite benchmark (silhouette + spatial coherence).

- 100 clusters across Scotland (49), England (41), Wales (10)
- Total area: ~700,000 ha of conifer forest
- Cluster sizes range from ~300 ha to ~80,000 ha

## Getting started

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### Environment variables

For Google Places reviews and transit routing, create `.env.local`:

```
GOOGLE_MAPS_API_KEY=
UPSTASH_REDIS_REST_URL=
UPSTASH_REDIS_REST_TOKEN=
```

Steps 1–5 (map, clusters, sidebar, filters, spinner) work without any API keys.

## Project structure

```
app/
├── app/
│   ├── page.tsx           ← main layout with sidebar state
│   └── api/
│       ├── places/        ← Google Places proxy
│       └── transit/       ← Google Routes proxy
├── components/
│   ├── MapView.tsx        ← Leaflet map + GeoJSON + markers + filter
│   ├── Sidebar.tsx        ← right-hand panel
│   ├── ForestPanel.tsx    ← forest metadata
│   ├── FilterBar.tsx      ← All / Conifer / Mixed chips
│   ├── ReviewsPanel.tsx   ← Google Places reviews
│   └── TransitPanel.tsx   ← journey planner
├── lib/
│   ├── types.ts           ← shared TypeScript interfaces
│   ├── forestUtils.ts     ← colour + label helpers
│   ├── leaflet-fix.ts     ← marker icon fix for Next.js
│   └── redis.ts           ← Upstash client
└── public/
    └── data/
        ├── clusters.geojson     ← 100 cluster polygons (10 MB)
        └── clusters_meta.json   ← cluster metadata
```

## Deployment

Deploy to Vercel with **Root Directory = `app`**. Add the three environment variables in the Vercel dashboard before deploying.

## Licence

MIT
