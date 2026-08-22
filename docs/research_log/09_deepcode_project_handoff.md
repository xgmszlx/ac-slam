# Stage A: DeepCode Project Handoff Audit

Audit date: 2026-08-22 (Asia/Shanghai)

## 0. Repository state at audit time

[Code]

| Repository | Path | Branch | HEAD | Note |
|---|---|---|---|---|
| ac-slam (main) | `/home/wcqw/ac-slam` | `main` | `3db06ddc252a25cf9819b334d5530beb8577aaa6` | single commit "publish active SLAM reproduction work"; only untracked `.vscode/` |
| Graph-Based baseline | `baseline/Graph-Based_SLAM-Aware_Exploration` | `master` | `211642d66c587419253cf90f0e5ecc7da520f46e` | upstream `6752993` -> `5a11667` (runtime compat) -> `2cfe168` (seed control + TSP record) -> `211642d` (loop-boundary observation logs); untracked: `results/*.g2o`, `__pycache__` |
| navigation_2d (incl. nav2d_karto / OpenKarto) | `dependencies/navigation_2d` | `main` | `96b3e1fed08823dd1dd11ddb0eeead3bd24dd686` | grafted clone; also mirrored at `catkin_ws/src/navigation_2d` |
| pyconcorde | `dependencies/pyconcorde` | `pyconcorde-subprocess-main` | `393a235a127dc4e887e77f1c2e7c5bd5cd28369c` | pinned old API `from concorde import Problem, run_concorde` |
| p2os | `dependencies/p2os` | n/a (source archive) | `f5ef44a0d0324a5177f29928b84593910d5d14ec` | pinned source, provides `p2os_urdf` |

[Code]
`catkin_ws/src/cpp_solver` is a symlink to `baseline/Graph-Based_SLAM-Aware_Exploration`; `catkin_ws/src/navigation_2d` mirrors `dependencies/navigation_2d`. No separate OpenKarto git repository exists; OpenKarto source is vendored inside `dependencies/navigation_2d/nav2d_karto/OpenKarto/`.

## 1. Project purpose

[Inference]
这个项目不是在做“新的 SLAM 后端”、“深度学习”或“强化学习”。它是一个**主动 SLAM（SLAM-aware autonomous exploration）的失败机制诊断研究**，基于一个强 baseline：Graph-Based SLAM-Aware Exploration With Prior Topo-Metric Information（作者公开代码 + 必要环境兼容修复 + observation-only instrumentation）。

[Inference]
研究母问题可以表述为：

> Graph-Based 高层规划器在 prior topo-metric graph 上做 TSP 排序，并用 D-opt/谱图指标选择 informative active-loop 动作；机器人被派回历史区域，期望 Karto 建立新的 loop closure constraint，从而改善定位和 pose-graph reliability。但实测中，规划层认为值得执行的 active loop 在机器人真正回访之后，**并不稳定转化为 Karto 后端真实接受的 loop closure**。

[Inference]
当前研究的确认问题是：

> 高层预测的 active-loop information value，为什么没有稳定兑现为 SLAM 后端真实可实现的 loop closure？

[Inference]
这不是最终论文创新点，而是一个 **confirmed research failure question**。研究进程当前停在“诊断具体失败机制”这一步，尚未进入“设计改进算法”。

## 2. System architecture

[Code]
真实数据流（根据 `01_code_architecture.md` 与源码核验）：

```text
Stage (Pioneer3AT + 2D LiDAR, world/map3/map3.world)
  launch/exploration.launch:39-42
        |
        | /base_scan, /odom, /base_pose_ground_truth, /tf
        v
nav2d_karto::MultiMapper (receiveLaserScan -> OpenMapper::Process)
        |
        | /map, /slam_path, /slam_pose_graph, /Mapper/closure_edges(marker), map->odom TF
        +--------------------------+
        |                          |
        v                          v
RobotNavigator                 path_planner.py
 (preparePlan, frontier       (read_drawio_to_nx -> prior graph,
  plugin MyPlanner /           all-pairs Dijkstra -> open TSP ->
  NearestFrontierPlanner)      SLAM-aware loop insertion via
        |                      offline_evaluate_tsp_path/greedy_tsp_update)
        |  prior_graph_service / path_plan_service / reliable_loop_service
        v
Exploration plugin (frontier detection / vertex allocation / reliable-loop state machine)
        |
        v
RobotNavigator::createPlan (Dijkstra on inflated occupancy grid) -> Operator -> /cmd_vel
        |
        v
Stage robot -> new SLAM observations -> back to Karto
```

