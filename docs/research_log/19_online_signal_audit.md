# Phase 3B Stage B: Online-Available Signal Audit

Date: 2026-08-23

## 1. Purpose

Determine, from the real system (no GT), which signals are genuinely available online
to a post-selection execution layer, which are only evaluation-grade, and which would
require a minimal interface addition. GT never enters the method.

## 2. Verified signal inventory (from code + Phase 2C/3A data)

| Signal | Source (file/line) | Online? | Reliability notes |
|---|---|---|---|
| Selected loop vertex | `MyPlanner::mActiveLoopVertex` / `setReliableLoopPath` | Yes | int; set when the reliable loop triggers |
| Reliable-loop historical poses (x,y) | `path_planner.py::handle_reliable_loop`, `self.vertices_to_poses` | Yes | SLAM pose-graph poses, already used by V0/V1 |
| **Historical pose heading (theta)** | `PoseGraph.msg::vertex_theta` ← `MultiMapper::publishPoseGraph` (corrected pose heading) | **Yes** | SLAM-estimated corrected heading; same estimate used to build the map. Usable for approach/tangent consistency gates (Phase 3A orientation analysis used trajectory-derived SLAM yaw with the same provenance) |
| Pose-graph historical sequence | pose ids in `self.pose_graph` (state-id order) | Yes | monotonic state ids = traversal order |
| Current robot pose | Navigator/SLAM localization (odom + corrected pose) | Yes | standard |
| Occupancy / navigation map | `GridMap` in MyPlanner/Navigator | Yes | used by A* |
| Path cost | A* in Navigator/MyPlanner | Yes | standard |
| Candidate chain / coarse / fine / reject reason | Phase 2C diagnostics `karto_loop_diagnostics.jsonl` (OpenMapper, default off) | Not for the method | evaluation/scientific only; would couple planner to Karto internals; left out of the method |

## 3. Accepted-closure online event (for early stop)

**Finding from Phase 2C data:** the *normal* published pose graph does **not** reliably
expose an accepted closure online. In seed_21001 the accepted closure at scan 679
(chain 429–434, gap 245–250) produced **no** long-gap edge in the saved pose graph
(`pose_graph.g2o` max vertex = 678; the 679 vertex and the closure edge were absent).
The incremental `/slam_pose_graph` therefore cannot be used as the early-stop trigger.

**What IS available in the normal SLAM interface:** OpenKarto raises
`MapperEventArguments("Loop closed!")` (`PreLoopClosed`/`PostLoopClosed` events), and
`MultiMapper::onMessage` (MultiMapper.cpp L916) currently only logs it at DEBUG.
`mCountLoop` increments there (OpenMapper.cpp L1768, "Add one Loop closure").

**Minimal recommended addition (observation-only, no algorithm change):** in
`MultiMapper::onMessage`, when `args.GetEventMessage() == "Loop closed!"`, publish one
`std_msgs::Int32` (running loop count) on a topic like `/Mapper/loop_closed`. This is a
plain interface event — the same kind as the existing `closure_edges` marker — and is
**not** the Phase 2C diagnostics (no candidate/chain/coarse/fine internals leak).

**Backend coupling discussion (required by the spec):**
- The planner observes a SLAM-side boolean event; it never writes into Karto, never
  alters thresholds or the graph. This is one-directional observation coupling, the
  same category as subscribing to `/slam_pose_graph` or odometry.
- It is *runtime-safe*: the event is emitted synchronously inside `TryCloseLoop` after
  `CorrectPoses`, in the mapper thread; publishing a small message is O(1) and cannot
  deadlock or stall the loop search (no blocking calls).
- It is *semantically* the ground-truth "a loop closure was accepted" signal — exactly
  the event the Phase 3A oracle used to evaluate acceptance (the diagnostics ACCEPTED
  record matched it 1:1).
- If the reviewer rejects any mapper change, the fallback is to keep the early stop off
  and rely on the bounded repair cap alone; but then "stop after accepted closure" is
  not implemented (it would degrade to Always-Trace-with-cap).

## 4. Signals the method will NOT use

- GT trajectories (evaluation only).
- Phase 2C diagnostics (candidate chain, coarse/fine response, reject reason): kept
  evaluation/scientific only. They are computed in Karto at runtime, but using them for
  online execution would couple the planner to internal matcher state and blur the
  "evaluation-only instrumentation" boundary established in Phase 2C.

## 5. Summary

Everything needed for the Realizability Check and the Bounded History-Trace Repair is
online today via normal interfaces (poses + headings + map + path cost + selected
vertex). The only missing online signal is the accepted-closure event, which requires
one observation-only publish of the existing "Loop closed!" event (documented above).
