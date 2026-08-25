# Phase 4B Offline Mapping Evaluation Protocol

Date frozen: 2026-08-25

This evaluator is offline-only. It reads the final estimated occupancy map and the
Stage ground-truth bitmap/YAML after a run. It does not contact ROS, modify Karto,
align a method by hand, or feed any result back to the planner.

## 1. Ground-truth occupancy map

Source:

- image: `world/map3/map3.png`, 740 x 740 pixels;
- YAML resolution: 0.1 m/cell;
- YAML origin: `[-9.0, -9.0, 0]` in the Karto `map` frame;
- spatial extent: 74.0 x 74.0 m.

The origin follows from the fixed Stage floorplan and fixed robot start and is
already expressed in the same robot-relative map frame used by Karto. Therefore the
frozen registration transform is **identity**. There is no evo alignment, ICP,
per-method translation or manually selected transform for map evaluation.

Occupancy conversion follows ROS map-server YAML semantics (`negate=0`):

`p_occ = (255 - grayscale) / 255`.

- occupied if `p_occ > occupied_thresh` (0.65);
- free if `p_occ < free_thresh` (0.196);
- otherwise unknown.

The final estimated map uses its saved YAML resolution and origin. Cell centres are
deterministically sampled into the GT grid in world coordinates. Out-of-bounds
estimated cells are unknown. A non-finite saved yaw (the observed `-nan` map-saver
convention) is interpreted as zero only; nonzero finite yaw is handled by the same
deterministic rigid map-origin transform.

## 2. Evaluation mask and unknown policy

The evaluation domain is all GT cells classified occupied or free. GT unknown cells
are excluded because their class is undefined in the source map. This mask and all
thresholds are identical for A/B/C.

Within the GT-known domain, estimated unknown/out-of-bounds cells are neither
occupied nor free. Consequently they count as false negatives where GT is occupied
or free, but do not become invented occupied/free cells. Estimated occupied cells in
GT-unknown cells are excluded from the primary scores. `estimated_unknown_ratio`
reports the fraction of the GT-known domain not classified by the estimated map.

## 3. Primary metric 1: occupied-space IoU

Let `Occ_gt` and `Occ_est` be occupied cells inside the frozen GT-known domain:

`IoU_occ = |Occ_est intersection Occ_gt| / |Occ_est union Occ_gt|`.

The evaluator also stores intersection, union, GT occupied and estimated occupied
counts. Free-space IoU is an explicitly secondary diagnostic using the same rule.

## 4. Primary metric 2: occupied-boundary F1

An occupied boundary is an occupied cell that is not preserved by one iteration of
8-neighbour 3 x 3 binary erosion. Precision and recall use symmetric nearest-boundary
matching with a frozen **0.20 m tolerance** (two GT cells at map3 resolution):

- precision: fraction of estimated boundary cells within 0.20 m of a GT boundary;
- recall: fraction of GT boundary cells within 0.20 m of an estimated boundary;
- F1: harmonic mean of precision and recall.

Distances are computed in metres. Empty-boundary cases are explicitly defined: both
empty gives 1; only one empty gives 0. The tolerance was frozen before viewing any
Phase 4B result and is not selected per method.

## 5. Synthetic validation gate

Before formal runs, unit tests must show:

1. GT versus GT: occupied IoU and boundary F1 approximately 1;
2. a multi-cell translation lowers both scores;
3. boundary thickening/double-wall corruption lowers boundary F1;
4. GT-unknown cells are excluded while estimated unknown on known occupancy lowers
   the score;
5. equivalent maps at different resolutions are resampled consistently.

The formal suite is blocked if these tests fail. The evaluator writes all input
hashes, thresholds, transform, grid metadata and raw count terms into
`mapping_metrics.json` so each score can be audited.
