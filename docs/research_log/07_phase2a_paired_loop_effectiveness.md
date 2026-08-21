# Phase 2A: map3 paired loop-effectiveness audit

Date: 2026-08-21

## Scope and frozen baseline

This phase observes the public-code baseline without changing its planning objective, skip logic, loop replanning logic, prior graph, or map. The only baseline-source changes are:

- `2cfe168 experiment: control and record Concorde TSP seed`
- `211642d observe: log active-loop execution boundaries`

The runtime-compatibility baseline is `5a11667`. All ten measured runs use source commit `211642d66c587419253cf90f0e5ecc7da520f46e`, map3, start pose `(-28, -28, 0)`, no prior noise, and alternating pair order. The failed runner startup attempt preceding these runs is preserved separately at `results/phase2/map3_pairs_runner_failure_20260821T1126`; it failed before ROS master/any experimental run because of a runner API typo and is not included in the five pairs.

## Reproducibility and initial TSP control

Concorde is invoked with `-s <seed>`. Seeds 21001--21005 are used once per pair. Prior-TSP and SLAM-aware both pass a pre-exploration gate against the pair reference record. In 5/5 pairs the following are exactly identical within the pair: solver, seed, `initial_tsp_path`, `full_tsp_path`, predicted lengths, and the complete TSP-record SHA-256. Pair execution order alternates to expose monotone order effects.

The exact hashes and validation booleans are in `results/phase2/map3_pairs/aggregate/reproducibility_check.json`. All 10/10 action runs returned success, and no run was silently retried. A 2700 s hard timeout and 30 s node/RSS monitor were active; no run timed out and maximum process-tree RSS was 1.47--1.52 GB.

## Pinned SLAM evaluation

- evo: 1.31.1, installed in the isolated target `evaluation/evo-1.31.1-target/site-packages`.
- Input: TUM trajectories; GT and Karto timestamps are associated by nearest timestamp with maximum difference 0.05 s and offset 0.
- Geometry: both trajectories are already expressed in the same map frame. Evaluation projects to the XY plane and performs no post-hoc alignment and no scale correction.
- APE: `trans_part`, RMSE, metres.
- Translational RPE: 1 m reference-distance pairs, all pairs, `trans_part`, RMSE, metres.
- Rotational RPE: the same 1 m reference-distance pairs, `angle_deg`, RMSE, degrees.

Canonical commands (absolute run paths omitted here) are:

```text
env PYTHONPATH=/home/wcqw/ac-slam/evaluation/evo-1.31.1-target/site-packages /usr/bin/python3 -m evo.main_ape tum GT SLAM -r trans_part --project_to_plane xy --t_max_diff 0.05 --t_offset 0 --no_warnings --save_results OUT.zip
env PYTHONPATH=/home/wcqw/ac-slam/evaluation/evo-1.31.1-target/site-packages /usr/bin/python3 -m evo.main_rpe tum GT SLAM -r trans_part --project_to_plane xy --t_max_diff 0.05 --t_offset 0 --no_warnings -d 1 -u m --all_pairs --pairs_from_reference --save_results OUT.zip
env PYTHONPATH=/home/wcqw/ac-slam/evaluation/evo-1.31.1-target/site-packages /usr/bin/python3 -m evo.main_rpe tum GT SLAM -r angle_deg --project_to_plane xy --t_max_diff 0.05 --t_offset 0 --no_warnings -d 1 -u m --all_pairs --pairs_from_reference --save_results OUT.zip
```

Every run contains its exact absolute commands, stdout/stderr, and result archives under `evo/`. Per-loop before/after values are cumulative-prefix metrics ending at loop start/end. They are descriptive, not causal estimates of the loop's isolated effect.

## Paired results

`Delta` is SLAM-aware minus Prior-TSP. `P/E/S` means planned/executed/successful SLAM loops. Edit is the normalized high-level vertex-sequence Levenshtein distance.

