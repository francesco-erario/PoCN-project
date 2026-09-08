import os
import numpy as np

from quantum_google import (
    build_google_matrix,
    classical_pagerank,
    initial_state,
    apply_U,
    quantum_pagerank,
)

ALPHA = 0.85
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "data", "task_25", "validation", "validation_report.txt")


def adjacency_from_edges(edges, N):

    A = np.zeros((N, N))
    for u, v in edges:
        A[u - 1, v - 1] = 1.0
    return A


def manual_power_iteration(G, tol=1e-14, max_iter=100000):
    N = G.shape[0]
    I = np.ones(N) / N
    for _ in range(max_iter):
        I_new = G @ I
        I_new /= I_new.sum()
        if np.max(np.abs(I_new - I)) < tol:
            return I_new
        I = I_new
    return I


# benchmark data transcribed from the 2012 paper

TREE_EDGES = [(2, 1), (3, 1), (4, 2), (5, 2), (6, 3), (7, 3)]
# classical PageRank per node (levels: 1 -> node 1; 2 -> 2,3; 3 -> 4,5,6,7)
TREE_CLASSICAL = {1: 0.37291, 2: 0.18012, 3: 0.18012,
                  4: 0.06671, 5: 0.06671, 6: 0.06671, 7: 0.06671}
# paper's average quantum PageRank per node (by level, Table 1)
TREE_QUANTUM = {1: 0.355905, 2: 0.151437, 3: 0.151437,
                4: 0.085305, 5: 0.085305, 6: 0.085305, 7: 0.085305}

GENERAL_EDGES = [(4, 6), (4, 3), (4, 5), (1, 6), (6, 3), (3, 1), (3, 2),
                 (3, 7), (1, 7), (1, 5), (1, 2), (7, 5), (5, 7)]
GENERAL_CLASSICAL = {1: 0.051019, 2: 0.061860, 3: 0.077924, 4: 0.028940,
                     5: 0.362387, 6: 0.047981, 7: 0.369889}
# paper's average quantum PageRank per node (Table 2)
GENERAL_QUANTUM = {1: 0.089076, 2: 0.126546, 3: 0.130587, 4: 0.076586,
                   5: 0.217691, 6: 0.131345, 7: 0.228169}


def check_normalization_unitarity(G, lines, tag):
    # returns (norm_ok, unit_ok)
    N = G.shape[0]
    sqrtG = np.sqrt(G)

    # check I_q(P_i, t) sums to 1 at every t of a short run
    Iq_series, _, _ = quantum_pagerank(G, T=300)
    sums = Iq_series.sum(axis=1)
    max_norm_err = np.max(np.abs(sums - 1.0))
    norm_ok = max_norm_err < 1e-8

    # check one step of U preserves the norm on random complex vectors
    rng = np.random.default_rng(0)
    max_unit_err = 0.0
    for _ in range(5):
        V = rng.standard_normal((N, N)) + 1j * rng.standard_normal((N, N))
        before = np.linalg.norm(V)
        after = np.linalg.norm(apply_U(V, sqrtG))
        max_unit_err = max(max_unit_err, abs(after - before))
    unit_ok = max_unit_err < 1e-8

    lines.append(f"  [{tag}] max |sum_i Iq(t) - 1| over t = {max_norm_err:.2e}"
                 f"  -> {'PASS' if norm_ok else 'FAIL'}")
    lines.append(f"  [{tag}] max unitarity norm error         = {max_unit_err:.2e}"
                 f"  -> {'PASS' if unit_ok else 'FAIL'}")
    return norm_ok, unit_ok


