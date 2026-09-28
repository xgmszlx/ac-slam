# V14 Prospective Confirmatory Validation

## A. Provenance

- **FACT:** Protocol `p1_v14_confirmatory_20260928` was preregistered before fresh collection. Preregistration SHA256: `6761a35511a17f73b77806fd0fbec33af98acdbf5a1078ba271144409fe85709`.
- **FACT:** Authorized baseline: `e112208bac21341a4b60a992dfa7434659af405d` on `research/phase4c-formal`.
- **FACT:** Frozen mapper binary SHA256: `7ab54496b4572e831d7f10d615ad3d700bec3a0b89c5abdb9c562616a67d92f6`; normalized mapper-config SHA256: `511dcacb4ff58a99d0f434cbfd604198c95f453e2bd18e35c0b5e0533437825c`.
- **FACT:** All 29 preregistered code hashes matched at final audit. The backend, matcher thresholds, planner, prior graph, and skip logic were not changed.
- **FACT:** Scientific treatment exposure was fixed at exactly `N=347` scans per branch.

## B. 32-candidate qualification ledger

- **MEASURED OBSERVATION:** Target A: 16 evaluated, 11 technically eligible. Seeds `91002`, `91003`, `91008`, `91009`, and `91011` failed exact numerical prefix repeatability.
- **MEASURED OBSERVATION:** Target B: 16 evaluated, 14 technically eligible. Seeds `92008` and `92016` failed exact numerical prefix repeatability.
- **FACT:** Each candidate received one history attempt. Selection occurred only after the complete 32-candidate pool was evaluated.
- Full records: `qualification/history_qualification_ledger.csv` and `qualification/history_eligibility_manifest.json`.

## C. Frozen 4A + 4B histories

| Block | Target | Seed | Five frozen state IDs |
|---|---|---:|---|
| target_A_H1 | A | 91001 | 13, 16, 18, 22, 25 |
| target_A_H2 | A | 91004 | 13, 16, 19, 22, 25 |
| target_A_H3 | A | 91005 | 12, 15, 17, 21, 24 |
| target_A_H4 | A | 91006 | 13, 16, 18, 22, 25 |
| target_B_H1 | B | 92001 | 13, 16, 19, 24, 27 |
| target_B_H2 | B | 92002 | 13, 16, 20, 24, 28 |
| target_B_H3 | B | 92003 | 13, 16, 20, 24, 28 |
| target_B_H4 | B | 92004 | 14, 17, 20, 25, 28 |

- **FACT:** These are the first four eligible histories in each frozen seed order. No reserve substitution occurred.
- Canonical source: `qualification/frozen_history_manifest.json`.

## D. Physical collection and arm order

- **MEASURED OBSERVATION:** All 24/24 physical branches were technically valid on their first capture attempt.
- **MEASURED OBSERVATION:** Completion margins ranged from 70 to 189 scans; every maneuver completed before scan 347.
- **FACT:** Position counts were balanced within one occurrence: A1 `(3,2,3)`, A3 `(3,3,2)`, A2 `(2,3,3)` for positions 1/2/3.
- **FACT:** `PHYSICAL_COLLECTION_LOCK.json` records exact raw/scientific hashes and prohibits further capture.

## E. Backend replay technical ledger

- **MEASURED OBSERVATION:** All 24/24 branches replayed successfully on their first replay attempt.
- **FACT:** Every replay used a fresh ROS master and MultiMapper, exact canonical prefix, processed-count barriers, synchronous graph dumps, zero-tolerance prefix comparison, and exact 347-scan scientific suffix.
- **FACT:** `BACKEND_REPLAY_LOCK.json` was written before scientific analysis.

## F. Eight-block primary table

`J_A1`, `J_A3`, and `J_A2` are `J_T = -logdet(Sigma_T)/15` over the five frozen target states.

