# SEAMLESS robustness run — schedule and parameters (2026-09-03, 13:30 → 2026-09-04, ~06:00)

Everything except the biggest network's adaptive-betweenness pass runs
**13:30 → ~23:50**; then **`eu_powergrid_adapbtw` runs overnight** from ~23:50,
finishing ~06:00 with an hour of margin before 07:00.

**This schedule assumes the parallelized `seamless_robustness.py`** (process-pool
over the stochastic protocols; §3a). The launcher passes `--n-workers 8` on every
run (global default), matched to this machine's 8 performance cores (M1 Pro:
8 performance + 2 efficiency).

Run each step with:

```bash
./run-seamless.sh --only <slug> --yes
```

(`--list` in place of `--yes` shows the resolved command without running it.)

---

## 1. Why the config has 7 entries, not 4

`seamless_robustness.py` takes a single `--btw-k` / `--btw-update` pair per
invocation, applied to **both** `betweenness` (static, one-shot) and
`adap_betweenness` (recomputed every `btw_update` removals), and `--n-attacks`
sizes *every* stochastic protocol in a run. So each big network is split into two
config entries pointing at the same edge list:
- **`<net>`**: `random, degree, adap_degree, betweenness, seamless` at
  `n_attacks=100`, `btw_k=null` (exact static betweenness — a cheap one-shot).
- **`<net>_adapbtw`**: `adap_betweenness` only, its own `n_attacks` / `btw_k` /
  `btw_update`, in a separate outdir.

The separate outdir also avoids a truncation trap: if `adap_betweenness` shared
an invocation with the cheap protocols at a different `n_attacks`, the final
assembly pass would silently truncate the cheap protocols' replicates to match.
Two folders per big network (e.g. `seamless_output/eu_railways` and
`.../eu_railways_adapbtw`), same label, easy to concatenate later.

`us_airlines` needs no split: N=488 makes even exact, fully-adaptive betweenness
(`btw_update=1`) cheap, so it runs all 6 protocols in one pass.

---

## 2. Network sizes (measured from the actual edge lists)

| network | N | E | notes |
|---|---:|---:|---|
| us_airlines | 488 | 12,971 | dense, max degree 258 — SEAMLESS's O(deg²) local scoring makes it the *most* expensive network for that one protocol despite the small N |
| eu_railways | 53,995 | 62,186 | sparse grid-like |
| us_powergrid | 71,856 | 87,692 | sparse grid-like |
| eu_powergrid | 130,880 | 149,283 | sparse grid-like, biggest by both N and E |

---

## 3a. What parallelism changed

`seamless_robustness.py` runs its compute loop in two phases:

- **Parallel phase (process pool, `--n-workers` workers):** `random`, `degree`,
  `adap_degree`, `seamless`. Every combination is independent (own RNG, own
  output files), distributed across worker processes. Each worker loads the graph
  once at start-up.
- **Sequential phase (parent process):** `betweenness` and `adap_betweenness`.
  With `--engine networkit` each betweenness call already uses every core via
  internal OpenMP threading, so parallelizing them across *processes* would
  oversubscribe the CPU. They run one at a time, each getting the whole machine.

**Correctness:** results are byte-identical regardless of worker count — verified
by running the full 6-protocol pipeline at 1 vs 4 workers (all 52 partial files
and 6 final CSVs hash-identical). Each combo's RNG derives from
`(seed, protocol, m, replicate)`, so worker count and completion order can't
affect output.

**Measured speedup:** `eu_railways` real protocol mix, 96 combinations,
**87s (1 worker) → 15s (8 workers) = ~5.8×** wall-clock. Effect on the cheap
bundles (SEAMLESS-dominated):

| run | before parallelism | after (8 workers) |
|---|---:|---:|
| us_airlines (all 6) | 3.34h | **~0.81h** |
| eu_railways main | 45min | **~9.7min** |
| us_powergrid main | 1.05h | **~14min** |
| eu_powergrid main | 2.04h | **~32min** |

The `adap_betweenness` passes are sequential and get **no** pool speedup — but
they turned out to be far cheaper than first modelled anyway (§3c).

## 3b. Parameters bumped on the adaptive-betweenness passes

