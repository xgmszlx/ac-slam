# ac-slam

Reproducible research workspace for the public Graph-Based SLAM-Aware
Exploration baseline. The repository preserves the code baseline, pinned
third-party source snapshots, Phase 1--4 experiment tooling, research logs, and
raw experiment archives used for the reported observations.

The code baseline is intentionally defined as:

> Author public code + required runtime/path compatibility fixes +
> observation-only instrumentation.

Known paper-code discrepancies are documented but are not silently corrected
in this baseline.

## Repository layout

```text
baseline/       author baseline plus separately documented experiment layers
dependencies/   pinned navigation_2d, pyconcorde, and p2os source
catkin_ws/      portable catkin workspace metadata and helper scripts
docs/           Phase 0–4 research, protocol, and mechanism audit logs
tools/          reproducible experiment, collection, and analysis scripts
results/        raw runs, trajectories, maps, pose graphs, and summaries
evaluation/     evo environment reconstruction notes
```

ROS build products, local Python packages, ROS logs, caches, and downloaded
Concorde binaries are deliberately excluded because they are machine-specific
or third-party redistributables. Exact versions and source URLs are recorded in
`catkin_ws/DEPENDENCIES.lock`, `requirements.txt`, and `THIRD_PARTY.md`.

## Environment

The measured environment used Ubuntu 20.04, ROS Noetic, and system
`/usr/bin/python3` 3.8.10. See
`docs/research_log/05_runtime_environment.md` for the complete audited setup.

After installing ROS Noetic and Stage, reconstruct the workspace-local Python
packages and Concorde executables from the pinned manifests, then build:

```bash
cd ac-slam
/usr/bin/python3 -m pip install --target catkin_ws/python -r requirements.txt

# Download Concorde/Linkern using the URLs in catkin_ws/tools/concorde/README.md

cd catkin_ws
source /opt/ros/noetic/setup.bash
catkin_make -DPYTHON_EXECUTABLE=/usr/bin/python3 -DCMAKE_BUILD_TYPE=Release
source ./activate.sh
```

The workspace source links are relative and resolve to the vendored snapshots
under `baseline/` and `dependencies/`.

## Research status

- Phase 1: environment and three public-code baseline smoke runs completed.
- Phase 2A: five paired map3 Prior-TSP vs SLAM-aware runs completed.
- Phase 2B: active-loop failure-mechanism diagnosis completed.
- Phase 4B/4C: controlled A/B/C evaluation completed on map3 and map8; the
  Radish Mexico environment exposed a separate planned-to-executed blocker.
- Formal Phase 4C contains 15 map-seed blocks and 45 method-runs. Initial TSP,
  full TSP, and planned-loop sequences match exactly within every A/B/C block.
- On the two maps where loops executed, Original, Always-Trace, and Selective
  each produced 5 target-attributable accepted events out of 36 executed loops.
  Selective reduced active-loop cost relative to Always-Trace, but did not meet
  the no-degradation condition because map8 geometry regressed systematically.
- The current rule-based decision is `REOPEN_EXECUTION_HYPOTHESIS`, not method
  generalization or a final algorithm claim.
- A subsequent constraint-realization Pilot corrected an important measurement
  boundary: zero explicit `TryCloseLoop` callbacks does not imply zero backend
  measurements. A fresh v7 episode recorded three exact target-attributable,
  non-explicit graph constraints with covariance while explicit callbacks stayed
  at zero. The earlier `0/21 explicit closures` observation remains valid; the
  stronger `0/21 backend constraints` interpretation does not.

Primary reports:

- `docs/research_log/06_phase1_smoke_runs.md`
- `docs/research_log/07_phase2a_paired_loop_effectiveness.md`
- `docs/research_log/08_karto_loop_closure_mechanism.md`
- `docs/research_log/53_phase4c_final_decision.md`
- `docs/research_log/54_constraint_realizability_pilot_protocol.md`

The Pilot v7 evidence is currently `ANALYZED_NOT_INDEPENDENTLY_VERIFIED`: one
fresh observer-validation episode is complete and three sentinel conditions are
still pending. No final method-generalization claim is made.