| Pair | Seed | TSP time/distance | SLAM time/distance | Delta time/distance | APE T/S (m) | RPE trans T/S (m) | RPE rot T/S (deg) | Loops P/E/S | Edit T/S |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 21001 | 808.6 s / 353.5 m | 1378.7 s / 524.4 m | +570.1 s / +170.8 m | 0.549 / 0.965 | 0.039 / 0.041 | 0.246 / 0.433 | 4/4/0 | 0.194 / 0.244 |
| 2 | 21002 | 889.8 s / 384.7 m | 1170.6 s / 453.6 m | +280.8 s / +68.9 m | 0.810 / 0.542 | 0.025 / 0.038 | 0.128 / 0.210 | 3/3/0 | 0.167 / 0.098 |
| 3 | 21003 | 850.6 s / 354.0 m | 1394.9 s / 534.9 m | +544.3 s / +180.9 m | 0.169 / 1.477 | 0.031 / 0.040 | 0.171 / 0.304 | 4/4/0 | 0.194 / 0.116 |
| 4 | 21004 | 833.5 s / 346.1 m | 1434.8 s / 549.9 m | +601.3 s / +203.8 m | 0.331 / 0.234 | 0.030 / 0.048 | 0.160 / 0.280 | 5/5/0 | 0.167 / 0.160 |
| 5 | 21005 | 785.8 s / 348.8 m | 1379.2 s / 537.0 m | +593.4 s / +188.2 m | 0.647 / 0.269 | 0.029 / 0.045 | 0.163 / 0.233 | 5/5/0 | 0.194 / 0.184 |

Mean paired increases are 518.0 s, 162.5 m, and 92.9 m of planned prior-graph path weight. Relative to each Prior-TSP run, time increases by 31.6--75.5% (mean 62.7%) and actual GT distance by 17.9--58.9% (mean 46.0%). Whole-run APE is lower in 3/5 pairs and higher in 2/5, but translational and rotational RPE are higher in all 5/5 SLAM-aware runs. These are five raw paired observations; no significance test is claimed.

## Active-loop effectiveness

Definitions are frozen as follows:

1. Planned: the high-level planner marks/inserts the loop vertex.
2. Executed: all emitted loop waypoints are reported reached.
3. Successful SLAM loop: an OpenKarto accepted-loop event (`Add one Loop closure`) occurs during execution and the before/after pose graph contains a new edge whose scan-index gap exceeds the default `ScanBufferSize=70`.

The `/Mapper/closure_edges` marker count is auxiliary only. `MultiMapper.cpp` builds this marker from edges not matching its sequential-edge traversal; it is not an accepted-loop callback. Consequently a positive marker delta is not treated as successful closure evidence.

`dNodes/dEdges` is the direct pose-graph snapshot delta. `Accepted/new>70` reports accepted-loop log events and newly added edges beyond the scan buffer. Metric deltas are cumulative-after minus cumulative-before.

