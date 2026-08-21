# Phase 0 代码架构与数据流

## 给初学者的整体解释

[Paper]
论文把系统分为两层：高层在 prior topo-metric graph 上给出区域访问顺序与主动回环动作；低层使用实时 SLAM occupancy map、frontier 和导航器把高层意图变成机器人运动。

[Code]
当前开源代码中的真实主流程是：

```text
Stage 中的 Pioneer3AT + 2D LiDAR
  launch/exploration.launch:39-42
  world/map3/map3.world
        |
        | /base_scan, /odom, /base_pose_ground_truth, TF
        v
nav2d_karto::MultiMapper
  dependencies/navigation_2d/nav2d_karto/src/MultiMapper.cpp
  receiveLaserScan() -> Karto Process() -> sendMap()/publishPoseGraph()
        |
        | /map, /slam_path, /slam_pose_graph, map->odom TF
        +--------------------------+
        |                          |
        v                          v
RobotNavigator                 path_planner.py
  preparePlan()                  读取 draw.io XML prior graph
  获取并膨胀 occupancy map         对齐坐标、计算 edge weight
        |                        all-pairs shortest paths -> open TSP
        |                          |                         |
        |                          | only_use_tsp=true       | false
        |                          |                         v
        |                          |                 D-opt/谱图指标筛选 loop edge
        |                          +-------------+-----------+
        |                                        |
        |          prior_graph_service / path_plan_service / reliable_loop_service
        v                                        |
Exploration plugin <-----------------------------+
  NearestFrontierPlanner 或 MyPlanner
  检测 frontier；MyPlanner 还把 frontier 分配给 prior vertex
        |
        | 返回 occupancy-grid 中的 goal cell
        v
RobotNavigator::createPlan()
  在膨胀后的 occupancy grid 上从 goal 反向做 Dijkstra
        |
        | /cmd (nav2d_operator::cmd)
        v
nav2d_operator::Operator
  局部避障与速度命令
        |
        | /cmd_vel
        v
Stage 差速机器人
```

## 文件、函数、输入与输出映射

| 阶段 | 真实文件/函数 | 主要输入 | 主要输出 |
|---|---|---|---|
| 仿真与传感器 | `launch/exploration.launch:39-42`；`world/map3/map3.world` | map3 位图、机器人初始位姿 | `/base_scan`、`/odom`、ground truth、TF |
| SLAM | `dependencies/navigation_2d/nav2d_karto/src/MultiMapper.cpp::receiveLaserScan` | 激光、odom/TF | Karto pose graph、map->odom |
| Occupancy map | `MultiMapper.cpp::sendMap/updateMap` | Karto processed scans | `/map`、`get_map` 服务 |
| Pose graph 增量 | `MultiMapper.cpp::publishPoseGraph` | Karto vertices/edges/covariance | `/slam_pose_graph` |
| Prior graph 读取 | `scripts/read_drawio_to_nx.py::build_prior_map_from_drawio` | `world/<map>/<map>.xml`、`map_width` | NetworkX 无向图 |
| Prior graph 对齐 | `PathPlanner.align_prior_map_with_robot` | draw.io 坐标、Stage 初始位姿 | 以机器人初始位置为原点的 vertex 坐标 |
| Prior graph 服务 | `PathPlanner.handle_prior_graph` | 空服务请求 | vertex id/坐标、edge endpoints |
| TSP 距离矩阵 | `offline_tsp_evaluation.py::get_distance_matrix_for_tsp` | prior graph 与 edge weight | all-pairs Dijkstra 距离矩阵 |
| TSP 求解 | `PathPlanner.solve_tsp_path` | 距离矩阵、起点、solver 参数 | 每个 prior vertex 一次的 open-TSP 顺序 |
| 恢复连通 walk | `connect_tsp_path` | TSP 顺序、prior graph | 插入 shortest-path 中间 vertex 的 `full_tsp_path` |
| SLAM-aware loop 选择 | `offline_evaluate_tsp_path`、`greedy_tsp_update` | `full_tsp_path`、固定 edge information | 插入 loop target 的高层路径与 `is_loop` |
| Frontier 检测 | `MyPlanner::findFrontiers/findCluster` 或 `NearestFrontierPlanner` 同名函数 | 膨胀 occupancy grid、机器人 cell | frontier clusters、wavefront distance |
| Frontier 到 vertex | `MyPlanner::allocateFrontierToVertex` | frontier center、prior vertex 坐标 | `frontier_to_vertex`、`vertex_to_frontiers` |
| 高层目标选择 | `MyPlanner::findExplorationTarget` | 当前地图、机器人 cell、TSP/loop 状态 | nav2d exploration status + goal cell |
| 主动回环执行 | `setReliableLoopPath`、`performReliableLooping` | prior loop vertex、历史 SLAM poses | 依次送给低层导航的历史 pose waypoint |
| 全局栅格路径 | `RobotNavigator::createPlan` | goal cell、膨胀 occupancy grid | 当前 cell 到 goal 的 Dijkstra cost-to-go |
| 低层控制 | `RobotNavigator::generateCommand` + `nav2d_operator` | cost-to-go、当前朝向、局部 costmap | `/cmd`，继而 `/cmd_vel` |
| 新 connectivity | `src/updateDistance.cpp::occupancyGridCallback` | `/map`、prior graph | 新的 `/edge_distance` 消息 |
| 轨迹日志 | `src/pubPathGT.cpp` | ground truth、SLAM pose/path、odom | `/path_gt`、`/path_slam`、两个 TUM 文本文件 |

