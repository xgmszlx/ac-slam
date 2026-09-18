# 57 — Pre-factorial direction decision: instrumentation validity and budget-matched action intervention

Status: in progress (results appended after the N0/N1 suites complete).
Round scope: N0 instrumentation validity → N1-A offline target screening →
N1-B budget-matched action intervention → direction gate → stop.

Nothing in this round changes the planner objective, the Karto thresholds, the
scenario, the map, or the route. No predictor, no factorial screen, no ML model.

## 1. Evidence classification used throughout

Every statement below is labelled:

* **CODE FACT** — read directly from the repository sources.
* **MEASURED OBSERVATION** — produced by an executed episode or by a read-only
  analysis of recorded artefacts.
* **INFERENCE** — a conclusion drawn from measured observations.
* **HYPOTHESIS** — a claim that the current round cannot decide.
* **UNKNOWN** — not measured.

## 2. Why the earlier OFF/ON comparison could not settle the instrument question

**CODE FACT.** `tools/realizability_pilot/run_pilot.py` derived the planner seed
from the episode sequence (`tsp_seed = 31000 + sequence`), so the diagnostics-OFF
and diagnostics-ON sentinel episodes of the v7 preflight ran with different TSP
seeds (31001 vs 31002). The observed difference between those two episodes
therefore mixed the instrument effect with a different exploration trace.

**MEASURED OBSERVATION (v7 suite).** The two sentinel episodes also differed in
pre-probe graph size (32 vs 33 nodes), which is the mechanism through which a
different seed propagates into the constraint outcome.

## 3. N0 — instrumentation validity with matched same-seed arms

Three arms, three seeds, one shared seed per block, Latin-square arm order:

| arm | loop diagnostics | edge provenance | purpose |
|---|---|---|---|
| `n0_instr_off` | off | off | instrument-free reference |
| `n0_prov_on` | off | on | the instrument N1 depends on |
| `n0_prov_diag_on` | on | on | the legacy diagnostics instrument |

All three arms keep the full pose-graph observer enabled, because the observer is
what makes the outcome measurable at all; it is a shared constant of the block,
and the observer's own effect is therefore not what N0 isolates (it is stated as
a limitation).

Pre-probe comparability gate (pre-registered in
`n0_analysis.PREPROBE_TOLERANCES`): identical target segment size, anchor distance
comparable within 0.25 m, node count within ±2, edge count within 15 %, edge
covariance median-trace ratio within [0.5, 2.0], and the corrected position and
heading of the node nearest to each executed route waypoint within 0.05 m /
0.05 rad. A block that fails the gate is reported as
`INVALID_FOR_CAUSAL_PAIR` rather than silently averaged.

Non-perturbation rule: a shift counts as detectable only when the absolute mean
paired difference (same seed, on minus off) exceeds **two times the measured
same-configuration repeatability** (mean absolute deviation across the nine N0
episodes) **and** every paired seed difference has the same non-zero sign.
Otherwise the verdict is `OUTCOME_MEASUREMENT_STABLE`.

## 4. N1-A — offline, outcome-blind target screening

The screen reads only pre-probe artefacts (`pose_graph_before.json` and
`resolved_history_route.json`), so no probe outcome can influence the selection.
Candidate set: the four waypoint regions of the frozen three-sided route.

Per candidate region, measured on each available pre-probe graph:

* scan-index separation (anchor scan vs newest scan),
* geodesic separation and hop count between the anchor and the newest scan,
* Euclidean separation and the geodesic/Euclidean ratio,
* local degree and neighbourhood edge count (local redundancy),
* frozen-segment length, scan count, mean scan spacing and accumulated heading
  change (local geometry descriptor).

Selection rule: rank by the mean quantile position in (hops, ratio, inverse
redundancy); region A is the top-ranked region, region B is the next region that
is above the median on both non-locality quantiles and differs from A in local
geometry by at least the median pairwise geometry difference. If no such second
region exists the screen returns `TARGET_SCREEN_FAILED`.

The selected pair is frozen in
`preregistration/n1_target_selection_preregistration.json` before any N1 episode
runs.

## 5. N1-B — budget-matched action intervention

Two targets × three actions × two blocks = 12 episodes, each block with its own
shared TSP seed and a balanced action order.

