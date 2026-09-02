#!/usr/bin/env python3
"""
Prepare SEAMLESS-format edge lists and node mappings for the four raw networks
(EU power grid, EU railways, US airlines, US power grid).

    - US power grid "broken index" remap (raw node index is a "lon|lat"
      string; remapped to a fresh sequential integer index).
    - Simple undirected graph construction via G.add_nodes_from(node_ids) +
      G.add_edges_from(zip(source, target)) (nx.Graph automatically dedupes
      mirrored/duplicate edges).
    - lat/lon attached separately via nx.set_node_attributes.
    - drops self-loops explicitly,
    - restricts every network to its largest connected component (LCC),
    - relabels LCC nodes to contiguous integers 1..N_lcc (required by
      seamless_robustness.read_integer_edgelist, whose default behaviour of
      filling in "missing" integer ids silently injects phantom isolated
      nodes if the relabeling has any gaps),
    - validates every written edge list by round-tripping it through
      read_integer_edgelist().

Safe to re-run: output files are overwritten in place.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import networkx as nx
import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
RAW_DATA_DIR = REPO_ROOT / "data" / "task_42" / "project_42_raw_datasets"
OUTPUT_DIR = SCRIPT_DIR / "seamless_input"

sys.path.insert(0, str(SCRIPT_DIR))
from seamless_robustness import (  # noqa: E402
    connected_component_sizes,
    read_integer_edgelist,
)


class SeamlessValidationError(RuntimeError):
    """Raised when a written edge list fails the mandatory round-trip validation."""


@dataclass
class NetworkStats:
    """Per-network bookkeeping for the final summary table."""

    label: str
    raw_n: int
    raw_e: int
    cleaned_n: int
    cleaned_e: int
    self_loops_dropped: int
    orphan_count: int
    lcc_n: int
    lcc_e: int
    written_n: int
    written_e: int
    lat_lon_missing: int
    lat_lon_out_of_range: int


# =======================================
# Raw loading + network-specific cleaning 
# =======================================

def load_eu_powergrid() -> tuple[pd.DataFrame, pd.DataFrame, str]:
    edges = pd.read_csv(RAW_DATA_DIR / "graph_EU_powergrid_osm_edgelist.csv.gz")
    nodes = pd.read_csv(RAW_DATA_DIR / "graph_EU_powergrid_osm_nodeloc.csv.gz")
    return edges, nodes, "id"


def load_eu_railways() -> tuple[pd.DataFrame, pd.DataFrame, str]:
    edges = pd.read_csv(RAW_DATA_DIR / "graph_EU_railways_osm_edgelist.csv.gz")
    nodes = pd.read_csv(RAW_DATA_DIR / "graph_EU_railways_osm_nodeloc.csv.gz")
    return edges, nodes, "NODE_ID"


def load_us_airlines() -> tuple[pd.DataFrame, pd.DataFrame, str]:
    edges = pd.read_csv(RAW_DATA_DIR / "graph_US_airlines_BTS_edgelist.csv.gz")
    nodes = pd.read_csv(RAW_DATA_DIR / "graph_US_airlines_BTS_nodeloc.csv.gz")
    return edges, nodes, "NODE_ID"


def load_us_powergrid() -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """
    US power grid raw node "index" is actually a "lon|lat" string, not a
    stable integer id. Reproduces the notebook's remap-to-sequential-integer
    cleaning step (data_explorer.ipynb, cell 2) before graph construction.
    """
    edges = pd.read_csv(RAW_DATA_DIR / "graph_US_powergrid_energyatlas_edgelist.csv.gz")
    nodes = pd.read_csv(RAW_DATA_DIR / "graph_US_powergrid_energyatlas_nodeloc.csv.gz")

    nodes = nodes.rename(columns={"index": "old_index"})
    dup = int(nodes["old_index"].duplicated().sum())
    if dup:
        print(f"  [US Power Grid] WARNING: {dup} duplicated raw node indexes")

    nodes["index"] = range(len(nodes))
    id_map = dict(zip(nodes["old_index"], nodes["index"]))

    used_nodes = set(edges["source_node"]) | set(edges["target_node"])
    all_nodes = set(nodes["old_index"])
    orphans = used_nodes - all_nodes
    if orphans:
        print(f"  [US Power Grid] WARNING: {len(orphans)} edge endpoints have no node-file match")

    edges["source"] = edges["source_node"].map(id_map).astype("Int64")
    edges["target"] = edges["target_node"].map(id_map).astype("Int64")

    missing = edges[edges["source"].isna() | edges["target"].isna()]
    if len(missing):
        raise SeamlessValidationError(
            f"US Power Grid: {len(missing)} edges could not be remapped to an integer index."
        )

    edges = edges.drop(columns=["source_node", "target_node"]).astype({"source": int, "target": int})
    nodes = nodes.drop(columns="old_index")

    return edges, nodes, "index"


LOADERS = {
    "eu_powergrid": ("EU Power Grid", load_eu_powergrid),
    "eu_railways": ("EU Railways", load_eu_railways),
    "us_airlines": ("US Airlines", load_us_airlines),
    "us_powergrid": ("US Power Grid", load_us_powergrid),
}


# ==================
# Graph construction 
# ==================

def build_graph(edges: pd.DataFrame, nodes: pd.DataFrame, node_col: str) -> nx.Graph:
    """
    Simple undirected graph construction, matching data_explorer.ipynb:
        G.add_nodes_from(node_ids) then G.add_edges_from(zip(source, target)).
    nx.Graph dedupes mirrored/duplicate edges automatically; self-loops are
    NOT dropped by this step (see drop_self_loops()).
    """
    G = nx.Graph()
    G.add_nodes_from(nodes[node_col])

    src_col, tgt_col = edges.columns[0], edges.columns[1]
    G.add_edges_from(zip(edges[src_col], edges[tgt_col]))

    coords = nodes.set_index(node_col)[["longitude", "latitude"]]
    nx.set_node_attributes(G, coords["longitude"].to_dict(), "lon")
    nx.set_node_attributes(G, coords["latitude"].to_dict(), "lat")

    return G


def drop_self_loops(G: nx.Graph) -> int:
    """Remove self-loops in place. Returns the number removed."""
    loops = list(nx.selfloop_edges(G))
    G.remove_edges_from(loops)
    return len(loops)


def count_orphans(G: nx.Graph, nodes: pd.DataFrame, node_col: str) -> int:
    """
    Count nodes present in the graph only because they appeared as an edge
    endpoint, with no matching row (and therefore no lat/lon) in the node
    file. These end up with no "lon"/"lat" node attribute.
    """
    return sum(1 for _, d in G.nodes(data=True) if "lat" not in d or "lon" not in d)


def check_lat_lon_sanity(G: nx.Graph) -> tuple[int, int]:
    """
    Basic sanity check only (per task instructions: the historical
    lon/lat-swap bug is already fixed upstream, no recovery logic needed).
    Returns (missing_count, out_of_range_count).
    """
    missing = 0
    out_of_range = 0

    for _, d in G.nodes(data=True):
        lat = d.get("lat")
        lon = d.get("lon")

        if lat is None or lon is None or pd.isna(lat) or pd.isna(lon):
            missing += 1
            continue

        if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
            out_of_range += 1

    return missing, out_of_range


# =============================================================================
# LCC extraction, relabeling, and file writing
# =============================================================================

def largest_connected_component(G: nx.Graph) -> nx.Graph:
    lcc_nodes = max(nx.connected_components(G), key=len)
    return G.subgraph(lcc_nodes).copy()


def _deterministic_sort(nodes: list) -> list:
    """Sort node ids deterministically: numeric sort for int ids, else string sort."""
    if all(isinstance(n, (int, np.integer)) for n in nodes):
        return sorted(nodes)
    return sorted(nodes, key=str)


def relabel_contiguous(G_lcc: nx.Graph) -> tuple[nx.Graph, pd.DataFrame]:
    """
    Relabel LCC nodes to contiguous integers 1..N_lcc.

    Returns the relabeled graph plus a mapping DataFrame with columns
    seamless_id, original_id, lat, lon.
    """
    ordered_original = _deterministic_sort(list(G_lcc.nodes()))
    mapping = {orig: i for i, orig in enumerate(ordered_original, start=1)}

    G_relabeled = nx.relabel_nodes(G_lcc, mapping, copy=True)

    rows = []
    for orig in ordered_original:
        d = G_lcc.nodes[orig]
        rows.append({
            "seamless_id": mapping[orig],
            "original_id": orig,
            "lat": d.get("lat"),
            "lon": d.get("lon"),
        })
    mapping_df = pd.DataFrame(rows).sort_values("seamless_id").reset_index(drop=True)

    return G_relabeled, mapping_df


def write_edgelist(G_relabeled: nx.Graph, path: Path, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    n, e = G_relabeled.number_of_nodes(), G_relabeled.number_of_edges()

    with path.open("w") as f:
        f.write(f"# {label} — SEAMLESS input edge list\n")
        f.write(f"# generated: {date.today().isoformat()}\n")
        f.write(f"# N={n} E={e}\n")
        for u, v in sorted((min(a, b), max(a, b)) for a, b in G_relabeled.edges()):
            f.write(f"{u} {v}\n")


def write_node_mapping(mapping_df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mapping_df.to_csv(path, index=False)


def validate_written_edgelist(path: Path, expected_n: int) -> None:
    """
    Mandatory validation: round-trip the just-written edge list through
    read_integer_edgelist() and confirm (a) node count matches the LCC size
    exactly and (b) the result is a single connected component.
    """
    adj = read_integer_edgelist(path)

    if len(adj) != expected_n:
        raise SeamlessValidationError(
            f"{path}: read_integer_edgelist returned {len(adj)} nodes, "
            f"expected exactly {expected_n} (LCC size). This likely means the "
            f"relabeling was not perfectly contiguous, or phantom isolated "
            f"nodes were injected."
        )

    sizes = connected_component_sizes(adj)
    if len(sizes) != 1:
        raise SeamlessValidationError(
            f"{path}: expected a single connected component, found {len(sizes)} "
            f"(sizes={sizes[:5]}{'...' if len(sizes) > 5 else ''})."
        )

    print(f"  ✓ validated: {path.name} -> N={len(adj)}, single connected component")


# =============================================================================
# Per-network pipeline
# =============================================================================

def process_network(slug: str, label: str, loader) -> NetworkStats:
    print(f"\n=== {label} ===")

    edges, nodes, node_col = loader()
    raw_n, raw_e = len(nodes), len(edges)

    G = build_graph(edges, nodes, node_col)
    self_loops = drop_self_loops(G)
    orphan_count = count_orphans(G, nodes, node_col)
    lat_lon_missing, lat_lon_bad = check_lat_lon_sanity(G)

    cleaned_n, cleaned_e = G.number_of_nodes(), G.number_of_edges()
    print(f"  raw:     N={raw_n:>7,}  E={raw_e:>7,}")
    print(f"  cleaned: N={cleaned_n:>7,}  E={cleaned_e:>7,}  (self-loops dropped: {self_loops})")
    if orphan_count:
        print(f"  WARNING: {orphan_count} node(s) have no lat/lon (edge-only orphans)")
    if lat_lon_missing:
        print(f"  WARNING: {lat_lon_missing} node(s) missing lat/lon")
    if lat_lon_bad:
        print(f"  WARNING: {lat_lon_bad} node(s) with out-of-range lat/lon")

    G_lcc = largest_connected_component(G)
    lcc_n, lcc_e = G_lcc.number_of_nodes(), G_lcc.number_of_edges()
    pct_dropped_n = 100.0 * (cleaned_n - lcc_n) / cleaned_n if cleaned_n else 0.0
    pct_dropped_e = 100.0 * (cleaned_e - lcc_e) / cleaned_e if cleaned_e else 0.0
    print(f"  LCC:     N={lcc_n:>7,} ({pct_dropped_n:.2f}% nodes dropped)  "
          f"E={lcc_e:>7,} ({pct_dropped_e:.2f}% edges dropped)")

    G_relabeled, mapping_df = relabel_contiguous(G_lcc)

    net_dir = OUTPUT_DIR / slug
    edgelist_path = net_dir / f"{slug}_edgelist.txt"
    mapping_path = net_dir / f"{slug}_node_mapping.csv"

    write_edgelist(G_relabeled, edgelist_path, label)
    write_node_mapping(mapping_df, mapping_path)

    written_n, written_e = G_relabeled.number_of_nodes(), G_relabeled.number_of_edges()
    validate_written_edgelist(edgelist_path, expected_n=lcc_n)

    return NetworkStats(
        label=label,
        raw_n=raw_n, raw_e=raw_e,
        cleaned_n=cleaned_n, cleaned_e=cleaned_e,
        self_loops_dropped=self_loops,
        orphan_count=orphan_count,
        lcc_n=lcc_n, lcc_e=lcc_e,
        written_n=written_n, written_e=written_e,
        lat_lon_missing=lat_lon_missing,
        lat_lon_out_of_range=lat_lon_bad,
    )


# =============================================================================
# Main
# =============================================================================

def print_summary(all_stats: list[NetworkStats]) -> None:
    print(f"\n{'='*100}")
    print("SUMMARY")
    print(f"{'='*100}")
    header = f"{'Network':<16}{'Raw N/E':>16}{'LCC N/E':>16}{'Written N/E':>16}{'Self-loops':>12}{'Orphans':>10}"
    print(header)
    print("-" * len(header))
    for s in all_stats:
        print(
            f"{s.label:<16}"
            f"{f'{s.raw_n:,}/{s.raw_e:,}':>16}"
            f"{f'{s.lcc_n:,}/{s.lcc_e:,}':>16}"
            f"{f'{s.written_n:,}/{s.written_e:,}':>16}"
            f"{s.self_loops_dropped:>12}"
            f"{s.orphan_count:>10}"
        )

    print("\nWarnings:")
    any_warning = False
    for s in all_stats:
        if s.orphan_count:
            print(f"  - {s.label}: {s.orphan_count} orphan node(s) with no lat/lon coordinates")
            any_warning = True
        if s.lat_lon_missing:
            print(f"  - {s.label}: {s.lat_lon_missing} node(s) missing lat/lon")
            any_warning = True
        if s.lat_lon_out_of_range:
            print(f"  - {s.label}: {s.lat_lon_out_of_range} node(s) with out-of-range lat/lon")
            any_warning = True
    if not any_warning:
        print("  none")
    print(f"{'='*100}\n")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_stats = [
        process_network(slug, label, loader)
        for slug, (label, loader) in LOADERS.items()
    ]

    print_summary(all_stats)


if __name__ == "__main__":
    main()
