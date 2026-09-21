# v13-C Final Fresh Confirmatory Experiment

Date: 2026-09-21

Protocol: `p1_confirmatory_v13c_20260921`

Base commit: `201e4b78345019af5b0d718a416ce6fa17e063d9`

Result root: `results/realizability_pilot/p1_confirmatory_v13c_20260921/`

This log reports the preregistered v13-C experiment. It deliberately separates code facts, measured observations, inferences, hypotheses, and unknowns. The final outcome is technical incompleteness, not confirmation or rejection of either scientific contrast.

## 1. Stage-0 local estimand amendment

**CODE FACT.** The offline amendment used the unchanged target identities, the existing 2.5 m target radius, the route-start cut, the largest contiguous state-ID run containing the unchanged nearest action anchor, and fixed normalized-arc quantiles `[0.10, 0.30, 0.50, 0.70, 0.90]`. It read all 16 frozen v13-T canonical histories and did not rerun a history or action.

**MEASURED OBSERVATION.** The selector results were:

| Target | Seed | Old technical | Local run | Arc (m) | Anchor / distance (m) | Selected five | Local valid | Confirmatory eligible / reason |
|---|---:|---|---|---:|---|---|---|---|
| A | 81001 | yes | 13–17 (5) | 3.858592 | 15 / 0.353829 | 13,14,15,16,17 | yes | yes |
| A | 81002 | yes | 13–17 (5) | 3.746186 | 15 / 0.345506 | 13,14,15,16,17 | yes | yes |
| A | 81003 | yes | 14–19 (6) | 4.768043 | 16 / 0.460013 | 15,16,17,18,19 | yes | yes |
| A | 81004 | no | 14–18 (5) | 3.886084 | 16 / 0.285277 | 14,15,16,17,18 | yes | no: old v13-T ineligible |
| A | 81005 | yes | 14–18 (5) | 3.915548 | 16 / 0.223053 | 14,15,16,17,18 | yes | yes |
| A | 81006 | yes | 13–18 (6) | 4.809995 | 15 / 0.449111 | 14,15,16,16,17 | no | no: duplicate quantile mapping |
| A | 81007 | no | 14–19 (6) | 4.841279 | 17 / 0.454642 | 15,16,17,18,19 | yes | no: old v13-T ineligible |
| A | 81008 | no | 14–18 (5) | 3.965237 | 16 / 0.371474 | 14,15,16,17,18 | yes | no: old v13-T ineligible |
| B | 82001 | yes | 18–24 (7) | 4.739608 | 21 / 0.406137 | 18,19,20,22,24 | yes | yes |
| B | 82002 | yes | 18–24 (7) | 4.921360 | 21 / 0.301789 | 19,20,21,22,23 | yes | yes |
| B | 82003 | yes | 18–24 (7) | 4.419856 | 21 / 0.306078 | 18,19,20,22,24 | yes | yes |
| B | 82004 | no | 18–24 (7) | 4.513111 | 21 / 0.287108 | 18,19,20,22,24 | yes | no: old v13-T ineligible |
| B | 82005 | yes | 19–25 (7) | 4.278498 | 21 / 0.343825 | 19,20,22,24,25 | yes | yes |
| B | 82006 | yes | 17–23 (7) | 4.562006 | 20 / 0.382841 | 17,18,19,21,23 | yes | yes |
| B | 82007 | yes | 18–24 (7) | 4.647769 | 21 / 0.292446 | 18,19,20,22,24 | yes | yes |
| B | 82008 | yes | 17–23 (7) | 4.651930 | 20 / 0.265337 | 17,18,20,21,23 | yes | yes |

**MEASURED OBSERVATION.** Target A had exactly four confirmatory-eligible histories and target B had seven. Both met the minimum-four gate, producing `LOCAL_ESTIMAND_AMENDMENT_PASS`.

## 2. Frozen manifest

**CODE FACT.** Immutable seed order selected the first four jointly eligible histories per target, with no substitution or runtime reserve:

| Block | Seed | Anchor | Frozen local state IDs |
|---|---:|---:|---|
| target_A_H1 | 81001 | 15 | 13,14,15,16,17 |
| target_A_H2 | 81002 | 15 | 13,14,15,16,17 |
| target_A_H3 | 81003 | 16 | 15,16,17,18,19 |
| target_A_H4 | 81005 | 16 | 14,15,16,17,18 |
| target_B_H1 | 82001 | 21 | 18,19,20,22,24 |
| target_B_H2 | 82002 | 21 | 19,20,21,22,23 |
| target_B_H3 | 82003 | 21 | 18,19,20,22,24 |
| target_B_H4 | 82005 | 21 | 19,20,22,24,25 |

