# Phase 4C Statistics Protocol

Date frozen: 2026-08-31, before M2/M3 performance runs

## Unit and estimands

The primary paired unit is **map-seed** (`3 maps x 5 seeds = 15 blocks`), not an
individual active loop. For every block, compute method rates `r_A`, `r_B`, `r_C`
and paired differences C-A, B-A, and C-B.

Target-attributable acceptance rate is:

`executed active-loop actions with >=1 TARGET_ATTRIBUTABLE accepted constraint /
executed active-loop actions`.

This action-level binary numerator prevents multiple accepted constraints from one
action inflating success. A zero-executed-loop denominator is `NA`, never zero.

## Required reporting

- per-map raw target-attributable numerator and executed denominator;
- every map-seed rate and paired difference;
- pooled rates labelled descriptive only;
- map-seed paired mean, median, range, and positive/tie/negative direction count;
- active-loop distance/time contrasts, especially C-B;
- APE/RPE, boundary metrics, and availability/missingness by map-seed;
- all experimental failures retained under the frozen validity policy.

Optional exact randomization/permutation analysis must permute within paired
map-seed blocks. A bootstrap, if used, resamples map-seed clusters. Wilson or
Jeffreys intervals around pooled loop counts must state that they do not account for
within-seed dependence. No loop-level significance test is permitted.

## Outcome hierarchy

1. Loop realization: strong target-attributable action-level acceptance.
2. Execution efficiency: active-loop distance/time; C-B is the selective-versus-
   blind control contrast.
3. Pose-graph impact: final-edge ablation and continuous pose correction only where
   technically available; explicitly exploratory because strict causal pre/post is
   not ready.
4. Trajectory: SE(2) APE, translational RPE, rotational RPE.
5. Mapping: Boundary F1 and symmetric mean boundary distance primary; local 5 m
   metrics bridge/secondary with coverage; occupied IoU secondary.

Outcomes are not collapsed into a new composite score. No post-hoc primary switch,
map exclusion, threshold change, seed addition, or “run B only if C fails” is
allowed.

## Scientific decision rule

Minimum method support requires all three: C has a positive or non-inferior
cross-map realization trend versus A; C reduces blind-revisit cost versus B on most
or all maps; and pose-graph/trajectory/map outcomes show no systematic degradation.
The frozen four scientific cases are
`GENERALIZATION_SUPPORTED`, `REDESIGN_REALIZABILITY_GATE`,
`REOPEN_EXECUTION_HYPOTHESIS`, and `REASSESS_LOOP_UTILITY` as defined in the
machine-readable protocol.

## Eleven-item fallacy scan

1. **Pseudo-replication:** loops are not independent samples; map-seed is primary.
2. **Aggregation/Simpson risk:** show per-map and per-seed before pooled rates.
3. **Denominator drift:** use executed actions and report numerator/denominator.
4. **Rare-event instability:** report raw counts, ties, and ranges; do not infer
   stability from a pooled percentage.
5. **Attrition/survivorship:** retain navigation failures and all technical attempts;
   classify them before inspecting outcomes.
6. **Optional stopping/retry:** exactly five preregistered seeds; no automatic retry
   of unfavorable experimental outcomes.
7. **Order/confounding:** fixed counterbalanced A/B/C order on each new map.
8. **Multiple outcomes/look-elsewhere:** frozen outcome groups and no metric swapping.
9. **Post-hoc threshold/subgroup:** 4.0 m, 0.20 m, 5.0 m and map selection are frozen.
10. **Missingness/coverage:** report availability and local coverage; do not impute
    unavailable local distances as success or failure.
11. **Causal overclaim/construct mismatch:** temporal events are not target success;
    interval graph growth is not closure gain; filled-obstacle IoU is secondary.

The protocol is machine-readable at
`results/phase4c0/statistics/statistics_protocol.json`.
