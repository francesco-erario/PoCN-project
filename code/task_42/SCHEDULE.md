# SEAMLESS robustness run — schedule and parameters (2026-09-03, 11:00 → 2026-09-04, 07:00)

Window: ~20h, one network at a time, biggest network (`eu_powergrid`) alone in the
last 7h (overnight, unattended). The other three fit in the preceding 13h.

Everything below is already written into **`run-config.json`** in this directory.
You just run each step with:

```bash
./run-seamless.sh --only <slug> --yes
```

(`--yes` skips the confirmation prompt; drop it if you want to eyeball the plan
first — `./run-seamless.sh --only <slug> --list` shows the resolved command
without running anything.)

---

## 1. Why the config has 7 entries, not 4

`seamless_robustness.py` takes a single `--btw-k` / `--btw-update` pair per
invocation, applied to **both** `betweenness` (static, one-shot) and
`adap_betweenness` (recomputed every `btw_update` removals). Static betweenness
is a *single* computation — cheap even exact, on every network. Adaptive
betweenness recomputes it up to `N/btw_update` times per replicate — on the
three big networks, exact is not just slow, it's off by 3–4 orders of
magnitude from anything achievable in this window (numbers below).

So each big network is split into two config entries pointing at the same
edge list:
- **`<net>`**: `random, degree, adap_degree, betweenness, seamless` at full
  `n_attacks=100`, `btw_k=null` (exact — trivial cost as a one-shot).
- **`<net>_adapbtw`**: `adap_betweenness` only, reduced `n_attacks`, approximate
  `btw_k`.

This also sidesteps a real trap: `--n-attacks` is global per invocation and
sizes *every* stochastic protocol in that run (`random`, `adap_degree`,
`seamless` too). If I'd crammed `adap_betweenness` into the same invocation
with a lower `n_attacks` to make it affordable, the final assembly pass would
have silently **truncated** `random`/`adap_degree`/`seamless` down to that same
low replicate count (it only aggregates combos matching the *current* run's
`--protocols`/`--n-attacks`, even if more replicates exist on disk from a
previous run). Splitting into a separate outdir avoids this entirely — you get
two folders per big network (`seamless_output/eu_railways` and
`.../eu_railways_adapbtw`), both labelled the same, easy to concatenate later.

`us_airlines` doesn't need a split: even fully exact, fully adaptive
betweenness (`btw_update=1`) costs 17 minutes there (see §3), so it runs as a
single 6-protocol invocation at `n_attacks=100`.

---

## 2. Network sizes (measured from the actual edge lists)

| network | N | E | notes |
|---|---:|---:|---|
| us_airlines | 488 | 12,971 | dense, max degree 258 — tiny but SEAMLESS's O(deg²) local scoring makes it the *most* expensive network for that one protocol despite the small N |
| eu_railways | 53,995 | 62,186 | sparse grid-like |
| us_powergrid | 71,856 | 87,692 | sparse grid-like |
| eu_powergrid | 130,880 | 149,283 | sparse grid-like, biggest by both N and E |

## 3. Cost model used for the estimates

All numbers below come from **direct timing measurements** on your machine
this session (order-generation and curve-build timings for every protocol on
all four networks, plus networkit betweenness timings at several `k`), not
from the script's built-in `estimate_cost_breakdown` (which is a *relative*
heuristic, not wall-clock).

Two calibrated scaling laws, both cross-validated against independent
measurements:
- **Exact betweenness** (networkit, one full computation): `t ≈ 4.03e-8 × N × E`
  seconds. Calibrated on the measured `eu_railways` exact run (135.2s); it
  *predicts* 786.5s on `eu_powergrid`, matching the previously-measured ≈787s
  (13.1 min) almost exactly — good confidence in this law.
- **Approximate betweenness** (`--btw-k k`, one full computation):
  `t ≈ 5.25e-8 × k × E` seconds. Calibrated across all three measured `k=256`
  points (eu_railways, us_powergrid, eu_powergrid); predicts eu_powergrid's
  `k=256` cost to within 3% of the measured value.
- **Adaptive betweenness over a full replicate** (recomputing every
  `btw_update` removals on a *shrinking* graph, not a fixed-size one):
  `T_exact ≈ (N / 3·btw_update) × t_exact_full` and
  `T_approx ≈ (N / 2·btw_update) × t_approx_full(k)`, derived by integrating
  the per-recompute cost over the shrinking node count (assumes edges shrink
  roughly proportionally to remaining nodes — reasonable for these sparse
  grids; likely a mild *overestimate* for degree/betweenness-driven removal,
  since high-degree nodes get removed first and edges tend to drop faster
  than nodes early on).

