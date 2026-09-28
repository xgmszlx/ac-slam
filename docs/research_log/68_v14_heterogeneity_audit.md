# 68 — V14 context-dependent realization audit

## Scientific status and scope

- **FACT:** The prospective v14 gate remains `V14_PROSPECTIVE_NO_SUPPORT`.
- **FACT:** The frozen recommendation remains `STOP_CURRENT_CONFIRMATORY_INTERVENTION_AND_ANALYZE_HETEROGENEITY`.
- **FACT:** This audit is `POST_CONFIRMATORY_EXPLORATORY` and every generated analysis row is labelled `EXPLORATORY_HETEROGENEITY_ONLY`.
- **FACT:** The universal broad-sweep hypothesis is stopped. Target B's 4/4 positive result is not a confirmatory success, and Target A's 4/4 negative result does not show that broad sweep is universally harmful.
- **FACT:** No Stage data were collected, no v15 run was started, and no A1/A3/A2 action, planner, predictor, or backend was changed.

The audit reads the eight frozen canonical-history blocks under `results/realizability_pilot/p1_v14_confirmatory_20260928/` and writes only to `results/realizability_pilot/p1_v14_heterogeneity_20260928/`.

## Immutability and provenance

At audit start, local branch and remote branch were both `research/phase4c-formal` at `42944155d268dfa46d3d0a1079133635addef595`, and the worktree was clean. The frozen v14 Git tree object is `82c934201e75dc42c9718455c860fa1cc4f2630e`. The manifest records SHA256 values for the preregistration, physical and backend locks, primary analysis, mechanism analysis, gate, and final report. All 14 hashes passed both before and after this audit.

Canonical provenance:

- `results/realizability_pilot/p1_v14_heterogeneity_20260928/provenance/v14_immutable_manifest.json`
- `results/realizability_pilot/p1_v14_heterogeneity_20260928/provenance/v14_post_audit_verification.json`

## One-row-per-block result

The following values are recomputed from frozen raw captures/GT and frozen replay outputs. Deltas are A2 minus A3.

| Block | Target | D_trigger | D_sweep | Delta yaw [rad] | Delta completion scans | Delta keyscans | Delta total | Delta local | Delta historical | A2-only endpoints | A3-only endpoints |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| target_A_H1 | A | 0.0335 | -0.1084 | 0.6017 | 26 | 1 | 1 | 3 | -2 | 3 | 5 |
| target_A_H2 | A | 0.1656 | -0.2904 | 0.5622 | 26 | 1 | 2 | 3 | -1 | 4 | 5 |
| target_A_H3 | A | -0.0008 | -0.1318 | 0.5969 | 24 | 1 | 2 | 3 | -1 | 3 | 4 |
| target_A_H4 | A | 0.1408 | -0.3387 | 0.5611 | 26 | 1 | 2 | 3 | -1 | 4 | 5 |
| target_B_H1 | B | 0.0001 | 0.1585 | 2.6417 | 55 | 5 | 9 | 7 | 2 | 6 | 4 |
| target_B_H2 | B | 0.0061 | 0.2218 | 2.4805 | 54 | 5 | 9 | 6 | 3 | 7 | 4 |
| target_B_H3 | B | 0.0020 | 0.1942 | 2.3654 | 52 | 5 | 9 | 6 | 3 | 10 | 7 |
| target_B_H4 | B | 0.0095 | 0.1601 | 2.4946 | 54 | 5 | 9 | 6 | 3 | 7 | 4 |

**FACT:** Raw-GT recomputation confirms the expected dose separation: Target A Delta yaw ranges from 0.5611 to 0.6017 rad; Target B ranges from 2.3654 to 2.6417 rad. The ranges do not overlap. Target A has exactly +1 accepted keyscan per block and -1/-2 historical factors; Target B has exactly +5 accepted keyscans and +2/+3 historical factors.

Full tables:

- `analysis/block_heterogeneity_table.csv`
- `analysis/action_dose_table.csv`
- `analysis/realized_measurement_difference_table.csv`
- `analysis/pretreatment_feature_table.csv`
- `analysis/pretreatment_feature_contract.json`

