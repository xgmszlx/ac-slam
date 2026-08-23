# Phase 3B Stage A: Realization-Aware Literature Boundary

Date: 2026-08-23

## 1. Scope and method

Reviewed the four designated core papers in detail plus the closest 2022–2026 and
classical relatives found via Semantic Scholar / arXiv search on: active loop closure,
loop closure probability, revisit trajectory, historical trajectory, keyframe cluster,
pose graph stabilization, loop-aware exploration, relocalization-aware navigation,
viewpoint consistency. "Evidence" marks whether the claim is from full text (FT) or
abstract only (AB). The purpose is a *boundary*: which parts of our Phase 3A finding
are already occupied in the literature, and which are not.

## 2. Literature table

Legend for the last columns: Sel=target selection, Model-P=loop-success probability
modeled, Hist=historical trajectory used in revisit, View=orientation/viewpoint
considered in revisit, Adapt=execution adapts after target selection, Online=closure
success observed online, Stop=execution stops after accepted closure.

| paper | year/venue | sensor | SLAM backend | ALC target repr. | how target selected | Model-P | Hist | View | what robot does during revisit | Adapt | Online | Stop |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Graph-Based SLAM-Aware Exploration** (Bai et al., 2308.16522) — our baseline | 2024 RA-L | 2D laser | Karto (grid) | prior-graph vertex | D-opt informative loop edges over TSP | No (topology-based objective) | Yes (up to 7 SLAM pose-graph poses) | No (position-only waypoints) | re-traverse ≤7 historical poses through the vertex | No (fixed reliable-loop state machine) | Indirect (Karto accepts/rejects; not used for adaptation) | No | 
| **Lighthouses & Global Graph Stabilization** (Deshpande et al., 2306.10463) | 2023 ICRA | narrow-FoV depth+stereo | keyframe pose-graph vSLAM | lighthouse = spatially-clustered keyframes (panoramic view) | view-score threshold; timer / relative-uncertainty trigger | Heuristic (feature count correlates with LC likelihood) | Yes (travel back to created lighthouses) | **Yes** (in-place rotation emulates panoramic; bi-directional hull views) | travel to lighthouse + in-place rotation; GGS traverses convex-hull vertices both directions | Yes (preempts FE; connects lighthouses) | Yes (SLAM reports LC) | No per-revisit (continues to next plan; GGS is a phase) |
| **Probabilistic Active Loop Closure** (Yin et al., ICRA 2024) | 2024 ICRA | (indoor robot, on-device) | pose graph | pose on the pose graph | reward = P(loop closure at pose) × uncertainty reduction − travel cost; argmax | **Yes** (probabilistic reward of getting a loop closure at a pose) | Not stated in AB | Not stated in AB | navigate to the chosen pose (execution detail not in abstract) | Selection-level; execution not detailed | Not stated in AB | Not stated in AB |
| **Region Based SLAM-Aware Exploration** (Maheshwari et al., 2504.10416) | 2025 arXiv | (indoor robot) | pose graph + keyframe marginalization | region (partition of environment) | partition → explore+stabilize each region before next | No | Partial (keyframes) | No | region-by-region exploration; in-region stabilization; checkpoint resume | Yes (region sequencing) | Yes (stability check) | Not per-loop |
| **Loop-Aware Exploration Graph** (Pittol et al., 10.1016/j.robot.2022.104179) | 2022 RAS | 2D (indoor) | pose graph | loop candidates on an exploration graph | graph-based representation for exploration + active LC | No (AB) | Partial (graph of visited structure) | No (AB) | revisit to close loops (AB) | No (AB) | Not stated | No |
| **Exploration with Global Consistency via Re-integration + Active LC** (Zhang et al., ICRA 2022) | 2022 ICRA | RGB-D | dense/voxel + LC | frame (LC detection) | frame pruning + active LC (drift correction focus) | No | No | No | re-integration mapping after detected LC (not target revisit) | No | Yes (detects LC online) | N/A |
| **A3RGB-D SLAM** (Zhu et al., ICRA 2023) | 2023 ICRA | RGB-D | RGB-D SLAM | loop closure (waypoint) | RL + active exploration + adaptive TEB + active LC | No | No | No | active exploration toward LC waypoints (RL/TEB) | Yes (RL/TEB) | Yes | No |
| **Exploration with active loop closing: trade-off** (Lehner et al., IROS 2017) | 2017 IROS | 3D | 3D graph SLAM | loop-closing location | utility = info gain vs LC benefit | No | No | No | revisit past locations for LC | Yes | Yes | No |
| **Active loop-closing for FastSLAM** (Stachniss et al., IROS 2004) | 2004 IROS | laser | FastSLAM (RB-PF) | goal pose for LC | uncertainty-based LC goal selection | No | No | No | navigate to goal for LC | No | Yes | No |
| **Active SLAM with 3D Submap Saliency** (Suresh et al., ICRA 2020) | 2020 ICRA | 3D (underwater) | submap iSAM | submap | uncertainty-driven revisitation vs exploration | No | Partial (submaps) | Partial | revisit salient submaps | Yes | Yes | No |
| **MA-SLAM** (Yin et al., 2511.14330) | 2025 arXiv | 2D LiDAR | Gmapping | (none — exploration) | DRL over structured map (visited regions + boundaries) | No | Yes (historical trajectory in structured map, for coverage) | No | explore frontier waypoints (no LC-focused revisit) | Yes (AOU projects to feasible boundary) | No LC focus | N/A |
| **A survey on active SLAM** (Placed et al., 2207.00254 / T-RO 2023) | 2022/2023 | — | — | — | taxonomy: utility-based, belief-space, RL | survey | survey | survey | survey | survey | survey | survey |