### 关键 file/function/topic/service 映射

| 阶段 | 文件 / 函数 | 主要输入 | 主要输出 |
|---|---|---|---|
| 仿真与传感器 | `launch/exploration.launch`; `world/map3/map3.world` | map3 位图、初始位姿 `(-28,-28,0)` | `/base_scan`, `/odom`, GT, `/tf` |
| SLAM 前端 | `dependencies/navigation_2d/nav2d_karto/src/MultiMapper.cpp::receiveLaserScan` -> `OpenKarto/source/OpenMapper.cpp::OpenMapper::Process` | 激光 + odom/TF | pose graph, `map->odom` |
| keyscan 判定 | `OpenMapper::HasMovedEnough` (MinimumTravelDistance=1.0 m / MinimumTravelHeading=0.52 rad) | 上一 keyscan 位姿 | 是否产生新 keyscan |
| occupancy map | `MultiMapper::sendMap/updateMap` | Karto processed scans | `/map`, `get_map` service |
| pose graph 发布 | `MultiMapper::publishPoseGraph` | Karto vertices/edges | `/slam_pose_graph` (custom incremental), `/slam_path` (full) |
| prior graph 加载 | `scripts/read_drawio_to_nx.py::build_prior_map_from_drawio` | `world/map3/map3.xml`, `map_width` | NetworkX 无向图 (36 vertices) |
| prior graph 对齐 | `PathPlanner.align_prior_map_with_robot` | draw.io 坐标 + 机器人初始位姿 | 以机器人初始位姿为原点的坐标 |
| prior graph 服务 | `PathPlanner.handle_prior_graph` | 空请求 | vertex/edge 数组 (`/prior_graph_service`, `RequestGraph.srv`) |
| TSP 距离矩阵 | `scripts/offline_tsp_evaluation.py::get_distance_matrix_for_new_tsp_solver` | prior graph | all-pairs shortest-distance 矩阵 |
| TSP 求解 | `PathPlanner.solve_tsp_path` / `concorde_tsp_solver` | 距离矩阵、起点、seed | open-TSP 顺序 `tsp_path` |
| 连通 walk | `connect_tsp_path` | TSP 顺序、prior graph | `full_tsp_path` |
| SLAM-aware loop 选择 | `offline_evaluate_tsp_path` / `greedy_tsp_update` | `full_tsp_path`、固定 edge information | 插入 loop target 的路径 + `is_loop` |
| loop 执行服务 | `PathPlanner.handle_reliable_loop` | goal_vertex | 历史 pose 序列（最多 7 个）(`/reliable_loop_service`, `ReliableLoop.srv`) |
| 高层目标选择 | `src/MyPlanner.cpp::findExplorationTarget` | 地图、机器人 cell、TSP/loop 状态 | goal cell / loop 状态 |
| 主动回环执行 | `MyPlanner::performReliableLooping` / `setReliableLoopPath` | loop vertex、历史 poses | 依次发给低层导航的历史 pose waypoint |
| 全局栅格路径 | `RobotNavigator::createPlan` | goal cell、膨胀 occupancy grid | cost-to-go map |
| 低层控制 | `RobotNavigator::generateCommand` + `nav2d_operator::Operator` | cost-to-go、朝向、局部 costmap | `/cmd` -> `/cmd_vel` |
| 在线 connectivity | `src/updateDistance.cpp::occupancyGridCallback` | `/map`、prior graph | `/edge_distance` |
| 轨迹日志 | `src/pubPathGT.cpp` | GT、SLAM pose/path、odom | `/path_gt`, `/path_slam`, 两个 TUM 文件 |

### Karto loop-closure pipeline（Phase 2C 的 instrumentation 目标）

[Code]
全部位于 `dependencies/navigation_2d/nav2d_karto/OpenKarto/source/OpenMapper.cpp`（MapperGraph/OpenMapper 实现）与 `OpenKarto/source/OpenKarto/OpenMapper.h`：

