# ROS 1 compatibility

[Config] Ubuntu 20.04, ROS Noetic, system Python 3.8.10, GCC 9.4.0. Baseline `6a0a5b89227d560c5bda2a2b2ef6b58ca96b2ff3`. Candidate is ROS 1 `slam_toolbox` 1.5.7, official tag commit `1b18cacfa6971bd9c3f8fdd965d7baeecffbedf0`; current `noetic-devel` ref observed `8a754bb37485c598064dd1e5d00057ece4e3891d`. The tag has three ROS 1 package directories; the mapping package uses catkin/roscpp and `slam_toolbox_msgs`, not ROS 2 APIs.

[Source] The official release repository records Noetic 1.5.7-1 (21 December 2022): <https://github.com/SteveMacenski/slam_toolbox-release>. Pinned source: <https://github.com/SteveMacenski/slam_toolbox/tree/1b18cacfa6971bd9c3f8fdd965d7baeecffbedf0/slam_toolbox>. ROS package metadata: <https://index.ros.org/p/slam_toolbox/>.

[Code] Source was retrieved as the ROS release source tar from the Tsinghua ROS mirror after GitHub full/filtered clone and archive transfers stalled. Its SHA is recorded in `upstream_source_provenance.json`. Audited files were separately downloaded from official `raw.githubusercontent.com` at 1.5.7 and checked byte-for-byte against release source. Incomplete downloads were not used as source. The executable is compiled from the audited source, not the downloaded distribution executable.

[Config] Independent workspace `/home/wcqw/ac-slam_cd_b0_ws`. Missing Ceres/glog/gflags/ATLAS, `slam_toolbox_msgs` and sparse bundle packages were downloaded and extracted into this workspace's `apt_root`; no sudo or system package installation. Ceres imported-link path required one local relocation fix (`isolation_dependency.patch`). Production catkin workspace is absent from the build/runtime environment. The selected binary and actual loaded library paths/hashes are independently recorded.

[Code] Synchronous mapping still has a worker thread and TBB Karto matching; Ceres 1.5.7 hard-codes `options_.num_threads=50`. This PoC makes no claim of a single-thread backend, and those settings are unchanged. No matcher threshold, search grid, keyframe threshold, or solver option was tuned. Official `mapper_params_online_sync.yaml` is preserved byte-for-byte.

[Unknown] Binary reproducibility across compilers, machines, longer histories and different scan inputs is outside this one-input PoC.
