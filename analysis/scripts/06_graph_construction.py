"""
Phase 0d-B: Graph construction ablation.

Build 4 spatial graphs over the filtered NFI conifer centroids and characterize each.
The same graphs are reused by Agglomerative, SKATER, Max-P, and Louvain in Phase 0d-C.

Outputs:
  data/output/graphs/{name}.npz             — sparse adjacency for each variant
  data/output/clustering/graph_stats.csv    — summary table for the methods section
  data/output/clustering/figures/10_graph_comparison.png — histograms + component CDF
"""

from __future__ import annotations

import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, save_npz
from scipy.spatial import cKDTree

import config
import utils

utils.log("Loading filtered NFI...")
gdf    = utils.load_filtered_nfi()
coords = utils.centroids_array(gdf)
n      = len(coords)
utils.log(f"  {n:,} centroids in EPSG:{config.CRS_OSGB36}")


def build_proximity_graph(radius_m: float, tree: cKDTree) -> tuple[csr_matrix, np.ndarray]:
    """Return symmetric sparse adjacency + edge-length array for centroids within radius."""
    pairs = tree.query_pairs(radius_m, output_type="ndarray")  # (K, 2) unique unordered
    diffs = coords[pairs[:, 0]] - coords[pairs[:, 1]]
    lengths = np.sqrt((diffs ** 2).sum(axis=1))

    rows = np.concatenate([pairs[:, 0], pairs[:, 1]])
    cols = np.concatenate([pairs[:, 1], pairs[:, 0]])
    data = np.concatenate([lengths, lengths])
    adj = csr_matrix((data, (rows, cols)), shape=(n, n))
    return adj, lengths


def build_knn_graph(k: int, tree: cKDTree) -> tuple[csr_matrix, np.ndarray]:
    """Symmetric mutual + non-mutual k-NN graph. Edge weight = distance.

    For each node we find its k+1 nearest (including self), drop self, build a directed
    graph, then symmetrize (a known weakness of asymmetric k-NN: we make it symmetric
    so SKATER/Max-P treat it consistently).
    """
    dists, idxs = tree.query(coords, k=k + 1)  # +1 because self is included
    rows, cols, data = [], [], []
    for i in range(n):
        for j in range(1, k + 1):  # skip self at idx 0
            rows.append(i);  cols.append(idxs[i, j]);  data.append(dists[i, j])
    rows = np.array(rows);  cols = np.array(cols);  data = np.array(data)

    # Symmetrize: build directed, then OR with transpose
    adj_dir = csr_matrix((data, (rows, cols)), shape=(n, n))
    adj     = adj_dir.maximum(adj_dir.T)

    # Edge lengths for the symmetric graph (avoid double counting)
    coo = adj.tocoo()
    upper_mask = coo.row < coo.col
    lengths = coo.data[upper_mask]
    return adj.tocsr(), lengths


# ── Build all graph variants ──────────────────────────────────────────────────
tree = cKDTree(coords)
stats_rows = []
adj_objects: dict[str, csr_matrix] = {}
lengths_objects: dict[str, np.ndarray] = {}

for name, spec in config.GRAPH_VARIANTS.items():
    t0 = time.time()
    if spec["kind"] == "proximity":
        adj, lengths = build_proximity_graph(spec["radius_m"], tree)
    elif spec["kind"] == "knn":
        adj, lengths = build_knn_graph(spec["k"], tree)
    else:
        raise ValueError(f"unknown graph kind: {spec['kind']}")
    build_s = time.time() - t0

    # Persist sparse adjacency
    out_path = config.GRAPH_DIR / f"{name}.npz"
    save_npz(out_path, adj)

    # Characterize via NetworkX (only connectivity / degree stats — fast on n=13k)
    G = nx.from_scipy_sparse_array(adj)
    components = list(nx.connected_components(G))
    comp_sizes = sorted([len(c) for c in components], reverse=True)
    degrees    = np.array([d for _, d in G.degree()])

    n_isolated = int((degrees == 0).sum())
    n_edges    = int(G.number_of_edges())  # unique unordered

    stats_rows.append({
        "graph":             name,
        "kind":              spec["kind"],
        "param":             spec.get("radius_m") or spec.get("k"),
        "n_nodes":           n,
        "n_edges":           n_edges,
        "n_components":      len(components),
        "n_isolated":        n_isolated,
        "largest_component": comp_sizes[0],
        "mean_degree":       round(float(degrees.mean()), 2),
        "median_degree":     int(np.median(degrees)),
        "max_degree":        int(degrees.max()),
        "mean_edge_m":       round(float(lengths.mean()), 0) if lengths.size else 0,
        "median_edge_m":     round(float(np.median(lengths)), 0) if lengths.size else 0,
        "build_seconds":     round(build_s, 2),
    })

    adj_objects[name]     = adj
    lengths_objects[name] = lengths

    utils.log(f"  {name}: {n_edges:,} edges, {len(components)} components, "
              f"largest={comp_sizes[0]:,}, built in {build_s:.1f}s")

