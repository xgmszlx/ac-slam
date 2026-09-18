# Constraint-realizability direction audit (adversarial review)

Date: 2026-09-16
Auditor role: strict robotics collaborator / hostile reviewer
Scope: is the "realized constraint set" direction worth continuing, and what is the
next cheapest, highest-information experiment?
Evidence base: local artifacts only (docs 53-55, `results/realizability_pilot/p1_preflight_v7_20260916`,
nested mapper source), plus an independent literature sweep (arXiv API, 2026-09-16)
and the project's own prior literature boundary (doc 18).

New analysis added by this audit (read-only, no planner/harness change):
`tools/realizability_pilot/graph_separation_ablation_audit.py` →
`results/realizability_pilot/p1_preflight_v7_20260916/graph_separation_ablation_audit.json`.

Evidence labels: **[FACT]** published fact · **[CODE FACT]** from checked control flow ·
**[MEASURED]** from saved artifacts · **[INFERENCE]** combination · **[HYPOTHESIS]** ·
**[UNKNOWN]**.

---

## A. Facts that are now confirmed

A1. **[CODE FACT]** Constraint insertion has one choke point (`LinkObjects`), but six
creation paths. `AddEdges` (`PREVIOUS_SCAN`, `RUNNING_SCAN_CHAIN`, `NEAR_CHAIN`) runs
**before** `TryCloseLoop`; near-chain linking accepts on chain size ≥ 4, response
> 0.6 − TOL, endpoint ≤ 10 m, with no loop-pipeline gate. (doc 55 table; verified in
source.)

A2. **[MEASURED]** 3 valid sentinel episodes produced **15 target-attributable
historical constraints and 0 explicit `TryCloseLoop` target closures**; 12 of 15 have
recorded provenance (6 `RUNNING_SCAN_CHAIN`, 6 `NEAR_CHAIN`); all 12 entered
`ScanSolver::AddConstraint`, existed pre-`TryCloseLoop`, and their historical source
scans are members of the exact pre-loop `nearLinkedScans` set. (docs 54/55,
`sentinel_constraint_summary.csv`, `sentinel_edge_ledger.csv`.)

A3. **[MEASURED — new]** Target-attributable edges are *not* uniformly non-local.
Cycle length at insertion (pre-insertion graph-geodesic + new edge length):
- baseline OFF: 3/3 target edges > 4 m (cycles 8.09, 14.92, 16.44 m; hops 3, 3, 5);
- baseline ON: 3/3 > 4 m (9.96, 13.39, 19.16 m; hops 3, 4, 5);
- sweep90 ON: **only 3/9 > 4 m** (7.84, 14.97, 16.26 m); 1 edge < 1 m (0.19 m) and
  5 edges in 1–4 m (1.91, 1.93, 2.08, 3.93, 3.94 m; all 2–3 hops).
- **Sharpest form of the same observation**: in sweep90 the *wrong-target* historical
  edges are the non-local ones (all 13 cycles ≥ 7.69 m, up to 16.95 m) while 6/9
  *target* edges are local reinforcement of the target scan.
  **[HYPOTHESIS]** Proximity-driven creation is therefore self-limiting: the harder the
  action aims at one history region, the more its realized edges to that region become
  local stiffening rather than large-cycle closure. (n = 1 condition; requires repeats.)

A4. **[MEASURED — new]** Using the paper's own utility (`utils.get_d_opt` edge weights
from `covariance^-1`, `get_normalized_weighted_spanning_trees` on the reduced
Laplacian), conditional ablation on the realized graph:
- ΔU_target = 851 / 895 / 2195 (7.0% / 7.3% / 15.1% of U_all) for
  baseline OFF / baseline ON / sweep90 ON;
- ΔU_history (target + wrong-target) = 3950 / 4479 / 5451 (34.1% / 35.1% / 37.5%);
- per probe metre: target 132 / 126 / 337; history 614 / 632 / 837.