| action | description | sensing/motion intent |
|---|---|---|
| `n1_a0_baseline` | frozen Graph-Based revisit execution (`pass`) | reference |
| `n1_a1_neutral` | away-and-back translation of 2 × 1.5 m along the arrival heading, yaw unchanged | matched scan-addition opportunity without new yaw viewpoints |
| `n1_a2_sweep90` | frozen 90° sweep (−30°, 0°, +30° at the anchor) | deliberate yaw viewpoints of the historical region |

**CODE FACT (budget rationale).** Karto adds a key scan after
`MinimumTravelDistance = 1.0 m` or `MinimumTravelHeading = 0.52 rad` (≈30°). The
sweep therefore crosses the heading threshold three times, i.e. it creates about
three additional key scans, and 2 × 1.5 m of translation crosses the distance
threshold about three times. The 1.5 m offset is chosen so that A1 and A2 have a
comparable scan-addition opportunity; the realised budget is measured per episode
(probe ground-truth distance, probe duration, new key scans, new edges) and
reported, not assumed.

The neutral direction is chosen at run time as the sign along the arrival heading
that increases the distance to the frozen target segment centroid, so the neutral
motion never approaches the historical region.

## 6. Measurement and estimation analyses

* **Measurement ledger** (`edge_measurement_ledger.csv`): per constraint, the
  source/target state and unique ids, the SE(2) relative measurement
  (dx, dy, dθ), the 3×3 covariance, the provenance, the creation order, the
  phase flag and the instrument that produced it (`PROVENANCE_RELATIVE_MEAN` or
  `RECONSTRUCTED_FROM_CORRECTED_POSES`). The fallback exists because the
  instrument-free arm has no raw measurements; the reconstructed value is the
  relative pose implied by the corrected estimate and is labelled as such.
* **Posterior uncertainty ablation** (`posterior_uncertainty_ablation.csv`): the
  linearised information matrix `Λ = Σ Jᵀ Ω J` is built for the full graph, for
  the graph with the target-attributable constraints removed, and for the graph
  with all history-touching probe constraints removed. The gauge freedom is
  removed with the Moore-Penrose pseudoinverse, so every reported 3×3 block is a
  covariance relative to the removed gauge and ablation *differences* are
  gauge-independent. Reported per metric group: target segment, current pose,
  historical region, all history, new scans.
* **Graph utility ablation** (`graph_utility_ablation.csv`): the D-optimality
  scalar of each constraint's own 3×3 information matrix, grouped by attribution,
  plus the D-optimality scalar of each information-matrix build.
* **Insertion-time non-locality** (`insertion_nonlocality.csv`): the after-probe
  edge list is replayed in creation order and the geodesic distance and hop count
  between the two endpoints are measured *before* the edge itself is inserted.

Constraint attribution is structural (one endpoint inside the frozen historical
target segment, the other endpoint a post-freeze scan), so it works in every arm
including the instrument-free one. The round never labels a constraint a false
closure and never computes a planned/realised utility ratio.

## 7. Effect thresholds (frozen before N1 outcomes are inspected)

`preregistration/effect_threshold_preregistration.json` is written from N0 only,
after N0 completes and before the first N1 episode runs. For count outcomes the
MDE is `max(1, 2 × measured MAD)`; for continuous outcomes
`max(numerical tolerance, 2 × measured MAD)`; for the relative posterior and
utility outcomes the frozen MDE is 5 % of the block baseline, which is above the
numerical noise of the linearised build.

## 8. Direction gate

`direction_gate.py` implements the pre-registered criteria: N0 certified the
instrumentation; the sweep adds target-attributable constraints beyond the frozen
MDE; the sweep beats the budget-matched neutral in the same direction; the target
segment posterior uncertainty shrinks beyond the frozen MDE; graph utility rises
beyond the frozen MDE; the utility gain per extra metre favours the sweep; and
the effect is present on both targets. Output: `INTERVENTION_SUPPORTED`,
`NOT_SUPPORTED`, `INCONCLUSIVE_NEEDS_ONE_MORE_CONTROL` or `STOP_DIRECTION`.

## 9. Results

(to be appended)

