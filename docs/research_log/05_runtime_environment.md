# Phase 1A 永久运行环境与门槛审计

记录日期：2026-08-21（Asia/Shanghai）

## 结论

[Code]
Phase 1A 已通过。作者公开代码在永久 catkin workspace 中完成了干净构建、默认 `exploration.launch` 启动、初始建图 action 和短时 exploration action 探针。Stage、Karto、Navigator、`path_planner` 及三个规划服务在探针结束后仍存活。

[Inference]
Phase 1A 的判定是 **PASS with recorded non-fatal anomalies**。探针中出现两次作者代码的 local-replan 起终点错误，但旧路径继续执行、action 可停止、核心节点未退出，因此它不是“程序无法完成最基本运行”的阻塞项，本阶段不修算法。

完整证据目录：

```text
results/phase1/phase1a_pass_attempt_20260821/
```

## 永久 workspace 与 Python

[Code]

```text
/home/wcqw/ac-slam/catkin_ws
├── src/cpp_solver -> ../../baseline/Graph-Based_SLAM-Aware_Exploration
├── src/navigation_2d -> ../../dependencies/navigation_2d
├── src/p2os_urdf -> ../../dependencies/p2os/p2os_urdf
├── python/                 # system Python 3.8 的 workspace-local packages
├── tools/concorde/         # Concorde、Linkern
├── build/
├── devel/
├── activate.sh
└── DEPENDENCIES.lock
```

[Code]
`catkin_ws/activate.sh` 把 `/usr/bin` 放在 Conda 前，加载 workspace-local Python packages、Concorde 和 catkin `devel`，并把 `ROS_HOME`、`ROS_LOG_DIR` 固定到 workspace。CMake cache 的实际解释器为：

```text
PYTHON_EXECUTABLE:FILEPATH=/usr/bin/python3
/usr/bin/python3 --version -> Python 3.8.10
```

## 固定版本与依赖闭包

| 组件 | 固定版本/commit | 验证 |
|---|---|---|
| Code Baseline 上游 | `675299330dff0460d42c0ffd87a2f1f7f9f959da` | checkout 完整 |
| 最小兼容修复后 | `5a116671143611601736c3e4218a762a6a5a9263` | baseline worktree clean |
| navigation_2d | `96b3e1fed08823dd1dd11ddb0eeead3bd24dd686` | build/runtime 通过 |
| p2os source archive | `f5ef44a0d0324a5177f29928b84593910d5d14ec` | `/publisher` 存活 |
| NetworkX | `2.8.8` | import/runtime 通过 |
| SciPy | `1.10.1` | import/runtime 通过 |
| NumPy | `1.24.4` | import/runtime 通过 |
| tsp-solver | `0.1` | import 通过 |
| tsplib95 | `0.7.1` | import 通过 |
| PyConcorde | commit `393a235...`, package `0.2.0` | 作者旧 API 可用 |
| Concorde / Linkern | Waterloo 官方 Linux executable | map3 TSP 成功 |

[Code]
补充发现的实际依赖为 NumPy、tsplib95、Matplotlib，以及系统已有的 Stage、Karto、TF、TBB、Eigen 和 navigation ROS libraries。PyConcorde 固定到仍提供 `from concorde import Problem, run_concorde` 的历史版本，避免把当前主线不同 API 混入 baseline。

## 未执行的 sudo / 系统安装

[Code]
没有执行 sudo。以下命令只作为可选系统级替代方案记录：

```bash
sudo apt update
sudo apt install ros-noetic-p2os-urdf python3-networkx python3-scipy
sudo rosdep init
rosdep update
```

[Inference]
当前 workspace-local 依赖已闭合，Phase 1 不需要用户执行这些命令。

## 唯一 baseline 兼容修复

[Code]
独立 commit：

```text
5a11667 fix(runtime): parameterize prior map output path
```

[Code]
修改仅包含：把作者机器绝对输出路径改为 `~prior_map_save_path` ROS 私有参数；launch 默认指向 `$(find cpp_solver)/results/`；保存前创建目录；加入 `results/.gitkeep`。共 3 个文件、`10 insertions / 3 deletions`。

[Code]
未修改 TSP/`full_tsp_path`、loop insertion、loop 后 replanning、covariance/D-opt、frontier association、prior-edge update 或 Navigator 状态机。

## 干净 catkin build

[Code]
从空 `build/` 和 `devel/` 开始执行：

