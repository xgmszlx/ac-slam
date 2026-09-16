# Constraint-generation provenance audit

Date: 2026-09-16  
Scope: outcome-definition stabilization only  
Suite: `results/realizability_pilot/p1_preflight_v7_20260916`  
Evidence status: `ANALYZED_NOT_INDEPENDENTLY_VERIFIED`

## Decision

`PAUSED_OUTCOME_DEFINITION_NOT_STABLE`

The edge-level outcome can now be defined without using an explicit
`TryCloseLoop` callback as a proxy. However, the larger factorial screen remains
blocked: only three of four frozen sentinel conditions have a valid outcome,
and the diagnostics/provenance OFF/ON comparison uses different pre-existing
sequence-derived TSP seeds (`31001` and `31002`). It therefore cannot isolate a
causal instrumentation effect.

No planner objective, active-loop selection, prior graph, robot revisit action,
skip/replan logic, Karto matcher threshold, or graph-connectivity decision was
changed in this audit.

## Evidence language

- **[Code fact]** follows directly from the checked source control flow.
- **[Measured observation]** follows from saved sentinel artifacts.
- **[Inference]** combines code and measured evidence.
- **[Unknown]** is not recoverable from the saved evidence.

## Source-level constraint-generation map

### Call order

**[Code fact]** For an accepted laser keyscan, `OpenMapper::Process` executes:

```text
sequential MatchScan against running scans
  -> MapperSensorManager::AddLocalizedObject (assign state/unique ids)
  -> MapperGraph::AddVertex (and ScanSolver::AddNode)
  -> MapperGraph::AddEdges
       -> PREVIOUS_SCAN
       -> RUNNING_SCAN_CHAIN
       -> LinkNearChains -> NEAR_CHAIN
  -> MapperSensorManager::AddRunningScan
  -> MapperGraph::TryCloseLoop
       -> FindPossibleLoopClosure
       -> coarse loop matcher
       -> fine sequential matcher
       -> TRY_CLOSE_LOOP constraint if accepted
       -> CorrectPoses if accepted
  -> CorrectPoses fallback if TryCloseLoop returned false
```

`LinkObjects` is the single constraint insertion point. It first calls
`AddEdge`; an existing edge receives `AddCovariance`, but only
`isNewEdge == true` receives a `LinkInfo`, calls
`m_pScanSolver->AddConstraint(pEdge)`, and emits a provenance record. No stable
numeric Karto edge ID is invented; the observer identity is the directed
`[source_state_id, target_state_id]` pair at first creation.

### Creation paths

| Provenance | Source call site and matcher | Acceptance before `LinkObjects` | Timing | Covariance | Can link history? | Optimization |
| --- | --- | --- | --- | --- | --- | --- |
| `PREVIOUS_SCAN` | `AddEdges(scan)`; sequential running-buffer match computed in `Process` | No additional link threshold | Before `TryCloseLoop` | Sequential matcher covariance passed by `Process` | Normally previous keyscan only | Enters solver; later `CorrectPoses` |
| `RUNNING_SCAN_CHAIN` | `AddEdges(scan)` -> `LinkChainToScan(runningScans)`; closest running scan | Closest endpoint must be within `LinkScanMaximumDistance=10 m`; no response threshold at this link | Before `TryCloseLoop` | Same sequential running-buffer covariance | Yes; observed in target history | Enters solver; later `CorrectPoses` |
| `NEAR_CHAIN` | `LinkNearChains`; sequential matcher against a spatial near chain | Chain size at least 4; response `> 0.6 - KT_TOLERANCE`; closest endpoint within 10 m | Before `TryCloseLoop` | Near-chain sequential matcher covariance | Yes; observed in target history | Enters solver; later `CorrectPoses` |
| `TRY_CLOSE_LOOP` | `TryCloseLoop` -> `LinkChainToScan`; loop coarse matcher then sequential fine matcher | Candidate search within 4 m after near-linked exclusion; coarse response/variance gate, then fine response `>= 0.7` | Inside `TryCloseLoop` | Fine matcher covariance | Yes | Enters solver and immediately calls `CorrectPoses` |
| `FIRST_SCAN_CROSS_SENSOR` | First scan of a sensor matched to another sensor | `LinkObjects` is called before response is used for the weighted-mean gate | Before `TryCloseLoop` | Cross-sensor sequential matcher covariance | Cross-sensor history only | Enters solver; later `CorrectPoses` |
| `CUSTOM_OBJECT_LAST_SCAN` | Non-laser custom object linked to last sensor scan | Last scan exists | Before explicit loop search | Loose diagonal `MAX_VARIANCE` covariance | Possible for custom objects | Enters solver; later graph correction path |
| `OTHER` | Defensive enum value | No current creation call site | N/A | N/A | Unknown | N/A |

The current mapper parameters relevant here are:

```text
LinkMatchMinimumResponseFine = 0.6     (OpenKarto default; not overridden)
LinkScanMaximumDistance = 10.0 m       (OpenKarto default; not overridden)
LoopSearchMaximumDistance = 4.0 m
LoopMatchMinimumChainSize = 4
LoopMatchMinimumResponseCoarse = 0.6
LoopMatchMinimumResponseFine = 0.7
LoopMatchMaximumVarianceCoarse = 0.16
```

