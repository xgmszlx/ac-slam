# Map Metric Construct Audit

Date frozen: 2026-08-31

## Why occupied IoU is limited

The Stage ground-truth bitmaps encode filled obstacle polygons/interiors. Karto's
2D LiDAR occupancy estimate primarily marks sensor-observed obstacle surfaces and
may differ in wall thickness. Even with geometrically well-located walls, the two
occupied sets can therefore have a small intersection and a large representation-
driven union. Phase 4B IoU values near 0.06--0.08 are consistent with this construct
mismatch and cannot alone distinguish wall displacement from occupancy thickness.

Occupied IoU is retained unchanged as a secondary metric. It is not discarded and
is not the sole map-quality outcome.

## Frozen primary map metrics

1. **Occupied Boundary F1**, symmetric nearest-boundary matching at the Phase 4B
   frozen tolerance of 0.20 m. Precision uses estimated boundary source points;
   recall uses GT boundary source points.
2. **Symmetric Boundary Distance**, in metres:
   `0.5 * (mean(est -> nearest GT boundary) + mean(GT -> nearest est boundary))`.
   The analogous symmetric median and p95 are supporting values.

No manual transform, ICP, evo alignment, per-method registration, or result-based
tolerance selection is allowed. Map YAML origins/resolutions define the identity
map-frame registration and deterministic resampling.

## Unknown and empty-boundary policy

All GT-known cells form the global domain. Estimated unknown/out-of-bounds cells
are unobserved; they remain missing GT boundary for recall rather than being
excluded to improve scores. A one-empty global boundary gives Boundary F1 zero and
undefined geometric distance. A local ROI with no GT boundary is explicitly
`NOT_APPLICABLE_NO_GT_BOUNDARY`, never a perfect score.

## Local revisit construct

The frozen local radius is 5.0 m around the high-level loop vertex in the common
map/prior coordinate frame. Boundary source points must lie inside the circle, but
nearest-neighbour search uses the complete opposite boundary to prevent circular
crop-edge artifacts. Local observed coverage is all estimated-known GT-domain
cells divided by all GT-known cells in the circle. This makes low exploration
coverage visible and prevents scoring only convenient observed pixels.

No MSD/MAD metric was added: Boundary F1 plus symmetric mean/median/p95 distance
already cover the required placement/thickness evidence without multiplying
primary outcomes.