```bash
cd /home/wcqw/ac-slam/catkin_ws
source ./activate.sh
catkin_make -DPYTHON_EXECUTABLE=/usr/bin/python3 -DCMAKE_BUILD_TYPE=Release
```

结果为 exit code `0`，11 个 catkin packages 全部完成。保留的编译 warning 包括 `graph.cpp` 赋值运算符缺少 return、`%d`/`size_t` 格式不匹配、TBB deprecated header 和 Eigen3 catkin metadata；它们未阻止 runtime，本阶段不修。

## 默认 launch 与核心接口

[Code]
官方默认 `roslaunch cpp_solver exploration.launch` 启动 17 个节点。以下核心节点在探针前后均存活：

```text
/Stage /Mapper /Navigator /Operator /path_planner /updateDistance
/pubPath /publisher /robot_state_publisher
```

[Code]
以下关键服务存在并可调用：

```text
/StartMapping          std_srvs/Trigger
/StartExploration      std_srvs/Trigger
/Stop                  std_srvs/Trigger
/prior_graph_service   cpp_solver/RequestGraph
/path_plan_service     cpp_solver/TspPathList
/reliable_loop_service cpp_solver/ReliableLoop
```

[Code]
`/map`、`/base_pose_ground_truth`、`/tf`、`/slam_pose_graph`、Navigator plan/frontier topics 和 Karto graph-marker topics 均正常发布。`tf_echo map robot` 在探针结束后仍返回连续有效 transform。

## mapping/exploration 生命周期验证

[Code]
初始 map 为 `0.1 m` resolution、`250 x 321`，known/free/occupied cells 为 `6242 / 6036 / 206`。`/StartMapping` 返回 success；`/GetFirstMap/result` 最终 status `3`（SUCCEEDED）。初始建图后观测到 map 扩展到约 `331 x 323`，known cells 增至 `33638`；Stage ground-truth pose 发生平移和旋转，证明机器人实际执行了初始建图动作。

[Code]
随后 `/StartExploration` 返回 success，Explore action 进入 ACTIVE；Navigator 发布 high-level/nav goal，机器人继续移动，occupancy map 继续更新。约 10 秒后调用官方 `/Stop`，Explore result 为 status `2`（PREEMPTED）。这是主动结束探针，不是 planner abort。停止后核心节点、服务、map 和 TF 仍可用。

[Code]
prior graph 成功加载 map3 的 36 个 vertices；Concorde 求解成功并输出 optimal tour；默认 SLAM-aware 分支生成带 loop 标记的高层路径。因此 prior graph、TSP、`path_plan_service` 和 Navigator planner 接线均已通过最小 runtime 验证。

## 已观察但非阻塞异常

- `TF_REPEATED_DATA`：`map -> offset -> odom` 存在同时间戳重复发布；没有造成 TF 中断。
- Concorde 打印 `ERROR: No dual change in basis finding code` 后继续得到相同 lower/upper bound 和 optimal solution；本次未失败。
- KDL root-link inertia warning，以及 costmap pre-Hydro 参数 warning；节点继续运行。
- 默认 SLAM-aware exploration 探针两次打印 `Local path replan get wrong start and end vertex! Specify_end: True`；对应 path 被拒绝后 Navigator 继续旧路径，action 和节点均存活。该项升级为 Phase 2 failure-mode 候选，不在 Code Baseline 中修复。

## Phase 1A 门槛表

| 门槛 | 证据 | 判定 |
|---|---|---|
| 永久 workspace + system Python 3.8 | cache/activate 固定 | PASS |
| clean catkin build | 11 packages, exit 0 | PASS |
| 核心节点稳定存活 | 探针前后 ping 成功 | PASS |
| Stage/Karto/Navigator/path_planner | nodes/topics/services 正常 | PASS |
| prior graph 加载 | map3, 36 vertices | PASS |
| TSP 可计算 | Concorde optimal tour | PASS |
| mapping service 可调用 | GetFirstMap SUCCEEDED | PASS |
| occupancy map 正常更新 | map/known cells 显著增加 | PASS |
| pose 与 TF 正常 | GT 移动、TF 连续 | PASS |
| exploration service 可执行 | ACTIVE 后由 `/Stop` 正常 PREEMPT | PASS |
| 无持续性核心报错 | 无 crash/abort；仅记录非阻塞异常 | PASS |

[Inference]
Phase 1A 总判定：**PASS**。可以进入 Phase 1B；三组 smoke run 的结果记录在 `06_phase1_smoke_runs.md`。
