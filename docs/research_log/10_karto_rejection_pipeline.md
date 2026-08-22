# Phase 2C: Karto loop-closure rejection pipeline (code-level map)

Date: 2026-08-22

## Scope

This document is the ground-truth code map of every stage of the Karto loop-closure
pipeline as it actually runs in this workspace, plus the Phase 2C observation-only
diagnostics instrumentation that records each stage. All line numbers refer to the
post-instrumentation source files.

Source root: `dependencies/navigation_2d/nav2d_karto/`
(also mirrored at `catkin_ws/src/navigation_2d/`; navigation_2d commit `96b3e1f`)

## Effective runtime configuration (map3)

| Parameter | Value | Source |
|---|---:|---|
| `MinimumTravelDistance` | 1.0 m | `baseline/.../param/mapper.yaml` |
| `MinimumTravelHeading` | 0.52 rad | `param/mapper.yaml` |
| `LoopSearchMaximumDistance` | 4.0 m | `param/mapper.yaml` |
| `LoopSearchSpaceDimension` | 5.0 m | `param/mapper.yaml` |
| `LoopSearchSpaceResolution` | 0.05 m | OpenKarto default (absent from yaml) |
| `LoopSearchSpaceSmearDeviation` | 0.03 m | OpenKarto default (absent from yaml) |
| `LoopMatchMinimumChainSize` | 4 scans | `param/mapper.yaml` |
| `LoopMatchMaximumVarianceCoarse` | 0.16 m² per x/y diagonal | `param/mapper.yaml` |
| `LoopMatchMinimumResponseCoarse` | 0.6 | `param/mapper.yaml` |
| `LoopMatchMinimumResponseFine` | 0.7 | `param/mapper.yaml` |
| `LinkScanMaximumDistance` | 10.0 m | OpenKarto default |
| `LinkMatchMinimumResponseFine` | 0.6 | OpenKarto default |
| `ScanBufferSize` | 70 | OpenKarto default |

## Pipeline stage table

Steps are numbered in execution order for one accepted keyscan.