| Pair-loop | Vertex | Time (s) | Distance (m) | Waypoints | Service | dNodes/dEdges | Aux marker | Accepted/new>70 | dAPE (m) | dRPE-t (m) | dRPE-r (deg) | Success |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---|
| 1-1 | 15 | 50.1 | 16.6 | 6/6 | OK | 11/13 | 12 | 0/0 | +0.003 | -0.000 | -0.026 | no |
| 1-2 | 11 | 89.1 | 28.0 | 5/5 | OK | 16/16 | 19 | 0/0 | +0.007 | +0.001 | +0.004 | no |
| 1-3 | 8 | 44.4 | 20.5 | 7/7 | OK | 6/6 | 21 | 0/0 | +0.179 | -0.001 | -0.010 | no |
| 1-4 | 26 | 66.1 | 18.4 | 7/7 | OK | 6/6 | 3 | 0/0 | +0.022 | -0.000 | -0.007 | no |
| 2-1 | 8 | 35.2 | 14.4 | 7/7 | OK | 36/72 | 36 | 0/0 | +0.170 | -0.001 | -0.005 | no |
| 2-2 | 38 | 100.9 | 23.4 | 7/7 | OK | 21/21 | 10 | 0/0 | -0.009 | -0.001 | -0.005 | no |
| 2-3 | 16 | 63.9 | 28.0 | 7/7 | OK | 25/29 | 4 | 0/0 | -0.008 | +0.000 | +0.000 | no |
| 3-1 | 15 | 80.9 | 22.7 | 6/6 | OK | 11/11 | 8 | 0/0 | +0.109 | -0.000 | -0.001 | no |
| 3-2 | 37 | 158.0 | 37.2 | 5/5 | OK | 56/76 | 19 | 0/0 | -0.010 | +0.002 | -0.006 | no |
| 3-3 | 8 | 24.8 | 8.6 | 7/7 | OK | 0/0 | 41 | 0/0 | -0.004 | -0.000 | -0.002 | no |
| 3-4 | 21 | 48.1 | 22.0 | 7/7 | OK | 7/7 | 12 | 0/0 | -0.000 | +0.004 | +0.012 | no |
| 4-1 | 15 | 51.9 | 15.6 | 5/5 | OK | 10/13 | 17 | 0/0 | +0.004 | +0.002 | +0.007 | no |
| 4-2 | 26 | 65.9 | 23.3 | 4/4 | OK | 24/24 | 15 | 0/0 | -0.002 | +0.000 | +0.002 | no |
| 4-3 | 35 | 80.2 | 19.8 | 7/7 | OK | 10/12 | 34 | 0/0 | +0.017 | +0.020 | +0.146 | no |
| 4-4 | 22 | 61.0 | 17.4 | 5/5 | OK | 0/0 | 26 | 0/0 | +0.019 | +0.000 | +0.017 | no |
| 4-5 | 8 | 61.6 | 31.0 | 7/7 | OK | 22/25 | 37 | 0/0 | +0.027 | -0.001 | +0.001 | no |
| 5-1 | 15 | 46.1 | 15.7 | 5/5 | OK | 26/33 | 7 | 0/0 | +0.014 | +0.001 | +0.021 | no |
| 5-2 | 26 | 70.2 | 22.9 | 4/4 | OK | 20/21 | 33 | 0/0 | +0.005 | -0.000 | -0.007 | no |
| 5-3 | 35 | 73.9 | 20.4 | 7/7 | OK | 8/9 | 23 | 0/0 | +0.024 | +0.012 | +0.040 | no |
| 5-4 | 22 | 59.1 | 19.3 | 6/6 | OK | 7/7 | 11 | 0/0 | -0.000 | +0.000 | +0.007 | no |
| 5-5 | 8 | 79.2 | 35.8 | 7/7 | OK | 30/34 | 62 | 0/0 | +0.020 | -0.001 | -0.001 | no |

Total loop-execution intervals contain 1410.6 s and 461.0 m of motion. These are measured action-interval costs, not counterfactual marginal costs. Reliable-loop service succeeds in 21/21 cases, all waypoints are reached, and no fallback occurs. OpenKarto reports zero accepted loop events in all execution intervals and in all complete run logs; no new edge exceeds the 70-scan buffer. Therefore counts are 21 planned / 21 executed / 0 successful SLAM loops.

Cumulative APE decreases over 7/21 loop intervals and increases over 14/21; translational RPE decreases over 10/21 and increases over 11/21; rotational RPE decreases over 10/21 and increases over 11/21. Because prefix sample populations change and no accepted constraint occurs, these deltas must not be interpreted as loop-closure gains.

## Planned-versus-actual execution

Normalized edit distance is Levenshtein distance divided by the longer sequence; zero means an exact sequence match. LCS recall is LCS length divided by planned sequence length. No-frontier and local-replan counts are callback/event counts, not distinct vertices or unique path changes.