def run_benchmark(name, edges, N, classical_ref, quantum_ref, lines):
    lines.append("=" * 70)
    lines.append(f"Benchmark: {name}  ({N} nodes, {len(edges)} edges)")
    lines.append("=" * 70)

    A = adjacency_from_edges(edges, N)
    G = build_google_matrix(A, alpha=ALPHA)

    # classical exact-match check (4+ decimal places)
    I = classical_pagerank(G)
    I_manual = manual_power_iteration(G)
    # cross-check the two classical implementations agree
    cross = np.max(np.abs(I - I_manual))

    ref = np.array([classical_ref[i + 1] for i in range(N)])
    max_cls_err = np.max(np.abs(I - ref))
    classical_ok = max_cls_err < 1e-4

    lines.append("  in/out degree per node (node: in, out):")
    for i in range(N):
        indeg = int(A[:, i].sum())
        outdeg = int(A[i, :].sum())
        lines.append(f"    node {i + 1}: in={indeg}, out={outdeg}")
    lines.append("  classical PageRank (computed vs paper):")
    for i in range(N):
        lines.append(f"    node {i + 1}: {I[i]:.6f}  (paper {ref[i]:.6f})")
    lines.append(f"  max |classical - paper|      = {max_cls_err:.2e}"
                 f"  -> {'PASS' if classical_ok else 'FAIL'}")
    lines.append(f"  power-iter vs networkx-free cross-check = {cross:.2e}")
    lines.append(f"  sum of classical PageRank    = {I.sum():.10f}"
                 f"  -> {'PASS' if abs(I.sum() - 1) < 1e-8 else 'FAIL'}")

    Iq_series, Iq_avg, T_used = quantum_pagerank(G)
    variance = Iq_series.var(axis=0)
    qref = np.array([quantum_ref[i + 1] for i in range(N)])
    lines.append(f"  quantum run converged at T = {T_used}")
    lines.append("  average quantum PageRank / variance per node "
                 "(computed vs paper):")
    for i in range(N):
        lines.append(f"    node {i + 1}: <Iq>={Iq_avg[i]:.6f} (paper {qref[i]:.6f})"
                     f"  var={variance[i]:.7f}")

    max_q_err = np.max(np.abs(Iq_avg - qref))
    magnitude_ok = max_q_err < 1e-3

    paper_order = np.argsort(-qref)
    ours_along = Iq_avg[paper_order]
    tie_tol = 5e-3
    ordering_ok = np.all(np.diff(ours_along) <= tie_tol)
    lines.append(f"  paper quantum order (desc): "
                 f"{[int(x + 1) for x in paper_order]}")
    lines.append(f"  our quantum order  (desc): "
                 f"{[int(x + 1) for x in np.argsort(-Iq_avg)]}")
    lines.append(f"  max |quantum - paper|        = {max_q_err:.2e}"
                 f"  -> magnitude {'PASS' if magnitude_ok else 'FAIL'}")
    lines.append(f"  quantum ordering matches paper's quantum column -> "
                 f"{'PASS' if ordering_ok else 'FAIL'}")
    ordering_ok = ordering_ok and magnitude_ok

    norm_ok, unit_ok = check_normalization_unitarity(G, lines, name)

    lines.append("")
    return {
        "classical": classical_ok,
        "ordering": ordering_ok,
        "normalization": norm_ok and unit_ok,
    }


def main():
    lines = []
    lines.append("Task 25 validation report")
    lines.append(f"alpha = {ALPHA}")
    lines.append("")

    res_tree = run_benchmark("three-level tree (Fig. 7)",
                             TREE_EDGES, 7, TREE_CLASSICAL, TREE_QUANTUM, lines)
    res_gen = run_benchmark("general 7-node graph (Fig. 8)",
                            GENERAL_EDGES, 7, GENERAL_CLASSICAL,
                            GENERAL_QUANTUM, lines)

    lines.append("=" * 70)
    lines.append("SUMMARY (6 numeric checks)")
    lines.append("=" * 70)
    checks = [
        ("tree: classical exact match", res_tree["classical"]),
        ("tree: quantum ordering", res_tree["ordering"]),
        ("tree: normalization + unitarity", res_tree["normalization"]),
        ("general: classical exact match", res_gen["classical"]),
        ("general: quantum ordering", res_gen["ordering"]),
        ("general: normalization + unitarity", res_gen["normalization"]),
    ]
    all_ok = True
    for label, ok in checks:
        lines.append(f"  {'PASS' if ok else 'FAIL'}  {label}")
        all_ok = all_ok and ok
    lines.append("")
    lines.append(f"GATE: {'ALL PASS' if all_ok else 'FAILURE - do not proceed'}")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write("\n".join(lines) + "\n")

    print("\n".join(lines))
    print(f"\nReport written to {OUT}")
    return all_ok


if __name__ == "__main__":
    ok = main()
    raise SystemExit(0 if ok else 1)
