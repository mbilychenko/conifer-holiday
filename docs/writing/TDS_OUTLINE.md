# TDS Article Outline — Spatial Clustering Explainer

**Working title:** "I tried every spatial clustering algorithm on 13,000 forest polygons. The simplest one won."
**Alt title:** "Geospatial clustering, explained with a festival analogy"
**Format:** Tutorial / explainer (~2,500 words)
**Vehicle:** UK NFI conifer forest clustering project (real data, reproducible)
**Demo link:** [INSERT APP URL when live]

---

## The hook (intro, ~200 words)

Opening problem: national forest inventories give you survey polygons, not destinations.
641,000 raw NFI polygons → unusable. You need to group them into ~100 human-scale places.
This is a solved problem in spatial data science — but the "obvious" algorithms fail in surprising ways.
**Reveal at end of intro:** the winner is K-means. The most boring algorithm in the toolbox.

---

## Section 1 — The core idea: spatial clustering is not regular clustering (~300 words)

Regular clustering (iris, blobs): distance in feature space.
Spatial clustering: distance IS the feature, AND geography adds two extra rules:
- Contiguity can matter (connected regions vs scattered points)
- Density varies (dense Scottish plantations vs isolated English copses)

**Metaphor:** 13,000 strangers at a music festival. You want to find the "friend groups."
- Regular K-means: assign everyone to the nearest of K stages upfront
- DBSCAN: find natural crowds — dense groups form, lone wanderers become "noise"
- HDBSCAN: smarter crowd-finding — handles the packed main stage AND the small acoustic tent
- Graph methods (Louvain): build a "who stood near whom" friendship map, find cliques
- Regionalization (SKATER): draw electoral districts — groups must be *contiguous*, no island members

Key insight to plant here: the festival is so spread out (13,000 patches across GB, highly fragmented)
that the friendship map has 2,600+ disconnected components. Graph methods can only split components,
not merge them. This preview sets up why K-means wins.

---

## Section 2 — The algorithms, one by one (~600 words)

For each: one paragraph explanation + one metaphor image + one "when to use it" line.

**K-means**
- You pick K upfront; each polygon assigned to nearest centroid; centroids update iteratively
- Festival: assigning everyone to the nearest of K tent poles before the event starts
- When to use: you have a target count, data is roughly isotropic, no contiguity needed

**DBSCAN**
- Two params: epsilon (neighbourhood radius), min_samples (density threshold)
- Festival: find crowds by looking for people within 2m of each other; lone wanderers = noise
- When to use: unknown cluster count, want to detect outliers, density is roughly uniform
- Our result: 328 clusters, negative silhouette (-0.10) — noise polygons hurt coherence

**HDBSCAN**
- Hierarchical version: adapts epsilon to local density; more robust
- Festival: the same crowd-finder but it adjusts its definition of "dense" per area of the festival
- When to use: variable density data, heterogeneous cluster sizes
- Our result: 293 clusters, good silhouette (0.40) but low bootstrap stability (ARI 0.42)

**Louvain (community detection)**
- Build a proximity graph (edges = within 10km), maximise modularity
- Festival: build the friendship network, find natural cliques via graph community detection
- When to use: data has natural network structure, graph is well-connected
- Our result: 186 clusters, strong stability (ARI 0.84) — BUT needs a dense graph

**Agglomerative + connectivity**
- Ward linkage with spatial connectivity constraint; merge nearest clusters bottom-up
- Festival: start with everyone alone; keep merging the closest pairs who are already neighbours
- When to use: you want spatial coherence + interpretable hierarchy
- Our result: 150 clusters, good all-round performance

**SKATER / Max-P (why they failed here)**
- Contiguity-constrained regionalization — clusters must be connected subgraphs
- Festival: draw electoral districts — can't have a constituency with two disconnected halves
- Why excluded: spopt 0.7.0 timed out at n=13,434. Implementation limit, not algorithm limit.
  (Mention as honest caveat — Riitters 2012 ran SKATER on continental US data in Fortran)

---

## Section 3 — How we validated (the gazetteer trick) (~300 words)

Can't use ground truth labels — there aren't any. So we used three approaches:
1. Internal metrics: silhouette, Davies-Bouldin (the standard, but gameable)
2. Bootstrap stability: ARI across 50 sub-samples (does it reproduce?)
3. **The gazetteer trick** (novel): 22 named UK forests from Wikipedia + Forestry Commission.
   Does each algorithm find Kielder as one cluster? Thetford as one cluster?
   Detection rate, single-cluster rate, area accuracy.

This is the interesting bit for readers — entity-based validation borrowed from NLP place-name extraction.
One paragraph on *why* internal metrics alone aren't enough.

---

## Section 4 — The surprise result (~300 words)

Results table (simplified — 5 algorithms, composite score).
K-means wins. Composite 0.713. Beats Louvain 0.711, Agglomerative 0.708, HDBSCAN 0.688.

**Why K-means won — the structural explanation:**
The proximity graph at 2,500m has 2,600+ disconnected components.
Graph-aware methods (Louvain, Agglomerative) can only work within components — they can't bridge the gaps.
K-means ignores the graph entirely and clusters in raw coordinate space.
On *highly fragmented* polygon networks, spatial graph structure is a liability, not an asset.

**The lesson:** match your algorithm to your data's connectivity structure, not just its geometry.
Fragmented data → density-based or partitional methods win.
Contiguous data → regionalization wins.

---

## Section 5 — Decision guide (200 words + diagram)

Quick reference for readers:

```
Is your polygon network spatially contiguous (touching/overlapping)?
  Yes → SKATER or Max-P (pygeoda implementation)
  No → is density roughly uniform?
       Yes → DBSCAN
       No → does density vary a lot (urban+rural mix)?
            Yes → HDBSCAN
            No → do you have a target cluster count?
                 Yes → K-means or Agglomerative
                 No  → Louvain on a dense proximity graph
```

Closing: the code, the dataset (Zenodo DOI when published), and the interactive app.

---

## Data + reproducibility note (50 words)

- Data: NFI Woodland GB 2023, Forestry Commission, OGL v3.0
- Code: GitHub [INSERT URL]
- Dataset: Zenodo [INSERT DOI when published]
- All analysis in Python: geopandas, scikit-learn, hdbscan, python-louvain, libpysal

---

## Key numbers to remember

| Metric | Value |
|---|---|
| Raw NFI polygons | 641,092 |
| After conifer filter + 10ha min | 13,434 |
| Final clusters | 100 |
| Winner | K-means (n=100) |
| Runner-up | Louvain on prox_10000m (n=186, composite 0.711) |
| Best stability | DBSCAN (ARI 0.894) — but negative silhouette |
| Best entity validation | DBSCAN (100% detection AND single-cluster rate) |
| Gazetteer size | 22 named UK forests |
| Detection rate (K-means) | 100% |
| Single-cluster rate (K-means) | 90% |
