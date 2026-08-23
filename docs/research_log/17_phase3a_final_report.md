# Phase 3A Final Report — Causal Validation of Planner-to-SLAM Revisit Realization

Date: 2026-08-23 · Branch: `research/phase3a-revisit-oracle`

## A. Executive summary

Phase 2C confirmed that the active-loop revisit fails at two internal Karto gates:
**C3 candidate-chain insufficiency** (12 loops) and **D1 coarse-response rejection**
(8 loops). Phase 3A asked whether these failures are *caused* by the quality of the
revisit realization (the actual path the robot takes when re-observing its history)
and whether a "more achievable" history-trace revisit — with loop selection, planning,
Karto and all thresholds held fixed — causally rescues closures.

**Answer: yes for D1, partially for C3, with a documented non-monotonicity cost.**
In a minimal oracle experiment (V0 baseline vs V1 history-trace revisit, same seed and
same loop vertex, TSP byte-identical), all three D1 target loops crossed the coarse
gate with V1 (0.685, 0.734, 0.656 vs 0.401/0.570/0.307 in V0); two were accepted by
Karto and one was blocked only by the fine gate (0.689 < 0.70). The C3 chain bottleneck
improved in one case (valid-chain fraction 0.07→0.36) but neither C3 target reached
acceptance. The single success reference (s21001 v26) **regressed** under V1
(0.657→0.493), showing the intervention can displace existing acceptances. The phase
conclusion: **the D1 coarse-response bottleneck is causally rescuable by revisit
realization; C3 is only partially so; the hypothesis is supported for D1 with a
realization-cost trade-off.**

## B. Research question and hypothesis

- **RQ**: Does improving the *realization* of the planned loop revisit (how the robot
  re-observes its own history) causally improve Karto loop acceptance, while keeping
  the high-level loop selection fixed?
- **Hypothesis**: Active SLAM loop value is realized only when the robot produces a
  sustained, matchable history re-observation. If this is true, a longer/denser
  history-trace revisit should raise chain persistence (C3) and coarse response (D1)
  and produce accepted closures without touching any threshold.

## C. Method overview (three stages)

1. **Stage A — Scientific audit of Phase 2C** (descriptive, no new runs).
2. **Stage B — Natural experiment** on the existing 21 Phase 2C loops (features vs
   outcome, no new runs).
3. **Stage C — Minimal causal/oracle experiment**: V0 (Phase 2C baseline) vs V1
   (history-trace oracle), 4 runs / 6 target loops, early-stop protocol.

## D. Stage A audit (PASS with corrections)

- **A1**: Phase 2B→2C taxonomy is a replication-level comparison (same seed/index/vertex
  re-run), not event-level relabeling; wording corrected in 12_phase2c.
- **A2**: Gate A = ACCEPTED-path instrumentation validated (1:1 via seed_21001 active
  closure); explicit positive control uncompleted (environmental); wording corrected.
- **A3**: Run-to-run nondeterminism documented (Phase 2A vs 2C: same loops, different
  waypoint counts/timings/accepted counts).
- **A4**: wall/sim 4.62–4.96× (all Phase 2C and oracle runs); isolated Stage ≈4.9×;
  CPU governor powersave, no sudo → **environmental timing limitation**, recorded per
  run (oracle runs: 4.89/4.92/4.97/4.97).
- **A5**: diagnostics `scan_yaw` invalid (always 0; barycenter heading); all orientation
  analysis uses trajectory-derived yaw.

## E. Stage B natural experiment (descriptive)

- **BQ1 (chain availability ↔ realization): Supported.** Valid-chain fraction separates
  C3 (0.22) from D1 (0.63) and correlates with history-path length (r≈+0.67); chain
  formation needs *coverage* of the history graph, not proximity (spatial overlap r≈−0.35).
- **BQ2 (matcher response ↔ realization): Weakly supported/inconclusive.** D1 loops
  reach the matcher but best coarse clusters in [0.30, 0.57] < 0.60 regardless of
  measured trajectory-level realization features; coarse is dominated by scan-content
  similarity at candidate poses.
- **BQ3 (success vs failures): Supported (descriptive, n=1).** The single success
  (s21001 l4 v26) jointly had best orientation consistency (yaw-med 0.56), long
  continuous overlap (223 samples) and high chain persistence (0.59), and was the only
  loop with coarse ≥ 0.60.
- **BQ4 (same-vertex replications): Mixed.** v8→C3 in all 5 seeds, v15→D1 in all 4
  seeds (vertex-stable mechanisms); v26→S/C3/C3 (realization-dependent).

## F. Stage C oracle experiment

- **Oracle V1** (baseline repo `dbc01b3`, default off): `reliable_loop_service` returns
  a contiguous ±8-pose window of SLAM-estimated history around the loop vertex,
  densified at 0.5 m (position-only, like V0). GT never used by the service.
- **Test cases**: S reference (s21001 v26), D1 (s21003 v15), C3+D1 (s21004 v26/v22),
  C3+D1 (s21005 v26/v22). TSP byte-identical to Phase 2C in all 4 runs.
- **Results** (see §G): 3/3 D1 targets crossed coarse ≥ 0.60; 2 accepted (+1 bonus
  D1→accepted at s21005 v15); C3 improved once (chain 0.07→0.36) but not accepted; S
  reference regressed.