With direct measurements (§3c) showing adaptive betweenness is cheap, all three
levers were pushed up from the original plan:

| entry | n_attacks | btw_k | btw_update | vs. original |
|---|---:|---:|---:|---|
| eu_railways_adapbtw | **100** | **450** | **38** (≈0.070%·N) | was 20 / 300 / 107 |
| us_powergrid_adapbtw | **100** | **450** | **50** (≈0.070%·N) | was 20 / 300 / 143 |
| eu_powergrid_adapbtw | **100** | **450** | **107** (≈0.082%·N) | was 15 / 300 / 261 |

- **`n_attacks=100`** — uniform with every other stochastic protocol; removes the
  replicate-count asymmetry entirely (all mean±SE bands at the same n).
- **`btw_k=450`** — the least-noisy approximate estimator in the sensible range;
  +50% source samples vs the earlier `k=300`.
- **`btw_update ≈ 0.07–0.08%·N`** — ~1200–1400 betweenness recomputations over the
  full dismantling of each network, i.e. betweenness re-ranked every ~40–110
  removals. About 3× finer adaptiveness than the earlier 0.20%·N — as close to
  *fully* adaptive as the overnight budget allows. (Exact/fully-adaptive is still
  off the table on these sizes; §3c.)

The daytime nets get the finest `btw_update` because two of them share a large
budget; `eu_powergrid` is slightly coarser so its single overnight pass finishes
before 07:00 (§6).

## 3c. Cost model — corrected by measurement

The cheap-bundle numbers come from direct per-protocol timings scaled by the
measured 5.8× parallel speedup. **Static** betweenness uses
`t ≈ 4.03e-8 × N × E` (exact, validated to 0.03% on eu_powergrid).

**Adaptive** betweenness was *measured directly* — because an earlier analytic
model (which assumed the graph shrinks proportionally as nodes are removed)
overestimated it by **~8–10×**. Under betweenness-targeted attack the network
**fragments early** (high-betweenness nodes are bridges), and betweenness on many
small components is far cheaper than on one big connected graph, so the later
recomputes cost almost nothing. Measured single-replicate cost at `k=400`,
`btw_update=0.20%·N`:

| network | measured per replicate |
|---|---:|
| eu_railways | **43 s** |
| us_powergrid | **54 s** |
| eu_powergrid | **81 s** |

These scale linearly and cleanly: cost ∝ `n_attacks`, ∝ `k` (source samples), and
∝ `1/btw_update` (recompute count). The schedule below applies exactly those
scalings to the measured points — no analytic model in the loop anymore. (Because
early recomputes on the still-connected graph dominate, and finer `btw_update`
samples every removal phase proportionally, the `1/btw_update` scaling is exact,
not an approximation.)

Exact adaptive betweenness stays out: a single *full-graph* exact recompute on
eu_railways is 135s, so even one fully-adaptive exact replicate would take hours
— `k`-approximation is mandatory on all three grids.

---

## 4. Per-network parameters

### `us_airlines` — single pass, everything exact

| param | value | why |
|---|---|---|
| protocols | all 6 | inherits global |
| n_attacks | 100 | global |
| btw_k | `null` (exact) | N=488 → exact is cheap |
| btw_update | **1** (fully adaptive) | per-network; ~free at this size, most faithful setting |
| n_workers | 8 | global |

**Estimated time: ~0.81h (~49 min)** — parallel SEAMLESS ~32 min + sequential
`btw_update=1` adaptive betweenness ~17 min. (The launcher prints a generic
`btw_update=1` WARNING calibrated for the big nets; ignore it here.)

### `eu_railways` — main pass (5 cheap protocols)

`n_attacks=100`, `btw_k=null` (static one-shot ~135s), `p_step_nodes=50`.
**~9.7 min** (parallel ~7.4 min + static betweenness ~2.3 min).

### `eu_railways_adapbtw`

`n_attacks=100`, `btw_k=450`, `btw_update=38`, `p_step_nodes=50`.
**~3.78h** (~1420 recomputes/replicate × 100 replicates).

### `us_powergrid` — main pass

`n_attacks=100`, `btw_k=null`, `p_step_nodes=70`. **~14 min**.

