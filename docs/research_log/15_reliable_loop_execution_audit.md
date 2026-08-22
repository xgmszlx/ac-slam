# Phase 3A Stage C: Reliable-Loop Execution Audit

Date: 2026-08-22

## 1. Purpose

Before designing the minimal oracle (V1 history-trace revisit), audit exactly how the
active-loop revisit is realized today: what the `reliable_loop_service` returns, how the
C++ planner consumes it, how the robot navigates it, and where orientation is lost.
Everything below refers to the active tree `catkin_ws/src/cpp_solver` (built) and
`catkin_ws/src/navigation_2d/nav2d_*` (built); the `baseline/` copy is the frozen
reference.

## 2. Service contract

`catkin_ws/src/cpp_solver/srv/ReliableLoop.srv`:

```
int32 goal_vertex
---
float32[] loop_x_coords
float32[] loop_y_coords
```

- Request: a prior-graph vertex id.
- Response: x and y coordinate arrays only. **There is no yaw / orientation field.**

## 3. Server behavior

`catkin_ws/src/cpp_solver/scripts/path_planner.py::handle_reliable_loop` (L670):

1. Looks up `self.vertices_to_poses[map_vertex]` — the list of pose-graph (Karto state)
   ids whose closest prior-graph vertex is `map_vertex`, in state-id order (the robot's
   passage through the vertex region).
2. Finds `closest_pose_idx`: the passage pose whose (x,y) is closest to the vertex
   position.
3. Returns the **next up-to-7 consecutive passage poses** after `closest_pose_idx`
   (`range(closest_pose_idx, min(closest_pose_idx+7, len(...)))`), x/y only.

History-pose source: `self.pose_graph`, populated by `handle_pose_graph` from the Karto
`PoseGraph` messages — i.e., **SLAM-estimated poses** (x, y, theta stored; only x/y
returned). This is deployable (no GT). Node ids are Karto state ids, added in order, so
the pose-graph node order equals the historical traversal order.

## 4. C++ consumption

`catkin_ws/src/cpp_solver/src/MyPlanner.cpp`:

- `setReliableLoopPath` (L208): stores the response as `std::vector<std::pair<double,
  double>> mClosingPath` (`make_pair(x_pos[i], y_pos[i])`). No theta is stored.
- Fallback when the service returns empty: a 4-point cross (`±1.5 m`) around the vertex.
- `loopVertexReached` (L280): advances to the next waypoint when
  `dx^2+dy^2 < 0.3` (≈ 0.55 m radius).
- `performReliableLooping` (L324): converts each waypoint to a grid index `goal` and
  returns it as the navigation target; position only.

## 5. Navigation path and orientation

- The strategy runs inside the `Navigator` node (`exploration_strategy=MyPlanner`); the
  grid `goal` becomes the navigator's `mGoalPoint` and the robot drives toward it
  (position-only).
- The navigation infrastructure **can** carry orientation elsewhere:
  `set_goal_client.cpp` converts a `PoseStamped` into `MoveToPosition2DGoal` with
  `target_pose.theta = tf::getYaw(orientation)` and `target_angle = 0.1`, and
  `RobotNavigator::receiveMoveGoal` (L637) does final heading alignment against
  `target_pose.theta` (L734-755).
- But the **reliable-loop strategy path never sets theta**: the grid-index goal is
  position-only, so the robot's heading at each waypoint is whatever the local plan
  implies. **Orientation is lost in the active-loop execution.**

## 6. Waypoint spacing

The returned waypoints are consecutive SLAM pose-graph poses (one per Karto state, i.e.,
per scan). Observed across the 21 Phase 2C loops: mean waypoint spacing 0.67–0.98 m,
max up to ~1.3 m (loop_realization_features.csv). With the 0.55 m waypoint-reached
tolerance, position-only navigation can deviate noticeably from the history path between
waypoints.

## 7. Passage length

Phase 2C returned 3–7 waypoints per loop (service cap 7 and short passages), i.e., the
vertex-assigned passage spans only ~2–9 m of history. For chain formation
(chain size ≥ 4 linked scans, sustained over consecutive keyscans) this is short —
consistent with the C3 bottleneck and with Stage B's finding that chain persistence
correlates with history-path length (r ≈ +0.67).

## 8. Oracle design constraints (derived)

- V1 must stay within the **same deployable SLAM pose-graph source**, same loop vertex
  selection, same planning, same Karto, same thresholds.
- V1 should return a **longer contiguous history trace** (extend the 7-pose cap into a
  window over the global pose-graph order spanning the vertex passage), **densified**
  (linear interpolation at ~0.5 m) to help position-only navigation hug the history.
- V1 remains **position-only** (x/y) — matching the current navigation capability. A V2
  with commanded heading would require changing the strategy→navigator goal to carry
  theta (not cheap); it is **not** part of V1.
- Oracle must be an independent variant behind an explicit switch, **default off**;
  when off, behavior is byte-identical to V0.
- GT is used only for post-hoc evaluation, never as an input to the service.

## 9. Termination feasibility

The diagnostics writer (`OpenMapper::AppendLoopDiagnosticsLine`, OpenMapper.cpp L2472)
opens the JSONL in append mode, writes one line, and closes — every record is flushed
immediately. It is therefore safe to terminate a run right after the target loop
finishes without losing loop evidence. `stop_exploration` only parks the robot
(EXPL_WAITING) without completing the Explore action, so early termination is done by
shutting the launch tree after the target loop's `PHASE2_LOOP_EXECUTION_FINISHED` plus a
short grace period.
