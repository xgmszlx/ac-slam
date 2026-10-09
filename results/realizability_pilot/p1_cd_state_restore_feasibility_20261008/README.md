# CD-B0 technical state-restore PoC — sealed incomplete attempt

Final gate: `TECHNICALLY_INCOMPLETE`. See [research record](../../../docs/research_log/75_cd_state_restore_backend_feasibility.md) and `analysis/final_gate.json`.

This attempt remains frozen. The worker's header-sequence assertion failed on the first continuous publication. No checkpoint/restore trial exists. Do not delete the existing row or rerun the original protocol to obtain a passing result.

## Evidence layout

- `audit/`: ROS 1 source/restore audit, source hashes and observation patch, dependency relocation patch, build/runtime provenance, before/after protected-tree and production-binary hashes.
- `protocol/`: preregistered one-input matrix and its hash, frozen before the first replay.
- `technical/`: exact H/C copies, unchanged upstream parameters, frozen runner/comparison tools, actual build/run logs, checkpoint NOT_EXECUTED records and offline failure tests.
- `analysis/`: final incomplete gate, unmeasured restore comparisons and complete local artifact hashes.

The permanent isolated workspace is `/home/wcqw/ac-slam_cd_b0_ws`, including extracted dependencies and compiled source. It is not the production workspace and is not vendored into this repository. Its source, packages and selected executable/libraries are identified by SHA. ROS internal logs remain locally under the result tree and are hashed. No checkpoint `.data` / `.posegraph` files were created.

## Safe read-only review commands

```bash
source results/realizability_pilot/p1_cd_state_restore_feasibility_20261008/technical/environment.sh
/usr/bin/python3 results/realizability_pilot/p1_cd_state_restore_feasibility_20261008/technical/test_b0.py
/usr/bin/python3 results/realizability_pilot/p1_cd_state_restore_feasibility_20261008/technical/test_publisher_forensic.py
```

Both tests are offline; they publish no ROS scans. The second invokes the installed rospy publisher method with an in-memory transport to reproduce pre-increment serialization. Existing source files produce ResourceWarnings for read handles; they remain unchanged because their hashes are frozen. Those warnings are not the runtime failure.

## Source/build reconstruction for review

Pinned upstream ROS 1 package: `slam_toolbox` 1.5.7, official tag commit `1b18cacfa6971bd9c3f8fdd965d7baeecffbedf0`. ROS source tar SHA `f254dd7122cd58d032e1575065e4aa2030a9451d614e18b2f7f1634d27315059`. Official-tag files were individually compared to the package source. Extract the package source into a separate technical workspace, apply `audit/observation.patch` with its candidate-relative paths, and use locally extracted dependency package versions in `audit/isolated_build_manifest.json`. The only dependency-file change is the relocation in `audit/isolation_dependency.patch`.

Original isolated build command:

```bash
source /home/wcqw/ac-slam/results/realizability_pilot/p1_cd_state_restore_feasibility_20261008/technical/environment.sh
cd /home/wcqw/ac-slam_cd_b0_ws
catkin_make --force-cmake -DPYTHON_EXECUTABLE=/usr/bin/python3 -DCMAKE_BUILD_TYPE=Release \
  -Dgflags_DIR=/home/wcqw/ac-slam_cd_b0_ws/apt_root/usr/lib/x86_64-linux-gnu/cmake/gflags -j2 -l2
```

This is a construction recipe, not authorization to restart the sealed replay matrix. A future adapter-only amendment needs a new protocol ID/hash and explicit scope. Old CD/v14 gates are unaffected.
