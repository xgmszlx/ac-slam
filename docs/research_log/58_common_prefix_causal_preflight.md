# v9 common-prefix causal preflight

Date: 2026-09-17
Scope: one target x three actions x one branch/action, proof of experimental design
Status: `BUDGET_MATCH_INVALID`
Evidence status: `ANALYZED`, not confirmatory and not independently verified

## 1. Motivation

The old N1 independently rebuilt the mapping history for each arm. That design yielded
zero usable Sweep90-vs-Neutral blocks because the pre-treatment graphs differed in
node count, edge topology and target history. v9 tests a narrower architectural
question: can one canonical history `H` be replayed identically and then combined with
controlled physical probe streams so that only action `a` changes?

The intervention hypothesis remains `UNTESTED`. This round cannot output either
`PROCEED_TO_MODELING` or `STOP_DIRECTION`.

## 2. Why independent-history N1 failed

The post-hoc audit of all 17 old attempts found that the old arrival gate did not
directly mix map and world coordinates. It instead assumed that a nearby Karto anchor
and a historical waypoint's Stage pose were the same physical target. Their mismatch
is median 0.427 m / 0.060 rad and reaches 0.709 m / 0.667 rad. Independent histories
also have genuinely different graph structures in all four blocks. No global rigid
transform can explain different nodes and edges.

Old episode statuses, tolerances and direction decisions were not modified.

## 3. Frame/gauge audit

All 17 attempts support a history-only no-scale SE(2) fit:

| quantity | median | maximum |
| --- | ---: | ---: |
| position fit RMSE | 0.0222 m | 0.0976 m |
| heading fit RMSE | 0.00627 rad | 0.0235 rad |
| raw probe position error | 0.524 m | 0.841 m |
| transformed-current-goal position error | 0.181 m | 0.324 m |
| raw probe heading error | 0.0893 rad | 0.798 rad |
| transformed-current-goal heading error | 0.0730 rad | 0.215 rad |

Median `T_W_M` is `tx=-28.030 m`, `ty=-27.952 m`, `yaw=-0.00641 rad`. The
classification is 2 G0, 0 G1, 15 G2. The absence of G1 is deliberate: the raw old
gate was already world-vs-world, so the relevant defect is target correspondence and
independent-history divergence, not a direct frame subtraction.

Evidence: `frame_gauge_audit/frame_alignment_summary.json` and the accompanying CSVs
and figures.

## 4. Common-prefix protocol

One canonical map3 history was captured for `map3_grid_anchor_01` and stopped before
any probe. It contains 33 accepted keyscans and freezes historical target IDs
`[13, 14, 15, 16, 17]`. Two fresh Karto replays produce exactly 33 nodes, 38 edges and
the same signature:

```text
d697659a6ca52d529a14171c3b383fb2b83696d108874edfbf579f570b29fe88
```

Corrected poses, edge order/endpoints, SE(2) measurements and covariances differ by
exactly zero. Replay teardown initially exposed a process-exit `double free` caused by
the same exported OpenKarto logger event being linked into both the shared library and
mapper executable. The observation-only repair uses one process-lifetime accessor;
the mapper instrumentation thread is also joined before object destruction. No graph,
matcher, planner or provenance decision path changed. Stable replay retains the same
graph hash, so N0 is not reopened.

## 5. Stream stitching

The raw canonical `/karto_out` records had 33 zero LaserScan header stamps. The first
stitch attempt correctly failed the strict monotonic-time gate and is retained as an
anomaly. A uniform, outcome-blind repair assigned the canonical records a fixed 0.1 s
period in their original order; poses, ranges and record order were unchanged. Two
fresh replays of this derived prefix again produced the exact canonical graph hash.

Each probe stream was aligned by one fixed SE(2) transform computed only from the
prefix terminal odometry and the probe initial odometry. A fixed time offset placed
the first probe record 0.1 s after the prefix. All three final streams have:

* 33 byte-identical prefix records, hash
  `9c906816468b3120e6e45d6d201235170ae76b45fdceffeb93f8faca0028da4b`;
* strictly increasing timestamps;
* no duplicate/reversed boundary stamp;
* no outcome-dependent alignment.

## 6. Proof-of-design execution

Three reset calibrations froze a branch-start tolerance of 0.08 m / 0.04 rad before
branch outcomes. A harness-only failed launch and the first blocked A0 route are
preserved. The uniform repair made every arm follow the same known collision-free
history route backwards before executing its already frozen core action; it did not
change the A0/A1/A2 action definition.

