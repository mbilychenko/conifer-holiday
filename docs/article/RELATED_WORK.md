# Related Work — Spatial Clustering of Forest & Land-Cover Polygons

This overview documents the peer-reviewed literature (2008–2025) that informed
the algorithm selection, evaluation strategy, and publication framing for the
**UK NFI Conifer Destination Clustering** benchmark.

Use this file as the starting point for the Related Work section of the article.
The auto-generated `PAPER_METHODOLOGY.md` (produced by `10_methodology_export.py`)
contains the methods + results tables for the manuscript; this file provides the
*narrative* and *justification* of why those methods were chosen.

---

## Research question

**How should ~13,400 conifer forest polygons from a national forest inventory be
grouped into a small set (≈100–300) of named, contiguous-feeling "forest
destinations" suitable for both an interactive web map and a publishable open
dataset, when the underlying patch network is highly fragmented?**

This is a *regionalization* problem in spatial data science vocabulary — but the
specific constraint (polygons that are *near* but not *touching*) puts it
between density-based clustering and contiguity-constrained regionalization.
That motivates a multi-family comparison.

---

## 1. Algorithm family selection

### 1.1 Density-based methods

**Ester, Kriegel, Sander & Xu (1996) — DBSCAN.** *Proceedings of KDD.*
The foundational density-based clustering algorithm. Uses two parameters
(`eps`, `min_samples`) and labels low-density points as noise. Included in our
benchmark as the simplest density-based baseline; well understood by reviewers.

**McInnes, Healy & Astels (2017) — HDBSCAN.** *Journal of Open Source Software.*
DOI: 10.21105/joss.00205.
Hierarchical extension of DBSCAN that adapts to varying cluster densities — the
single most important property for our data, where dense Scottish plantation
networks coexist with isolated English lowland forests. HDBSCAN does **not**
require a graph, so it bypasses the structural fragmentation that traps
graph-based methods. We adopt this as our primary candidate.

**Why included:** Density-based methods operate on raw centroid coordinates and
do not impose contiguity. They naturally handle the heterogeneous density
profile of UK conifer forests. Their main weakness — that the resulting clusters
need not be spatially contiguous — turns out to be irrelevant for our use case,
because the dissolved cluster polygons are visually compact regardless.

### 1.2 Contiguity-constrained regionalization

**Assunção, Neves, Câmara & Da Costa Freitas (2006) — SKATER.** *International
Journal of Geographical Information Science*, 20(7), 797–811.
SKATER (Spatial K-cluster Analysis by Tree Edge Removal) builds a minimum
spanning tree of a spatial adjacency graph and removes the highest-cost edges
to produce *k* contiguous regions. Deterministic; widely cited; included in the
PySAL `spopt` package.

**Duque, Anselin & Rey (2012) — Max-P regions.** *Journal of Regional Science*,
52(3), 397–419. Solves the regionalization problem with an *attribute-based*
constraint (each region must satisfy a minimum size on some attribute, e.g.
total forest area). Unlike SKATER, the number of regions *p* is not specified
in advance — it emerges from the constraint. Folch & Spielman (2014, *IJGIS*
28(1), 164–184) provide the heuristic implementation used by `spopt`.

**Riitters, Wickham, Costanza & Vogt (2012) — Forest pattern regionalization
across the conterminous United States.** *Landscape Ecology*, 27(3), 393–407.
**Direct precedent for our work.** Applies SKATER to continental-scale forest
inventory data, demonstrating that contiguity-constrained hierarchical clustering
produces interpretable forest regions. The methodology section of this paper is
the closest published reference for our SKATER application.

**Why included:** Regionalization methods explicitly enforce spatial coherence —
each cluster forms a connected sub-graph. For a publishable dataset, this is the
methodologically "purest" framing: each forest destination is provably a
contiguous group of patches. The benchmark tests whether this purity is worth
the limitations imposed by graph connectivity.

### 1.3 Graph community detection

**Blondel, Guillaume, Lambiotte & Lefebvre (2008) — The Louvain method.**
*Journal of Statistical Mechanics: Theory and Experiment*, 2008(10), P10008.
DOI: 10.1088/1742-5468/2008/10/P10008.
Hierarchical modularity optimization for community detection. Standard tool in
network science; included via `python-louvain`. Tunable resolution parameter
controls the number of communities.

**Why included:** Many spatial clustering problems are equivalent to community
detection on a proximity graph. If forest patches naturally form modular
sub-graphs (i.e. each forest has many internal edges and few external edges),
Louvain should detect them. This tests whether the *network* view of the data
captures the destination structure better than the *geometric* view.

### 1.4 Hierarchical agglomerative + Ward linkage

