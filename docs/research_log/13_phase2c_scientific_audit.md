# Phase 3A Stage A: Phase 2C Scientific Audit

Date: 2026-08-22

## Scope

This audit re-examines the Phase 2C scientific claims before any new experiment.
It verifies (1) whether the old→new taxonomy table can be called event-level
relabeling, (2) whether Gate A was validated, (3) the extent of run-to-run
nondeterminism between Phase 2A and Phase 2C, (4) the Stage timing limitation, and
(5) the quality of the instrumentation fields. The audit does not re-run anything.

## Repository state at audit time

| Repo | Branch | HEAD | Worktree |
|---|---|---|---|
| ac-slam (main) | `research/phase3a-revisit-oracle` (new) | `d9c869ce6255bd9b54012d949580e7daaa825ab2` | only `.vscode/` untracked |
| baseline | `master` | `547ea24dcf18d3108302f4fd15cea83565c2a2fa` | pre-existing untracked g2o/pyc artifacts |
| navigation_2d | `main` | `8ae4895a2666b54ad6fa42fc01a1b2912cd94a65` | clean |

## Audit 1 — Old → New taxonomy legitimacy

Facts (verified from data, not from the handoff):

- Phase 2B labels were computed from the **old Phase 2A runs** (results/phase2/map3_pairs).
- Phase 2C diagnostics were collected on **new re-runs** of the same seeds
  (results/phase2c/map3).
- Same seed ⇒ same Concorde TSP (SHA-256 identical, verified per seed).
- Same planned loop vertices (verified: loop vertex sequence is identical per seed).
- **But the execution differs**: per-seed waypoint counts differ
  (e.g., seed_21001 v11: 5 vs 3, v26: 7 vs 6; seed_21004 several differ), loop
  start/end sim times differ, and actual trajectories differ.

Therefore the Phase 2C "failure transition matrix" is a **replication-level
comparison** (same seed / same loop index / same planned-vertex replication), NOT an
event-level relabeling of the same physical loop event.

**Correction required in `12_phase2c_failure_mechanism.md`:**
- Replace the implication that "Phase 2B loop label X was proven wrong" with the
  supported statement: "Phase 2B's offline taxonomy has limited predictive power for
  the actual internal rejection mechanism observed in independent re-runs of the same
  planned loops." The new table is re-labelled as a replication-level evidence table.
- The per-loop C3/D1/S assignments in Phase 2C are direct Karto-internal evidence for
  the *new* runs only; they are not a retrospective relabeling of Phase 2A events.

Stage-A verdict on Audit 1: the C3/D1 internal rejection mechanisms are real for the
Phase 2C runs; the old→new comparison must be reframed as replication-level.

## Audit 2 — Gate A expression

Facts:

- The explicit Phase 2B-protocol positive control was **not** completed on this host
  (5 attempts; navigation timeouts and Stage slowdown; environmental).
- In the seed_21001 SLAM-aware run, Karto accepted a closure during an active loop and
  the structured diagnostics record (`ACCEPTED`, scan 679, coarse 0.657, fine 0.927)
  matched the "Add one Loop closure" callback 1:1 at sim 1297.7.

Conclusion: this validates the **ACCEPTED-path instrumentation** (a structured
diagnostics record is emitted exactly when Karto accepts, with full internals). It does
**not** validate an "explicit positive-control instrumentation" claim — no explicit
positive-control revisit was completed.

**Correction required:** Gate A should be stated as
"ACCEPTED-path instrumentation validated (1:1 via a real closure in a SLAM-aware run);
explicit positive-control validation incomplete (environmental blocker)."
The earlier wording "Gate A = PASS" must not be conflated with an explicit-PC PASS.

## Audit 3 — Phase 2A vs Phase 2C nondeterminism

Per-seed comparison (both runs same seed / same TSP / same planned loop vertices):

| Seed | 2A loops (v, waypoints) | 2C loops (v, waypoints) | 2A accepted | 2C accepted |
|---|---|---|---|---|
| 21001 | (15,6)(11,5)(8,7)(26,7) | (15,6)(11,3)(8,7)(26,6) | 0 | 1 |
| 21002 | (8,7)(38,7)(16,7) | (8,7)(38,7)(16,7) | 0 | 0 |
| 21003 | (15,6)(37,5)(8,7)(21,7) | (15,5)(37,5)(8,7)(21,7) | 0 | 1 |
| 21004 | (15,5)(26,4)(35,7)(22,5)(8,7) | (15,6)(26,5)(35,6)(22,6)(8,7) | 0 | 0 |
| 21005 | (15,5)(26,4)(35,7)(22,6)(8,7) | (15,6)(26,5)(35,7)(22,6)(8,7) | 0 | 0 |

