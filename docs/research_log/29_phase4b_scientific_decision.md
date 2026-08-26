# Phase 4B Scientific Decision

Date: 2026-08-26

Decision: **PROCEED_TO_PHASE4C**

This decision means that the frozen Phase 4B evidence is sufficient to test the
same question across additional maps. It does **not** mean that Selective is already
validated as generally superior, that 4.0 m is an optimal or backend-derived
threshold, or that mapping quality improved reliably.

## 1. Decision-tree application

The literal pre-frozen Case A gate is met, with substantial uncertainty:

1. C's seed-rate mean exceeded A (0.130 versus 0.0667; pooled descriptive counts
   3/21 versus 1/21), although the median was zero for both and C-A changed sign
   across seeds.
2. C cost less than B in every seed: mean active-loop savings were 68.61 m and
   275.44 s; total exploration distance/time were also lower in every seed.
3. At least part of the A-relative outcome layer was not degraded on aggregate:
   mean/median APE and mean boundary F1 favored C. However, RPE mostly favored A,
   occupied IoU was nearly unchanged on average, and all outcome metrics were
   heterogeneous.

Therefore Case A authorizes Phase 4C generalization testing. It does not authorize
method tuning, a general mapping-improvement claim, or a claim of statistical
significance.

## 2. Answers to Q1-Q10

### Q1. Is fresh Original active-loop acceptance still low?

**Confirmed.** A accepted 1/21 executed loops (4.76% pooled descriptive rate); four
of five seed rates were zero and the seed-rate median was zero.

### Q2. Does Always-Trace improve backend acceptance?

**Inconclusive.** B accepted 2/21 versus A's 1/21, but its seed-rate mean advantage
was only +0.0133, the median difference was zero, and seed 21002 regressed from one
A acceptance to zero B acceptances. The intervention can change matching outcomes,
but these five fresh seeds do not show a stable acceptance improvement.

### Q3. Does Selective improve backend acceptance?

**Supported, not confirmed.** C accepted 3/21 versus A's 1/21 and had a +0.0633
mean seed-rate difference. C improved in seeds 21003 and 21005, tied in 21001 and
21004, and regressed in 21002. The direction is favorable in the aggregate but not
stable enough for a confirmed general claim.

### Q4. Does Selective reduce revisit cost relative to Always-Trace?

**Confirmed for map3.** C active-loop distance and time were lower than B in all
five paired seeds. Mean reductions were 68.61 m and 275.44 s; total exploration
distance and time were also lower in all five seeds.

### Q5. Does Selective reduce unnecessary repair?

**Confirmed operationally.** B traced 21/21 loops; C repaired 9/21 and selected
`NO_REPAIR` for 12/21. Two accepted C repairs stopped after one waypoint, skipping
23/24 planned waypoints each. “Unnecessary” here means avoided by the frozen proxy,
not a theoretical backend label.

### Q6. Is there easy-loop regression?

**Confirmed as an observed paired outcome.** A seed 21002 vertex 8 was accepted,
whereas B and C were not. B seed 21004 vertices 15 and 22 were accepted, whereas C
was not. Because conditions are fresh stochastic executions, these observations do
not prove a deterministic per-loop counterfactual mechanism.

### Q7. Do additional accepted constraints improve APE/RPE?

**Inconclusive.** C's accepted-closure seed 21003 improved APE and both RPE metrics
relative to A; accepted-closure seed 21005 had slightly worse APE/RPE than A. B's
accepted seed 21004 improved APE but worsened both RPE metrics. Across all seeds C
had lower mean APE than A, but worse RPE translation and rotation in 4/5 seeds.

### Q8. Does final occupancy-map quality improve?

**Inconclusive.** Relative to A, C's mean occupied IoU changed by only +0.00106 and
was better in 3/5 seeds; boundary F1 improved on average but included a large
negative seed. Relative to B, C IoU was lower in all five seeds and boundary F1 was
lower on average. The data do not support a stable “mapping improved” statement.

### Q9. Did closure increase without mapping improvement?

**Confirmed as a possible Phase 4B outcome.** In seed 21003, C uniquely accepted an
active loop while both occupied IoU and boundary F1 were lower than B. At the
five-seed C-B aggregate, acceptance was higher but occupied IoU was lower in all
five seeds and mean boundary F1 was lower. Loop realization and map quality are not
interchangeable outcomes.

### Q10. Is Phase 4B sufficient to enter multi-map generalization?

**Supported.** The frozen Case A gate is met narrowly and the core cost result is
consistent enough to justify the prescribed Phase 4C test. The next phase is needed
because acceptance, APE/RPE and map outcomes remain heterogeneous; Phase 4B alone
is not evidence of generalization.

## 3. Negative results and limitations

- Acceptance remained sparse: 1, 2 and 3 accepted active loops out of 21 for A, B
  and C, respectively; every condition's median seed acceptance rate was zero.
- Always-Trace did not reliably raise acceptance and incurred higher loop distance
  and time in every seed. Seed 21005 included a 491.3 s unaccepted traced loop.
- C did not preserve every A/B success. The span proxy produced both helpful repair
  cases and missed/regressed cases.
- C's two seed-21005 repair acceptances early-stopped correctly, but seven other
  repairs produced no accepted constraint. One C acceptance occurred without repair.
- Trajectory accuracy and map quality did not move monotonically with acceptance.
- The sample contains five seeds, one map, one Karto backend and one 2D planar Stage
  setup. Stage timing and navigation execution vary across fresh runs.
- The 4.0 m gate remains a configuration-inspired lightweight prototype heuristic,
  not a Karto theorem, scan-count conversion or calibrated classifier.
- Map IoU has a known frozen construct limitation from filled Stage obstacles versus
  primarily surface-observed LiDAR occupancy.
- No p-values are reported. Statistical interpretation uses seed-wise paired raw
  differences; 11/11 methodological fallacies were checked, and individual loops
  are not treated as independent replicates.

## 4. Exact next recommendation

Run Phase 4C only as the pre-specified multi-map generalization study: map3 plus one
corridor-heavy and one room/loop-rich map, prioritizing fresh Original versus frozen
Selective runs. Keep high-level selection, 4.0 m proxy, repair bounds, Karto,
diagnostics-off policy and offline trajectory/map metrics unchanged. Report loop
acceptance, execution cost, APE/RPE, occupied IoU and boundary F1 per map and seed.
Do not tune the gate or implement a new realization descriptor before reviewing
those cross-map results.