A5. **[MEASURED — new, decisive]** The **actual historical pose correction** caused by
all new constraints is negligible: maximum historical node shift 1.9 mm (baseline OFF),
0.9 mm (baseline ON), 11.7 mm (sweep90); target-source nodes move 0.5–0.9 mm
(baselines) and 4.5–11.7 mm (sweep90). Compare with inter-scan spacing ~0.5–1 m.

A6. **[MEASURED]** Probe cost differs across conditions: baseline 6.43 m / 24 s,
baseline ON 7.09 m / 23 s, sweep90 6.51 m / **35 s**; new edges 34 / 34 / 51.

A7. **[MEASURED]** `align60` is `TECHNICAL_INVALID_FINAL`; three of four frozen
sentinel conditions have a valid outcome.

A8. **[MEASURED]** The diagnostics OFF/ON pair used different sequence-derived TSP
seeds (31001 vs 31002) → `INCONCLUSIVE_FOR_CAUSAL_NON_PERTURBATION` (doc 55, admitted).

A9. **[MEASURED, prior phase]** Phase 4C: all 15 accepted *explicit* target events had
zero measured pose correction; decision was `REOPEN_EXECUTION_HYPOTHESIS` (doc 53).

A10. **[FACT]** The baseline RA-L 2024 method itself re-traverses a segment of the
previous trajectory at loop vertices, and already uses scan-matching covariance for
degeneracy update (doc 18 §5; paper Sec. V-A).

A11. **[UNKNOWN / artifact gap]** The saved snapshots store node poses, edge
endpoints, indices and covariances but **not the SE(2) relative measurements**, and
`pose_graph.g2o` is partial (17 lines, no edges). Exact posterior covariance from the
saved artifacts is therefore not computable today.

## B. Old assumptions that are now refuted

B1. ~~`TryCloseLoop == false` ⇒ no historical constraint was created.~~ **Refuted**
(A2). The explicit pipeline is a *subset* of constraint creation, and it is
structurally excluded from re-finding constraints that `LinkNearChains` already
created (their sources are in `nearLinkedScans`).

B2. ~~"Non-explicit historical constraint" implies "non-local / large-cycle
constraint".~~ **Refuted** (A3): 6 of 9 sweep90 target edges close cycles < 4 m.

B3. ~~Target edge count is a meaningful proxy for realization success.~~ **Refuted**
(A3+A5): count tripled (3→9) while the non-local count stayed constant (3→3) and the
measured estimate impact stayed ~0.

B4. ~~Higher D-opt marginal utility implies a realized benefit.~~ **Not supported**
(A4 vs A5): ΔU_target rises 2.5× across conditions while pose correction stays
≤ 1.2 cm. The topological metric and the estimation effect are decoupled here.

B5. ~~The 3→9 sweep90 change is evidence that a 90° sweep improves loop realization.~~
**Not supported**: single pair, no repeats, different probe duration (35 s vs 23–24 s)
and different maneuver semantics; and the extra edges are largely local (A3).

B6. ~~Phase 2C labels (`CHAIN_TOO_SHORT`, `COARSE_LOW_RESPONSE`, `no-chain`) describe
the SLAM constraint outcome.~~ **Refuted**: they describe only the explicit
`TryCloseLoop` pipeline outcome (doc 55).

## C. What the literature already covers

C1. **Closure-probability × information − cost at selection** is occupied: P-ALC
(ICRA 2024) reward `R = −c_t·l + PLC·ΔU`, `PLC = tanh(view)·exp(−relative uncertainty²)`,
branch-and-bound over keyframe clusters; Lehner et al. (IROS 2017) joint
match-likelihood/effect/cost; Lighthouses (ICRA 2023) revisit + in-place rotation with
a heuristic closure likelihood and online closure observation (doc 18 table, verified
with full text where noted).

