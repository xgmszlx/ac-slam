# v13-C Post-hoc Target-B Diagnostic

Date: 2026-09-21 to 2026-09-22

Label: `POSTHOC_NONCONFIRMATORY_TARGET_B_DIAGNOSTIC`

Base commit: `9edba1dbe2e397aa074f4cf11d9035bc40bf4b5c`

Result root: `results/realizability_pilot/p1_v13c_posthoc_targetB_20260921/`

This diagnostic does not alter the v13-C sample or final gate. B-H4 had already
been observed; the new backend endpoints were B-H1 through B-H3. No Stage or
physical branch was recollected, no original v13-C artifact was modified, and
no future phase was started.

## 1. Provenance and technical execution

**CODE FACT.** The frozen preregistration SHA-256 is
`c3a45391e2bb073e919b9f94ea22ed4a1b497ac18e62872e68bd203e5c4566a6`,
the code-bundle SHA-256 is
`d0bb808e256a0fc788629e8984fde8f1af57a3cec848ca40049f762291c0865b`,
and the frozen primary-analysis SHA-256 is
`7b0cbfe03619a8b3f5ccdecd91b7c776d677f78dd58d8935ca4bbe34c352c43e`.
The preregistration records `B_H4_ENDPOINT_PREVIOUSLY_OBSERVED = true` and
`CONFIRMATORY_EXPERIMENT_TECHNICALLY_INCOMPLETE` as the original gate.

**CODE FACT.** Two pre-backend path/setup errors occurred before any ROS graph
endpoint was generated. The first required creation of the `collection/`
directory. The second was a same-file `copy2` error because the stitched input
and canonical output copy had the same path. The first preregistration and
partial pre-backend files were preserved under `preregistration/` and
`technical/prebackend_failure_01/`; the minimal input-path correction was
tested and the protocol was refrozen before any replay. It changed no capture,
graph parameter, estimand, threshold, or decision rule.

**MEASURED OBSERVATION.** The locked collection contains 24 unique, complete
replays: 12 FULL and 12 MATCHED. Every replay passed exact prefix equivalence,
processed-count barrier, and suffix-publication checks. The three B-H4 FULL
graphs and all B-H4 `J_T` values exactly reproduce the original v13-C results
with zero numerical tolerance.

## 2. Budget geometry forensic

The frozen dwell error is `frozen - required`; positive values mean the frozen
dwell was too long for that history. Rotation demand is the absolute wrapped
rotation from arrival bearing to final target yaw.

| Group | A1 rot (rad) | A2 rot (rad) | A3 rot (rad) | Required A1 dwell / error (s) | Required A3 dwell / error (s) | Full-duration spread (s) | Scan-relative spread |
|---|---:|---:|---:|---:|---:|---:|---:|
| Calibration 1 | 1.637 | 3.077 | 1.635 | 11.7 / -0.3 | 7.1 / -0.1 | 0.3 | 0.00374 |
| Calibration 2 | 1.636 | 3.077 | 1.635 | 11.4 / 0.0 | 6.8 / +0.2 | 0.1 | 0.00373 |
| Calibration 3 | 1.636 | 3.077 | 1.635 | 11.4 / 0.0 | 6.7 / +0.3 | 0.6 | 0.01124 |
| B-H1 | 2.172 | 2.540 | 2.172 | 9.9 / +1.5 | 5.2 / +1.8 | 1.9 | 0.03708 |
| B-H2 | 2.167 | 2.545 | 2.166 | 9.8 / +1.6 | 5.1 / +1.9 | 1.6 | 0.03140 |
| B-H3 | 2.176 | 2.535 | 2.177 | 9.8 / +1.6 | 5.3 / +1.7 | 1.6 | 0.02811 |
| B-H4 | 1.573 | 3.141 | 1.572 | 11.5 / -0.1 | 7.1 / -0.1 | 0.1 | 0.00190 |

**MEASURED OBSERVATION.** Timing decomposition residuals were zero. Relative
to the calibration median, B-H1 through B-H3 shifted the arm rotation demands
by about 0.53--0.54 rad and required 1.5--1.9 s less dwell than the frozen
values. B-H4 remained within 0.064 rad and 0.1 s.

**INFERENCE.** The frozen forensic rule returns
`GEOMETRY_DEPENDENT_CALIBRATION_SUPPORTED`: the B-H1--H3 budget failure is
consistent with history-dependent arrival/rotation geometry and controller
timing, while B-H4 happened to be close to the calibration geometry. This is
an explanation of the technical mismatch, not evidence about the backend
scientific endpoint.

## 3. FULL Target-B results

`J_T = -logdet(Sigma_T)/15`, with the unchanged five-state fixed-linearisation
local Gaussian marginal.

| Block | J(A1) | J(A3) | J(A2) | D_trigger | D_sweep | D_total |
|---|---:|---:|---:|---:|---:|---:|
| B-H1 | 8.939458072 | 8.890380104 | 8.898448942 | -0.049077968 | +0.008068837 | -0.041009130 |
| B-H2 | 8.833222794 | 8.958631297 | 9.079597462 | +0.125408503 | +0.120966166 | +0.246374669 |
| B-H3 | 7.970111514 | 7.971661467 | 8.369865537 | +0.001549953 | +0.398204070 | +0.399754023 |
| B-H4 | 8.451754535 | 8.591971057 | 8.742389135 | +0.140216523 | +0.150418078 | +0.290634600 |

**MEASURED OBSERVATION.** B-H1--H3 are 3/3 positive for `D_sweep`, with mean
`+0.175746358`. All four blocks are positive, with mean `+0.169414288` and
median `+0.135692122`.

## 4. Exposure-matched Target-B results

