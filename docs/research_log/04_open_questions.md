# Phase 0 未决问题与 candidate failure modes

## 证据等级说明

[Code]
以下代码风险均在静态审计中可定位。

[Unknown]
它们尚未经过完整 baseline 运行和重复实验，因此只能称为 **candidate failure modes**，不能称为稳定失败、研究结论或创新点。

## Candidate failure mode 1：frontier 与 prior region 的拓扑误关联

[Code]
当前 `allocateFrontierToVertex()` 使用栅格 Manhattan distance，并对不在当前 free map 中的 vertex 乘 1.3；没有逐对运行 A*。README 也明确警告只用坐标距离可能关联错误。

[Inference]
在隔墙房间、U 形走廊、狭窄连接或长绕行环境中，坐标近但实际不可达/远距离的 vertex 可能抢走 frontier，改变 region 的“是否已覆盖”判断和高层目标顺序。

[Unknown]
默认 map3 中是否会稳定发生、发生频率和性能影响未知。Phase 1 只应记录 association line 与实际导航路径，不应先改算法。

## Candidate failure mode 2：high-level waypoint fallback 导致导航 abort

[Code]
若目标 prior vertex 不在当前 map 或其 cell 不 reachable，`getWaypointToGoal()` 会把目标拉到 map 边界，或退化为坐标上最近的 frontier center。代码注释自身标有 “may be stucked in front of a wall/corner”。

[Code]
若最终 goal 仍不可达，`RobotNavigator::createPlan()` 会 abort 整个 Explore action，而不是通知 MyPlanner 跳过该 vertex。

[Unknown]
尚不清楚默认 map3 是否会出现稳定 abort。Phase 1 应保存 goal cell、Dijkstra 建路结果、abort 原因与最后有效 frontier。

## Candidate failure mode 3：主动 loop target 没有成功闭环确认与失败恢复

[Code]
active loop 通过历史 poses（最多 7 个）或 prior vertex 周围 4 个固定偏移点执行；每个 waypoint 到达后继续下一个，完成后即回到 replanning。状态机没有订阅“新 Karto loop edge 成功”的确认。

[Code]
某个 loop waypoint 不可达时，Navigator 会直接 abort；fallback waypoint 也没有 free/map-bound 检查。

[Inference]
可能出现“规划日志标记了 loop action，但 Karto 没有形成 loop closure”，或一次不可达 loop target 终止整场探索。

[Unknown]
是否可重复、与 APE/路程的关系未知。Phase 1 必须把 planned loop、executed loop path 和 actual pose-graph loop edge 分开记录。

## Candidate failure mode 4：在线 prior connectivity 只增不减且只评估一次

[Code]
`updateDistance` 跳过所有原始 prior edges；对新 vertex pair 一旦加入 `updated_edges` 就不再重新计算。Python 端仅在新距离更短时增加 direct edge，没有删除、升高成本或失效机制。

[Inference]
地图早期不完整时得到的新连接或原始错误 edge 可能长期保留；相反，早期 A* 无路径的 pair 因未加入 `updated_edges` 可在后续 map 回调重试。

[Unknown]
当前默认地图是否受影响完全未知。按照研究原则，在 baseline 稳定前不制造 prior 错误，也不把它预设为研究方向。

## Candidate failure mode 5：论文功能与公开代码接线不完整导致趋势复现偏差

[Paper]
论文描述了实际 covariance 驱动的 degeneracy update、loop 后 SLAM-aware 全局 replanning，以及恢复满足 prior connectivity 的 TSP walk。

[Code]
当前 commit 中：实际 pose-graph covariance 被接收但未发现回写 prior edge D-opt 的路径；loop 分支的 `modify_existing_tsp_path()` 被注释；纯 TSP 返回未展开的 `tsp_path`。

[Inference]
即使环境完全正确，公开代码也可能只复现论文方法的一部分，造成三种策略差异小于或异于论文描述。

[Unknown]
必须通过 Phase 1 的 path/is_loop/pose-graph 日志验证。不能在实跑前自行补全论文功能，因为那会改变待复现的 baseline。

## 其他必须确认的问题

[Unknown]
当前仓库没有 coverage 自动计算脚本，也没有把路径长度、探索总时间、APE/RPE 统一写入一次实验目录的 runner。`pubPathGT.cpp` 只直接保存 GT/SLAM TUM trajectory，APE 需要后处理工具（论文使用 evo）。

[Unknown]
`results/` 不存在，现有 launch 以 suffix 区分输出但没有日期/map/method/seed 层级；Phase 1 需要在不改算法的前提下补实验编排与日志工具。

[Unknown]
`NearestFrontierPlanner` 的 `target_index` 在函数中未显式初始化；如果所有 frontier cells 都因 free-neighbor 条件被跳过，后续比较可能具有未定义行为。是否能在正常地图触发未知。

[Unknown]
`MyPlanner::allocateFrontierToVertex()` 的 `closest_cell_idx` 也可能在一个 cluster 没有合格 cell 时未初始化。需先用 sanitizer 或真实日志确认，不能直接认定它就是 observed crash 原因。

## Phase 0 停止点

[Inference]
目前最有价值的下一步不是选择其中一个方向做方法，而是先完成 Phase 1 的单图、三策略、可记录 smoke reproduction。只有重复日志证明某项稳定发生，才允许把 candidate failure mode 升级为 failure hypothesis。
