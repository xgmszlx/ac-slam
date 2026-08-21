# ac-slam

Reproducible research workspace for the public Graph-Based SLAM-Aware
Exploration baseline. The repository preserves the code baseline, pinned
third-party source snapshots, Phase 1/2 experiment tooling, research logs, and
raw experiment archives used for the reported observations.

The code baseline is intentionally defined as:

> Author public code + required runtime/path compatibility fixes +
> observation-only instrumentation.

Known paper-code discrepancies are documented but are not silently corrected
in this baseline.

## Repository layout

```text
baseline/       pinned author baseline at commit 211642d66c...
dependencies/   pinned navigation_2d, pyconcorde, and p2os source
catkin_ws/      portable catkin workspace metadata and helper scripts
docs/           Phase 0–2 research and mechanism audit logs
tools/          reproducible experiment, collection, and analysis scripts
results/        Phase 1/2 raw runs, trajectories, maps, graphs, and summaries
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
- Current measured behavior: 21 planned and executed active loops produced zero
  confirmed Karto loop constraints, while 3/3 valid positive-control revisits
  produced accepted Karto closures.

Primary reports:

- `docs/research_log/06_phase1_smoke_runs.md`
- `docs/research_log/07_phase2a_paired_loop_effectiveness.md`
- `docs/research_log/08_karto_loop_closure_mechanism.md`

No final algorithmic solution or paper-intent variant is mixed into this code
baseline.
