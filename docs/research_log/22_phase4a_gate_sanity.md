# Phase 4A Stage B: Gate Sanity Audit

Date: 2026-08-23 · tools: `audit_phase4a_gates.py`, `audit_phase4a_online_g2.py`
· outputs: `results/phase4a/gate_audit/`

## 1. What was audited

The Phase 3B gates:
- G1: contiguous history span `history_path_length_m < 4.5 m`
- G2: heading consistency `yaw_diff_median_rad > 0.78 rad`
(REPAIR if G1 OR G2; else NO_REPAIR, i.e., keep original execution).

Audit: (a) descriptive sensitivity over small mechanism-reasonable grids
(T_span ∈ {3.0,…,6.0}, T_yaw ∈ {0.5,…,1.2}) — **no threshold optimization**;
(b) leave-one-seed-out; (c) gate formulation comparison (A span+yaw / B
history-continuity support / C span-only / D yaw-only); (d) yaw definition audit.

## 2. Gate sensitivity (results/phase4a/gate_audit/gate_decision_matrix.csv, threshold_stability.csv)

- Stable-REPAIR loops (repair_frac=1.0 across the grid): all short-span / high-yaw
  failures (s21001l1,l2,l3; s21002l1; s21003l1,l3; s21004l1,l2,l5; s21005l1,l2,l5).
- Stable-NO_REPAIR loops (repair_frac 0.14–0.43): long-span, good-yaw failures
  (s21002l2,l3; s21003l4; s21004l3; s21005l3).
- **Threshold-sensitive loops (repair_frac 0.52–0.71)**: exactly the cases the
  Phase 3B thresholds were chosen around:
  - the S reference s21001l4 (span 4.81, yaw 0.561): repair_frac **0.524** — its
    decision flips from NO_REPAIR to REPAIR as soon as T_span ≥ 5.0 or T_yaw ≤ 0.5;
  - the medium-yaw D1 s21004l4 (yaw 0.836) and s21005l4 (yaw 0.824): repair_frac
    0.714 / 0.643 — right at the 0.78 boundary.

Conclusion: the current threshold VALUES (4.5, 0.78) are **case-informed heuristics**
pinned by the single S reference from below (T_span ≤ 4.81, T_yaw ≥ 0.561) and by two
D1 targets from above (T_yaw ≤ 0.836). They are **not mechanistically validated
thresholds**.

## 3. Leave-one-seed-out (results/phase4a/gate_audit/leave_one_seed_out.csv)

| held-out seed | S in train | C3 span range | D1 span range | failed caught by current gates |
|---|---|---|---|---|
| 21001 (the only S) | **0** | (1.39, 6.04) | (3.92, 5.90) | 12/17 |
| 21002 | 1 | (1.39, 4.83) | (3.92, 5.90) | 14/17 |
| 21003 | 1 | (1.39, 6.04) | (4.82, 5.81) | 12/16 |
| 21004 | 1 | (1.39, 6.04) | (3.92, 5.90) | 11/15 |
| 21005 | 1 | (1.39, 6.04) | (3.92, 5.90) | 11/15 |

**Answer to the spec question:** without seed 21001 (the only original S), there is
**no independent mechanism basis for choosing 4.5 m / 0.78 rad**:
- C3 spans span (1.39, 6.04) and D1 spans (3.92, 5.90) — a single span threshold cannot
  separate failures from nothing (there is no success to bound it);
- the yaw threshold similarly has no upper/lower anchors without S and the two
  near-0.78 D1.

**Written explicitly: the current thresholds are case-informed heuristics, not
mechanistically validated thresholds.**

## 4. Gate formulation comparison (results/phase4a/gate_audit/gate_formulations.csv)

On the 21-loop retrospective (descriptive; no fitting):

| Formulation | REPAIR count | Protects S | Catches the 3 oracle-rescued D1 targets (s21003l1, s21004l4, s21005l4) |
|---|---|---|---|
| A span(4.5)+yaw(0.78) | 15/21 | ✓ | ✓ all 3 |
| B history-support (wp<4 or span<4.0) | 10/21 | ✓ | only s21003l1 (misses s21004l4, s21005l4) |
| C span-only (4.5) | 12/21 | ✓ | only s21003l1 |
| D yaw-only (0.78) | 14/21 | ✓ (at 0.78) | ✓ all 3 |

