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
| **Probabilistic Active Loop Closure** (Yin et al., ICRA 2024) | 2024 ICRA | depth (narrow-FoV) | keyframe pose graph vSLAM | keyframe cluster τ (lighthouse or passive cluster) | reward R= −ct·l + PLC·ΔU; branch-and-bound argmax | **Yes** (PLC = tanh(view)×exp(−rel.uncertainty²)) | Partial (keyframes of the cluster; no trajectory-segment re-traversal) | **Yes** (drive to τ*, 360° in-place rotation) | drive to target + in-place 360° rotation; path-coverage refinement stage afterwards | Yes (refinement stage) | Yes | No per-revisit |
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

- Loop-Aware Exploration Graph, A3RGB-D, Zhang et al. ICRA 2022, Lehner 2017, Stachniss
  2004 are abstract-level rows; they are included for boundary completeness but not
  deeply read.
- The boundary claim rests on the *combination* of properties in Q3, which no found
  abstract/full-text describes; if a deeper read reveals a paper that describes
  per-loop selective bounded repair with early stop, the Q3 claim must be narrowed.

## 5. Corrected nearest-neighbor boundary before implementation (Phase 4A)

Re-verified the nearest neighbors with primary sources. Corrections to §2–§3:

### A. Graph-Based SLAM-Aware Exploration (our baseline, RA-L 2024) — history revisit is in the paper

Original text (Sec. V-A "Hierarchical Autonomous Exploration"):

> "Active loop-closing: if current vertex is a loop-closing vertex, the robot will
> follow a segment of its previous trajectory to establish loop closures in current
> region."

**Conclusion: history-trajectory revisit itself is NOT a contribution of this project.**
It is already the baseline's designed behavior (and the reliable-loop path in the code
implements it as ≤7 SLAM pose-graph poses). Our claimed gap is not "revisit history";
it is the *post-selection, failure-conditioned adaptation* of that already-existing
revisit.

### B. Active SLAM using 3D Submap Saliency for Underwater Volumetric Exploration (ICRA 2020) — top similarity nearest neighbor

- Revisit execution replays a **cached/historical path**: the planner finds the closest
  node on the cached pose/trajectory graph (`GETCLOSESTNODE`), traces back through the
  pose tree (`RETRACETREE`), interpolates poses along it (`INTERPOLATE`), and builds a
  smooth revisit trajectory (`GETREVISITTRAJECTORY`) that the robot then executes. This
  is a historical-trajectory replay mechanism, methodologically very close to our V1 /
  selective revisit.
- Evidence: abstract (balancing volumetric exploration vs revisitation to reduce pose
  uncertainty) + code function names as provided in the Phase 4A spec; the full PDF was
  not retrievable from the CMU/author mirrors at review time. Row is upgraded to a
  **highest-similarity nearest neighbor** in §2.
- Difference from our method: their revisit target selection is saliency/uncertainty
  driven and the revisit is a full replay; no per-loop realizability gate, no bounded
  corrective cap keyed to "historical support sufficient vs insufficient", no acceptedclosure early stop, no easy-loop preservation.

### C. Lighthouses & Global Graph Stabilization (ICRA 2023) — confirmed

Lighthouse construction = in-place rotation generating a spatially clustered set of
keyframes (panoramic view emulation); LH-ALC drives the robot back to a lighthouse and
rotates in place; orientation/viewpoint is explicitly handled ("views have
directionality"); GGS traverses the convex hull of keyframes in both directions. The
revisit is **unconditional** (always rotate at lighthouses), not gated on whether the
selected target's history support is sufficient.

### D. Probabilistic Active Loop Closure (ICRA 2024) — correction of "selection-level" simplification

Full text retrieved (amazon.science PDF). The paper is NOT only selection-level:
- **PLC**: `PLC(pτ) = tanh(cv·sv(pv)) · exp(−(l⁻(p′r,pv,G′))²/c²l)`; for a keyframe cluster
  `PLC(pτ) = 1 − Πᵢ(1 − PLC(pvi))`. Loop closure is explicitly modeled as a
  probabilistic event at keyframe clusters.
- **ALC candidate τ** = a cluster of keyframes (from proactive lighthouses + passive
  downsampled keyframe neighborhoods) with representative pose, view scores, PLC, ΔU,
  reward `R(τ) = −ct·l(pr,pτ,M) + PLC·ΔU`; target selection via branch-and-bound.
- **Execution**: "The ALC planner guides the robot to target τ*, rotating 360° there
  to enhance loop closure chances for robots with limited field of view." After
  exploration, a **path coverage refinement** stage further stabilizes the pose graph.
- So: drive-to-target + 360° in-place rotation + refinement stage. This is closer to
  Lighthouses than to "selection-only". It still does **not** do a bounded corrective
  re-traversal of the selected target's historical trajectory segment, and does **not**
  early-stop on an accepted closure.

### E. Perception-Aware Planning for Active SLAM in Dynamic Environments (Remote Sensing 2022)

NBVP next-best-view + Active Loop Closing Planner (ALCP). The paper uses **yaw change
> 45°** in key-waypoint selection (per the Phase 4A spec; full text behind MDPI
anti-bot, marked AB-level). The 45° there is a *key-waypoint selection* criterion in
ALCP, **not** a realizability gate for an already-selected loop. Consequence: we must
**not present 0.78 rad (≈45°) as a newly introduced mechanism threshold**; our G2 is a
different role (post-selection realizability gate for an already-selected loop) but the
number itself is not a novel threshold value.

### F. Narrowest claim (revised)

> The method does NOT introduce trajectory revisiting itself.
> The investigated gap is: post-selection, failure-conditioned adaptation of an
> already-selected informative active-loop action, where the execution policy preserves
> the original action when historical support appears sufficient, and applies only a
> bounded corrective revisit otherwise.

No occurrence of "first", "first-ever", "no prior work", or "novel trajectory revisit"
is claimed without direct evidence.