The pre-treatment contract explicitly marks every candidate feature true or false. Local scan-geometry and occupancy-geometry descriptors are false because no strictly pre-treatment, consistently serialized representation was available; they were not reconstructed from outcomes. Future predictors are restricted to the true allow-list, but no predictor was trained here.

## Historical endpoint realization

**FACT:** Historical-factor endpoint sets are not nested. Every block has both A2-only and A3-only endpoint pairs. Jaccard overlap is 0.308–0.364 for Target A and 0.056–0.286 for Target B. Thus, A2 changes which historical associations are realized, not merely their count.

**FACT:** All 140 historical factors have exact endpoint pairs, target/non-target attribution, creation provenance/family, match response, full 3x3 covariance, information eigenvalues, insertion geodesic/hops, and cycle length when available. The frozen factors comprise 124 `RUNNING_SCAN_CHAIN` and 16 `PREVIOUS_SCAN` associations; no historical factor in these A2/A3 branches was an explicit `TRY_CLOSE_LOOP` constraint.

**MEASURED ASSOCIATION:** `Delta historical factors` and `D_sweep` have the same non-zero sign in all eight blocks: `HISTORICAL_REALIZATION_SIGN_ALIGNMENT = 8/8`. Under a simple equiprobable independent-sign reference, all-eight alignment has probability 1/256; because the check is post-confirmatory and target-confounded, this is descriptive rather than confirmatory evidence.

The comparison is more specific than “more factors”:

| Candidate realization measure | Sign aligned with D_sweep | Evaluable blocks |
|---|---:|---:|
| Historical-factor difference | 8 | 8 |
| Total-factor difference | 4 | 8 |
| Local-factor difference | 4 | 8 |
| Accepted-keyscan difference | 4 | 8 |

**INFERENCE:** Historical measurement realization is the closest observed mediator of the primary effect among the audited count variables. It is not established as a cause: target, angular dose, completion exposure, and historical realization are not experimentally separated in v14.

Endpoint artefacts:

- `analysis/endpoint_set_comparison.csv`
- `analysis/historical_factor_details.csv`
- `analysis/sign_alignment_audit.json`

## Target confounding and competing hypotheses

The target indicator is highly associated with Delta yaw (Spearman 0.873), Delta completion scan index (0.900), Delta historical factors (0.918), endpoint novelty (0.889), and nonlocal historical gain (0.918); their Target A/B ranges do not overlap. These are marked `TARGET_FEATURE_CONFOUNDING_NOT_IDENTIFIABLE`.

- **H1 — ACTION_DOSE, MEASURED ASSOCIATION:** Delta yaw correlates with D_sweep (Pearson 0.939; Spearman 0.786). **UNKNOWN:** Its causal contribution cannot be separated from target/context in these eight blocks.
- **H2 — MEASUREMENT_REALIZATION, MEASURED ASSOCIATION:** Historical-factor realization gives the unique 8/8 sign alignment, whereas total factors, local factors, and keyscans each give 4/8. **INFERENCE:** This is the strongest measured mechanism candidate. **UNKNOWN:** It remains target-confounded and endpoint utility may depend on context.
- **H3 — PREGRAPH_CONTEXT, MEASURED ASSOCIATION:** Simple Spearman associations with D_sweep are 0.393 for pre-cycle rank and 0.238 for J_pre. Leave-one-block values remain modest/unstable (cycle rank 0.158–0.593; J_pre -0.143–0.429). **UNKNOWN:** n=8 and possible interactions prevent ruling context in or out.
- **H4 — SCENE_ASSOCIATION_GEOMETRY, UNKNOWN:** Arrival/anchor geometry is recorded, but target geometry and realized dose were not crossed. Strict local scan/occupancy descriptors are unavailable, so this mechanism is not identified.

The evidence-ranked direction is therefore `MULTIFACTOR_INTERACTION_CANDIDATE`, not a single dominant cause. The machine-readable accounts are:

