#!/usr/bin/env python3
"""
SEAMLESS robustness analysis for a single undirected, unweighted network.

SEAMLESS:
    Locally Adaptive Multi-seed Edge-neighborhood Scoring & Sampling

===============================================================================
CHANGELOG (vs. the original seamless_robustness.py)
===============================================================================
This is a performance/robustness rewrite of the original script. The scientific
removal-order *semantics* of every protocol are preserved; only the
implementation and the set of outputs changed. Summary of changes and why:

1. S1/S2 CURVE ENGINE (was O(N^2) per curve -> now near-linear).
   The original recomputed connected components with a full DFS at every
   checkpoint. It is replaced by the *offline reverse-deletion Union-Find*
   technique: the removal order is processed in reverse (insertions), starting
   from an empty disjoint-set structure (path compression + union by size), and
   the largest / second-largest component sizes are tracked after every
   insertion with a lazy-deletion max-heap. This yields S1(k), S2(k) for every
   k = 0..N in O((N+E) alpha(N) + N log N). The forward curve is obtained by
   reversing the sequence. `--p-step-nodes` is now an OUTPUT row-subsampling
   control only (the full curve is always computed cheaply, then rows are
   subsampled for raw.csv) -- it is no longer a computation shortcut.
   The old DFS-based code is kept as `*_reference` functions for validation.

2. ADAPTIVE DEGREE (was O(N^2) -> now O(N+E)).
   The original re-scanned all nodes for the max degree at every step. It is
   replaced by degree buckets with O(1) swap-remove sampling. The uniform
   tie-breaking distribution (pick uniformly at random among ALL nodes tied at
   the current maximum degree) is preserved exactly -- the bucket at the current
   max degree *is* the full tied set. The old scan is kept as
   `order_adaptive_degree_reference` for validation.

3. BETWEENNESS (kept as a required baseline, made tractable).
   `--btw-update` now defaults to 10 (was 1); at update_every=1 adaptive
   betweenness needs one recomputation per removal and is intractable on the
   large networks. New `--btw-k INT` (default None = exact) enables
   random-source-sampled approximate betweenness (the `k=` parameter), applied
   to both static and adaptive betweenness, turning O(V*E) into ~O(k*E) per
   recomputation. New `--engine {networkx,networkit}` (default networkit) routes
   betweenness through networkit (C++) for large-network speed, falling back to
   networkx automatically if networkit is unavailable. Betweenness is used only
   for ranking, so a global scale difference between libraries does not change
   the order. NOTE: because the default engine is now networkit, betweenness
   orders may differ from the original networkx implementation only where exact
   ties are resolved differently (rank correlation ~1.0 in validation); pass
   --engine networkx to reproduce the original exactly.

4. SEAMLESS SEED SAMPLING (removed a hidden O(N^2)).
   The original rebuilt `list(adj.keys())` every step (O(N) per step, O(N^2)
   total). Seed sampling now uses an O(1)-removal active-node array. The
   sampling distribution (m uniform distinct seeds from the residual graph) and
   the scoring are unchanged.

5. NEW OUTPUT: PER-NODE VULNERABILITY SCORES.
   For every generated removal order, each node's removal rank/fraction is
   recorded and aggregated over replicates into node_scores.csv (long) and
   node_scores_wide.csv (one row per node, one column per protocol).

6. OPERATIONAL ROBUSTNESS.
   Incremental per-combination writes to a `partial/` folder, resume-on-restart
   (skip already-completed combinations; `--force` recomputes everything),
   a timestamped log file (logs/run.log) with per-combination duration and a
   running ETA, and a startup estimate of total operation count with a
   per-protocol cost breakdown.

7. RNG SEEDING SCHEME (enables resumability).
   The original derived per-replicate seeds *sequentially* from the master
   seed, so a replicate's realization depended on run order. Each combination
   (protocol, m, replicate) now gets an independent, reproducible seed derived
   from (master seed, protocol, m, replicate) via numpy SeedSequence. This makes
   partial results resumable and reproducible regardless of run order. The
   distribution sampled by each protocol is unchanged; only the specific random
   realizations differ from the original (statistically equivalent Monte Carlo).

Input:
    Edge list with integer node labels starting from 1:
        u v
    The graph is interpreted as undirected and unweighted.
    Lines starting with # are ignored. Self-loops are ignored.

Dependencies:
    numpy, pandas, networkx  (networkit optional, only for --engine networkit)
"""

from __future__ import annotations

import argparse
import heapq
import json
import logging
import os
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import networkx as nx
import numpy as np
import pandas as pd


# Type alias for a lightweight adjacency representation.
Adjacency = Dict[int, "set[int]"]


# =============================================================================
# Configuration
# =============================================================================

@dataclass(frozen=True)
class RunConfig:
    """Container for run parameters saved into config.json."""

    edge_file: str
    label: str
    outdir: str
    seed: int
    n_attacks: int
    p_step_nodes: int
    m_min: int
    m_max: int
    m_step: int
    btw_update: int
    btw_k: Optional[int]
    engine: str
    force: bool
    protocols: List[str]
    n_nodes: int
    n_edges: int
    method_name: str = "SEAMLESS"
    method_full_name: str = "Locally Adaptive Multi-seed Edge-neighborhood Scoring & Sampling"


# =============================================================================
# Graph IO and adjacency utilities
# =============================================================================

def read_integer_edgelist(
    path: Path,
    include_missing_integer_nodes: bool = True,
    zero_indexed: bool = False,
) -> Adjacency:
    """
    Read an undirected, unweighted edge list with integer node labels.

    Parameters
    ----------
    path:
        Input file path.
    include_missing_integer_nodes:
        If True, all nodes from min to max observed node id are included.
        This is useful when isolated nodes are represented implicitly by labels.
        If False, only nodes appearing in at least one non-self-loop edge are included.
    zero_indexed:
        If True, node labels start from 0. If False, start from 1.
    """
    min_label = 0 if zero_indexed else 1

    edges: list[tuple[int, int]] = []
    nodes: set[int] = set()

    with path.open("r") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            parts = line.split()
            if len(parts) < 2:
                raise ValueError(f"Malformed edge-list line {line_no}: {line!r}")

            try:
                u = int(parts[0])
                v = int(parts[1])
            except ValueError as exc:
                raise ValueError(f"Node labels must be integers. Bad line {line_no}: {line!r}") from exc

            if u < min_label or v < min_label:
                raise ValueError(f"Node labels must be >= {min_label}. Bad line {line_no}: {line!r}")

            nodes.add(u)
            nodes.add(v)

            # Ignore self-loops for robustness analysis.
            if u != v:
                edges.append((u, v))

    if not nodes:
        raise ValueError("No nodes found in edge list.")

    if include_missing_integer_nodes:
        node_set = set(range(min_label, max(nodes) + 1))
    else:
        node_set = set(nodes)

    adj: Adjacency = {u: set() for u in node_set}

    for u, v in edges:
        adj[u].add(v)
        adj[v].add(u)

    return adj


