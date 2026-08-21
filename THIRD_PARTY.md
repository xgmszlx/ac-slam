# Third-party source and data boundary

This repository vendors source snapshots needed to reproduce the measured
workspace. Each component remains under its upstream license.

| Path | Upstream | Pinned revision | License evidence |
|---|---|---|---|
| `baseline/Graph-Based_SLAM-Aware_Exploration` | https://github.com/bairuofei/Graph-Based_SLAM-Aware_Exploration | upstream `675299330d...` plus local compatibility/observation commits through `211642d66c...` | vendored `LICENSE` |
| `dependencies/navigation_2d` | https://github.com/bairuofei/navigation_2d | `96b3e1fed08823dd1dd11ddb0eeead3bd24dd686` | vendored `LICENSE` |
| `dependencies/pyconcorde` | https://github.com/jvkersch/pyconcorde | `393a235a127dc4e887e77f1c2e7c5bd5cd28369c` | vendored `COPYING` |
| `dependencies/p2os` | ROS p2os source snapshot | `f5ef44a0d0324a5177f29928b84593910d5d14ec` | vendored package license files |

Concorde and Linkern executables are not committed. The measured Linux
executables were downloaded from the University of Waterloo URLs recorded in
`catkin_ws/DEPENDENCIES.lock`; reconstruction instructions live in
`catkin_ws/tools/concorde/README.md`.

The top-level `results/` directory contains experiment outputs generated in
Stage from this workspace. It does not include external rosbag datasets.
