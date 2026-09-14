# Phase 4C Formal Protocol and Execution Record

Date: 2026-08-31

## Scope and freeze

Phase 4C reuses the 15 Phase 4B map3 method-runs and adds 30 performance runs:
five seeds by A/B/C on frozen `map8`, and the same matrix on frozen
`radish_mexico`. The scientific base is `3ffaa2672816d5f5f20e0d8019054bdd47f2961b`.
The formal branch contains experiment orchestration and offline aggregation only;
it does not change the planner, gate, Karto, navigation, prior, attribution target,
mapping metrics, or statistical unit.

A/B/C differ only in `oracle_mode` (`0/1/2`). The runner test removes that one
launch argument and requires the remaining command tokens to be identical. The
legacy map3 Phase 4B command is also required to remain byte-equivalent to the
recorded command.

## Frozen materials

- M1: existing map3 Phase 4B data, five paired seeds.
- M2: `map8`, start `[0, 0, 0]`, author world/GT/prior. Frozen hashes are recorded
  in `tools/phase4c_formal_common.py` and copied into every run manifest.
- M3: `radish_mexico`, start `[-6.25, -1.6, 0]`, Phase 4C-1 frozen world/GT/prior.
  The runtime materializer verifies every source and destination SHA-256 and
  refuses to overwrite a mismatching file. It never regenerates the prior.
- Runtime: ROS Noetic, system Python 3.8, diagnostics disabled.
- Trajectory evaluation: evo 1.31.1, maximum timestamp difference 0.05 s, no
  alignment, XY projection.
- Map evaluation: 0.20 m boundary tolerance and a method-neutral 5 m ROI centered
  at the selected high-level prior vertex.
- Attribution: unique active interval plus accepted historical-chain overlap with
  the fixed seven-keyscan method-neutral H*.

## Order and attempt policy

Both new maps use `21001 ABC`, `21002 BCA`, `21003 CAB`, `21004 ACB`, and
`21005 BAC`. Every attempt is append-only under `attempt_NN`. Experimental
failures are selected as outcomes and are not retried. A technical retry requires
an explicit `MAP:SEED:CONDITION` authorization and a preceding attempt classified
`TECHNICAL_INVALID`. There is no outcome-based stopping or automatic retry.

Initial TSP mismatch is fail-closed before mapping. Full-TSP or selected-loop
sequence divergence after a matched initial condition is retained as an outcome,
not invalidated. Every run stores the selected sequence, order, timestamp, and
initial/full canonical path hashes.

## Frozen commands

```bash
source catkin_ws/activate.sh
/usr/bin/python3 tools/preflight_phase4c_formal.py
/usr/bin/python3 tools/run_phase4c_formal.py
/usr/bin/python3 tools/analyze_phase4c_formal.py
```

The preflight checks clean tracked worktrees in the root, baseline, and
`navigation_2d` repositories; free disk; frozen environment hashes; clean catkin
build; unit tests; no residual ROS master; all core nodes/services; diagnostics
off; and identical frozen TSP input under modes 0/1/2 for both new maps. It writes
`results/phase4c/formal/protocol_manifest.json`. The performance runner refuses a
different commit or a dirty tracked worktree.

## Execution record

The detached formal suite finished at
`2026-09-12T02:58:08.185019+00:00`. The selected dataset contains all 30 new
map8/Mexico cells. Together with the 15 reused map3 cells, the aggregate contains
45 method-runs and all 15 planned map-seed blocks.

| Map | Selected cells | Outcome |
| --- | ---: | --- |
| map3 (reused Phase 4B) | 15 | 15 `VALID` |
| map8 | 15 | 15 `VALID` |
| radish_mexico | 15 | 15 `EXPERIMENTAL_FAILURE` |

Mexico was not censored or rerun for an unfavorable outcome. Four interrupted
attempts were retained as `TECHNICAL_INVALID`, followed by explicitly selected
attempts:

- map8/21002/C `attempt_01`: external runner/session interruption;
- radish_mexico/21002/B `attempt_01`: external runner/session interruption;
- radish_mexico/21002/A `attempt_01`: external detached-runner interruption;
- radish_mexico/21004/B `attempt_01`: external detached-runner interruption.

All other cells selected `attempt_01`; the four cells above selected
`attempt_02`. Automatic retry remained disabled. Mexico seed 21004/B ended at
the frozen 18,001 s hard timeout; the other 14 selected Mexico cells returned
Explore action status 4. These are experimental failures under the frozen
definition, not technical invalidations.

## Post-run aggregation audit

The original runtime `selection_sequence.json` and `loops.json` files did not
record a Mexico loop until that loop became the next executable target. In every
Mexico run, navigation failed before this transition, while the append-only
`events.csv` already contained eleven `LOOP_INSERTED` records. Therefore the
runtime summary's zero planned-loop count was an instrumentation omission.

The offline analyzer was minimally amended after the runs to use
`LOOP_INSERTED` as the authoritative planned high-level sequence, create
unexecuted `NOT_REACHED` rows, and write a separate
`selection_sequence_observed.json`. No raw artifact, planner, treatment,
attribution rule, metric, or selected attempt was changed. The correction
changes Mexico from `0 planned / 0 executed` to `11 planned / 0 executed` per
run. Unit tests cover both zero-loop blocks and event-based recovery.

The final offline commands were:

```bash
source catkin_ws/activate.sh
/usr/bin/python3 -m unittest \
  tools/test_phase4a_selective.py \
  tools/test_phase4b_mapping.py \
  tools/test_phase4c0_mapping.py \
  tools/test_phase4c_formal_runner.py

env -u PYTHONPATH /home/wcqw/anaconda3/bin/python \
  tools/analyze_phase4c_formal.py \
  > results/phase4c/aggregate/analyzer_stdout.json
```

The ROS-side suite passed 19/19 tests with system Python 3.8. The analyzer's
focused suite passed 7/7 under the frozen offline environment (Python 3.12.7,
NumPy 1.26.4, SciPy 1.13.1, Matplotlib 3.9.2). The split is deliberate: ROS
runtime remains isolated from Conda, while the offline statistical/plotting
stack uses the pinned Conda environment.

## Integrity conclusion

The formal method code remained frozen during all performance attempts. The
protocol manifest records root commit
`342e7c1e4af47e3c256a87bf3511d3d910e34748`, baseline commit
`7993bf8b93e503b352d89e3992b8e5d7b08e4459`, and navigation commit
`062283d364d891603a546b83e557ab638ffaa163`. The analyzer change is explicitly
post-hoc and observation-only. All raw and invalid attempts remain preserved
under `results/phase4c/formal/`.
