#!/usr/bin/env python3
"""
Validation gate for the seamless_robustness.py performance rewrite.

Checks (in order):
  1. Fast S1/S2 Union-Find engine == reference DFS engine, EXACTLY (within float
     tolerance), on several small synthetic graphs and on the full US Airlines
     network, for multiple removal orders (random, degree, betweenness, seamless).
  2. Fast adaptive-degree engine reproduces the reference uniform tie-break
     DISTRIBUTION (empirical, over many replicates) on a small heavily-tied graph.
  3. (Informational) networkit vs networkx static-betweenness ordering agreement
     on US Airlines, if networkit is available.

Exit code 0 iff all mandatory checks (1 and 2) pass.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

import seamless_robustness as sr


TOL = 1e-9
FAILURES: list[str] = []


def small_graphs() -> dict[str, sr.Adjacency]:
    """A battery of small graphs exercising components, isolates, ties, bridges."""
    graphs: dict[str, sr.Adjacency] = {}

    def from_edges(n, edges):
        adj = {i: set() for i in range(1, n + 1)}
        for u, v in edges:
            adj[u].add(v)
            adj[v].add(u)
        return adj

    # Path
    graphs["path10"] = from_edges(10, [(i, i + 1) for i in range(1, 10)])
    # Cycle
    graphs["cycle10"] = from_edges(10, [(i, i % 10 + 1) for i in range(1, 11)])
    # Two disconnected triangles + isolated nodes
    graphs["two_tri_iso"] = from_edges(
        9, [(1, 2), (2, 3), (3, 1), (4, 5), (5, 6), (6, 4)]
    )  # nodes 7,8,9 isolated
    # Barbell: two cliques joined by a bridge
    graphs["barbell"] = from_edges(
        10,
        [(1, 2), (1, 3), (2, 3), (3, 4),  # left clique + bridge
         (4, 5), (5, 6), (4, 6),          # (bridge 3-4) right small
         (6, 7), (7, 8), (8, 9), (9, 10), (7, 10)],
    )
    # Star (one hub) -> huge degree ties among leaves
    graphs["star12"] = from_edges(12, [(1, j) for j in range(2, 13)])
    # Complete graph (all-tied degrees)
    K = 8
    graphs[f"complete{K}"] = from_edges(K, [(i, j) for i in range(1, K + 1) for j in range(i + 1, K + 1)])

    # Random Erdos-Renyi graphs of varying density (may be disconnected)
    rng = np.random.default_rng(7)
    for idx, (n, p) in enumerate([(20, 0.1), (30, 0.15), (40, 0.08), (25, 0.3)]):
        edges = []
        for u in range(1, n + 1):
            for v in range(u + 1, n + 1):
                if rng.random() < p:
                    edges.append((u, v))
        graphs[f"er_{n}_{idx}"] = from_edges(n, edges)

    return graphs


def orders_for(adj, seed=0):
    """Generate several removal orders per graph to stress the curve engine."""
    rng = np.random.default_rng(seed)
    orders = {}
    orders["random"] = sr.order_random(adj, np.random.default_rng(seed + 1))
    orders["degree_static"] = sr.order_degree_static(adj)
    orders["adap_degree"] = sr.order_adaptive_degree(adj, np.random.default_rng(seed + 2))
    orders["betweenness_static"] = sr.order_betweenness_static(adj)
    orders["seamless_m3"] = sr.order_seamless(adj, np.random.default_rng(seed + 3), 3)
    return orders


def check_curve_engine():
    print("\n[1] S1/S2 engine: fast Union-Find vs reference DFS")
    print("-" * 70)
    graphs = small_graphs()

    # Add full US Airlines.
    air = Path("seamless_input/us_airlines/us_airlines_edgelist.txt")
    if air.exists():
        graphs["us_airlines"] = sr.read_integer_edgelist(air)
    else:
        print("  WARNING: US Airlines edge list not found; skipping that case.")

    n_checked = 0
    max_abs_diff = 0.0
    for gname, adj in graphs.items():
        for p_step in (1, 3, 7):
            for oname, order in orders_for(adj, seed=hash(gname) % 1000).items():
                ref = sr.robustness_curve_reference(adj, order, p_step)
                fast = sr.robustness_curve(adj, order, p_step)

                # Same rows.
                if not np.array_equal(ref["removed"].to_numpy(), fast["removed"].to_numpy()):
                    FAILURES.append(f"curve rows mismatch: {gname}/{oname}/p{p_step}")
                    continue

                d1 = np.abs(ref["S1_over_N"].to_numpy() - fast["S1_over_N"].to_numpy()).max()
                d2 = np.abs(ref["S2_over_N"].to_numpy() - fast["S2_over_N"].to_numpy()).max()
                d = max(d1, d2)
                max_abs_diff = max(max_abs_diff, d)
                if d > TOL:
                    FAILURES.append(
                        f"S1/S2 mismatch {gname}/{oname}/p{p_step}: max|diff|={d:.3e}"
                    )
                n_checked += 1

    print(f"  checked {n_checked} (graph x order x p_step) cases")
    print(f"  max |S1/S2 difference| over ALL cases = {max_abs_diff:.3e} (tol={TOL:.0e})")
    ok = max_abs_diff <= TOL and not any(f.startswith(("curve", "S1")) for f in FAILURES)
    print(f"  RESULT: {'PASS' if ok else 'FAIL'}")
    return ok


def check_adap_degree_distribution():
    print("\n[2] Adaptive degree: fast bucket engine vs reference tie-break distribution")
    print("-" * 70)

    # A graph engineered to force large max-degree tie sets at multiple steps.
    def from_edges(n, edges):
        adj = {i: set() for i in range(1, n + 1)}
        for u, v in edges:
            adj[u].add(v)
            adj[v].add(u)
        return adj

    # Two disjoint 4-cliques + a 6-cycle: many equal-degree ties.
    edges = []
    for base in (0, 4):
        nodes = [base + 1, base + 2, base + 3, base + 4]
        for i in range(4):
            for j in range(i + 1, 4):
                edges.append((nodes[i], nodes[j]))
    cyc = [9, 10, 11, 12, 13, 14]
    for i in range(6):
        edges.append((cyc[i], cyc[(i + 1) % 6]))
    adj = from_edges(14, edges)
    N = len(adj)

    R = 40000

    def empirical(order_fn):
        # Track mean removal rank per node and the distribution of the first pick.
        rank_sum = np.zeros(N + 1)
        first_pick = np.zeros(N + 1)
        for r in range(R):
            rng = np.random.default_rng(10_000 + r)
            order = order_fn(adj, rng)
            for pos, node in enumerate(order):
                rank_sum[node] += pos + 1
            first_pick[order[0]] += 1
        return rank_sum / R, first_pick / R

    ref_rank, ref_first = empirical(sr.order_adaptive_degree_reference)
    fast_rank, fast_first = empirical(sr.order_adaptive_degree)

    rank_diff = np.abs(ref_rank - fast_rank).max()
    # Total variation distance of first-pick distribution.
    tv = 0.5 * np.abs(ref_first - fast_first).sum()

    # Monte Carlo tolerances for R replicates.
    rank_tol = 0.15 * N       # generous vs sqrt(N^2/R)-scale noise
    tv_tol = 0.02

    print(f"  graph N={N}, replicates each={R}")
    print(f"  max |mean-removal-rank difference| = {rank_diff:.4f} (tol {rank_tol:.3f})")
    print(f"  first-pick total-variation distance = {tv:.4f} (tol {tv_tol:.3f})")

    # Show first-pick distributions side by side for the top nodes.
    print("  first-pick probability by node (ref vs fast):")
    for node in range(1, N + 1):
        if ref_first[node] > 1e-4 or fast_first[node] > 1e-4:
            print(f"    node {node:2d}: ref={ref_first[node]:.4f}  fast={fast_first[node]:.4f}")

    ok = rank_diff <= rank_tol and tv <= tv_tol
    if not ok:
        FAILURES.append(f"adap_degree distribution mismatch: rank_diff={rank_diff}, tv={tv}")
    print(f"  RESULT: {'PASS' if ok else 'FAIL'}")
    return ok


def check_betweenness_engines():
    print("\n[3] (informational) networkit vs networkx static betweenness ordering")
    print("-" * 70)
    air = Path("seamless_input/us_airlines/us_airlines_edgelist.txt")
    if not air.exists():
        print("  US Airlines not found; skipping.")
        return True
    adj = sr.read_integer_edgelist(air)
    try:
        import networkit  # noqa: F401
    except Exception:
        print("  networkit not available; skipping.")
        return True

    order_nx = sr.order_betweenness_static(adj, engine="networkx")
    order_nk = sr.order_betweenness_static(adj, engine="networkit")

    same = sum(1 for a, b in zip(order_nx, order_nk) if a == b)
    # Rank correlation of removal positions.
    pos_nx = {v: i for i, v in enumerate(order_nx)}
    pos_nk = {v: i for i, v in enumerate(order_nk)}
    nodes = list(adj.keys())
    x = np.array([pos_nx[v] for v in nodes])
    y = np.array([pos_nk[v] for v in nodes])
    corr = float(np.corrcoef(x, y)[0, 1])
    print(f"  identical positions: {same}/{len(order_nx)}")
    print(f"  Pearson corr of removal ranks (nx vs nk): {corr:.4f}")
    print("  NOTE: differences are expected (library scale/tie-order); this is a")
    print("        separate accelerated baseline, not required to match bit-for-bit.")
    return True


def main():
    print("=" * 70)
    print("SEAMLESS rewrite validation gate")
    print("=" * 70)

    ok1 = check_curve_engine()
    ok2 = check_adap_degree_distribution()
    check_betweenness_engines()

    print("\n" + "=" * 70)
    if ok1 and ok2 and not FAILURES:
        print("VALIDATION PASSED (mandatory checks 1 and 2).")
        print("=" * 70)
        return 0
    print("VALIDATION FAILED.")
    for f in FAILURES:
        print("  - " + f)
    print("=" * 70)
    return 1


if __name__ == "__main__":
    sys.exit(main())