All results below are **MEASURED OBSERVATION** from the executed N0 suite
(`results/realizability_pilot/p1_dir_dec_v8_20260916/n0_instrument`, 9 episodes,
all SUCCEEDED) unless labelled otherwise.

### 9.1 Instrumentation validity (N0)

Arm means are given as the three per-seed values so the reader can see the
dispersion instead of a single aggregate.

| outcome | OFF | provenance-ON | diagnostics+provenance | verdict |
|---|---|---|---|---|
| target-attributable constraints | 4, 3, 4 | 4, 4, 2 | 4, 3, 3 | stable |
| history-touching probe constraints | 6, 10, 8 | 7, 7, 7 | 6, 10, 9 | stable |
| target-attributable geodesic mean (m) | 8.13, 7.56, 7.55 | 7.97, 7.96, 10.04 | 8.18, 9.40, 9.02 | shifted in the two-instrument arm (+1.12 m) |
| probe key scans | 15, 17, 16 | 15, 16, 14 | 15, 15, 15 | not flagged |
| final node count | 50, 51, 50 | 50, 50, 48 | 49, 49, 49 | shifted (−1.33, two-instrument arm only) |
| final edge count | 76, 77, 75 | 75, 74, 71 | 72, 75, 73 | **shifted (−2.67 both instrumented arms)** |
| local probe constraints | 23, 23, 22 | 21, 23, 22 | 22, 20, 20 | shifted (−2.00, two-instrument arm) |

Two of the nine episodes produced a probe that the frozen navigation gate
rejected (GT heading error 1.80 rad against the frozen 0.35 rad tolerance); the
failed attempts are preserved and one retry was executed, as the suite protocol
requires.

Verdict: `POSSIBLE_INSTRUMENTATION_PERTURBATION`. The decisive measurement is the
final constraint count: every paired seed shows the instrumented arms producing
fewer constraints (OFF 76/77/75 vs 75/74/71 and 72/75/73), a shift of about 3 %
that exceeds twice the measured same-configuration repeatability. The primary
outcome of the planned intervention (target-attributable constraints) is *not*
flagged, but the target-attributable geodesic mean is shifted in the
two-instrument arm, so the instrument cannot be certified as neutral for the
outcome family the intervention was going to measure.

Pre-probe comparability: 3 of 9 pairs passed the frozen 0.05 m route-node
tolerance; the measured per-pair maximum route-node deviation was 0.028–0.240 m,
with pre-probe node counts differing by at most one scan and edge counts by up to
three. Matched pairs therefore control the TSP seed, the route, the map and the
probe, but they do not reproduce the graph exactly; the residual is measured and
reported rather than assumed away.

### 9.2 Target screening (N1-A, executed, outcome-blind)

| region | geodesic hops (mean) | geodesic/Euclidean | local redundancy | segment length | segment heading change |
|---|---|---|---|---|---|
| 0 (anchor_01) | 7.50 | 2.01 | 2.0 | 3.29 m | 1.47 rad |
| 1 (anchor_03) | 7.75 | 1.67 | 2.8 | 3.25 m | 2.61 rad |
| 2 (anchor_02) | 3.00 | 1.07 | 1.8 | 3.72 m | 2.65 rad |
| 3 (anchor_04) | 0.75 | 1.89 | 1.3 | 2.70 m | 3.28 rad |

Regions 2 and 3 are rejected by the screen because they sit at the end of the
history route, where the robot already is: their graph separation is small, which
is exactly the condition under which a revisit constraint can only duplicate an
existing short path. Selected pair: `map3_grid_anchor_01` (region 0) and
`map3_grid_anchor_03` (region 1), geometry difference 5.77 against a median
pairwise difference of 4.97, frozen in
`preregistration/n1_target_selection_preregistration.json`.

### 9.3 Intervention (N1-B) — not executed

The N1-B suite was planned, preregistered and tooled
(12 episodes, two targets × three actions × two blocks, balanced order, matched
seeds, frozen thresholds), but the round rule gates N1 on a stable N0 verdict and
N0 was not stable. The suite directory
`results/realizability_pilot/p1_dir_dec_v8_20260916/n1_blocks` contains the
frozen `suite_state.json` with all twelve episode specifications and no attempts.

### 9.4 Direction decision

