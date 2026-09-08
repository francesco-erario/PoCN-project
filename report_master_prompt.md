# MASTER PROMPT — PoCN final report (Task 25 + Task 42)

> How to use it: open a **new Claude session** with the folder
> `/Users/francesco/anaconda_projects/complex_networks/PoCN-project` connected and the
> `complex_networks` Claude project attached, then paste everything between the two
> `=====` lines below as your first message. The answer you get back is **not the report**:
> it is (A) a very detailed outline and (B) a numbered series of ready-to-paste prompts,
> one per report unit, which you then fire one at a time.

=====================================================================================

You are helping me, Francesco Erario, write the final report for the course *Physics of
Complex Networks: Structure and Dynamics* (SCQ2101383, Prof. Manlio De Domenico,
University of Padova, a.y. 2025/2026). The report covers two tasks:

* **Task 25 — Quantum Google Network** (theoretical task, difficulty score 0.6)
* **Task 42 — Adaptive vulnerability in transportation and power-grid networks with
  SEAMLESS** (data task, difficulty score 1.2)

Everything is already done: code is written, simulations have been run, figures and
result tables exist. What is missing is only the written report, in LaTeX.

**Your output in this first turn is NOT the report.** It is exactly two deliverables:

* **(A) A very detailed, unit-by-unit outline** of the whole report.
* **(B) A numbered series of self-contained prompts**, one per unit of the outline, that
  I will paste back to you one at a time, in order, so that the report gets written
  piece by piece while staying coherent.

Do not write any report prose in this first turn beyond what is needed to specify the
outline. Do not start writing `.tex` content yet.

---

## 1. Read and analyse the material first — deeply, not superficially

Before producing anything, read the material below. This is not optional background: the
outline must be built out of what is actually in these files, and every number that will
end up in the report must be traceable to one of them.

### 1.1 Working notes (useful, but NOT the primary source of truth)

```
notes_task25/00_summary.md
notes_task25/01_theoretical_framework.md
notes_task25/02_validation.md
notes_task25/03_topology_sweep.md
notes_task25/04_damping_robustness.md

notes_task42/00_summary.md
notes_task42/01_classical_vs_seamless.md
notes_task42/02_cross_network_comparison.md
notes_task42/03_residual_vulnerability.md
notes_task42/04_local_vs_global.md
notes_task42/05_cascade_simulation.md
notes_task42/notes.txt
```

**Important: these notes were themselves written by an AI assistant while it was running
the pipelines and generating the outputs.** They are a reliable record of *what was done*
(parameters, scope decisions, which script produced which file, which caveats were
knowingly accepted), and they state for almost every claim which file the number came
from. That is what they are for.

They are **not** the source of truth for anything else. In particular:

* **Never take wording, phrasing or lexicon from the notes.** They are AI-written, so
  their sentences carry exactly the register the report must avoid (Sec. 3). Use them for
  facts, then write from scratch.
* **Never quote a number straight out of a note.** Recompute it from the CSV or the
  result file the note points at, and if the two disagree, the data wins and you tell me.
* If anything does not add up, if a note is ambiguous, or if a note's interpretation of a
  result looks like a stretch, go back to the primary sources in this order: **the code,
  the figures and the raw output files, the two reference papers, the task brief
  (`project_42.md`) and the Moodle page.** Those five override the notes every time.
* The notes' own structure (bold "Finding:" labels, bullet lists, tables of numbers) is a
  notebook format, not a report format. Do not carry it over.

**Known stale numbers in the notes** (found by checking the run configurations, and proof
that the rule above is not theoretical). `notes_task42/notes.txt` says the
`adap_betweenness` runs used 20/20/15 replicates against 100 for the other protocols, and
`btw_k = 300`. The actual `config.json` and `metrics_summary.csv` of those runs say
`n_attacks = 100` for every protocol and `btw_k = 450`, with `btw_update` equal to 107
(eu\_powergrid), 38 (eu\_railways) and 50 (us\_powergrid). The runs were evidently redone
after the note was written. So the note's advice, that the adaptive-betweenness error
bands are wider because of a lower replicate count, is **no longer true** and must not be
repeated in the report. That particular file has since been corrected in place (the fixed
passages are marked `[CORRECTED 2026-09-08]`, and the original is kept as
`notes_task42/notes.txt.bak`), but treat it as a sample of the problem rather than the
whole of it. **Read every `config.json` yourself and build a single parameter table**
(per run: `n_attacks`, `m` grid, `p_step_nodes`, `btw_update`, `btw_k`, engine, protocols,
$N$, $E$) before writing a word about methods, and tell me every place where a note and a
config disagree.

### 1.2 Figures — analyse each one properly, this is the part usually done badly