### `us_powergrid_adapbtw`

`n_attacks=100`, `btw_k=450`, `btw_update=50`, `p_step_nodes=70`. **~4.83h**
(~1437 recomputes/replicate × 100).

### `eu_powergrid` — main pass

`n_attacks=100`, `btw_k=null`, `p_step_nodes=130`. **~32 min**.

### `eu_powergrid_adapbtw` — the overnight run

`n_attacks=100`, `btw_k=450`, `btw_update=107`, `p_step_nodes=130`. **~6.17h**
(~1223 recomputes/replicate × 100). Starts ~23:51, finishes ~06:01 — the only
step running unattended, with ~1h margin before 07:00. `btw_update` is a touch
coarser than the daytime nets purely so this single pass fits the night; it's
still ~2.4× finer than the original plan.

---

## 5. If you want to rebalance

Everything scales linearly, so it's easy to trade. At the chosen `n=100`, `k=450`:

| entry | current (chosen) | 2× finer btw_update | coarser (0.15%·N) |
|---|---:|---:|---:|
| eu_railways_adapbtw (bu=38) | 3.78h | 7.6h (bu=19) | ~1.8h (bu=81) |
| us_powergrid_adapbtw (bu=50) | 4.83h | 9.7h (bu=25) | ~2.3h (bu=108) |
| eu_powergrid_adapbtw (bu=107) | 6.17h | 12.3h (bu=54) | ~2.9h (bu=196) |

To finish the overnight run *earlier*, coarsen `eu_powergrid_adapbtw`'s
`btw_update` (each +N/current step is roughly −6% time) or drop its `n_attacks`.
Anything re-run is resumable and only overwrites with `--force`.

**Don't** make `eu_powergrid_adapbtw` finer than `bu≈90` — below that its single
overnight pass risks running past 07:00.

---

## 6. Timeline (start 13:30)

| step | command | est. duration | finishes |
|---|---|---:|---:|
| 13:30 | `./run-seamless.sh --only us_airlines --yes` | ~49 min | 14:18 |
| 14:18 | `./run-seamless.sh --only eu_railways --yes` | ~10 min | 14:28 |
| 14:28 | `./run-seamless.sh --only eu_railways_adapbtw --yes` | ~3.78h | 18:15 |
| 18:15 | `./run-seamless.sh --only us_powergrid --yes` | ~14 min | 18:29 |
| 18:29 | `./run-seamless.sh --only us_powergrid_adapbtw --yes` | ~4.83h | 23:19 |
| 23:19 | `./run-seamless.sh --only eu_powergrid --yes` | ~32 min | 23:51 |
| **23:51** | `./run-seamless.sh --only eu_powergrid_adapbtw --yes` | ~6.17h | **06:01** ← overnight |
| | **total** | **~16.5h** | **~1h margin before 07:00** |

Clock times are guidance — each step is independent, so start the next whenever
the previous finishes. The only step meant to run unattended is
`eu_powergrid_adapbtw`; everything ahead of it is short enough for an
afternoon/evening. A few minutes of "assembly" (concatenating partials, building
summary/metrics/node-score tables) is added at the end of each run — seconds on
the small runs, up to ~5 min on the big-net mains, comfortably inside the margin.

**Monitoring:** each run writes `logs/run.log` with a live per-combination ETA and
an execution-plan line (`N sequential + M parallel combos; workers = 8`).
Everything is resumable — Ctrl+C or an interruption is fine; re-run the same
command to continue from the completed partials under `partial/`.

---

## 7. Other parameters kept at defaults

- **`n_workers=8`** (global): matches the 8 performance cores, leaving 2 efficiency
  cores for OS/logging/IO.
- **`n_attacks=100`** for the cheap stochastic protocols: parallelized, so cheap
  everywhere; solid mean±SE replicate count.
- **`m` grid (`1..20`, step 1)**: fits every budget.
- **`p_step_nodes`**: 50/70/130 (≈N/1000) on the big nets — pure output-size
  control; the full S1/S2 curve is always computed internally. `us_airlines`
  keeps `p_step_nodes=1` (N=488 makes it a non-issue).
- **`--engine networkit`**: the only way the betweenness numbers are achievable
  at all.
