# REVIEW_PACKET — p1 continuous revisit action validation (2026-10-10)

Purpose: let a second reviewer check this round's claims without re-running the
experiment, and re-derive every number from the recordings.

## 1. What is claimed (status: PAUSED at 40/48 episodes)

Doc 77 section 6–7 holds the current quantitative claims, all marked as the pause
point (2026-10-10):

1. The return leg itself adds target information: mean `return_gain` +0.056 (S0),
   +0.082 (S1), +0.121 (L+), +0.088 (L-) nats.
2. The extra rotation also adds information, but the largest rotation is **not**
   dominant: mean `action_gain` +0.097 (S1), +0.120 (L-), +0.069 (L+),
   exactly 0.000 for S0 (10/10 episodes).
3. The two directions differ: paired `L+ - L-` mean -0.051 nats (3/9 groups
   positive) and `L+ - S1` mean -0.035 (3/9).
4. `S1` is not mainly limited by the mapper's 0.52 rad keyframe gate: it creates
   1.2 states per action on average (L+: 5.9, L-: 5.7) yet reaches the same
   information order as `L+`/`L-`.
5. The information gains are **not** accompanied by measurable real map-error
   changes at the target states (+0.0001 m mean; Pearson r = +0.18 for the action
   stage).
6. Not yet claimable: whether any of the paired differences exceed run-to-run
   variation (the repeatability suite has not run), and the final numbers for the
   remaining 8 episodes.

Status bookkeeping: `suite_state.json` has 40 SUCCEEDED, 1 FAILED
(`0022_place_B_r3_L+`, navigator ABORT on `history_02`), 1 INTERRUPTED
(`0042_place_D_r2_L-`, graceful pause), 6 PENDING.  `verification.json` lists the
per-episode integrity checks and one protocol flag (`place_D` executed L+/L-
rotations differ by more than 0.6 rad — an execution-level asymmetry, reported in
doc 77 section 6.4).

## 2. Where to look first

| question | artefact |
| --- | --- |
| Does the continuous chain hold (no stitching, no displaced suffix)? | `analysis/figures/fig1_continuous_trajectory.png`, `analysis/per_episode_metrics.csv` (`{phase}_path_length_m`, `odom_gt_residual_*`) |
| Does the return leg already deliver the information? | `analysis/stage_gains.csv` (`return_gain` vs `action_gain`), `fig2_information_decomposition.png` |
| Is the large rotation still dominant, and does direction matter? | `analysis/within_place_action_comparison.csv`, `summary.json:difference_summary` (`L+_L-`, `L+_S1`), `fig4_direction_and_contrast.png` |
| Is the metric able to see a constraint on the target at all? | `summary.json:measurement_sensitivity` (synthetic edge response ≫ 0) |
| Are the group/arm pre-states comparable? | `analysis/pre_state_differences.csv` |
| What constraints were actually created, and where? | `analysis/constraint_provenance.csv`, `fig5_historical_constraints.png` |
| Does more graph information mean less real map error? | `fig6_information_vs_error.png`, `summary.json:errors_vs_information` |
| Is the difference bigger than run-to-run variation? | `repeatability/` + doc 77 section 8 |
| Is anything hidden by a failed run? | `suite_state.json` (all attempts and reasons), `episodes/*/attempt_*/run_state.json`, `analysis/analysis_failures.csv` |

## 3. Frozen protocol (check that nothing moved after the fact)

* `experiment_plan.json` — places, route, actions, doses, tolerances, arm order.
* `tools/realizability_pilot/continuous_revisit/protocol.py` — the same values in code.
* Places were selected from static floor-plan geometry only (nearest-obstacle
  distance and occupied 30° sectors); the selection is described in doc 77 §2.1.
* Per-episode target identity is frozen from the history leg's **executed
  arrival pose** (`episodes/*/attempt_*/frozen_target.json`), before the action.
