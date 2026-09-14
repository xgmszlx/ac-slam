# Phase 4C Final Decision

Date: 2026-09-14

## Decision

`REOPEN_EXECUTION_HYPOTHESIS`

## Rule-based justification

The formal results do not satisfy `METHOD_GENERALIZATION_SUPPORTED`: C meets the
narrow H3 tradeoff rule on the two executable maps (the same pooled realization
count as B at lower cost), but Mexico never reaches the treatment and C exhibits
systematic map8 map-geometry regression. The cross-environment and supporting-H4
requirements therefore fail.

They do not satisfy `REDESIGN_REALIZABILITY_GATE`: B is not clearly better than A
in target-attributable realization, so there is no demonstrated B benefit for C
to preserve.

They also do not satisfy the strict trigger for `REASSESS_LOOP_UTILITY`: all 15
accepted target events have zero measured pose correction, but B/C did not
produce more target closures than A across the evaluable maps. The zero-correction
result remains an important secondary warning rather than the primary branch
decision.

The evidence fits `REOPEN_EXECUTION_HYPOTHESIS`: map3 has almost no
target-attributable closure under any condition, map8 has sparse and treatment-
insensitive formation, and Mexico never reaches active-loop execution despite
55 planned loops per method. The first unresolved causal boundary is therefore
planned target to reached/executed action, followed by executed action to backend
constraint.

## Exact next recommendation

After explicit approval, run a measurement-controlled execution-hypothesis study
that first explains and removes only the Mexico experimental execution blocker
(including the negative-vertex `handle_edge_distance` failures) without changing
the planner objective, gate, Karto matching, skip policy, or frozen attribution.
Then repeat a small pre-registered A/B execution-leverage check in a stable
environment and, only if the intervention is actually reached, validate the same
causal step with one independent SLAM backend. Do not redesign the gate or claim
method generalization before that evidence exists.