Strict tail truncation retained 527, 531, 524, and 527 scans per arm in B-H1
through B-H4 respectively. All removed scans followed final action completion;
their GT translation and yaw excursion were both exactly zero.

| Block | J(A1) | J(A3) | J(A2) | D_trigger | D_sweep | D_total |
|---|---:|---:|---:|---:|---:|---:|
| B-H1 | 8.939458072 | 8.890380104 | 8.898448942 | -0.049077968 | +0.008068837 | -0.041009130 |
| B-H2 | 8.833222794 | 8.958631297 | 9.079597462 | +0.125408503 | +0.120966166 | +0.246374669 |
| B-H3 | 7.970111514 | 7.971661467 | 8.369865537 | +0.001549953 | +0.398204070 | +0.399754023 |
| B-H4 | 8.451754535 | 8.591971057 | 8.742389135 | +0.140216523 | +0.150418078 | +0.290634600 |

**MEASURED OBSERVATION.** FULL and MATCHED results are numerically identical
for all four blocks. In the original B-H1--H3 captures, A2 already had fewer
raw scans than A1/A3; removing only their extra static-tail scans does not
change any accepted graph element or `J_T`.

**INFERENCE.** The positive A2-versus-A3 direction is robust to this particular
static-tail exposure imbalance. This is post-hoc diagnostic robustness, not a
confirmatory causal proof and not a physical equal-exposure counterfactual.

## 5. Mechanism

FULL and MATCHED generated identical graph summaries.

| Arm | Mean accepted keyscans | Mean E_T | Mean E_N | Mean local edges | Mean all new edges |
|---|---:|---:|---:|---:|---:|
| A1 | 18.50 | 3.00 | 7.25 | 21.25 | 31.50 |
| A3 | 19.50 | 3.25 | 8.50 | 21.50 | 33.25 |
| A2 | 25.00 | 4.00 | 11.75 | 27.25 | 43.00 |

**MEASURED OBSERVATION.** Across the 431 new factors in either mode, exact
creation provenance was 252 `PREVIOUS_SCAN`, 166 `RUNNING_SCAN_CHAIN`, and 13
`NEAR_CHAIN`. Matcher type was 418 `SEQUENTIAL_RUNNING_BUFFER` and 13
`SEQUENTIAL_NEAR_CHAIN`. Historical factors numbered 151; insertion-time hops
ranged 2--10 (median 4; 120 at least 3 hops and 61 at least 5), and insertion
geodesics ranged 0.215--17.017 m (median 10.258 m). Removing action-induced
historical edges disconnected every branch graph.

**POST-ANALYSIS CORRECTION.** The frozen mechanism classifier used substring
matching and incorrectly counted all 431 `ADD_EDGES_BEFORE_TRY_CLOSE_LOOP`
edges as explicit `TRY_CLOSE_LOOP`. Exact-token re-audit of the raw provenance
finds zero explicit `TRY_CLOSE_LOOP` constraints in FULL and zero in MATCHED:
`NO_EXPLICIT_TRY_CLOSE_LOOP_OBSERVED`. The correction is isolated in
`analysis/mechanism_classifier_correction.json`; it changes no `J_T`, contrast,
graph, threshold, or decision label.

**MEASURED OBSERVATION.** Exact target-edge endpoint sets differ among arms in
all four blocks, so the covariance swap remains
`COUNTERFACTUAL_SWAP_NOT_IDENTIFIABLE`. Raw covariance/information values and
per-edge match responses, cycle lengths, endpoints, geodesics, and hops remain
in `analysis/{FULL,MATCHED}/constraint_mechanism.csv`.

**INFERENCE.** A2 primarily creates more sequential and near-chain historical
associations, not explicit Karto loop-closure factors. These associations are
not merely immediate local reinforcement: many close cycles only after 3--10
existing graph hops and span substantial insertion-time graph distance.
Nevertheless, the instrumentation identifies their creation path as
sequential/near-chain, not the explicit loop matcher.

## 6. Scientific questions and interpretation

**FACT.** B-H1--H3 were not part of the v13-C confirmatory endpoint sample;
this analysis is `POSTHOC_DESCRIPTIVE_ONLY`. B-H4 was previously observed.

**MEASURED OBSERVATION.** History-specific geometry explains the frozen budget
mismatch under the preregistered forensic rule. The newly replayed H1--H3 have
positive `D_sweep` in 3/3 blocks, and FULL/MATCHED directions and values are
identical. A2 has more accepted keyscans and more sequential/near-chain
historical factors, but no explicit `TRY_CLOSE_LOOP` factor.

**INFERENCE.** Static-tail scan count alone does not explain the A2 diagnostic
advantage. The evidence supports the narrower description
**action-conditioned historical measurement realization**, not **explicit
active loop closure realization**.

**UNKNOWN.** This diagnostic does not establish prospective causal efficacy,
generalization beyond the four Target-B histories, nonlinear posterior gain,
planner-level utility after motion/time cost, or whether a fresh fixed-scan
experiment will reproduce these contrasts. Different endpoint sets also
prevent an isolated covariance-quality counterfactual.

## 7. Frozen diagnostic decision

Both modes satisfy all preregistered retry conditions: H1--H3 are 3/3
positive with positive mean, H1--H4 are 4/4 positive, both Target-B means are
positive with the same sign, the result is not driven only by B-H4, and all
exposure-matching gates are valid.

`DIAGNOSTIC_SUPPORTS_ONE_PROSPECTIVE_RETRY`

This means only that one fresh prospective validation is worth designing. It
does not upgrade or retroactively complete v13-C.

## 8. Original confirmatory status

`v13-C remains CONFIRMATORY_EXPERIMENT_TECHNICALLY_INCOMPLETE`

No v14 collection, predictor, planner integration, or second backend was
started.
