# Doc-80 analysis corrections (audit side)

## 1. Corrected target map GT (replaces nothing)

`TARGET_MAP_ERROR` in Doc-79 was computed from the driver-recorded
`map_base` at the target acceptance time, reused for all four stages.
The corrected computation reads the target node pose from each
synchronous stage graph (frame-verified: dump nodes are map->laser
poses; the base pose adds T_LASER_BASE = (-0.20, 0, 0)).

Stage means of the corrected target map error (m):
- action_done: mean 0.0165, max 0.0601 (n=35)
- arrival: mean 0.0158, max 0.0612 (n=35)
- before_return: mean 0.0153, max 0.0612 (n=35)
- final: mean 0.0165, max 0.0601 (n=35)

Node displacement between consecutive stages (optimisation movement of
historical target nodes):
- action_done: mean 0.00324 m, max 0.01423 m
- arrival: mean 0.00135 m, max 0.00594 m
- final: mean 0.00000 m, max 0.00000 m

Difference vs Doc-79 original: within the 2-5 cm TF-lag band
(driver map_base vs graph node at the acceptance stamp); the original
metric was therefore numerically close, but it could not have detected
stage-dependent movement, which the correction shows is <= 0.014 m.

## 2. Boundary watermark semantics

The watermark asserts the coverage of the driver-observed scans, not
the absence of later scans. Measured: 0 nodes beyond the watermark in
all 28 boundary graphs (stationary dwell produces no new keyframes),
so the stage attribution of the synchronous graphs is clean.

## 3. Provenance identity

0 duplicate (source,target) endpoint keys in 7/7 runs; every graph edge
has exactly one creation record (171-187 per run); the frozen
dictionary indexing is lossless on this data.

## 4. Target freeze

Re-running the driver freeze rule reproduces the original anchor and
targets from the topic graph in 7/7 runs; using the synchronous graph
or a laser-frame-corrected reference changes nothing (same anchor,
same five targets). The topic deficit and the lever arm did NOT affect
the frozen estimand.
