#!/usr/bin/env python3
# builds one master per-node comparison csv per network, joining node_mapping,
# classical descriptors and the SEAMLESS score files together

from __future__ import annotations

from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
DATA_DIR = REPO_ROOT / "data" / "task_42"
INPUT_DIR = DATA_DIR / "seamless_input"
OUTPUT_DIR = DATA_DIR / "seamless_output"
TABLES_DIR = DATA_DIR / "comparison_tables"

NETWORKS = ["eu_powergrid", "eu_railways", "us_airlines", "us_powergrid"]

# adap_betweenness scores live in their own folder for the big three, but
# us_airlines ran all protocols together so it's in the main output folder
ADAPBTW_SOURCE = {
    "eu_powergrid": "eu_powergrid_adapbtw",
    "eu_railways": "eu_railways_adapbtw",
    "us_powergrid": "us_powergrid_adapbtw",
    "us_airlines": "us_airlines",
}


def build_one(network: str) -> None:
    mapping = pd.read_csv(INPUT_DIR / network / f"{network}_node_mapping.csv")
    mapping = mapping.rename(columns={"seamless_id": "node"})

    classical = pd.read_csv(TABLES_DIR / f"_classical_descriptors_{network}.csv")

    wide = pd.read_csv(OUTPUT_DIR / network / "node_scores_wide.csv")
    wide = wide.rename(columns={
        "adap_degree": "adap_degree_frac",
        "betweenness": "betweenness_frac",
        "random": "random_frac",
    })
    wide = wide[["node", "adap_degree_frac", "betweenness_frac", "random_frac", "seamless_mavg"]]

    adap_src = pd.read_csv(OUTPUT_DIR / ADAPBTW_SOURCE[network] / "node_scores_wide.csv")
    adap = adap_src[["node", "adap_betweenness"]].rename(
        columns={"adap_betweenness": "adap_betweenness_frac"}
    )

    df = mapping[["node", "original_id", "lat", "lon"]]
    df = df.merge(classical, on="node", how="left")
    df = df.merge(wide, on="node", how="left")
    df = df.merge(adap, on="node", how="left")

    cols = ["node", "original_id", "lat", "lon", "degree", "betweenness",
            "community_id", "adap_degree_frac", "betweenness_frac",
            "random_frac", "seamless_mavg", "adap_betweenness_frac"]
    df = df[cols]

    out = TABLES_DIR / f"{network}_node_level_comparison.csv"
    df.to_csv(out, index=False)
    n_missing = int(df.isna().any(axis=1).sum())
    print(f"{network}: {len(df)} rows -> {out.name}"
          + (f"  (WARNING: {n_missing} rows with NaN)" if n_missing else ""))


def main() -> None:
    for network in NETWORKS:
        build_one(network)


if __name__ == "__main__":
    main()