**CODE FACT.** The old v13-T results, eligibility manifest, technical gate, forensic artifacts, and research log 63 were not modified.

## 3. v13-C preregistration

**CODE FACT.** The frozen plan contained 8 canonical-history blocks and 24 branches. Arm orders were:

| Block | Order |
|---|---|
| A-H1 | A1, A3, A2 |
| A-H2 | A3, A2, A1 |
| A-H3 | A2, A1, A3 |
| A-H4 | A1, A2, A3 |
| B-H1 | A3, A1, A2 |
| B-H2 | A2, A3, A1 |
| B-H3 | A1, A3, A2 |
| B-H4 | A3, A2, A1 |

**CODE FACT.** A1 was static dwell (A 7.1 s, B 11.4 s); A3 was `theta0 -> theta0 + 0.5439732814124923 -> theta0` plus residual dwell (A 2.6 s, B 7.0 s); A2 was the frozen relative Sweep90 package with zero residual dwell. The budget gates were distance range <= 0.10 m, duration range <= 1.5 s, and raw-scan relative range <= 3%.

**CODE FACT.** The primary estimator was the fixed-first-pose, fixed-linearisation, local linear-Gaussian joint marginal over the five frozen SE(2) states: `J_T = -logdet(Sigma_T) / 15`. It is not an exact nonlinear posterior.

**CODE FACT.** The preregistration SHA-256 was `62f3521fbe8b9c3a5976f5ca518e064b4367bd2a0f894698fa30eed7b97873ec`; the code-bundle SHA-256 was `00fe8adddb89ed5b10bd42757b537715bb0c510b56829638e15de8f654f1d4bc`; the frozen analysis-code SHA-256 was `51294aaf14bbb0ad3e0182f1e2d9abff31751ea8583138bb4d915f486d710a02`. A post-collection audit found zero mismatches across all 15 preregistered code hashes.

**CODE FACT.** Collection used only technical/physical fields until `COLLECTION_LOCKED.json` was written. The analysis script was executed once after that lock.

## 4. Collection ledger

**MEASURED OBSERVATION.** All 24 Stage captures completed on their first capture attempt. Fifteen branches in five budget-valid blocks then completed one unified backend replay each. Nine branches in three budget-invalid blocks were not replayed.

| Block | Arm | Capture / replay status | Distance (m) | Duration (s) | Raw scans | Prefix attempts / exact |
|---|---|---|---:|---:|---:|---|
| A-H1 | A1 | REPLAYED | 13.758149 | 64.6 | 649 | 1 / yes |
| A-H1 | A3 | REPLAYED | 13.769026 | 65.0 | 652 | 1 / yes |
| A-H1 | A2 | REPLAYED | 13.765217 | 64.6 | 649 | 1 / yes |
| A-H2 | A3 | REPLAYED | 13.613042 | 64.3 | 645 | 1 / yes |
| A-H2 | A2 | REPLAYED | 13.595254 | 64.2 | 644 | 1 / yes |
| A-H2 | A1 | REPLAYED | 13.612717 | 64.7 | 649 | 1 / yes |
| A-H3 | A2 | REPLAYED | 13.915908 | 64.4 | 645 | 1 / yes |
| A-H3 | A1 | REPLAYED | 13.917469 | 64.8 | 651 | 1 / yes |
| A-H3 | A3 | REPLAYED | 13.913940 | 65.0 | 652 | 1 / yes |
| A-H4 | A1 | REPLAYED | 13.623742 | 64.5 | 647 | 1 / yes |
| A-H4 | A2 | REPLAYED | 13.624015 | 64.4 | 647 | 1 / yes |
| A-H4 | A3 | REPLAYED | 13.630380 | 64.5 | 647 | 1 / yes |
| B-H1 | A3 | CAPTURED; budget invalid | 9.846482 | 54.4 | 547 | 0 / n.a. |
| B-H1 | A1 | CAPTURED; budget invalid | 9.847527 | 54.1 | 544 | 0 / n.a. |
| B-H1 | A2 | CAPTURED; budget invalid | 9.852619 | 52.5 | 527 | 0 / n.a. |
| B-H2 | A2 | CAPTURED; budget invalid | 9.944987 | 52.9 | 531 | 0 / n.a. |
| B-H2 | A3 | CAPTURED; budget invalid | 9.945808 | 54.5 | 548 | 0 / n.a. |
| B-H2 | A1 | CAPTURED; budget invalid | 9.946095 | 54.3 | 545 | 0 / n.a. |
| B-H3 | A1 | CAPTURED; budget invalid | 9.486906 | 53.6 | 538 | 0 / n.a. |
| B-H3 | A3 | CAPTURED; budget invalid | 9.494560 | 53.7 | 539 | 0 / n.a. |
| B-H3 | A2 | CAPTURED; budget invalid | 9.487720 | 52.1 | 524 | 0 / n.a. |
| B-H4 | A3 | REPLAYED | 9.710294 | 52.5 | 527 | 1 / yes |
| B-H4 | A2 | REPLAYED | 9.704535 | 52.6 | 528 | 1 / yes |
| B-H4 | A1 | REPLAYED | 9.709892 | 52.6 | 528 | 1 / yes |

