# App Creation Plan — Conifer Holiday

## Overview

A web application that displays UK conifer and mixed woodland on an interactive
map, with public transport routing from London and forest detail (reviews, photos).
The map's primary data layer is produced by the geospatial clustering pipeline
described in `ANALYSIS_PLAN.md`. The app is the interactive face of that analysis.

**Target:** Personal use + shareable with UK outdoor community.
**Hosting:** Vercel (free Hobby tier), auto-deploy from GitHub.
**User:** Someone in London with no car, relying on trains.

---

## Tech Stack

| Layer | Choice |
|---|---|
| Framework | Next.js 15 (App Router) |
| Map | Leaflet.js via react-leaflet v4 |
| Styling | Tailwind CSS v3 |
| Language | TypeScript (`strict: false` initially) |
| Server cache | Upstash Redis (free tier) |
| Transit API | Google Routes API v2 (`travelMode: TRANSIT`) |
| Reviews/photos | Google Places API (New) |
| Hosting | Vercel Hobby (free) |

All Google API calls happen inside Next.js Route Handlers — never in client code.
The API key lives only in Vercel environment variables.

---

## Data Layer Decision (Deferred)

The primary map layer comes from the cluster analysis pipeline (`ANALYSIS_PLAN.md`).

**After running the pipeline:**
- If output GeoJSON < ~8MB → serve directly from `public/data/clusters.geojson`
- If output GeoJSON 8–20MB → serve directly but show loading spinner; add
  `Cache-Control: max-age=86400` in `next.config.js` headers
- If output GeoJSON > 20MB → convert to PMTiles format and serve via
  `protomaps/leaflet-hash` plugin (tiles load only for current viewport)

Raw NFI polygon layer (unfiltered) can be offered as a separate toggle that
loads on demand, with a performance warning.

---

## Data Pipeline (Pre-work Before Coding)

Run this before writing any app code. Output files go into `public/data/`.

### Step 1 — Download NFI data
From: https://data-forestry.opendata.arcgis.com
Search "National Forest Inventory Woodland" and download Shapefile for
England, Scotland, and/or Wales (or GB combined if available).

### Step 2 — Filter to conifer types
```python
# scripts/pipeline/01_filter.py
import geopandas as gpd

gdf = gpd.read_file('nfi_gb.shp')
conifer_types = ['Conifer', 'Mixed mainly conifer', 'Mixed mainly broadleaved']
gdf = gdf[gdf['IFT_IOA'].isin(conifer_types)]
gdf = gdf[gdf['HECTARES'] >= 10]                    # drop tiny patches
gdf = gdf[['IFT_IOA', 'HECTARES', 'geometry']]      # drop unused fields
gdf.to_file('filtered_conifers.geojson', driver='GeoJSON')
print(f"Filtered: {len(gdf)} polygons")
```

### Step 3 — Run clustering (see ANALYSIS_PLAN.md Phase 2)
The clustering script produces `clusters.geojson` — one dissolved polygon per
forest block, with cluster ID, area, dominant species type, centroid lat/lng.
This file goes into `public/data/clusters.geojson`.

### Step 4 — Simplify geometry for web display
```bash
# Using mapshaper (browser or CLI)
mapshaper clusters.geojson -simplify 10% weighted -o public/data/clusters.geojson
```
Or use https://mapshaper.org if CLI is not available.

### Step 5 — Verify
Load `public/data/clusters.geojson` in https://geojson.io — green polygons
should appear across UK, matching known forests (Kielder, Thetford, etc.).
Check that major forests appear as single coherent polygons.

---

## Project Structure

```
D:\Projects\Conifer_holiday\
├── app/
│   ├── layout.tsx                    # Root layout, fonts, OG meta tags
│   ├── page.tsx                      # Home page — server component
│   ├── globals.css
│   └── api/
│       ├── transit/
│       │   └── route.ts              # POST → Google Routes API proxy
│       └── places/
│           └── route.ts              # GET → Google Places API proxy
├── components/
│   ├── MapView.tsx                   # 'use client' — Leaflet map
│   ├── Sidebar.tsx                   # 'use client' — state hub
│   ├── ForestPanel.tsx               # Forest name, area, type chip
│   ├── ReviewsPanel.tsx              # Google reviews + photo
│   ├── TransitPanel.tsx              # Start location + journey result
│   └── FilterBar.tsx                 # 'use client' — type filter chips
├── lib/
│   ├── types.ts                      # TypeScript interfaces
│   ├── forestUtils.ts                # IFT_IOA → label + colour
│   └── redis.ts                      # Upstash Redis client singleton
├── public/
│   └── data/
│       ├── clusters.geojson          # Cluster polygons (from pipeline)
│       └── clusters_meta.json        # Cluster metadata (name, centroid,
│                                     # area, type, googlePlaceId, description)
├── scripts/
│   ├── pipeline/
│   │   ├── 01_filter.py              # Filter NFI → conifer types
│   │   └── README.md
│   └── analysis/                     # See ANALYSIS_PLAN.md
├── docs/                             # Project documentation
│   ├── INDEX.md
│   ├── APP_PLAN.md                   # This file
│   └── ANALYSIS_PLAN.md
├── .env.local                        # GOOGLE_MAPS_API_KEY + UPSTASH_* (never commit)
├── .env.example                      # Template with empty values (committed)
├── .gitignore
├── next.config.js
├── tailwind.config.js
├── tsconfig.json
└── package.json
```

