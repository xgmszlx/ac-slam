# Phase 4A Final Review

Date: 2026-08-24 (session 2026-08-23 ~11:00 → 08-24 01:15)

> **Phase 4B terminology correction (2026-08-25):** the 4.0 m span gate is a
> configuration-inspired lightweight prototype heuristic. It is not theoretically
> or dimensionally derived from Karto: `LoopMatchMinimumChainSize` is a scan count.
> This correction changes no Phase 4A code, threshold or result.

## A. Repository state

| repo | HEAD | status |
|---|---|---|
| main (`/home/wcqw/ac-slam`) | `14392db` | Phase 4A complete; all docs 22-25 + results committed |
| baseline `Graph-Based_SLAM-Aware_Exploration` | `7c20c3c` | Phase 4A oracle_mode=2 committed; working tree clean (only run outputs untracked) |
| `dependencies/navigation_2d` | `062283d` | Phase 4A observation-only `/Mapper/loop_closed` committed |

Phase 4A artifacts: `results/phase4a/{gate_audit,closure_event_validation,targeted_cases}/`,
docs `22_phase4a_gate_sanity.md`, `23_phase4a_implementation_audit.md`,
`24_phase4a_targeted_validation.md`, this review. No stray ROS processes.

## B. Corrected literature boundary

`18_realization_aware_literature_boundary.md` §5 corrected the nearest-neighbour
boundary. **The contribution is NOT "follow a segment of the previous trajectory"
(history revisit)**: Graph-Based SLAM-Aware Exploration already does that, so that
idea is not ours. The narrowest defensible innovation is **post-selection,
failure-conditioned, realization-aware adaptation**: after the baseline planner
SELECTS a loop, a realization-aware layer decides whether to adapt the execution
(gate), and only for failure-prone short-span loops applies a bounded history
re-trace. The online-gate redesign (Stage B/D) removes the case-informed
thresholds that were the residual overfitting risk.

## C. Gate sanity

The original gate (G1 span<4.5, G2 yaw>0.78) was **case-informed**:
- S reference pins it (repair_frac for S was 0.524 under span<4.5 across the grid —
  the S reference would be repaired ~half the time).
- s21004l4 / s21005l4 sit right on the 0.78 yaw boundary.
- Online yaw G2 is unstable vs the offline oracle (agreement only 16/21 pathdir,
  12/21 traj tangent) and misfires on the S reference (online 0.804/2.333 vs
  offline 0.561).

Verdict: **REJECT the old gate; adopt G1' = contiguous history span < 4.0 m** as a
frozen, configuration-inspired prototype heuristic. It is not a theoretical Karto
threshold and is not claimed optimal. Yaw is demoted to a direction-selection cue.
Gate audit CSVs: `gate_decision_matrix.csv`, `threshold_stability.csv`,
`leave_one_seed_out.csv`, `gate_formulations.csv`, `online_g2_validation.csv`.

## D. Final online gate

Only online inputs: the planner's pose graph at loop-selection time.
`span = path length of the 7-pose V0 loop path`; REPAIR if `span < 4.0`, else
NO_REPAIR (original V0 path). Live evidence across the 3 targeted cases (7 gate
decisions): spans {4.88, 3.93, 4.12, 3.97, 3.87, 1.40, 4.83} — every span < 4.0
was REPAIRED, every span ≥ 4.0 was NO_REPAIR. **Consistent with the mechanism.**

Run-variability is real and documented: the same nominal loop's span varies
(21003-v15: 3.92 design ↔ 4.88 online; 21005-v26: 3.63 design ↔ 4.12 online),
so a loop near the 4.0 boundary can flip across runs. This is inherent to
computing the span from the run's own pose graph.

## E. Accepted closure event validation (Stage C)

**YES — 1:1 validated, attribution RELIABLE** (2 independent accepted closures,
both diagnostics-OFF):
1. Positive control trial 9: `Add one Loop closure.` (t=931.1) ↔
   `PHASE4A_LOOP_CLOSED seq=1 current_scan=624 chain 28-31` (same timestamp).
2. Targeted Case 3 v8: `Add one Loop closure.` (sim 1150.3) ↔
   `PHASE4A_LOOP_CLOSED seq=1 current_scan=633 chain 17-22` (same timestamp).

Both: **one_to_one=true, attribution_ok=true, no_duplicates=true,
seq_contiguous=true, max_callback_to_event_delay_s=0.0**.

**CRITICAL instrument finding**: the per-loop-search loop diagnostics
(Phase 2C) **perturb closure acceptance** — with diagnostics ON, zero accepted
closures in every trial (Phase 2C 5/5, Phase 4A trials 5-8, Case 1); with them
OFF, closures fire (Phase 2B 3/3, trial 9, Case 3). The observation-only
`/Mapper/loop_closed` event does NOT perturb. **Phase 4B must run with loop
diagnostics DISABLED and use the event as the accepted-closure signal.**

Honest record: the natural-closure attempts (seed_21003_v1 INCONCLUSIVE, fine
0.687 vs 0.7; seed_21001_v0 INCONCLUSIVE_NO_CLOSURE) and Case 1 (NO_REPAIR) are
preserved as-is; they predate/are invalidated by the diagnostics finding.