def adjacency_to_networkx(adj: Adjacency) -> nx.Graph:
    """Convert adjacency dictionary to a NetworkX undirected graph."""
    G = nx.Graph()
    G.add_nodes_from(adj.keys())

    for u, neigh in adj.items():
        for v in neigh:
            if u < v:
                G.add_edge(u, v)

    return G


def copy_adjacency(adj: Adjacency) -> Adjacency:
    """Return a deep copy of the adjacency dictionary."""
    return {u: set(vs) for u, vs in adj.items()}


def remove_node_inplace(adj: Adjacency, node: int) -> None:
    """Remove a node from the adjacency dictionary in-place."""
    for neighbor in list(adj[node]):
        adj[neighbor].remove(node)
    del adj[node]


def edge_count(adj: Adjacency) -> int:
    """Return the number of undirected edges."""
    return sum(len(vs) for vs in adj.values()) // 2


# =============================================================================
# Component metrics -- REFERENCE (validation only, O(N^2) per curve)
# =============================================================================

def connected_component_sizes(adj: Adjacency) -> list[int]:
    """
    Compute connected component sizes in descending order (explicit DFS).

    Retained from the original implementation and used only by the reference
    curve builder for validation against the new Union-Find engine.
    """
    unseen = set(adj.keys())
    sizes: list[int] = []

    while unseen:
        start = unseen.pop()
        stack = [start]
        size = 1

        while stack:
            u = stack.pop()
            for v in adj[u]:
                if v in unseen:
                    unseen.remove(v)
                    stack.append(v)
                    size += 1

        sizes.append(size)

    sizes.sort(reverse=True)
    return sizes


def giant_and_second_component_fraction(adj: Adjacency, n_initial: int) -> tuple[float, float]:
    """Return S1/N and S2/N for the current residual graph (reference)."""
    if not adj:
        return 0.0, 0.0

    sizes = connected_component_sizes(adj)
    s1 = sizes[0] / n_initial
    s2 = sizes[1] / n_initial if len(sizes) > 1 else 0.0

    return s1, s2


def robustness_curve_reference(adj0: Adjacency, order: list[int], p_step_nodes: int) -> pd.DataFrame:
    """
    REFERENCE S1/S2 curve using the original DFS-based component computation.

    Used only for validation of the fast Union-Find engine.
    """
    n_initial = len(adj0)

    if len(order) != n_initial:
        raise AssertionError(f"Removal order has length {len(order)} but expected {n_initial}.")
    if len(set(order)) != n_initial:
        raise AssertionError("Removal order contains duplicate nodes.")

    adj = copy_adjacency(adj0)
    rows: list[dict] = []
    idx = 0

    for removed in range(0, n_initial + 1, p_step_nodes):
        while idx < removed:
            remove_node_inplace(adj, order[idx])
            idx += 1

        s1, s2 = giant_and_second_component_fraction(adj, n_initial)
        rows.append({"removed": removed, "p": removed / n_initial, "S1_over_N": s1, "S2_over_N": s2})

    if rows[-1]["removed"] != n_initial:
        while idx < n_initial:
            remove_node_inplace(adj, order[idx])
            idx += 1
        s1, s2 = giant_and_second_component_fraction(adj, n_initial)
        rows.append({"removed": n_initial, "p": 1.0, "S1_over_N": s1, "S2_over_N": s2})

    return pd.DataFrame(rows)


# =============================================================================
# Fast S1/S2 engine: offline reverse-deletion Union-Find
# =============================================================================

