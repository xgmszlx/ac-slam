# p1 continuous revisit action validation (2026-10-10)

Round: **连续几何一致采集与局部动作辨别实验** (continuous, geometry-consistent
capture with local action discrimination).

This root contains the whole round:

| path | content |
| --- | --- |
| `experiment_plan.json` | frozen places, route, actions, repeats, order, tolerances |
| `suite_state.json` | suite ledger: one record per planned episode, with attempts |
| `episodes/<episode_id>/attempt_NN/` | one physical run: raw streams, graph snapshots, result |
| `analysis/` | per-episode metrics, stage gains, comparisons, summary JSON |
| `analysis/figures/` | figures (`fig*.png` preview + `fig*.svg` editable) |
| `smoke/` | the four-arm smoke validation (not part of the main matrix) |
| `repeatability/` | the limited repeatability re-executions (4 fixed configs x 2, all succeeded) |
| `verification.json` | per-episode integrity / protocol checks (47/48 clean, 1 flagged record) |
| `STATUS.md` | running status and deviations |
| `REVIEW_PACKET.md` | what to review, where to look, and what is claimed |

## One main run command

```bash
cd /home/wcqw/ac-slam

# 1. plan the 48-episode matrix (writes experiment_plan.json + suite_state.json)
/usr/bin/python3 tools/realizability_pilot/continuous_revisit/runner.py plan \
  --suite-dir results/realizability_pilot/p1_continuous_revisit_actions_20261010

# 2. execute it serially, resumable at any time (safe to re-run the same line)
setsid nohup /usr/bin/python3 tools/realizability_pilot/continuous_revisit/runner.py run \
  --suite-dir results/realizability_pilot/p1_continuous_revisit_actions_20261010 \
  > /tmp/cr_suite.log 2>&1 < /dev/null
```

## Resume after an interruption

```bash
# failed episodes are retried in a *new* attempt directory; nothing is overwritten
setsid nohup /usr/bin/python3 tools/realizability_pilot/continuous_revisit/runner.py resume \
  --suite-dir results/realizability_pilot/p1_continuous_revisit_actions_20261010 \
  >> /tmp/cr_suite.log 2>&1 < /dev/null

# progress snapshot
/usr/bin/python3 tools/realizability_pilot/continuous_revisit/runner.py status \
  --suite-dir results/realizability_pilot/p1_continuous_revisit_actions_20261010
```

## Completion count (final)

The round finished on 2026-10-11 with **48/48 main episodes** and **8/8
repeatability executions** succeeded (0 failed).  One main episode needed its
single allowed retry after a navigator ABORT, and one repeatability execution was
resumed after the user-requested pause; both first attempts are kept in the
ledger.

```bash

```bash
/usr/bin/python3 -c "
import json
state = json.load(open('results/realizability_pilot/p1_continuous_revisit_actions_20261010/suite_state.json'))
counts = {}
for episode in state['episodes']:
    counts[episode['status']] = counts.get(episode['status'], 0) + 1
print(state['status'], counts)"
```

## Offline re-analysis (no ROS, reproducible from the recordings)

```bash
cd /home/wcqw/ac-slam
PYTHONPATH=/home/wcqw/ac-slam/catkin_ws/python /usr/bin/python3 \
  tools/realizability_pilot/continuous_revisit/analysis.py \
  results/realizability_pilot/p1_continuous_revisit_actions_20261010

PYTHONPATH=/home/wcqw/ac-slam/catkin_ws/python /usr/bin/python3 \
  tools/realizability_pilot/continuous_revisit/figures.py \
  results/realizability_pilot/p1_continuous_revisit_actions_20261010

/usr/bin/python3 tools/realizability_pilot/continuous_revisit/test_continuous_revisit.py
```

Everything in `analysis/` is derived from `episodes/*/attempt_*/`; deleting
`analysis/` and re-running the two commands reproduces it byte-for-byte except
for the figure timestamps.

## What one episode directory contains

| file | content |
| --- | --- |
| `episode_spec.json` | the frozen episode spec (place, action, seeds, tolerances) |
| `scan_stream.jsonl` | every native `/base_scan` message with its wire ranges, the laser and base pose in the correction-free `odom` chain, and the SLAM pose |
| `gt_stream.jsonl` | `/base_pose_ground_truth` samples |
| `keyscan_stream.jsonl` | `/others` accepted-scan poses (state-time correspondence) |
| `loop_events.jsonl` | `/Mapper/loop_closed` events |
| `graph_before_return.json`, `graph_arrival.json`, `graph_action_done.json`, `graph_final.json` | full pose-graph snapshots (nodes, edges, covariances) with the scan index and the quiescence record of their boundary |
| `frozen_target.json` | anchor state, target states and the frozen identity gate result |
| `episode_result.json` | driver result: per-move errors, phase scan marks, action cost, boundaries |
| `karto_edge_provenance.jsonl` | mapper-side edge provenance (observation-only) |
| `monitor.csv`, `driver.log`, `roslaunch.log`, `map_saver.log`, `final_map.*` | process-level evidence |

## Boundary guarantee (recorded, not assumed)

The mapper has no per-scan processing acknowledgement.  Each snapshot is
therefore taken **after** the phase's last scan plus at least 0.5 s in which no
new full-graph message, no new accepted-scan publication and no new keyscan
event appeared (`quiescence_s`), and every snapshot records the scan index,
node/edge counts and that quiescence record.  The analysis additionally checks
node/edge counts per phase and reports them in `analysis/per_episode_metrics.csv`.

## Frozen, non-negotiable choices

* One Stage + Karto run per episode; **no suffix stitching** and no reuse of the
  earlier stitching module.
* Four actions with the handoff's doses: `S0` static, `S1` `theta0 -> theta0 +
  1.087946562824985/2 -> theta0`, `L+` `theta0 -> theta0 + pi/2 -> theta0`,
  `L-` `theta0 -> theta0 - pi/2 -> theta0`.
* 4 places x 3 repeats x 4 actions = 48 episodes, arm order rotated per group.
* No matcher threshold changes, no added noise, no favourable place selection,
  no selector training, no backend migration.