| Pair | Method | Planned vertices | Actual vertices | Planned graph length (m) | Actual GT length (m) | Norm. edit | LCS recall | No-frontier events | Repeated skips | Goal skips | Local replans |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | TSP | 36 | 31 | 415.2 | 353.5 | 0.194 | 0.806 | 26 | 5 | 5 | 143 |
| 1 | SLAM-aware | 43 | 45 | 503.6 | 524.4 | 0.244 | 0.860 | 26 | 8 | 5 | 191 |
| 2 | TSP | 36 | 32 | 415.2 | 384.7 | 0.167 | 0.833 | 26 | 6 | 4 | 157 |
| 2 | SLAM-aware | 41 | 40 | 478.9 | 453.6 | 0.098 | 0.902 | 25 | 8 | 5 | 164 |
| 3 | TSP | 36 | 31 | 415.2 | 354.0 | 0.194 | 0.806 | 25 | 5 | 6 | 150 |
| 3 | SLAM-aware | 43 | 41 | 503.6 | 534.9 | 0.116 | 0.884 | 25 | 9 | 5 | 180 |
| 4 | TSP | 36 | 31 | 415.2 | 346.1 | 0.167 | 0.833 | 24 | 4 | 8 | 148 |
| 4 | SLAM-aware | 45 | 50 | 527.2 | 549.9 | 0.160 | 0.956 | 28 | 7 | 5 | 183 |
| 5 | TSP | 36 | 34 | 415.2 | 348.8 | 0.194 | 0.861 | 25 | 5 | 6 | 136 |
| 5 | SLAM-aware | 45 | 49 | 527.2 | 537.0 | 0.184 | 0.933 | 24 | 9 | 7 | 173 |

SLAM-aware normalized mismatch is 0.098--0.244 in all five runs (mean 0.160). Repeated-visit skips are 7--9 per SLAM-aware run versus 4--6 for TSP. Logs directly show the executor skipping repeated vertices immediately after completed loops and selecting later goals from the existing high-level path. The mismatch is real and repeatable, although this five-pair descriptive phase does not assign an inferential p-value and does not isolate skip logic from frontier and local-replanning effects.

## H1--H4 decisions

- **H1 Supported on map3.** All 21 planned loops are executed, but 0/21 become a confirmed Karto loop constraint. Positive closure-marker deltas are not accepted-loop evidence.
- **H2 Supported on map3.** At least some, and in this sample all, active-loop executions incur path/time cost without a confirmed SLAM constraint. Paired physical distance and time increase in 5/5 pairs; whole-run translational and rotational RPE worsen in 5/5. APE is mixed, so the result is not a claim that every SLAM metric always worsens.
- **H3 Supported as a behavioral/effect-size claim.** All 5/5 SLAM-aware runs have nonzero sequence mismatch, 7--9 repeated skips, and 5--7 goal skips. The optimizer path is therefore not the exact executed high-level sequence. Statistical significance and the isolated causal contribution of each skip type remain untested.
- **H4 Supported for the structural/behavioral mechanism; performance impact Inconclusive.** The loop-index replanning branch in `path_planner.py` is an explicit `pass`; each SLAM-aware run publishes one initial SLAM path and no new global SLAM-aware path after any of 21 loops. Runtime continues through the existing path. Because no loop produced a confirmed new SLAM constraint and no counterfactual replanning variant is allowed in Phase 2A, this phase cannot estimate the performance loss specifically attributable to stale post-loop optimization.

## Observed runtime anomalies and evidence locations

All actions succeed, but every one of the ten launch logs prints `double free or corruption (fasttop)` during shutdown after exploration completion. One run also emits `Local path replan get wrong start and end vertex`; repeated TF-data warnings occur. These do not invalidate the completed action data, but they are retained rather than suppressed.

Primary artifacts:

- `results/phase2/map3_pairs/aggregate/paired_results.csv`
- `results/phase2/map3_pairs/aggregate/per_loop_effectiveness.csv`
- `results/phase2/map3_pairs/aggregate/reproducibility_check.json`
- `results/phase2/map3_pairs/aggregate/aggregate_summary.json`
- `results/phase2/map3_pairs/aggregate/paired_raw_points.png`
- `results/phase2/map3_pairs/aggregate/paired_differences.png`
- Per-run raw logs, trajectories, maps, events, manifests, full loop paths/actual trajectories, pose-graph updates/snapshots, and evo archives under `results/phase2/map3_pairs/pair_*/{prior_tsp,slam_aware}/`.