- `analysis/feature_correlation_matrix.csv`
- `analysis/target_feature_confounding.csv`
- `analysis/leave_one_block_sensitivity.csv`
- `analysis/competing_hypotheses.json`
- `analysis/causal_relationship_summary.json`

The relationship file distinguishes measured associations, inferred links, and unidentified direct/context-modifying links. Its arrows are a hypothesis map, not an identified causal DAG.

## D_trigger and adaptive-action hypothesis

**FACT:** Target A D_trigger has mean 0.08476 and median 0.08714 (3/4 positive). Target B has mean 0.00440 and median 0.00402 (4/4 positive but close to zero). A3 versus A1 adds historical factors by `[2, 1, 0, 1]` at Target A and `[1, 1, 0, 1]` at Target B.

**INFERENCE:** The pattern is compatible with `CONTEXT_DEPENDENT_ACTION_INTENSITY_HYPOTHESIS`: the near-threshold action may already capture most useful realization at Target A, while the broader action is associated with useful additional realization at Target B.

**UNKNOWN:** The hypothesis is not proved. In particular, “minimal sufficient at A” and “broad needed at B” cannot be separated from scene, exposure, endpoint identity, or factor-utility differences using v14 alone.

## Cross-protocol context

`analysis/cross_protocol_context.csv` records 14 legacy rows from v13-C, post-hoc Target B FULL, v12, and the technically incomplete v12b status. Every row is marked `NOT_DIRECTLY_COMPARABLE` and `pooled_with_v14 = false`; no pooled p-value is computed. Older results show some compatible positive Target B and historical-realization patterns, but v13-C/v12 Target A does not reproduce v14's uniform negative sign. This supports protocol sensitivity, not replication.

## Next experiment — design only

`design/CONTEXT_DISENTANGLEMENT_EXPERIMENT.json` specifies, but does not execute, a Target A/B × dose design. Both targets receive identical post-arrival cumulative-yaw packages:

- ZERO: 0 rad, static reference under the same sensing budget;
- THRESHOLD: 1.08795 rad, the median v14 A3 planned post-arrival angular path;
- HIGH: 3.14159 rad, the median v14 A2 planned post-arrival angular path.

The template uses a common initial orientation, symmetric rotation returning to the same final orientation, fixed N=347 sensing budget, fresh preregistered histories, full seed-pool qualification before outcome-blind selection, and no outcome-driven replacement. The primary unit remains the canonical-history block; the intended estimand is dose × target/context interaction in realized historical endpoints and J_T. `execution_authorized` is false.

## Figures and reproducibility

Seven SVG figures are under `results/realizability_pilot/p1_v14_heterogeneity_20260928/figures/`, covering the requested block effects, dose and measurement associations, three-layer realization chain, A1/A3/A2 J_T trajectories, pre-graph context, and endpoint overlap/novelty.

Reproduce the audit without ROS or new data:

```bash
PYTHONPATH=tools/realizability_pilot python3 tools/realizability_pilot/v14_heterogeneity_audit.py
PYTHONPATH=tools/realizability_pilot python3 -m pytest -q tools/realizability_pilot/test_v14_heterogeneity.py
```

The dedicated audit suite passes 8/8 tests. The compatible current-HEAD v14 test selection passes 21 tests with three legacy preregistration-construction tests deselected. Those three deliberately refuse to construct a new v14 preregistration unless current HEAD equals the original authorized base commit; invoking them now fails at that guard as intended and does not indicate frozen-result corruption.

## Final audit judgment

- **FACT:** v14 remains a prospective no-support result for the universal broad-sweep intervention.
- **MEASURED ASSOCIATION:** historical-factor realization tracks D_sweep sign 8/8 and more closely than total/local factor or keyscan counts.
- **INFERENCE:** the most defensible research direction is `MULTIFACTOR_INTERACTION_CANDIDATE` involving action dose, backend measurement realization, and context-dependent endpoint utility.
- **UNKNOWN:** which component is causal cannot be determined because target and effective dose/realization are highly confounded.
- **DECISION:** do not revive the universal intervention, do not train a predictor on n=8, and do not start another experiment without separately authorizing the predesigned context-disentanglement protocol.
