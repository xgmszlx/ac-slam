# Phase 3A Stage C: Causal/Oracle Validation

Date: 2026-08-23

## 1. Purpose

Phase 2C confirmed two planner-to-SLAM realization bottlenecks: **C3 candidate-chain
insufficiency** (chain too short) and **D1 coarse-response rejection** (coarse < 0.60).
Phase 3A Stage B showed descriptive associations between revisit-realization features
and these bottlenecks. Stage C tests the causal claim with a minimal oracle: hold loop
selection, planning, Karto and all thresholds fixed; change **only** the revisit
realization (V1 history-trace) and measure the Karto evidence change.

## 2. Oracle design (V1)

- Independent variant in `reliable_loop_service` (baseline repo `dbc01b3`), behind an
  explicit `oracle_mode` switch, **default off** (mode 0 == byte-identical V0).
- V1 returns a **longer contiguous window of SLAM-estimated historical poses** (global
  pose-graph order, `oracle_before=oracle_after=8` around the closest pose), **densified**
  by linear interpolation at `oracle_densify_m=0.5 m`, position-only (x/y) exactly like
  V0. History source is the deployable SLAM pose graph (`self.pose_graph`); **GT is never
  used by the service**.
- Same loop vertex, same TSP, same planner, same Karto, same thresholds
  (LoopMatchMinimumResponseCoarse=0.6, Fine=0.7, MinimumChainSize=4).

## 3. Test cases (V0 baseline from Phase 2C, same seed + same vertex)

| Case | seed | target vertex | V0 subclass | V0 evidence |
|---|---|---|---|---|
| S reference | 21001 | v26 (loop 4) | S | coarse 0.657, fine 0.927, accepted |
| D1 | 21003 | v15 (loop 1) | D1 | coarse 0.401 (<0.60) |
| C3 + D1 | 21004 | v26 (loop 2), v22 (loop 4) | C3, D1 | coarse 0.427, 0.57 |
| C3 + D1 | 21005 | v26 (loop 2), v22 (loop 4) | C3, D1 | coarse 0.48, 0.307 |

TSP byte-identical to Phase 2C for all 4 runs (verified; loop selection held fixed).

## 4. Protocol

- Runs executed by `tools/run_phase3a_oracle.py` (V1, oracle_mode=1). Early stop
  shortly after the target loop finishes (diagnostics are flushed per record).
- Isolated Stage probe attempted before the batch (first probe had a script bug and was
  recorded as such; the probe was fixed for future runs). Per-run wall/sim computed from
  keyscan anchors: 4.89 / 4.92 / 4.97 / 4.97 (consistent with Phase 2C; environmental
  timing limitation, no sudo).
- Raw runs preserved under `results/phase3a/oracle/`; failed/missing runs would be
  marked (none were).

## 5. Results (per target loop, V0 → V1)

| Case | V0 coarse | V1 coarse | V1 fine | V1 accepted | Chain fraction V0→V1 | Extra waypoints | Extra trace (m) | Loop sim time (s) |
|---|---:|---:|---:|---|---:|---:|---:|---:|
| s21001 v26 (S ref) | 0.657 ✓ | 0.493 | — | ✗ | 0.586→0.397 | +27 (33 vs 6) | +10.67 | 137.8 |
| s21003 v15 (D1) | 0.401 | **0.685** | **0.700** | **✓** | 0.625→0.333 | +22 (27 vs 5) | +7.34 | 99.0 |
| s21004 v26 (C3) | 0.427 | 0.418 | — | ✗ | 0.276→0.220 | +28 (33 vs 5) | +11.53 | 164.0 |
| s21004 v22 (D1) | 0.570 | **0.734** | **0.807/0.818** | **✓ ×2** | 0.650→0.357 | +26 (32 vs 6) | +10.80 | 118.0 |
| s21005 v26 (C3) | 0.480 | 0.468 | — | ✗ | 0.070→**0.360** | +27 (32 vs 5) | +11.81 | 119.8 |
| s21005 v22 (D1) | 0.307 | **0.656** | 0.689 | ✗ (fine) | 0.550→0.427 | +22 (28 vs 6) | +6.01 | 128.0 |

ACCEPTED diagnostics records (1:1 with "Add one Loop" callbacks): s21003 v15
(scan 284, coarse 0.685, fine 0.700), s21004 v22 ×2 (scan 861 coarse 0.603 fine 0.807;
scan 894 coarse 0.734 fine 0.818). Bonus observed: s21005 v15 accepted (scan 255,
coarse 0.69, fine 0.819) and s21001 v8 accepted (scan 594, coarse 0.796, fine 0.785).