## G. Karto evidence before/after (V0 → V1)

| Case | subclass | V0 coarse | V1 coarse | V1 fine | accepted V1 | chain frac V0→V1 |
|---|---:|---:|---:|---:|---|---:|
| s21001 v26 | S | 0.657 | 0.493 | — | ✗ | 0.586→0.397 |
| s21003 v15 | D1 | 0.401 | **0.685** | 0.700 | **✓** | 0.625→0.333 |
| s21004 v26 | C3 | 0.427 | 0.418 | — | ✗ | 0.276→0.220 |
| s21004 v22 | D1 | 0.570 | **0.734** | 0.807/0.818 | **✓×2** | 0.650→0.357 |
| s21005 v26 | C3 | 0.480 | 0.468 | — | ✗ | 0.070→**0.360** |
| s21005 v22 | D1 | 0.307 | **0.656** | 0.689 | ✗ (fine) | 0.550→0.427 |

ACCEPTED diagnostics records matched "Add one Loop" callbacks 1:1 (s21003 v15 scan 284;
s21004 v22 scans 861, 894; bonus s21005 v15 scan 255; s21001 v8 scan 594).

## H. Causal interpretation

- **D1**: The coarse gate is *causally reachable* by realization: a dense, contiguous
  re-traversal of SLAM history raises the scan-content similarity at candidate poses
  above 0.60. This is the strongest causal result of the phase.
- **C3**: Coverage helps chain persistence but does not, in the tested cases, produce a
  ≥ 0.60 match; the chain and coarse gates interact, and C3 alone may need a different
  lever (e.g., timing/coverage relative to scan-graph connectivity).
- **Non-monotonicity**: the S reference regressed — a better-looking trace can displace
  a good match by changing the scan sequence. The intervention is a trade-off, not a
  free improvement.
- **Emerging fine gate**: once coarse passes, fine (0.70) can block (s21005 v22 fine
  0.689) — D4-type rejection that was absent in Phase 2C.

## I. Costs

Each V1 loop: +22–28 waypoints, +6–12 m trace, +~100–165 sim s execution (2–5× V0 loop
duration). These must be weighed against acceptance gains.

## J. Limitations

- Small n (3 D1, 2 C3, 1 S); BQ3 descriptive.
- V0 vs V1 separate runs (nondeterminism); TSP-fixed consistency mitigates but does not
  eliminate the confound.
- V2 (commanded heading) not implemented (position-only strategy goal channel).
- Environmental wall/sim ~5×; timing limitation recorded, not silently ignored.

## K. Safety & reproducibility

- No sudo, no CPU-governor changes, no Karto threshold/algorithm changes, no GT as a
  deployable input, no ML, no new scoring.
- Oracle is an independent variant, default off; off == byte-identical V0.
- All raw oracle runs preserved (`results/phase3a/oracle/`), wall/sim per run recorded,
  failed runs would be marked (none).

## L. Answers to the phase questions (Q1–Q7)

**Q1. Is the Phase 2C bottleneck classification trustworthy?** Yes — Confirmed via
direct Karto diagnostics; Stage A audits (replication-level wording, invalid scan_yaw,
Gate-A wording) documented in `13_phase2c_scientific_audit.md`.

**Q2. Are the two bottlenecks (C3, D1) distinct mechanisms?** Yes — C3 is a
candidate/chain availability problem (coverage-dependent); D1 is a matcher scan-content
problem (coarse response < 0.60). Stage B feature analysis and Stage C oracle outcomes
both separate them.

**Q3. Is the revisit realization the cause of D1?** Yes (causal, this phase): with loop
selection fixed, a denser/longer history-trace revisit lifted all three D1 targets past
the coarse gate; two accepted.

**Q4. Is the revisit realization the cause of C3?** Partially — coverage improves chain
persistence (0.07→0.36 in one case) but did not close the gap to acceptance in the two
tested cases.

**Q5. Is the improvement monotonic?** No — the S reference regressed (0.657→0.493);
the intervention can displace acceptances and carries a large travel cost.

**Q6. Can the fine gate become binding?** Yes — under V1, s21005 v22 was blocked at fine
0.689 (< 0.70) after coarse passed; D4-type rejection can emerge.

**Q7. What should the next stage do?** Proceed to literature boundary + minimal method
design focused on *realization-level* revisit (history-trace re-traversal), with cost
modeling and scan-descriptor matching for the emerging fine gate. Do not change
thresholds or add scoring from this phase's data.

## M. Gate decision and recommendation

- **Stage A gate: PASS** (with documented corrections).
- **Stage B gate: PASS** (interpretable associations; descriptive).
- **Stage C gates: A PASS, B PASS, C PASS** (stable D1→accepted improvements without
  threshold changes; caveats F3/F4 recorded), **D PASS**.
- **Overall Phase 3A: PARTIAL PASS — hypothesis supported for D1, partially for C3,
  non-monotonic.** 
- **Recommended next stage: Proceed to literature boundary + minimal method design**
  (realization-level revisit improvement), explicitly including cost and the observed
  fine-gate constraint. Do not propose threshold or scoring changes.
- **Safety confirmation**: no Karto thresholds/algorithm changed; oracle default off and
  independent; no GT as method input; no sudo/apt/CPU-governor/destructive git; all raw
  runs preserved with wall/sim recorded.
