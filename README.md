# ac-slam

最新研究状态（2026-10-20）：[RGB-D删除消融结题](research_archive/20261020_rgbd_deletion_ablation/REPORT.md)。**STOP_CURRENT_COMBINATION_PROTOTYPE**：E1二维删除、E2三维删除及S0重复各一次完成；在线ATE为0.749/0.714/0.554m，两项消融均差于旧S1和两次原生S0。未找到可继续投入的删除改进环节，三次预算关闭，不追加模块或实验。原[S0/S1/S2真实比较](research_archive/20261020_rgbd_combo_e2e/REPORT.md)、更早失败及旧主动/AMCL收口保持。

Reproducible research workspace for the public Graph-Based SLAM-Aware
Exploration baseline. The repository preserves the code baseline, pinned
third-party source snapshots, Phase 1--4 experiment tooling, research logs, and
compact evidence artifacts used for the reported observations. High-volume
per-frame replay streams and machine-generated ROS logs remain local.

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
results/        compact run manifests, ledgers, audits, and result summaries
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
- Controlled v8--v11 experiments isolated history, action geometry, sensing
  budget, keyscan triggering, and realized factor generation. v12 produced a
  Target-A descriptive signal but was technically incomplete because Target B
  yielded no usable blocks; those Target-A effects are not confirmatory.
- v12b repaired target-specific timing and replay instrumentation, then ran a
  fresh preregistered collection. It closed as
  `CONFIRMATORY_EXPERIMENT_TECHNICALLY_INCOMPLETE`: Target A delivered 4/4
  usable blocks, Target B only 1/4, with recurrent target matching and prefix
  identity failures. No v12b scientific endpoint analysis was executed.

Primary reports:

- `docs/research_log/06_phase1_smoke_runs.md`
- `docs/research_log/07_phase2a_paired_loop_effectiveness.md`
- `docs/research_log/08_karto_loop_closure_mechanism.md`
- `docs/research_log/53_phase4c_final_decision.md`
- `docs/research_log/54_constraint_realizability_pilot_protocol.md`
- `docs/research_log/56_constraint_realizability_direction_audit.md`
- `docs/research_log/61_confirmatory_action_constraint_experiment.md`
- `docs/research_log/62_v12b_technical_repair_and_confirmatory_rerun.md`

The latest controlled confirmatory attempt is technically incomplete. No final
method-generalization or action-effect claim is made.
