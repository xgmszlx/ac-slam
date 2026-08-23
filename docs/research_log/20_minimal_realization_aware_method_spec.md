# Phase 3B Stage C: Minimal Realization-Aware Method Specification

Date: 2026-08-23 · **Spec only — no implementation in this phase.**

## 1. Problem statement

Graph-Based SLAM-aware exploration selects informative loop vertices (D-opt over the
prior graph), then executes a *reliable-loop revisit*: re-traverse up to 7 SLAM
pose-graph poses through the vertex (position-only). Phase 2C showed this realization
fails at two Karto gates (C3 chain-too-short ×12, D1 coarse<0.60 ×8). Phase 3A
showed the failures are *causally* tied to the realization: a denser, longer
history-trace revisit (V1 oracle) rescued D1 (coarse 0.401→0.685, 0.570→0.734,
0.307→0.656; two accepted) but also (i) cost +22–28 waypoints / +6–12 m / +100–165 sim s
per loop, and (ii) **regressed** the natural success s21001 v26 (0.657→0.493). Goal:
repair the realization *only when needed* and *only as much as needed*, preserving
easy loops.

## 2. Inputs

Selected loop vertex (from MyPlanner), V0 reliable-loop path (poses + x/y), pose-graph
historical sequence (SLAM pose-graph, state-id order, incl. `vertex_theta`), current
robot pose (SLAM), occupancy/navigation map, A* path cost. **No GT. No Phase 2C
diagnostics** (candidate/chain/coarse/fine stay evaluation-only).

## 3. Online-available signals

From `19_online_signal_audit.md`: selected vertex ✓, historical poses (x,y,θ) ✓
(PoseGraph.msg `vertex_theta`, corrected poses), pose-graph sequence ✓, current pose ✓,
occupancy map + A* cost ✓. The only missing signal is the **accepted-closure event**:
the normal published pose graph missed the closure vertex/edge in Phase 2C (verified).
Required addition: publish the existing "Loop closed!" mapper event as one
observation-only `std_msgs::Int32` (documented, one-directional backend coupling; no
Karto internals leak).

## 4. Realizability check (hard gates, no ML)

Two transparent gates evaluated when a loop vertex is selected, using only the V0 path
and the pose graph:

- **G1 — contiguous history span.** `span = length(V0 reliable-loop path)`. If
  `span < T_span`, the revisit cannot sustain Karto chains (chain size ≥ 4 needs ≥ 4
  linked scans ≈ 4 m at `MinimumTravelDistance = 1.0 m`; sustaining chains across the
  loop needs margin) → **C3 risk**.
- **G2 — approach/history heading consistency.** `Δ = |angle(current robot heading,
  history tangent at the closest pose)|` (tangent from `vertex_theta` of consecutive
  poses). If `Δ > T_yaw`, the scans generated during the revisit differ too much in
  view content from the historical scans at the candidate poses → **D1 risk**.

Repair fires when **G1 or G2 fails**. Otherwise original execution.

Gate-value derivation (from Phase 3A data, mechanism-based, not searched):

| Gate | Value | Basis |
|---|---|---|
| T_span | 4.5 m | Karto min chain 4 × 1.0 m scan spacing = 4 m minimum; sustaining chains needs margin; the single natural success had span 4.81 m; failing v26/C3 spans ≤ 4.15 m. |
| T_yaw | 0.78 rad (45°) | Phase 3A success yaw-med 0.561; the two D1 targets that V1 rescued (s21004 v22 0.836, s21005 v22 0.824) are just above 0.78; at ~45° a 2D scan's range profile changes materially; Karto's own MinimumTravelHeading is 0.52 rad. |

Behavior on the 21 Phase 2C loops (retrospective, not a search): repairs 17/21; the
only 4 "no-repair" cases are the natural success S (s21001 v26, protected) + 2 C3 with
long span & good heading (s21002 v26? no — s21002 v38/v16 long-span C3) + 2 good-heading
D1 (s21003 v21, s21005 v35) whose coarse failure BQ2 showed is not predictable from
trajectory features. A small sensitivity analysis (T_span±1 m, T_yaw±0.26 rad) is
planned, **not** a brute-force map3 search.