## 5. Technical validity

**MEASURED OBSERVATION.** Budget ranges were:

| Block | Distance range (m) | Duration range (s) | Scan relative range | Verdict |
|---|---:|---:|---:|---|
| A-H1 | 0.010877 | 0.4 | 0.004615 | pass |
| A-H2 | 0.017788 | 0.5 | 0.007740 | pass |
| A-H3 | 0.003529 | 0.6 | 0.010780 | pass |
| A-H4 | 0.006638 | 0.1 | 0.000000 | pass |
| B-H1 | 0.006137 | 1.9 | 0.037083 | fail: time and scans |
| B-H2 | 0.001108 | 1.6 | 0.031404 | fail: time and scans |
| B-H3 | 0.007654 | 1.6 | 0.028107 | fail: time |
| B-H4 | 0.005759 | 0.1 | 0.001895 | pass |

**MEASURED OBSERVATION.** Every replayed branch matched its frozen prefix reference exactly at zero tolerance on the first attempt, before suffix publication. There were no post-treatment technical failures.

**MEASURED OBSERVATION.** A deliberately mismatched-reference preflight processed exactly 33/33 prefix scans, produced `TECHNICAL_INVALID_PREFIX_PRETREATMENT`, and left both suffix authorization and suffix publication false. It used neither a background graph dump nor a fixed sleep drain barrier.

**INFERENCE.** The incomplete confirmatory sample arose at the preregistered physical exposure gate, not at the unified prefix barrier or post-treatment Karto replay.

**UNKNOWN.** This experiment does not determine whether the Target-B calibration mismatch is a stable target-specific timing property or run-to-run Stage/controller variability; the protocol forbids recalibration or replacement here.

## 6. Primary D_sweep

`D_sweep = J_T(A2_SWEEP90) - J_T(A3_MIN_TRIGGER)`.

**MEASURED OBSERVATION.** Only five complete blocks were analyzable:

| Block | J(A3) | J(A2) | D_sweep |
|---|---:|---:|---:|
| A-H1 | 9.021821207 | 9.070681119 | +0.048859912 |
| A-H2 | 8.867291818 | 8.983059377 | +0.115767558 |
| A-H3 | 9.230804323 | 9.207081492 | -0.023722832 |
| A-H4 | 9.142543834 | 9.308510876 | +0.165967041 |
| B-H1 | — | — | technically unavailable |
| B-H2 | — | — | technically unavailable |
| B-H3 | — | — | technically unavailable |
| B-H4 | 8.591971057 | 8.742389135 | +0.150418078 |

**MEASURED OBSERVATION.** Descriptively, mean = 0.091457952, median = 0.115767558, positive blocks = 4/5, one-sided exact sign-test p = 0.1875, one-sided exact sign-flip-mean p = 0.0625, and the target-stratified block-bootstrap interval was `[0.039003428, 0.142777456]`.

**INFERENCE.** The five observed blocks lean positive, but the preregistered 8/8 evaluability condition failed. Therefore the contrast is `INCONCLUSIVE_TECHNICAL_INCOMPLETENESS`, not `SUPPORTED` and not `NOT SUPPORTED`.

## 7. D_trigger

`D_trigger = J_T(A3_MIN_TRIGGER) - J_T(A1_DWELL)`.

| Block | J(A1) | J(A3) | D_trigger |
|---|---:|---:|---:|
| A-H1 | 8.976480368 | 9.021821207 | +0.045340839 |
| A-H2 | 8.858350612 | 8.867291818 | +0.008941206 |
| A-H3 | 9.234050312 | 9.230804323 | -0.003245988 |
| A-H4 | 9.211119184 | 9.142543834 | -0.068575350 |
| B-H1 | — | — | technically unavailable |
| B-H2 | — | — | technically unavailable |
| B-H3 | — | — | technically unavailable |
| B-H4 | 8.451754535 | 8.591971057 | +0.140216523 |

**MEASURED OBSERVATION.** Descriptively, mean = 0.024535446, median = 0.008941206, positive blocks = 3/5, one-sided exact sign-test p = 0.5, one-sided exact sign-flip-mean p = 0.3125, and the descriptive interval was `[-0.011313664, 0.054598610]`.

**INFERENCE.** This contrast is also `INCONCLUSIVE_TECHNICAL_INCOMPLETENESS`.