| # | Stage | Repo / file | Function | Line range | Input | Output | Reject condition | Existing logging |
|---|---|---|---|---|---|---|---|---|
| 1 | keyscan creation | OpenKarto `source/OpenMapper.cpp` | `OpenMapper::Process` ("object is a key scan") | ~2430-2510 (post-instr) | raw scan, last scan | accepted keyscan with state id | `HasMovedEnough` false and no custom item → not a keyscan, no loop search | ROS_DEBUG only; Phase 2C adds `PHASE2C_KEYSCAN_ACCEPTED` in `MultiMapper.cpp` |
| 2 | loop search trigger | OpenKarto `OpenMapper.cpp` | `Process` end (`TryCloseLoop(pScan, *iter)`) | ~2505 | keyscan | loop search | none | commented `ROS_WARN` |
| 3 | historical scan search | `MapperGraph::FindPossibleLoopClosure` | ~2327-2400 | current scan, sensor scans | candidate chain (one at a time) | none (returns empty if none) | none |
| 4 | max-distance filtering | same | loop body | ~2360 | candidate scan pose vs current pose | in-distance set | `squaredDistance >= maxDist² + tol` → candidate skipped; chain flushed | none |
| 5 | near-linked (BFS) filtering | `MapperGraph::FindNearLinkedScans` | ~2110-2128 | current scan, max distance | near-linked scan set | — | — | none |
| 5b | near-linked exclusion | `FindPossibleLoopClosure` | ~2366-2375 | in-distance scan | chain reset if near-linked | scan in `nearLinkedScans` → `chain.Clear()` | none |
| 6 | candidate chain construction | `FindPossibleLoopClosure` | ~2376-2384 | non-near-linked in-distance scans | running chain | — | — | none |
| 7 | minimum chain-size decision | `FindPossibleLoopClosure` | ~2385-2394 | running chain | return chain or clear | chain left with `Size() < LoopMatchMinimumChainSize` and scan left the window → cleared (except trailing partial chain at end of scan list, which is returned as-is) | `KARTO_DEBUG2` only |
| 8 | coarse match | `MapperGraph::TryCloseLoop` | ~1675 | current scan + candidate chain | best pose + covariance + coarse response | — | — | `COARSE RESPONSE` event (INFO level event, ROS_DEBUG in `MultiMapper::onMessage`) |
| 9 | coarse response | same | ~1676 | coarse match result | `coarseResponse` | — | `coarseResponse <= LoopMatchMinimumResponseCoarse (0.6)` | same event |
| 10 | coarse variance | same | ~1678 | covariance | `cov(0,0)`, `cov(1,1)` | — | `cov >= LoopMatchMaximumVarianceCoarse (0.16)` on either diagonal | same event |
| 11 | alternate coarse condition | same | ~1686-1692 | response + variance | primary OR alternate branch | — | alternate: `coarseResponse > 0.54` AND both `cov < 0.0016` | ROS_DEBUG "Coarse LC failed" |
| 12 | fine match | same | ~1710 | current scan (pose temporarily = coarse best) + chain | `fineResponse` | — | — | `FINE RESPONSE` event |
| 13 | fine response | same | ~1711 | fine match result | `fineResponse` | — | `fineResponse < LoopMatchMinimumResponseFine (0.7)` → revert pose | ROS_DEBUG "Fine LC failed" + `REJECTED!` event |
| 14 | accepted/rejected decision | same | ~1719-1790 | coarse pass AND fine pass | loopClosed | — | — | `Add one Loop closure` ROS_WARN on accept |
| 15 | `LinkChainToScan` | `MapperGraph::LinkChainToScan` | ~1960-1985 | chain, current scan, best pose/cov | graph edge to closest chain scan | `distance >= LinkScanMaximumDistance (10 m)` → no edge | `KARTO_DEBUG2` |
| 16 | `CorrectPoses` | `MapperGraph::CorrectPoses` | ~2410-2440 | full pose graph | optimized poses | — | — | none |
| 17 | accepted callback/log | `TryCloseLoop` | ~1755-1766 | — | `mCountLoop++`, `ROS_WARN("Add one Loop closure. ...")`, PreLoopClosed/PostLoopClosed events | — | — | ROS_WARN |
| 18 | closure edge publishing | `MultiMapper.cpp` | `onMessage` (ROS_DEBUG), `closure_edges` marker builder | ~920-925 | graph edges | `/Mapper/closure_edges` marker | — | marker is NOT an accepted-loop callback |

Note on stage 7: in this OpenKarto version, when the scan list ends while the running
chain still contains eligible scans, the trailing partial chain is returned even when
its size is below `LoopMatchMinimumChainSize`. `TryCloseLoop` therefore *can* coarse-match
a chain of size 1-3. This is faithful to the vendored code and is recorded verbatim by
the diagnostics (`chain_size`).

## Phase 2C diagnostics instrumentation (observation-only)

Added files/members (default off):

- `OpenKarto/source/OpenKarto/OpenMapper.h`
  - public `SetLoopDiagnostics(kt_bool enable, const karto::String& path, const karto::String& runId)`
  - private `ResetLoopDiagnostics()`, `AppendLoopDiagnosticsLine(const std::string&)`,
    `BuildLoopDiagBaseFragment(LocalizedLaserScan*)`
  - private members `m_LoopDiagnosticsEnabled`, `m_LoopDiagnosticsPath`,
    `m_LoopDiagnosticsRunId`, `m_DiagScansConsidered`, `m_DiagScansInDistance`,
    `m_DiagScansNearLinked`, `m_DiagChainCount`
- `OpenKarto/source/OpenMapper.cpp`
  - `SetLoopDiagnostics` / `ResetLoopDiagnostics` / `AppendLoopDiagnosticsLine` /
    `BuildLoopDiagBaseFragment` implementations
  - `TryCloseLoop`: resets counters; classifies coarse outcome; emits one JSONL record
    per candidate-chain attempt (coarse-reject / fine-reject / accepted)
  - `TryCloseLoop`: emits one `loop_search_no_chain` record when no chain was attempted
  - `FindPossibleLoopClosure`: accumulates `m_DiagScansConsidered/InDistance/NearLinked/ChainCount`
