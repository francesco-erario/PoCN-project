#!/usr/bin/env python3
# compares SEAMLESS scores against classical centralities: scatter plots,
# Spearman correlations, and top-5% overlap between critical sets

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from scipy.stats import spearmanr

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
DATA_DIR = REPO_ROOT / "data" / "task_42"
TABLES_DIR = DATA_DIR / "comparison_tables"
FIG_DIR = DATA_DIR / "comparison_figures"

NETWORKS = ["eu_powergrid", "eu_railways", "us_airlines", "us_powergrid"]
LABELS = {
    "eu_powergrid": "EU Power Grid",
    "eu_railways": "EU Railways",
    "us_airlines": "US Airlines",
    "us_powergrid": "US Power Grid",
}

CLASSICAL_COLS = ["degree", "betweenness", "adap_degree_frac",
                  "betweenness_frac", "adap_betweenness_frac"]

plt.rcParams.update({
    "figure.dpi": 120,
    "savefig.dpi": 300,
    "axes.labelsize": 13,
    "axes.titlesize": 14,
    "legend.fontsize": 12,
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
    "lines.linewidth": 1.8,
})


def top_set(df: pd.DataFrame, col: str, frac: float = 0.05) -> set:
    # most-central nodes by a classical measure = LARGEST values
    k = max(1, int(round(frac * len(df))))
    return set(df.nlargest(k, col)["node"])


def critical_seamless_set(df: pd.DataFrame, frac: float = 0.05) -> set:
    # most-critical by SEAMLESS = SMALLEST seamless_mavg (removed first -> ~0)
    k = max(1, int(round(frac * len(df))))
    return set(df.nsmallest(k, "seamless_mavg")["node"])


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return float("nan")
    return len(a & b) / len(a | b)


def main() -> None:
    spearman_rows = []
    overlap_rows = []

    for network in NETWORKS:
        df = pd.read_csv(TABLES_DIR / f"{network}_node_level_comparison.csv")
        label = LABELS[network]

        row = {"network": network}
        for col in CLASSICAL_COLS:
            rho, _ = spearmanr(df["seamless_mavg"], df[col])
            row[f"spearman_{col}"] = rho
        spearman_rows.append(row)

        seamless_crit = critical_seamless_set(df)
        deg_top = top_set(df, "degree")
        btw_top = top_set(df, "betweenness")
        overlap_rows.append({
            "network": network,
            "top_frac": 0.05,
            "n_top": len(seamless_crit),
            "jaccard_seamless_vs_degree": jaccard(seamless_crit, deg_top),
            "jaccard_seamless_vs_betweenness": jaccard(seamless_crit, btw_top),
        })

        fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))
        pairs = [
            ("degree", "raw degree $k$"),
            ("betweenness", "static betweenness $b$"),
            ("adap_betweenness_frac", "adaptive-betweenness score"),
        ]
        for ax, (col, xlabel) in zip(axes, pairs):
            ax.scatter(df[col], df["seamless_mavg"], s=8, alpha=0.35,
                       c="#31688e", edgecolors="none")
            ax.set_xlabel(xlabel)
            ax.set_ylabel("SEAMLESS score $s$")
            rho, _ = spearmanr(df["seamless_mavg"], df[col])
            ax.set_title(f"Spearman $\\rho$ = {rho:.3f}")
        fig.suptitle(f"{label}: SEAMLESS vs classical measures", fontsize=15)
        fig.tight_layout(rect=(0, 0, 1, 0.96))
        out_dir = FIG_DIR / network
        out_dir.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_dir / "seamless_vs_classical_scatter.png")
        plt.close(fig)
        print(f"{network}: wrote seamless_vs_classical_scatter.png")

    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    sp = pd.DataFrame(spearman_rows)
    sp.to_csv(TABLES_DIR / "spearman_correlations.csv", index=False)
    print("\nspearman_correlations.csv:")
    print(sp.to_string(index=False))

    ov = pd.DataFrame(overlap_rows)
    ov.to_csv(TABLES_DIR / "topk_overlap.csv", index=False)
    print("\ntopk_overlap.csv:")
    print(ov.to_string(index=False))


if __name__ == "__main__":
    main()