def s1s2_forward_sequence(adj0: Adjacency, order: list[int]) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute S1(k) and S2(k) (raw component sizes) for every forward removal
    count k = 0..N, using the offline reverse-deletion Union-Find technique.

    Method
    ------
    The removal order is processed in REVERSE (insertions). Starting from an
    empty disjoint-set structure over the N nodes, nodes are inserted one at a
    time in reverse-removal order; each inserted node is unioned with every
    already-inserted neighbor (from the ORIGINAL graph). After t insertions the
    structure represents exactly the induced subgraph on the t most-recently
    surviving nodes = the residual after removing the first (N-t) nodes.

    The largest / second-largest component sizes are tracked with a
    lazy-deletion max-heap of component sizes plus a `pending` counter of stale
    heap entries, giving the correct top-two of the size multiset in amortized
    O(log N) per insertion.

    Returns
    -------
    (s1_fwd, s2_fwd):
        Integer arrays of length N+1 where index k is the residual after
        removing the first k nodes of `order`. s1_fwd[0], s2_fwd[0] correspond
        to the full graph; s1_fwd[N] = s2_fwd[N] = 0 (empty graph).
    """
    nodes = list(adj0.keys())
    n = len(nodes)

    if len(order) != n:
        raise AssertionError(f"Removal order has length {len(order)} but expected {n}.")

    index = {node: i for i, node in enumerate(nodes)}

    # Neighbor lists in index space (original graph).
    nbrs: list[list[int]] = [[] for _ in range(n)]
    for node, i in index.items():
        nbrs[i] = [index[w] for w in adj0[node]]

    try:
        order_idx = [index[u] for u in order]
    except KeyError as exc:  # pragma: no cover - defensive
        raise AssertionError("Removal order contains a node not present in the graph.") from exc
    if len(set(order_idx)) != n:
        raise AssertionError("Removal order contains duplicate nodes.")

    rev = order_idx[::-1]

    parent = list(range(n))
    size = [0] * n           # component size, valid at roots (0 => not yet active)
    active = bytearray(n)

    heap: list[int] = []                    # max-heap of sizes via negation
    pending: dict[int, int] = {}            # size -> count of stale heap entries

    s1_at_t = np.zeros(n + 1, dtype=np.int64)
    s2_at_t = np.zeros(n + 1, dtype=np.int64)

    def find(x: int) -> int:
        root = x
        while parent[root] != root:
            root = parent[root]
        # Path compression.
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def clean_top() -> int:
        """Return the largest live size (skipping/removing stale entries)."""
        while heap:
            top = -heap[0]
            p = pending.get(top, 0)
            if p:
                pending[top] = p - 1
                heapq.heappop(heap)
            else:
                return top
        return 0

    for t in range(1, n + 1):
        u = rev[t - 1]
        active[u] = 1
        parent[u] = u
        size[u] = 1
        heapq.heappush(heap, -1)

        ru = u
        for w in nbrs[u]:
            if not active[w]:
                continue
            rw = find(w)
            ru = find(ru)
            if ru == rw:
                continue
            su, sw = size[ru], size[rw]
            if su < sw:
                ru, rw = rw, ru
                su, sw = sw, su
            # Merge rw into ru.
            parent[rw] = ru
            size[ru] = su + sw
            pending[su] = pending.get(su, 0) + 1
            pending[sw] = pending.get(sw, 0) + 1
            heapq.heappush(heap, -(su + sw))

        s1 = clean_top()
        if s1 == 0:
            continue
        # Temporarily remove one live copy of s1 to read the second largest.
        heapq.heappop(heap)
        s2 = clean_top()
        heapq.heappush(heap, -s1)

        s1_at_t[t] = s1
        s2_at_t[t] = s2

    # Reverse back to forward-removal order: k removed  <->  t = N - k inserted.
    s1_fwd = s1_at_t[::-1].copy()
    s2_fwd = s2_at_t[::-1].copy()
    return s1_fwd, s2_fwd


def robustness_curve(adj0: Adjacency, order: list[int], p_step_nodes: int) -> pd.DataFrame:
    """
    Compute S1/N and S2/N along a node-removal order (fast Union-Find engine).

    The full curve is computed cheaply for every k; `p_step_nodes` only controls
    which rows are emitted (output subsampling). Row selection matches the
    original: rows at removed = 0, p_step, 2*p_step, ..., plus the final p=1 row
    if it is not already included.
    """
    n_initial = len(adj0)
    s1_fwd, s2_fwd = s1s2_forward_sequence(adj0, order)

    ks = list(range(0, n_initial + 1, p_step_nodes))
    if ks[-1] != n_initial:
        ks.append(n_initial)

    inv_n = 1.0 / n_initial
    rows = [
        {
            "removed": k,
            "p": k * inv_n,
            "S1_over_N": float(s1_fwd[k]) * inv_n,
            "S2_over_N": float(s2_fwd[k]) * inv_n,
        }
        for k in ks
    ]
    return pd.DataFrame(rows)


# =============================================================================
# SEAMLESS local scoring
# =============================================================================

def edge_neighborhood_dissimilarity_score(adj: Adjacency, node: int) -> float:
    """
    Compute the SEAMLESS local edge-neighborhood dissimilarity score.

    For each incident edge (node, u), compare N(node)\\{u} and N(u)\\{node} with
    Jaccard dissimilarity 1 - |A ∩ B| / |A ∪ B|. The node score is the mean
    dissimilarity over incident edges, scaled by sqrt(degree).
    """
    neighbors = adj[node]
    degree = len(neighbors)

    if degree == 0:
        return 0.0

    total = 0.0
    for u in neighbors:
        a = neighbors - {u}
        b = adj[u] - {node}
        union = a | b
        if union:
            total += 1.0 - len(a & b) / len(union)

    return (total / degree) * (degree ** 0.5)


# =============================================================================
# Attack protocols
# =============================================================================

def order_random(adj0: Adjacency, rng: np.random.Generator) -> list[int]:
    """Uniform random node-removal order."""
    order = list(adj0.keys())
    rng.shuffle(order)
    return [int(v) for v in order]


def order_degree_static(adj0: Adjacency) -> list[int]:
    """Static degree attack. Ties resolved deterministically by node id."""
    return [int(v) for v in sorted(adj0.keys(), key=lambda v: (-len(adj0[v]), v))]


def order_adaptive_degree_reference(adj0: Adjacency, rng: np.random.Generator) -> list[int]:
    """
    REFERENCE adaptive degree attack (original O(N^2) linear max-scan).

    Retained only for validating the fast bucket-based implementation.
    """
    adj = copy_adjacency(adj0)
    order: list[int] = []

    while adj:
        max_degree = max(len(neigh) for neigh in adj.values())
        candidates = [v for v, neigh in adj.items() if len(neigh) == max_degree]
        selected = int(rng.choice(candidates))
        order.append(selected)
        remove_node_inplace(adj, selected)

    return order


def order_adaptive_degree(adj0: Adjacency, rng: np.random.Generator) -> list[int]:
    """
    Adaptive degree attack, O(N + E) via degree buckets with swap-remove.

    Degree is maintained incrementally after each removal. At every step the
    node is chosen uniformly at random among ALL nodes currently tied at the
    maximum degree -- identical tie-breaking distribution to the reference
    implementation. The bucket at the current maximum degree IS the full tied
    set, and swap-remove gives O(1) uniform sampling and O(1) degree updates.
    """
    neighbors = {u: list(vs) for u, vs in adj0.items()}
    deg = {u: len(vs) for u, vs in adj0.items()}
    n = len(deg)

    if n == 0:
        return []

    maxd = max(deg.values())

    # Bucket d -> list of nodes with current degree d; bpos gives each node's
    # index inside its bucket for O(1) swap-remove.
    bl: list[list[int]] = [[] for _ in range(maxd + 1)]
    bpos: dict[int, int] = {}
    for u, d in deg.items():
        bpos[u] = len(bl[d])
        bl[d].append(u)

    def bucket_remove(node: int, d: int) -> None:
        lst = bl[d]
        i = bpos[node]
        last = lst[-1]
        lst[i] = last
        bpos[last] = i
        lst.pop()

    def bucket_add(node: int, d: int) -> None:
        bpos[node] = len(bl[d])
        bl[d].append(node)

    removed: set[int] = set()
    order: list[int] = []
    maxdeg = maxd

    while len(order) < n:
        # Max degree is non-increasing (edges only disappear); walk the pointer
        # down past emptied buckets.
        while maxdeg > 0 and not bl[maxdeg]:
            maxdeg -= 1

        lst = bl[maxdeg]
        idx = int(rng.integers(len(lst)))   # uniform over the full tied set
        sel = lst[idx]

        bucket_remove(sel, maxdeg)
        removed.add(sel)
        order.append(sel)

        for w in neighbors[sel]:
            if w in removed:
                continue
            d = deg[w]
            bucket_remove(w, d)
            deg[w] = d - 1
            bucket_add(w, d - 1)

    return [int(x) for x in order]


# ----------------------------------------------------------------------------
# Betweenness (with --btw-k approximation and optional --engine networkit)
# ----------------------------------------------------------------------------

_NETWORKIT_WARNED = False


def _betweenness_networkit(adj: Adjacency, k: Optional[int], seed: int) -> Optional[Dict[int, float]]:
    """
    Betweenness via networkit (C++). Returns None if networkit is unavailable
    or errors, so the caller can fall back to networkx.

    Only used for ranking, so a constant scale difference vs. networkx does not
    affect the produced order.
    """
    global _NETWORKIT_WARNED
    try:
        import networkit as nk
    except Exception:
        if not _NETWORKIT_WARNED:
            logging.getLogger("seamless").warning(
                "networkit not available; falling back to networkx for betweenness."
            )
            _NETWORKIT_WARNED = True
        return None

    try:
        nodes = list(adj.keys())
        idx = {u: i for i, u in enumerate(nodes)}
        G = nk.Graph(len(nodes), weighted=False, directed=False)
        for u in nodes:
            iu = idx[u]
            for v in adj[u]:
                if u < v:
                    G.addEdge(iu, idx[v])

        if k is not None and k < len(nodes):
            nk.setSeed(int(seed) % (2 ** 31), True)
            bc = nk.centrality.EstimateBetweenness(G, int(k), False, True)
        else:
            bc = nk.centrality.Betweenness(G, normalized=False)
        bc.run()
        scores = bc.scores()
        return {nodes[i]: float(scores[i]) for i in range(len(nodes))}
    except Exception as exc:  # pragma: no cover - defensive fallback
        if not _NETWORKIT_WARNED:
            logging.getLogger("seamless").warning(
                "networkit betweenness failed (%s); falling back to networkx.", exc
            )
            _NETWORKIT_WARNED = True
        return None


def compute_betweenness(
    adj: Adjacency,
    engine: str,
    k: Optional[int],
    seed: int,
) -> Dict[int, float]:
    """
    Compute (unnormalized) betweenness centrality for all nodes.

    engine : "networkx" or "networkit". If "networkit" is requested but
             unavailable/failing, transparently falls back to networkx.
    k      : None => exact; otherwise random-source-sampled approximation.
    seed   : RNG seed for the sampled approximation (ignored when k is None).
    """
    if engine == "networkit":
        result = _betweenness_networkit(adj, k, seed)
        if result is not None:
            return result

    G = adjacency_to_networkx(adj)
    if k is not None and k < G.number_of_nodes():
        return nx.betweenness_centrality(G, normalized=False, k=int(k), seed=int(seed))
    return nx.betweenness_centrality(G, normalized=False)


def order_betweenness_static(
    adj0: Adjacency,
    engine: str = "networkx",
    k: Optional[int] = None,
    seed: int = 0,
) -> list[int]:
    """
    Static betweenness attack. Betweenness computed once on the initial graph;
    ties resolved deterministically by node id.

    Note: when --btw-k is set, static betweenness uses the sampled approximation
    (reproducible given the derived seed) and is therefore approximate but still
    a single deterministic run.
    """
    bc = compute_betweenness(adj0, engine, k, seed)
    return [int(v) for v in sorted(adj0.keys(), key=lambda v: (-bc.get(v, 0.0), v))]


def order_adaptive_betweenness(
    adj0: Adjacency,
    rng: np.random.Generator,
    update_every: int = 1,
    engine: str = "networkx",
    k: Optional[int] = None,
) -> list[int]:
    """
    Adaptive betweenness attack. Betweenness is recomputed every `update_every`
    removals. Random jitter breaks exact ties (original semantics preserved).
    """
    if update_every < 1:
        raise ValueError("update_every must be >= 1")

    adj = copy_adjacency(adj0)
    order: list[int] = []

    while adj:
        seed = int(rng.integers(0, 2 ** 31 - 1))
        bc = compute_betweenness(adj, engine, k, seed)

        jitter = {v: rng.random() for v in adj}
        ranking = sorted(adj.keys(), key=lambda v: (-bc.get(v, 0.0), jitter[v]))

        removed_in_batch = 0
        for v in ranking:
            if v not in adj:
                continue
            selected = int(v)
            order.append(selected)
            remove_node_inplace(adj, selected)
            removed_in_batch += 1
            if removed_in_batch >= update_every or not adj:
                break

    return order


def order_seamless(
    adj0: Adjacency,
    rng: np.random.Generator,
    sensing_budget_m: int,
) -> list[int]:
    """
    SEAMLESS attack order.

    At each step: (1) sample m seed nodes uniformly from the residual graph;
    (2) build the candidate set as the union of their neighbors; (3) score
    candidates by edge-neighborhood dissimilarity; (4) remove one maximally
    scoring candidate; (5) if all sampled seeds are isolated, remove one seed.

    Implementation note: seed sampling uses an O(1)-removal active-node array
    (`active` list + `pos` map) instead of rebuilding list(adj.keys()) each step.
    The sampling distribution and scoring are identical to the original.
    """
    if sensing_budget_m < 1:
        raise ValueError("sensing_budget_m must be >= 1")

    adj = copy_adjacency(adj0)

    # Active-node array with swap-remove for O(1) uniform sampling / deletion.
    active = list(adj.keys())
    pos = {node: i for i, node in enumerate(active)}

    def drop_active(node: int) -> None:
        i = pos[node]
        last = active[-1]
        active[i] = last
        pos[last] = i
        active.pop()
        del pos[node]

    order: list[int] = []

    while active:
        n_live = len(active)
        n_seeds = min(sensing_budget_m, n_live)
        seed_idx = rng.choice(n_live, size=n_seeds, replace=False)
        seeds = [active[int(i)] for i in seed_idx]

        candidate_set: set[int] = set()
        for seed in seeds:
            candidate_set.update(adj[seed])

        if candidate_set:
            best_score = -1.0
            best_candidates: list[int] = []
            for candidate in candidate_set:
                score = edge_neighborhood_dissimilarity_score(adj, candidate)
                if score > best_score:
                    best_score = score
                    best_candidates = [candidate]
                elif score == best_score:
                    best_candidates.append(candidate)
            selected = int(rng.choice(best_candidates))
        else:
            # All sampled seeds are isolated: remove one of them.
            selected = int(rng.choice(seeds))

        order.append(selected)
        remove_node_inplace(adj, selected)
        drop_active(selected)

    return order


# =============================================================================
# Metrics
# =============================================================================

def auc_from_curve(curve: pd.DataFrame, y_column: str) -> float:
    """Compute trapezoidal AUC for a curve column as a function of p."""
    ordered = curve.sort_values("p")
    return float(np.trapezoid(ordered[y_column].to_numpy(), ordered["p"].to_numpy()))


def threshold_crossing_p(curve: pd.DataFrame, threshold: float, y_column: str = "S1_over_N") -> float:
    """Estimate the first p at which y_column <= threshold (linear interp)."""
    ordered = curve.sort_values("p")
    x = ordered["p"].to_numpy()
    y = ordered[y_column].to_numpy()

    crossing = np.where(y <= threshold)[0]
    if len(crossing) == 0:
        return np.nan

    i = crossing[0]
    if i == 0:
        return float(x[0])

    x0, x1 = x[i - 1], x[i]
    y0, y1 = y[i - 1], y[i]
    if y1 == y0:
        return float(x1)

    return float(x0 + (threshold - y0) * (x1 - x0) / (y1 - y0))


def build_summary_tables(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build summary.csv, metrics.csv, and metrics_summary.csv from raw data."""
    summary = raw.groupby(
        ["label", "protocol", "m", "removed", "p"],
        dropna=False,
        as_index=False,
    ).agg(
        mean_S1_over_N=("S1_over_N", "mean"),
        sd_S1_over_N=("S1_over_N", "std"),
        sem_S1_over_N=("S1_over_N", lambda x: x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else 0.0),
        mean_S2_over_N=("S2_over_N", "mean"),
        sd_S2_over_N=("S2_over_N", "std"),
        sem_S2_over_N=("S2_over_N", lambda x: x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else 0.0),
        n=("S1_over_N", "size"),
    )

    metric_rows: list[dict] = []
    for (label, protocol, m, stochastic_id), group in raw.groupby(
        ["label", "protocol", "m", "stochastic_id"],
        dropna=False,
    ):
        metric_rows.append({
            "label": label,
            "protocol": protocol,
            "m": m,
            "stochastic_id": stochastic_id,
            "AUC_S1": auc_from_curve(group, "S1_over_N"),
            "AUC_S2": auc_from_curve(group, "S2_over_N"),
            "p_LCC_0.5": threshold_crossing_p(group, 0.5, "S1_over_N"),
            "p_LCC_0.25": threshold_crossing_p(group, 0.25, "S1_over_N"),
            "p_LCC_0.1": threshold_crossing_p(group, 0.1, "S1_over_N"),
            "p_LCC_0.05": threshold_crossing_p(group, 0.05, "S1_over_N"),
            "max_S2_over_N": float(group["S2_over_N"].max()),
            "p_at_max_S2": float(group.loc[group["S2_over_N"].idxmax(), "p"]),
        })

    metrics = pd.DataFrame(metric_rows)

    metrics_summary = metrics.groupby(
        ["label", "protocol", "m"],
        dropna=False,
        as_index=False,
    ).agg(
        mean_AUC_S1=("AUC_S1", "mean"),
        sd_AUC_S1=("AUC_S1", "std"),
        sem_AUC_S1=("AUC_S1", lambda x: x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else 0.0),
        mean_AUC_S2=("AUC_S2", "mean"),
        sd_AUC_S2=("AUC_S2", "std"),
        sem_AUC_S2=("AUC_S2", lambda x: x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else 0.0),
        mean_p_LCC_0_5=("p_LCC_0.5", "mean"),
        sd_p_LCC_0_5=("p_LCC_0.5", "std"),
        mean_p_LCC_0_25=("p_LCC_0.25", "mean"),
        sd_p_LCC_0_25=("p_LCC_0.25", "std"),
        mean_p_LCC_0_1=("p_LCC_0.1", "mean"),
        sd_p_LCC_0_1=("p_LCC_0.1", "std"),
        mean_p_LCC_0_05=("p_LCC_0.05", "mean"),
        sd_p_LCC_0_05=("p_LCC_0.05", "std"),
        mean_max_S2_over_N=("max_S2_over_N", "mean"),
        sd_max_S2_over_N=("max_S2_over_N", "std"),
        mean_p_at_max_S2=("p_at_max_S2", "mean"),
        sd_p_at_max_S2=("p_at_max_S2", "std"),
        n=("AUC_S1", "size"),
    )

    return summary, metrics, metrics_summary


