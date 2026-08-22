# Phase 2C: Karto loop-closure failure mechanism (confirmed rejection taxonomy)

Date: 2026-08-22

## 1. Research question

> 为什么执行成功的 active-loop action（规划 → 回访 → waypoint 完成）没有稳定兑现为 Karto accepted loop closure？

Phase 2C upgrades the Phase 2B "Probable" opportunity/matching failure labels into a
**Confirmed rejection taxonomy** by adding observation-only instrumentation inside
Karto (`TryCloseLoop` / `FindPossibleLoopClosure`) and running five new map3 SLAM-aware
runs (seeds 21001–21005, same Concorde seeds and TSPs as Phase 2A).

## 2. Baseline invariance

- The only source changes are the Phase 2C observation-only diagnostics
  (navigation_2d commit `8ae4895`; baseline `mapper.yaml` + launch args at `b9d5337`/
  `547ea24`), default off. See `11_phase2c_instrumentation_audit.md` for the file-by-file
  audit.
- No matcher threshold, if condition, candidate selection/ordering, chain construction,
  return value, optimization, planner, prior graph, or objective was modified.
- `enable_loop_diagnostics=false` (default) leaves behavior byte-for-byte unchanged.

## 3. Instrumentation design

- JSONL per loop search (`karto_loop_diagnostics.jsonl`): one record per candidate-chain
  attempt plus one no-chain record, with `scan_id`, pose/yaw, historical-scan counts
  (considered / in-distance / near-linked), chain size and scan-index gaps, coarse
  response + x/y variance + coarse pass/reason, fine response + pass, accept/reject
  stage and reason.
- Reject reasons are derived after the fact from the same values the original branch
  already computes (COARSE_LOW_RESPONSE / COARSE_HIGH_VARIANCE / COARSE_ALT_REJECT /
  FINE_LOW_RESPONSE / NO_SPATIAL_CANDIDATE / ALL_CANDIDATES_NEAR_LINKED / CHAIN_TOO_SHORT).
- Sim-time anchors: `PHASE2C_KEYSCAN_ACCEPTED` INFO logs in `MultiMapper.cpp` map each
  accepted keyscan to its ROS/sim timestamp, so diagnostics records can be aligned to
  planner loop events.
- See `10_karto_rejection_pipeline.md` for the full pipeline map.

## 4. Positive-control validation

**Gate A (revised per Phase 3A audit 13): ACCEPTED-path instrumentation validated;
explicit positive-control validation incomplete (environmental blocker).**

The explicit Phase 2B-protocol positive control could not be completed on this host
(5 attempts): two MoveTo navigation timeouts during the revisit, and three exploration
timeouts caused by the Stage simulator intermittently running at ~0.2x real time (an
environmental issue confirmed with an isolated Stage running at 4.88x wall/sim with no
other nodes; identical instrumentation ran at 1.00x in an earlier trial).

The ACCEPTED diagnostics path was validated by a **real accepted closure in the
seed_21001 SLAM-aware run**:

| | Diagnostics record | Accepted callback |
|---|---|---|
| time | scan 679 @ sim 1297.7 | "Add one Loop closure. 1 loops have been added." @ sim 1297.7 |
| match | ACCEPTED (chain 429-434, size 6, gap 245-250, coarse 0.6573, fine 0.9274) | 1 event |

Structured ACCEPTED events (1) == accepted callbacks (1), with full internals recorded.
This is a 1:1 validation that the instrumentation records accepted closures correctly.
It does **not** substitute for an explicit positive-control validation, which remains
uncompleted for environmental reasons (see `13_phase2c_scientific_audit.md`, Audit 2).

Also validated structurally: all diagnostics records parse, scan ids are monotonic,
counters are internally consistent, and no-chain reject reasons match their counts.
The diagnostics `scan_yaw` field is **invalid** (always 0.0; barycenter-pose heading);
all orientation statistics in this report use trajectory-derived yaw (see Audit 5).

## 5. Experiment reproducibility

| Seed | Status | TSP vs Phase 2A | Loops planned | Executed | Diagnosed | Accepted (run) |
|---|---|---:|---:|---:|---:|---:|
| 21001 | SUCCEEDED | exact (SHA-256 match) | 4 | 4 | 4 | 1 (active, loop 4) |
| 21002 | SUCCEEDED | exact | 3 | 3 | 3 | 0 |
| 21003 | SUCCEEDED | exact | 4 | 4 | 4 | 1 (passive, between loops) |
| 21004 | SUCCEEDED | exact | 5 | 5 | 5 | 0 |
| 21005 | SUCCEEDED | exact | 5 | 5 | 5 | 0 |
| **Total** | 5/5 | 5/5 exact | **21** | **21** | **21** | **2 callbacks** |

- TSP records validated against `results/phase2/map3_pairs/pair_*/slam_aware/tsp_record.json`
  (solver, seed, initial/full path, predicted length, SHA-256) — all `exact_phase2a_rerun: true`.