## F. Implementation invariance

- `oracle_mode=0` returns exactly the original V0 path (unit-tested).
- Forbidden modules untouched: prior graph loading, TSP/Concorde, D-opt /
  loop-edge selection, frontier planner, Karto matcher thresholds and candidate
  logic, SLAM optimization. GT never read by the method.
- Only additions: `LoopClosureEvent.msg`, observation-only `LoopClosureObserved`
  emission in the accepted path, `/Mapper/loop_closed` publisher,
  `ReliableLoop.srv.selective_repair`, `oracle_mode=2` branch in
  `handle_reliable_loop`, MyPlanner subscriber + early-stop, prototype params.
- 17/17 deterministic unit tests pass (`tools/test_phase4a_selective.py`).
- Full audit: `23_phase4a_implementation_audit.md`.

## G. Targeted cases table (all oracle_mode=2, span_gate=4.0)

| case | seed | loops this run | gate decisions | outcome |
|---|---|---|---|---|
| 1 D1-rescue (target v15) | 21003 | {v15} | v15 span 4.88 → **NO_REPAIR** | V0 path; 0 closure (also invalidated by diagnostics-ON) |
| 2 C3-opp (target v26) | 21005 | {v15, v26} | v15 span 3.93 → **REPAIR** 12.11m/24wp (executed); v26 span 4.12 → **NO_REPAIR** | repair executed fully; 0 closure (run variability) |
| 3 S-ref (target v26) | 21001 | {v15, v11, v8, v26} | v15 3.97 REPAIR, v11 3.87 REPAIR, v8 1.40 REPAIR, **v26 (S) 4.83 NO_REPAIR** | **v8 repair → closure accepted (scan 633↔17-22) → event 1:1 zero-delay → attributed → EARLY_STOP wp 19/24** |

Case 3 is the full end-to-end demonstration of the method: short-span gate →
bounded dense re-trace → Karto accepts a closure with early history → the
accepted-closure event is published 1:1 with zero delay → MyPlanner attributes
it to the active loop and early-stops the remaining trace. The S reference is
correctly NOT repaired (regression guard).

## H. Gates A-F

- **A. Corrected literature boundary**: PASS (contribution = post-selection
  failure-conditioned adaptation, not history revisit).
- **B. Gate overfitting check**: PASS for the historical targeted sanity check (old
  case-informed gate rejected; G1' frozen as a lightweight prototype heuristic).
- **C. Minimal selective execution implemented**: PASS (oracle_mode=2, default
  off, bounded repair, early-stop; unit-tested).
- **D. Accepted-closure online attribution**: PASS (1:1, attribution, no dup,
  zero delay; 2 independent closures). Conditional: diagnostics OFF.
- **E. Targeted cases**: PASS (gate consistent across 7 decisions; repair
  mechanism works; full chain demonstrated; S-ref guard confirmed).
- **F. Implementation invariance / honesty**: PASS (oracle_mode=0 unchanged;
  failed attempts preserved; diagnostics perturbation documented).

## I. Remaining risks

1. **Closure acceptance is run-to-run variable** on this host (matcher
   responses hover near thresholds: coarse ≤ 0.555 in one run, fine 0.687 in
   another). Phase 4B's PRIMARY metrics (Active Loop Acceptance Rate) are
   exactly this quantity, so the experiment design already measures it; expect
   moderate variance and plan for repeats.
2. **Span near the 4.0 boundary can flip across runs** (documented live).
   Phase 4B must log per-run spans and treat decisions near 4.0 as
   boundary-sensitive.
3. **Loop diagnostics must stay OFF** for any run needing closure acceptance;
   the per-run diagnostics JSONL is unavailable in that mode (use the event).
4. Repair bounds (12 m / 24 wp / 0.5 m densify) are prototype defaults, not
   claimed optimal (documented).
5. Case 2's intended C3 target turned NO_REPAIR this run (span 4.12); the C3
   repair case was instead exercised by Case 3's v15/v11/v8 and Case 2's v15.
6. Machine is ~4.6x slower than the Phase 2B era; wall-clock budgets must be
   scaled (this session's runtime confirms: exploration ~60-90 min, not ~20).

## J. Decision

**PROCEED_TO_PHASE4B**, with mandatory conditions:
1. Run Phase 4B with `enable_loop_diagnostics:=false`; use the observation-only
   `/Mapper/loop_closed` event as the accepted-closure signal (diagnostics
   perturb acceptance — confirmed).
2. Follow the doc-21 protocol: PRIMARY 1 = Active Loop Acceptance Rate, PRIMARY 2
   = Active Loop Overhead; Always-Trace (V1) as mechanism upper-bound/stress-test;
   oracle_mode=0 as baseline.
3. Log per-run gate spans and wall/sim ratios; treat boundary decisions
   (span ≈ 4.0) as sensitive.
4. Do NOT change Karto thresholds; do NOT use GT in the method; oracle default
   off.

STOP here. Phase 4B is NOT entered in this session.