| Block | J_A1 | J_A3 | J_A2 | D_trigger | D_sweep | D_total |
|---|---:|---:|---:|---:|---:|---:|
| target_A_H1 | 8.634024 | 8.667551 | 8.559124 | 0.033527 | -0.108427 | -0.074900 |
| target_A_H2 | 8.320162 | 8.485715 | 8.195357 | 0.165553 | -0.290358 | -0.124805 |
| target_A_H3 | 8.398402 | 8.397605 | 8.265794 | -0.000797 | -0.131811 | -0.132608 |
| target_A_H4 | 8.071479 | 8.212239 | 7.873501 | 0.140760 | -0.338738 | -0.197978 |
| target_B_H1 | 7.738064 | 7.738142 | 7.896597 | 0.000079 | 0.158455 | 0.158533 |
| target_B_H2 | 8.152751 | 8.158845 | 8.380664 | 0.006094 | 0.221819 | 0.227913 |
| target_B_H3 | 8.117904 | 8.119859 | 8.314053 | 0.001955 | 0.194194 | 0.196150 |
| target_B_H4 | 7.635120 | 7.644582 | 7.804667 | 0.009462 | 0.160084 | 0.169546 |

## G. Primary summary

- **MEASURED OBSERVATION:** `D_sweep > 0` in 4/8 blocks: Target A 0/4, Target B 4/4.
- **MEASURED OBSERVATION:** Mean `D_sweep = -0.0168477`; median `= 0.0250139`.
- **MEASURED OBSERVATION:** Target-stratified block-bootstrap 95% CI is `[-0.0687043, 0.0333040]` (10,000 repetitions, seed 140928).
- **MEASURED OBSERVATION:** Support checks: complete sample PASS; overall positives FAIL; Target-A positives FAIL; Target-B positives PASS; mean threshold FAIL; CI lower-bound threshold FAIL.
- **MEASURED OBSERVATION:** Secondary summaries: `D_trigger` positive 7/8, mean `0.0445791`; `D_total` positive 4/8, mean `0.0277314`.
- **INFERENCE:** The broad-sweep action package does not have a target-invariant prospective effect under this protocol. The opposite Target-A/Target-B directions are material heterogeneity, not overall support.

## H. GT sanity

- **MEASURED OBSERVATION:** Strict evaluation succeeded for seven blocks but failed for `target_B_H2` because exact pre-treatment SLAM/GT timestamp pairing was unavailable.
- **FACT:** The preregistered overall label is therefore `GT_SANITY_UNAVAILABLE`; partial GT values do not alter the primary gate.
- **UNKNOWN:** A complete eight-block GT directional conclusion cannot be made without changing the frozen evaluation rule.

## I. Mechanism

- **MEASURED OBSERVATION:** Accepted keyscans: A1 69, A3 76, A2 100.
- **MEASURED OBSERVATION:** Historical target constraints `E_T`: A1 5, A3 8, A2 8. Non-target historical constraints `E_N`: A1 55, A3 59, A2 65. Local factors: A1 61, A3 68, A2 105.
- **MEASURED OBSERVATION:** Exact classifier totals were `PREVIOUS_SCAN=245`, `RUNNING_SCAN_CHAIN=189`, and exact `TRY_CLOSE_LOOP=0`.
- **FACT:** `NO_EXPLICIT_TRY_CLOSE_LOOP_OBSERVED` and `PHASE_ATTRIBUTION_NOT_IDENTIFIABLE` remain the correct instrumentation-bounded labels.
- **INFERENCE:** A2 changed accepted-keyscan/factor exposure, but equal aggregate `E_T` counts for A2 and A3 did not produce a consistent Target-A/Target-B information effect.

## J. Final scientific gate

- **INFERENCE:** `V14_PROSPECTIVE_NO_SUPPORT`.
- **FACT:** This is a complete 8/8 technical sample, so the result is not classified as technical incompleteness.

## K. Next-step recommendation

- **INFERENCE:** `STOP_CURRENT_CONFIRMATORY_INTERVENTION_AND_ANALYZE_HETEROGENEITY`.
- **FACT:** No v15, predictor training, planner integration, second backend, or additional same-type confirmatory experiment was started.
- **UNKNOWN:** These data alone do not establish whether the Target-A/Target-B split is caused by scene geometry, target-state selection, scan-matching opportunity, or another measured block property.