1. keyscan creation —— `OpenMapper::Process`（“object is a key scan”分支，约 L2360-2412），由 `HasMovedEnough` 决定是否插入新 keyscan（L2425-2448）。
2. loop search trigger —— `Process` 在 `AddVertex`/`AddEdges` 后对每个 sensor 调用 `MapperGraph::TryCloseLoop`（约 L2407-2408）。
3. historical scan search —— `FindPossibleLoopClosure`（L2096-2143）。
4. max-distance filtering —— `LoopSearchMaximumDistance`（运行时 4.0 m）空间过滤。
5. near-linked filtering —— `FindNearLinkedScans`（L2006-2023）对当前 scan 做图 BFS，近邻 scan 显式排除出候选链。
6. candidate chain construction —— 按 scan 序扫描历史 keyscan，满足距离 + 非 near-linked 即入链。
7. minimum chain-size decision —— `chain.Size() >= LoopMatchMinimumChainSize(4)` 才返回链，否则清空。
8. coarse match —— `m_pLoopScanMatcher->MatchScan(pScan, candidateChain, bestPose, covariance, false, false)`（TryCloseLoop 内 L1575）。
9. coarse response —— `coarseResponse`（> 0.6）。
10. coarse variance —— `covariance(0,0)` 与 `covariance(1,1)`（< 0.16）。
11. alternate coarse condition —— `coarseResponse > 0.9*0.6` 且两方差 `< 0.01*0.16` 的宽松分支（L1587-1593）。
12. fine match —— 粗匹配通过后临时应用 bestPose，`m_pSequentialScanMatcher->MatchScan(...)`（L1596）。
13. fine response —— `fineResponse`（>= 0.7）。
14. accepted/rejected —— fine < 0.7 则 revert 并拒绝；否则接受。
15. `LinkChainToScan`（L1861-1882）—— 把当前 scan 链到链中最近 scan（`LinkScanMaximumDistance` 默认 10 m）。
16. `CorrectPoses`（L2147-2176）—— 触发 pose-graph 优化。
17. accepted callback/log —— `mCountLoop++; ROS_WARN("Add one Loop closure. ...")`（L1630-1631）；`PreLoopClosed`/`PostLoopClosed` 事件。
18. closure edge publishing —— `MultiMapper::onMessage` 只是 `ROS_DEBUG`；`/Mapper/closure_edges` 是**辅助 marker**，不是 accepted-loop 回调。

## 3. Baselines

[Code]
三种 baseline 的唯一控制变量是**高层目标产生机制**；底层 robot/Stage/Karto/Navigator/Operator 完全一致（同一 `exploration.launch` 不同参数）。

- **Nearest Frontier**（`strategy:=NearestFrontierPlanner`）：不用 prior graph、不解 TSP、不插入 loop target。从机器人所在 free cell 做 wavefront，聚类 reachable frontier，选择距离最小的 frontier cell。
- **Prior-TSP**（`strategy:=MyPlanner only_use_tsp:=true`）：在 prior graph 的 all-pairs shortest-distance 上解 open TSP，按 TSP 区域顺序访问；所有 `is_loop=false`，不插入主动回环。当前实现发送 `tsp_path`（未展开 `full_tsp_path`）。
- **Graph-Based SLAM-Aware**（`strategy:=MyPlanner only_use_tsp:=false`）：先构造 `full_tsp_path`，再用加权 Laplacian/D-opt 与额外路程代价选择 informative loop edges，插入历史 vertex 作为 loop target；C++ `MyPlanner` 对 `is_loop=true` 的目标走 reliable-loop 状态机（先调 `reliable_loop_service` 拿历史 pose，最多 7 个；服务失败时用 prior vertex 周围 4 个 1.5 m 偏移点的 fallback）。

## 4. Phase history

### Phase 0（环境与代码审计）

