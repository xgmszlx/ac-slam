# Phase 4B Mapping Reanalysis

Date: 2026-08-31

The frozen Phase 4C evaluator was applied offline to all 15 valid Phase 4B map3
runs. No robot run, planner action, Karto parameter, raw artifact, or old aggregate
was changed. Detailed outputs are under `results/phase4c0/map_evaluation/phase4b_map3`
and new aggregate tables under `results/phase4b/map3/aggregate_v2`.

## Global results

| Method | Boundary F1 mean / median / range | symmetric distance mean / median / range (m) | occupied IoU mean (secondary) |
|---|---|---|---:|
| A | 0.4106 / 0.3920 / 0.3159--0.5586 | 0.6095 / 0.6023 / 0.3856--0.8525 | 0.06645 |
| B | 0.5045 / 0.5235 / 0.4361--0.5842 | 0.4771 / 0.4589 / 0.4478--0.5284 | 0.08043 |
| C | 0.4495 / 0.4855 / 0.3278--0.5455 | 0.5199 / 0.4763 / 0.4178--0.6803 | 0.06751 |

C versus A Boundary F1 is positive in 4/5 seeds but includes one large negative
difference; symmetric distance is lower (better) in 4/5 and higher in one seed.
C is worse than B in Boundary F1 for 3/5 seeds and in symmetric distance for 2/5.
With one map and five seeds, these are mixed descriptive observations, not evidence
of general map improvement.

## Local revisit results

Loop-row descriptive means (not inferential units) are:

| Method | eligible Boundary F1 mean (n) | eligible symmetric distance mean m (n) | observed coverage mean (n=21) |
|---|---:|---:|---:|
| A | 0.2561 (14) | 0.6993 (9) | 0.98995 |
| B | 0.3061 (11) | 0.6540 (8) | 0.99735 |
| C | 0.2736 (11) | 0.4941 (7) | 0.99491 |

Across 63 method-loop rows, local Boundary F1 status was: 24 `AVAILABLE`, 9
`NO_ESTIMATED_BOUNDARY`, 3 `ESTIMATED_BOUNDARY_WITHOUT_GT`, and 27
`NOT_APPLICABLE_NO_GT_BOUNDARY`. Distance is undefined for one-empty cases. Missing
values are not replaced with zero or one.

For each seed the planned loop-vertex sequence is identical across A/B/C, so target
coordinate comparability is established. Nevertheless, differing availability and
only five seed blocks prohibit treating the 63 rows as independent evidence. Formal
Phase 4C will aggregate/contrast at map-seed level and show coverage alongside local
scores.

## Interpretation

The boundary metrics are more geometrically interpretable than filled-cell IoU,
but Phase 4B remains mixed: B has the best global map means; C is usually better
than A but not uniformly, and local eligible subsets vary. The reanalysis does not
upgrade the Phase 4B scientific conclusion.
