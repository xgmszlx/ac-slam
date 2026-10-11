# REVIEW_PACKET — p1 continuous revisit action validation (2026-10-10)

Purpose: let a second reviewer check this round's claims without re-running the
experiment, and re-derive every number from the recordings.

## 1. What is claimed (final: 48/48 main + 8/8 repeatability)

Doc 77 sections 0 and 6–9 hold the quantitative claims; each is backed by
`analysis/per_episode_metrics.csv`, `analysis/summary.json` or
`analysis/figures/*`.

1. The measurement chain is trustworthy: the static arm's action-stage gain is
   exactly 0.00000 nats in 12/12 episodes, and a synthetic constraint on the
   target states moves J_T by +0.01934 nats on average (48/48 positive).
2. The return leg itself adds target information: mean `return_gain` +0.10082
   (S0), +0.11725 (S1), +0.11894 (L+), +0.10608 (L-) nats.
3. The extra rotation adds a comparable amount, but the largest rotation is not
   dominant: mean `action_gain` **+0.08144 (S1)**, **+0.06485 (L+)**,
   **+0.11562 (L-)**, **0.00000 (S0)**; positive in 11/12, 7/12, 12/12, 0/12.
4. Direction matters only in sign, not in size: paired `L+ - L-` mean -0.05077
   nats (4/12 groups positive), `L+ - S1` mean -0.01659 (5/12).
5. **Neither difference exceeds the same-configuration re-run spread**:
   `s_rep = 0.10458` nats (pooled within-configuration sd of `action_gain`, 3
   executions per configuration; e.g. place_B `L+` returned 0.000 / 0.277 / 0.119
   under the identical command).  By the pre-registered rule in doc 77 section 1
   the ordering differences are therefore not usable as a selection signal.
6. `S1` is not limited by the mapper's 0.52 rad keyframe gate: it creates
   1.33 states per action (L+: 5.92, L-: 5.50) yet still gains +0.08144 nats.
7. Graph information does not translate into measurable map-error change at the
   target states: +0.00010 m mean change, Pearson r = +0.14 with `action_gain`.
8. Recommendation: do not build an action selector from this evidence.  First
   reduce the run-to-run variance (paired initialisation or replayed backend), or
   reframe the question as which pre-action geometry predicts a new target
   constraint.

Data-quality flags (kept, not hidden): `0020_place_B_r2_L-` ended 0.378 rad from
theta0 (gate 0.35); `place_D` executed L+/L- rotations differ by more than
0.6 rad.  `verification.json` holds all per-episode checks.

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