[Code]
- Ubuntu 20.04.6 / ROS Noetic / system Python 3.8.10 确认；Conda Python 3.12.7 会劫持 catkin，已固定 `PYTHON_EXECUTABLE=/usr/bin/python3`。
- 依赖补齐：workspace-local `catkin_ws/python`（NetworkX 2.8.8、SciPy 1.10.1、NumPy 1.24.4、tsp-solver、tsplib95、pyconcorde 0.2.0）；Concorde/Linkern Waterloo 官方 Linux 可执行文件；`p2os_urdf` 源码。
- 唯一 baseline 兼容修复 commit `5a11667`：把作者绝对 `prior_map.pickle` 输出路径参数化为 `~prior_map_save_path`（3 文件、10+/3-），未动任何算法。
- 记录论文-代码差异（只记录、不修复，见 §8）。
- 发现 baseline 分支的 loop 后全局 SLAM-aware replanning 是 `pass`；纯 TSP 发送 `tsp_path` 而非 `full_tsp_path`；prior-edge information 初始化为常数 `diag(0.1,0.1,0.001)`，未发现 covariance 动态回写 D-opt 的路径。

### Phase 1（Baseline reproduction）

[Code]
- 1A：永久 catkin workspace 干净构建 11 packages（exit 0），默认 launch 17 节点存活，服务/topic/TF 正常，map3 初始建图与 exploration action 探针 PASS（记录非阻塞异常：TF_REPEATED_DATA、local-replan 起终点错误两次）。
- 1B：三种 baseline 各 1 次 smoke run，均 SUCCEEDED：
  - A Nearest Frontier：832.4 s / 379.83 m / 475,702 known cells / V=495,E=740，无规划 loop。
  - B Prior-TSP：946.7 s / 396.42 m / 477,401 / V=520,E=743，0 loop。
  - C SLAM-aware：1355.9 s / 547.57 m / 478,666 / V=706,E=1020，5 个规划 loop（15/26/35/22/8 全部进入 LOOP_STARTED）。
- 关键行为确认：Prior-TSP 改变区域访问顺序；SLAM-aware 确实在 TSP 路径中插入并**实际执行**了额外 active-loop actions（5 段合计约 303.2 s / 105.76 m）。C 中仅 loop 8 有一次 `Add one Loop closure` 日志。

### Phase 2A（Paired experiment）

[Code]
- 解决公平性：Concorde 初始 TSP 有随机性，因此做 5 组 paired experiments（seeds 21001-21005），每组 Prior-TSP vs SLAM-aware，solver/seed/initial_tsp_path/full_tsp_path/predicted length/SHA-256 完全一致（`reproducibility_check.json`，5/5 pair 全部 `sha256_identical: true`）。
- 10/10 runs 全部成功；无静默重跑；2700 s 硬超时 + RSS 监控（max 1.47-1.52 GB）。
- evo 1.31.1 固定于 `evaluation/evo-1.31.1-target`；APE/RPE 采用固定协议（project to XY plane, 无后对齐/无尺度校正）。
- 结果：SLAM-aware 相对 Prior-TSP 平均 +518.0 s（+62.7%）时间、+162.5 m（+46.0%）GT 距离；APE 3/5 更好、2/5 更差；trans/rot RPE 5/5 更差（5 个 raw paired observations，未做显著性检验）。
- 核心：21 planned / 21 executed / 0 accepted Karto loop closure；21 段 loop 执行区间共 1410.6 s / 461.0 m。`Add one Loop closure` 事件在全部 run 的 rosout 中为 0（含 passive audit）。
- H1-H4：H1（loop 不产生确认约束）Supported on map3；H2（回环执行带来成本而无确认收益）Supported on map3；H3（路径不严格一致）Supported as behavioral claim（SLAM-aware normalized edit 0.098-0.244，repeated skips 7-9 次/run）；H4（loop 后 replanning 分支为 `pass`，21 个 loop 后无新全局 SLAM-aware path）Structural mechanism supported / performance impact Inconclusive。

### Phase 2B（Positive Control + 失败诊断）