**Ward (1963) — Hierarchical grouping to optimize an objective function.**
*JASA*, 58(301), 236–244. Implemented in `sklearn.cluster.AgglomerativeClustering`
with a sparse connectivity matrix to constrain merges to spatially-near pairs.
Provides a hierarchical alternative to SKATER without the MST step.

**Why included:** Ward linkage is among the best-studied hierarchical methods;
including it gives reviewers a familiar baseline and lets us compare it against
the more specialised SKATER on the same connectivity graph.

### 1.5 Non-spatial baseline

**K-means (MacQueen, 1967).** Standard partitioning baseline on raw centroid
coordinates. Included at reviewer request and as a sanity check — any
spatial-aware method should outperform it.

---

## 2. Why a graph-construction ablation

Our preliminary Phase 0c comparison revealed that graph-based methods (SKATER,
Max-P, Louvain) all collapsed to ~1,448 clusters when run on a 2.5 km proximity
graph. The reason was structural, not algorithmic: the 2.5 km graph has 1,448
disconnected components, and these methods can only split components, not merge
them. To produce a *fair* comparison, we therefore vary the graph construction
itself and test all algorithms across multiple graphs.

This ablation is — to the best of our literature search — a **novel
methodological contribution**. We found no published study that systematically
varies graph construction across density-based, regionalization, and community-
detection algorithms on a national-scale fragmented polygon network.

Closest precedent: Constrained spectral clustering studies (e.g. Lai & Tan,
*IEEE DSAA 2015*) demonstrate trade-offs between contiguity and homogeneity,
but they assume a fixed graph.

---

## 3. Evaluation strategy

### 3.1 Internal validity indices

**Saraçli, Doğan & Doğan (2023) — A new approach for evaluating internal cluster
validation indices.** *arXiv:2308.03894.* Systematic evaluation of silhouette,
Davies-Bouldin, and Calinski-Harabasz across varying cluster geometries.
Concludes that no single internal index is universally best — multi-metric
reporting is recommended. We adopt this guidance and report all three.

### 3.2 Spatial validity

For spatially-aware validation, we adopt **Black-Black join-count statistics**
(the correct spatial autocorrelation test for *nominal/categorical* labels —
Moran's I is invalid for nominal cluster IDs because relabelling changes the
statistic without changing the clustering) and an **intra-/inter-cluster
centroid-distance ratio**. The join-count approach is recommended in the
WIREs 2025 survey (below) for categorical spatial data.

### 3.3 Entity-based validation against a verified gazetteer

**Ju, Gao, Lewis & Crooks (2018) — A natural language processing and geospatial
clustering framework for harvesting local place names.** *arXiv:1809.02824.*
Demonstrates entity-based cluster validation against a known gazetteer in the
place-name extraction domain. We adapt this approach: 22 verified UK forest
destinations (Wikipedia + Forestry England / Forestry Land Scotland / Natural
Resources Wales) serve as gazetteer entries against which each algorithm's
clusters are scored on detection rate, single-cluster rate, tight placement,
and area accuracy.

To our knowledge, **no prior NFI clustering work has used a verified named-forest
gazetteer for validation.** This is a second novel methodological element.

### 3.4 Stability

Bootstrap resampling (80% of polygons, 50 iterations) with **Adjusted Rand Index**
(Hubert & Arabie, 1985) between the bootstrap clustering and the full clustering
quantifies algorithm reproducibility under data perturbation. Friedman test +
Nemenyi post-hoc (`scikit-posthocs`) provides the cross-algorithm statistical
comparison.

---

## 4. Survey citation: positioning our work

**Nguyen et al. (2025) — Geospatial Data Clustering in Network Space: A Survey.**
*WIREs Data Mining and Knowledge Discovery.* DOI: 10.1002/widm.70023.
The most recent comprehensive survey of geospatial clustering. Provides our
algorithm taxonomy (density-based vs. partitional vs. regionalization vs.
graph community detection) and motivates the multi-family approach. Cite this
as the framing reference in the introduction.

---

## 5. Recent applied work in forest inventory clustering

These contextual citations show that spatial clustering of forest data is a
live research area, even though no direct comparison study like ours exists.

**Wong, Hermosilla, Wulder et al. (2024) — SCANFI: a spatialized Canadian
National Forest Inventory using Landsat dense time series.** *Canadian Journal
of Forest Research.* DOI: 10.1139/cjfr-2023-0118. The recent equivalent in
Canada — demonstrates that aggregating NFI data into named spatial units, with
open data release, is publishable methodology.

**Räty, Vauhkonen et al. (2024) — Efficiency of data clustering for stratification
and sampling in the two-phase ALS-enhanced forest stock inventory.** *Remote
Sensing,* 17(23), 3871. K-means clustering of forest plot variables for sampling
design, validated via silhouette and stability across designs. Cite as recent
example of internal-validity-based cluster evaluation in forestry.

