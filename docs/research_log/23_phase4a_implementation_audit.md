# Phase 4A Stage D: Implementation Audit

Date: 2026-08-23

## 1. Scope of the audit

Verify (a) what was implemented for the Selective Realization-Aware layer, (b) that
the forbidden subsystems were NOT modified, and (c) that `oracle_mode=0` (baseline)
behavior is unchanged.

## 2. What was implemented (all default OFF / observation-only)

| Change | Location | Repo |
|---|---|---|
| `LoopClosureEvent.msg` (seq, loop_count, current_scan, chain_start, chain_end, stamp) | `srv/…msg/LoopClosureEvent.msg` + `CMakeLists.txt` | baseline `f245537` |
| OpenKarto observation-only `LoopClosureObserved` event (emitted once per accepted closure with Karto state ids) | `OpenKarto/source/OpenKarto/OpenMapper.h`, `OpenKarto/source/OpenMapper.cpp` | navigation_2d `062283d` |
| `/Mapper/loop_closed` publisher (subscribes `LoopClosureObserved`, publishes the msg; **no matcher internals** published) | `nav2d_karto/src/MultiMapper.cpp/.h` | navigation_2d `062283d` |
| `ReliableLoop.srv` adds `bool selective_repair` response field | `srv/ReliableLoop.srv` | baseline `7c20c3c` |
| `handle_reliable_loop` `oracle_mode=2`: redesigned prototype gate G1′ (V0 history span < 4.0 m; configuration-inspired heuristic, not a theoretical Karto threshold) → REPAIR; else NO_REPAIR returns the original V0 path. Bounded repair = contiguous pose-graph segment (≤ 12 m / ≤ 24 wp, 0.5 m densify, forward/reverse by entry-distance + heading alignment). Yaw used only as direction cue. | `scripts/path_planner.py` | baseline `7c20c3c` |
| `MyPlanner` subscribes `/Mapper/loop_closed`; during repair an attributable closure (event sim stamp ≥ loop start) early-stops the remaining trace (`PHASE4A_EARLY_STOP`) | `src/MyPlanner.cpp/.h` | baseline `7c20c3c` |
| Prototype params (span_gate=4.0, max_len=12, max_wp=24, densify=0.5, dir_lambda=1.0) | launch args → path_planner params | baseline |

## 3. What was NOT modified (verified by change scope)

- **prior graph** (XML/drawio loading, `build_prior_graph*`, `prior_graph` node positions): untouched.
- **TSP** (`solve_tsp_path`, Concorde seed handling): untouched.
- **D-opt / loop-edge selection** (`MyPlanner` loop insertion, `greedy_tsp_update`, D-opt in `offline_tsp_evaluation.py`): untouched.
- **frontier planner** (`findFrontiers`, frontier allocation, Navigator frontier strategy): untouched.
- **Karto matcher thresholds** (`mapper.yaml`: LoopSearchMaximumDistance, LoopMatchMinimumChainSize, LoopMatchMaximumVarianceCoarse, LoopMatchMinimumResponseCoarse/Fine): untouched.
- **Karto candidate logic** (`FindPossibleLoopClosure`, `FindNearLinkedScans`, `LinkChainToScan`, `CorrectPoses`): untouched — the only OpenKarto edit is an additional observation-only event emission in the already-accepting path.
- **SLAM optimization** (`CorrectPoses`, scan solver, SPA): untouched.
- **GT** is never read by the method (only by evaluation tools).

Diff-scope confirmation: the three repos' changes are exactly the files listed in §2
(baseline `7c20c3c`, navigation_2d `062283d`, main repo tools/docs); no other planner /
matcher / graph / frontier files were touched.

## 4. Invariance: `oracle_mode=0` / proposed-mode-off behavior unchanged

- `oracle_mode` defaults to 0 (launch arg `oracle_mode:=0`); in `handle_reliable_loop`
  modes 0 and the NO_REPAIR branch return **exactly** the V0 7-pose path
  (`selective_repair=false`); unit test `test_no_repair_returns_original` asserts the
  V0 path is returned.
- The `/Mapper/loop_closed` publisher is observation-only: it only emits when Karto
  already accepted a closure (no behavior change; publishing is O(1) and non-blocking).
- `MyPlanner` early-stop is gated on `mSelectiveRepair` (only true for a REPAIR path),
  so a NO_REPAIR loop executes the original path to completion.
- 17/17 deterministic unit tests pass (`tools/test_phase4a_selective.py`), including
  the no-repair and early-stop state transitions and the fallback.

## 5. Residual risks recorded (not hidden)

- Repair bounds (12 m / 24 wp / 0.5 m) are **prototype defaults**, not claimed optimal.
- Direction selection uses Euclidean distance as an A* proxy (documented; the A* path
  cost is available in the C++ executor but not wired in this phase).
- The `loop_count` field is the per-mapper accepted-closure counter (== `mCountLoop`
  value for this mapper).
