# STATUS — continuous revisit action validation (round of 2026-10-10)

Maintained continuously while the round runs.  Newest entries first.

## Current state

| item | value |
| --- | --- |
| branch | `research/phase4c-formal` |
| protocol | `p1_continuous_revisit_v1` (`tools/realizability_pilot/continuous_revisit/protocol.py`) |
| places / route | 4 places on one 64.4 m loop; worst clearance 1.10 m |
| matrix | 48 episodes = 4 places x 3 repeats x 4 actions |
| execution | serial, one Stage + Karto run per episode, resumable |
| smoke | 4/4 arms succeeded and passed all five handoff checks |
| main matrix | **PAUSED 2026-10-10 16:0x at 40 SUCCEEDED / 1 FAILED / 1 INTERRUPTED / 6 PENDING** |
| repeatability | planned (8 executions = 4 fixed configurations x 2), not started |
| analysis at pause point | 40 episodes analysed, 8 without a successful attempt (6 pending, 1 failed, 1 interrupted) |

### Pause point (user-requested interruption, 2026-10-10)

The suite was stopped gracefully: the runner received SIGTERM, so the episode in
flight is recorded as `INTERRUPTED` (episode `0042_place_D_r2_L-`) and every
finished episode is committed to disk.  All ROS processes were stopped; no run
was left half-written inside the ledger.

Outstanding work when the round resumes:

1. `resume` the main matrix: retries the interrupted episode and the six pending
   episodes, and retries the one genuine technical failure
   (`0022_place_B_r3_L+`, `RuntimeError: MoveTo history_02 failed with state 4` —
   the navigator aborted the history move; first failure record kept).
2. Run the repeatability suite (already planned by `runner.py plan
   --repeatability ...`, 8 executions).
3. Re-run analysis/figures/verify and fill doc 77 sections 6–8 with the final
   numbers.

Partial results at the pause point are written into
`docs/research_log/77_continuous_revisit_action_validation.md` (marked as
partial) and into `analysis/` (which always reflects whatever episodes exist).

## Implementation fixes made during smoke validation

All fixes happened **before** any main-matrix episode was executed, and each is
recorded here with its evidence:

1. **Wrong action message type** in the first driver draft (`cpp_solver` instead
   of `nav2d_navigator.msg.MoveToPosition2DAction`).  Evidence: import of
   `cpp_solver.msg` has no `MoveToPosition2DGoal`; `pilot_driver.move_to` uses
   `nav2d_navigator.msg`.  Fixed by using the navigator message and the frozen
   `target_distance = 0.25`, `target_angle = 0.1`.
2. **Wrong laser topic** `/scan` (no publisher).  Evidence: `rostopic info
   /base_scan` shows `/Stage` publishing, and `exploration.launch` remaps `scan`
   to `base_scan`.  Fixed: the driver subscribes `/base_scan`
   (`~scan_topic` parameter) and recorded zero scans before the fix.
3. **Wrong TF frames** `map -> laser`.  Evidence: the live TF tree is
   `map -> offset -> odom -> base_footprint -> base_link -> base_laser_link`.
   Fixed: the scan record now carries the laser and base poses in the
   correction-free `odom` chain (continuity) plus the SLAM-corrected
   `map -> base_link` pose, and goal checks use `map -> base_link` exactly as the
   earlier pilot did.
4. **`tf` rotations come back as lists**, not quaternions, in this ROS version.
   Evidence: `AttributeError: 'list' object has no attribute 'w'` in
   `driver.log`.  Fixed with `yaw_from_tf_rotation`.
5. **Covariance parsing**: `PoseGraph.covariance` is a `string[]` of six
   space-separated upper-triangle terms; the first draft stored the string's
   characters.  Evidence: `graph_before_return.json` contained
   `['0', '.', '0', ...]`.  Fixed with `parse_covariance` (and the analysis
   refuses any edge whose covariance is not six numeric terms).
6. **Anchor identity**: with the anchor defined as "graph state closest to the
   commanded waypoint", the closest state was a state created *while the probe
   was already turning away* from the place (`theta = -0.699` while the executed
   arrival heading was `-1.64`), so the return goal asked for a heading the
   history leg never held (`GT heading error 0.854 rad`).
   Fixed: the target is now frozen from the **executed arrival pose**
   (`map -> base_link` recorded by `move_to`), and the anchor is the state with
   the smallest position distance plus `0.5 m/rad` times the wrapped heading
   difference, with a frozen heading gate of `0.6 rad`
   (`TARGET_ANCHOR_HEADING_TOLERANCE_RAD`).  Outcome-blind: it reads only the
   history leg and the pre-return snapshot.
7. **Static arm hold**: `S0` took its `G_action_done` snapshot immediately; the
   handoff asks for an explicitly recorded end of the initial hold.  Fixed: every
   arm now waits the same `action_finish_hold_s` before that snapshot.

## Smoke validation (4 actions at one place)

Place `place_B`, repeat 1, arms `S0`, `S1`, `L+`, `L-`; results in `smoke/`.

| check (handoff section 5) | result |
| --- | --- |
| geometric chain continuous (no stitching, no re-parameterisation) | see `analysis/per_episode_metrics.csv` (`*_path_length_m`, `odom_gt_residual_*`) |
| no phase lost: history / return / action / tail all present | `episode_result.json:phase_scan_marks` + `phase_boundaries` |
| action directions, rotation and return to `theta0` | `episode_result.json:action_moves`, `action_max_abs_yaw_from_start_rad` |
| snapshots paired with ground truth and scan indices | `phase_boundaries`, `gt_stream.jsonl` |
| metrics computable | `analysis/summary.json` (including `measurement_sensitivity`) |

## Observations that need attention at the end of the round

* `verify.py` flags `place_D: L+ and L- rotations differ by more than 0.6 rad`.
  In the available episodes the **executed** rotation at place_D is
  `L+ 6.83 / 5.59 rad` versus `L- 3.44 rad`, i.e. the commanded dose is identical
  but the executed one is not.  This is a backend/navigation effect (the probe
  rotates near the wall corner and overshoots), not a protocol change; doc 77
  reports both the planned and the executed geometry.
* `tail_gain` is exactly zero for every arm: the static tail triggers no mapper
  keyframe (statistics in `analysis/per_episode_metrics.csv`,
  `action_keyscans_created`).

## Deviations and open items

* The limited repeatability check is executed as a **re-execution** of four
  fixed configurations (L+ and L- at the first repeat of the first two places,
  twice each = 8 backend runs, within the handoff's 12-run budget) instead of
  offline replay of the recorded mapper input.  Reason: this round's chain is
  native (no recorded mapper input stream exists to replay, by design — §4.1
  option b), and a replay publisher for the new chain would be a new
  instrumented backend path.  The re-execution measures exactly what the check
  is for: whether between-arm differences exceed run-to-run variation.