[Code]
- Positive control：同一 map3、机器人、Karto、Karto 参数（4 次 attempt 的 `/Mapper` 参数 dump SHA-256 全同 `519303a8...`）。每次先跑正常 Nearest-Frontier 探索，再用独立 `/MoveTo` 客户端按 Karto history index 60,55,50,45,40,35,30 反序显式重访。4 次 attempt：3 次有效（7/7 targets），1 次无效（trial 3 target 3 timeout，不计为 Karto-negative）。3/3 有效重访都产生 accepted loop callback + 跨 cutoff 的非局部 marker edge + 历史轨迹修正。⇒ **Karto success given valid revisit = 100%**，排除“Karto 本身不能闭环”和“全局检测链失效”两个解释。
- 同时验证了检测链：positive control 中能稳定看到 accepted callback、`Add one Loop closure`、pose graph 非局部连接、轨迹修正、closure marker。⇒ Phase 2A 的 0/21 不能用“logger 看不到”解释。
- 21 个 active loop 的几何分析：21/21 进入 service 指定历史 pose 的 1 m 邻域（mean min dist 0.232 m / median 0.092 m）；但只有 10/21 同时满足 `distance<1m 且 yaw<0.52rad`；历史轨迹 overlap ratio mean 0.327 / median 0.320；high-level loop vertex → service 选择历史 pose 距离 mean 2.560 m / median 2.851 m / max 4.143 m ⇒ 存在 high-level region → service 历史 pose → 真实轨迹 → Karto candidate 的层级失配。
- 粗粒度 taxonomy：A Measurement=0；B Backend/Config=0；C Opportunity=10 Probable；D Matching=9 Probable；E Redundant-loop=0；F Unknown=2。
- 限制：Phase 2A 原始运行没有保存 candidate historical scans、exact candidate chains、chain size、rejected coarse/fine response、variance、exact matcher rejection stage/reason。因此 C/D 只能标 **Probable**。

## 5. Confirmed facts

只列有直接实验或代码证据的结论（证据来源：`07_phase2a_paired_loop_effectiveness.md`、`08_karto_loop_closure_mechanism.md`、`results/phase2*`、`per_loop_effectiveness.csv`、`reproducibility_check.json`、`passive_loop_audit.csv`、`positive_control_summary.json`、`failure_taxonomy.csv`、`aggregate_summary.json`）。

1. [Code] 5 组 paired runs（5 Prior-TSP + 5 SLAM-aware）全部成功，组内 TSP 记录（solver/seed/initial/full/length/SHA-256）完全一致。
2. [Code] 21 个 active loops 全部被规划并被实际执行（waypoints 全到达，reliable-loop service 21/21 成功，fallback=0）。
3. [Code] 21/21 loop 执行区间及全部 10 个 run 中，Karto `Add one Loop closure` accepted 事件数为 0；无任何新 edge 超过 70-scan buffer。
4. [Code] 3/3 有效 positive-control 显式重访产生 accepted loop closure；4 次 attempt 中 1 次因导航 timeout 无效（不计为 Karto-negative）。
5. [Code] 21/21 active loop 的机器人实际轨迹进入 service 指定历史 pose 的 1 m 邻域（min-distance mean 0.232 m / median 0.092 m）。
6. [Code] 仅 10/21 同时满足 1 m 位置 + 0.52 rad 朝向邻域；overlap ratio mean 0.327 / median 0.320。
7. [Code] Phase 2B 重建证据下：10 Opportunity Probable、9 Matching Probable、2 Unknown、0 Redundant、0 Measurement、0 Backend。
8. [Code] 论文-代码差异已静态确认（loop 后 replanning 为 `pass`；纯 TSP 发送 `tsp_path`；prior-edge information 常数化），这些差异**未被修复**。
9. [Code] Karto 参数在 Phase 2A 与 2B 之间保持不变，且 `/Mapper` 运行时参数 dump 一致。
10. [Code] `/Mapper/closure_edges` 不是 accepted-loop 回调；仅凭 marker 增量不能判定成功闭环。

## 6. Probable findings

1. [Inference] 10 个 loop 可能是 **Opportunity failure**（keyscan 出现，但重建不到满足 4 m / near-linked 排除 / chain size>=4 的合格历史链）。
2. [Inference] 9 个 loop 可能是 **Matching failure**（keyscan 与至少一条候选链存在，但无 accepted 事件；具体是 coarse 还是 fine 阶段被拒、response/variance 数值均未知）。
3. [Inference] 存在 high-level region → service 历史 pose → 实际轨迹 → Karto candidate 之间的层级失配（vertex 到 service pose 距离 mean 2.56 m，超出部分 candidate 生成窗口）。
4. [Inference] 朝向差异与轨迹 overlap 不足可能影响 scan matching 质量，但无 Karto 内部证据，不能直接定级。
5. [Inference] 2 个 loop 的 keyscan 批次无法与 loop 区间可靠对齐（Unknown timing cases）。