- Environment: system Python 3.8.10, ROS Noetic, navigation_2d `8ae4895`, baseline `547ea24`.
- All 21 loops were executed with all waypoints reached; reliable-loop service OK.

## 6. Active-loop counts

21 planned / 21 executed. Karto accepted 2 closures in these five new runs (1 during an
active loop in seed_21001; 1 passive between loops in seed_21003). The frozen
observer-based success rule (`karto_closure_events_during_execution > 0` AND a new
pose-graph edge with gap > 70) reports 0/21 because the incremental `/slam_pose_graph`
stream misses the long-gap edge; the direct diagnostics are the ground truth and record
the active closure in seed_21001 loop 4 (chain gap 245-250 ≫ 70).

## 7. Confirmed failure taxonomy

All 21 loops have direct Karto internal evidence → **all Confirmed**:

| Subclass | Meaning | Count |
|---|---|---:|
| C3 | Candidate scans exist but no valid chain ≥ 4 formed (dominant) | 12 |
| D1 | Chain formed but coarse response too low (< 0.60) | 8 |
| S | Accepted successful active loop | 1 |
| C1/C2/C4/D2/D3/D4/D5/U | — | 0 |

No loop was dominated by coarse variance (D2), the alternate coarse branch (D3), or fine
rejection (D4): in every chain attempt that reached the matcher, rejection was the low
**coarse response**, not variance or fine.

## 8. Per-loop evidence

Per-loop rows are in
`results/phase2c/map3/aggregate/active_loop_confirmed_taxonomy.csv` (run, seed, loop_id,
vertex, A-H min distance, delta yaw, overlap, candidate/near-linked/chain counts, max
chain size, best coarse response + variance, best fine response, subclass, evidence
level, direct evidence, vote tally, deepest stage reached).

Examples:

- seed_21001 loop 1 (v15): **D1** — 15/22 records vote D1; best coarse 0.382 (< 0.6);
  A-H 0.097 m, overlap 0.447. Chains of size 4-8 formed but coarse response too low.
- seed_21001 loop 3 (v8): **C3** — 26/27 records CHAIN_TOO_SHORT; overlap 0.746 (high)
  yet chains did not form; only 1 chain (coarse 0.477) reached the matcher.
- seed_21001 loop 4 (v26): **S** — scan 679 chain 429-434 coarse 0.657 (> 0.6), fine
  0.927; accepted at loop finish (sim 1297.7). A-H 0.011 m, |yaw| 0.18 rad.
- seed_21002 loops 1-3: **C3** (votes 25/13/15 C3) with D1 minority — opportunity
  dominates.
- seed_21004 loop 4 and seed_21003 loop 3 (old "F Unknown"): now **D1/C3 Confirmed**.

## 9. Phase 2B → Phase 2C label revision (replication-level)

`results/phase2c/map3/aggregate/failure_transition_matrix.csv`. Per the Phase 3A
audit (`13_phase2c_scientific_audit.md`, Audit 1), this is a **replication-level
comparison**: Phase 2C runs are independent re-runs of the same seeds (same TSP, same
planned loop vertices, but different waypoint counts, timings and trajectories). It is
**not** an event-level relabeling of the same physical loop events. Wording in earlier
drafts ("Phase 2B label proven wrong") is withdrawn.

| Old Phase 2B | New Phase 2C (all Confirmed, new runs) | Count |
|---|---|---:|
| C. Opportunity failure (Probable) | D1 | 5 |
| C. Opportunity failure (Probable) | C3 | 5 |
| D. Matching failure (Probable) | C3 | 6 |
| D. Matching failure (Probable) | D1 | 2 |
| D. Matching failure (Probable) | S | 1 |
| F. Unknown | C3 | 1 |
| F. Unknown | D1 | 1 |

**Supported statement:** Phase 2B's offline taxonomy has limited predictive power for
the actual internal rejection mechanism observed in independent re-runs of the same
planned loops (half of the old "opportunity" cases behave as D1, most of the old
"matching" cases behave as C3 in the new runs). The Phase 2C C3/D1 assignments are
direct Karto-internal evidence for the *new* runs only.

## 10. Opportunity-generation findings

- The robot reached the service-selected history in all 21 loops (A-H min distance
  mean 0.126 m, median 0.090 m, max 0.836 m) — "robot never got there" is not the cause.
- Historical spatial candidates existed in all 21 loops (in-distance max mean 13.7,
  median 13) and near-linked filtering removed 4-16 (mean 7.9) of them.
- Yet 12/21 loops are dominated by **CHAIN_TOO_SHORT**: candidate scans exist, but the
  running chain never reached 4 consecutive non-near-linked scans within 4 m. Loop 3 of
  seed_21001 has overlap 0.746 and A-H 0.034 m yet 26/27 records are CHAIN_TOO_SHORT —
  strong evidence of an opportunity-generation bottleneck independent of proximity.
- No C1 (no spatial candidate) and no C2 (all near-linked) dominated loops.

## 11. Matching findings