`STOP_DIRECTION`, recorded in
`results/realizability_pilot/p1_dir_dec_v8_20260916/direction_gate_decision.json`
with the reason, the flagged measurements and the required next action (repair
the instrument so that provenance writing no longer blocks the mapper's answer
path, then repeat N0; a stable N0 is the only entry condition for N1).

### 9.5 What this round established

1. **The instrument is not neutral.** Observation-only JSONL provenance logging
   correlates with about 3 % fewer graph constraints and fewer probe key scans in
   the same matched configuration, from the initial mapping phase onwards. Every
   instrumented analysis in this project (docs 55 and 56 and the v7 preflight
   suite) inherits that qualification.
2. **The old OFF/ON comparison had two independent defects**, not one: the
   sequence-derived TSP seed and the instrument itself. Fixing the seed (this
   round) left the instrument effect visible.
3. **Matched same-seed pairs remove the seed confound but do not reproduce the
   graph exactly**; the residual geometry variation (≤ 0.24 m at route waypoints,
   ≤ 1 scan and ≤ 3 edges in the pre-probe graph) is now measured.
4. **The candidate screen works and is discriminative**: it rejects the two route
   regions whose graph separation is small and selects two regions with high
   separation and different local geometry.
5. The analysis tooling for the intervention (SE(2) information build, gauge
   anchored posterior ablation, insertion-time non-locality, budget matching,
   frozen-threshold gate) is implemented and unit-tested against the existing
   recorded suites, so the intervention can start as soon as N0 passes.

---

## Amendment (2026-09-17): gate semantics and project state

**Why this amendment exists.** The section above (9.4) reports that the round
ended with the automatic label `STOP_DIRECTION`. That label was produced by the
pre-amendment gate code, which mapped *any* N0 failure to `STOP_DIRECTION`. That
mapping conflated two independent decisions and is corrected here. The original
record is preserved: nothing above was rewritten or deleted.

**What was wrong.**

* `STOP_DIRECTION` is a statement about the **research hypothesis**. It may only
  be produced after the preregistered intervention experiment (N1) has been
  executed and has failed its frozen criteria.
* The N0 block checks the **measurement infrastructure**. Its failure says the
  instrument is not certified; it says nothing about whether the hypothesis is
  true.
* Because N1-B was never executed, there is no evidence at all about
  Baseline vs Budget-Matched Neutral vs Sweep90. The scientific hypothesis is
  therefore **alive but untested**, not rejected.

**Corrected state machine (implemented in `tools/realizability_pilot/direction_gate.py`).**

```
N0: OUTCOME_MEASUREMENT_STABLE   -> RUN_N1
N0: INSTRUMENTATION_NOT_NEUTRAL  -> PAUSED_INSTRUMENTATION_NOT_CERTIFIED
N1: INTERVENTION_SUPPORTED       -> PROCEED_TO_MODELING
N1: INTERVENTION_NOT_SUPPORTED   -> STOP_DIRECTION
N1: AMBIGUOUS_SINGLE_BLOCKER     -> INCONCLUSIVE_NEEDS_ONE_MORE_CONTROL
```

**Corrected statement of the project state as of the first N0 round.**

```
Measurement Gate:          NOT CERTIFIED
Intervention Hypothesis:   NOT YET TESTED
Project State:             PAUSED_INSTRUMENTATION_NOT_CERTIFIED
```

**Corrected wording of the first N0 finding.** The first round measured an
association, not a proven cause:

> The matched online experiment failed to certify instrumentation neutrality: the
> instrumented arms produced fewer graph constraints than the instrument-free arm
> in the same seed-matched configuration. It did **not** prove that the
> instrumentation causally reduces constraints by 3 %, because the matched pairs
> did not share a bit-identical pre-probe graph (route-node deviation
> 0.028-0.240 m, up to one extra scan and three extra edges).

A buffered implementation and a same-input replay are required before the
preregistered action-intervention experiment can be interpreted scientifically.
The first-round decision artefact is retained verbatim as
`direction_gate_decision_pre_amendment_STOP_LABEL.json`; the corrected artefact
is `direction_gate_decision.json`.

## Amendment (2026-09-17, second): instrumentation repair and N0 certification

