#!/usr/bin/env python3
# cuts a local subnetwork (a city radius or a country) out of one of the full
# SEAMLESS networks and writes it out in the same SEAMLESS input format

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import networkx as nx
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
DATA_DIR = REPO_ROOT / "data" / "task_42"
INPUT_DIR = DATA_DIR / "seamless_input"
OUT_DIR = DATA_DIR / "seamless_input_local"

sys.path.insert(0, str(SCRIPT_DIR))
from prepare_seamless_inputs import (  # noqa: E402
    largest_connected_component,
    relabel_contiguous,
    write_edgelist,
    write_node_mapping,
    validate_written_edgelist,
)


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    # great-circle distance in km, mean Earth radius 6371 km
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def root_prefix(original_id: str) -> str:
    # country prefix = part before the first '_' or '.'
    s = str(original_id)
    for sep in ("_", "."):
        idx = s.find(sep)
        if idx != -1:
            s = s[:idx]
    return s


def load_full_graph(network: str) -> nx.Graph:
    edge_file = INPUT_DIR / network / f"{network}_edgelist.txt"
    G = nx.Graph()
    with edge_file.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            u, v = line.split()[:2]
            G.add_edge(int(u), int(v))
    return G


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract a local subnetwork in SEAMLESS format.")
    ap.add_argument("--network", required=True,
                    choices=["eu_powergrid", "us_powergrid", "eu_railways"])
    ap.add_argument("--country", type=str, default=None,
                    help="ISO3 root prefix to keep (eu_railways mode).")
    ap.add_argument("--center-lat", type=float, default=None)
    ap.add_argument("--center-lon", type=float, default=None)
    ap.add_argument("--radius-km", type=float, default=40.0)
    ap.add_argument("--label", required=True, help="Short slug for the output folder name.")
    args = ap.parse_args()

    mapping = pd.read_csv(INPUT_DIR / args.network / f"{args.network}_node_mapping.csv")

    if args.country is not None:
        code = args.country.upper()
        # BUFFER* nodes are OSM extraction padding, drop them before matching
        keep = mapping[~mapping["original_id"].astype(str).str.startswith("BUFFER")]
        keep = keep[keep["original_id"].apply(lambda s: root_prefix(s) == code)]
        selector = f"country={code}"
    else:
        if args.center_lat is None or args.center_lon is None:
            ap.error("radius mode needs --center-lat and --center-lon")
        d = mapping.apply(
            lambda row: haversine_km(args.center_lat, args.center_lon, row["lat"], row["lon"]),
            axis=1,
        )
        keep = mapping[d <= args.radius_km]
        selector = f"center=({args.center_lat},{args.center_lon}) r={args.radius_km}km"

    keep_ids = set(keep["seamless_id"])
    print(f"[{args.network}] {selector}: {len(keep_ids)} nodes match filter")

    G = load_full_graph(args.network)
    sub = G.subgraph(keep_ids).copy()
    print(f"  induced subgraph: N={sub.number_of_nodes()} E={sub.number_of_edges()}")

    if sub.number_of_nodes() == 0:
        raise SystemExit("No nodes selected — check the filter.")

    lcc = largest_connected_component(sub)
    print(f"  LCC: N={lcc.number_of_nodes()} E={lcc.number_of_edges()}")

    # attach lat/lon back onto the LCC nodes since relabel_contiguous reads them
    coords = keep.set_index("seamless_id")[["lat", "lon"]]
    nx.set_node_attributes(lcc, coords["lat"].to_dict(), "lat")
    nx.set_node_attributes(lcc, coords["lon"].to_dict(), "lon")
    orig = keep.set_index("seamless_id")["original_id"]
    nx.set_node_attributes(lcc, orig.to_dict(), "original_id")

    G_relabeled, mapping_df = relabel_contiguous(lcc)

    # relabel_contiguous sets original_id to the old graph key (global
    # seamless_id); swap it for the true original_id so local<->global joins work
    id_lookup = {old: orig[old] for old in orig.index}
    mapping_df["original_id"] = mapping_df["original_id"].map(id_lookup)

    slug = f"{args.network}_{args.label}"
    net_dir = OUT_DIR / slug
    edge_path = net_dir / f"{slug}_edgelist.txt"
    map_path = net_dir / f"{slug}_node_mapping.csv"
    write_edgelist(G_relabeled, edge_path, slug)
    write_node_mapping(mapping_df, map_path)
    validate_written_edgelist(edge_path, expected_n=lcc.number_of_nodes())

    n = G_relabeled.number_of_nodes()
    print(f"  wrote {edge_path.relative_to(DATA_DIR)}  (N={n}, E={G_relabeled.number_of_edges()})")
    if args.country is None and n > 2000:
        print(f"  WARNING: N={n} > 2000 — consider halving --radius-km "
              f"and re-running to keep the exact SEAMLESS step cheap.")


if __name__ == "__main__":
    main()
