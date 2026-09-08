#!/usr/bin/env python3
# compares local-run SEAMLESS scores against the global run for the 3 local
# subnetworks (Paris, San Francisco, Netherlands), matched on original_id,
# plus draws zoom maps for each

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
INPUT_LOCAL = DATA_DIR / "seamless_input_local"
OUTPUT_LOCAL = DATA_DIR / "seamless_output_local"
TABLES_DIR = DATA_DIR / "comparison_tables"
FIG_DIR = DATA_DIR / "comparison_figures" / "local_vs_global"

# (network, slug, human label)
LOCALS = [
    ("eu_powergrid", "paris", "EU Power Grid — Paris"),
    ("us_powergrid", "san_francisco", "US Power Grid — San Francisco"),
    ("eu_railways", "nld", "EU Railways — Netherlands"),
]

plt.rcParams.update({
    "figure.dpi": 120,
    "savefig.dpi": 300,
    "axes.labelsize": 13,
    "axes.titlesize": 14,
    "legend.fontsize": 11,
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
})


def vuln_rank(values: pd.Series) -> pd.Series:
    # rank 1 = most vulnerable. seamless_mavg is a removal fraction, so the
    # most-vulnerable node has the SMALLEST value -> ascending rank
    return values.rank(ascending=True, method="average")


def build_table(network: str, slug: str) -> pd.DataFrame:
    # global master table (has original_id, seamless_mavg, adap_betweenness_frac)
    g = pd.read_csv(TABLES_DIR / f"{network}_node_level_comparison.csv")
    g = g[["original_id", "seamless_mavg", "adap_betweenness_frac"]].rename(columns={
        "seamless_mavg": "seamless_mavg_global",
        "adap_betweenness_frac": "adap_betweenness_frac_global",
    })

    # local run has its own node ids, so map local seamless_id -> original_id first
    lslug = f"{network}_{slug}"
    lmap = pd.read_csv(INPUT_LOCAL / lslug / f"{lslug}_node_mapping.csv")
    lmap = lmap.rename(columns={"seamless_id": "node"})
    lwide = pd.read_csv(OUTPUT_LOCAL / lslug / "node_scores_wide.csv")
    lwide = lwide[["node", "seamless_mavg", "adap_betweenness"]].rename(columns={
        "seamless_mavg": "seamless_mavg_local",
        "adap_betweenness": "adap_betweenness_frac_local",
    })
    l = lmap.merge(lwide, on="node")[
        ["original_id", "lat", "lon", "seamless_mavg_local", "adap_betweenness_frac_local"]
    ]

    df = l.merge(g, on="original_id", how="inner")
    df["rank_global"] = vuln_rank(df["seamless_mavg_global"])
    df["rank_local"] = vuln_rank(df["seamless_mavg_local"])

    # flag nodes that sit in the top quartile of one ranking but bottom of the other
    n = len(df)
    top = n * 0.25
    bot = n * 0.75
    disagree = (((df["rank_global"] <= top) & (df["rank_local"] >= bot)) |
                ((df["rank_local"] <= top) & (df["rank_global"] >= bot)))
    df["rank_disagreement"] = disagree

    cols = ["original_id", "lat", "lon", "seamless_mavg_global", "seamless_mavg_local",
            "rank_global", "rank_local", "adap_betweenness_frac_global",
            "adap_betweenness_frac_local", "rank_disagreement"]
    return df[cols]


def scatter_ranks(df: pd.DataFrame, label: str, out: Path, rho: float) -> None:
    fig, ax = plt.subplots(figsize=(6.2, 6))
    ok = ~df["rank_disagreement"]
    ax.scatter(df.loc[ok, "rank_global"], df.loc[ok, "rank_local"],
               s=18, alpha=0.6, c="#31688e", edgecolors="none", label="node")
    dis = df["rank_disagreement"]
    if dis.any():
        ax.scatter(df.loc[dis, "rank_global"], df.loc[dis, "rank_local"],
                   s=42, facecolors="none", edgecolors="crimson", linewidths=1.2,
                   label=f"rank disagreement (n={int(dis.sum())})")
    lim = len(df) + 1
    ax.plot([1, lim], [1, lim], color="gray", linestyle=":", linewidth=1.2)
    ax.set_xlabel("global rank (1 = most vulnerable)")
    ax.set_ylabel("local rank (1 = most vulnerable)")
    ax.set_title(f"{label}\nSpearman $\\rho$ = {rho:.3f} (n={len(df)})")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def add_osm_basemap(ax) -> None:
    # Esri WorldGrayCanvas doesn't need an API key, unlike the usual OSM/CartoDB
    # tile servers. Falls back to a plain scatter if every provider fails.
    try:
        import contextily as cx
    except Exception as e:
        print(f"    [basemap] contextily unavailable ({e}); plain scatter")
        return
    providers = [
        cx.providers.Esri.WorldGrayCanvas,
        cx.providers.Esri.WorldStreetMap,
    ]
    for prov in providers:
        try:
            cx.add_basemap(ax, crs="EPSG:4326", source=prov)
            return
        except Exception as e:
            print(f"    [basemap] {prov.get('name', '?')} failed ({type(e).__name__}); trying next")
    print("    [basemap] all providers failed; plain scatter")


def zoom_map(df: pd.DataFrame, label: str, out: Path) -> None:
    geo = df.dropna(subset=["lat", "lon"])
    fig, axes = plt.subplots(1, 2, figsize=(13, 6.2))
    for ax, col, sub in [(axes[0], "seamless_mavg_global", "global run"),
                         (axes[1], "seamless_mavg_local", "local run")]:
        sc = ax.scatter(geo["lon"], geo["lat"], c=geo[col], cmap="viridis",
                        s=28, alpha=0.85, edgecolors="none")
        fig.colorbar(sc, ax=ax, shrink=0.8, label="SEAMLESS score $s$ (low = critical)")
        ax.set_xlabel("longitude")
        ax.set_ylabel("latitude")
        ax.set_title(f"{label}\n{sub}")
        add_osm_basemap(ax)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def main() -> None:
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    for network, slug, label in LOCALS:
        df = build_table(network, slug)
        out_csv = TABLES_DIR / f"{network}_{slug}_local_vs_global.csv"
        df.to_csv(out_csv, index=False)

        rho, _ = spearmanr(df["rank_global"], df["rank_local"])
        n_dis = int(df["rank_disagreement"].sum())
        print(f"{network}_{slug}: n_common={len(df)}  Spearman(rank_global,rank_local)={rho:.3f}  "
              f"disagreements={n_dis}  -> {out_csv.name}")

        scatter_ranks(df, label, FIG_DIR / f"{network}_{slug}_rank_scatter.png", rho)
        zoom_map(df, label, FIG_DIR / f"{network}_{slug}_map.png")
        print(f"    wrote {network}_{slug}_rank_scatter.png and {network}_{slug}_map.png")


if __name__ == "__main__":
    main()
