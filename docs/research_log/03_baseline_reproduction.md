# Phase 0 复现准备与官方 demo

## 当前状态

[Code]
Phase 0 只完成静态审计与临时编译。三种 baseline 尚未正式运行，因此没有 coverage、路径长度、探索时间或 APE 结果。

[Inference]
当前状态是：**源码可编译，但官方 demo 不能直接启动。** 已知阻塞项见 `00_environment.md`。

## 官方最小启动命令

[Code]
README 给出的官方流程需要一个已经构建并 source 的 catkin workspace。默认 launch 是 map3 + `MyPlanner` + `only_use_tsp=false`，即 Graph-Based SLAM-Aware。

终端 1：

```bash
cd <catkin_ws>
source /opt/ros/noetic/setup.bash
source devel/setup.bash
roslaunch cpp_solver exploration.launch
```

[Code]
依赖齐全时，终端 1 应启动 Stage、Karto Mapper、Navigator、Operator、Python path planner、轨迹/edge 更新节点、robot model publishers 与 RViz。关键正常信号应包括：

- `path_planner` 打印 prior map vertex 数和初始 TSP path；
- `MyPlanner` 成功调用 `prior_graph_service`、`path_plan_service`、`reliable_loop_service`；
- Navigator 报告成功载入 `MyPlanner`；
- Stage 中出现 Pioneer3AT，RViz 能看到 `/map`、机器人、prior graph 与 TSP path。

终端 2：

```bash
cd <catkin_ws>
source /opt/ros/noetic/setup.bash
source devel/setup.bash
rosservice call /StartMapping
rosservice call /StartExploration
```

[Code]
`/StartMapping` 会向 Navigator 的 `GetFirstMap` action 发送目标：机器人先短暂前进，再原地转一圈生成初始地图。服务响应只表示 action 已发送，最终成功/失败应从 Navigator 日志确认。

[Code]
`/StartExploration` 会向 `Explore` action 发送目标。正常情况下 Navigator 周期性获取 `/map`、调用 exploration plugin、创建 Dijkstra plan 并经 Operator 驱动机器人。

## 当前机器实际会在哪里失败

[Code]
当前默认 launch 在 XML 解析阶段就会因找不到 `p2os_urdf` 失败。

[Code]
补上 `p2os_urdf` 后，`path_planner.py` 仍会因系统 Python 缺少 NetworkX/SciPy/tsp-solver/pyconcorde，或因作者绝对 `prior_map.pickle` 路径不存在而退出。

[Code]
如果直接按当前 shell 执行 `catkin_make`，Conda Python 3.12 会先导致 catkin 配置失败。

[Inference]
因此现在运行上述 demo 只会重复已知环境失败，不会产生有科研意义的 baseline 结果；Phase 0 在这里停止是合理的。

## 三种 baseline 的建议 launch 参数（Phase 1 才执行）

[Code]
同一 map3、robot、sensor、Karto 和起点下，可用以下参数切换主要策略：

```bash
# A: Nearest Frontier
roslaunch cpp_solver exploration.launch \
  strategy:=NearestFrontierPlanner \
  only_use_tsp:=true \
  suffix:=_NearestFrontier_map3

# B: Prior-TSP
roslaunch cpp_solver exploration.launch \
  strategy:=MyPlanner \
  only_use_tsp:=true \
  suffix:=_PriorTSP_map3

# C: Graph-Based SLAM-Aware
roslaunch cpp_solver exploration.launch \
  strategy:=MyPlanner \
  only_use_tsp:=false \
  suffix:=_SLAMAware_map3
```

[Inference]
对 Frontier 模式设置 `only_use_tsp` 不会改变 `NearestFrontierPlanner` 自身，但当前通用 launch 仍会启动 Python `path_planner` 与 `updateDistance`。Phase 1 应决定是保留完全相同的节点集合，还是为 Frontier 建一个仅移除无关节点的兼容 launch；无论如何必须记录差异，不能让后台节点崩溃被当作“正常”。

## Phase 1 最小复现任务

[Inference]
等待用户确认后，Phase 1 应只做以下最小闭环：

1. 建立永久 catkin workspace，并固定系统 Python 3.8；
2. 补齐依赖、参数化作者绝对路径、建立结果目录；
3. 先只启动默认 map3，不开始探索，验证所有节点/服务/topic/TF 存活；
4. 手动触发 `StartMapping`，验证初始 map 和定位；
5. 每种方法先跑 1 次 smoke test，确认能启动、运动、停止并保存轨迹；
6. 若三种都稳定，再用相同起点与配置做少量重复运行；
7. 自动记录 APE、路径、时间和 coverage；任何核心节点 crash 或探索频繁 abort 时停止扩展实验。

[Unknown]
Stage 的随机性来源、Concorde 可重复性、Karto scan matching 的运行间波动尚未实测。Phase 1 必须先确认 seed 能控制哪些模块，不能仅在目录名中写 seed。

## Phase 1 通过门槛

[Inference]
最小通过条件不是复现论文表格的绝对数值，而是：

- 三种策略在同一 map3 上均能完成至少一次探索；
- Prior-TSP 的 high-level visit order 与 Nearest Frontier 明显不同；
- SLAM-aware 的 `is_loop`、loop waypoint 和实际 Karto loop edge 能被分别记录；
- 每次运行自动保存 commit、命令、配置、stdout/stderr、轨迹、路径长度、时间、coverage 与 APE；
- 若公开 commit 的行为与论文描述不一致，保留原始日志并明确报告，不用核心算法修改“补出”预期趋势。