* No matcher threshold, no added noise, no selector training, no backend change:
  `episodes/*/attempt_*/mapper_params.yaml` and `manifest.json` record the
  launch parameters actually used.

## 4. Boundary guarantee (the honest limitation)

The mapper exposes no per-scan processing acknowledgement. Each snapshot records
its scan index, node/edge counts and a quiescence window; the analysis reports
node/edge counts at every boundary in `per_episode_metrics.csv`. Anyone wanting a
stronger guarantee can compare `graph_*.json` with the mapper's
`pose_graph_dump.json` in the same directory (written at shutdown).

## 5. Analysis choices that a reviewer should challenge

1. **J_T** is the anchored, 5-target-state log-determinant score of the earlier
   rounds. `summary.json:measurement_sensitivity` shows it responds to a
   constraint attached to the target states; the sensitivity magnitude varies by
   episode (0.018–0.067 nats in the smoke), so cross-episode comparisons of
   *absolute* J_T are not meaningful — only within-episode deltas.
2. `return_gain`, `action_gain`, `tail_gain` are defined on the four snapshots;
   the action-phase window for the heading/keyframe statistics is exactly the 347
   retained valid scans.
3. The executed actions overshoot the commanded deflection by roughly 0.3 rad
   (navigator rotation overshoot); the measured values are reported next to the
   planned ones (`action_measured_rotation_rad`, `max_heading_deflection_rad`).
4. `new_heading_fraction` compares the action-phase observation headings with the
   frozen target states' own headings (15° margin). It is a geometric description,
   not a success criterion.

## 6. Reproduce everything offline

```bash
cd /home/wcqw/ac-slam

# resume the paused matrix (retries the interrupted, pending and failed episodes)
setsid nohup /usr/bin/python3 tools/realizability_pilot/continuous_revisit/runner.py resume \
  --suite-dir results/realizability_pilot/p1_continuous_revisit_actions_20261010 \
  >> /tmp/cr_suite.log 2>&1 < /dev/null

# limited repeatability (4 fixed configurations x 2 extra executions)
/usr/bin/python3 tools/realizability_pilot/continuous_revisit/runner.py plan \
  --repeatability "place_A:1:L+,place_A:1:L-,place_B:1:L+,place_B:1:L-" --replays 2 \
  --suite-dir results/realizability_pilot/p1_continuous_revisit_actions_20261010/repeatability
setsid nohup /usr/bin/python3 tools/realizability_pilot/continuous_revisit/runner.py run \
  --suite-dir results/realizability_pilot/p1_continuous_revisit_actions_20261010/repeatability \
  >> /tmp/cr_repeat.log 2>&1 < /dev/null

# doc-ready tables (optionally with the repeatability spread)
PYTHONPATH=/home/wcqw/ac-slam/catkin_ws/python /usr/bin/python3 \
  tools/realizability_pilot/continuous_revisit/report_tables.py \
  results/realizability_pilot/p1_continuous_revisit_actions_20261010 \
  --repeatability-dir results/realizability_pilot/p1_continuous_revisit_actions_20261010/repeatability

# integrity + protocol verification
PYTHONPATH=/home/wcqw/ac-slam/catkin_ws/python /usr/bin/python3 \
  tools/realizability_pilot/continuous_revisit/verify.py \
  results/realizability_pilot/p1_continuous_revisit_actions_20261010
PYTHONPATH=/home/wcqw/ac-slam/catkin_ws/python /usr/bin/python3 \
  tools/realizability_pilot/continuous_revisit/analysis.py \
  results/realizability_pilot/p1_continuous_revisit_actions_20261010
PYTHONPATH=/home/wcqw/ac-slam/catkin_ws/python /usr/bin/python3 \
  tools/realizability_pilot/continuous_revisit/figures.py \
  results/realizability_pilot/p1_continuous_revisit_actions_20261010
/usr/bin/python3 tools/realizability_pilot/continuous_revisit/test_continuous_revisit.py
```
