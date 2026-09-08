import os
import csv
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from quantum_google import build_google_matrix, classical_pagerank, quantum_pagerank
from topology_generators import directed_scale_free

plt.rcParams.update({
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "axes.labelsize": 13,
    "axes.titlesize": 15,
    "legend.fontsize": 12,
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
    "lines.linewidth": 1.8,
    "lines.markersize": 4,
})

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
FIG_DIR = os.path.join(ROOT, "data", "task_25", "figures", "damping_sweep")
CSV_DIR = os.path.join(ROOT, "data", "task_25", "damping_sweep")

ALPHA_REF = 0.85


def fidelity(p, q):
    return float(np.sum(np.sqrt(p * q)))


def trace_dist(p, q):
    return float(np.max(np.abs(p - q)))


def main():
    os.makedirs(FIG_DIR, exist_ok=True)
    os.makedirs(CSV_DIR, exist_ok=True)

    # same graph reused for every alpha value
    G = directed_scale_free(N=128, seed=0)

    # fix T once at the reference alpha, then reuse it for all alphas
    Gm_ref = build_google_matrix(G, alpha=ALPHA_REF)
    _, _, T_fixed = quantum_pagerank(Gm_ref)
    print(f"fixed T (from alpha'={ALPHA_REF} convergence run) = {T_fixed}")

    # reference vectors at alpha'=0.85, same fixed T
    cls_ref = classical_pagerank(Gm_ref)
    _, q_ref, _ = quantum_pagerank(Gm_ref, T=T_fixed)

    alphas = np.linspace(0.01, 0.98, 30)
    rows = []
    for a in alphas:
        Gm = build_google_matrix(G, alpha=a)
        cls = classical_pagerank(Gm)
        _, q_avg, _ = quantum_pagerank(Gm, T=T_fixed)
        rows.append({
            "alpha": a,
            "fidelity_quantum": fidelity(q_avg, q_ref),
            "fidelity_classical": fidelity(cls, cls_ref),
            "trace_dist_quantum": trace_dist(q_avg, q_ref),
            "trace_dist_classical": trace_dist(cls, cls_ref),
        })

    csv_path = os.path.join(CSV_DIR, "damping_sweep_results.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        cols = ["alpha", "fidelity_quantum", "fidelity_classical",
                "trace_dist_quantum", "trace_dist_classical"]
        w.writerow(cols)
        for r in rows:
            w.writerow([f"{r['alpha']:.6f}"] + [f"{r[c]:.10f}" for c in cols[1:]])

    a = np.array([r["alpha"] for r in rows])
    fq = np.array([r["fidelity_quantum"] for r in rows])
    fc = np.array([r["fidelity_classical"] for r in rows])
    dq = np.array([r["trace_dist_quantum"] for r in rows])
    dc = np.array([r["trace_dist_classical"] for r in rows])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.6))

    ax1.plot(a, fq, "s-", color="#d62728", label="quantum")
    ax1.plot(a, fc, "o-", color="#1f77b4", label="classical")
    ax1.axvline(ALPHA_REF, color="gray", ls="--", lw=1.2,
                label=r"reference $\alpha'=0.85$")
    ax1.set_xlabel(r"damping parameter $\alpha$")
    ax1.set_ylabel(r"fidelity $f(\alpha, \alpha')$")
    ax1.set_title("(a) Bhattacharyya fidelity")
    ax1.legend()

    ax2.plot(a, dq, "s-", color="#d62728", label="quantum")
    ax2.plot(a, dc, "o-", color="#1f77b4",
             label="classical (extension by analogy)")
    ax2.axvline(ALPHA_REF, color="gray", ls="--", lw=1.2,
                label=r"reference $\alpha'=0.85$")
    ax2.set_xlabel(r"damping parameter $\alpha$")
    ax2.set_ylabel(r"trace-distance-equivalent $D$")
    ax2.set_title("(b) Trace-distance-equivalent")
    ax2.legend()

    fig.suptitle(r"Damping robustness, directed scale-free $N=128$ "
                 r"(reference $\alpha'=0.85$)", fontsize=15)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(os.path.join(FIG_DIR, "fidelity_and_trace_distance_vs_alpha.png"))
    plt.close(fig)

    print(f"fixed T = {T_fixed}, wrote {csv_path} and the 2-panel figure")
    print(f"fidelity range: quantum [{fq.min():.4f}, {fq.max():.4f}], "
          f"classical [{fc.min():.4f}, {fc.max():.4f}]")
    print(f"max trace dist: quantum {dq.max():.4f}, classical {dc.max():.4f}")


if __name__ == "__main__":
    main()