---

## TypeScript Interfaces

```typescript
// lib/types.ts

export interface ForestCluster {
  id: string                  // e.g. "cluster_042"
  name: string                // e.g. "Kielder Forest" (from nearest OS place name)
  lat: number
  lng: number
  hectares: number
  dominant_type: string       // IFT_IOA value of largest constituent polygon
  country: 'England' | 'Scotland' | 'Wales'
  googlePlaceId?: string      // Hardcoded after manual testing (optional)
  description?: string        // Fallback text if Places returns nothing
}

export interface TransitResult {
  durationText: string        // "2h 45min"
  durationSeconds: number
  steps: TransitStep[]
}

export interface TransitStep {
  instruction: string
  mode: 'WALK' | 'TRAIN' | 'BUS' | 'SUBWAY'
  durationText: string
  departureStop?: string
  arrivalStop?: string
  line?: string
}

export interface PlacesResult {
  rating?: number
  reviewCount?: number
  reviews: PlaceReview[]
  photoUri?: string
  editorialSummary?: string
}

export interface PlaceReview {
  authorName: string
  rating: number
  text: string
  relativeTime: string
}
```

---

## Implementation: Day by Day

### Day 0 — Data pipeline (before any app code)
- [ ] Install Python + geopandas (`conda install -c conda-forge geopandas`)
- [ ] Download NFI shapefile from Forestry Commission ArcGIS Hub
- [ ] Run `scripts/pipeline/01_filter.py`
- [ ] Run clustering (see `ANALYSIS_PLAN.md`)
- [ ] Simplify with mapshaper
- [ ] Verify output in geojson.io
- [ ] Check file size → decide on serving strategy (see Data Layer Decision above)

### Day 1 — Scaffold + base map
```bash
npx create-next-app@latest . --typescript --tailwind --app --no-src-dir --eslint
npm install leaflet react-leaflet @types/leaflet
npm install @upstash/redis
```

Fix the Leaflet icon issue (add to `lib/leaflet-fix.ts`):
```typescript
import L from 'leaflet'
// @ts-expect-error
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: '/leaflet/marker-icon-2x.png',
  iconUrl: '/leaflet/marker-icon.png',
  shadowUrl: '/leaflet/marker-shadow.png',
})
```
Copy the Leaflet marker images from `node_modules/leaflet/dist/images/` to `public/leaflet/`.

In `app/page.tsx`:
```typescript
const MapView = dynamic(() => import('@/components/MapView'), { ssr: false })
```
`ssr: false` is non-negotiable — Leaflet uses `window` and will break SSR.

Set initial map center: `[54.5, -2.5]` (central GB), zoom 5.

Verify: tiles render, no console errors, map pans and zooms.

### Day 2 — Cluster polygon layer + filter bar
- Fetch `/data/clusters.geojson` in `MapView` via `useEffect`
- Render `<GeoJSON>` with style by `dominant_type`:
  - `Conifer` → `#1a5c1a` (dark green)
  - `Mixed mainly conifer` → `#3d8b3d` (medium green)
  - `Mixed mainly broadleaved` → `#6b8e23` (olive)
- Add circle markers at each cluster centroid (from `clusters_meta.json`)
- `FilterBar` with toggle chips — filter updates the GeoJSON `data` prop client-side
- Show loading spinner until GeoJSON fetch completes
- `Cache-Control` header for `/data/` in `next.config.js`:
  ```js
  headers: async () => [{
    source: '/data/:path*',
    headers: [{ key: 'Cache-Control', value: 'public, max-age=86400, stale-while-revalidate=604800' }]
  }]
  ```

### Day 3 — Sidebar + forest detail panel
- Two-column layout: map (left/full), sidebar (right, 380px). Stacked on mobile (`sm:flex-row`).
- `selectedForest: ForestCluster | null` state lives in `app/page.tsx`
  - Passed as setter to `MapView` (for marker clicks)
  - Passed as value to `Sidebar`
- `Sidebar` renders:
  - No selection: "Click a forest on the map to explore it."
  - Selected: `<ForestPanel>` with name, hectares, type chip (coloured), country
- Close button on sidebar resets selection