## 3. Boundary answers

### Q1 — 简单增加 "loop success probability" 是否已明显撞上已有工作？

**是，已明显撞上。** Probabilistic Active Loop Closure (Yin et al., ICRA 2024)
explicitly computes a probabilistic reward of getting a loop closure at any pose on the
pose graph (uncertainty reduction × success probability − travel cost) and selects the
argmax pose. Modelling "probability that a selected target yields a loop closure" is
therefore an occupied idea at the **selection** level. Any Phase 4 proposal whose main
claim is "model loop-success probability" would not clear the boundary.

### Q2 — "沿历史轨迹进行 loop revisit" 是否已被已有工作覆盖？

**部分覆盖。** At the *target-selection* level, using the historical pose graph to
choose where to revisit is covered by our own baseline (reliable-loop path = SLAM
pose-graph poses), by Lighthouses (revisit lighthouse keyframe clusters), and by
Probabilistic ALC (poses on the pose graph). At the *execution* level, Lighthouses is
the closest: it physically travels back to a lighthouse and performs an in-place
rotation to emulate a panoramic view, and its GGS planner traverses the convex hull of
keyframes in **both directions** explicitly because "views have directionality".
However, no found work re-traces a *continuous historical SLAM trajectory segment
through an already-selected loop vertex* as a *selective, bounded repair* — the
revisit in Lighthouses is unconditional (always rotate at lighthouses), and our
baseline's revisit is fixed (≤7 poses) and is exactly what Phase 3A showed to fail.

### Q3 — "selected loop 之后的 selective realization repair" 是否仍存在明确方法空间？

**是，仍存在明确方法空间。** The gap is the conjunction of four properties that no
found work combines:
1. **Per-selected-loop decision**: decide, for the *already chosen* loop vertex,
   whether the original baseline execution is realizable (hard gates from Phase 3A:
   history continuity/span, waypoint spacing, approach-vs-history tangent
   consistency) — rather than always executing one fixed revisit (baseline,
   Lighthouses) or only re-selecting targets (Probabilistic ALC).
2. **Bounded repair**: if not realizable, repair with a *bounded* history-trace
   segment (max distance / max waypoints) — Phase 3A showed Always-Trace is
   over-revisiting (extra +22–28 waypoints per loop and S-reference regression).
3. **Online accepted-closure early stop** using only real SLAM loop-closure events —
   no found work terminates the repair trajectory upon an accepted closure.
4. **Easy-loop protection**: avoid degrading loops that would close anyway — Phase 3A
   demonstrated regression (seed21001 v26 coarse 0.657→0.493); no found work addresses
   non-monotonicity of revisit extension.

### Q4 — 最窄、最安全的创新边界是什么？

Keep the entire existing pipeline fixed (prior graph, TSP, D-opt loop selection, Karto
thresholds, frontier planner, SLAM backend) and add **only a post-selection execution
layer** for an already-selected loop vertex:

1. Realizability check (transparent hard gates, no ML, no learned scoring);
2. If gate fails → bounded history-trace repair (finite max distance/waypoints, forward
   vs reverse direction selection);
3. Online accepted-closure early stop (real SLAM closure event only);
4. Otherwise → original baseline execution.

This is the narrowest boundary: it is *not* loop-selection, *not* probability
modelling, *not* an unconditional history revisit, and *not* a strategy redesign.
Safety argument vs Phase 3A: gates are derived from Phase 3A data (history continuity
drives chain persistence; dense re-traversal lifts coarse response), and the early stop
bounds the regression risk that Always-Trace exhibited.

## 4. Honest limitations of this review

- Probabilistic ALC full text could not be retrieved (PDF fetch failed); its row is
  abstract-level. Its execution details (whether it adapts after selection, stops on
  closure) are marked "not stated in AB".
- Loop-Aware Exploration Graph, A3RGB-D, Zhang et al. ICRA 2022, Lehner 2017, Stachniss
  2004, Suresh 2020 are abstract-level rows; they are included for boundary completeness
  but not deeply read.
- The boundary claim rests on the *combination* of properties in Q3, which no found
  abstract/full-text describes; if a deeper read of Probabilistic ALC or a not-yet-found
  paper describes per-loop selective bounded repair with early stop, the Q3 claim must
  be narrowed.