There are 22 figures on disk. **Open and actually look at every one of them.** Staging a
PNG into the container and viewing it is required; reading only the filename or the note
that mentions it is not acceptable. In my experience an AI assistant glances at plots and
then writes vague sentences about them, while the plots are in fact the single most
important thing the report is built around, and the professor explicitly asks for clear
figures whose captions and numbers are readable on printed paper.

Task 25 (4 figures):

```
data/task_25/figures/topology_sweep/erdos_renyi_comparison.png
data/task_25/figures/topology_sweep/scale_free_comparison.png
data/task_25/figures/topology_sweep/hierarchical_comparison.png       (3 subplots, n=2,3,4)
data/task_25/figures/damping_sweep/fidelity_and_trace_distance_vs_alpha.png  (2 panels)
```

Task 42 (18 figures):

```
data/task_42/comparison_figures/<network>/seamless_vs_classical_scatter.png   (4 networks, 3 panels each)
data/task_42/comparison_figures/<network>/vulnerability_map_full.png          (4 networks)
data/task_42/comparison_figures/cross_network/robustness_overlay_seamless.png
data/task_42/comparison_figures/cross_network/robustness_overlay_adap_betweenness.png
data/task_42/comparison_figures/local_vs_global/<network>_<slug>_map.png       (3)
data/task_42/comparison_figures/local_vs_global/<network>_<slug>_rank_scatter.png (3)
data/task_42/comparison_figures/cascade/<network>_<slug>_cascade_comparison.png   (2)
```

with `<network>` in {eu_powergrid, eu_railways, us_airlines, us_powergrid} and
`<network>_<slug>` in {eu_powergrid_paris, us_powergrid_san_francisco, eu_railways_nld}.

For **each** figure produce a short *figure dossier* entry inside deliverable (A),
containing:

1. what is plotted on each axis, with units and the actual numerical range shown;
2. how many curves/panels/series there are and what distinguishes them (colour, line
   style, marker size encoding, colormap direction);
3. the two or three quantitative facts you can read *off the plot itself* (where a curve
   crosses a threshold, where the spread is largest, which point is an outlier), each
   cross-checked against the backing CSV;
4. whether the figure is legible at the size it would occupy in a two-column-free A4
   report at 12 pt — flag any figure whose tick labels or legend would be unreadable when
   scaled to `0.48\textwidth` or `\textwidth`;
5. the single sentence of report text that this figure is able to support, and one claim
   that it is *not* able to support.

Rank the 22 figures by how much they earn their place. The page budget (Sec. 2.1) will
not fit all of them in the main text: you must choose, and justify the choice.

### 1.3 Result tables (verify numbers here)

```
data/task_25/validation/validation_report.txt
data/task_25/topology_sweep/{erdos_renyi,scale_free,hierarchical}_results.csv
data/task_25/damping_sweep/damping_sweep_results.csv

data/task_42/comparison_tables/spearman_correlations.csv
data/task_42/comparison_tables/topk_overlap.csv
data/task_42/comparison_tables/category_fragmentation_summary.csv
data/task_42/comparison_tables/classical_descriptors_summary.csv
data/task_42/comparison_tables/residual_regression_summary.csv
data/task_42/comparison_tables/<network>_node_level_comparison.csv
data/task_42/comparison_tables/<network>_hidden_vulnerable_nodes.csv
data/task_42/comparison_tables/<network>_top_residual_nodes.csv
data/task_42/comparison_tables/<network>_<slug>_local_vs_global.csv
data/task_42/comparison_tables/<network>_<slug>_cascade_results.csv

data/task_42/seamless_output/<network>/{summary.csv,metrics_summary.csv,node_scores.csv,config.json}
data/task_42/seamless_output/<network>_adapbtw/...
data/task_42/seamless_output_local/<network>_<slug>/...
```

Some of these are large (there are ~16000 CSVs under `data/task_42`, most of them
per-replicate raw output). Use pandas on the user's machine rather than reading files by
eye, and never quote a number you have not recomputed or seen in a note that names its
source file.

### 1.4 Code (for the Methods paragraphs)

```
code/task_25/{quantum_google.py,validate_toy_graphs.py,topology_generators.py,
              run_topology_sweep.py,run_damping_sweep.py}
code/task_42/...   (SEAMLESS driver seamless_robustness.py and the analysis scripts:
                    find_hidden_vulnerabilities.py, residual_vulnerability.py,
                    extract_local_subnetwork.py, compare_local_vs_global.py,
                    cascade_simulation.py)
```

Read enough of them to describe honestly what was actually computed, including the
parameters (`--btw-k`, `--btw-update`, number of replicates per protocol, the `m`
sensing-budget grid, the convergence rule for `T`, `alpha = 0.85`).

### 1.5 Reference papers and course material