**Why this amendment exists.** The first amendment corrected the *labelling* of
the round. It left two engineering facts unresolved: the instrument still
performed I/O on the constraint-creation path (a periodic flush every 5 s), and
the online matched-pair block could not be evaluated as a neutrality test. This
amendment records the repair, the two new zero-in-run-I/O blocks (R2 and the
pre-registered extension R3) and the resulting certification. The original
record above is preserved: nothing was rewritten or deleted.

### A.1 What was repaired (CODE FACT)

* The flush period now defaults to `0`: no flush thread exists, a created
  constraint only fills a plain struct under a short lock, and the buffer is
  serialised **once at shutdown**. There is therefore no file I/O, allocation
  burst or string work on the constraint-creation path during a run.
* The graph dump is written from the mapper's own processing thread and from the
  destructor, never from the maintenance thread: reading the pose graph from a
  foreign thread can block against the mapper's work (observed: a 0-byte dump and
  an unresponsive mapper).
* `SetPoseGraphDumpPath` is now called after the mapper is constructed; before, a
  configured dump path was silently ignored and no dump was ever written.
* Verified on real output: `karto_edge_provenance.jsonl` for the first N1 episode
  contains 252 records (116 `constraint_created`), every required schema field
  present, strictly increasing unique `creation_sequence`, all 3x3 covariances
  finite; the instrument-off arm writes no provenance file at all.

### A.2 Same-input replay (MEASURED — the decisive evidence)

60 accepted keyscans were recorded from a real episode (`/karto_out` carries
exactly the scan plus the odometric pose Karto processed) and replayed twice per
arm through `nav2d_karto/mapper` with identical parameters.

| quantity | OFF vs ON |
| --- | --- |
| node count | 60 vs 60 |
| edge count | 98 vs 98 |
| node id set | identical |
| edge endpoint set | identical |
| edge insertion order | identical |
| node pose max difference | `0.0` |
| SE(2) measurement max difference | `0.0` |
| covariance max difference | `0.0` |
| same-arm replay repeatability | `0.0` (so the pipeline is deterministic under replay) |

Verdict: `REPLAY_NEUTRALITY_CERTIFIED`
(`results/realizability_pilot/p1_dir_dec_v8_20260916/replay_same_input/`).

This removes scheduler, planner, navigation and Stage variability entirely: for a
bit-identical input the instrument does not change one node, one edge, one
measurement or one covariance.

### A.3 Online block (MEASURED, and why it cannot decide)

| block | seeds | ON−OFF final edges | ON−OFF target geodesic (m) | pairs matched? |
| --- | --- | --- | --- | --- |
| pre-repair (flush 5 s) | 41001, 41002 | +4, −1 | −2.80, −2.15 | 1 of 2 (route dev 0.041 m) |
| R2 (zero I/O) | 41001, 41002 | −14, −6 | +1.36, +2.90 | 0 of 2 (0.103 / 0.212 m) |
| R3 (extension, zero I/O) | 41003, 41004 | +22, −9 | −2.36, +1.74 | 0 of 2 (0.189 / 0.339 m) |

The pre-registered comparability gate (`node_count_abs_tolerance` 2,
`edge_count_relative_tolerance` 0.15, `route_node_position_abs_tolerance_m`
0.05) failed in 3 of the 6 recorded pairs, including both R2 pairs and both R3
pairs: the two arms of a seed did not enter the probe from the same state, so a
paired difference cannot be attributed to the instrument.

The extension rule was written down **before** R3 was collected
(`n0_extension_preregistration.json`): pause only if *all four* pairs show a
same-sign, non-zero difference on the same watched outcome with a mean beyond the
measured repeatability; otherwise the block reflects run-to-run variability and
the replay decides. Result: signs are mixed on all four watched outcomes
(edges `[-14, -6, +22, -9]`, nodes `[-6, -2, +11, -4]`, keyscans `[-4, 0, +1, -2]`,
geodesic `[+1.36, +2.90, -2.36, +1.74]`) → no pause.

Same-condition spread across the four runs of one condition is larger than any
cross-arm mean difference: edges ON 69–96 (range 27), OFF 73–105 (range 32).

**UNKNOWN** (recorded rather than resolved): a closed-loop timing effect smaller
than this spread is not excluded by the online block. The replay does not address
it either, because it deliberately removes the closed loop.