## 5. History segment construction

On repair: take the contiguous pose-graph segment around the vertex's closest pose,
bounded:
- `S = poses[c − k, c + k]` in state-id order, where `k` grows until the segment length
  reaches `min(required_span, L_repair_max)` or the vertex passage ends.

## 6. Direction selection

Compare forward (enter at segment start, walk toward vertex, same direction as the
original history) vs reverse (enter at segment end). Score both by
`cost = A*(robot → entry) + λ · |heading at entry − history heading at entry|`; choose
the smaller. Rationale: Phase 3A / Lighthouses both note *view directionality* matters;
the entry that aligns with the history heading and is cheaper to reach yields
better scan-content overlap. (Only one extra A* call per candidate.)

## 7. Bounded repair

Execute the chosen segment as waypoints, densified by linear interpolation at
`d_repair = 0.5 m` (justification: the strategy's waypoint-reached tolerance is
≈0.55 m, so 0.5 m spacing keeps position-only navigation within ~0.25 m of the history
polyline). Hard caps:
- `L_repair_max = 12 m` (≈ V1's effective useful span, bounded below its 15.5 m to cut
  cost),
- `W_repair_max = 24` waypoints,
- direction fixed by §6; all caps stop the trace.

## 8. Accepted-closure early stop

During the repair, subscribe to the observation-only `/Mapper/loop_closed` event. On
the **first** accepted closure, immediately set the remaining repair waypoints as
finished (terminate the trace) and complete the loop. Only a real online SLAM closure
event triggers this — no GT, no diagnostics, no heuristic.

## 9. Fallback

- If gates pass → execute the original V0 reliable-loop path (byte-identical behavior;
  the S-reference and other easy loops are therefore untouched).
- If the repair cannot be built (e.g., contiguous segment unavailable) → fall back to
  the original V0 path.
- If the repair runs but produces no closure by the end of the trace → the loop ends as
  before (no infinite retry; recorded as a failed loop like V0).

## 10. Computational complexity

- Gates: O(|V0 path|) length + O(1) heading (from pose graph). Negligible.
- Segment construction: O(|pose graph|) in the worst case, bounded.
- Direction selection: 2 × A* on the occupancy map (already standard in the pipeline).
- Densify/interp: O(W_repair_max).
- Early stop: O(1) subscription.
Total: no learned components, no optimization loops, bounded by map size like the
existing planner.

## 11. Parameters (with basis, small sensitivity planned)

| Param | Value | Basis |
|---|---|---|
| T_span | 4.5 m | §4 |
| T_yaw | 0.78 rad | §4 |
| d_repair | 0.5 m | waypoint-reached tolerance 0.55 m |
| L_repair_max | 12 m | ≤ V1's 15.5 m; cost bound |
| W_repair_max | 24 | 12 m / 0.5 m |
| λ (direction) | 1.0 m/rad | equal-weight default; sensitivity |

## 12. Failure cases

- **Gates pass but original still fails** (e.g., good-heading D1 s21003 v21, s21005
  v35): accepted as a limitation (BQ2: not trajectory-predictable); recorded, no
  infinite retry.
- **Repair regresses a loop that would have closed**: possible for borderline loops
  near the gates; mitigated by bounded caps + early stop; measured by Regression Rate
  (§Phase 4). If systematic, raise T_span/T_yaw.
- **Segment spans unknown/obstructed terrain**: A* cost is prohibitive → direction
  selection picks the feasible one, else fallback to V0.
- **Closure event loss**: if `/Mapper/loop_closed` is missed (no event), repair simply
  runs to its caps — safe.

## 13. Difference from Oracle V1 (Phase 3A)

V1 = **Always-Trace**: unconditional ±8-pose window, full 0.5 m densify, no caps, no
early stop, no direction selection → +22–28 waypoints and the S-reference regression.
Proposed = **Selective**: gate decides repair vs original (protects easy loops),
bounded (12 m / 24 wp), direction-aware, and early-stops on the first accepted closure.
This directly targets Phase 3A's F3 (non-monotonicity) and F4 (cost) findings.

