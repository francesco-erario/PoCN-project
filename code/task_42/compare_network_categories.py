#!/usr/bin/env python3
# compares transportation networks (railways, airlines) against power grids:
# overlays robustness curves per protocol and builds a small summary table

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
DATA_DIR = REPO_ROOT / "data" / "task_42"
OUTPUT_DIR = DATA_DIR / "seamless_output"
TABLES_DIR = DATA_DIR / "comparison_tables"
FIG_DIR = DATA_DIR / "comparison_figures" / "cross_network"

CATEGORY = {
    "eu_railways": "transportation",
    "us_airlines": "transportation",
    "eu_powergrid": "power_grid",
    "us_powergrid": "power_grid",
}
LABELS = {
    "eu_powergrid": "EU Power Grid",
    "eu_railways": "EU Railways",
    "us_airlines": "US Airlines",
    "us_powergrid": "US Power Grid",
}
# adap_betweenness lives in its own folder for the big three, main folder for us_airlines
ADAPBTW_SOURCE = {
    "eu_powergrid": "eu_powergrid_adapbtw",
    "eu_railways": "eu_railways_adapbtw",
    "us_powergrid": "us_powergrid_adapbtw",
    "us_airlines": "us_airlines",
}

# distinct color per network, distinct line style per category
COLORS = {
    "eu_powergrid": "#1f77b4",
    "us_powergrid": "#17becf",
    "eu_railways": "#d62728",
    "us_airlines": "#ff7f0e",
}
STYLE = {"power_grid": "-", "transportation": "--"}

plt.rcParams.update({
    "figure.dpi": 120,
    "savefig.dpi": 300,
    "axes.labelsize": 13,
    "axes.titlesize": 14,
    "legend.fontsize": 11,
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
    "lines.linewidth": 1.8,
})


def load_summary(network: str, protocol: str) -> pd.DataFrame:
    src = ADAPBTW_SOURCE[network] if protocol == "adap_betweenness" else network
    df = pd.read_csv(OUTPUT_DIR / src / "summary.csv")
    return df[df["protocol"] == protocol].copy()


def seamless_curve_avg(df: pd.DataFrame) -> pd.DataFrame:
    # seamless has one row per (m, p), average mean_S1_over_N over the m grid
    return df.groupby("p", as_index=False)["mean_S1_over_N"].mean()


def load_metrics(network: str, protocol: str) -> pd.DataFrame:
    src = ADAPBTW_SOURCE[network] if protocol == "adap_betweenness" else network
    df = pd.read_csv(OUTPUT_DIR / src / "metrics_summary.csv")
    return df[df["protocol"] == protocol].copy()


def make_overlay(protocol: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 6))
    for network in ["eu_powergrid", "us_powergrid", "eu_railways", "us_airlines"]:
        s = load_summary(network, protocol)
        if protocol == "seamless":
            curve = seamless_curve_avg(s)
        else:
            curve = s[["p", "mean_S1_over_N"]].sort_values("p")
        ax.plot(curve["p"], curve["mean_S1_over_N"],
                color=COLORS[network], linestyle=STYLE[CATEGORY[network]],
                label=f"{LABELS[network]} ({CATEGORY[network].replace('_', ' ')})")
    ax.set_xlabel("fraction of nodes removed $p$")
    ax.set_ylabel("relative LCC size $S_1/N$")
    nice = "SEAMLESS" if protocol == "seamless" else "adaptive betweenness"
    ax.set_title(f"Robustness under {nice} attack")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend(loc="upper right")
    fig.tight_layout()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out = FIG_DIR / f"robustness_overlay_{protocol}.png"
    fig.savefig(out)
    plt.close(fig)
    print(f"wrote {out.relative_to(DATA_DIR)}")


def main() -> None:
    for protocol in ["seamless", "adap_betweenness"]:
        make_overlay(protocol)

    rows = []
    for network in ["eu_powergrid", "us_powergrid", "eu_railways", "us_airlines"]:
        for protocol in ["seamless", "adap_betweenness"]:
            m = load_metrics(network, protocol)
            # seamless has one row per m in the grid, so average over it
            rows.append({
                "network": network,
                "category": CATEGORY[network],
                "protocol": protocol,
                "AUC_S1": m["mean_AUC_S1"].mean(),
                "p_LCC_0.5": m["mean_p_LCC_0_5"].mean(),
                "p_LCC_0.25": m["mean_p_LCC_0_25"].mean(),
                "p_LCC_0.1": m["mean_p_LCC_0_1"].mean(),
            })
    table = pd.DataFrame(rows)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    out = TABLES_DIR / "category_fragmentation_summary.csv"
    table.to_csv(out, index=False)
    print(f"\nwrote {out.name}:")
    print(table.to_string(index=False))


if __name__ == "__main__":
    main()