The coarse loop gate also contains the existing alternate branch:
response `> 0.9 * 0.6` with both XY variances `< 0.01 * 0.16`.
No value was changed.

### Marker boundary

**[Code fact]** `/Mapper/closure_edges` is a visualization split based on
whether an edge appears as the next sequential vertex pair in the graph's edge
iteration. Its non-sequential marker can therefore contain `RUNNING_SCAN_CHAIN`
and `NEAR_CHAIN` edges as well as `TRY_CLOSE_LOOP` edges. Marker membership is
not creation provenance and is not by itself a loop-closure ground truth.

## Observation-only instrumentation

The default-disabled instrumentation adds:

- exact state and unique endpoints for every newly created edge;
- creation path, function, stage, matcher response/threshold when applicable;
- relative measurement and full 3x3 covariance;
- solver insertion flag, creation sequence, graph edge count, wall/sim time,
  and probe phase;
- pre/post `TryCloseLoop` graph edge sets and the exact pre-loop
  `nearLinkedScans` set already computed by the original candidate path;
- unique IDs on the default-disabled full pose-graph observer;
- forced publication through the existing `/get_map` service immediately before
  the before/after evidence cuts.

The TBB near-chain branch stores its already-computed matcher response for
logging. The response is not recomputed and the original boolean acceptance
array controls linking exactly as before. Provenance logging occurs only after
the original solver insertion in the `isNewEdge` branch. Existing-edge
covariance accumulation is not logged as new constraint creation.

## Frozen target attribution

Before each probe, the runner freezes `H_target` with state IDs, unique IDs,
corrected poses, selection rule, and time. The deterministic attribution is:

```text
TARGET_ATTRIBUTABLE:
  source state in frozen H_target
  AND, when available, source unique id in frozen H_target
  AND target state is post-freeze

WRONG_TARGET_HISTORICAL:
  source is a pre-freeze non-target state
  AND target is post-freeze
  AND state gap > 1

ORDINARY_RECENT_OR_SEQUENTIAL:
  state gap == 1 OR source is post-freeze

AMBIGUOUS:
  everything else; never forced into target success
```

These are independent primitive labels. An episode is not forced into one
exclusive category.

## Sentinel status

| Condition | Selected attempt | Scientific status | Target constraints | Explicit | Non-explicit | Wrong-target | Notes |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| baseline diagnostics OFF | 02 | VALID | 3 | 0 | 3 | 12 | Historical v7 run; exact graph evidence, but provenance was not yet recorded |
| baseline diagnostics ON | 01 | VALID | 3 | 0 | 3 | 13 | All 3 target edges are `RUNNING_SCAN_CHAIN` |
| align 60 diagnostics ON | none | TECHNICAL_INVALID_FINAL | N/A | N/A | N/A | N/A | Attempts 01/04 failed frozen Stage-GT arrival; attempt 02 had stale observer cut; attempt 03 stopped before intervention due wrong refresh service name |
| sweep 90 diagnostics ON | 02 | VALID | 9 | 0 | 9 | 13 | 3 `RUNNING_SCAN_CHAIN`, 6 `NEAR_CHAIN` |

Across the three valid outcomes: 15 target-attributable constraints, 0 explicit
target constraints, 15 non-explicit target constraints, 38 wrong-target
historical constraints, 66 ordinary recent/sequential constraints, and 0
ambiguous constraints. All 15 saved target covariances are mathematically
positive definite; this is a validity statement, not a claim of high measurement
quality.

For the 12 target constraints with direct creation provenance:

- 6 are `RUNNING_SCAN_CHAIN`;
- 6 are `NEAR_CHAIN`;
- all 12 have `solver_add_constraint_called=true`;
- all 12 are already in the graph at the pre-`TryCloseLoop` context;
- all 12 historical source scans are in the exact pre-loop
  `near_linked_scan_ids` set;
- all full-graph edge sets reconcile exactly with the creation-record prefix at
  the observer cut.

The three diagnostics-OFF edges `16->38`, `13->39`, and `14->47` remain
`UNKNOWN_NOT_RECORDED` for creation subtype. Their provenance is not guessed
retroactively.

## Diagnostics/provenance perturbation check

**[Measured observation]** The frozen OFF/ON baseline action definition and
executed waypoint labels match. Both actions completed, both have zero explicit
`TryCloseLoop` events, and both realized three target constraints. ON minus OFF:

```text
after nodes       +1
after edges       +3
new probe edges    0
target edges       0
probe distance    +0.659 m
probe duration    -1 s
```

**[Unknown]** This does not establish causal non-perturbation. The OFF run did
not record provenance and the frozen runner used different sequence-derived TSP
seeds (`31001` versus `31002`). With one pair, stochastic Stage/ROS variation
also cannot be separated from instrumentation. The result is therefore
`INCONCLUSIVE_FOR_CAUSAL_NON_PERTURBATION_SINGLE_PAIR_SEED_CONFOUNDED`, not
"instrumentation proven harmless."