- `src/MultiMapper.cpp`
  - reads `enable_loop_diagnostics` (default false), `loop_diagnostics_path`,
    `loop_diagnostics_run_id`; calls `SetLoopDiagnostics`
  - emits observation-only `PHASE2C_KEYSCAN_ACCEPTED unique_id=.. state_id=.. sim_time=..`
    after each accepted keyscan (sim-time anchor for alignment)
- `baseline/Graph-Based_SLAM-Aware_Exploration/param/mapper.yaml`
  - adds `enable_loop_diagnostics: false`, `loop_diagnostics_path: ""`, `loop_diagnostics_run_id: ""`

### JSONL record schema

One record per candidate-chain attempt:

```json
{
  "event": "loop_search_chain" | "loop_search_no_chain",
  "wall_time_ms": <steady clock ms>,
  "run_id": "<set externally>",
  "scan_id": <current keyscan state id>,
  "scan_unique_id": <unique id>,
  "scan_pose_x": ..., "scan_pose_y": ..., "scan_yaw": ...,
  "loop_search_triggered": true,
  "historical_scans_considered": N,
  "historical_scans_in_distance": N,
  "historical_scans_filtered_near_linked": N,
  "candidate_chain_count": N,
  "chain_attempt_index": i | null,
  "chain_id": i | null,
  "chain_size": n,
  "scan_ids": [ ... ],
  "min_scan_index_gap": g, "max_scan_index_gap": g,
  "coarse_attempted": bool,
  "coarse_response": r | null,
  "coarse_variance_x": v | null,
  "coarse_variance_y": v | null,
  "coarse_pass": bool | null,
  "coarse_reject_reason": "COARSE_LOW_RESPONSE"|"COARSE_HIGH_VARIANCE"|"COARSE_ALT_REJECT"|null,
  "fine_attempted": bool,
  "fine_response": r | null,
  "fine_pass": bool | null,
  "accepted": bool,
  "reject_stage": "CANDIDATE"|"COARSE"|"FINE"|"ACCEPTED",
  "reject_reason": "..."|null
}
```

`historical_scans_*` are cumulative over all `FindPossibleLoopClosure` calls of one
`TryCloseLoop` (i.e., per keyscan loop search). `candidate_chain_count` is the number of
non-empty chains returned by `FindPossibleLoopClosure` during that search.

### Reject-reason derivation (faithful to the vendored condition)

- no chain: `NO_SPATIAL_CANDIDATE` (in_distance == 0), `ALL_CANDIDATES_NEAR_LINKED`
  (in_distance == near_linked), else `CHAIN_TOO_SHORT` (eligible scans existed but no
  chain of size >= 4 formed).
- coarse rejected: `COARSE_LOW_RESPONSE` (response <= 0.6 and not in the 0.54..0.6 window),
  `COARSE_ALT_REJECT` (response in 0.54..0.6 but variance not < 0.0016),
  `COARSE_HIGH_VARIANCE` (response > 0.6 but variance >= 0.16 on a diagonal).
- fine rejected: `FINE_LOW_RESPONSE` (fine response < 0.7).
- accepted: `ACCEPTED`.

These are computed after the fact from the same already-computed values; the original
decision branch is untouched.

## Diagnostics control-flow guarantee

- When `enable_loop_diagnostics=false` (default), `SetLoopDiagnostics` stores state only;
  `AppendLoopDiagnosticsLine` returns immediately; counters are still incremented in
  `FindPossibleLoopClosure` (integer adds, no control-flow effect) and reset at each
  `TryCloseLoop` (no effect). No threshold, branch, selection, ordering, chain
  construction, return value, optimization, or SLAM decision is modified.
- The only new ROS log in `MultiMapper.cpp` (`PHASE2C_KEYSCAN_ACCEPTED`) is emitted
  regardless of the flag; it is observation-only (one INFO line per keyscan).
