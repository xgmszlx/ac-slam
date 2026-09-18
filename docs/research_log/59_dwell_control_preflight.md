# Phase v10: Budget-Matched Dwell Control Preflight

Date: 2026-09-17

Scope: exploratory proof-of-design with one frozen canonical history, one target,
and one fresh branch per action. This is not a confirmatory experiment and does
not validate an intervention or an innovation.

## 1. Why the old neutral was invalid

The v9 `A1_neutral` translated 16.872 m over 80.6 s and exposed 809 raw scans,
whereas `A2_sweep90` translated 13.954 m over 65.3 s and exposed 655 scans.
The 2.918 m and 15.3 s excess made the old arm an invalid control for a
viewpoint-only contrast. It remains preserved as failed control-design evidence
and is not used in the v10 scientific comparison.

## 2. Causal contrast definition

- `A0_baseline`: frozen v9 baseline action.
- `A1_dwell`: the exact A0 waypoint geometry, followed by zero-Twist static
  dwell at the baseline arrival heading.
- `A2_sweep90`: frozen v9 sweep action.

The intended decomposition is `A2-A0` (whole sweep package), `A1-A0` (extra
sensing exposure), and `A2-A1` (viewpoint/rotational action at matched physical
budget). Accepted Karto keyscans are a mediator/outcome and never a budget
variable.

## 3. Timestamp dependency audit

Source inspection produced `DETERMINISTIC_RETIMING_ACCEPTABLE`. The ROS wrapper
uses the message stamp for TF lookup and diagnostics, but constructs
`LocalizedRangeScan` without `SetTime`. In this checkout, OpenKarto never reads
`SensorData::GetTime` in keyscan selection, running-buffer maintenance,
sequential matching, near-chain linking, `TryCloseLoop`, or optimization. Those
paths use ordered scans/state IDs, pose distance, scan geometry, correlation
scores, constraints, and covariance. Deterministic replay retiming therefore
does not introduce an algorithmic delta-time input. Full source hashes and
stage-by-stage checks are in
`timestamp_audit/timestamp_source_audit.json`.

## 4. Historical physical target

The target remains frozen to state/unique IDs 13--17. Each ID indexes the
canonical 33-row SLAM trajectory; its original capture timestamp was joined
exactly to the Stage GT trajectory. No nominal waypoint was used.

| ID | time (s) | Stage GT base pose `(x,y,yaw)` | Karto map pose `(x,y,yaw)` |
|---:|---:|---|---|
| 13 | 20.4 | `(3.95631, 0.03927, 0.18457)` | `(3.95261, 0.00935, 0.18550)` |
| 14 | 21.9 | `(4.87728, 0.13696, 0.06043)` | `(4.86994, 0.10962, 0.06075)` |
| 15 | 24.7 | `(5.80695, 0.11609, -0.04840)` | `(5.81494, 0.11911, -0.04840)` |
| 16 | 29.2 | `(6.76544, 0.06015, -0.03569)` | `(6.76093, 0.05523, -0.03569)` |
| 17 | 34.1 | `(7.75011, 0.03606, -0.01572)` | `(7.75384, 0.03039, -0.01608)` |

The machine-readable record is `target_physical_region.json`.

## 5. Dwell calibration and preregistration

Before any v10 backend outcome existed, the old v9 `A2-A0` time difference
fixed the engineering candidate at 7.6 s. Three backend-free captures used only
GT distance, elapsed time, raw LaserScan count, start pose, and action execution.

| calibration run | distance (m) | time (s) | raw scans | dwell motion/yaw |
|---:|---:|---:|---:|---:|
| 1 | 13.9633 | 66.2 | 664 | `0 m / 0 rad` |
| 2 | 13.9499 | 66.0 | 661 | `0 m / 0 rad` |
| 3 | 13.9530 | 65.9 | 661 | `0 m / 0 rad` |

The medians differed from the frozen v9 A2 engineering reference by 0.0013 m,
0.7 s, and 0.91% raw scans. Repeatability ranges were 0.0134 m, 0.3 s, and
0.45%. The original suggested gates (0.15 m, 2.0 s, 5%) were therefore retained
and frozen. The selected dwell is 7.6 s in `v10_dwell_preregistration.json`.

## 6. Common-prefix identity and branch start

All three fresh branches replayed the exact same 33-record normalized prefix.
Their preprobe graph was exactly 33 nodes/38 edges with hash:

`d697659a6ca52d529a14171c3b383fb2b83696d108874edfbf579f570b29fe88`

All branch starts passed the frozen v9 tolerance of 0.08 m and 0.04 rad:

| arm | position deviation (m) | heading deviation (rad) |
|---|---:|---:|
| A0 | 0.0396 | 0.01745 |
| A1 dwell | 0.0450 | 0.01692 |
| A2 sweep | 0.0364 | 0.01557 |

## 7. Action execution and budget gate

| arm | distance (m) | time (s) | yaw excursion (rad) | raw scans | Karto keyscans |
|---|---:|---:|---:|---:|---:|
| A0 | 13.9514 | 58.2 | 9.3134 | 583 | 27 |
| A1 dwell | 13.9484 | 66.3 | 9.3115 | 666 | 27 |
| A2 sweep | 13.9584 | 65.7 | 10.9228 | 658 | 29 |