A is the only formulation that both protects S and catches all three oracle-rescued
D1 targets. But A's VALUES are case-informed (§2, §3). B is the simplest
configuration-inspired prototype heuristic (using the numbers 4 and 1.0, without a
dimensional derivation) but misses the medium-span D1.
C and D each miss part of the mechanism.

**Mechanism mapping (backend-aligned, not label-tuned):**
- C3 = candidate chain too short → the contiguous history SUPPORT (span) is the
  mechanism cue (chains need ≥ LoopMatchMinimumChainSize=4 linked scans ≈ 4×1.0 m).
- D1 = coarse response < 0.60 → scan-content/viewpoint at candidates; BQ2 showed this
  is NOT trajectory-predictable, and the online yaw cue is not stable (see §5).

## 5. Yaw audit

**Definition of `yaw_diff_median_rad` (from `tools/analyze_phase3a.py`):** for every GT
sample of the loop's actual trajectory, `|wrap(actual_heading − heading_of_nearest_
pre_loop_SLAM_pose)|`, then median. Source = GT heading during the loop; reference =
nearest historical SLAM pose heading; frame = mixed GT/SLAM. It represents
"viewpoint consistency of the actual revisit vs its nearest history" — it is **not**
the loop-start approach heading, **not** the history tangent, and it is **offline /
evaluation-only (uses GT)**.

**Online replacement (SLAM-only, computable at loop start)** = `|wrap(robot SLAM
heading at loop start − history tangent at closest pose)|`, with history tangent from
(a) the V0 path direction or (b) the local pre-loop SLAM trajectory tangent.
Validation vs the offline cue on 21 loops
(`results/phase4a/gate_audit/online_g2_validation.csv`):

| online G2 source | binary agreement with offline (>0.78) |
|---|---|
| V0-path direction | 16/21 (76%) |
| local SLAM-trajectory tangent | 12/21 (57%) |

**Fatal case for G2 as a repair trigger:** the S reference s21001l4 has offline yaw
0.561 (< 0.78, protected) but online G2 = 0.804 (pathdir) / 2.333 (traj tangent)
(> 0.78 → would be REPAIRED). The robot's loop-start approach heading differs from the
history tangent even though its actual natural traversal during the loop is
history-consistent — the loop-start heading is not predictive of the loop's heading
consistency. For a 2D LiDAR + Karto system (360° scans) the viewpoint penalty is also
weaker than for narrow-FoV visual SLAM, and the 45°/0.78 value is not novel (used as a
key-waypoint-selection criterion in Remote Sensing 2022, a different role).

**Conclusion (per spec §7): demote yaw from a repair trigger** to a
**direction-selection cue** (choose forward/reverse repair traversal by heading
alignment at the segment entry) and a **secondary diagnostic**. It is not a stable
online realizability cue.

## 6. Gate decision

**GATE_REDESIGN_REQUIRED (minimal, within this phase — no new experiments beyond the
audit).**

Redesigned gate (simpler prototype rule; not a theoretical backend threshold):
- **G1′ (primary repair trigger) — history-continuity support**: repair if the
  contiguous history span at the selected loop vertex `span < 4.0 m`. The numerical
  value is configuration-inspired, but `LoopMatchMinimumChainSize` is a scan count
  and does not dimensionally derive a distance threshold. Protects the S
  reference (span 4.81 m > 4.0). Catches the short-history failures (all short-span
  C3 + the short-span D1 s21003l1 that Phase 3A rescued).
- **G2 (yaw)**: demoted to direction-selection cue + secondary diagnostic (not a
  repair trigger).
- Retrospective behavior of G1′ alone on the 21 loops: REPAIR on the 10 short-history
  loops, NO_REPAIR on the S + long-history loops. Documented limitation: the
  medium-history D1 (s21004l4 span 4.82, s21005l4 span 5.01) are not repaired by the
  selective method (their rescue required the Always-Trace density, which is exactly
  what the selective method avoids). Phase 4B's Always-Trace (B) condition provides the
  upper bound for these.

This redesign is a simple, single-feature prototype gate (no ML, no logistic
regression, no accepted-label optimization). Its 4.0 m value is frozen for testing,
not claimed as a Karto-derived or mathematically justified threshold.
