# Pose-Graph Impact Metric Audit

Date: 2026-08-31

## Baseline reliability metric

The author planner uses a normalized weighted spanning-tree D-optimality measure.
For a graph with `N` vertices, edge weight is the geometric mean of the eigenvalues
of the edge information matrix `inv(covariance)`. Reliability is

`R = exp(log(det(L_reduced)) / (N - 1))`,

where `L_reduced` is a weighted Laplacian cofactor. This audit mirrors the baseline
`utils.get_normalized_weighted_spanning_trees` and `get_d_opt` behavior; it does not
introduce a new graph score. Sparse log-determinant evaluation exactly matched a
dense toy implementation (`73.68062997280772`, absolute error 0).

## What can be computed offline

- Final-graph accepted-edge ablation is available for 5/7 accepted events. It asks
  how much the saved final graph reliability changes when the identified closure
  edge is removed.
- Compatible trajectory-estimate snapshots give continuous historical pose
  correction for 6/6 active accepted events. No post-hoc material-correction
  threshold is defined; mean, median, and maximum displacement are reported.
- Interval-wide `R_before` and `R_after` exist for 6/6 active events, but node and
  odometry-edge growth also occurs while the robot executes the active loop. The
  observed interval difference is therefore not a causal closure gain.
- The planner's per-selected-loop predicted gain was not logged in a compatible
  form. `Delta_R_predicted` and `eta_real` are `NOT_AVAILABLE`.

## Phase 4B observations

Final-edge marginal D-opt values were 6.4685 (A/21002 temporal), 3.6285 and 3.0049
(B/21004 target events), 12.4916 (C/21004 passive), and 22.7450 (C/21005 temporal).
The two target C edges were absent from their saved final graphs, so claiming a
target-event marginal gain for C would be fabrication.

Continuous mean/max historical pose corrections for the six active events were:

| event | attribution | mean / max correction (m) |
|---|---|---:|
| A/21002 v8 | temporal | 0.04949 / 0.13996 |
| C/21003 v21 | target | 0.0000337 / 0.000134 |
| B/21004 v15 | target | 0.01322 / 0.05215 |
| B/21004 v22 | target | 0.15963 / 0.81396 |
| C/21005 v26 | temporal | 0.00586 / 0.07764 |
| C/21005 v8 | target | 0.0000187 / 0.0000618 |

These values show that accepted constraints can have markedly different realized
effects, but they do not establish a thresholded useful/not-useful label.

## Readiness decision

- Baseline reliability metric reproduction: **READY**.
- Strict accepted-constraint pre/post causal graph evaluation: **NOT READY**.
- Continuous pose correction from compatible snapshots: **READY**, availability
  conditional on snapshots.

Graph impact remains an explicitly exploratory/nonblocking outcome in Phase 4C.
Final-edge ablation may be reported when the exact accepted edge is present, but
interval-wide graph growth must not be labelled `Delta_R_actual` caused by the
closure.
