# Phase 2B: Karto loop-closure mechanism and failure diagnosis

Date: 2026-08-21

## Scope

[Config] Phase 2B preserves map3, Pioneer 3-AT, the existing Mapper launch, `mapper.yaml`, scan source, planner code, reliable-loop service, prior graph, and all Karto matching thresholds. The only runtime intervention in the positive control is an independent `/MoveTo` action client after normal Nearest-Frontier exploration.

[Code] Baseline source commit remains `211642d66c587419253cf90f0e5ecc7da520f46e`. Phase 2B scripts live outside the baseline repository.

## Actual Karto loop configuration

The explicit runtime parameter dump is saved for every positive-control trial as `mapper_params.yaml`.

| Parameter | Effective value | Evidence |
|---|---:|---|
| `LoopSearchSpaceDimension` | 5.0 m | [Config] `param/mapper.yaml` and `/Mapper` runtime dump |
| `LoopSearchSpaceResolution` | 0.05 m | [Code] absent from ROS params; OpenKarto default at `OpenMapper.cpp:2245` |
| `LoopSearchSpaceSmearDeviation` | 0.03 m | [Code] absent from ROS params; OpenKarto default at `OpenMapper.cpp:2246` |
| `LoopSearchMaximumDistance` | 4.0 m | [Config] `param/mapper.yaml` and `/Mapper` runtime dump |
| `LoopMatchMinimumChainSize` | 4 scans | [Config] `param/mapper.yaml` and `/Mapper` runtime dump |
| `LoopMatchMaximumVarianceCoarse` | 0.16 m² per x/y diagonal test | [Config] `param/mapper.yaml`; [Code] tests `cov(0,0)` and `cov(1,1)` |
| `LoopMatchMinimumResponseCoarse` | 0.6 | [Config] `param/mapper.yaml` and `/Mapper` runtime dump |
| `LoopMatchMinimumResponseFine` | 0.7 | [Config] `param/mapper.yaml` and `/Mapper` runtime dump |

[Config] Key-scan creation also uses `MinimumTravelDistance=1.0 m` or `MinimumTravelHeading=0.52 rad`. A raw laser message that does not satisfy either condition is not inserted as a new Karto scan and does not enter `TryCloseLoop`.

[Code] Parameters absent from `mapper.yaml` are not injected by `MultiMapper.cpp`; the instantiated `OpenMapper` therefore retains the constructor defaults shown above. The runtime `/Mapper` parameter dump confirms that resolution and smear are absent rather than silently overridden.

## Matching pipeline

### 1. Candidate formation

[Code] For every accepted key scan, `OpenMapper::Process` adds ordinary graph edges and then calls `MapperGraph::TryCloseLoop` (`OpenMapper.cpp:2393-2408`).

[Code] `FindPossibleLoopClosure` first performs a graph BFS around the current scan. Scans graph-linked to the current scan and spatially within `LoopSearchMaximumDistance=4 m` form `nearLinkedScans` and are explicitly excluded from loop-candidate chains (`OpenMapper.cpp:2096-2144`).

[Code] It then traverses historical scans in scan order. A scan can enter a candidate chain only when its corrected reference pose is within 4 m and it is not in `nearLinkedScans`. The intended minimum chain length is 4.

[Inference] Merely reaching the coordinates returned by `reliable_loop_service` is insufficient. If those scans are already connected to the current scan through the local graph neighborhood, Karto deliberately excludes them from loop matching even when spatial overlap is high.

[Unknown] Phase 2A did not save scan barycenters or the exact `nearLinkedScans` set at every key-scan insertion. The offline candidate-chain reconstruction uses saved corrected scan poses, graph edges, and publication timestamps and is therefore an evidence-backed approximation, not a byte-identical replay of Karto internals.

### 2. Coarse matching

[Code] The loop scan matcher is constructed with a 5.0 m correlation search dimension, 0.05 m resolution, 0.03 m smear deviation, and the current 25 m range threshold (`OpenMapper.cpp:1431-1435`).

[Code] A normal coarse pass requires:

```text
coarse_response > 0.6
covariance(0,0) < 0.16
covariance(1,1) < 0.16
```

[Code] A second branch accepts `coarse_response > 0.54` only when both x/y variances are below `0.0016` (`0.01 * 0.16`).

[Inference] Search-space dimension controls the translational correlation window, resolution controls its grid discretization, and smear changes the spatial smoothing applied to scan hits. Maximum variance and coarse response jointly reject ambiguous or weak alignments.