# =============================================================================
# Combination bookkeeping (seeding, keys, dispatch)
# =============================================================================

# Stable integer codes per protocol for deterministic per-combination seeding.
PROTOCOL_CODES = {
    "random": 1,
    "degree": 2,
    "adap_degree": 3,
    "betweenness": 4,
    "adap_betweenness": 5,
    "seamless": 6,
}

# Protocols whose order is deterministic -> exactly one replicate.
DETERMINISTIC_PROTOCOLS = {"degree", "betweenness"}


@dataclass
class Combo:
    protocol: str
    m: Optional[int]
    stochastic_id: int

    @property
    def key(self) -> str:
        ms = "NA" if self.m is None else f"{self.m:03d}"
        return f"{self.protocol}__m{ms}__rep{self.stochastic_id:04d}"


def combo_rng(master_seed: int, combo: Combo) -> np.random.Generator:
    """Independent, reproducible generator per combination (resume-safe)."""
    # SeedSequence requires non-negative ints: encode m=None as 0, else m+1.
    m_code = 0 if combo.m is None else combo.m + 1
    ss = np.random.SeedSequence([int(master_seed), PROTOCOL_CODES[combo.protocol], m_code, combo.stochastic_id])
    return np.random.default_rng(ss)


def enumerate_combos(protocols: List[str], m_values: List[int], n_attacks: int) -> List[Combo]:
    """Full list of (protocol, m, replicate) combinations for this run."""
    combos: List[Combo] = []
    # Deterministic baselines (single replicate).
    if "degree" in protocols:
        combos.append(Combo("degree", None, 1))
    if "betweenness" in protocols:
        combos.append(Combo("betweenness", None, 1))
    # Stochastic baselines.
    for protocol in ("random", "adap_degree", "adap_betweenness"):
        if protocol in protocols:
            for sid in range(1, n_attacks + 1):
                combos.append(Combo(protocol, None, sid))
    # SEAMLESS m sweep.
    if "seamless" in protocols:
        for m in m_values:
            for sid in range(1, n_attacks + 1):
                combos.append(Combo("seamless", m, sid))
    return combos


