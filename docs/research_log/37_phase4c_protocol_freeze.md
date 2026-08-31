# Phase 4C Formal Protocol Freeze

Date frozen: 2026-08-31

Status after Phase 4C-0.5 amendment: **BLOCKED; M2/M3 FORMAL RUNS NOT STARTED**.

The original map4/map7 matrix remains preserved as `NOT_STARTED`, but Phase 4C-0.5
found that both maps fail the frozen initial active-loop opportunity criterion.
Document 41 supersedes the earlier authorization language; no row may execute until
two adequate new author maps are frozen.

## Study matrix

M1 reuses the verified 15-run Phase 4B map3 dataset. New data consist of M2 map4
and M3 map7, each with A Original (`oracle_mode=0`), B Always-Trace (`1`), and C
Selective (`2`) at seeds 21001--21005: 30 new runs. The eventual dataset target is
45 map-seed-method runs.

| seed | within-map order |
|---:|---|
| 21001 | A -> B -> C |
| 21002 | B -> C -> A |
| 21003 | C -> A -> B |
| 21004 | A -> C -> B |
| 21005 | B -> A -> C |

B is mandatory. It is not conditionally added after seeing C.

## Controlled variables

Only `oracle_mode` differs across A/B/C. For a map-seed block, code commits, world,
prior, start pose, Concorde seed, robot/sensor, Karto, navigation, TSP objective,
diagnostics-off policy, evaluator, attribution, and statistics remain identical.
The runner must compare solver, seed, `initial_tsp_path`, `full_tsp_path`, predicted
TSP length, and predicted full-TSP length before exploration. A mismatch stops and
marks the block technical-invalid; it cannot be repaired by changing the objective.

Map configurations are:

- M2: `map4/map4`, Stage start `[-17.9,-26.35,0]`, width 39.8 m;
- M3: `map7/map7`, Stage start `[-55,-20,0]`, width 138.2 m.

Both use existing author priors and identity start-relative GT/map registration.

## Frozen method semantics

The online baseline remains nested commit `7993bf8b...`; navigation/Karto remains
`062283d...`. The 4.0 m gate is a configuration-inspired lightweight prototype
proxy. Repair uses a nominal 12 m repair-extension budget with possible terminal-
segment overshoot, 24-waypoint cap, 0.5 m densification, existing direction and
early-stop logic. Every run stores nominal, generated, and executed repair lengths.
No online matching diagnostic or ground truth is available to the planner.

## Required artifacts and offline evaluation

Every run preserves manifest/source hashes, launch command, TSP record/pair check,
stdout/stderr/rosout, observer events and loop intervals, keyscan acquisition
records, accepted typed events, trajectories, loop table, final map, pose graph,
repair records, exploration outcome, and validity state.

Every run must additionally save `selected_loop_vertex_sequence`, `selection_order`,
`selection_timestamp`, `initial_tsp_hash`, and `full_tsp_hash`. If A/B/C sequences
are identical, the paper may say loop targets were matched. If they differ, it may
only say the high-level selection algorithm/objective was held fixed; a common
selected-loop subset is secondary and the primary analysis remains map-seed.

Offline outputs use the common strong attribution in document 31; evo trajectory
protocol from Phase 4B; global Boundary F1 at 0.20 m; symmetric boundary distance;
5 m local revisit metrics plus coverage; and secondary occupied IoU. Strict causal
graph pre/post is not a formal required success endpoint. Final-edge ablation and
continuous correction are exploratory where source graphs permit them.

Phase 4C-0.5 supersedes document 31's target construction. The primary H* is now
the method-neutral high-level loop vertex, the original baseline closest historical
anchor, and exactly seven chronological pre-loop keyscans from that anchor. H* is
constructed before `oracle_mode` branching. The 5 m local ROI remains centred on
the high-level prior vertex and never on an executed replay/repair path.

ROS/catkin runs use system Python 3.8. The Phase 4C offline map/topology tools use
the existing Conda Python 3.12 environment and must run in a clean shell (or with
`PYTHONPATH` unset); inheriting catkin's Python 3.8 package path into Python 3.12 is
forbidden and is checked during preflight.

## Failure and retry policy

- Launch, source mismatch, residual ROS, missing mandatory artifact, or TSP mismatch:
  `TECHNICAL_INVALID`, preserve the attempt, stop, diagnose, and never auto-retry.
- Navigation/exploration timeout or failure with a normally functioning stack:
  `EXPERIMENTAL_FAILURE`, retain as method outcome; do not rerun for favorability.

Before the first formal run, a clean-code preflight must build catkin, run online
method and map evaluator tests, verify no residual ROS, verify diagnostics off and
typed event availability, repeat the A/B/C TSP equality probe on that map, and write
the exact final root/baseline/navigation hashes. The two startup-only smokes do not
replace this formal preflight.

The exact 30-row frozen matrix is
`results/phase4c0/protocol/phase4c_run_matrix.csv`; all rows are `NOT_STARTED`.