The A1 dwell itself produced exactly 0 m translation and 0 rad yaw excursion
while publishing only zero Twist. A1 versus A2 differed by 0.0101 m, 0.6 s,
and 1.21% raw scans. Thus the fresh physical gate is
`BUDGET_MATCH_ACCEPTABLE`. The two-keyscan difference is reported as a
mechanism variable and was excluded from the gate.

## 8. Exploratory realized constraints

| arm | new edges | E_T | E_N | local | PREVIOUS_SCAN | RUNNING_SCAN_CHAIN | NEAR_CHAIN | TRY_CLOSE_LOOP |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A0 | 42 | 2 | 9 | 31 | 27 | 15 | 0 | 0 |
| A1 dwell | 42 | 2 | 10 | 30 | 27 | 15 | 0 | 0 |
| A2 sweep | 47 | 2 | 11 | 34 | 29 | 18 | 0 | 0 |

Every target-attributed edge was created by `RUNNING_SCAN_CHAIN`, not explicit
`TRY_CLOSE_LOOP`. Target insertion-time graph geodesics were about 9.07--9.22 m
with 5--6-edge cycles in every arm. Non-target historical cycles ranged from
4 to 11 edges (apart from the first history-to-new sequential link, whose
pre-insertion geodesic is undefined). Per-edge covariance, relative measurement,
match response, geodesic, and cycle length are preserved in
`analysis/realized_constraints.csv`.

## 9. Graph utility

The primary quantity uses the author's covariance-weighted reduced-Laplacian
D-opt definition: `delta_U_T = U(G_all)-U(G_minus_target_edges)`.

| arm | U(all) | delta_U_T | delta_U_T/m | delta_U_T/s |
|---|---:|---:|---:|---:|
| A0 | 11561.0910 | 475.7851 | 34.1030 | 8.1750 |
| A1 dwell | 11448.0003 | 507.6817 | 36.3973 | 7.6573 |
| A2 sweep | 12787.2215 | 543.2161 | 38.9167 | 8.2681 |

Removing all action-induced historical edges disconnects every arm. Therefore
`history_connectivity_critical=true`; `delta_U_H` is not reported as a finite
continuous outcome. The raw numerical diagnostic is retained only under
`delta_U_H_numeric_not_interpreted`.

## 10. Posterior uncertainty

Values are the validated linearized local-Gaussian SE(2) approximation. The
ablation impact is `(G_minus_target) - G_all`, so positive trace/logdet changes
mean the target edges reduced uncertainty.

| arm/region | all trace | all logdet | minus-target trace | minus-target logdet | delta trace | delta logdet |
|---|---:|---:|---:|---:|---:|---:|
| A0 target | 0.002066 | -24.8298 | 0.003449 | -23.5861 | 0.001384 | 1.2438 |
| A0 current | 0.001436 | -25.6665 | 0.001542 | -25.4621 | 0.000106 | 0.2044 |
| A1 target | 0.002081 | -24.8520 | 0.003576 | -23.4993 | 0.001495 | 1.3527 |
| A1 current | 0.001430 | -25.7214 | 0.001536 | -25.5150 | 0.000105 | 0.2064 |
| A2 target | 0.001907 | -25.1313 | 0.003352 | -23.7606 | 0.001445 | 1.3707 |
| A2 current | 0.001256 | -25.7547 | 0.001444 | -25.3870 | 0.000188 | 0.3677 |

Per-meter and per-second trace/logdet impacts are in
`analysis/posterior_uncertainty.csv`.

## 11. Exploratory causal contrasts

| contrast | keyscans | E_T | E_N | delta_U_T | U(all) | target all-trace | current all-trace |
|---|---:|---:|---:|---:|---:|---:|---:|
| A2-A0 | +2 | 0 | +2 | +67.4311 | +1226.1305 | -0.000158 | -0.000180 |
| A1-A0 | 0 | 0 | +1 | +31.8966 | -113.0907 | +0.000016 | -0.000005 |
| A2-A1 | +2 | 0 | +1 | +35.5345 | +1339.2212 | -0.000174 | -0.000175 |

The matched A2-A1 comparison gives an exploratory signal that rotation changed
keyscan triggering and the broader realized graph. It did **not** add a target
edge in this block: all arms had E_T=2. The higher A2 graph utility and lower
all-graph posterior traces therefore cannot be summarized as “more target loop
closures.” They mix two extra keyscans, one extra non-target historical edge,
four extra local edges, and changed covariances. With n=1, these observations do
not establish stability or causality across histories.

## 12. Proof gate and remaining unknowns

All preregistered engineering gates passed:

- `COMMON_PREFIX_IDENTICAL`
- `BRANCH_START_PASS`
- `ACTION_EXECUTION_PASS`
- `DWELL_BUDGET_MATCH_PASS`
- `CONSTRAINT_ANALYTICS_PASS`
- `GRAPH_UTILITY_PASS`
- `POSTERIOR_PIPELINE_PASS`

Final gate: `READY_FOR_CONFIRMATORY_COMMON_PREFIX_EXPERIMENT`.

This means only that the matched-control protocol is technically usable. It
does not authorize modeling and no 12/18-branch expansion was started. Remaining
unknowns are history/target dependence, repeatability of the two-keyscan effect,
whether covariance/utility differences survive paired blocks, and why target
edges arise through running-chain linkage rather than explicit loop closure.