## ROS 节点之间如何连接

[Code]
`launch/exploration.launch` 默认同时启动：Stage、map_server、Operator、Mapper、Navigator、三个 nav2d client、`pubPath`、`updateDistance`、exploration button server、Python `path_planner`、robot model publishers 和 RViz。

[Code]
`Navigator` 通过 pluginlib 载入 `exploration_strategy`：

- `NearestFrontierPlanner` 来自 `dependencies/navigation_2d/nav2d_exploration`；
- `MyPlanner` 来自主仓库 `exploration.xml` 与 `src/exploration_plugins.cpp`。

[Code]
`MyPlanner` 构造时会等待并调用三个 Python 服务：

- `prior_graph_service`：获取 prior graph；
- `path_plan_service`：获取或重规划高层路径；
- `reliable_loop_service`：获取某 prior region 中历史 pose 序列。

[Code]
`path_planner.py` 订阅 `/slam_pose_graph`，把实际 Karto pose 分配给最近的 prior vertex，并保存 pose graph；它还订阅 `/edge_distance`，接收在线发现的新 prior connectivity。

## 三种 baseline 的实际差异

### Nearest Frontier

[Code]
`strategy:=NearestFrontierPlanner` 时，Navigator 使用作者版 nav2d 的 `NearestFrontierPlanner::findExplorationTarget`。它从机器人所在 free cell 做 wavefront 搜索，聚类 reachable frontier，并在所有合格 frontier cell 中选择 `mPlan` 距离最小者。

[Code]
它不读取 prior graph，不解 TSP，不主动插入 loop-closing target。

### Prior-TSP

[Code]
`strategy:=MyPlanner only_use_tsp:=true` 时，Python 先按 prior graph 的 all-pairs shortest distance 求 open TSP；`modify_tsp_path()` 不执行 D-opt loop 选择，所有 `is_loop` 都为 false。

[Code]
C++ `MyPlanner` 按 TSP 指定的 region 顺序工作：先向目标 region 靠近，再优先探索分配给该 region 的 frontier；已扫描且无 frontier 的非-loop vertex 可跳过。

[Code]
当前实现的纯 TSP 响应发送 `self.tsp_path`，不是已经插入 shortest-path 中间 vertices 的 `self.full_tsp_path`。这与论文描述的“恢复实际 prior-graph walk”不完全一致，需在 Phase 1 通过 RViz 路径和日志确认实际影响。

### Graph-Based SLAM-Aware

[Code]
`strategy:=MyPlanner only_use_tsp:=false` 时，先构造 `full_tsp_path`，再以该 walk 形成的抽象 pose graph 为基础，用 weighted Laplacian/D-opt 指标与额外路程代价选择 loop edges。

[Code]
选中 loop edge 后，高层路径在当前 vertex 后插入一个历史 vertex，再回到当前 vertex；C++ 端把该插入点标为 loop target，并尝试沿该 region 内以前的 SLAM pose 序列运动以促成 Karto loop closure。

[Inference]
因此三者的主要控制变量是高层目标产生机制：全局最近 frontier、prior-TSP 区域顺序、TSP 加信息性 loop 动作。低层 robot、Stage、Karto、Navigator 和 Operator 应保持一致。

## 当前代码与最初示意流程的修正

[Code]
“Occupancy Map -> Frontier -> Prior Graph -> TSP”并不是严格的在线先后顺序。真实实现中 prior graph 和初始 TSP 在 `path_planner.py` 启动时先离线生成；每次在线规划才从当前 occupancy map 检测 frontier，并把 frontier 分配给已经存在的 prior vertices。

[Code]
更准确的表达是：

```text
prior XML -> prior graph -> initial TSP -> optional SLAM-aware loop insertion
                                      |
SLAM -> occupancy map -> frontier ----+-> high-level region/loop decision
                                           |
                                           v
                                    occupancy-grid navigation
```
