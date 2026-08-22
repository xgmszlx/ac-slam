# Phase 2C: Instrumentation diff audit

Date: 2026-08-22

## Scope

This document audits every source change made for Phase 2C and verifies, file by
file, that each change is observation-only: it records intermediate quantities the
original algorithm already computes, and it does not change control flow, parameters,
planner behavior, or any Karto decision.

## Repositories and commits

| Repository | Baseline HEAD (reference) | Instrumentation commit | Worktree state |
|---|---|---|---|
| `dependencies/navigation_2d` (incl. OpenKarto) | `96b3e1fed08823dd1dd11ddb0eeead3bd24dd686` | to be created | 3 modified files (this audit) |
| `baseline/Graph-Based_SLAM-Aware_Exploration` | `211642d66c587419253cf90f0e5ecc7da520f46e` | to be created | `param/mapper.yaml` +10 lines (this audit); `scripts/__pycache__/offline_tsp_evaluation.cpython-38.pyc` changed (pre-existing bytecode artifact, not part of this change) |
| ac-slam (main) | `3db06ddc252a25cf9819b334d5530beb8577aaa6` | n/a (docs/tools) | `docs/research_log/09/10/11*` added |

## File-by-file audit

### 1. `dependencies/navigation_2d/nav2d_karto/OpenKarto/source/OpenKarto/OpenMapper.h`

Changed: +53 lines, -1.

- Added public method `SetLoopDiagnostics(kt_bool enable, const karto::String& path, const karto::String& runId)`.
  - Effect: stores configuration only. No control flow, no parameters, no thresholds.
- Added private members `m_LoopDiagnosticsEnabled`, `m_LoopDiagnosticsPath`,
  `m_LoopDiagnosticsRunId`, `m_DiagScansConsidered`, `m_DiagScansInDistance`,
  `m_DiagScansNearLinked`, `m_DiagChainCount`.
  - Effect: inert state. Counters are incremented only; never read by any decision.
- Added private methods `ResetLoopDiagnostics()`, `AppendLoopDiagnosticsLine(const std::string&)`,
  `BuildLoopDiagBaseFragment(LocalizedLaserScan*)`.
  - Effect: observation-only helpers; only invoked from diagnostic paths.

Does it change control flow / parameters / planner / Karto decision? **No.**

### 2. `dependencies/navigation_2d/nav2d_karto/OpenKarto/source/OpenMapper.cpp`

Changed: +293 lines, -0.

- Added includes (`<fstream>`, `<sstream>`, `<chrono>`, `<string>`) and anonymous-namespace
  helpers `LoopDiagDouble`, `LoopDiagBool`, `LoopDiagChainFragment`, `LoopDiagNoChainReason`.
  - Effect: serialization helpers only.
- OpenMapper constructors: initialize the six diagnostic members.
  - Effect: default state `disabled`, path empty, run id empty, counters zero.
- `OpenMapper::SetLoopDiagnostics` / `ResetLoopDiagnostics` / `AppendLoopDiagnosticsLine` /
  `BuildLoopDiagBaseFragment`: implementations.
  - Effect: `AppendLoopDiagnosticsLine` returns immediately when disabled or path empty;
    file write is append-mode and never influences mapping.
- `MapperGraph::TryCloseLoop`:
  - Resets counters at entry (`m_pOpenMapper->ResetLoopDiagnostics()`).
  - After the coarse `MatchScan`, classifies the coarse outcome into
    `coarsePass`/`coarseReason` by re-evaluating the *same* response/variance values
    against the *same* thresholds. This is read-only; the original `if (...) {...} else {...}`
    branch below is byte-for-byte unchanged.
  - Emits one JSONL record per candidate-chain attempt at each of the three terminal
    outcomes (coarse-reject, fine-reject, accepted).
  - Emits one `loop_search_no_chain` record when no candidate chain was ever returned.
  - The original decision branch, `LinkChainToScan`, `CorrectPoses`, `mCountLoop++`,
    `ROS_WARN("Add one Loop closure...")`, events, and `return loopClosed` are untouched.
- `MapperGraph::FindPossibleLoopClosure`:
  - Adds four integer counter increments (`m_DiagScansConsidered`, `m_DiagScansInDistance`,
    `m_DiagScansNearLinked`, `m_DiagChainCount`).
  - These are pure additions with no effect on the chain, the return value, or iteration.
    The chain construction logic (near-linked reset, size check, clear, return) is unchanged.

Does it change control flow / parameters / planner / Karto decision? **No.** The original
`TryCloseLoop` and `FindPossibleLoopClosure` decision code is untouched; instrumentation
only adds counters, read-only classification, and file appends.

### 3. `dependencies/navigation_2d/nav2d_karto/src/MultiMapper.cpp`

Changed: +27 lines, -0.

- After the existing Karto parameter loading, reads three ROS params
  (`enable_loop_diagnostics` default false, `loop_diagnostics_path` default "",
  `loop_diagnostics_run_id` default "") and calls `mMapper->SetLoopDiagnostics(...)`.
  - Effect: when disabled (default), nothing happens. When enabled, only the
    diagnostics file path/run id are configured; no Karto parameter or behavior changes.
  - One `PHASE2C_LOOP_DIAGNOSTICS_ENABLED` INFO log when enabled.
- After a successful `Process` (accepted keyscan), emits one observation-only
  `PHASE2C_KEYSCAN_ACCEPTED unique_id=.. state_id=.. sim_time=..` INFO log.
  - Effect: this is a new log only; it anchors each accepted keyscan to the ROS/sim
    timestamp so the diagnostics JSONL (keyed by state id) can be aligned to planner
    loop events. It does not publish, subscribe, or call any service.

Does it change control flow / parameters / planner / Karto decision? **No.**

### 4. `baseline/Graph-Based_SLAM-Aware_Exploration/param/mapper.yaml`

Changed: +10 lines.

- Adds `enable_loop_diagnostics: false`, `loop_diagnostics_path: ""`,
  `loop_diagnostics_run_id: ""` with a comment.
  - Effect: when the launch does not override them, diagnostics stay disabled and
    Karto behavior is unchanged. No existing parameter value was modified (verified:
    diff touches only the appended section).

Does it change control flow / parameters / planner / Karto decision? **No.** (The yaml
adds new keys only; existing keys are untouched.)

## Verification performed

- Clean rebuild with system Python 3.8 (`/usr/bin/python3` 3.8.10), ROS Noetic:
  `catkin_make -DPYTHON_EXECUTABLE=/usr/bin/python3 -DCMAKE_BUILD_TYPE=Release`
  completed; `mapper` target built/linked (exit 0). Only pre-existing Eigen/TBB warnings.
- `git diff --stat` above matches exactly the changes listed.
- No `sudo`, no `apt`/system install, no destructive git operation was used.
- Language-server diagnostics report no errors in the three modified C++ files.

## Baseline invariance statement

With `enable_loop_diagnostics=false` (the default in `mapper.yaml`):

- `SetLoopDiagnostics` stores `enabled=false`; `AppendLoopDiagnosticsLine` returns
  immediately; no file is opened.
- The counter increments and `ResetLoopDiagnostics` have no effect on any branch,
  value, return, or optimization.
- `PHASE2C_KEYSCAN_ACCEPTED` is a new INFO log line only; it does not affect mapping.
- The original decision code in `TryCloseLoop` / `FindPossibleLoopClosure` is unchanged
  (verified by keeping the original `if/else` verbatim and only adding instrumentation
  around it).

Therefore the baseline algorithm behavior is unchanged when diagnostics are off, and the
only runtime difference when diagnostics are on is the appended JSONL file plus the two
new INFO logs.