## 8. Target-wise consistency

**MEASURED OBSERVATION.** For D_sweep, Target A was 3/4 positive with mean 0.076717920 and median 0.082313735; the only usable Target B block was positive at 0.150418078. For D_trigger, Target A was 2/4 positive with mean -0.004384823 and median 0.002847609; the only usable Target B block was positive at 0.140216523. For secondary D_total, Target A was 3/4 positive with mean 0.072333097 and the only usable Target B block was +0.290634600.

**UNKNOWN.** With only 1/4 Target-B blocks, the preregistered target heterogeneity rule cannot be evaluated. The absence of a heterogeneity flag in the machine summary is not evidence of target invariance.

## 9. Mechanism analysis

**MEASURED OBSERVATION.** Across the five usable blocks:

| Arm | Mean accepted keyscans | Mean E_T | Mean E_N | Mean local edges | Mean all new edges |
|---|---:|---:|---:|---:|---:|
| A1 | 24.4 | 1.8 | 10.4 | 27.6 | 39.8 |
| A3 | 25.6 | 2.4 | 10.6 | 28.6 | 41.6 |
| A2 | 27.8 | 3.0 | 12.2 | 30.8 | 46.0 |

**MEASURED OBSERVATION.** Total new-edge creation provenance was A1: 122 `PREVIOUS_SCAN`, 70 `RUNNING_SCAN_CHAIN`, 7 `NEAR_CHAIN`; A3: 128, 73, 7; A2: 139, 87, 4. Matcher labels were exclusively `SEQUENTIAL_RUNNING_BUFFER` and `SEQUENTIAL_NEAR_CHAIN`; no `TRY_CLOSE_LOOP` factor appeared in these 15 branches.

**MEASURED OBSERVATION.** Target-factor covariance eigenvalue ranges were A1 `[6e-06, 8.62572e-04]`, A3 `[6e-06, 7.43390e-03]`, and A2 `[6e-06, 3.06904e-03]`; corresponding information eigenvalue ranges were A1 `[1159.32, 166666.67]`, A3 `[134.52, 166666.67]`, and A2 `[325.83, 166666.67]`. These are raw ranges over non-identically matched factors, not arm-level causal covariance estimates.

**MEASURED OBSERVATION.** Exact target-edge sets matched across all three arms only in A-H3. The other four usable blocks had different target-factor endpoints/counts. The covariance-swap diagnostic is therefore `COUNTERFACTUAL_SWAP_NOT_IDENTIFIABLE`.

**MEASURED OBSERVATION.** Removing action-induced historical edges disconnected all 15 usable branch graphs, yielding `HISTORY_CONNECTIVITY_CRITICAL`; no finite pseudoinverse scalar is interpreted as normal `Delta U_H`.

**INFERENCE.** Broad sweep co-occurs descriptively with more accepted scans and more generated factors, but endpoint identity differs and the experiment is incomplete. Edge counts alone do not establish that factor count mediates the observed J_T contrast.

## 10. v12 descriptive replication

**MEASURED OBSERVATION.** Target-A direction was qualitatively consistent with v12 for D_sweep (v13-C mean +0.076717920 versus v12 +0.070868296) and D_total (+0.072333097 versus +0.128537673). D_trigger was not directionally consistent (v13-C -0.004384823 versus v12 +0.057669378).

**CODE FACT.** v12 was not pooled with v13-C because the target-state estimand changed to the local 2.5 m region.

## 11. Limitations

**CODE FACT.** Confirmatory evaluability required 8/8 matched triples; only 5/8 were available. The statistical unit remained the canonical-history block, with no branch-level pseudoreplication.

**MEASURED OBSERVATION.** Target B contributed only one analyzable block. This prevents the preregistered per-target support and heterogeneity checks.

**MEASURED OBSERVATION.** Several keyscan reconstructions report count mismatch in the secondary forensic output. Accepted-keyscan comparisons are therefore descriptive and do not affect inclusion, primary estimation, or the final gate.

**INFERENCE.** Positive descriptive D_sweep values, a bootstrap interval above zero on the incomplete subset, and larger A2 factor counts cannot override the missing-block gate.

**UNKNOWN.** The incomplete data do not identify whether a complete 8-block experiment would preserve the observed contrast directions.

## 12. Final gate

**MEASURED OBSERVATION.** The immutable collection lock is `COLLECTION_LOCKED_TECHNICALLY_INCOMPLETE` with 5/8 complete blocks and 15/24 analyzed branches.

**INFERENCE.** Per the preregistered decision order, the only valid final scientific gate is:

`CONFIRMATORY_EXPERIMENT_TECHNICALLY_INCOMPLETE`

No predictor, planner integration, second backend, fifth control, recalibration, added seed, or automatic next phase was started.
