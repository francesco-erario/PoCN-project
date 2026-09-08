#!/usr/bin/env python3
# Motter-Lai cascade simulation, only run on the two power grid city subnetworks
# (Paris and San Francisco) since it's cheap enough to run exactly there

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
DATA_DIR = REPO_ROOT / "data" / "task_42"
INPUT_LOCAL = DATA_DIR / "seamless_input_local"
OUTPUT_LOCAL = DATA_DIR / "seamless_output_local"
TABLES_DIR = DATA_DIR / "comparison_tables"
FIG_DIR = DATA_DIR / "comparison_figures" / "cascade"

ALPHA = 0.2

CITIES = [
    ("eu_powergrid", "paris", "EU Power Grid — Paris"),
    ("us_powergrid", "san_francisco", "US Power Grid — San Francisco"),
]

plt.rcParams.update({
    "figure.dpi": 120,
    "savefig.dpi": 300,
    "axes.labelsize": 13,
    "axes.titlesize": 14,
    "legend.fontsize": 12,
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
})


def load_local_graph(network: str, slug: str) -> nx.Graph:
    lslug = f"{network}_{slug}"
    G = nx.Graph()
    with (INPUT_LOCAL / lslug / f"{lslug}_edgelist.txt").open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            u, v = line.split()
            G.add_edge(int(u), int(v))
    return G


def run_cascade(G_full: nx.Graph, capacity: dict, trigger: int) -> int:
    # returns number of nodes removed, including the trigger node
    G = G_full.copy()
    G.remove_node(trigger)
    removed = {trigger}
    while G.number_of_nodes() > 0:
        bc = nx.betweenness_centrality(G, normalized=True)
        overloaded = [n for n, b in bc.items() if b > capacity[n]]
        if not overloaded:
            break
        G.remove_nodes_from(overloaded)
        removed.update(overloaded)
    return len(removed)


def main() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    for network, slug, label in CITIES:
        lslug = f"{network}_{slug}"
        G = load_local_graph(network, slug)
        N = G.number_of_nodes()

        # capacity is fixed once, based on the initial betweenness load
        L0 = nx.betweenness_centrality(G, normalized=True)
        capacity = {n: (1.0 + ALPHA) * L0[n] for n in G.nodes()}

        # triggers: top 5 by local seamless score, top 5 by static betweenness.
        # seamless_mavg is a removal fraction, so most-critical = SMALLEST value
        lmap = pd.read_csv(INPUT_LOCAL / lslug / f"{lslug}_node_mapping.csv")
        lwide = pd.read_csv(OUTPUT_LOCAL / lslug / "node_scores_wide.csv")
        seamless_top = lwide.nsmallest(5, "seamless_mavg")["node"].tolist()
        btw_series = pd.Series(L0)
        classical_top = btw_series.nlargest(5).index.tolist()

        rows = []
        for kind, triggers in [("seamless", seamless_top), ("classical", classical_top)]:
            for t in triggers:
                size = run_cascade(G, capacity, t)
                rows.append({
                    "trigger_node": t,
                    "trigger_type": kind,
                    "cascade_size": size,
                    "cascade_fraction": size / N,
                })
        res = pd.DataFrame(rows)
        out_csv = TABLES_DIR / f"{lslug}_cascade_results.csv"
        res.to_csv(out_csv, index=False)
        print(f"{lslug} (N={N}): "
              f"seamless mean frac={res[res.trigger_type=='seamless'].cascade_fraction.mean():.3f}, "
              f"classical mean frac={res[res.trigger_type=='classical'].cascade_fraction.mean():.3f} "
              f"-> {out_csv.name}")

        fig, ax = plt.subplots(figsize=(8, 5))
        s_frac = res[res.trigger_type == "seamless"]["cascade_fraction"].to_numpy()
        c_frac = res[res.trigger_type == "classical"]["cascade_fraction"].to_numpy()
        x = range(5)
        w = 0.4
        ax.bar([i - w / 2 for i in x], s_frac, width=w, color="#31688e",
               label="SEAMLESS top-5 trigger")
        ax.bar([i + w / 2 for i in x], c_frac, width=w, color="#e69f00",
               label="static-betweenness top-5 trigger")
        ax.set_xticks(list(x))
        ax.set_xticklabels([f"#{i+1}" for i in x])
        ax.set_xlabel("trigger rank within its set")
        ax.set_ylabel("cascade size (fraction of local $N$)")
        ax.set_title(f"{label}: Motter-Lai cascade ($\\alpha$={ALPHA})")
        ax.legend()
        fig.tight_layout()
        fig.savefig(FIG_DIR / f"{lslug}_cascade_comparison.png")
        plt.close(fig)
        print(f"    wrote {lslug}_cascade_comparison.png")


if __name__ == "__main__":
    main()
