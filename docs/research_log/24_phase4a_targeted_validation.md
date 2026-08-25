# Phase 4A Stage D: Targeted Selective-Execution Validation

Date: 2026-08-23 (runs) — updated after Case 3

## 0. Context and critical finding first

Stage C (closure-event 1:1) was validated in a **diagnostics-OFF** positive
control (trial 9): Karto internal accepted ("Add one Loop closure.", t=931.1)
== published `/Mapper/loop_closed` event (`PHASE4A_LOOP_CLOSED seq=1
current_scan=624 chain 28-31`, same timestamp) — 1:1, attribution ok, no
duplicates, seq contiguous, zero delay.

**The per-loop-search loop diagnostics (Phase 2C) are confirmed to PERTURB
closure acceptance**: with `enable_loop_diagnostics:=true`, zero accepted
closures in every trial (Phase 2C 5/5, Phase 4A trials 5-8, Case 1); with it
OFF, closures fire (Phase 2B 3/3; trial 9). The observation-only diagnostics
append to a file on every loop search, which perturbs the mapper on this slow
host. **All Stage D targeted cases therefore run with diagnostics OFF.**

## 1. Purpose

Validate the minimal Selective Realization-Aware execution (oracle_mode=2):
(1) the redesigned G1' prototype heuristic (contiguous history span < 4.0 m;
configuration-inspired, not a theoretically derived Karto threshold) triggers REPAIR only
when the baseline loop's span is short; (2) the bounded repair re-traces the
contiguous pose-graph segment (≤ 12 m / ≤ 24 wp, 0.5 m densify); (3) the
early-stop on an attributable accepted closure (PHASE4A_EARLY_STOP); (4) the S
reference (span ≥ 4.0) is NOT repaired (regression guard).

## 2. Method

`tools/run_phase4a_targeted.py --case N --no-diagnostics`: launches
oracle_mode=2 with span_gate=4.0, max_len=12.0, max_wp=24, densify=0.5,
dir_lambda=1.0; records gate decisions, repair paths, early-stop, and the
accepted-closure event (callbacks vs events). Diagnostics OFF.

## 3. Results

### Case 1 — seed 21003, D1-rescue target v15 (ran WITH diagnostics; gate finding valid)

| field | value |
|---|---|
| gate decision (v15) | **NO_REPAIR** — span 4.88 m ≥ 4.0 |
| repair | none (V0 path, 6 waypoints) |
| closure | 0 (run invalid for closure evidence: diagnostics ON) |

**Gate finding (valid regardless of diagnostics)**: the design assumed v15 span
~3.92 < 4.0 (REPAIR), but the online span in this run was 4.88 ≥ 4.0 →
NO_REPAIR. Same nominal loop, span 3.92↔4.88 across runs — **direct live
confirmation of the span boundary instability** flagged in the Stage B gate
audit. The gate itself behaved exactly as designed (span ≥ 4.0 → NO_REPAIR).

### Case 2 — seed 21005, C3-opp target v26 (diagnostics OFF)

Loop set this run = {v15, v26}.

| loop | gate decision | span | action | waypoints | closure |
|---|---|---|---|---|---|
| v15 (D1-like) | **REPAIR** | 3.93 m | 12.11 m dense trace (24 wp cap) | 24 executed | 0 |
| v26 (C3-opp target) | **NO_REPAIR** | 4.12 m | original V0 path | 5 | 0 |

**Findings**:
- The repair mechanism fired correctly: v15 span 3.93 < 4.0 → REPAIR with a
  12.11 m / 24-waypoint dense re-trace of the contiguous pose-graph segment;
  all 24 waypoints were executed. No PHASE4A_EARLY_STOP (no attributable closure
  fired during the trace).
- v26's span was 4.12 (design assumed 3.63) → NO_REPAIR — again the span
  boundary is run-variable; the gate still decided consistently (span ≥ 4.0 →
  NO_REPAIR).
- No accepted closure fired during the repair trace (run-to-run variability;
  the same loop's trace in the diagnostics-OFF positive control did fire a
  closure at a different seed).

### Case 3 — seed 21001, S reference v26 (diagnostics OFF) — FULL END-TO-END

Loop set this run = {v15, v11, v8, v26}.

| loop | gate decision | span | action | waypoints | closure |
|---|---|---|---|---|---|
| v15 | **REPAIR** | 3.97 m | 12.17 m dense trace | 24 | — |
| v11 | **REPAIR** | 3.87 m | 12.49 m dense trace | 24 | — |
| v8  | **REPAIR** | 1.40 m | 9.94 m dense trace | 24 | **closure accepted at wp 19/24 → EARLY_STOP** |
| v26 (S reference) | **NO_REPAIR** | 4.83 m | original V0 path | — | — |

**Complete selective-execution chain demonstrated (sim 1150.3):**
1. v8 (span 1.40 < 4.0) → REPAIR, 9.94 m / 24-wp dense trace of the contiguous
   pose-graph segment.
2. During the trace, Karto ACCEPTED a closure: `Add one Loop closure. 1 loops
   have been added.` at sim 1150.3 (current scan 633 ↔ early-history chain
   17-22).
3. The `/Mapper/loop_closed` event was published at the SAME sim time:
   `PHASE4A_LOOP_CLOSED seq=1 current_scan=633 chain_start=17 chain_end=22`.
   closure_event_validation.json: **one_to_one=true, attribution_ok=true,
   no_duplicates=true, seq_contiguous=true, max_callback_to_event_delay_s=0.0**.
4. MyPlanner attributed the closure to the active loop (`PHASE4A_CLOSURE_ATTRIBUTED`)
   and **early-stopped the remaining repair at waypoint 19 of 24**
   (`PHASE4A_EARLY_STOP vertex=8 at_waypoint=19 of 24`).

**S-reference regression guard confirmed**: v26 span 4.83 ≥ 4.0 → NO_REPAIR;
 the S reference loop is NOT over-repaired.

## 4. Interpretation

- The redesigned gate G1' behaves consistently with its mechanism: short-span
  loops (3.93, 3.97, 3.87, 1.40) are repaired; span ≥ 4.0 loops (4.12, 4.83,
  4.88) are not — across all three cases and seven gate decisions.
- The span itself is **run-dependent** (3.92↔4.88 for 21003-v15; 3.63-design
  vs 4.12-online for 21005-v26), i.e., the same nominal loop can flip across
  runs near the 4.0 boundary. This is inherent to computing the span from the
  run's own pose graph and is documented (not hidden).
- The repair path construction and execution are correct, and **the full
  end-to-end chain "short span → REPAIR → dense trace → Karto accepts closure
  → event published 1:1 (zero delay) → attribution to the active loop →
  EARLY STOP" was demonstrated in Case 3 (v8)**. Whether a closure is accepted
  during a given repair is subject to Karto's run-to-run match-response
  variability (Case 2's repair and Case 3's v15/v11 repairs did not cross the
  threshold; v8's did).
- Diagnostics must stay OFF for any run that needs closure acceptance (they
  perturb the mapper); the observation-only `/Mapper/loop_closed` event is the
  non-perturbing signal for Phase 4B.

## 5. Honest limitations

- Case 1 was run before the diagnostics-perturbation discovery, so its closure
  evidence is invalid (but its gate decision is a valid finding).
- Only Case 2's v15 exercised the repair path; Case 2's intended C3 target
  (v26) turned out NO_REPAIR this run.
- The closure-acceptance variability means targeted-case outcomes are not
  stable run-to-run on this host.
