# Next round: input-order and simple-person-exclusion diagnostic only

Proposal, NOT executed or automatically authorized. No new SLAM backend or method architecture.

Question: Does the observed high localization error on `fr3/walking_xyz`, despite exported coverage and an all-OK observer replay, remain after correcting the RGB/BGR transport convention and applying a reasonable existing person-exclusion baseline?

Use the qualified headless ORB-SLAM3 estimator, fixed original TUM3 intrinsics/depth factor, all 827 existing input pairs and the same offline GT evaluator. Start with this existing sequence; do not download additional data. The second low-dynamic sequence, if acquired in this round, is context rather than a camera-motion-matched causal control.

Three configurations, with all estimator parameters unchanged:

1. P0: current official RGB-D example convention, viewer disabled.
2. P1: only swap imread BGR to RGB immediately before `TrackRGBD`, retaining `Camera.RGB=1`; no change to intrinsics or feature thresholds. This is a format-control baseline, not an algorithm.
3. P2: P1 plus existing person detections converted to coarse feature-exclusion regions. Use either authenticated per-frame public masks with no pose-GT dependence, or an existing small CPU detector through installed OpenCV DNN. [MobileNet-SSD author code/weights](https://github.com/chuanqi305/MobileNet-SSD) is one bounded candidate; only the model availability and local Caffe reader API were inspected, inference and indoor detection quality remain UNQUALIFIED. Do not install Torch/FlowFormer or generate GT-pose-based DynaPix probabilities as a shortcut.

At most two complete runs per configuration (six short runs), with order frozen before execution and identical diagnostics on all configurations. This limited replication is motivated by the already observed native/observer/headless numerical differences; a small single-run gain cannot establish a mechanism. Keep every failure and use fresh processes/maps.

Required small engineering change: a frontend mask interface must filter keypoints/descriptors consistently before RGB-D depth association. Do not simply paint black rectangles into the input and attribute all resulting changes to feature removal. Verify the no-mask branch reproduces the original extracted features on a few existing input images. No robust-kernel, BA, matching threshold or map-lifecycle redesign. If the mask interface cannot be made trustworthy at this cost, stop the comparison.

GT remains offline. Detector inputs are the current RGB frame only. Precomputing per-frame masks may keep SLAM input pacing equal, but all inference time/storage and lack of online integration must be reported. This is not a real-time claim.

Primary measurements: full-input and GT-eligible coverage, ATE (SE3, no scale), 1s translational/rotational RPE and all failure intervals. Also report feature retention/spatial distribution, motion-blur/depth-invalid context and complete runtime including perception cost. Validate mask misses and excess removal on a fixed uniform image sample before interpreting P2 failure; detector failure is not evidence that all simple masks are insufficient. Nonnull map-point pointers do not become static/inlier labels.

Stop / interpretation:

- If P1 alone removes the apparent problem, stop proposing a dynamic-specific method from this result.
- If a reasonable P2 consistently reduces errors to the low-dynamic reference range without a coverage loss, prioritize the conclusion that a simple existing method suffices; do not add new modules to preserve a topic.
- If P2 fails with poor detections, the mechanism remains UNKNOWN. Do not declare a geometry or uncertainty-weighting gap.
- If differences are within execution variability, retain UNRESOLVED; do not select the best run or tune thresholds.
- Only a persistent, directly diagnosable residual after these controls can justify another narrow prior-art check. DynaPix already covers soft probabilities and retaining usable stationary parts; QualiSLAM and DGO-VINS also prevent generic feature-quality/adaptation claims.

This proposal can falsify the need for a new method. It does not establish SCI novelty or authorize formal algorithm development.
