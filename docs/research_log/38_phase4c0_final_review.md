# Phase 4C-0 Final Review

## A. Repository State

Phase 4C-0 was isolated on `research/phase4c0-scientific-audit`. Phase 4B raw data
was not modified; online baseline and navigation nested commits remain frozen.

## B. Phase4B Handoff Verification

15/15 formal map3 runs and their paired TSP, manifests, raw logs, trajectories,
maps, and aggregates are verified. Raw artifacts take precedence over prose.

## C. Active-Loop Attribution

Strong target attribution: **READY**. Phase4B compatible: **YES**. Current keyscan
must be acquired inside exactly one active interval and the accepted history chain
must exactly overlap frozen-replay intended history IDs. Reanalysis gives A 0/21,
B 2/21, C 2/21 target-attributable actions.

## D. Pose-Graph Impact

Baseline metric is normalized weighted spanning-tree D-opt. Reproduction is ready;
strict causal constraint pre/post evaluation is **NOT READY**. Continuous pose
correction is ready when compatible snapshots exist. This is nonblocking and
exploratory, not a fabricated primary endpoint.

## E. Map Metric Construct Audit

Filled Stage obstacles and surface-like LiDAR occupancy make occupied IoU thickness-
sensitive. IoU remains secondary.

## F. Mapping Evaluator Validation

Boundary F1 at 0.20 m and symmetric mean boundary distance are frozen. Identity,
1/2/4-cell translation, double wall, thickening, unknown mask, resolution, and empty
local ROI tests pass 7/7.

## G. Phase4B Mapping Reanalysis

A/B/C global Boundary F1 means are 0.4106/0.5045/0.4495; symmetric distances are
0.6095/0.4771/0.5199 m. Results are mixed; B has best means and C is not uniformly
better than A.

## H. Local Revisit Consistency

**READY** as a bridge/secondary metric with 5 m ROI and explicit observed coverage.
Unavailable/no-GT-boundary cases remain labelled, and map-seed is inferential unit.

## I. Map/Prior Inventory

Four author map/prior pairs are GT- and launch-ready; no prior was hand-designed.

## J. Selected M2/M3

M2=map4 and M3=map7. Selection before performance runs: **YES**. Both passed
startup-only smoke without exploration.

## K. Statistics Freeze

Primary unit is map-seed (15 eventual blocks). Rare events use per-map raw counts,
per-seed rates, descriptive pooled rates, paired contrasts and direction counts;
individual loops are never independent significance samples.

## L. Phase4C Formal Protocol

M2/M3 each run A/B/C x five paired seeds (30 new runs) in the frozen counterbalanced
order. Only `oracle_mode` differs; B is mandatory.

## M. Remaining Risks

The 4 m heuristic is uncalibrated; only Karto is tested; closures remain rare;
Stage execution is stochastic; map representation differs from LiDAR occupancy;
history replay cannot eliminate all attribution ambiguity; and the nominal 12 m
repair budget can overshoot on the terminal segment. Strict closure-specific graph
gain is unavailable for some events.

## N. Decision

**GRAPH_IMPACT_NOT_READY_BUT_NONBLOCKING**

## O. Exact Next Step

After user confirmation, perform a clean formal preflight and then execute the
frozen 30-row map4/map7 matrix in its recorded order, one fresh ROS/Stage process per
cell, with fail-closed TSP pairing and no automatic experimental retry. Do not tune
the method between maps or start any run before that confirmation.

# STOP