**López-Serrano, López-Sánchez et al. (2023) — Spatial predictions of tree
density and tree height across Mexico forests using ensemble learning and forest
inventory data.** *Remote Sensing.* PMC10200803. Hierarchical spatial aggregation
from individual NFI plots to regional units.

**Roy, Sun et al. (2021) — Enhancing an unsupervised clustering algorithm with a
spatial contiguity constraint for river habitat analysis.** *Ecohydrology.*
DOI: 10.1002/eco.2285. RegK-Means with spatial contiguity for ecological
regionalization — uses silhouette and Davies-Bouldin on polygon features.
Closely analogous methodology in a different ecological domain.

---

## 6. Reproducibility and data publication

**Wilkinson, Dumontier et al. (2016) — The FAIR Guiding Principles for scientific
data management and stewardship.** *Scientific Data,* 3, 160018.
DOI: 10.1038/sdata.2016.18. The canonical reference for Findable, Accessible,
Interoperable, Reusable data publication. We follow these principles for the
Zenodo deposit: DOI, OGL v3.0 licence, GeoJSON + CSV formats, schema-rich
metadata, complete reproducibility from the published GitHub repository.

---

## 7. Algorithm-selection summary table

| Algorithm | Selected because... | Primary citation |
|---|---|---|
| K-means | Non-spatial baseline; reviewer expectation | MacQueen 1967 |
| DBSCAN | Density-based baseline | Ester et al. 1996 |
| **HDBSCAN** | Handles variable density (Scottish vs. English forests) | McInnes & Healy 2017 |
| Agglomerative + connectivity | Familiar baseline for graph-constrained hierarchical clustering | Ward 1963 |
| SKATER | Proven on continental forest inventory data | Riitters et al. 2012; Assunção et al. 2006 |
| Max-P | Auto-selects k via area threshold; interpretable framing | Duque et al. 2012; Folch & Spielman 2014 |
| Louvain | Tests whether forest patches form natural network communities | Blondel et al. 2008 |

---

## 8. Gap our paper fills

To the best of our knowledge:

1. **No published study compares density-based, regionalization, and
   community-detection methods on a UK NFI-scale fragmented polygon network.**
   The closest precedent (Riitters et al. 2012) tested only SKATER on US
   forest pattern metrics rasters.

2. **No prior work uses a verified named-forest gazetteer (Wikipedia +
   Forestry Commission coordinates) to validate spatial clusters of NFI
   polygons.** This is borrowed from the place-name extraction literature
   (Ju et al. 2018) but applied to forest data for the first time.

3. **No prior work compares clustering algorithms across multiple graph
   constructions** (proximity radius variants + k-NN) for UK NFI data.

## 9. Limitations

The Phase 0d implementation relies on the `spopt 0.7.0` Python library for
SKATER and Max-P regionalization. In our environment, these implementations
exceeded the 600 s per-run timeout on all four graph variants at n = 13,434.
The root cause is implementation-specific: `spopt`'s MST-traversal step in
SKATER and its simulated-annealing region-growing in Max-P do not scale
gracefully to this dataset size. **This is an spopt 0.7.0 implementation
limitation, not a finding about the SKATER or Max-P algorithms themselves.**
Riitters et al. (2012) demonstrated SKATER feasibility on continental-US
forest pattern metrics (larger dataset) in a custom Fortran implementation.
Future work should compare alternative implementations: `pygeoda` Python
bindings, the R `ClustGeo` package (Chavent et al. 2018), or a custom
Numba MST. For this paper, SKATER and Max-P are excluded from the headline
benchmark and reported as an `spopt 0.7.0` performance note.

**Friedman test design.** A secondary design limitation emerges from the
above exclusions. After SKATER and Max-P are dropped and Agglomerative +
connectivity is restricted to `prox_2500m` only (an `O(n²)` memory
constraint on larger graphs), Louvain is the only algorithm with coverage
across all four graph variants. The planned Friedman test across the
four graphs therefore reduces to k = 1 algorithm × n = 4 graphs, which is
undefined; the test cannot run as a cross-algorithm comparison in this
design. We retain the (NaN) results table in the methodology document for
transparency and rest the cross-algorithm conclusions on the composite
ranking + bootstrap stability comparison instead. Future work should
either replace Friedman with a paired-bootstrap composite-CI comparison
across best-per-algorithm configs, or restructure the experiment as a
graph-construction ablation within Louvain.

---

## 9. BibTeX citation block

