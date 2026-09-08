#!/usr/bin/env python3
# computes degree, exact betweenness, and Louvain communities for the 4
# SEAMLESS networks, so we can compare them against the SEAMLESS scores later

from __future__ import annotations

import sys
import time
from pathlib import Path

import networkx as nx
import networkit as nk
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
DATA_DIR = REPO_ROOT / "data" / "task_42"
INPUT_DIR = DATA_DIR / "seamless_input"
OUT_DIR = DATA_DIR / "comparison_tables"

NETWORKS = ["eu_powergrid", "eu_railways", "us_airlines", "us_powergrid"]
LABELS = {
    "eu_powergrid": "EU Power Grid",
    "eu_railways": "EU Railways",
    "us_airlines": "US Airlines",
    "us_powergrid": "US Power Grid",
}

SEED = 12345


def load_graph(network: str) -> nx.Graph:
    edge_file = INPUT_DIR / network / f"{network}_edgelist.txt"
    G = nx.Graph()
    with edge_file.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            u, v = line.split()
            G.add_edge(int(u), int(v))
    return G


def exact_betweenness_networkit(G: nx.Graph) -> dict:
    # networkit is way faster than networkx for exact betweenness on big graphs
    nodes = sorted(G.nodes())
    idx = {n: i for i, n in enumerate(nodes)}
    Gk = nk.Graph(len(nodes), weighted=False, directed=False)
    for u, v in G.edges():
        Gk.addEdge(idx[u], idx[v])
    bc = nk.centrality.Betweenness(Gk, normalized=True)
    bc.run()
    scores = bc.scores()
    return {n: scores[idx[n]] for n in nodes}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_rows = []

    for network in NETWORKS:
        print(f"\n=== {LABELS[network]} ({network}) ===")
        t0 = time.time()
        G = load_graph(network)
        N, E = G.number_of_nodes(), G.number_of_edges()
        print(f"  loaded: N={N:,} E={E:,}")

        degree = dict(G.degree())

        print("  computing exact betweenness (networkit)...")
        tb = time.time()
        betweenness = exact_betweenness_networkit(G)
        print(f"    done in {time.time() - tb:.1f}s")

        r = nx.degree_assortativity_coefficient(G)

        print("  detecting communities (networkx Louvain)...")
        tc = time.time()
        communities = nx.community.louvain_communities(G, seed=SEED)
        Q = nx.community.modularity(G, communities)
        print(f"    {len(communities)} communities, Q={Q:.4f}, in {time.time() - tc:.1f}s")

        community_id = {}
        for cid, comm in enumerate(communities):
            for n in comm:
                community_id[n] = cid

        nodes = sorted(G.nodes())
        df = pd.DataFrame({
            "node": nodes,
            "degree": [degree[n] for n in nodes],
            "betweenness": [betweenness[n] for n in nodes],
            "community_id": [community_id[n] for n in nodes],
        })
        out_path = OUT_DIR / f"_classical_descriptors_{network}.csv"
        df.to_csv(out_path, index=False)
        print(f"  wrote {out_path.name}  (assortativity r={r:.4f})")

        summary_rows.append({
            "network": network,
            "N": N,
            "E": E,
            "assortativity_r": r,
            "modularity_Q": Q,
            "n_communities": len(communities),
        })
        print(f"  total {time.time() - t0:.1f}s")

    summary = pd.DataFrame(summary_rows)
    summary_path = OUT_DIR / "classical_descriptors_summary.csv"
    summary.to_csv(summary_path, index=False)
    print(f"\nwrote {summary_path}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
