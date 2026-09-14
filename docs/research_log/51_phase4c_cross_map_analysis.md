# Phase 4C Cross-Map Analysis

Date: 2026-09-14

## Dataset and statistical unit

The aggregate contains the intended 15 map-seed blocks and 45 method-runs.
Map-seed is the primary paired unit; individual loops are not treated as
independent inferential samples. No p-values are reported because Mexico supplies
no executed-loop denominator and the remaining ten evaluable blocks contain only
15 target-attributable events.

## Cross-map realization

| Map | A | B | C |
| --- | ---: | ---: | ---: |
| map3 | 0/21 | 0/21 | 1/21 |
| map8 | 5/15 | 5/15 | 4/15 |
| radish_mexico | 0/0 (55 planned) | 0/0 (55 planned) | 0/0 (55 planned) |

Across the two maps with executed loops, A, B, and C each produced 5 target-
attributable events out of 36 executed loops. B therefore supplied no aggregate
system-level execution leverage over A. C retained the same pooled count at much
lower cost than B, but its realization advantage was neither positive nor stable.

## Selection control

All 15 blocks had exact A/B/C equality for initial TSP, full TSP, and recovered
planned-loop sequence. The common-target dataset contains 273 method-loop rows:
91 planned target occurrences per method. Therefore observed differences are not
explained by method-induced selection divergence in this dataset.

## C versus B cost

Among the ten blocks where active loops executed:

- map3: C reduced active-loop distance in 5/5 blocks by 68.61 m on average and
  time in 5/5 by 275.44 s on average;
- map8: C reduced distance in 4/5 blocks by 42.83 m on average and time in 5/5
  by 166.06 s on average;
- Mexico contributes no active-loop cost comparison because all loop intervals
  are absent.

Across all 15 blocks, the pre-specified paired summary contains five structural
Mexico ties: C-B distance mean -37.15 m, median -32.07 m, range -162.77 to
+1.74 m (9 lower, 5 ties, 1 higher); time mean -147.17 s, median -108.0 s,
range -850.2 to 0 s (10 lower, 5 ties). These 15-block summaries must be read
together with the structural-tie caveat.

## C versus B SLAM and map consistency

The cross-map direction is mixed rather than a consistent benefit:

- APE: C was slightly better on map3 on average, worse in 4/5 map8 blocks, and
  worse in all five incomplete Mexico runs;
- translation RPE: C was lower in all map3 blocks and 4/5 map8 blocks;
- rotation RPE: C was lower in all map3 blocks but mixed on map8 and Mexico;
- global map geometry: C was worse than B on every map8 seed for both Boundary
  F1 and symmetric boundary distance;
- local revisit geometry: C was worse on 4/5 map8 seeds for local Boundary F1
  and worse on all five for local symmetric distance.

Thus the cost reduction is repeatable on the two executable environments, but
the supporting no-degradation condition is not met.

## Pose correction and Pareto interpretation

All 15 target-attributable accepted events had available before/after graph
estimates. Mean, median, and maximum historical-pose correction were exactly
0.0 m for every event. This does not invalidate the constraints, but it provides
no observed trajectory-correction benefit and raises a loop-utility concern.

The realization-cost figure therefore has two distinct messages: C occupies a
lower-cost region than B on map3/map8, while B does not improve pooled
realization and C does not preserve or improve map8 map consistency. Mexico is
shown only as planned-but-unexecuted and cannot establish a Pareto comparison.