def compute_order(combo: Combo, adj0: Adjacency, rng: np.random.Generator, args: argparse.Namespace) -> list[int]:
    """Dispatch to the right protocol and return a full removal order."""
    p = combo.protocol
    if p == "random":
        return order_random(adj0, rng)
    if p == "degree":
        return order_degree_static(adj0)
    if p == "adap_degree":
        return order_adaptive_degree(adj0, rng)
    if p == "betweenness":
        seed = int(rng.integers(0, 2 ** 31 - 1))
        return order_betweenness_static(adj0, args.engine, args.btw_k, seed)
    if p == "adap_betweenness":
        return order_adaptive_betweenness(adj0, rng, args.btw_update, args.engine, args.btw_k)
    if p == "seamless":
        return order_seamless(adj0, rng, combo.m)
    raise ValueError(f"Unknown protocol: {p}")


# =============================================================================
# Incremental partial IO
# =============================================================================

def partial_paths(partial_dir: Path, combo: Combo) -> tuple[Path, Path]:
    """Return (curve_csv_path, order_npy_path) for a combination."""
    return partial_dir / f"{combo.key}.csv", partial_dir / f"{combo.key}.order.npy"


def combo_is_done(partial_dir: Path, combo: Combo) -> bool:
    curve_path, order_path = partial_paths(partial_dir, combo)
    return curve_path.exists() and order_path.exists()


def write_partial(
    partial_dir: Path,
    combo: Combo,
    label: str,
    curve: pd.DataFrame,
    order: list[int],
) -> None:
    """Atomically write the curve rows and the full removal order for a combo."""
    curve_path, order_path = partial_paths(partial_dir, combo)

    out = curve.copy()
    out.insert(0, "stochastic_id", combo.stochastic_id)
    out.insert(0, "m", combo.m if combo.m is not None else np.nan)
    out.insert(0, "protocol", combo.protocol)
    out.insert(0, "label", label)

    tmp_curve = curve_path.with_suffix(".csv.tmp")
    out.to_csv(tmp_curve, index=False)
    os.replace(tmp_curve, curve_path)

    tmp_order = order_path.with_suffix(".npy.tmp")
    # Pass an explicit file handle so np.save does not re-append ".npy".
    with open(tmp_order, "wb") as fh:
        np.save(fh, np.asarray(order, dtype=np.int64))
    os.replace(tmp_order, order_path)