C2. **Data-association uncertainty inside planning** is occupied, and explicitly so:
DA-BSP (Pathak et al. 2016) states that "existing BSP approaches typically assume data
association is given and perfect" and models DA within belief evolution (multi-modal
posterior, ambiguity cost, active disambiguation); D2A-BSP (ICRA 2022) and Nonmyopic
Distilled DA-BSP (ISRR 2022) add budget-aware distillation with guarantees; iX-BSP
(Farhi & Indelman) computes expected belief-dependent reward by sampling future
measurements while accounting for DA.

C3. **Planning over future factor-graph topology with a spanning-tree-based
information metric** is occupied: t-BSP (Kitanov & Indelman) performs decision making
"considering only topologies of factor graphs that correspond to posterior future
beliefs", with bounds against an information-theoretic BSP whose metric is "based on
the number of spanning trees". This is the closest prior art to our D-opt-over-graph
formulation and to any claim about predicting future constraint topology.

C4. **Robust data association on the estimation side** is mature (e.g. cycle-consistent
multiway matching, Tian et al. IJRR) — it does not plan actions.

C5. **Active-loop execution adaptation** exists (P-ALC refinement stage, Lighthouses
preemption/global graph stabilization, our Phase 4A post-selection repair), so
"adapt execution after selection" is not novel by itself.

## D. Research gaps that may still be defensible

D1. **Realized-vs-planned constraint mismatch as a measured object** — no found work
reports, per action, the *creation-path provenance, identity, and covariance of the
constraints that a real front-end actually inserts* against the *hypothetical edge* a
planner assumed. Our A2/A3 evidence is direct and (as far as this search goes)
unoccupied.

D2. **Planning consequence of that mismatch** — if the realized set is created by
proximity/chain linkage *before* any loop test, then the planner's D-opt credit for a
"loop edge" is being delivered (or not) by a different mechanism at different cost.
No found work quantifies planned-vs-realized *reliability credit* per unit motion.

D3. **Action-conditioned, measured reliability credit** — an objective of the form
`E[ΔU_realized | action, history] / cost`, where ΔU_realized is measured on the graph
the backend actually produced, is not found in the active-SLAM line reviewed (P-ALC and
Lighthouses model closure *probability*, not the realized constraint-set utility;
DA-BSP/t-BSP model *hypothesized* measurements/topologies).

**Conditional on D1-D3 surviving the next experiment**, the direction is a *measurement
+ planning-credit* contribution, not a "predict loop probability" contribution.

## E. The five most dangerous reviewer risks

E1. **Unvalidated proxy objective.** A reviewer will observe that ΔU (topological,
D-opt-like) is presented as utility while the measured pose effect is ≤ 1.2 cm and no
posterior-covariance reduction is reported. Verdict risk: "optimizes a metric that
measures nothing." This is the same failure mode as "more edges = better SLAM", one
level deeper.

E2. **n = 3, one map, one anchor, no repeats.** Any claim about *distributions* or
*manipulation* is anecdotal; the single 3→9 observation is confounded (duration,
maneuver semantics, keyscans).

E3. **Prior-art collision.** DA-aware BSP (2016–2022) plus t-BSP already occupy
"reason about uncertain data association in planning" and "decide using future
factor-graph topologies with spanning-tree metrics". The remaining delta is thin and
must be stated with those works explicitly in the boundary.

E4. **Single-backend engineering result.** The provenance finding is OpenKarto-specific
(chain linking before loop search). Without a second backend, a reviewer may classify it
as an implementation detail; Phase 4C already flagged an independent backend as
untested.

E5. **Instrument validity not established.** The only ON/OFF comparison is
seed-confounded (A8); a reviewer can argue the provenance instrumentation itself
changed the realized set, which would undermine the measurement layer of any
follow-up.

## F. Next round: minimal experiment

Pre-registered, small, decision-oriented. Two experiments only.

**N0 — instrument validity (cheap, blocks everything else).**
Paired **same-seed** diagnostics/provenance OFF vs ON (3 seeds × 1 pair), same route,
same probe, same target, with the frozen pre-probe signature gate (see §G). Primary
outcome: realized constraint set (E_T, E_N, provenance, covariances) and probe cost;
secondary: probe wall/sim timing and keyscans.