## 14. Difference from nearest-neighbor literature

- vs **Probabilistic Active Loop Closure** (ICRA 2024): they model P(loop closure) at
  the *selection* level (uncertainty × success − cost). We keep selection fixed and
  never model probability; we act *after* selection on realization.
- vs **Lighthouses/SAE** (ICRA 2023): they *always* travel back and rotate in place at
  feature-rich lighthouses; we repair *only when gates fail*, only at the already
  selected loop vertex, with bounded re-traversal (not in-place rotation) and early
  stop.
- vs **Region-based SLAM-aware** (2025): strategy-level region partitioning; we change
  no strategy, only post-selection execution.
- vs **baseline**: only the execution layer after target selection changes.

## 15. Planned ablations (Phase 4)

1. **A Original** vs **C Proposed** (primary).
2. **B Always-Trace V1** vs **C Proposed** (cost + regression).
3. Gate ablation: C-without-G1 (only heading), C-without-G2 (only span),
   C-without-early-stop — attribute the acceptance/cost/regression contributions.
4. Parameter sensitivity (small grid): T_span {3.5, 4.5, 5.5}, T_yaw {0.52, 0.78, 1.04},
   L_repair_max {8, 12, 16}.

## Pseudocode

```
# Online, per selected loop vertex v (called once when the loop triggers)
def realizability_check(v, current_pose, pose_graph, v0_path):
    span = path_length(v0_path)
    tangent = history_tangent_at_closest_pose(pose_graph, v)      # from vertex_theta
    heading = current_pose.theta
    d_yaw = wrap_angle(heading - tangent)
    g1 = span < T_span
    g2 = abs(d_yaw) > T_yaw
    return (g1 or g2), g1, g2

def build_repair(v, pose_graph, robot):
    seg = contiguous_segment(pose_graph, v, max_len=L_repair_max)  # state-id order
    fwd_cost = A_star(robot, seg.start) + LAMBDA * |heading_at(seg.start) - history_heading(seg.start)|
    rev_cost = A_star(robot, seg.end)   + LAMBDA * |heading_at(seg.end)   - history_heading(seg.end)|
    seg = reverse(seg) if rev_cost < fwd_cost else seg
    waypoints = densify(seg, d_repair)                                # 0.5 m
    return waypoints[:W_repair_max]

# Main flow
on_loop_selected(v):
    v0_path = reliable_loop_service(v)                 # unchanged baseline query
    repair, g1, g2 = realizability_check(v, current_pose, pose_graph, v0_path)
    if not repair:
        execute(v0_path)                               # original baseline execution
    else:
        wp = build_repair(v, pose_graph, current_pose)
        log PHASE3B_REPAIR vertex=v g1=... g2=... waypoints=len(wp)
        for w in wp:
            if loop_closed_event_seen:                  # /Mapper/loop_closed (real SLAM event)
                log PHASE3B_EARLY_STOP vertex=v
                break
            navigate_to(w)
        finish_loop()
```

## Design verification against the Phase 3A counter-example

- **Why did s21001 v26 regress under Always-Trace?** Its V0 execution was already
  realizable (span 4.81 m, yaw-med 0.56 rad, chain 8, coarse 0.657): the natural
  trajectory through the vertex produced the match. Always-Trace unconditionally
  replaced that trajectory with a 33-waypoint detour, changing the scan sequence at the
  vertex so the good match was never formed.
- **Why does the Selective method avoid it?** The gates evaluate the *same* features
  that were good for v26: span 4.81 ≥ T_span and |Δyaw| 0.56 ≤ T_yaw → no repair →
  original V0 execution → the natural closure is preserved. Repair fires only on
  profiles that Phase 3A data shows are structurally inadequate (short span → C3;
  heading mismatch → D1). Regression is further bounded by the early stop and the
  explicit Regression Rate metric.
