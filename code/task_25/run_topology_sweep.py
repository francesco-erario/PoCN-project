import os
import csv
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from quantum_google import build_google_matrix, classical_pagerank, quantum_pagerank
from topology_generators import (
    directed_erdos_renyi, directed_scale_free, hierarchical_digraph,
)

plt.rcParams.update({
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "axes.labelsize": 13,
    "axes.titlesize": 15,
    "legend.fontsize": 12,
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
    "lines.linewidth": 1.8,
    "lines.markersize": 4,
})

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
FIG_DIR = os.path.join(ROOT, "data", "task_25", "figures", "topology_sweep")
CSV_DIR = os.path.join(ROOT, "data", "task_25", "topology_sweep")

ALPHA = 0.85


def run_pipeline(G):

    nodes = sorted(G.nodes())
    Gm = build_google_matrix(G, alpha=ALPHA)
    cls = classical_pagerank(Gm)
    _, q_avg, T_used = quantum_pagerank(Gm)
    return nodes, cls, q_avg, T_used


def comparison_plot(ax, cls, q_avg, title):
    # sort nodes by classical rank so both curves line up on the x axis
    order = np.argsort(-cls)
    x = np.arange(len(cls))
    ax.plot(x, cls[order], "o-", color="#1f77b4", label="classical PageRank")
    ax.plot(x, q_avg[order], "s-", color="#d62728",
            label=r"average quantum PageRank $\langle I_q\rangle$")
    ax.set_xlabel("node rank (by classical PageRank, descending)")
    ax.set_ylabel("importance")
    ax.set_title(title)
    ax.legend()


def write_csv(path, nodes, cls, q_avg, extra_col=None, extra_val=None):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        header = ["node", "classical_pagerank", "quantum_pagerank"]
        if extra_col:
            header = [extra_col] + header
        w.writerow(header)
        for i, node in enumerate(nodes):
            row = [node, f"{cls[i]:.10f}", f"{q_avg[i]:.10f}"]
            if extra_col:
                row = [extra_val] + row
            w.writerow(row)


def do_erdos_renyi():
    G = directed_erdos_renyi(N=128, p=0.05, seed=0)
    nodes, cls, q_avg, T = run_pipeline(G)
    fig, ax = plt.subplots(figsize=(6, 4.2))
    comparison_plot(ax, cls, q_avg,
                    f"Directed Erdos-Renyi ($N=128$, $p=0.05$)")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "erdos_renyi_comparison.png"))
    plt.close(fig)
    write_csv(os.path.join(CSV_DIR, "erdos_renyi_results.csv"), nodes, cls, q_avg)
    print(f"Erdos-Renyi: N={len(nodes)}, T_used={T}")
    return T


def do_scale_free():
    G = directed_scale_free(N=128, seed=0)
    nodes, cls, q_avg, T = run_pipeline(G)
    fig, ax = plt.subplots(figsize=(6, 4.2))
    comparison_plot(ax, cls, q_avg, "Directed scale-free ($N=128$)")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "scale_free_comparison.png"))
    plt.close(fig)
    write_csv(os.path.join(CSV_DIR, "scale_free_results.csv"), nodes, cls, q_avg)
    print(f"Scale-free: N={len(nodes)}, T_used={T}")
    return T


def do_hierarchical():
    csv_path = os.path.join(CSV_DIR, "hierarchical_results.csv")
    # one figure with 3 panels, for n = 2, 3, 4
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4))
    rows = []
    Ts = {}
    for ax, n in zip(axes, [2, 3, 4]):
        G = hierarchical_digraph(n)
        nodes, cls, q_avg, T = run_pipeline(G)
        Ts[n] = T
        comparison_plot(ax, cls, q_avg, f"Hierarchical $n={n}$ ($N={3**n}$)")
        for i, node in enumerate(nodes):
            rows.append([n, node, f"{cls[i]:.10f}", f"{q_avg[i]:.10f}"])
    fig.suptitle("Hierarchical directed triangle family (2013 paper, Fig. 7b)",
                 fontsize=16)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(os.path.join(FIG_DIR, "hierarchical_comparison.png"))
    plt.close(fig)
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["n", "node", "classical_pagerank", "quantum_pagerank"])
        w.writerows(rows)
    print(f"Hierarchical: T_used per n = {Ts}")
    return Ts


def main():
    os.makedirs(FIG_DIR, exist_ok=True)
    os.makedirs(CSV_DIR, exist_ok=True)
    t_er = do_erdos_renyi()
    t_sf = do_scale_free()
    t_h = do_hierarchical()
    print("\nT_used summary (record in notes):")
    print(f"  erdos_renyi = {t_er}")
    print(f"  scale_free  = {t_sf}")
    print(f"  hierarchical = {t_h}")


if __name__ == "__main__":
    main()