**N1 — realized-impact experiment (the decisive one).**
Question: can a *deliberately chosen* active revisit produce realized historical
constraints with a **measurable estimation impact** attributable to the action?
- Target selection rule (outcome-blind, fixed before runs): anchor with **large
  travel/state separation** from the current chain (e.g. ≥ 40 state gap *and*
  ≥ 20 m geodesic separation in the pre-probe graph) and **low alternative-path
  redundancy** (pre-probe geodesic between the two endpoints ≥ 4 × Euclidean
  separation, i.e. the graph detour is large).
- Independent variable: probe maneuver class at fixed budget — `pass`, `lateral
  offset`, `90° sweep` — with probe distance controlled to ±0.5 m and duration
  reported, **3 repeats each**.
- Primary outcome: measured effect on the estimate — (i) max/mean historical pose
  correction, (ii) relative change of the posterior marginal covariance (trace) of the
  target segment and its neighbours, computed offline from the full before/after graph
  **including SE(2) measurements**.
- Secondary: provenance-resolved E_T/E_N with cycle length, ΔU_target/ΔU_history
  (paper definition), ΔU per metre, target_selectivity.

Both experiments require one artifact addition (no algorithm change): **record, for
every created edge, the SE(2) relative measurement (dx, dy, dθ) and dump the full
before/after graph with measurements** so exact posterior covariance is computable.

## G. Per-experiment specification

| item | N0 | N1 |
|---|---|---|
| independent variable | diagnostics/provenance ON vs OFF (same seed within pair) | maneuver class at fixed distance budget |
| control variables | map3, history route, TSP seed, target anchor, probe geometry, Karto config, planner | same as N0 plus identical pre-probe graph signature and identical probe distance |
| pre-probe signature gate | node id set + unique ids, edge endpoint set, per-edge covariance summary (median + max), corrected-pose summary (mean/max deviation ≤ 2 cm), target id set identical, GT start pose ≤ 1e-3 m, keyscan count equal | same |
| primary outcome | E_T/E_N with provenance + probe cost; divergence of timing | (i) max/mean historical pose correction, (ii) relative posterior-covariance (trace) reduction of target segment |
| secondary outcome | wall/sim ratio, keyscan count | provenance-resolved constraint set, cycle length, ΔU_target/ΔU_history, ΔU per metre |
| invalid condition | pre-probe signature mismatch; navigation GT gate fail; observer cut incomplete; pre-freeze closure (contamination); any harness crash | same |
| stop rule | any pair diverges beyond tolerance → escalate to same-input replay before any N1 claim | if best configuration fails to exceed the pre-registered impact floor in ≥ 2 of 3 repeats → **STOP_DIRECTION** |

Pre-registered impact floor (proposal): max historical pose correction ≥ 3 cm **or**
relative trace reduction ≥ 5% of the target segment's marginal covariance. Below that,
the realized target constraints are indistinguishable from graph redundancy at this map
scale.

## H. Matched online runs vs same-input Karto replay

**[INFERENCE]** Same-input replay (record `/scan`, odom, TF, timestamps; replay into
Karto OFF/ON) is scientifically the cleanest isolation of the instrumentation effect,
but this project's own history (v1–v7 repairs: cursor, TF vs `/slam_path`, gate
refreshes) shows the harness is the dominant failure source; a replay driver is a new
nontrivial component and the machine runs at ≈ 4.6× slower than the Phase 2B era.

Recommendation: **matched online runs, same seed within pair**, with the pre-probe
signature gate, as the primary design for N0 (6 episodes). Escalate to replay **only
if** N0 shows a divergence beyond tolerance — that keeps the cost bounded while
answering the actual question ("did instrumentation change the realized set?"). State
explicitly that matched runs control the seed confound but not ROS/Stage scheduling
jitter; the signature gate is what makes residual mismatch visible.

## I. Should realized graph utility be computed now?

