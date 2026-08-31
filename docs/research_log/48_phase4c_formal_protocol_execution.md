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

## Execution state

At this protocol-freeze checkpoint, performance runs remain **NOT_STARTED**.
Preflight and each formal attempt will be recorded below after execution; no
scientific source will be edited between the passing preflight and completion of
the matrix.