```bibtex
@article{ester1996dbscan,
  title   = {A density-based algorithm for discovering clusters in large spatial databases with noise},
  author  = {Ester, Martin and Kriegel, Hans-Peter and Sander, J{\"o}rg and Xu, Xiaowei},
  booktitle = {Proceedings of the Second International Conference on Knowledge Discovery and Data Mining},
  pages   = {226--231},
  year    = {1996}
}
@article{assuncao2006skater,
  title   = {Efficient regionalization techniques for socio-economic geographical units using minimum spanning trees},
  author  = {Assun{\c{c}}{\~a}o, R. M. and Neves, M. C. and C{\^a}mara, G. and Da Costa Freitas, C.},
  journal = {International Journal of Geographical Information Science},
  volume  = {20},
  number  = {7},
  pages   = {797--811},
  year    = {2006}
}
@article{blondel2008louvain,
  title   = {Fast unfolding of communities in large networks},
  author  = {Blondel, V. D. and Guillaume, J.-L. and Lambiotte, R. and Lefebvre, E.},
  journal = {Journal of Statistical Mechanics: Theory and Experiment},
  year    = {2008},
  doi     = {10.1088/1742-5468/2008/10/P10008}
}
@article{duque2012maxp,
  title   = {The max-p-regions problem},
  author  = {Duque, J. C. and Anselin, L. and Rey, S. J.},
  journal = {Journal of Regional Science},
  volume  = {52},
  number  = {3},
  pages   = {397--419},
  year    = {2012}
}
@article{riitters2012forest,
  title   = {A regionalization of forest pattern metrics for the conterminous United States},
  author  = {Riitters, K. H. and Wickham, J. D. and Costanza, J. K. and Vogt, P.},
  journal = {Landscape Ecology},
  volume  = {27},
  number  = {3},
  pages   = {393--407},
  year    = {2012}
}
@article{folch2014maxp,
  title   = {Identifying regions based on flexible user-defined constraints},
  author  = {Folch, D. C. and Spielman, S. E.},
  journal = {International Journal of Geographical Information Science},
  volume  = {28},
  number  = {1},
  pages   = {164--184},
  year    = {2014}
}
@article{wilkinson2016fair,
  title   = {The FAIR Guiding Principles for scientific data management and stewardship},
  author  = {Wilkinson, M. D. and Dumontier, M. and others},
  journal = {Scientific Data},
  volume  = {3},
  pages   = {160018},
  year    = {2016},
  doi     = {10.1038/sdata.2016.18}
}
@article{mcinnes2017hdbscan,
  title   = {hdbscan: Hierarchical density based clustering},
  author  = {McInnes, L. and Healy, J. and Astels, S.},
  journal = {Journal of Open Source Software},
  volume  = {2},
  number  = {11},
  pages   = {205},
  year    = {2017}
}
@article{ju2018placenames,
  title   = {A natural language processing and geospatial clustering framework for harvesting local place names from geotagged housing advertisements},
  author  = {Ju, Y. and Gao, S. and Lewis, P. and Crooks, A.},
  journal = {arXiv preprint arXiv:1809.02824},
  year    = {2018}
}
@article{saracli2023validity,
  title   = {A new approach for evaluating internal cluster validation indices},
  author  = {Sara{\c{c}}l{\i}, S. and Do{\u{g}}an, N. and Do{\u{g}}an, {\.I}.},
  journal = {arXiv preprint arXiv:2308.03894},
  year    = {2023}
}
@article{wong2024scanfi,
  title   = {A {Spatialized Canadian National Forest Inventory (SCANFI)} using {Landsat} dense time series},
  author  = {Wong, R. and Hermosilla, T. and Wulder, M. A. and others},
  journal = {Canadian Journal of Forest Research},
  year    = {2024},
  doi     = {10.1139/cjfr-2023-0118}
}
@article{nguyen2025geospatial,
  title   = {Geospatial data clustering in network space: A survey},
  author  = {Nguyen, P. and others},
  journal = {WIREs Data Mining and Knowledge Discovery},
  year    = {2025},
  doi     = {10.1002/widm.70023}
}
```

---

## 10. Reading-list priority for writing the Related Work section

If time is tight, read in this order:

1. **Nguyen et al. 2025** (WIREs survey) — frames the whole comparison
2. **Riitters et al. 2012** (Landscape Ecology) — direct precedent for forest clustering
3. **Duque et al. 2012 + Folch & Spielman 2014** — the Max-P pair
4. **Assunção et al. 2006** — SKATER foundational paper
5. **McInnes & Healy 2017** — HDBSCAN paper
6. **Saraçli et al. 2023** — internal validity methodology
7. **Ju et al. 2018** — gazetteer-based validation precedent
8. **Wilkinson et al. 2016** — FAIR data principles

Items 1–5 are necessary to write the Methods section. Items 6–8 round out the
Evaluation Strategy + Reproducibility sections.