[Unknown] ROS logging was at INFO in all Phase 2A runs. The coarse response and covariance are emitted through Karto events/DEBUG paths but were not present in the saved logs, so they cannot be reconstructed reliably for the 21 historical active loops.

### 3. Fine matching

[Code] After coarse acceptance, Karto temporarily applies the coarse best pose and runs the sequential matcher against the candidate chain. `fine_response < 0.7` is rejected and the scan pose is reverted (`OpenMapper.cpp:1596-1615`).

[Inference] Fine matching is the final scan-overlap consistency gate. High spatial proximity alone does not imply a response above 0.7; heading, occlusion, corridor symmetry, and which scans form the chain can all affect it.

[Unknown] Phase 2A contains no fine-response values or rejected-match covariance, so a specific no-closure case cannot be labelled coarse versus fine rejection from logs alone.

### 4. Constraint insertion and correction

[Code] On fine acceptance, Karto calls `LinkChainToScan`, optimizes with `CorrectPoses`, emits update events, increments `mCountLoop`, and logs `Add one Loop closure` (`OpenMapper.cpp:1616-1633`).

[Code] `LinkChainToScan` links the current scan to the closest scan in the accepted chain when their corrected-pose distance is below `LinkScanMaximumDistance` (default 10 m; not modified here).

[Inference] The accepted-loop log is the most direct observable for a genuine Karto loop closure. A new graph edge temporally associated with that callback and a correction of the pre-existing trajectory provide independent corroboration.

[Code] `/Mapper/closure_edges` is not an accepted-loop callback. `MultiMapper.cpp` fills it with graph edges that do not match its sequential edge traversal. Ordinary running-scan and near-chain links can therefore increase this marker without `TryCloseLoop` acceptance.

## Frozen detection rule

[Config] Positive-control success requires both:

1. `Add one Loop closure` during the explicit revisit window; and
2. a new before/after pose-graph edge connecting the new scan region to historical scans with clear temporal/index separation.

[Inference] For Phase 2A global audit, the accepted Karto callback is primary. Large scan-index gaps and marker edges without that callback remain auxiliary local/unknown graph links and are not promoted to true loop constraints.

## Positive control

[Config] All attempted map3 trials use the unchanged robot and Karto configuration. Each trial first runs normal `NearestFrontierPlanner` exploration to completion, then an independent `/MoveTo` client revisits Karto history indices 60, 55, 50, 45, 40, 35, and 30 in reverse order. The action tolerance is 0.25 m and 0.10 rad. This intervention is outside the Graph-Based planner and does not alter any matching threshold.

[Config] Four trials were attempted to obtain three complete explicit revisits. Trial 3 is retained as an invalid control execution: `/MoveTo` target 3 remained ACTIVE until its fixed 420 s timeout, so no complete after snapshot exists and it is not counted as a Karto-negative trial. Trials 1, 2, and 4 completed all 7/7 targets. All four runtime `/Mapper` dumps have identical SHA-256 `519303a86f1c58b1c55e286f2ba0d2f0293b8f263506ea4255827366b5a9ffd7`.

| Trial | Valid revisit | Revisit accepted events | Full nodes before/after | Cross-cutoff non-local marker edges | Historical correction mean/max | Result |
|---:|---|---:|---:|---:|---:|---|
| 1 | yes, 7/7 targets | 1 | 565 / 720 | 41 | 0.113 / 0.220 m | positive |
| 2 | yes, 7/7 targets | 1 | 527 / 610 | 2 | 0.104 / 0.211 m | positive |
| 3 | no, target 3 timeout | n/a | no complete after snapshot | n/a | n/a | invalid execution |
| 4 | yes, 7/7 targets | 1 | 512 / 635 | 75 | 0.087 / 0.247 m | positive |

[Inference] Karto success conditional on a valid explicit revisit is 3/3 (100%). End-to-end positive-control completion is 3/4 attempts (75%) because of the one navigation failure. Every valid revisit contains exactly one accepted Karto callback plus corroborating cross-cutoff graph-marker edges and a nonzero historical trajectory correction.

[Code] Each valid trial's `positive_control.json` contains every resolved marker-edge `source`, `target`, scan-index gap, and endpoint match error under `marker_nonlocal_history_link_edges`. The accepted callback does not expose its edge ID, so the marker list corroborates graph change but is not used to assert which single edge was inserted by that callback.

