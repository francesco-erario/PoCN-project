# SEAMLESS robustness output — EU Railways — Netherlands

Network: N=517, E=663
Protocols: random, degree, adap_degree, betweenness, adap_betweenness, seamless
Replicates (n_attacks): 100
SEAMLESS m-grid: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
Betweenness: engine=networkit, btw_update=1, btw_k=None

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
This table uses a single m-averaged column `seamless_mavg` (mean of the per-m `mean_removal_fraction`), because the m-grid is large (20 values). The authoritative per-m data is in node_scores.csv.

### RNG / reproducibility
Each (protocol, m, replicate) combination is seeded independently and
reproducibly from (master seed, protocol code, m, replicate). This makes the run
resumable and reproducible regardless of order. Protocol *distributions* are
unchanged vs. the original; only the specific random realizations differ.

### Resumability
On startup, already-completed combinations (both partial files present) are
skipped. Use `--force` to recompute everything from scratch.