# =============================================================================
# Node vulnerability scores
# =============================================================================

def build_node_scores(
    partial_dir: Path,
    label: str,
    node_list: List[int],
    combos: List[Combo],
    m_values: List[int],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Aggregate per-node removal rank/fraction over replicates from partial order
    files. Returns (node_scores_long, node_scores_wide).

    Wide table m-handling for seamless: one column per m if the grid is small
    (<= 5 m values), otherwise a single m-averaged column `seamless_mavg`.
    (Documented in the output README.)
    """
    n = len(node_list)
    index = {node: i for i, node in enumerate(node_list)}
    inv_n = 1.0 / n

    # Accumulators keyed by (protocol, m).
    acc: dict[tuple[str, Optional[int]], dict[str, np.ndarray]] = {}

    def group_for(protocol: str, m: Optional[int]) -> dict[str, np.ndarray]:
        gkey = (protocol, m)
        if gkey not in acc:
            acc[gkey] = {
                "sum_rank": np.zeros(n, dtype=np.float64),
                "sumsq_rank": np.zeros(n, dtype=np.float64),
                "count": np.zeros(n, dtype=np.int64),
            }
        return acc[gkey]

    for combo in combos:
        _, order_path = partial_paths(partial_dir, combo)
        if not order_path.exists():
            continue
        order = np.load(order_path)
        # rank_of_node[index] = 1-based removal rank
        ranks = np.empty(n, dtype=np.float64)
        idxs = np.fromiter((index[int(node)] for node in order), dtype=np.int64, count=len(order))
        ranks[idxs] = np.arange(1, len(order) + 1, dtype=np.float64)

        g = group_for(combo.protocol, combo.m)
        g["sum_rank"] += ranks
        g["sumsq_rank"] += ranks * ranks
        g["count"] += 1

    long_rows: list[pd.DataFrame] = []
    for (protocol, m), g in acc.items():
        count = g["count"].astype(np.float64)
        mean_rank = g["sum_rank"] / count
        with np.errstate(invalid="ignore", divide="ignore"):
            var_rank = (g["sumsq_rank"] - g["sum_rank"] ** 2 / count) / (count - 1)
        sd_rank = np.sqrt(np.where(count > 1, var_rank, np.nan))
        sd_rank = np.where(count > 1, sd_rank, np.nan)

        mean_frac = mean_rank * inv_n
        sd_frac = sd_rank * inv_n

        df = pd.DataFrame({
            "label": label,
            "protocol": protocol,
            "m": m if m is not None else np.nan,
            "node": node_list,
            "mean_removal_rank": mean_rank,
            "sd_removal_rank": sd_rank,
            "mean_removal_fraction": mean_frac,
            "sd_removal_fraction": sd_frac,
            "n_replicates": g["count"],
        })
        long_rows.append(df)

    if long_rows:
        long_df = pd.concat(long_rows, ignore_index=True)
    else:
        long_df = pd.DataFrame(columns=[
            "label", "protocol", "m", "node", "mean_removal_rank", "sd_removal_rank",
            "mean_removal_fraction", "sd_removal_fraction", "n_replicates",
        ])

    long_df = long_df.sort_values(["protocol", "m", "node"], na_position="first").reset_index(drop=True)

    # ------- Wide table (one row per node, one column per protocol) -------
    wide = pd.DataFrame({"node": node_list})
    small_grid = len(m_values) <= 5

    for (protocol, m), g in sorted(acc.items(), key=lambda kv: (kv[0][0], -1 if kv[0][1] is None else kv[0][1])):
        count = g["count"].astype(np.float64)
        mean_frac = (g["sum_rank"] / count) * inv_n
        if protocol == "seamless":
            if small_grid:
                col = f"seamless_m{int(m):03d}"
                wide[col] = mean_frac
            # m-averaged column handled after the loop
        else:
            wide[protocol] = mean_frac

    if "seamless" in {p for p, _ in acc} and not small_grid:
        # m-averaged: average the per-m mean_removal_fraction across the m grid.
        seamless_cols = []
        for (protocol, m), g in acc.items():
            if protocol == "seamless":
                count = g["count"].astype(np.float64)
                seamless_cols.append((g["sum_rank"] / count) * inv_n)
        if seamless_cols:
            wide["seamless_mavg"] = np.mean(np.vstack(seamless_cols), axis=0)

    return long_df, wide


# =============================================================================
# Logging
# =============================================================================

def setup_logging(log_dir: Path) -> logging.Logger:
    """Configure a logger writing to both stdout and logs/run.log."""
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("seamless")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    fh = logging.FileHandler(log_dir / "run.log")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return logger


def format_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


# =============================================================================
# Cost estimation / reporting
# =============================================================================

def estimate_cost_breakdown(
    protocols: List[str],
    m_values: List[int],
    n_attacks: int,
    n_nodes: int,
    n_edges: int,
    btw_update: int = 10,
    btw_k: Optional[int] = None,
) -> tuple[int, List[tuple[str, int, float]]]:
    """
    Return (total_ops, breakdown) where breakdown is a list of
    (protocol, n_ops, relative_cost_weight) sorted by estimated dominance.

    The relative cost weight is a rough per-op cost heuristic (NOT wall clock):
      - curve engine cost ~ (N+E) applies to every op;
      - order-generation cost differs sharply per protocol;
      - betweenness cost reflects --btw-k (k*E vs V*E per recompute) and, for the
        adaptive variant, the number of recomputations ~ ceil(N / btw_update).
    It is only used to indicate which protocols dominate the run.
    """
    ne = n_nodes + n_edges
    curve_cost = ne  # every op builds one curve

    # Cost of a single betweenness recomputation: ~k*E (approx) or ~V*E (exact).
    src = btw_k if (btw_k is not None) else n_nodes
    one_betweenness = src * n_edges
    n_recomputes = -(-n_nodes // max(1, btw_update))  # ceil(N / btw_update)

    per_op_cost = {
        "random": ne + curve_cost,
        "degree": ne + curve_cost,
        "adap_degree": ne + curve_cost,
        "betweenness": one_betweenness + curve_cost,                     # one static recompute
        "adap_betweenness": n_recomputes * one_betweenness + curve_cost, # N/btw_update recomputes
        "seamless": 5 * ne + curve_cost,                                 # local scoring per step
    }

    n_ops = {
        "random": n_attacks if "random" in protocols else 0,
        "degree": 1 if "degree" in protocols else 0,
        "adap_degree": n_attacks if "adap_degree" in protocols else 0,
        "betweenness": 1 if "betweenness" in protocols else 0,
        "adap_betweenness": n_attacks if "adap_betweenness" in protocols else 0,
        "seamless": len(m_values) * n_attacks if "seamless" in protocols else 0,
    }

    total_ops = sum(n_ops.values())
    breakdown = []
    for p in protocols:
        ops = n_ops.get(p, 0)
        if ops == 0:
            continue
        weight = float(per_op_cost[p]) * ops
        breakdown.append((p, ops, weight))

    total_weight = sum(w for _, _, w in breakdown) or 1.0
    breakdown = [(p, ops, w / total_weight) for p, ops, w in breakdown]
    breakdown.sort(key=lambda t: t[2], reverse=True)
    return total_ops, breakdown


# =============================================================================
# Execution orchestration
# =============================================================================

def write_readme(outdir: Path, config: RunConfig, m_values: List[int]) -> None:
    """Document design choices in the output folder."""
    small_grid = len(m_values) <= 5
    if small_grid:
        seamless_wide = (
            f"one column per m value (`seamless_m{{m:03d}}`), because the m-grid is small "
            f"({len(m_values)} value(s): {m_values})."
        )
    else:
        seamless_wide = (
            f"a single m-averaged column `seamless_mavg` (mean of the per-m "
            f"`mean_removal_fraction`), because the m-grid is large "
            f"({len(m_values)} values). The authoritative per-m data is in node_scores.csv."
        )

    text = f"""# SEAMLESS robustness output — {config.label}

Network: N={config.n_nodes}, E={config.n_edges}
Protocols: {", ".join(config.protocols)}
Replicates (n_attacks): {config.n_attacks}
SEAMLESS m-grid: {m_values}
Betweenness: engine={config.engine}, btw_update={config.btw_update}, btw_k={config.btw_k}

## Files

- `config.json`         — full run configuration.
- `raw.csv`             — complete robustness curves (one row per replicate & sampled removal step).
- `summary.csv`         — mean/sd/sem of S1/N and S2/N over replicates.
- `metrics.csv`         — per-replicate AUC and threshold metrics.
- `metrics_summary.csv` — mean/sd/sem of metrics over replicates.
- `node_scores.csv`     — LONG per-node vulnerability scores (authoritative).
- `node_scores_wide.csv`— one row per node, one column per protocol (mean_removal_fraction).
- `logs/run.log`        — timestamped run log (per-combination duration + ETA).
- `partial/`            — incremental per-combination files (curve + removal order).
                          This directory is the live source of truth during a run;
                          raw.csv and the score tables are assembled from it at the end.

## Design choices

### S1/S2 curve engine
Computed via offline reverse-deletion Union-Find (near-linear), validated to
match the original DFS-based engine exactly for identical removal orders.
`--p-step-nodes` only subsamples output rows; it does not change the computation.

### `--p-step-nodes`
Output subsampling only. The full k=0..N curve is always computed; rows written
to raw.csv are at removed = 0, p_step, 2*p_step, ..., plus the final p=1 row.

### node_scores_wide.csv — SEAMLESS m dimension
This table uses {seamless_wide}

### RNG / reproducibility
Each (protocol, m, replicate) combination is seeded independently and
reproducibly from (master seed, protocol code, m, replicate). This makes the run
resumable and reproducible regardless of order. Protocol *distributions* are
unchanged vs. the original; only the specific random realizations differ.

### Resumability
On startup, already-completed combinations (both partial files present) are
skipped. Use `--force` to recompute everything from scratch.
"""
    (outdir / "README.md").write_text(text)


def run_analysis(args: argparse.Namespace) -> None:
    """Run the full robustness analysis with incremental writes and resume."""
    outdir: Path = args.outdir
    outdir.mkdir(parents=True, exist_ok=True)
    partial_dir = outdir / "partial"
    partial_dir.mkdir(parents=True, exist_ok=True)
    log_dir = outdir / "logs"

    logger = setup_logging(log_dir)

    adj0 = read_integer_edgelist(
        args.edge_file,
        include_missing_integer_nodes=not args.no_missing_integer_nodes,
        zero_indexed=args.zero_indexed,
    )
    node_list = sorted(adj0.keys())
    n_nodes = len(adj0)
    n_edges = edge_count(adj0)

    m_values = list(range(args.m_min, args.m_max + 1, args.m_step))

    config = RunConfig(
        edge_file=str(args.edge_file),
        label=args.label,
        outdir=str(args.outdir),
        seed=args.seed,
        n_attacks=args.n_attacks,
        p_step_nodes=args.p_step_nodes,
        m_min=args.m_min,
        m_max=args.m_max,
        m_step=args.m_step,
        btw_update=args.btw_update,
        btw_k=args.btw_k,
        engine=args.engine,
        force=args.force,
        protocols=args.protocols,
        n_nodes=n_nodes,
        n_edges=n_edges,
    )
    with (outdir / "config.json").open("w") as f:
        json.dump(asdict(config), f, indent=2)

    write_readme(outdir, config, m_values)

    # --force: wipe existing partial results.
    if args.force:
        for p in partial_dir.glob("*"):
            p.unlink()

    combos = enumerate_combos(args.protocols, m_values, args.n_attacks)
    total_ops = len(combos)

    est_total_ops, breakdown = estimate_cost_breakdown(
        args.protocols, m_values, args.n_attacks, n_nodes, n_edges,
        args.btw_update, args.btw_k,
    )

    logger.info("=" * 70)
    logger.info("SEAMLESS Robustness Analysis")
    logger.info("=" * 70)
    logger.info("Network: %s (N=%d, E=%d)", args.label, n_nodes, n_edges)
    logger.info("Protocols: %s", ", ".join(args.protocols))
    if "seamless" in args.protocols:
        logger.info("SEAMLESS m range: %d..%d step %d -> %d values",
                    args.m_min, args.m_max, args.m_step, len(m_values))
    logger.info("Stochastic replicates: %d", args.n_attacks)
    logger.info("Betweenness engine=%s btw_update=%d btw_k=%s",
                args.engine, args.btw_update, args.btw_k)
    logger.info("Total operations (protocol x m x replicate): %d", total_ops)
    logger.info("Estimated cost dominance (relative, rough heuristic):")
    for p, ops, frac in breakdown:
        logger.info("    %-18s ops=%-6d  ~%5.1f%% of estimated cost", p, ops, 100.0 * frac)
    logger.info("=" * 70)

    # Resume: figure out what is already done.
    done_flags = [combo_is_done(partial_dir, c) for c in combos]
    n_done_start = sum(done_flags)
    todo = [c for c, d in zip(combos, done_flags) if not d]
    if n_done_start:
        logger.info("Resuming: %d/%d combinations already complete, %d to compute.",
                    n_done_start, total_ops, len(todo))

    # Main compute loop.
    durations: list[float] = []
    for i, combo in enumerate(todo, start=1):
        rng = combo_rng(args.seed, combo)
        m_str = "-" if combo.m is None else str(combo.m)
        t0 = time.time()
        logger.info("[%d/%d] START %s (m=%s, rep=%d)",
                    i, len(todo), combo.protocol, m_str, combo.stochastic_id)

        order = compute_order(combo, adj0, rng, args)

        # Integrity check: order must be a permutation of the node set.
        if len(order) != n_nodes or len(set(order)) != n_nodes:
            raise AssertionError(
                f"Protocol {combo.protocol} produced an invalid removal order "
                f"(len={len(order)}, unique={len(set(order))}, expected N={n_nodes})."
            )

        curve = robustness_curve(adj0, order, args.p_step_nodes)
        write_partial(partial_dir, combo, args.label, curve, order)

        dt = time.time() - t0
        durations.append(dt)
        avg = sum(durations) / len(durations)
        remaining = len(todo) - i
        eta = remaining * avg
        logger.info("[%d/%d] DONE  %s (m=%s, rep=%d) in %s | avg=%s | ETA=%s",
                    i, len(todo), combo.protocol, m_str, combo.stochastic_id,
                    format_duration(dt), format_duration(avg), format_duration(eta))

    # -------------------- Final assembly pass --------------------
    logger.info("=" * 70)
    logger.info("Assembling final outputs from partial/ ...")

    curve_frames = []
    for combo in combos:
        curve_path, order_path = partial_paths(partial_dir, combo)
        if curve_path.exists():
            curve_frames.append(pd.read_csv(curve_path))

    if not curve_frames:
        logger.warning("No completed combinations found; nothing to assemble.")
        return

    raw = pd.concat(curve_frames, ignore_index=True)
    raw = raw[["label", "protocol", "m", "stochastic_id", "removed", "p", "S1_over_N", "S2_over_N"]]
    raw = raw.sort_values(["protocol", "m", "stochastic_id", "removed"], na_position="first").reset_index(drop=True)

    summary, metrics, metrics_summary = build_summary_tables(raw)

    node_long, node_wide = build_node_scores(
        partial_dir, args.label, node_list, combos, m_values
    )

    raw.to_csv(outdir / "raw.csv", index=False)
    summary.to_csv(outdir / "summary.csv", index=False)
    metrics.to_csv(outdir / "metrics.csv", index=False)
    metrics_summary.to_csv(outdir / "metrics_summary.csv", index=False)
    node_long.to_csv(outdir / "node_scores.csv", index=False)
    node_wide.to_csv(outdir / "node_scores_wide.csv", index=False)

    logger.info("=" * 70)
    logger.info("ANALYSIS COMPLETE")
    logger.info("Output directory: %s", outdir)
    logger.info("Files: config.json, raw.csv, summary.csv, metrics.csv, metrics_summary.csv, "
                "node_scores.csv, node_scores_wide.csv, README.md, logs/run.log, partial/")
    logger.info("Raw rows: %d | node_scores rows: %d", len(raw), len(node_long))
    logger.info("=" * 70)


# =============================================================================
# CLI
# =============================================================================

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SEAMLESS robustness analysis on a single undirected, unweighted edge-list network."
    )

    parser.add_argument("--edge-file", required=True, type=Path,
                        help="Input edge list with integer node labels starting from 1. Format: u v per line.")
    parser.add_argument("--label", required=True, type=str,
                        help="Required network label written to every output row.")
    parser.add_argument("--outdir", required=True, type=Path, help="Output directory.")

    parser.add_argument("--seed", type=int, default=12345, help="Master random seed. Default: 12345.")
    parser.add_argument("--n-attacks", type=int, default=100,
                        help="Number of stochastic replicates (random, adap_degree, adap_betweenness, "
                             "and every SEAMLESS m value). Static degree/betweenness run once. Default: 100.")
    parser.add_argument("--p-step-nodes", type=int, default=1,
                        help="OUTPUT row subsampling for raw.csv, in removed nodes. The full curve is always "
                             "computed; this only controls which rows are written. Default: 1 (every step).")

    parser.add_argument("--m-min", type=int, default=1, help="Minimum SEAMLESS sensing budget m. Default: 1.")
    parser.add_argument("--m-max", type=int, default=20,
                        help="Maximum SEAMLESS sensing budget m, inclusive. Default: 20.")
    parser.add_argument("--m-step", type=int, default=1, help="Step size for SEAMLESS sensing budget m. Default: 1.")

    parser.add_argument("--btw-update", type=int, default=10,
                        help="Adaptive betweenness recomputation interval (number of removals between "
                             "recomputations). 1 = recompute after every removal (fully adaptive, most "
                             "expensive); larger values reduce cost by roughly that factor at the price of "
                             "less adaptiveness. Default: 10. NOTE: on the large networks even this is heavy "
                             "at update_every=1; consider a larger value (e.g. 50-100) and/or fewer replicates.")
    parser.add_argument("--btw-k", type=int, default=None,
                        help="If set, use random-source-sampled APPROXIMATE betweenness with this many source "
                             "samples (the `k=` parameter), applied to both static and adaptive betweenness. "
                             "Turns O(V*E) into ~O(k*E) per recomputation. Default: None (exact).")
    parser.add_argument("--engine", choices=["networkx", "networkit"], default="networkit",
                        help="Backend for betweenness computations. 'networkit' (C++) is much faster on large "
                             "networks and is the default; it falls back to networkx automatically if networkit "
                             "is unavailable. Use 'networkx' to reproduce the original library's exact "
                             "betweenness values/tie-order. Default: networkit.")
    parser.add_argument("--force", action="store_true",
                        help="Ignore existing partial results and recompute every combination from scratch.")

    parser.add_argument("--protocols", nargs="+",
                        default=["random", "degree", "adap_degree", "betweenness", "adap_betweenness", "seamless"],
                        choices=["random", "degree", "adap_degree", "betweenness", "adap_betweenness", "seamless"],
                        help="Protocols to run. 'seamless' runs all m values in the m-grid. "
                             "Default: all six.")

    parser.add_argument("--no-missing-integer-nodes", action="store_true",
                        help="By default, nodes 1..max_id are included even if isolated/missing from edges. "
                             "Set this flag to include only nodes explicitly appearing in the edge list.")
    parser.add_argument("--zero-indexed", action="store_true",
                        help="Node labels start from 0 instead of 1.")

    args = parser.parse_args(argv)

    if args.n_attacks < 1:
        raise ValueError("--n-attacks must be >= 1.")
    if args.p_step_nodes < 1:
        raise ValueError("--p-step-nodes must be >= 1.")
    if args.m_min < 1:
        raise ValueError("--m-min must be >= 1.")
    if args.m_max < args.m_min:
        raise ValueError("--m-max must be >= --m-min.")
    if args.m_step < 1:
        raise ValueError("--m-step must be >= 1.")
    if args.btw_update < 1:
        raise ValueError("--btw-update must be >= 1.")
    if args.btw_k is not None and args.btw_k < 1:
        raise ValueError("--btw-k must be >= 1 when set.")

    return args


def main() -> None:
    args = parse_args()
    run_analysis(args)


if __name__ == "__main__":
    main()