```
latex/reference_papers/srep00444.pdf   Paparo & Martin-Delgado, Sci. Rep. 2, 444 (2012)
latex/reference_papers/srep02773.pdf   Paparo, Muller, Comellas & Martin-Delgado, Sci. Rep. 3, 2773 (2013)
```

In the attached Claude project (`complex_networks`), also read:

* `PHYSICS OF COMPLEX NETWORKSSTRUCTURE AND DYNAMICS 20252026  SCQ2101383  moodleSTEM.pdf`
  — the professor's own instructions: expected output, repository structure, report
  length, supplementary-material rule, guidelines for theoretical and data tasks. **Follow
  what the professor asks, literally.**
* `project_42.md` — the Task 42 brief, including the 8 mandatory analysis points and the
  optional extensions. Every one of the 8 points must be visibly answered in the report.
* `claude/task_25_outline.md`, `claude/task_25_analysis.md`,
  `claude/task_25-quantum-google-analysis.md` — the Task 25 roadmap and scope decisions.
* `exam-notes/*.md` — my own notes on the course lectures. Read at least
  `01_Fundamentals_and_Representation.md`, `02_Network_Ensembles_and_Models.md`,
  `03_Correlations_Centrality_Communities.md`, `05_Diffusion_and_Random_Walks.md` and
  `08_Robustness_Percolation_Cascades.md`. Use the vocabulary, notation and framing of
  the course: I am a student who was taught these things in this specific way, and the
  report should read like it was written by someone who has just been taught them. For
  instance, robustness should be discussed in terms of the relative size of the largest
  connected component versus the removed fraction, percolation thresholds and targeted
  versus random attacks, exactly as in the lectures; PageRank should be framed as a
  random walk with teleportation.

---

## 2. Hard constraints

### 2.1 Page budget (binding)

From the Moodle page: *"a short report (max 1-2 pages per task * number of tasks + Refs
if any)"* and *"Each project task can have up to 5 pages of supplementary materials,
including plots, tables, etc."*

We adopt the conservative reading:

* **Main text: max 2 pages per task.** Task 25: 2 pages. Task 42: 2 pages. So 4 pages of
  main text, plus the title page, table of contents and bibliography.
* **Supplementary: up to 5 pages per task**, in an appendix at the end of the report,
  clearly labelled as supplementary and clearly not required to follow the main text.
* The main text must be self-contained: a reader who stops after page 4 must already have
  the full answer to both tasks.

Plan Task 42's appendix around the local-versus-global study and the Motter-Lai cascade
extension, and Task 25's appendix (shorter, or empty if not needed) around the validation
against the 2012 paper's benchmark graphs and the array-level implementation of `U`.

Budget the pages explicitly in the outline: give every unit a target length in
*number of lines of typeset text* at 12 pt with the template's 2.75 cm margins, and give
every figure a target width so the totals actually add up to the budget. Overshooting the
page limit is a failure, not a detail.

### 2.2 LaTeX (binding)

The template lives in `latex/`. **Do not restructure it.**