**[MEASURED answer]** Yes — it is cheap, it reuses the paper's definitions, and it was
already informative: it converts "more target edges" into "conditional marginal
reliability credit", and it exposed that the sweep90 gain is largely *local* (A3/A4).
**[INFERENCE]** But it must **not** be the primary outcome yet: ΔU and the measured
estimate effect are decoupled in the current data (A4 vs A5). Report ΔU as a
*mechanism/credit* quantity, always alongside the measured impact.

**[FACT]** The ablation is a **conditional marginal contribution** `U(G_all) −
U(G_all − E_S)` given the fixed realized graph; it is not a Shapley value, not an
ordered decomposition, and not an absolute causal effect. Removing E_T while keeping
E_N and every other edge also means the estimate is "the value unique to E_T given the
rest", which *understates* the total contribution of the action.

## J. Add graph-geodesic / cycle-size as standing diagnostics?

**[MEASURED answer]** Yes — it changed a conclusion in this very audit (sweep90's 3×
count is 6/9 local). Recommended standing quantities per realized edge: pre-insertion
graph-geodesic hop count and metric distance, cycle length, plus provenance. Caveats to
state: the pre-insertion state is reconstructed by replaying edge creation order; the
geodesic uses Euclidean edge weights, so "cycle length" is a graph-metric length, not
travelled distance; state-id gap alone must never be used as a locality criterion.

## K. Verdict on the candidate research question

> "Can an active revisit planner predict and manipulate the distribution and
> information utility of historical pose-graph constraints actually created by a real
> SLAM data-association pipeline, rather than optimizing a deterministic hypothetical
> loop edge?"

**[INFERENCE]** As literally stated: **not supported by the current evidence, and
partially contradicted.**
- "actually created by a real pipeline" — supported and useful (A2, A3).
- "predict the distribution" — untested: n = 3, one map, one anchor, no repeats; and
  the mechanism found (proximity/chain linkage) is geometric, which makes prediction
  plausible but trivial to demonstrate and therefore a weak contribution by itself.
- "manipulate … information utility" — contradicted in the utility-relevant sense: the
  maneuver that tripled the target count did **not** increase non-local cycles (3→3)
  and produced ≤ 1.2 cm of estimate change (A3, A5).
- "rather than optimizing a deterministic hypothetical loop edge" — this is the
  defensible core, but the literature already contains both halves of the neighbouring
  space (DA-aware planning; topology/spanning-tree-based planning utility), so the
  claim must be recast as a *measured credit* question, not a "predict probability"
  question.

### Decision

**PROCEED_WITH_REFRAMING** — with a hard gate.

Justification: (i) the measurement finding (A1-A3) is solid and, in this search,
unoccupied; (ii) the *planning* claim is currently unsupported, and the most likely
reason is the pilot's target/map design (an "infrastructure/debug target" in an
already well-constrained graph, per doc 54), not a fundamental impossibility — so it
must be tested before the direction is either endorsed or dropped; (iii) the test is
cheap (one harness already exists; the only new artifact is per-edge SE(2)
measurements).

Reframed claim to carry forward (nothing broader):

> For an already-selected active revisit, the *realized* historical constraint set of a
> real SLAM front-end — its identity, creation path, covariance and graph-geodesic
> role — can be measured, and its **conditional marginal reliability credit per unit
> motion** is the quantity a planner should reason about; the classic hypothetical
> loop edge is the wrong credit model.

Hard gate: if N1 (Section F) does not exceed the pre-registered impact floor in ≥ 2 of
3 repeats for its best configuration → **STOP_DIRECTION**. Do not build a predictor,
factorial screen, ML model or second backend before that gate is passed.

Explicit non-claims to keep in the write-up: no claim that "non-explicit" implies
"non-local"; no claim that more target edges means better SLAM; no realized/planned
information ratio (see below); no "first to model data-association uncertainty in
planning" (DA-BSP/D2A-BSP/iX-BSP); no "first to use factor-graph topology for planning
utility" (t-BSP).