## Effect on the old Phase 2C interpretation

**[Fact]** Old `CHAIN_TOO_SHORT`, `COARSE_LOW_RESPONSE`, and accepted-event
labels describe outcomes inside the explicit `TryCloseLoop` pipeline.

**[Measured observation]** In the new valid provenance runs, 12 target-related
ordinary constraints were created before `TryCloseLoop`; their source scans were
then present in the near-linked exclusion set. Thus the mechanism

```text
ordinary AddEdges historical link
  -> source becomes graph-near-linked
  -> FindPossibleLoopClosure excludes it
  -> no explicit TryCloseLoop acceptance
```

does occur in this implementation.

**[Inference]** Some old C3/no-chain observations may mean only that the
explicit-loop pathway did not run, not that no target-related pose-graph
constraint was realized. This does not retroactively relabel all 21 old active
loops as successes because their exact edge creation provenance was not saved.

## Q1--Q8

### Q1 — What created the non-explicit target constraints?

**[Measured observation]** Of 12 fresh edges with direct provenance, 6 came
from `RUNNING_SCAN_CHAIN` and 6 from `NEAR_CHAIN`. The three older baseline-OFF
edges are `UNKNOWN_NOT_RECORDED`.

### Q2 — Can ordinary AddEdges create historical constraints first?

**[Code fact + measured observation]** Yes. Both observed creation paths execute
inside `AddEdges` before `TryCloseLoop`, and exact pre-loop contexts contain the
new edges.

### Q3 — Did those constraints enter the solver/optimization path?

**[Measured observation]** Yes for all 12 provenance-known target constraints:
the solver insertion flag is true and the full graph reconciles exactly. With no
accepted explicit loop, `Process` subsequently follows its normal
`CorrectPoses` fallback. This says they entered graph optimization; it does not
claim they caused a useful trajectory correction.

### Q4 — Were their historical scans excluded as near-linked afterward?

**[Measured observation]** Yes for all 12 provenance-known target constraints.
Each source is present in the exact `nearLinkedScans` set used by the subsequent
`FindPossibleLoopClosure` call.

### Q5 — Can TryCloseLoop failure proxy for no target constraint?

No. All three valid episodes have zero explicit target constraints yet have
3, 3, and 9 target-attributable pose-graph constraints.

### Q6 — Is target realization repeatable in the remaining sentinels?

It is observed in all three valid outcomes (3/3), with 15 non-explicit target
constraints and no explicit target constraint. The fourth planned condition has
no valid outcome, so four-condition repeatability is not established.

### Q7 — Is instrumentation detectably perturbing behavior?

No material pairwise qualitative divergence was observed, but the causal answer
is inconclusive because the single OFF/ON pair has different seeds and only the
ON run records provenance.

### Q8 — Is the outcome definition ready for a factorial screen?

The exact edge-level Layer-A definition is usable:

```text
target_constraint_realized :=
  at least one newly created solver constraint at the frozen observer cut
  whose source state/unique identity belongs to pre-frozen H_target
  and whose target is post-freeze
```

`TRY_CLOSE_LOOP` is retained as a separate provenance subtype. Covariance and
information-matrix quantities remain descriptive Layer-B outcomes.

The experiment is nevertheless **not ready to scale** because the required
instrumentation non-perturbation comparison is confounded and the 60-degree
sentinel has no valid post-repair outcome.

## Evidence files

- `results/realizability_pilot/p1_preflight_v7_20260916/edge_provenance_schema.json`
- per-run `karto_edge_provenance.jsonl` under each instrumented attempt
- `results/realizability_pilot/p1_preflight_v7_20260916/sentinel_edge_ledger.csv`
- `results/realizability_pilot/p1_preflight_v7_20260916/sentinel_constraint_summary.csv`
- `results/realizability_pilot/p1_preflight_v7_20260916/diagnostics_perturbation_check.json`
- `results/realizability_pilot/p1_preflight_v7_20260916/observer_validation_summary.json`
- `results/realizability_pilot/p1_preflight_v7_20260916/target_attribution_audit.json`
- `results/realizability_pilot/p1_preflight_v7_20260916/pilot_episodes.csv`

## Verification

The final verification commands are:

```bash
cd /home/wcqw/ac-slam/catkin_ws && catkin_make -DCMAKE_BUILD_TYPE=Release
cd /home/wcqw/ac-slam && /usr/bin/python3 -m unittest tools.realizability_pilot.test_pilot -v
cd /home/wcqw/ac-slam && /usr/bin/python3 -m py_compile tools/realizability_pilot/*.py
cd /home/wcqw/ac-slam && git diff --check
```

Final results: catkin build passed with system `/usr/bin/python3` 3.8.10;
18/18 ROS-free unit tests passed; all pilot Python files compiled; the analyzer
regenerated four sentinel rows and 119 probe-period edge rows; `git diff
--check` passed. No ROS/Stage/pilot worker remained after the suite stopped.

This round intentionally stops here. It does not run the factorial screen and
does not propose a planner modification.
