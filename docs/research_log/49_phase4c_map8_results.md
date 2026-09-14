# Phase 4C Map8 Results

Date: 2026-09-14

## Completion and pairing

All 15 map8 method-runs completed as `VALID`. All five A/B/C blocks had exact
initial-TSP, full-TSP, and planned-loop-sequence agreement. Each method planned
and executed 15 active loops (three per seed), so the frozen primary acceptance
denominator is fully observed.

## Realization outcomes

| Method | Planned | Executed | TARGET_ATTRIBUTABLE | R_target | Temporal | Passive/unrelated |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A Original | 15 | 15 | 5 | 0.333 | 4 | 7 |
| B Always-Trace | 15 | 15 | 5 | 0.333 | 7 | 7 |
| C Selective | 15 | 15 | 4 | 0.267 | 6 | 3 |

Per-seed target realization rates for A/B/C were:

| Seed | A | B | C |
| --- | ---: | ---: | ---: |
| 21001 | 0.333 | 0.333 | 0.333 |
| 21002 | 0.000 | 0.333 | 0.333 |
| 21003 | 0.333 | 0.000 | 0.333 |
| 21004 | 0.667 | 0.667 | 0.000 |
| 21005 | 0.333 | 0.333 | 0.333 |

B did not increase the aggregate numerator over A. C produced one fewer accepted
target-attributable event than A or B. The seed-level direction is not stable.

## Execution cost

| Method | Mean active distance (m) | Mean active time (s) | Repairs | No repair | Early stops |
| --- | ---: | ---: | ---: | ---: | ---: |
| A Original | 68.824 | 150.02 | 0 | 0 | 0 |
| B Always-Trace | 106.559 | 314.22 | 15 | 0 | 0 |
| C Selective | 63.725 | 148.16 | 10 | 5 | 9 |

For C minus B, active-loop distance changed by -42.834 m per seed on average
(median -32.857 m; range -97.234 to +1.744; 4 lower, 1 higher). Active-loop time
changed by -166.06 s on average (median -152.6 s; range -304.5 to -50.5; all
five lower). C generated 115.69 m of repair path in total and executed 202.53 m
inside repaired loops. Its 81.84 m avoided nominal extension is a geometric lower
bound, not observed counterfactual saved travel.

## Trajectory and map outcomes

Means over five seeds:

| Method | APE (m) | RPE trans. (m) | RPE rot. (deg) | Boundary F1 | Sym. boundary dist. (m) | Local F1 | Local dist. (m) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 0.138 | 0.03384 | 0.1818 | 0.5984 | 0.2019 | 0.7492 | 0.1532 |
| B | 0.120 | 0.03362 | 0.2123 | 0.6050 | 0.1990 | 0.7585 | 0.1522 |
| C | 0.179 | 0.03203 | 0.2178 | 0.5657 | 0.2156 | 0.6388 | 0.1993 |

C versus B had lower translation RPE in four of five seeds, but higher APE in
four of five. Global Boundary F1 was lower in all five C runs, symmetric boundary
distance was higher in all five, local Boundary F1 was lower in four of five,
and local symmetric boundary distance was higher in all five. This is a
consistent map-geometry regression on map8, despite C's lower execution cost.

## Evidence paths

Primary evidence is in `results/phase4c/aggregate/run_table.csv`,
`acceptance_by_map_method.csv`, `map_seed_paired_effects.csv`, and the selected
attempts below `results/phase4c/formal/map8/`.