### Q4 answer (realized/planned information ratio)

**Do not compute it.** **[INFERENCE]** The planner's object is a region-level abstract
pose graph over prior-graph vertices with a single prior covariance model; the realized
object is a scan-level Karto graph with per-edge matcher covariances. Node dimensions,
edge definitions, covariance weighting and the normalisation inside
`get_normalized_weighted_spanning_trees` (dividing by the number of reduced-Laplacian
nodes) are not commensurable, so any ratio is dimensionally meaningless. If a
comparison is ever wanted, first define and validate an explicit projection
scan-graph → region-level graph, and report the projection error.

### Q5 answer (target_selectivity as objective)

**Diagnostic only.** **[INFERENCE]** E_N constraints are valid measurements with real
utility: A4 shows 34–38% of U comes from the action's whole historical edge set while
E_T contributes 7–15%; and in the current episodes many E_T edges add nothing
measurable (A5). Optimising `|E_T|/(|E_T|+|E_N|)` would reward planner-target
bookkeeping rather than graph benefit, and could actively harm the system by
discouraging cheap, informative ordinary links. Keep it as a planner-fidelity metric.

---

## Novelty matrix (2010–2026, verified during this audit)

`exists` = models/branches on uncertain measurement existence; `DA` = models
data-association uncertainty; `future-id` = predicts identity/topology of future
factors; `real-Σ` = uses real measured covariances from a running SLAM front-end;
`view` = optimises viewpoint/action; `loop-back` = closes the loop into planning;
`realized-set` = evaluates the constraint/factor set actually created; `perfect-DA` =
assumes perfect data association.

| work | exists | DA | future-id | real-Σ | view | loop-back | realized-set | perfect-DA |
|---|---|---|---|---|---|---|---|---|
| Graph-Based SLAM-Aware Exploration (RA-L 2024, our baseline) | no (deterministic hypothetical loop edge) | no | partial (region-level edge exists) | partial (matcher covariance for degeneracy update) | no | yes | no | partial assumption |
| Active Loop Closing trade-off (Lehner, IROS 2017) | partial (info-gain vs LC benefit) | no | no | no | no | yes | no | yes |
| P-ALC (ICRA 2024) | yes (PLC probability) | no | no (cluster target) | no (data-driven view/uncertainty features) | yes | yes | no | yes (probability replaces DA) |
| Lighthouses + GGS (ICRA 2023) | heuristic likelihood | no | no | partial | yes | yes | no | yes |
| DA-BSP (2016) / D2A-BSP (ICRA 2022) / Nonmyopic DA-BSP (ISRR 2022) | yes (multi-modal hypotheses) | **yes** | partial (hypothesised DA topology) | no (simulated measurements) | yes | yes | no | no |
| iX-BSP (2021) | yes (sampled future measurements) | yes | no | no | yes | yes | no | no |
| t-BSP (2019, + journal line) | no | no | **yes (factor-graph topologies)** | no | yes | yes | no | yes |
| T-RO 2023 Active SLAM survey | survey | survey | survey | survey | survey | survey | survey | survey |
| this project (v7 sentinel) | measured | measured provenance | no | **yes (per-edge matcher Σ)** | action varied | not yet | **yes (measured set)** | no |

**[INFERENCE]** No row combines *measured realized constraint set* (provenance-resolved,
real backend) with *planning credit*. That is the defensible sliver; everything else in
the candidate question is adjacent to the rows above.

## Literature-search limitations (honesty)

Search performed with the arXiv API (2026-09-16) plus the project's prior full-text
boundary audit (doc 18). Semantic Scholar was rate-limited (HTTP 429), so ICRA/IROS/
RA-L/IJRR/T-RO coverage beyond arXiv and doc 18 is **partial**; the P-ALC PDF could not
be re-fetched today (content taken from doc 18's earlier verified full-text read). The
"no found work" statements are therefore *search-limited*, not proof of absence. A
structured database search (Scopus/IEEE Xplore) should precede any publication claim.