Evidence of run-to-run nondeterminism:
- Waypoint counts returned by `reliable_loop_service` differ between runs for the same
  vertex (e.g., v11: 5 vs 3; v26: 7 vs 6; seed_21004: nearly all differ by 1-2).
- Loop start sim times differ (e.g., seed_21001 loop 1 at 448.9 vs 436.7).
- Accepted closures differ for the same seed (seed_21001 and seed_21003 each gained an
  accepted closure in Phase 2C where Phase 2A had none).

Seed_21001 explanation (0 → 1): the exploration/revisit trajectories are not identical
across runs, so the loop-4 revisit geometry differed; in the Phase 2C run it produced a
valid chain with coarse 0.657 (> 0.60). There is no evidence this is instrumentation-
induced: the instrumentation is observation-only (see 11_phase2c_instrumentation_audit.md)
and runs with identical code executed at 1.00x earlier, so the instrumentation is not a
behavioral cause. The difference is attributed to run nondeterminism; a fully causal
attribution is out of scope for a descriptive phase.

## Audit 4 — Real-time factor / Stage slowdown

Phase 2C run wall/sim ratios (first-to-last keyscan):

| Run | wall/sim |
|---|---:|
| seed_21001 | 4.96 |
| seed_21002 | 4.63 |
| seed_21003 | 4.62 |
| seed_21004 | 4.96 |
| seed_21005 | 4.96 |

An isolated Stage (roscore + stageros only, no mapper/navigation/planner) measured
~4.88 wall/sim at the time of the failures, so the slowdown is not caused by the
instrumentation or the full stack. Phase 2A runs were partially at ~1x, so Phase 2C
experiments ran at ~0.2x real time.

Implication: ROS uses sim time, but CPU scheduling, callback backlog, thread
interleaving, and asynchronous ROS communication can still depend on real execution
timing. Therefore Phase 2C runs carry an **environmental timing limitation**: they are
not bit-identical to Phase 2A in wall-time behavior. All future run manifests must
record wall/sim. No CPU governor change is made (no sudo). If an isolated probe shows
wall/sim > 1.5 before a Phase 3A batch, the environment state is recorded and the
experiment proceeds with the limitation marked, per protocol.

## Audit 5 — Instrumentation field quality

- `scan_yaw` in `karto_loop_diagnostics.jsonl` is **0.0 in all 3422 records**. The field
  is produced from `pScan->GetReferencePose(m_pUseScanBarycenter=true)`, which returns
  the scan-point **barycenter** pose; the barycenter has a position but its heading is
  not the scan heading (always 0). The field is therefore **invalid** and must not be
  used for orientation analysis.
- Phase 2C scientific analysis (`tools/analyze_phase2c.py`) does **not** use `scan_yaw`:
  `delta_yaw_at_closest_rad` and all orientation statistics are computed from the TUM
  trajectories (`load_tum`), i.e., trajectory-derived yaw. The analysis is therefore
  unaffected.
- Phase 3A rule: all orientation features must come from trajectory-derived yaw
  (GT or SLAM path), explicitly labelled by source. The diagnostics `scan_yaw` field is
  retained only as a recorded-but-invalid field.

## Stage A conclusion

- The instrumentation does not alter the algorithm (Audit 4 + 11_phase2c doc).
- The C3/D1 internal rejection mechanisms are real for the Phase 2C runs (direct Karto
  evidence), and the classification (dominant vote + deepest-stage fields) is faithful.
- Required documentation corrections: (1) old→new table is replication-level, not
  event-level; (2) Gate A = ACCEPTED-path validated, explicit PC not completed;
  (3) `scan_yaw` marked invalid; (4) wall/sim recorded as an environmental timing
  limitation for all Phase 2C runs.

**Stage A = PASS** (with corrections recorded above). Core Phase 2C conclusions stand.
Proceed to Stage B (natural experiment analysis).