* **`latex/base/packages.tex` and `latex/base/style.tex`: strong preference for leaving
  them alone, but not an absolute prohibition.** Write the report against the preamble as
  it is. If something in there is genuinely broken, outdated, or a leftover from the
  template that actively gets in the way, you may change it, under these conditions: the
  change is the smallest one that fixes the problem; you list it in the outline (or, if
  discovered later, in the unit's output) with the symptom, the fix, and why no workaround
  in the section files was possible; and you wait for my approval before applying it.
  Never rewrite these files wholesale, never restyle them for taste, and never add a
  package just because it would be convenient.
* Known state of the preamble, so you plan around it rather than discovering it late:
  `booktabs` is *not* loaded, so tables use `\hline` and plain `tabular`;
  `caption`/`subcaption` are *not* loaded, but `subfigure` (the deprecated one) and
  `float` (for `[H]`) are; `siunitx` is not available; `amsmath`, `graphicx`, `natbib`
  (`\citep`/`\citet`, `plainnat`), `hyperref`, `multicol`, `wrapfig`, `enumitem`,
  `listings`, `mdframed`, `todonotes`, `lipsum` are available. Note that `hyperref` is
  loaded twice and `inputenc` three times, `subfigure` and `lipsum` are obsolete, and the
  `exercise`/`Answer` machinery and the `\startsolution` / `\solutionpoint` macros are
  leftovers from a problem-set template that this report does not use. Report anything of
  this kind that actually produces a warning or an error when you compile; leave the rest
  alone even though it is untidy.
* Task sections go in `latex/sections/`. **Task 25 goes in `task1.tex`, Task 42 goes in
  `task2.tex`.** `task3.tex` and `task4.tex` stay on disk but their `\input` lines are
  removed from `main.tex` (comment them out, do not delete the files).
* `latex/sections/front_page.tex`: replace the placeholder title with a real project
  title covering both tasks, and put `Erario, Francesco` where the template has
  `Surname, name`. Keep the layout, the logo and the `areas_of_physics.png` banner as they
  are.
* In each task file, the `\resp{...}` macro takes `Erario, Francesco` (individual
  project, single author, so I am the task leader of both). Delete the italic
  `Structure as...` instruction block that the template ships with, since the template
  itself says to remove it.
* **All figures used in the report must be copied into `latex/images/`** (keep the
  existing `logo.png` and `areas_of_physics.png` untouched). Give the copies short,
  descriptive, ASCII, lowercase filenames, and reference them as
  `\includegraphics[...]{images/<name>.png}`. Do not point `\includegraphics` at
  `../data/...`.
* `latex/bibliography.bib`: keep the three example entries as a formatting model but
  replace them with the real bibliography (the two Paparo papers, Szegedy FOCS 2004,
  Brin & Page or the original PageRank reference, Motter & Lai PRE 66, 065102 (2002),
  the SEAMLESS reference and dataset sources, Newman/Barrat-Barthelemy-Vespignani where
  the course material is cited). Use `\cite{}` keys that are readable, e.g.
  `paparo2012google`.
* The appendix must use the `appendix` package facilities already loaded, or simply a
  `\chapter{Supplementary material}` — whichever compiles cleanly with the existing
  preamble. Check it, do not assume.
* `style.tex` sets `\renewcommand{\contentsname}{Sommario}` and defines Italian
  environment names (`\theoname{Teorema}`, `\examname{Esempio}`, `\ExerciseName`,
  `\AnswerHeader` with "CAPITOLO" and "Problema"). The report is in English, so at least
  the table-of-contents title is a real defect. Propose the minimal fix in the outline
  (an override in `main.tex`, or a one-line change in `style.tex` if that is genuinely
  cleaner) and wait for my go-ahead; the environments that the report never uses can stay
  in Italian, they produce no visible output.

### 2.3 Characters (binding)

The `.tex` sources must be **pure ASCII**. No unicode dashes, no unicode arrows, no
unicode Greek letters or subscripts in text, no smart quotes, no non-breaking spaces, no
emoji. Write `Erd\H{o}s--R\'enyi`, `Mart\'in-Delgado`, `Szegedy`, `--` for ranges,
`` `` ``/`''` for quotes, and put all mathematics inside `$...$` or display environments.
Percent signs are `\%`, underscores in names are `\_`. Before delivering any `.tex`
fragment, grep it for non-ASCII bytes and report the result.

---

## 3. Writing style (binding, and the thing I care most about)

The report must read like a **physics master's student** wrote it: someone competent, who
has just been taught this material in this course, who is writing a serious short paper
but is not a professional academic. It must **not** read like AI-generated text.

**Model to imitate.** Read `latex/reference_papers/srep00444.pdf` (*Google in a Quantum
Network*) and mirror its register: plain declarative sentences, first person plural
("we introduce", "we have found", "we envision"), the physics stated directly without
decoration, equations woven into the prose rather than dumped in a list, honest hedging
("may break the classical hierarchy depending on the topology"), and paragraphs that
develop one argument each. That paper is close to how I write when I am writing well.

**Do:**

* Use "we" throughout, consistently, even though I am a single author — that is the
  convention of the papers being replicated.
* Vary sentence length a lot. Some sentences should be six words. Others should run for
  three lines because the argument genuinely needs a subordinate clause.
* Say *why* a choice was made, in the same sentence as the choice: "we used the
  Netherlands rather than Germany because exact adaptive betweenness on the 8232-node
  German component takes about 2.7 hours per replicate".
* Be concrete and numeric. Prefer "the largest component falls below half its size after
  2.1% of nodes are removed" to "the network fragments rapidly".
* Admit limitations in the running text, in a matter-of-fact tone, without a dedicated
  apologetic paragraph.
* Use the course's own vocabulary and notation ($S_1/N$, $p_c$, assortativity $r$,
  modularity $Q$, Spearman $\rho$).
* Let paragraph lengths be uneven. A three-line paragraph next to a nine-line one is
  normal writing.
* Occasionally start a sentence with "But", "So", or "This is" if that is the natural way
  to connect the thought.

**Do not:**

* No em dashes at all (use commas, parentheses, or a semicolon).
* No "delve", "leverage", "crucial", "pivotal", "robust insights", "underscores",
  "highlights the importance of", "it is worth noting that", "it is important to note",
  "sheds light on", "a testament to", "in the realm of", "landscape", "journey",
  "comprehensive", "nuanced", "seamlessly" (except as the literal name SEAMLESS).
