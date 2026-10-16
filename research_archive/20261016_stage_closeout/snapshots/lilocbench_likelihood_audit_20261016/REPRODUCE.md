# Offline-only reproduction

Requires existing ROS Noetic libraries and system Python3.8 for rosbag reading; existing Anaconda Python3.12/numpy/scipy/matplotlib for analysis. No new installation, ROS master, estimator or online GT.

Fixed inputs are read only from `/home/wcqw/lilocbench_amcl_validation_20261016` and `/home/wcqw/lilocbench_amcl_recovery_control_20261016`. Data selection/grid are fixed in `protocol/design_frozen.json` and actual centers/hashes in `protocol/candidates_frozen_before_scores.json`.

Actual source probe build:

```bash
/usr/bin/g++ -O3 -DNDEBUG -fPIC -shared \
 -I/opt/ros/noetic/include \
 -I/home/wcqw/lilocbench_amcl_validation_20261016/diagnostic_ws_v2/src/amcl/include \
 sources/native_probe.cpp \
 -L/home/wcqw/lilocbench_amcl_validation_20261016/diagnostic_ws_v2/devel/lib \
 -L/opt/ros/noetic/lib -lamcl_sensors -lamcl_map -lamcl_pf \
 -lmap_server_image_loader -lrostime \
 -Wl,-rpath,/home/wcqw/lilocbench_amcl_validation_20261016/diagnostic_ws_v2/devel/lib:/opt/ros/noetic/lib \
 -o build/native_probe.so
```

This calls original scoring functions, not `UpdateSensor`, any `pf_update_*`, or a ROS node. Header access-control macro is only for direct static method testing; no class layout/algorithm changes. Common91 A0 uses max_beams91 only in the offline function call to select stride9, while A1 max_beams100 also selects stride9. Native102 is a separate equivalence control, never the main comparison.

Executed stages, from this directory:

```bash
source /opt/ros/noetic/setup.bash
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 code/extract_scans.py
PYTHONDONTWRITEBYTECODE=1 python3 code/prepare_candidates.py
# Candidate/hash registration was completed before any scoring.
PYTHONDONTWRITEBYTECODE=1 python3 code/test_native.py
PYTHONDONTWRITEBYTECODE=1 python3 code/score_profiles.py
PYTHONDONTWRITEBYTECODE=1 python3 code/figures.py
PYTHONDONTWRITEBYTECODE=1 python3 code/auxiliary_checks.py
PYTHONDONTWRITEBYTECODE=1 python3 code/write_report.py
PYTHONDONTWRITEBYTECODE=1 python3 code/protect.py
```

Re-executing analysis would overwrite this directory's derived files, not old inputs; preserve the published artifacts first if independently reproducing. Original pre-score lowercase-yaw helper/center registration is retained in `sources/pre_score_projection_v01`; final uppercase intrinsic ZYX correction and refreeze occurred before scores. The unused cross10s metadata placeholder is superseded by explicit brackets in `results/interpolation_audit.json`; no candidate or score was revised after results.

Main outputs: all42 named center scores and ranks, all24 model/profile summaries, angular contributions for every available named candidate, all12 candidate-grid aggregate log-score arrays. Each score NPZ stores named per-beam pz and valid physical indices. Other candidate per-beam values are reproducibly computed by `Native.pz` from fixed map/scan/poses; they are not falsely claimed as saved PF internals.

GT is an offline candidate/reference only. Model normalization over the uniform GT-local grid is a descriptive score concentration proxy; it is not posterior calibration or actual PF ESS. No motion prior, resampling history, original A2 masks, or particle ancestry is reconstructed.