### A.4 Certification

```
Measurement Gate:          CERTIFIED  (OUTCOME_MEASUREMENT_STABLE)
Decided by:                same-input replay (bit-identical graphs)
Online block:              unusable as a neutrality test (0 of 4 pairs matched);
                           unfiltered reading recorded as ONLINE_SANITY_PASSED
Intervention Hypothesis:   NOT YET TESTED at the time of certification
```

Artefacts: `n0_certification_decision_final.json`,
`n0_extension_decision.json`, `n0_extension_preregistration.json`,
`replay_same_input/replay_comparison.json`, `n0r2_sanity/`, `n0r3_sanity/`.

## Amendment (2026-09-17, third): N1-B executed under the certified instrument

**Why this amendment exists.** The second amendment certified the instrument and
cleared the frozen N1-B suite to run. This amendment records what the frozen
suite actually produced. Nothing above was rewritten or deleted.

### A.5 What ran (CODE FACT)

The suite `results/realizability_pilot/p1_dir_dec_v8_20260916/n1_blocks` was
executed unchanged: the same two anchors (`map3_grid_anchor_01`,
`map3_grid_anchor_03`), the same three actions (A0 `pass`, A1 budget-matched
neutral 2 x 1.5 m away-and-back, A2 Sweep90 -30/0/+30 deg), the same four block
seeds, the same frozen target segment and the same pre-registered tolerances.
The runner defaults resolved the instrumentation to the certified
configuration: provenance enabled, pose-graph observer enabled, zero in-run I/O.

### A.6 Technical validity of the episodes (MEASURED)

Every episode must pass an independent ground-truth pose check at each commanded
goal (position 0.75 m, heading 0.35 rad) in addition to the navigator's own
success report.

| arm | attempts | failed attempts |
| --- | --- | --- |
| A0 baseline | 5 | 3 |
| A1 budget-matched neutral | 6 | 4 |
| A2 Sweep90 | 6 | 3 |

Seven episodes succeeded; five were finalised as `TECHNICAL_INVALID_FINAL` after
bounded retries. Three distinct mechanisms were measured:

* **map translation offset** - episode 0006 failed three times with ground-truth
  position errors of 0.841 / 0.812 / 0.751 m while TF reported 0.144-0.220 m and
  the mapper's own corrected pose sat 0.011-0.267 m from the commanded map
  target: the mapper believed it was at the target while the simulated robot was
  ~0.8 m away from it.
* **map frame rotation** - episodes 0008 (0.583 / 0.798 rad), 0010 (0.431 /
  0.603 rad), 0011 (0.576 rad) and 0012 (0.611 rad) failed the heading criterion
  although position was fine. The measured map-to-world rotation at the probe
  pose of the *same* route was +0.208 rad in a neighbouring successful episode
  and +0.345 / -0.319 rad in two failed attempts: the mapper frame itself is
  rotated by up to about 20 degrees relative to the world and is not reproducible
  between runs of the same route.
* **route execution** - episode 0009 failed with GT 0.613 m / 0.643 rad while the
  map frame was nearly aligned (0.089 rad). Its block was already unusable.

No tolerance was changed at any point; failures were recorded, not argued away.

### A.7 Pre-probe comparability of the blocks (MEASURED)

Of the four planned blocks:

| block | arms available | pre-probe verdict |
| --- | --- | --- |
| anchor_01 / seed42001 | baseline, neutral, sweep | **rejected**: baseline-neutral differ by 19 nodes / 50.6 % of edges and the frozen target segment has 12 vs 5 scans; baseline-sweep differ by 18 nodes / 46.9 %; neutral-sweep by 0.133 m of route displacement |
| anchor_01 / seed42002 | baseline, sweep | neutral arm technically invalid |
| anchor_03 / seed42003 | neutral | sweep and baseline arms technically invalid |
| anchor_03 / seed42004 | sweep | baseline and neutral arms technically invalid |

Zero blocks carry a usable `sweep - neutral` contrast.

### A.8 Direction gate (state, not a verdict about the hypothesis)

```
state:  INCONCLUSIVE_NEEDS_ONE_MORE_CONTROL
reason: the frozen N1 suite was executed but no block yielded a usable
        sweep-minus-neutral contrast
```

