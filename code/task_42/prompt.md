You are optimizing and extending `seamless_robustness.py`, a script that runs node-removal robustness/percolation simulations on graphs. It currently works correctly but does not scale to networks with tens/hundreds of thousands of nodes, and lacks per-node output. Read the entire current file before making any change.

CONTEXT ON THE BOTTLENECKS (confirmed by profiling the algorithm, not guessed):
1. `robustness_curve()` recomputes connected components via a full manual DFS (`connected_component_sizes`) at every checkpoint. With `--p-step-nodes 1` this is O(N) DFS calls per curve, each O(residual N+E) — O(N²) total per curve, and this is called once per (protocol, m, replicate) combination — thousands of times across the default grid.
2. `order_adaptive_degree` does an O(N) linear scan for the max-degree node at every removal step — O(N²) per replicate.
3. `order_adaptive_betweenness` recomputes exact `nx.betweenness_centrality` (O(V·E)) after every single removal by default — intractable for N > ~10⁴.

=== MANDATORY PERFORMANCE REWRITE ===

A) Replace the S1/S2 curve engine with the offline reverse-deletion Union-Find technique:
   - The full removal order is already computed before `robustness_curve` runs — this technique needs exactly that.
   - Process the order in REVERSE: start from an empty Union-Find (disjoint-set, path compression + union by size) over the N nodes. Insert nodes one at a time in reverse-removal order. When node u is inserted, union it with every already-inserted neighbor of u (from the ORIGINAL graph).
   - After t insertions, the structure represents exactly the induced subgraph on the t most-recently-surviving nodes = the residual graph after removing the first (N−t) nodes of the original order.
   - Track the largest and second-largest component size after every insertion (e.g. a size-frequency counter with two pointers that only move monotonically, or a lazy-deletion max-heap of component sizes — pick whichever you can implement correctly). This gives S1(k), S2(k) for EVERY k=0..N in O((N+E)·α(N)) — near-linear, not quadratic.
   - Reverse the resulting sequence back to forward-removal order.
   - `--p-step-nodes` should become an OUTPUT row-subsampling control only (compute the full curve cheaply, then subsample rows written to raw.csv) — not a computation shortcut anymore.
   - MANDATORY VALIDATION before trusting this on large networks: confirm bit-for-bit-equivalent (within float tolerance) S1_over_N/S2_over_N sequences vs. the OLD `connected_component_sizes`-based code, on a few small synthetic graphs and on the full US Airlines network (516 nodes, cheap enough to brute-force both ways). Do not proceed to the large networks until this passes exactly.

B) Replace `order_adaptive_degree`'s O(N) linear max-scan with an O(log N)-per-op structure (lazy-deletion max-heap or degree-bucket map) → O(N log N) total.
   CRITICAL correctness constraint: original semantics pick uniformly at random among ALL nodes currently tied at maximum degree. Your optimized version must reproduce this exact tie-breaking distribution — a heap alone only exposes the single max, not the full tied set. Validate the tie-set enumeration explicitly (e.g. compare empirical removal-order distributions on a small graph across many replicates, old vs new).

C) `order_adaptive_betweenness` must be kept (it's a required baseline per the project spec) but made tractable:
   - Keep `--btw-update` as-is (already exposed).
   - Add `--btw-k INT` (default None = exact) to enable networkx's random-source-sampled approximate betweenness (`k=` parameter), applied to both static and adaptive betweenness. Turns O(V·E) into ~O(k·E) per recomputation.
   - Optional: if `networkit` is available/installable in this environment and you judge it worthwhile, add an accelerated path behind `--engine {networkx,networkit}` for the betweenness-heavy protocols, falling back to networkx otherwise. Skip this if it adds too much dependency risk — the `--btw-k` approximation alone already makes things tractable.

=== NEW OUTPUT: PER-NODE VULNERABILITY SCORES ===

For every removal order generated (every protocol × replicate × m-value), also record for each node: its removal step (1-indexed rank) and removal fraction (rank/N). Aggregate over replicates, grouped by (label, protocol, m, node):
  mean_removal_rank, sd_removal_rank, mean_removal_fraction, sd_removal_fraction, n_replicates
(deterministic protocols — static degree, static betweenness — have 1 replicate; sd = NaN.)

Write to `node_scores.csv`: label, protocol, m, node, mean_removal_rank, sd_removal_rank, mean_removal_fraction, sd_removal_fraction, n_replicates.

Also produce `node_scores_wide.csv`: one row per node, one column per protocol (mean_removal_fraction). For `seamless`'s m-dimension in the wide table, use your judgment (one column per m if the grid stays small, a representative m, or an m-averaged summary) — document whichever choice you make in a README in the output folder. `node_scores.csv` (long format) remains the authoritative complete data regardless of this choice.

=== OPERATIONAL ROBUSTNESS (these runs go unattended overnight — losing partial results to a crash is unacceptable) ===

- INCREMENTAL WRITES: never hold everything in memory until one final write (current script does this). Write each completed (protocol, m, replicate) combination to disk immediately — append to raw.csv with header written once, or one small file per combination in a `partial/` folder merged at the end. At any point mid-run, the output directory must reflect everything computed so far.
- RESUMABILITY: on startup, detect already-completed combinations from existing partial output and skip them. Add `--force` to ignore checkpoints and recompute everything.
- LOGGING: timestamped log file (not just stdout) with start/end/duration per combination and a running ETA based on observed average time-per-unit.
- Keep `build_summary_tables` as a cheap final pass over the completed raw data — that part is fine as-is.

=== OUTPUT ORGANIZATION ===

results/<label>/
  config.json, raw.csv, summary.csv, metrics.csv, metrics_summary.csv,
  node_scores.csv, node_scores_wide.csv, README.md (documents your design choices),
  logs/run.log, partial/ (incremental files)

At the start of any run, print an estimated total operation count and which protocols dominate the estimated cost (extend the existing total_ops reporting).

=== CLI ===

Preserve every existing flag with identical name/semantics. Add `--btw-k`, optionally `--engine`, `--force`. Document new flags in --help. Add a short CHANGELOG comment at the top of the file summarizing what changed vs. the original and why (needed for the report — same removal-order semantics, purely an implementation/performance rewrite plus added output).

=== MANDATORY VALIDATION GATE BEFORE REAL RUNS ===

1. Confirm the new S1/S2 engine and new adap_degree engine match the original exactly on small test cases and on full US Airlines (old vs new).
2. Full end-to-end dry run on ALL FOUR networks with drastically reduced settings (e.g. `--n-attacks 2 --m-min 1 --m-max 3`) to confirm paths, output schema, and incremental-write/resume logic — before committing to the real overnight run.

After the dry run completes on all four networks, extrapolate estimated wall-clock time for the real settings (full --n-attacks, full --m-min/--m-max grid) per network, based on observed per-unit timings from the dry run and the total_ops count for the real config. Print this estimate clearly before I commit to launching the full run, broken down by protocol so I can see which ones dominate.

Report what you validated and any discrepancies found, however small. If any requirement above is ambiguous, or you'd be making a judgment call about scientific semantics (not just implementation), stop and ask me.