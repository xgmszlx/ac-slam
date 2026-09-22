# Future v14 confirmatory design, if separately authorized

This document freezes the intended scientific design boundary after v14-T.
It does not authorize or launch collection.

## Research question and intervention language

Research question:

> How does an active revisit action translate into the set and information
> utility of historical pose-graph constraints actually realized by a SLAM
> backend?

Modeling hypothesis: `planned revisit value != realized backend information`.
Future prediction targets should be `E[Delta J_realized | G_pre, action]` or
`P(E_realized | G_pre, action)`, not merely an undifferentiated loop-closure
probability. No predictor is trained in v14-T.

A2 is retained exactly as `theta0 -> +90 -> -30 -> 0 -> +30`; it does not
return to theta0. Therefore the primary contrast is a
`BROAD_SWEEP_ACTION_PACKAGE_EFFECT`, not a `PURE_SWEEP_PATH_EFFECT`.

The Stage laser is 360-degree/near-360-degree. Rotation must not be described
as simply expanding a visual field of view. Plausible mechanisms to distinguish
are keyscan triggering, scan-matching geometry, orientation-conditioned scan
registration, running-scan candidates, near-chain association, and historical
factor endpoint selection.

## Fixed intervention exposure

- Frozen scientific treatment budget: exactly `N=347` scans per arm.
- Counter reset: `probe_arrival.start_time`.
- Scientific suffix: exact first N treatment scans by index.
- Completion after N: fail closed; do not increase N after seeing data.
- No target-specific dwell calibration.
- Physical raw data may include a short debug tail, but it is outside the
  scientific suffix.

## Scientific estimands and support rule

For the frozen five target states:

`J_T = -logdet(Sigma_T)/15`.

Primary:

`D_sweep = J_T(A2_SWEEP90) - J_T(A3_MIN_TRIGGER)`.

Secondary:

- `D_trigger = J_T(A3_MIN_TRIGGER) - J_T(A1_DWELL)`
- `D_total = J_T(A2_SWEEP90) - J_T(A1_DWELL)`

The statistical unit is the canonical-history block. Primary support requires
all of the following unchanged v13-C conditions:

- at least 6/8 positive `D_sweep` blocks;
- at least 3/4 positive in Target A;
- at least 3/4 positive in Target B;
- mean `D_sweep > 1e-4`;
- target-stratified block-bootstrap 95% CI lower bound greater than zero.

`D_trigger` remains secondary because its direction was unstable across prior
experiments. The Target-B post-hoc magnitude cannot change thresholds.

## Estimator-effect sanity endpoints

These endpoints test whether lower modeled covariance corresponds to better
actual estimation. They do not replace the primary `J_T` endpoint.

For each canonical-history block, fit one SE(2) map/world transformation from
the pre-treatment canonical history only. Freeze and reuse that transformation
for before/after and all three arms; per-arm after-result realignment is
forbidden. On the same five target states report:

- translation RMSE before and after;
- heading MAE and RMSE before and after;
- delta translation RMSE (`before - after`);
- delta heading MAE/RMSE (`before - after`);
- maximum and mean historical target-state correction.

The shared common prefix requires the before error to be identical across arms
within a block. A hazardous pattern is `J_T` improvement accompanied by clear
empirical GT-error deterioration; it must be reported, not hidden. NEES is not
preregistered because covariance/gauge consistency is not yet unambiguous.

## Fresh, outcome-blind history plan

Frozen ordered candidate pools, disjoint from v13/v13-C/post-hoc:

- Target A: seeds 91001 through 91016.
- Target B: seeds 92001 through 92016.

Before any action branch or backend endpoint is read, evaluate the complete
pool once per seed. Retain the unchanged target identities
`map3_grid_anchor_01` and `map3_grid_anchor_03`. Use the v13-T block-local
selector: nearest legal post-route-start historical scan to the fixed target
waypoint, continuous half-width 10 states, normalized arc-length quantiles
0.1/0.3/0.5/0.7/0.9, exactly five distinct states in strict order.

Technical eligibility requires history completion, a nonempty canonical
stream, a valid five-state target, complete mapper provenance, and three
same-input unified-lifecycle prefix replays with exact structural and numerical
identity. Replays require a fresh ROS master/MultiMapper, publisher-subscriber
connection, exact prefix, processed-scan-count barrier, and synchronous graph
snapshot. The frozen tolerance is zero unless a separately measured same-input
envelope is justified before endpoint collection.

After the whole pool is evaluated, select the first four technically eligible
seeds per target in frozen order. If either target has fewer than four, stop.
There is no runtime seed substitution or outcome-based replacement.

## Collection lock and no-peeking

Before collection lock, only controller state, branch start, exact N count,
action execution, GT motion, timestamp integrity, input hashes, and prefix
equivalence may be inspected.

Until every authorized confirmatory branch is locked, it is forbidden to read
or compare `J_T`, posterior, E_T/E_N, accepted keyscans, factor counts,
`D_sweep`, `D_trigger`, or `D_total`. Analysis occurs once after the complete
lock.

## Mechanism analysis vocabulary

The future exact classifier must keep these families separate:
`PREVIOUS_SCAN`, `RUNNING_SCAN_CHAIN`, `NEAR_CHAIN`, and exact
`TRY_CLOSE_LOOP`. If the last count is zero, report
`NO_EXPLICIT_TRY_CLOSE_LOOP_OBSERVED`. Preferred terms are historical revisit
association, historical pose-graph constraint, and action-conditioned
historical measurement realization; sequential/near-chain edges are not all
called loop closures.

## Remaining scientific risks

- Evidence still concerns one SLAM backend.
- Current scope is map3 with two target regions, not broad environment
  generalization.
- The 360-degree LiDAR makes narrow-FoV visibility explanations inappropriate.
- A2 is a package effect with a different final heading, not a pure sweep-only
  intervention.
- Better `J_T` may not imply improved realized estimator accuracy; the frozen
  GT sanity endpoints are essential.
- Target-B motivation is post-hoc diagnostic evidence and must not be described
  as confirmatory support.
- Existing frozen data cannot resolve the action phase of accepted keyscans or
  factors because exact scan timestamps were not logged in graph/provenance
  time coordinates.

No v14 confirmatory collection was started.
