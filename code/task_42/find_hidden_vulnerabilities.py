#!/usr/bin/env python3
# finds "hidden-vulnerable" nodes: bottom quartile of seamless_mavg but also
# below the median in both degree and betweenness, so classical measures would
# never flag them. Also draws the full-network vulnerability maps.

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

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

plt.rcParams.update({
    "figure.dpi": 120,
    "savefig.dpi": 300,
    "axes.labelsize": 13,
    "axes.titlesize": 14,
    "legend.fontsize": 12,
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
})


def size_by_degree(deg: np.ndarray) -> np.ndarray:
    # linear map of degree into roughly [6, 60] pt^2 for marker sizes
    deg = deg.astype(float)
    lo, hi = deg.min(), deg.max()
    if hi <= lo:
        return np.full_like(deg, 20.0)
    return 6.0 + 54.0 * (deg - lo) / (hi - lo)


def main() -> None:
    for network in NETWORKS:
        df = pd.read_csv(TABLES_DIR / f"{network}_node_level_comparison.csv")
        label = LABELS[network]

        s_q25 = df["seamless_mavg"].quantile(0.25)
        deg_med = df["degree"].median()
        btw_med = df["betweenness"].median()

        # using <= instead of < here: grids/railways have a tie-heavy degree
        # distribution whose median equals its mode (2), so a strict "<" would
        # exclude the whole degree-2 population, which is exactly what we want
        hidden = df[(df["seamless_mavg"] <= s_q25) &
                    (df["degree"] <= deg_med) &
                    (df["betweenness"] <= btw_med)].copy()
        hidden = hidden.sort_values("seamless_mavg", ascending=True)

        cols = ["node", "original_id", "lat", "lon", "community_id",
                "seamless_mavg", "degree", "betweenness"]
        out_csv = TABLES_DIR / f"{network}_hidden_vulnerable_nodes.csv"
        hidden[cols].to_csv(out_csv, index=False)
        print(f"{network}: {len(hidden)} hidden-vulnerable nodes "
              f"(seamless<=Q25={s_q25:.3f}, deg<=med={deg_med:g}, btw<=med={btw_med:.2e}) "
              f"-> {out_csv.name}")

        geo = df.dropna(subset=["lat", "lon"])
        fig, ax = plt.subplots(figsize=(8, 7))
        sc = ax.scatter(geo["lon"], geo["lat"],
                        c=geo["seamless_mavg"], cmap="viridis",
                        s=size_by_degree(geo["degree"].to_numpy()),
                        alpha=0.75, edgecolors="none")
        cb = fig.colorbar(sc, ax=ax, shrink=0.85)
        cb.set_label("SEAMLESS score $s$ (low = critical)")

        hgeo = hidden.dropna(subset=["lat", "lon"])
        if len(hgeo):
            # smaller/thinner rings when there are lots of them, so the base
            # layer underneath stays visible
            ms = 10 if len(hgeo) > 500 else 40
            lw = 0.5 if len(hgeo) > 500 else 1.2
            ax.scatter(hgeo["lon"], hgeo["lat"], s=ms, facecolors="none",
                       edgecolors="crimson", linewidths=lw, alpha=0.8,
                       label=f"hidden-vulnerable (n={len(hgeo)})")
            ax.legend(loc="best", framealpha=0.9)

        ax.set_xlabel("longitude")
        ax.set_ylabel("latitude")
        ax.set_title(f"{label}: SEAMLESS vulnerability map")
        ax.set_aspect("equal", adjustable="datalim")
        fig.tight_layout()
        out_dir = FIG_DIR / network
        out_dir.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_dir / "vulnerability_map_full.png")
        plt.close(fig)
        print(f"         wrote {network}/vulnerability_map_full.png")


if __name__ == "__main__":
    main()