[Inference] The positive control proves that the unchanged current Karto configuration and the combined accepted-log/full-graph detection chain can both produce and detect real closures on map3. Therefore a global backend inability or a globally blind measurement chain cannot explain the Phase 2A 0/21 result.

[Inference] The custom incremental `/slam_pose_graph` stream remained at 565 nodes after exploration even though Karto's full `/slam_path` reached 720. Consequently that custom stream is a known incomplete post-exploration observation channel; it is preserved as evidence but is not used alone to reject a closure.

## Phase 2A global passive-loop audit

[Config] The audit scans the complete saved `rosout.log` and pose-graph updates for all ten Phase 2A runs, not only active-loop intervals.

[Inference] None of the ten runs contains an `Add one Loop closure` callback. Thus the measured true-constraint counts are:

| Run set | Total true constraints | Passive/incidental | Planned-active | Unknown true constraints |
|---|---:|---:|---:|---:|
| 5 Prior-TSP runs | 0 | 0 | 0 | 0 |
| 5 SLAM-aware runs | 0 | 0 | 0 | 0 |

[Inference] The closure scan-index-gap distribution and closure time/position lists are empty in every run. The SLAM-aware graphs do contain auxiliary edges with gap above 70 in pair 1 (1), pair 4 (2), and pair 5 (12), but no accepted callback accompanies them. Under the frozen detection rule these remain local/unknown auxiliary links, not true Karto closures.

[Code] Per-run values are stored in `results/phase2b/diagnosis/passive_loop_audit.csv`; raw accepted-line and active-window evidence is stored in `passive_loop_audit_detail.json`.

## Active-loop opportunity and failure taxonomy

[Config] `results/phase2b/diagnosis/active_loop_opportunity.csv` records all 21 loops. Raw variables include high-level vertex, service-selected history pose IDs and poses, planned loop path, actual GT trajectory transformed to map frame, spatial/heading gaps, scan-index and temporal-gap lower bounds, reconstructed candidate chains, overlap lengths, keyscan timing, and accepted-constraint evidence. No synthetic score is introduced.

[Inference] All 21 executions entered within 1 m of at least one service-selected historical pose. The minimum distance has mean/median 0.232/0.092 m and range 0.014--0.871 m. Only 10/21 entered both the 1 m positional and 0.52 rad heading neighborhood.

[Inference] The high-level loop vertex and service-selected historical pose are not equivalent targets: target-to-history distance has mean/median 2.560/2.851 m and range 0.187--4.143 m. Actual trajectory to the high-level vertex has mean/median minimum distance 2.170/1.979 m. The actual loop trajectory fraction within 1 m of any pre-loop history has mean/median 0.327/0.320 and range 0.066--0.565.

[Inference] Ten of 21 loops reconstruct at least one candidate chain satisfying the explicit 4 m, near-linked-exclusion, and chain-size-four filters. Eleven do not. Nineteen have a new keyscan batch observed within the recorded loop interval; two have only a post-loop batch and cannot be aligned reliably.

[Inference] After the positive-control gate passed, the evidence-bounded primary taxonomy is 10 probable opportunity failures, 9 probable matching failures, and 2 unknown timing cases. No case is marked confirmed because Phase 2A lacks rejected coarse/fine response, covariance, scan barycenter, and exact in-process candidate-set telemetry. No redundant-loop case is confirmed.

| Category | Loop count | Evidence interpretation |
|---|---:|---|
| A. Measurement failure | 0 | Not supported as the 0/21 explanation; positive callbacks are observable and none exists in Phase 2A rosout |
| B. Backend/configuration failure | 0 | Not supported as a global inability; unchanged Karto closes loops in 3/3 valid controls |
| C. Opportunity failure | 10 | Probable; keyscan observed but no eligible chain reconstructed |
| D. Matching failure | 9 | Probable; keyscan and candidate chain reconstructed but no accepted callback |
| E. Redundant-loop case | 0 | No case can be confirmed from the saved graph evidence |
| F. Unknown | 2 | Keyscan publication batch cannot be aligned reliably to the loop interval |

[Code] The one-row-per-loop assignments and rationales are stored in `results/phase2b/diagnosis/failure_taxonomy.csv`.

[Unknown] The exact coarse-versus-fine rejection stage for the nine probable matching failures is unknowable from the saved INFO-level Phase 2A logs.