| arm | start position dev | start heading dev | distance | duration | yaw excursion | raw scans | accepted keyscans |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A0 Baseline | 0.0373 m | 0.0161 rad | 13.945 m | 57.7 s | 9.307 rad | 579 | 27 |
| A1 Neutral | 0.0403 m | 0.0174 rad | 16.872 m | 80.6 s | 15.584 rad | 809 | 39 |
| A2 Sweep90 | 0.0380 m | 0.0128 rad | 13.954 m | 65.3 s | 10.916 rad | 655 | 28 |

Every branch started inside the frozen tolerance and completed its commanded action.
Each fresh Karto replay was paused after prefix record 33 and dumped before its suffix
was published. All three pre-probe graphs are exactly 33 nodes / 38 edges with the
canonical hash above. This is the first local experiment in which the backend
pre-treatment graph is exactly identical across actions.

## 7. Constraint outcomes

The following values are exploratory and cannot establish action superiority:

| arm | final nodes/edges | E_T | E_N | local new edges | E_T provenance |
| --- | ---: | ---: | ---: | ---: | --- |
| A0 | 60 / 80 | 2 | 10 | 30 | 2 running-chain |
| A1 | 72 / 109 | 5 | 12 | 54 | 5 running-chain |
| A2 | 61 / 84 | 2 | 11 | 33 | 2 running-chain |

For A0 and A2 the two target edges have insertion-time geodesics around 9.1 m and
cycles around 15.0-15.3 m. A1 has five target edges: three are non-local and two are
shorter reinforcements (one cycle 0.82 m and one 3.83 m). Every constraint ledger row
records creation provenance, matcher response, relative SE(2) measurement, full
covariance, insertion geodesic and cycle length.

## 8. Utility pipeline

Graph utility uses the author's formula: per-edge D-opt of `covariance^-1`, followed by
the normalized eigenvalue product of the reduced covariance-weighted Laplacian.
Differences are conditional graph ablations, not causal effects or Shapley values.

| arm | Delta U_T | Delta U_H | Delta U_T/m | Delta U_H/m |
| --- | ---: | ---: | ---: | ---: |
| A0 | 386.52 | 3314.78 | 27.72 | 237.71 |
| A1 | 1106.12 | 4377.81 | 65.56 | 259.47 |
| A2 | 592.86 | 4233.44 | 42.49 | 303.38 |

The linearized/local-Gaussian SE(2) posterior build is finite, PSD and has exactly the
expected three gauge modes for the full and target-removed graphs. Target-segment
mean covariance traces are 0.002436 (A0), 0.001327 (A1), and 0.001872 (A2). Removing
E_T increases them by 0.001130, 0.002076 and 0.001504 respectively. Removing every
action-to-history edge disconnects the new scan component (nullity 6); that
counterfactual is correctly reported as `DISCONNECTED_UNBOUNDED`, not as a finite
posterior improvement. These are exploratory n=1 quantities.

## 9. Validity gates

| gate | result |
| --- | --- |
| frame audit complete | PASS |
| common-prefix 2x replay | PASS |
| stitched streams valid | PASS |
| identical preprobe graph hash | PASS |
| physical branch start | PASS |
| action execution | PASS |
| constraint analytics | PASS |
| graph utility | PASS |
| posterior uncertainty | PASS, with explicit disconnected history ablation |
| Neutral-vs-Sweep budget | **FAIL** |

The old N1 fixed-distance specification requires probe distance matching within
0.5 m. Neutral and Sweep differ by 2.918 m, 15.3 s and 11 accepted keyscans
(relative differences 18.9%, 21.0% and 32.8%). Calling this budget-matched would be
scientifically indefensible. The action definitions are not changed post hoc.

## 10. Decision

```text
BUDGET_MATCH_INVALID
```

The common-prefix branched-probe architecture **can** create causally comparable
pre-probe action conditions with identical SLAM history, deterministic replay and
repeatable physical starts. The frozen old Neutral action, however, does not match the
Sweep90 sensing/motion budget in this architecture. Therefore this proof-of-design is
not `READY_FOR_COMMON_PREFIX_CONFIRMATORY_N1`, and no confirmatory expansion is run.

## 11. Remaining unknowns

* The intervention hypothesis is still untested under a valid budget match.
* n=1 per action cannot distinguish action effect from probe realization variability.
* This round uses one map, one target and one backend.
* The author's reduced-Laplacian implementation filters small eigenvalues even in a
  disconnected ablation; the disconnection flag must always accompany Delta U_H.
* A future action-budget protocol would require a new preregistration and human review;
  it is not designed or executed here.