The gate abstains. This is deliberate and was recorded before the gate was
evaluated on the collected block table (see below): with no evaluable block there
is no evidence about the intervention, so neither `PROCEED_TO_MODELING` nor
`STOP_DIRECTION` is justified. The first N0 round taught the same lesson in the
other direction: a *measurement* failure must never be reported as a
*scientific* failure.

Also fixed in the gate code in this round (no threshold and no outcome
definition touched): blocks whose pre-probe graphs failed the comparability gate
are now excluded from the contrast instead of being silently averaged in, and an
empty contrast now abstains instead of falling through to the "sweep does not
beat neutral" branch.

### A.9 What this round established

* The instrumentation question is settled for the constraint-generation
  subsystem: identical input, identical graph, bit for bit.
* N1-B was executed as frozen, but this environment cannot currently support its
  matched-block design: the mapping phase of the same route is not reproducible
  (frame translation up to ~0.8 m, frame rotation up to ~0.35 rad, occasionally
  2-10 extra pre-probe keyscans), so the pre-registered validity and
  comparability requirements reject a large share of the arms.
* Consequently the intervention hypothesis remains **untested**, exactly as it
  was after the first N0 round - but now the blocking limitation is measured and
  named rather than suspected.

## Amendment (2026-09-17, fourth): post-hoc frame semantics audit

This amendment audits the interpretation in A.6 without changing any old episode,
gate, status, or direction decision. The machine-readable evidence is under
`results/realizability_pilot/p1_common_prefix_v9_20260917/frame_gauge_audit/`.

### A.10 What the old gate actually compared (CODE FACT)

The old `move_to` gate did **not** directly subtract a map-frame target from a
Stage-world pose. It compared the terminal Stage ground-truth robot pose with a
separately supplied Stage-world `expected_gt_pose`. Therefore the initial audit
hypothesis -- a direct `map`/`world` coordinate subtraction bug -- is not supported.

The actual protocol defect is a correspondence assumption. Navigation targeted a
frozen Karto keyscan anchor, while the ground-truth gate used the historical waypoint
endpoint's previously observed Stage pose as if it were the same physical pose as that
anchor. The anchor was selected by position only. Across the 17 attempts, the
transformed map anchor and that claimed historical world target differ by median
0.427 m and 0.060 rad, with maxima 0.709 m and 0.667 rad. Thus a robot can reach the
map anchor and still fail a world-pose gate attached to a different physical pose.

### A.11 SE(2) gauge result (MEASURED)

A no-scale SE(2) fit from the four history endpoint pairs was available for all 17
attempts. Its history-only residual is small (position RMSE median 0.022 m, maximum
0.098 m; heading RMSE median 0.0063 rad, maximum 0.0235 rad). The estimated transform
has median translation `(-28.030, -27.952) m` and median yaw `-0.0064 rad`.

Transforming the current map goal into Stage world reduces the diagnostic probe error
to median 0.181 m / 0.073 rad (maximum 0.324 m / 0.215 rad), and all 17 attempts are
inside the old 0.75 m / 0.35 rad arrival tolerance with respect to that transformed
current goal. This shows that the apparent raw errors do not prove that the robot
failed to reach the current map goal. It does **not** validate the historical target
correspondence used by the old gate.

The result-blind audit classification is 2 `G0_FRAME_ALIGNED`, 0 `G1_GAUGE_DOMINATED`,
and 15 `G2_TRUE_TRAJECTORY_OR_MAP_DIVERGENCE`. `G1` is intentionally empty because
the old raw gate already compared two Stage-world quantities; applying a global gauge
transform cannot repair the anchor-to-historical-pose correspondence assumption.

### A.12 Structural divergence remains (MEASURED)

All four old N1 blocks contain non-identical pre-probe graph signatures. Node counts,
edge endpoint topology, keyscan sequence, and target scan sets differ across arms.
A global SE(2) transform can explain coordinate gauge, but it cannot create or remove
nodes and edges. The old matched-arm N1 therefore remains
`INCONCLUSIVE_NEEDS_ONE_MORE_CONTROL`, and every old `TECHNICAL_INVALID` label is
preserved without retrospective relabelling.