### Day 4 — Google Places (reviews + photos)
**`app/api/places/route.ts`** (GET handler):
```typescript
// Pseudocode — actual implementation in the file
const cached = await redis.get(`places:${forestId}`)
if (cached) return Response.json(cached)

// If googlePlaceId known: call Place Details directly
// Else: call Text Search with name + lat/lng location bias
// Filter result: only accept types including 'park' or 'natural_feature'
// Extract: rating, reviews (max 3), photos (1 URI), editorialSummary

await redis.setex(`places:${forestId}`, 86400, result)  // 24h TTL
return Response.json(result)
```

`ReviewsPanel.tsx` calls `/api/places?forestId=X&name=Y&lat=Z&lng=W` when a
forest is selected. Shows skeleton loader → star rating + up to 3 review
excerpts + 1 photo. If no data: show `description` from `clusters_meta.json`.

**Note:** Manually test each cluster against Places API after pipeline runs.
Hardcode `googlePlaceId` in `clusters_meta.json` for clusters that match
correctly. Skip Text Search for those (cheaper, more reliable).

### Day 5 — Transit routing
**`app/api/transit/route.ts`** (POST handler):
```typescript
// Body: { origin: string, destinationLat: number, destinationLng: number }
// Calls Google Routes API v2:
// POST https://routes.googleapis.com/directions/v2:computeRoutes
// Headers: X-Goog-Api-Key, X-Goog-FieldMask: routes.duration,routes.legs.steps.transitDetails
// Body: travelMode: TRANSIT, allowedTravelModes: [TRAIN, RAIL]
// Returns: { durationText, durationSeconds, steps }
```

`TransitPanel.tsx` UX:
- Text input: "Starting point in London" (placeholder: "e.g. Waterloo, N1 9GU")
- "Get journey time" button — disabled until forest selected AND location typed
- On click: spinner → result card:
  ```
  ~ 2h 45min by public transport
  London Waterloo → Thetford (1h 40min, Greater Anglia)
  then 25min walk (1.8km)
  [Open in Google Maps →]
  ```
- Error state: "No direct public transport found to this forest."
- Google Maps deep link: `https://www.google.com/maps/dir/?api=1&origin=<encoded>&destination=<lat>,<lng>&travelmode=transit`

Do NOT auto-trigger on forest selection. Manual button keeps costs predictable.

### Day 6 — Polish + deploy
- OG meta tags in `layout.tsx` (`og:title`, `og:description`, `og:image`)
- Mobile spot-check on real device (Leaflet touch events can be tricky)
- Add environment variables in Vercel dashboard:
  - `GOOGLE_MAPS_API_KEY`
  - `UPSTASH_REDIS_REST_URL`
  - `UPSTASH_REDIS_REST_TOKEN`
- Restrict Google API key in Cloud Console:
  - HTTP referrer: `https://your-app.vercel.app/*`
  - APIs: Routes API only + Places API (New) only
- Push to GitHub → Vercel auto-deploys
- Test in Incognito window (no session)

---

## API Cost Control

| API | Free cap | Trigger | Cost after cap |
|---|---|---|---|
| Google Routes (transit) | 10,000/mo | Manual button click | $5/1,000 |
| Google Places Text Search | 5,000/mo | Forest first click (if no placeId) | $32/1,000 |
| Google Place Details | 1,000/mo | Forest first click | ~$20/1,000 |

**Mitigations:**
1. Upstash Redis caches Places responses for 24h — repeat clicks on same forest cost nothing
2. Hardcode `googlePlaceId` in `clusters_meta.json` to skip Text Search entirely
3. Manual "Get journey time" button — no auto-trigger
4. No rate-limiting needed at low traffic; add if app goes viral (Upstash can enforce)

Realistic expected cost at community scale: **$0–15/month**.

---

## Known Risks and Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| GeoJSON too large for Leaflet | Medium | Data layer decision deferred; PMTiles fallback available |
| Google Places no match for rural forest | High (20–30%) | Fallback to `description` field in clusters_meta.json |
| Google Routes poor coverage for remote forests | Medium | Show "no route found" message honestly; add nearest station field |
| Vercel cold start on infrequently-used proxy endpoints | Low | Upstash cache means repeat requests are fast; cold starts are rare |
| react-leaflet warnings with React 19 | Low | Non-fatal; pin `react-leaflet@4.2.1` if hard errors occur |
| `window is not defined` SSR error | Certain if forgotten | All Leaflet components must use `dynamic(..., { ssr: false })` |
| API key exposed in browser | Certain if not proxied | Zero Google calls from client code — all through `app/api/` |

---

## Verification Checklist (Before Sharing)

- [ ] DevTools Network tab shows no requests to `googleapis.com` from browser
- [ ] `.env.local` not in `git status`
- [ ] API key restricted to Vercel domain in Google Cloud Console
- [ ] Test on mobile (real device, not emulator)
- [ ] Open in Incognito → app loads and works
- [ ] Test 3+ forests: reviews load or fall back gracefully
- [ ] Test transit: major forest (e.g. Thetford) → result shows
- [ ] Test transit: remote forest (e.g. Galloway) → graceful "no route" message
- [ ] File size of `clusters.geojson` confirmed and serving strategy appropriate
