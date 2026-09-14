# Phase 4C Hypothesis Review

Date: 2026-09-14

## H1 — Realization Gap: SUPPORTED

Original realized 0/21 target-attributable constraints on map3 and 5/15 on map8.
Mexico added a more severe planned-to-executed gap: 55 planned Original loops,
none executed. Because Mexico has no executed denominator, it is not pooled into
`R_target`; nevertheless it is direct evidence that planner-selected loop actions
do not reliably propagate through the full system. The gap is environment-
dependent rather than universally 0%.

## H2 — Execution Leverage: INCONCLUSIVE

Always-Trace did not improve aggregate target-attributable formation over
Original: both were 0/21 on map3 and 5/15 on map8. Seed-level map8 changes occur
in both directions and cancel in aggregate. Mexico never activated either
execution treatment. Earlier mechanistic evidence may show that retracing can
alter matching conditions, but Phase 4C does not establish system-level
generalization of that leverage.

This is not classified `CONTRADICTED`, because the observed intervention did
change trajectories/cost substantially and individual paired outcomes varied;
the experiment is simply too event-sparse, and one environment never reached
the intervention.

## H3 — Selective Efficiency: INCONCLUSIVE

C and B each produced 5/36 target-attributable events over the two evaluable
maps. C used substantially less active-loop distance/time in 9/10 and 10/10
paired blocks respectively. This supports the cost half of H3.

However, C did not demonstrate a stable realization advantage, and on map8 it
showed systematic global and local map-geometry regression relative to B. Mexico
provides no active-loop comparison. The decision rule requires retained
realization benefit without systematic degradation, so formal support for H3 is
not established.

## Supporting H4 — No systematic degradation: NOT SUPPORTED

Translation RPE often improved under C, especially on map3, but APE and map
geometry did not. On map8, C had lower global Boundary F1 and higher symmetric
boundary distance in all five seeds; local symmetric boundary distance was also
higher in all five. These consistent map8 regressions violate the supporting
condition even without inferential significance claims.

## Answers to the frozen cross-map questions

1. The realization gap remains on map8 and becomes an execution-stage failure on
   Mexico.
2. B does not show cross-environment system-level execution leverage.
3. C produces target-attributable constraints on map3/map8 (5/36 overall), but
   not reliably enough to establish a benefit.
4. C consistently reduces time versus B on every executable paired block and
   reduces distance in 9/10.
5. C shows an easy-environment regression on map8 map geometry.
6. No method-induced planned selection-sequence divergence occurred (15/15 exact).
7. None of the 15 target-attributable constraints was accompanied by nonzero
   measured historical-pose correction.
8. C does not systematically improve trajectory accuracy: translation RPE often
   improves, while APE/rotation results are mixed or worse.
9. C systematically harms the two primary local geometry measures on map8, but
   not consistently on map3; Mexico is incomplete.
10. H1 is supported; H2 and H3 are inconclusive.