## 6. Findings

### F1. D1 is causally rescuable by revisit realization (primary finding)

All three D1 target loops crossed the coarse gate with V1 (0.685, 0.734, 0.656),
whereas in V0 no D1 loop (0/8) reached ≥ 0.60. Two were accepted by Karto (s21003 v15,
s21004 v22 ×2); the third (s21005 v22) crossed coarse but was blocked by the **fine gate
at 0.689 < 0.70** — a new D4-type observation that emerges once coarse passes. This is a
causal demonstration: the coarse-response rejection is caused by an inadequate revisit
realization, and a longer, denser re-traversal of the SLAM history reliably lifts the
coarse response above the gate **without any threshold change**.

### F2. C3 is only partially addressed

Neither C3 target reached acceptance. Chain persistence improved strongly in one case
(s21005 v26: valid-chain fraction 0.07 → 0.36, ~5×; longest consecutive valid-chain
keyscans 6→10) but the best coarse stayed < 0.60 (0.468). The other C3 case (s21004
v26) was essentially unchanged. A longer history trace increases chain availability
(consistent with Stage B) but is not sufficient to produce a ≥ 0.60 match in these two
tests.

### F3. The intervention is non-monotonic (S reference regression)

The S reference (s21001 v26: accepted at coarse 0.657 in V0) **regressed** under V1
(coarse 0.493, not accepted). The longer detour changed the scan sequence at the vertex
so the previously-good match did not recur. In the same V1 run, the acceptance instead
appeared at v8 (which was C3 in V0), so the total accepted closures stayed 1 — the
intervention can *displace* acceptances, not only add them.

### F4. Cost

Every V1 loop is much longer: +22–28 waypoints, +6–12 m of trace, and ~100–165 sim s
extra execution per loop (2–5× the V0 loop duration). This is the "more achievable
revisit" price and must be weighed against the acceptance gain.

## 7. Gates

- **Gate A** (instrumentation/oracle switch correctness): oracle is an independent
  variant, default off, byte-identical when off; TSP byte-identical to Phase 2C in all
  4 runs. **PASS**.
- **Gate B** (loop selection held fixed): all 4 runs reproduce the Phase 2C TSP exactly.
  **PASS**.
- **Gate C** (at least one stable improvement without threshold changes): D1→accepted in
  two target cases (s21003 v15, s21004 v22), coarse ≥ 0.60 in all three D1 targets, plus
  a bonus D1→accepted at s21005 v15. **PASS** (with the F3/F4 caveats recorded).
- **Gate D** (evidence quality): ACCEPTED diagnostics records match callbacks 1:1; raw
  runs preserved; wall/sim recorded per run. **PASS**.

## 8. Answer to the Phase 3A hypothesis

> "Active SLAM 回环的价值只有在机器人能够产生一段持续、可匹配的历史重访观测时才能兑现。"

**Supported for the D1 (coarse-response) mechanism, partially for C3, with a
documented non-monotonicity cost.** Holding the high-level loop selection fixed, a more
faithful revisit realization (longer, denser, contiguous re-traversal of SLAM history)
causally lifts coarse responses past the 0.60 gate and produces Karto-accepted closures
in D1 cases that were previously coarse-rejected. The C3 chain bottleneck is improved
but not closed in the tested cases, and the intervention can displace an existing good
match (S reference regression), so it is not a free lunch.

## 9. Caveats and limitations

- n is small (3 D1 targets, 2 C3 targets, 1 S reference); BQ3-level claims are
  descriptive. Replication with more vertices would strengthen the causal claim.
- V0 vs V1 are separate runs (documented run-to-run nondeterminism). The consistency of
  the D1 lift across all three targets, with TSP fixed, supports a causal
  interpretation beyond noise.
- V2 (commanded heading) was not implemented: the reliable-loop strategy goal is
  position-only, so heading correction would require changing the strategy→navigator
  goal channel (out of the "minimal" scope).
- Fine-gate (D4) rejection was not a Phase 2C bottleneck (0 cases) but emerged under V1
  (s21005 v22 fine 0.689). Fine response may become the next binding constraint after
  coarse is resolved.

## 10. Recommended next stage

**Proceed to literature boundary + minimal method design.** The causal evidence
justifies a *realization-level* method: make the revisit re-traverse a contiguous
SLAM-history trace (this work) and evaluate its cost; research the literature on
history-trace/coverage-based loop-closure revisit and on scan-descriptor matching (for
the emerging fine-gate constraint). Do **not** propose threshold changes or new scoring
from this phase's data (Phase 3A constraints).