stats_df = pd.DataFrame(stats_rows)
stats_path = config.CLUSTERING_DIR / "graph_stats.csv"
stats_df.to_csv(stats_path, index=False)
utils.log(f"\nSaved: {stats_path}")

# ── Sanity check from Phase 0c finding ────────────────────────────────────────
g1_components = stats_df.loc[stats_df["graph"] == "prox_2500m", "n_components"].iloc[0]
utils.log(f"\nSanity check — prox_2500m components: {g1_components} (Phase 0c saw 1448)")
if g1_components != 1448:
    utils.log(f"  NOTE: differs from prior run (1448). Check buffer(0) ordering or seed.")


# ── Figure: edge-length distribution + component-size CDF ──────────────────────
fig, axes = plt.subplots(2, 2, figsize=(13, 9))

# Top row: edge-length histograms (log y)
for i, (name, lengths) in enumerate(lengths_objects.items()):
    ax = axes[0, i // 2] if i < 2 else axes[1, i - 2]
    # ... actually use a single panel for all
    break  # simpler: replot below

# Single combined edge-length distribution
ax = axes[0, 0]
for name, lengths in lengths_objects.items():
    if lengths.size:
        ax.hist(lengths / 1000, bins=50, histtype="step", linewidth=1.5, label=name)
ax.set_xlabel("Edge length (km)")
ax.set_ylabel("Edge count")
ax.set_yscale("log")
ax.set_title("Edge-length distribution per graph")
ax.legend(fontsize=8)
ax.grid(alpha=0.3)

# Component-size CDF
ax = axes[0, 1]
for name, adj in adj_objects.items():
    G = nx.from_scipy_sparse_array(adj)
    sizes = sorted([len(c) for c in nx.connected_components(G)], reverse=True)
    cum = np.arange(1, len(sizes) + 1)
    ax.plot(cum, sizes, "o-", markersize=2, linewidth=1.5, label=name)
ax.set_xlabel("Component rank (largest first)")
ax.set_ylabel("Component size (nodes)")
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_title("Connected-component size distribution")
ax.legend(fontsize=8)
ax.grid(alpha=0.3, which="both")

# Degree histograms
ax = axes[1, 0]
for name, adj in adj_objects.items():
    G = nx.from_scipy_sparse_array(adj)
    degrees = [d for _, d in G.degree()]
    ax.hist(degrees, bins=50, histtype="step", linewidth=1.5, label=name)
ax.set_xlabel("Node degree")
ax.set_ylabel("Node count")
ax.set_yscale("log")
ax.set_title("Degree distribution per graph")
ax.legend(fontsize=8)
ax.grid(alpha=0.3)

# Stats table as image
ax = axes[1, 1]
ax.axis("off")
table_text = stats_df[[
    "graph", "n_edges", "n_components", "mean_degree", "mean_edge_m"
]].to_string(index=False)
ax.text(0, 0.95, "Graph properties", fontsize=10, fontweight="bold",
        family="monospace", verticalalignment="top")
ax.text(0, 0.85, table_text, fontsize=8, family="monospace", verticalalignment="top")

plt.tight_layout()
fig_path = config.FIGURE_DIR / "10_graph_comparison.png"
fig.savefig(fig_path, dpi=140)
plt.close(fig)
utils.log(f"Saved: {fig_path}")

utils.log("\n=== Phase 0d-B done ===")
utils.log(f"Adjacencies saved to: {config.GRAPH_DIR}")
utils.log(f"Stats table:          {stats_path}")
utils.log(f"Figure:               {fig_path}")