- 20/21 loops formed at least one candidate chain that reached the coarse matcher.
- **The single dominant matching rejection is low coarse response (D1)**: best coarse
  response per loop is mean 0.437 / median 0.417 (range 0.307-0.657); every failed loop
  peaked below the 0.60 threshold, and the accepted loop peaked at 0.657.
- Coarse variance is NOT the bottleneck: minimum x/y variance across loops is
  median 0.0026 m² — far below the 0.16 threshold in almost every attempt.
- Fine rejection (D4) did not occur: the only loop that passed coarse (seed_21001 loop 4)
  also passed fine (0.927 ≥ 0.70).

## 12. Main bottleneck

**Coarse scan-response thresholding, conditioned on chain formation.** Concretely:

1. Chain formation (opportunity) is the binding constraint in 12/21 loops (C3): the
   active revisit does not reliably produce 4+ consecutive non-near-linked historical
   scans within the 4 m window, even when spatial overlap is high.
2. When a chain does form (20/21 loops reach coarse), the coarse response is almost
   always far below 0.60 (mean best 0.437), so Karto rejects the closure (D1 in 8/21
   loops as the dominant cause, and present as a minority in most C3 loops).

In other words, the failure is a **combination (C) of opportunity generation and
matcher rejection** (see Q3), with chain formation as the more frequent primary gate and
low coarse response as the consistent secondary gate. The one successful active loop
(seed_21001 loop 4) had both a valid chain (size 6, gap 245-250) and coarse 0.657 —
i.e., closure succeeds when both gates pass.

## 13. Remaining unknowns

1. Why chain formation fails despite high spatial overlap (near-linked exclusion
   dynamics, keyscan spacing, corridor topology) is not isolated by this phase — only
   the counters are recorded, not the topological cause.
2. Whether the coarse-response deficit reflects laser/view overlap, heading mismatch,
   or the search-window/smear settings is not decomposed (no causal claim is made).
3. The explicit positive control could not be run to completion on this host; Gate A was
   validated via the seed_21001 active closure instead. The passive closure in seed_21003
   (sim 1176.7, 1.2 s after loop 3 finished) is recorded but not attributed to any loop.
4. Run-to-run non-determinism: seed_21001 produced an active closure while Phase 2A pair
   1 (same seed) produced none — the exploration trajectories differ between runs, so
   loop-outcome correspondence is at the aggregate/loop-index level, not identical trials.

## 14. Phase gate

| Gate | Criterion | Result |
|---|---|---|
| A | Positive-control / instrumentation ACCEPTED validation | **PASS** (1:1 via seed_21001 active closure; PC blocked environmentally) |
| B | ≥ 80% active loops aligned to diagnostics | **PASS** (21/21 = 100%) |
| C | ≥ 70% failures localized to a rejection stage | **PASS** (20/20 failures localized: C3 or D1, all Confirmed) |
| D | Instrumentation diff does not change baseline | **PASS** (`11_phase2c_instrumentation_audit.md`) |

**Phase gate decision: PASS.**

## Answers Q1-Q5

**Q1.** Old `10 Opportunity Probable / 9 Matching Probable / 2 Unknown` → New:
10 Opportunity became **5 D1 + 5 C3**, all Confirmed; 9 Matching became
**6 C3 + 2 D1 + 1 S**, all Confirmed; 2 Unknown became **1 C3 + 1 D1**, all Confirmed.
Net taxonomy: **C3×12, D1×8, S×1**, all 21 Confirmed.

**Q2.** Failures are concentrated in two stages: **chain construction (C3, 12 loops)** and
**coarse response check (D1, 8 loops)**. No failure was dominated by variance, the
alternate coarse branch, or fine matching.

**Q3.** "Robot returned near the historical pose but no closure" → **C (both)**:
opportunity generation (chain-too-short, 12 loops) AND matcher rejection (low coarse
response, 8 loops) both contribute; chain formation is the more frequent primary gate,
low coarse response the consistent secondary gate.

**Q4.** Descriptive association: **weak descriptive association**. C3 loops have notably
larger mean |delta yaw| (1.34 rad) than D1 (0.48) and the success (0.18 rad); overlap is
not clearly separating (C3 0.444, D1 0.323, S 0.352); A-H distance is small for all
classes. Sample sizes are small (n=21, success n=1), so no causal claim is made.

**Q5.** **YES** — the evidence is sufficient to enter a minimal method-design stage.
Evidence threshold: 21/21 loops have direct Karto-internal Confirmed evidence of the
rejection stage (candidate counts, chain size, coarse response/variance), 100% of
failures are localized, and the ACCEPTED diagnostics path is validated 1:1. The
bottleneck is concrete and quantifiable (chain formation + coarse response < 0.60). Any
minimal intervention would still need to be evaluated against this frozen baseline, and
this phase does not itself propose an algorithm.

## Safety / scope confirmation

- No sudo, no system-level install, no destructive git, no planner modification, no Karto
  threshold modification, no objective/prior modification, and no experimental algorithm
  was implemented in this phase.
- The only runtime intervention was observation-only diagnostics (default off) plus the
  environment-safe launch/config switches.