## 7. Unknowns

1. 21 个 active loop 每次 loop search 的：历史候选 scan 集合、candidate chain 内容与 size、coarse response、coarse variance、fine response、被拒的确切 matcher 阶段与原因。
2. Karto 内部 `nearLinkedScans` 集合在每个 keyscan 插入时的确切内容（Phase 2A 未保存 scan barycenter）。
3. Phase 2A 中 accepted-loop 为 0 是否在所有 21 次中都是同一失败机制（机会不足 / 匹配拒绝 / 两者混合）。
4. 失败与 yaw / overlap / A-H distance / scan gap 之间是否存在可描述的关联（目前无统计意义）。
5. 如果对失败机制做最小改进，是否能提升 closure rate（未到该阶段，禁止现在回答）。

## 8. Paper-code discrepancies（只记录，不修复）

1. [Paper/Code] 论文描述 pose-graph covariance 驱动 prior-edge D-opt 动态更新；当前代码把 prior-edge information 初始化为常数 `diag(0.1,0.1,0.001)`，未发现实际 covariance 回写 D-opt 的执行路径。
2. [Paper/Code] 论文描述 loop 后基于更新 prior graph 的全局 SLAM-aware replanning（选择新旧路径较优者）；当前 `handle_replanning()` 的 loop 分支为 `pass`，`modify_existing_tsp_path()` 调用被注释。21 个 loop 后均无第二次 SLAM-aware path。
3. [Paper/Code] 论文要求 metric-closure TSP 恢复为 prior-connectivity walk（`full_tsp_path`）；纯 TSP 分支发送 `tsp_path`。map3 上两者恰好相同，差异已静态确认但无本次行为影响。
4. [Plan/Runtime] optimizer 输出的 loop 返回 vertex 在 runtime 被 repeated-visit 逻辑跳过；实际 loop 轨迹由 reliable waypoint/fallback 决定，不严格等于输出数组。
5. [Intent/Runtime] 完成 reliable-loop waypoint 后系统直接恢复探索，不等待“新增 Karto loop edge”确认。
6. [Paper/Code] 论文对 frontier-vertex 关联的描述与实现不同：README 称 Euclidean/A*，实际是 grid-index Manhattan heuristic 加 1.3 penalty，无逐对 A*。
7. [Paper/Code] 在线 connectivity 更新只增不减：`updateDistance` 跳过原始 edge；Python 只在更短时 add edge，无 remove/invalid/超时重检机制。

## 9. Current failure chain

[Inference]
证据停止点用 `[ev]` 标注（有直接证据），`[na]` 标注（无 Karto 内部证据，Phase 2C 需要补）：

```text
SLAM-aware planner (D-opt 选择 loop vertex)          [ev: 21 planned]
   ↓
reliable-loop service 返回历史 poses (≤7)            [ev: 21/21 service OK]
   ↓
机器人回访 (waypoints 全到达, 1m 邻域)               [ev: 21/21, min-dist 0.232m]
   ↓
Karto keyscan 生成 (HasMovedEnough 门控)             [ev: 19/21 区间内有新 keyscan 批次, 2 ambiguous]
   ↓
FindPossibleLoopClosure: 4m 距离过滤                 [na]
   ↓
near-linked (BFS) 排除                              [na]
   ↓
candidate chain 构造 + chain-size>=4 检查            [na (Phase 2B 离线重建: 10/21 有链)]
   ↓
coarse scan matching (response>0.6, var<0.16)        [na]
   ↓
fine scan matching (response>=0.7)                   [na]
   ↓
accepted/rejected closure
   [ev: 0/21 accepted; 3/3 positive control accepted]
```

