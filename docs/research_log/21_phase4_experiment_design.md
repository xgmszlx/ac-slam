# Phase 3B: Phase 4 Experiment Design (design only — no batch runs)
# Revised in Phase 4A (spec §20) after the gate redesign and the literature correction.

Date: 2026-08-23 (rev. 2026-08-23)

## 1. Objective

Evaluate the Selective Realization-Aware method (spec `20_...`, redesigned gate in
`22_...`) against Original and Always-Trace on the same map3 protocol, then (only if
the Phase 4 gate passes) extend to other maps.

## 2. Conditions (first round, map3 only)

- **A — Original Graph-Based**: current baseline (`oracle_mode=0`), = Phase 2C runs.
- **B — Always-Trace Oracle V1**: Phase 3A oracle (`oracle_mode=1`). **Explicit status:
  mechanism upper-bound / stress-test**, NOT a normal competitor — it shows what
  unbounded dense re-traversal can achieve and at what cost (Phase 3A: +22–28
  waypoints/loop, S-reference regression). Existing Phase 3A runs are reused as B.
- **C — Proposed Selective Realization-Aware**: `oracle_mode=2` (redesigned gate G1′
  span<4.0 m config-grounded; bounded repair ≤12 m / ≤24 wp / 0.5 m densify;
  forward/reverse; early stop on attributable `/Mapper/loop_closed`; default off).

Seeds: same 5 seeds 21001–21005, same map3/start/TSP; TSP must remain byte-identical
to Phase 2C for each seed (loop selection held fixed).

## 3. Primary metrics

1. **Active Loop Acceptance Rate** = `accepted_active_loops / executed_active_loops`
   (diagnostics ACCEPTED records inside loop windows, cross-checked 1:1 with
   "Add one Loop" callbacks and `/Mapper/loop_closed` events).
2. **Active Loop Overhead** — reported per active loop as
   - active-loop **distance** (m) and
   - active-loop **time** (sim s),
   and as totals over the run.

## 4. Secondary metrics

- **Extra Cost per Accepted Closure** — only reported when accepted count > 0:
  (total active-loop distance of the condition − baseline active-loop distance) /
  accepted active loops.
- **Incremental Distance per Additional Accepted Closure**, when `N_condition >
  N_original`:
  `(D_condition − D_original) / (N_condition − N_original)`
  where D = total active-loop distance and N = accepted active loops. This quantifies
  the marginal cost of each extra closure gained by C (or B).
- C3 count/rate, D1 count/rate (per-loop dominant vote from diagnostics)
- valid-chain persistence (fraction of keyscans with chain ≥ 4; longest consecutive)
- best coarse response, best fine response per loop
- total exploration distance/time
- APE / RPE (trajectory_gt vs trajectory_slam, evo)
- **Regression Rate** (defined): for loops that in the same seed/vertex were accepted
  or near-gate in Original (V0), the fraction that fail (or cost > 2×) under C. This is
  the Phase 3A S-reference concern made quantitative. Reported separately for
  gate-passed (no-repair) vs repaired loops.

## 5. Run protocol

- Reuse Phase 2C (A) and Phase 3A oracle (B) raw runs where available; run C fresh.
- Early stop after the last target loop per run is allowed for C (diagnostics flushed
  per record); for completeness of APE/RPE, prefer full runs for the seeds used in the
  primary analysis.
- Timing probe before each batch + per-run wall/sim recorded (Phase 3A protocol).
- Preserve raw runs; mark environmental failures INVALID_ENVIRONMENT; no silent retries.

## 6. Phase 4 gate (stop conditions)

Proceed to other maps **only if** C vs A on map3 shows:
1. accepted active-loop rate clearly higher (descriptive; report counts + per-loop
   tables, no cherry-picking),
2. extra distance/time clearly lower than B (Always-Trace),
3. no systematic Regression Rate (easy/near-gate loops under A do not systematically
   fail under C; S-reference s21001 v26 must not regress).

If any of the three fails → REDESIGN (e.g., relax/strengthen gates, change caps) or stop
adding modules. No threshold tuning by exhaustive map3 search; only the small
sensitivity grid in spec §15.

## 7. Planned ablations (from spec §15)

C vs C-without-G1, C-without-G2, C-without-early-stop; parameter sensitivity grid
T_span {3.5,4.5,5.5}, T_yaw {0.52,0.78,1.04}, L_repair_max {8,12,16}. Each ablation is
a small run set; run only if the primary gate passes.

## 8. Confounds to record

- wall/sim per run (environmental ~5×, no sudo)
- run-to-run nondeterminism (A and C are separate runs; same TSP; report per-seed
  waypoint/timing differences like Phase 3A Audit 3)
- Karto threshold / prior / TSP / D-opt unchanged (assert in manifest)