* No "not only ... but also", no three-item lists used for rhythm ("faster, cheaper and
  more accurate"), no sentence of the form "X is not Y, it is Z".
* No bolded inline labels at the start of sentences in the main text ("**Finding:**",
  "**Key result:**"). The notes use that style because they are notes; the report must
  not.
* No bulleted lists in the main text except where a genuine enumeration is unavoidable
  (for example the list of the four networks). Results are argued in prose.
* No section-closing summary sentence that repeats what the section just said. No "In
  conclusion" at the end of every subsection.
* No hype ("remarkably", "strikingly", "dramatically") unless the number really is
  extreme, and then at most once per task.
* No perfectly parallel sentence structures across consecutive sentences, and no
  paragraph that opens with "Furthermore" / "Moreover" / "Additionally" more than once in
  the whole report.
* No filler transitions, no restating the task brief back at the reader, no
  meta-commentary about the report itself ("in this section we will...") beyond one
  functional sentence per chapter opening at most.

**Every single per-section prompt you generate in deliverable (B) must repeat a compact
version of this style clause**, because each section will be generated in a separate
turn and the constraint would otherwise be lost.

---

## 4. Content requirements

### 4.1 Task 25 (main text, 2 pages)

Must cover, at minimum: what the Google matrix and classical PageRank are, framed as a
random walk with teleportation; the Szegedy quantization (edge states $|\psi_j\rangle$,
$U = S(2\Pi - 1)$, instantaneous and time-averaged quantum PageRank, and why the ranking
uses the time average); the fact that the implementation is classical linear algebra at
the level of an $N \times N$ array rather than an $N^2 \times N^2$ operator; the
validation against the 2012 paper's two benchmark graphs; the three synthetic topology
classes and what each shows; and the damping-parameter robustness result. It must say
explicitly what was left out of scope (real-world networks, IPR/localization, the
coordinated-attack study) and why, since the Moodle FAQ makes scoping a graded skill.

Caveats that must be stated, not hidden: the hierarchical $n=3,4$ graphs are a principled
extrapolation of the paper's $n=1 \to 2$ construction rule and are not verified against a
published figure; the damping sweep uses $N=128$ for both curves whereas the paper's
Fig. 12 uses $N=128$ quantum and $N=256$ classical; the convergence rule for $T$ is ours,
neither paper fixes $T$.

### 4.2 Task 42 (main text, 2 pages)

The brief's **eight mandatory points must all be visibly answered**. Map them explicitly
in the outline: (1) network selection and preprocessing, (2) conversion to SEAMLESS
format, (3) adaptive vulnerability computation, (4) SEAMLESS versus classical centrality,
(5) hidden bridge dependencies and latent failure modes, (6) transportation versus power
grid fragmentation, (7) residual adaptive vulnerability, (8) does adaptive vulnerability
add information beyond static descriptors.

The polarity convention of `seamless_mavg` (mean removal fraction; **low = most
critical**) must be stated early and once, clearly, because every sign in the report
depends on it.

Caveats that must be stated: the `adap_betweenness` protocol has 15--20 replicates versus
100 for the others, so its error bands are wider partly by construction and partly
because the `btw_k = 300` sampling noise is folded into the same standard deviation;
`btw_update` is a bias, not a variance, and carries no error bar; the hidden-vulnerable
criterion uses "at or below the median" degree and betweenness because the median degree
of the spatial networks equals its mode, and a strict inequality empties the set; the
$R^2$ of the residual regression is an optimistic upper bound because the
community-grouping-mean term fits tiny communities almost exactly, which only strengthens
the conclusion; the cascade study uses a single tolerance $\alpha = 0.2$ and 5+5 triggers
per city and is illustrative.

Uncertainties should be reported where the data supports them: `summary.csv` and
`metrics_summary.csv` carry mean, sd and sem across replicates, and deterministic
protocols (degree, static betweenness) legitimately have `NaN` there because there is a
single removal order.

### 4.3 New figures and tables

You are expected to notice where the existing 22 figures do not cover what the argument
needs, and where a small table of numbers would carry an argument better than prose.
**Propose these in the outline as a dedicated numbered list — do not generate them yet.**
For each proposal state: what it shows, which existing CSV columns it is built from, why
the existing figures cannot do the job, the approximate cost, and where it would go
(main text or appendix). I will approve or reject them before anything is generated.

Once approved, the generating script goes in `code/task_25/` or `code/task_42/`
alongside the existing scripts (same style, standalone, runnable without a notebook), the
output PNG goes in `latex/images/`, and any new table of numbers is written both as a CSV
under the appropriate `data/task_XX/` folder and as a LaTeX `tabular`. Figures must be
saved at a size and font size that stay readable on printed A4, as the professor
explicitly requires.

Likely candidates worth considering, without committing to them: a compact LaTeX table
of the four networks' $N$, $E$, assortativity $r$, modularity $Q$ and number of
communities; a single-panel summary of the Spearman correlations across networks and
protocols; a robustness curve with the sem band drawn explicitly for one network, to show
the error treatment once; a small table of the Task 25 validation numbers against the
2012 paper's Table 1 and Table 2.

One of these is close to mandatory rather than optional: the Moodle page says that for a
data task the report is about *"the description of the data and possibly a visualization
of the corresponding network with some data analytics (degree distribution, mixing
patterns, community structure)"*. Mixing patterns and community structure are already
covered by `classical_descriptors_summary.csv` (assortativity $r$ and modularity $Q$ with
the number of Louvain communities), but **no degree-distribution figure exists**. Propose
one compact panel with the four degree distributions (log-log or log-binned, whichever the
data actually supports at $N$ from 488 to 130880) and treat it as a strong candidate for
the Task 42 main text.

### 4.4 Statement on the use of AI tools

The Moodle page allows AI assistance but requires it to be declared and cited, requires
that I can explain everything in the project as if I had produced it independently, and
warns that the professor expects to be able to tell AI-aided work apart. The report must
therefore contain a short, honest statement about how AI was used.

Place it as a short unnumbered block, about seven typeset lines, at the end of the main
text just before the bibliography. It belongs to neither task, so it must not eat into
either task's two-page budget. Set it in the same body font, not in a coloured box.

The text is fixed. Typeset it as follows, with no rewording, no softening and no
expansion, converting only what LaTeX requires:

> **Note on the use of AI tools.** As allowed by the course guidelines, I used an AI
> assistant (Anthropic's Claude) while working on this project. It helped me write and
> debug the analysis and plotting scripts under `code/`, and above all it helped me
> optimise the SEAMLESS pipeline so that the attack simulations could be run on the full
> networks, up to about $1.3\times10^5$ nodes, in a reasonable time. I also used it to
> work through the reference papers and to draft this report. What to run, what to leave
> out and what the results mean was decided by me, and every simplification I accepted is
> stated in the text. None of the numbers reported here were produced by the assistant:
> they all come from the output files under `data/`, and they can be reproduced by
> running the scripts under `code/`.

### 4.5 Compliance with what the professor actually asks

**This is the single most important requirement in this document.** What the professor
wrote in the project briefs and on the Moodle page is what the report is graded against,
and it takes priority over anything I have written here, over the working notes, and over
what would make a nicer paper.

So deliverable (A) must contain a **requirements trace table**. One row per requirement,
built by going through the Moodle page and `project_42.md` line by line and pulling out
every statement that constrains the report or the submission. Each row has: the
requirement quoted verbatim, the source (Moodle section, or the numbered point in
`project_42.md`), the unit ID of the outline that satisfies it, and a status of `covered`,
`partial` or `not covered`. Anything left `partial` or `not covered` gets one sentence
saying why. Build this table before finalising the outline, not after, and let it drive
what goes in and what gets cut: if a requirement and a nice-to-have compete for the same
half page, the requirement wins.

Requirements that are easy to miss, to get you started:

* **The report must say who was in charge of each task.** Individual project, so
  `\resp{Erario, Francesco}` in both task files.
* **Data task content.** Description of the data (source, what the nodes and edges are,
  $N$ and $E$, spatial embedding, the preprocessing that produced the SEAMLESS input),
  plus the data analytics the Moodle names: degree distribution, mixing patterns,
  community structure. Check that all three appear.
* **`project_42.md` expected output.** It explicitly lists *"visualizations of
  adaptive-vulnerability patterns on selected city maps"*. The city-scale maps are the
  `local_vs_global/<network>_<slug>_map.png` files (Paris, San Francisco, Netherlands).
  Since they answer an explicitly requested deliverable, **at least one of them goes in
  the Task 42 main text**, with a short paragraph; the full local-versus-global study
  belongs in the appendix, where it has room. See Sec. 4.6 for how the two scales are
  supposed to fit together.

### 4.6 How the global and the city-scale analyses fit together

The intended shape of Task 42 is this, and the outline should follow it unless the data
says otherwise:

* The eight mandatory points are answered on the **full networks**, and that is what
  carries the main text: they are what the brief actually grades.
* The **city-scale part** then does two jobs. It delivers the city-map visualisation the
  brief asks for, and it shows that the vulnerability ranking obtained by running SEAMLESS
  on an isolated city or country reproduces the ranking that the full-network run assigns
  to those same nodes (Spearman 0.958 to 0.977 on Paris, San Francisco and the
  Netherlands; zero, zero and one top-quartile-versus-bottom-quartile disagreement). The
  honest reading is that the adaptive vulnerability signal is largely local, so a
  well-chosen region can be ranked without paying for the full continental computation.
  The one disagreement, `NLD_1131` near the German border, is not noise: it is the
  systematic failure mode of local analysis, a node whose importance comes from structure
  that the national cut removes. Say both things, do not sell the agreement alone.
* **Be careful with a claim that is easy to get wrong here.** The SEAMLESS score itself is
  *not* computed more coarsely on the full networks than on the subnetworks: the
  configurations show the same `n_attacks = 100` and the same `m` grid from 1 to 20 in
  both cases. What differs is `p_step_nodes` (130 versus 1, which is the resolution at
  which the curve is sampled for the AUC, not the attack), and the adaptive-betweenness
  comparison protocol, which is approximated globally (`btw_k = 450` sampled sources,
  `btw_update` of 38 to 107 removals between recomputations) and exact locally
  (`btw_update = 1`, no `btw_k`). So the local-versus-global agreement is evidence about
  the **locality of the vulnerability signal**, and it is *not* by itself evidence that
  the global SEAMLESS computation is a good approximation of an exact one. Do not write
  the second claim. Verify all of this against the `config.json` files yourself before
  writing the paragraph.
* There is, however, a legitimate approximation check hiding in the same files, and it is
  worth proposing as an extra analysis: `adap_betweenness_frac` was computed **exactly**
  in the local runs and **approximately** in the global ones, for the same nodes, and both
  values sit side by side in `<network>_<slug>_local_vs_global.csv`. Comparing them
  isolates the cost of `btw_k` and `btw_update` on the nodes where both exist. Propose it,
  with the caveat that the subnetwork boundary also changes the true betweenness, so the
  two effects are not fully separable (`NLD_1131` alone jumps from 0.083 to 0.702).
* **`us_airlines` stands apart and should be used as the control case.** It is the only
  network where every protocol was run exactly at full size (`btw_update = 1`, no `btw_k`,
  `p_step_nodes = 1`, all six protocols) and the only one with no city subnetwork. Its
  natural place is the cross-network comparison, where it is both the dense non-spatial
  outlier (it keeps half its largest component until about 39\% of nodes are removed,
  against 2 to 4\% for the three spatial networks) and the case with zero
  hidden-vulnerable nodes and the highest regression $R^2$. Do not force it into the
  local-versus-global discussion.
* **Theoretical task guidelines.** The Moodle asks to synthesise the papers into one
  implementation rather than replicate each separately, to report the problems met during
  the replication and give my perspective on them, and says smaller system sizes are
  acceptable if the difficulty is reported. Make sure Task 25 does all three, explicitly.
* **Repository requirements** (report these to me as a checklist at the end of the
  outline; they are outside the report text but they are part of the same submission):
  `report.pdf` compiled at the repository root; `README.md` containing the chosen
  projects with number, name and score (it is currently **empty**); `code/` with
  standalone runnable scripts per task; `data/` with the output data **in edge list
  format with three columns `node_from,node_to,weight`, weight 1 for unweighted**, plus a
  node-metadata CSV for the spatially embedded networks. The Moodle also says explicitly
  that the original raw data of a data project need not be committed, only the
  output/post-processed data, so `data/task_42/project_42_raw_datasets/` stays ignored.
  What is currently wrong: the `seamless_input/<network>/<network>_edgelist.txt` files
  have two whitespace-separated columns and a comment header rather than the requested
  `node_from,node_to,weight` with `weight = 1`; and `.gitignore` excludes
  `seamless_input/`, `seamless_output/`, `seamless_input_local/` and
  `seamless_output_local/`, so none of the required output data is committed. Flag this
  and propose the fix, do not apply it silently. Note for the proposal that adding the
  weight column is safe: the loader in `seamless_robustness.py` splits on whitespace,
  requires at least two fields, reads only `parts[0]` and `parts[1]` and skips `#` lines,
  so a third column of ones is ignored and no result changes and nothing needs rerunning.
  For sizing: per SEAMLESS run, `config.json`, `metrics.csv`, `metrics_summary.csv`,
  `summary.csv` and `node_scores_wide.csv` are small enough to commit (about 17 MB for the
  largest run), while `node_scores.csv` (up to 300 MB) and `raw.csv` (up to 207 MB) are
  per-replicate bulk that must stay out.
* **Data provenance.** The four networks derive from
  `data/task_42/project_42_raw_datasets/`: EU power grid and EU railways from
  OpenStreetMap, US airlines from BTS, US power grid from the EIA Energy Atlas. The report
  must name these sources when it describes the data, and the repository should carry the
  same attribution alongside the committed edge lists.
* **Figure legibility.** The Moodle requires figures with font sizes readable on printed
  paper. This is the criterion behind item 4 of the figure dossier.

---

## 5. Deliverable (A) — the outline

Produce a hierarchical outline of the entire report, broken into **units small enough
that each one can be written in a single generation**. Aim for roughly 12--18 units
across the whole report. Give each unit:

* a **unit ID** (e.g. `T25-3`, `T42-APP-2`) and a title;
* the **exact file and location** it will be written into (e.g. "`sections/task1.tex`,
  section `Methods`, after the equation block");
* a **target length** in typeset lines and in words;
* the **figures and tables** it contains, with target widths, filenames in
  `latex/images/`, and a draft caption;
* the **specific claims it must make**, each with the source file and the numeric value;
* the **claims it must not make** (over-reach traps, caveats to preserve);
* its **dependencies** on earlier units (what it must be consistent with);
* for Task 42, which of the eight mandatory points it discharges.

Also include in (A): the requirements trace table from Sec. 4.5 (this one first, it drives
everything else), the parameter table built from the `config.json` files (Sec. 1.1), the
figure dossier from Sec. 1.2, the page budget arithmetic,
the list of proposed new figures/tables from Sec. 4.3,
any proposed change to `packages.tex` / `style.tex` with its justification, the
bibliography plan, and a short list of open questions for me if any remain.

## 6. Deliverable (B) — the per-unit prompts

Then write **one prompt per unit**, numbered to match the unit IDs, each in its own
fenced block so I can copy it verbatim. Each prompt must be **self-contained** and must:

1. State which unit it is writing, and in which file and at which location the output
   goes.
2. Instruct you (the future you, in a fresh turn) to **first re-read the master prompt,
   the outline, all the previously issued unit prompts, and the `.tex` text already
   written**, so that terminology, notation, symbol definitions, tense, level of detail
   and narrative thread stay consistent across units. Say explicitly which earlier units
   this one must not contradict and which symbols/definitions it inherits rather than
   redefines.
3. Re-state the compact style clause from Sec. 3, including the explicit requirement that
   the text must read as if written by a physics master's student and must not read as
   AI-generated.
4. Re-state the relevant hard constraints: ASCII only, compile against the existing
   preamble (any change to `packages.tex` / `style.tex` needs my approval first), target
   length, figure paths under `images/`, the page budget this unit is consuming.
5. List the exact facts and numbers this unit is allowed to use, with their source files,
   and forbid inventing anything not in those files. Repeat that the working notes are
   AI-written and are a record of what was done, not a source of wording and not a source
   of numbers: recompute from the data, and fall back on code, figures, papers and the
   task brief whenever something does not add up. If something needed is missing, the
   instruction is to stop and ask me, not to guess.
6. Specify the **output format**: a LaTeX fragment only, ready to paste (or to be written
   directly into the file), with no surrounding commentary, no markdown, and nothing
   touched outside the unit's location.
7. End with a check: non-ASCII scan, a `pdflatex` compile of `latex/main.tex`, and a
   report of the resulting page count against the budget.

Add, at the end of (B), a final unit prompt for a **whole-report consistency and
compilation pass**: symbol and notation consistency, caption style, citation coverage,
no repeated sentences across units, page count within budget, and a last read-through
specifically hunting for sentences that sound machine-written.

## 7. Honesty

Do not invent numbers, references, dataset provenance, or results. Do not smooth over the
caveats listed in Sec. 4. If the material does not contain something the outline seems to
need, say so and ask me rather than filling the gap. Everything in the report must be
traceable to a file in this repository or to one of the cited papers.

## 8. Before you start

If anything above is ambiguous or if you find that the material contradicts these
instructions, ask me first. Then produce (A) and (B).

=====================================================================================

## Notes for Francesco (not part of the prompt)

* The name and the file mapping (Task 25 in `task1.tex`, Task 42 in `task2.tex`) are
  baked in as you asked.
* Page budget uses the Moodle wording (2 main pages per task, up to 5 supplementary per
  task), which is stricter than the `task1.tex` boilerplate that says 3 + 5.
* New figures and tables are proposal-first: nothing gets generated until you approve the
  list in deliverable (A). The degree-distribution panel is flagged as near-mandatory,
  because the Moodle names degree distribution among the data analytics expected from a
  data task and no such figure exists yet.
* `packages.tex` / `style.tex` are a soft constraint: fixes to genuine defects are allowed
  but must be proposed, justified and approved first.
* The AI-use statement is left as a reserved slot: paste your reviewed text into the
  prompt (Sec. 4.4) before starting, otherwise the writing stops at that unit.
* Sec. 4.5 makes the assistant check the submission against the Moodle requirements and
  report back. Two things it will almost certainly flag: `README.md` is empty, and the
  SEAMLESS edge lists are two-column and gitignored, so the output data the professor asks
  for is not in the repository.