[Inference]
当前证据明确停在这里：**机器人确实回访了（21/21），Karto 确实接受了同样参数下的显式重访（3/3），但 21 次主动回访中 Karto 接受了 0 次。** 中间候选生成与匹配的每一级（距离过滤、near-linked 排除、chain 构造、coarse、fine）都没有内部观测，因此无法把 10 Opportunity / 9 Matching 从 Probable 升级为 Confirmed。

## 10. Current research question

[Inference]
只允许围绕：

> 为什么执行成功的 active-loop action（规划 → 回访 → waypoint 完成）没有稳定兑现为 Karto accepted loop closure？

[Inference]
Phase 2C 的唯一目标是把上面的 Probable 失败升级为 Confirmed rejection mechanism（通过 Karto 内部纯观测 instrumentation），**不是修复回环**。

## 11. Prohibited modifications（当前禁止）

[Code]
以下内容在 Phase 2C 及其之前禁止修改：

- 任何 Karto matcher threshold（LoopMatchMinimumResponseCoarse/Fine、LoopMatchMaximumVarianceCoarse、LoopMatchMinimumChainSize、LoopSearchMaximumDistance、LoopSearchSpace* 等）；
- 任何 if 条件、candidate selection/ordering、chain construction、return 值；
- 任何优化/pose correction（CorrectPoses、LinkChainToScan 行为）；
- 任何 SLAM 行为（keyscan 生成门控、scan matching、pose graph）；
- 任何 planner 行为（TSP、loop 插入、reliable-loop 状态机、skip 逻辑、replanning）；
- 任何 prior graph 内容、objective、参数（mapper.yaml、navigator.yaml、operator.yaml、ros.yaml）；
- 任何新算法实现（ML classifier、regression score、probability model、weighted loop score、threshold optimization）；
- 任何论文功能的“补全”（covariance 回写、loop 后全局 replanning 等）。

[Code]
允许的只有：observation-only instrumentation（只记录原算法已计算的中间量）、实验编排脚本、分析脚本与文档。若 instrumentation 必须改变算法控制流，则停止。

## 12. Stage A self-check

[Code]

| Check | Required | Verified from repo | Result |
|---|---|---:|---|
| Paired runs | 5 + 5 | `aggregate_summary.json` pairs=5, runs_succeeded=10 | PASS |
| Planned active loops | 21 | `aggregate_summary.json` planned_loops=21; `per_loop_effectiveness.csv` 21 rows | PASS |
| Executed loops | 21 | `per_loop_effectiveness.csv` executed_loop=True x21 | PASS |
| Accepted active closures | 0 | `per_loop_effectiveness.csv` karto_accepted_loop_events=0 x21; `passive_loop_audit.csv` accepted_loop_log_count=0 x10 | PASS |
| Positive-control valid revisits | 3 | `positive_control_summary.json` valid_completed_trials=3 | PASS |
| Positive-control accepted closures | 3 | `positive_control_summary.json` successful_trials=3 | PASS |
| Phase 2B Opportunity Probable | 10 | `failure_taxonomy_summary.json` counts["C. Opportunity failure"]=10 | PASS |
| Phase 2B Matching Probable | 9 | counts["D. Matching failure"]=9 | PASS |
| Unknown | 2 | counts["F. Unknown"]=2 | PASS |

[Inference]
**Stage A = PASS。** 仓库证据与 handoff summary 一致，无严重冲突。可以进入 Stage B（Phase 2C）。

## 13. Next task (Stage B preview)

[Inference]
Phase 2C：在 Karto 内部（`OpenMapper.cpp` 的 `TryCloseLoop` / `FindPossibleLoopClosure` 路径）加入默认关闭（`enable_loop_diagnostics=false`）的 observation-only 结构化诊断，输出 `karto_loop_diagnostics.jsonl`；先跑 1 个有效 positive-control 验证 instrumentation 能看到 `candidate → chain → coarse → fine → accepted` 且与 accepted callback 一致；再跑 map3 SLAM-aware seeds 21001-21005；对每个 active loop 输出 `active_loop_confirmed_taxonomy.csv`，把旧 Phase 2B Probable 标签升级为 Confirmed rejection mechanism（C1-C4/D1-D5/S/U），生成 `failure_transition_matrix.csv`，并撰写 `12_phase2c_failure_mechanism.md`。
