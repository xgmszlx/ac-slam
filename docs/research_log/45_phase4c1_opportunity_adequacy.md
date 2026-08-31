# Phase 4C-1 Opportunity Adequacy

Date: 2026-08-31

## Frozen offline test

For seeds 21001--21005, the audit uses the author prior reader, covariance/D-opt
wiring, seeded Concorde solver, `connect_tsp_path`, and
`offline_evaluate_tsp_path`. It stores initial/full paths and hashes. It does not
start ROS, Stage, navigation, Karto, frontier processing or A/B/C execution, so no
closure, trajectory, accuracy, time, distance or map-quality outcome is available
to selection.

PASS requires at least two planned active-loop actions in every seed and at least
ten total over five seeds.

| candidate | 21001 | 21002 | 21003 | 21004 | 21005 | total | loop vertices | gate |
|---|---:|---:|---:|---:|---:|---:|---|---|
| Radish CSAIL | 0 | 0 | 0 | 0 | 0 | 0 | none | FAIL |
| Radish Intel | 0 | 0 | 0 | 0 | 0 | 0 | none | FAIL |
| Radish Freiburg 079 | 0 | 0 | 0 | 0 | 0 | 0 | none | FAIL |
| Radish Mexico | 11 | 11 | 11 | 11 | 11 | 55 | mostly `59,41,82,69,58,166,87,106,100,64,65`; seed 21005 substitutes `153` for `64` | PASS |

Mexico predicted TSP length is 943.7375 m for every seed to numerical precision,
although seeded optimal-tour order/hashes differ. The small degenerate Concorde
instances emit non-fatal basis warnings but still report exact optimum; these
warnings are retained as an observed compatibility caveat, not hidden.

All 20 seed rows, selected vertices, complete paths and SHA-256 hashes are in
`results/phase4c1/opportunity_counts.csv` and `high_level_plans.json`. A repeated
complete audit reproduced those outputs byte-for-byte.

## Interpretation boundary

This establishes only that the frozen high-level planner can propose opportunities.
It says nothing about execution, target-attributable closure acceptance, mapping
quality, or cost. In particular, 11 planned actions must not be presented as 11
successful loops.
