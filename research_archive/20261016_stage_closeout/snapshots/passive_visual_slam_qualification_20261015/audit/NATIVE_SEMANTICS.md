# Official RGB-D output and observer semantics

Fixed ORB-SLAM3 commit: `4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4`.

- `rgbd_tum.cc` reads every row of its association file in a for-loop. It does not read GT. RGB-D timestamps are the RGB timestamps; the paired depth timestamp is parsed but not passed independently to the estimator. The association file therefore has no comment/header rows.
- `System::TrackRGBD()` calls the existing RGB-D tracker, then copies tracking state, map-point pointers and undistorted keypoints under `mMutexState`. Three public `GetTrackingState/GetTrackedMapPoints/GetTrackedKeyPointsUn` methods lock the same mutex and return values/copies. They contain no estimator setters, parameter changes, random calls, or graph operations.
- Optional observer code only calls these getters after `TrackRGBD` returns, buffers observations, and writes after shutdown. A pointer is counted by `point != nullptr`, never dereferenced. This is **not** an independently verified static feature or geometric inlier label. Keypoints and nonnull associations are image-space diagnostics, not pose covariance or an information matrix.
- The observer adds time and copies memory in a multi-threaded program. Source read-only semantics and unchanged core hashes establish no intentional estimator mutation. They cannot establish bitwise timing equivalence. The original example is run first and kept separately; a later observer replay is not treated as an algorithm comparison or a counterfactual of the first run.
- Tracking state codes in `Tracking.h`: -1 SYSTEM_NOT_READY, 0 NO_IMAGES_YET, 1 NOT_INITIALIZED, 2 OK, 3 RECENTLY_LOST, 4 LOST, 5 OK_KLT. RGB-D tracking is non-inertial here.
- `Tracking.cc` stores relative poses in its `mState==OK || mState==RECENTLY_LOST` branch. `mlbLost` is set from `mState==LOST` inside that branch. Consequently RECENTLY_LOST can appear in the exported trajectory and absence/presence of a camera row is not a trustworthy per-input state label.
- `System::SaveTrajectoryTUM()` concatenates frame-relative pose with optimized reference-keyframe poses, inverts to camera-to-world, and skips `mlbLost`. It does **not** contain the largest-map filter present in the separate EuRoC exporter. `Atlas::GetAllKeyFrames()` returns the current map's keyframes. A reset/new-map history would require a map/gauge audit before treating a single global SE(3)-aligned output as a coherent whole.
- `SaveKeyFrameTrajectoryTUM()` writes surviving current-map keyframes; these are a sparse map representation. Their number does not estimate per-input tracking success.
- Final optimized camera trajectories and online poses differ in timing/optimization semantics. Native export is evaluated as a final trajectory, never as an online future predictor.

These are source facts. Actual run counts, reset events and observed losses are recorded separately after execution.