This model is why exact adaptive betweenness is flatly ruled out for the three
big networks: at the previous default (`btw_update=10`, `n_attacks=100`), it
would take **hundreds to thousands of hours** on each (e.g. eu_powergrid:
~9,500h). No `n_attacks`/`btw_update` combination gets exact adaptive
betweenness under ~3h on eu_railways with fewer than 10 replicates — it's not
close.

---

## 4. Per-network parameters and why

### `us_airlines` — single pass, everything exact

| param | value | where |
|---|---|---|
| protocols | all 6 | `networks.us_airlines` doesn't override — inherits global `protocols` |
| n_attacks | 100 | global default |
| btw_k | `null` (exact) | global default |
| btw_update | **1** (fully adaptive) | `networks.us_airlines.btw_update` |
| p_step_nodes | 1 | global default |

**Why btw_update=1 here specifically:** on this network a single exact
betweenness recompute costs 0.063s (N=488 is tiny), so 100 replicates × up to
488 recomputes each ≈ **17 minutes total**. There is no reason to approximate
or de-adapt on the one network where full adaptiveness is nearly free — this
is the most scientifically faithful setting the tool supports.
(`run_seamless.py` will print a generic WARNING about `btw_update=1` being
intractable — that warning is calibrated for the big networks, not this one;
it's safe to ignore here, confirmed by the 17-min estimate.)

**Estimated time: ~3.34h** (dominated by SEAMLESS: ~3.05h for the full
`m=1..20 × 100` replicate sweep, because of the O(deg²) local scoring on this
dense network; everything else is under a minute combined).

### `eu_railways` — main pass

| param | value | where |
|---|---|---|
| protocols | `random, degree, adap_degree, betweenness, seamless` | `networks.eu_railways.protocols` |
| n_attacks | 100 | inherited |
| btw_k | `null` (exact) | inherited — fine, static betweenness is a one-shot 135s cost regardless of N |
| p_step_nodes | **50** | `networks.eu_railways.p_step_nodes` |

**Estimated time: ~45 min.**

### `eu_railways_adapbtw` — adaptive betweenness only

| param | value | where |
|---|---|---|
| protocols | `adap_betweenness` | `networks.eu_railways_adapbtw.protocols` |
| n_attacks | **20** | `networks.eu_railways_adapbtw.n_attacks` |
| btw_k | **300** | `networks.eu_railways_adapbtw.btw_k` |
| btw_update | **107** (≈0.20% of N) | `networks.eu_railways_adapbtw.btw_update` |
| p_step_nodes | 50 | inherited from the entry |

**Estimated time: ~1.4h** (505 recomputes/replicate × 20 replicates).

### `us_powergrid` — main pass

Same structure as `eu_railways`: `protocols` restricted to the 5 cheap ones,
`p_step_nodes=70`. **Estimated time: ~1.05h.**

### `us_powergrid_adapbtw`

`n_attacks=20`, `btw_k=300`, `btw_update=143` (≈0.20% of N).
**Estimated time: ~1.94h** (503 recomputes/replicate).

### `eu_powergrid` — main pass (overnight, part 1)

Same structure, `p_step_nodes=130`. **Estimated time: ~2.04h.**

### `eu_powergrid_adapbtw` — overnight, part 2, the real compromise

| param | value | why |
|---|---|---|
| n_attacks | **15** | fewer replicates than the daytime networks — needed to keep the *unattended* overnight run safely inside its slot |
| btw_k | **300** | same approximation quality as the other two, for methodological consistency (only replicate count and adaptiveness vary with size/budget, not the estimator itself) |
| btw_update | **261** (≈0.20% of N) | see impact table below |

**Estimated time: ~2.48h** (502 recomputes/replicate × 15 replicates).

Exact is off the table here by ~4 orders of magnitude (a single exact
recompute alone costs ~787s; even at `btw_update=1000` and `n_attacks=5` the
model gives multi-hour totals for a handful of *very* non-adaptive
replicates — not a usable trade). `k=300` with 0.20%·N adaptiveness is the
compromise: still recomputing 502 times over the full dismantling of the
network (i.e. real adaptiveness, not a static approximation), at a cost that
leaves comfortable slack before 07:00.

---

## 5. How much `btw_update` actually matters (the trade-off you asked me to check)

Fixed `btw_k=300`, replicate count as chosen above, varying `btw_update` as a
% of N:

| btw_update (% of N) | eu_railways (n=20) | us_powergrid (n=20) | eu_powergrid (n=15) |
|---|---:|---:|---:|
| 0.05% | 5.7h | 7.9h | *(not tested — too slow)* |
| 0.10% | 2.8h | 3.9h | 5.0h |
| **0.20% (chosen)** | **1.4h** | **1.9h** | **2.5h** |
| 0.50% | 33 min | 47 min | 59 min |
| 1.00% | 17 min | 23 min | 30 min |

Cost is ~linear in `1/btw_update`, as expected (halving the interval roughly
doubles the number of recomputes). 0.20%·N is the point where all three still
fit comfortably in their slots with real slack left over (§6) while still
recomputing betweenness 500+ times over the run — i.e., genuinely adaptive,
not a coarse approximation of it.

**If eu_railways/us_powergrid are running ahead of schedule during the day**,
you can tighten to 0.10%·N (`btw_update=53` / `71`) — it costs the extra
1.4h/1.9h shown above but doesn't touch anything already computed
(resumable), so it's a safe thing to re-run later with `--force` on just that
one entry if you want a tighter result and have the hours to spare.
**Don't do this for `eu_powergrid_adapbtw`** — at 0.10%·N it alone would take
~5.0h, which on top of the 2.0h main pass blows through the entire 7h
overnight budget with no margin; 0.20% is the right call there, not just the
safe one.

---

## 6. Suggested timeline

| step | command | est. duration | cumulative |
|---|---|---:|---:|
| 11:00 | `./run-seamless.sh --only us_airlines --yes` | 3.3h | 14:20 |
| 14:20 | `./run-seamless.sh --only eu_railways --yes` | 0.8h | 15:09 |
| 15:09 | `./run-seamless.sh --only eu_railways_adapbtw --yes` | 1.4h | 16:33 |
| 16:33 | `./run-seamless.sh --only us_powergrid --yes` | 1.1h | 17:36 |
| 17:36 | `./run-seamless.sh --only us_powergrid_adapbtw --yes` | 1.9h | 19:33 |
| *(free time — ~4.5h slack before midnight)* | | | |
| 00:00 | `./run-seamless.sh --only eu_powergrid --yes` | 2.0h | 02:02 |
| 02:02 | `./run-seamless.sh --only eu_powergrid_adapbtw --yes` | 2.5h | 04:30 |
| | **total estimated compute** | **~13.0h** | **2.5h slack before 07:00** |

You don't have to hit these clock times exactly — if `us_airlines` finishes
early, just start the next step immediately. The two `eu_powergrid` steps are
the only ones that *should* wait for the overnight block, since they're the
ones running unattended with no chance to react if something goes long.

**Monitoring:** every run writes `logs/run.log` in its output directory with
a live per-combination ETA (`avg=... | ETA=...`), so you can check progress
without guessing. Everything is resumable — if you need to Ctrl+C or a run
gets interrupted, re-running the exact same command picks up where it left
off (partial results live under `partial/` and are only wiped with
`--force`).

---

## 7. Other parameters I evaluated and kept at defaults, with reasoning

- **`n_attacks=100`** for all non-`adap_betweenness` stochastic protocols: this
  is cheap everywhere (seconds to tens of seconds outside SEAMLESS) and gives
  a solid replicate count for mean±SE bands — no reason to shrink it.
- **`m` grid (`1..20`, step 1)**: fits comfortably inside every network's
  budget as computed above; no reason to trim the SEAMLESS sensing-budget
  sweep.
- **`p_step_nodes`**: raised from 1 to 50/70/130 (≈N/1000) on the three big
  networks. This is a pure output-size control — `seamless_robustness.py`
  always computes the *full* S1/S2 curve internally via the Union-Find engine
  regardless of this value (see the script's own docstring, point 1 of the
  changelog); it only decides which rows get written to `raw.csv` and fed
  into the AUC/summary computation. At ~1000 points across a monotonic,
  smooth percolation curve, trapezoidal-rule AUC error is negligible, while
  keeping `p_step_nodes=1` on eu_powergrid with ~2,200 total combinations
  would produce on the order of **hundreds of millions of raw.csv rows**
  (tens of GB) for no scientific benefit. `us_airlines` keeps `p_step_nodes=1`
  since N=488 makes this a non-issue there.
- **`--engine networkit`**: kept globally, per your earlier instruction —
  it's the only way any of the betweenness numbers above are achievable
  (networkx exact betweenness on eu_powergrid would not finish in this
  window at all).
- **`btw_k=300`** for the three adaptive-betweenness passes: consistent
  across networks so the *only* things that vary by network are replicate
  count and adaptiveness (both budget-driven), not the estimator's own
  precision — cleaner to justify in a write-up than picking a different `k`
  per network.
