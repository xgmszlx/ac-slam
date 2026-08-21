# Phase 0 算法理解：21 个核心问题

## Prior graph

### 1. prior graph 从哪里加载？

[Code]
默认 `launch/exploration.launch` 把 `world/map3/map3.xml` 作为 `/path_planner/xml_path`。`PathPlanner.__init__()` 调用 `build_prior_graph_with_xml()`，后者调用 `read_drawio_to_nx.py::build_prior_map_from_drawio()` 解析 draw.io 导出的 XML。

[Code]
XML 中以 `ellipse...` 开头的 `mxCell` 被当作 vertex，以 `edgeStyle...` 开头并带 source/target 的 `mxCell` 被当作 edge。三个孤立圆不是环境 vertex，而是坐标定标点；完成缩放与居中后会由 `remove_isolated_nodes()` 删除。

### 2. vertex 和 edge 如何表示？

[Code]
Python 高层使用 `networkx.Graph`：vertex id 是从 0 开始的整数并有 `position=(x,y)`；edge 是无向边，至少有 `weight`，随后还会添加 `information` 与 `d_opt`。

[Code]
C++ `MyPlanner` 通过 `RequestGraph.srv` 获取 vertex/edge 数组，再在 `Graph` 类中建立 `Graph::Vertex` 与 undirected `Graph::Edge`。C++ 图主要用于坐标查找、可视化和 frontier 分配；SLAM-aware 谱计算发生在 Python NetworkX 图上。

### 3. edge weight 如何计算？

[Code]
draw.io 坐标先按 `actual_map_width / drawio_width` 缩放到米，y 轴翻转并以三枚定标点定义的地图中心平移；之后 `add_edge_distance_as_weight()` 把每条原始 prior edge 的两个 endpoint 欧氏距离作为 `weight`。

[Code]
`updateDistance.cpp` 还会对地图中同时已知且周围 8 邻域全 free 的**非已有 vertex pair**运行栅格 A*，得到路径长度并发布 `/edge_distance`。Python 只在这个新距离短于当前图上 shortest-path distance 时添加 direct edge。

### 4. prior graph 如何与机器人坐标系对齐？

[Code]
第一步由 `move_graph_to_border()` 把 draw.io 图转换到以环境中心为原点、单位为米的坐标。第二步由 `PathPlanner.align_prior_map_with_robot()` 对每个 vertex 执行 `(x, y) <- (x-robot_x, y-robot_y)`。

[Code]
默认 map3 的 Stage robot pose 是 `[-28,-28,0]`；相减后 prior graph 使用以机器人初始位姿为原点的 map 坐标。ground-truth logger 也从 Stage ground truth 中减去相同初始平移。

## TSP

### 5. all-pairs shortest path 在哪里计算？

[Code]
`scripts/offline_tsp_evaluation.py` 的以下函数调用 `nx.all_pairs_dijkstra_path_length(..., weight='weight')`：

- `get_distance_matrix_for_tsp()`；
- `get_distance_matrix_for_submap_tsp()`；
- `get_distance_matrix_for_new_tsp_solver()`。

### 6. TSP distance matrix 从哪里得到？

[Code]
初始 TSP 的矩阵来自 `get_distance_matrix_for_tsp(self.prior_graph)`。矩阵中的任意两个 vertex 距离不是直线距离，而是 prior graph 上的加权 shortest-path length。

[Code]
若选择 `tsp-solver`，代码把下三角矩阵交给 `solve_tsp(..., endpoints=(start_idx,None))`；默认 `concorde` 路径则由 `get_distance_matrix_for_new_tsp_solver()` 生成对称矩阵，再由 `concorde_tsp_solver()` 转换成 open-TSP 问题。

### 7. TSP 解出来以后，如何恢复真正经过的 prior vertices？

[Code]
`connect_tsp_path(graph, tsp_path)` 检查每对连续 TSP vertex。如果二者不是 direct edge，就调用 `nx.shortest_path(..., method='dijkstra')`，把中间 vertices 插入，得到 `full_tsp_path`。

[Paper]
论文 Sec. IV-B 明确描述了同样过程：先在 metric closure 上解 TSP，再用 G-prior 中的 shortest paths 恢复满足 connectivity 的 walk。

[Code]
但当前纯 TSP 分支最终发送的是 `self.tsp_path` 而不是 `self.full_tsp_path`；只有 SLAM-aware 的初始 loop 评估明确使用 `full_tsp_path`。这是待实跑确认的实现差异。

## SLAM-aware

### 8. Graph-Based 相比纯 TSP 多了什么？

[Paper]
纯 TSP 只最小化覆盖全部 prior vertices 的路径长度。Graph-Based 方法在该路径上额外选择能提高抽象 pose graph 全局可靠性、且额外路程划算的 loop-closing actions。

[Code]
开关是 `/path_planner/only_use_tsp`。为 false 时，`modify_tsp_path()` 调用 `offline_evaluate_tsp_path()`，返回插入 loop target 的 `curr_path` 和等长 `is_loop` 数组；C++ `MyPlanner` 对 `is_loop=true` 的目标走专门的 reliable-loop 状态机。

### 9. D-optimality / graph spectral information 在哪里计算？

[Paper]
论文以观测 Fisher information matrix 的 D-optimality 近似为按 edge information 加权的 reduced graph Laplacian 的 D-optimality，从而用图拓扑低维地估计 pose graph reliability。

[Code]
主要函数为：

- `utils.py::get_d_opt()`：information matrix 特征值几何均值；
- `utils.py::get_normalized_weighted_spanning_trees()`：weighted reduced Laplacian 特征值几何均值；
- `offline_tsp_evaluation.py::offline_evaluate_tsp_path()`：构造抽象 TSP pose graph；
- `greedy_tsp_update()`：用 Laplacian inverse/effective resistance 增量评价候选 loop edge。

[Code]
当前初始化把所有 prior edges 的 covariance 固定为 `diag(0.1,0.1,0.001)`，再取逆得到 information；并非从实时 Karto covariance 初始化。

### 10. informative loop closure 是怎样被选中的？

[Code]
代码先把 `full_tsp_path` 覆盖的边形成抽象图 `G_tsp`，枚举当前 path vertex 与较早 vertex 之间、且不已属于 `G_tsp` 的非邻接对作为候选。先用最大可能有效距离做 KD-tree coarse pruning，再用：

```text
normalized D-opt gain / relative path-cost gain > 1
```

做 fine pruning。每轮选择使 `D-opt / total-distance` 目标最大的候选，更新 Laplacian inverse，直到没有候选能继续提高目标。

[Paper]
论文把这里的“loop edge”定义为抽象 pose graph 中的连续移动动作，不等同于一条已经被 SLAM 验证成功的 loop-closure measurement。

### 11. loop closure 的额外路径成本怎样计算？

[Paper]
插入规则是当前 vertex -> 历史 vertex -> 当前 vertex，因此额外成本是二者在 prior graph 上 shortest distance 的两倍。

[Code]
代码的 `closure_length` 由 prior graph shortest path 得到，候选加入后的距离分母使用 `curr_path_dist + 2 * closure_length`。

## Online replanning

### 12. 什么事件会触发 replanning？

[Code]
外层 Navigator 会在以下情况重新调用 exploration plugin：

- 第一次规划；
- 距离上次检查超过 `min_replanning_period`；
- 距离上次检查超过 `max_replanning_period` 且已经接近当前 goal。

[Code]
默认参数是 Navigator 1 Hz、`min_replanning_period=5s`、`max_replanning_period=1s`、`exploration_goal_distance=3m`。

[Code]
在 `MyPlanner` 内，`use_local_planner=true` 且当前目标不是 loop 时，每次 plugin 调用都会调用 Python `path_plan_service`；完成一段 active loop-closing 后也会调用一次。

[Code]
`handle_replanning()` 在纯 TSP 模式直接返回原路径；SLAM-aware 非-loop 位置会尝试优化当前到下一个 loop target 前的 local subpath。loop 后的全局 `modify_existing_tsp_path()` 调用在当前 commit 中被注释并由 `pass` 代替。

### 13. 当前地图发生变化后，高层图会怎样更新？

[Code]
地图变化本身不会立即重建整个高层图。`updateDistance` 订阅 `/map`，识别当前已知 free 的 prior vertices，并对尚无 prior edge、也从未更新过的 pair 做一次 A*；若新 direct distance 优于当前图上 shortest path，则 Python prior graph 增加一条 edge。

[Code]
`path_planner.handle_pose_graph()` 会接收实际 pose graph、更新 pose 到 prior vertex 的归属并保存 g2o；但其末尾对 `update_prior_graph()` 的调用被注释掉。

### 14. 原系统可以增加哪些 prior connectivity？

[Code]
只增加两类条件同时满足的 connectivity：两个 prior vertices 都已落入当前 SLAM map 的 free 区，周围八邻域全部为 free；二者不是原始 edge，也没有被 `updated_edges` 处理过；A* 找到路径；新 A* 距离短于 prior graph 上已有绕行 shortest distance。

[Inference]
这意味着它主要补充“地图证实存在的捷径/额外连接”，不是持续校准原 edge。

### 15. 是否存在删除、降低、失效已有 prior edge 的机制？

[Code]
未发现。`updateDistance.cpp` 明确跳过所有原始 `edgeSet`；Python `handle_edge_distance()` 只在更短时 `add_edge`，没有 remove、increase weight、invalid 标志或超时重检。

[Unknown]
尚未实跑确认该加法式、一次性更新在默认四张地图中是否造成可测性能问题。

## Frontier

### 16. frontier 如何检测？

[Code]
`GridMap::isFrontier()` 要求当前 cell 周围八邻域中 unknown 数量大于 0，并且 unknown 数量大于 obstacle 数量。`findFrontiers()` 从机器人 cell 沿 free cells 做四邻域 wavefront；遇到 frontier cell 后，`findCluster()` 用四邻域将 frontier free cells 聚类。

[Code]
检测前会把“八邻域中至少 7 个 free neighbor”的小 unknown cell改为 free；聚类后再用一个跨规划周期不下降的 `mid_size` 阈值删除小 frontier。

### 17. frontier 如何分配到 prior vertex？

[Code]
`MyPlanner::allocateFrontierToVertex()` 先取每个 cluster 的平均栅格坐标，再选 cluster 内靠近中心且 free-neighbor 数不少于 4 的 cell 作为中心。随后比较该中心到未访问 prior vertices 的栅格 Manhattan distance；如果 vertex 当前不在 free map 内，距离乘 1.3。最小者获得该 frontier。

[Code]
这段当前代码并没有为每个 frontier-vertex pair 运行 A*；注释与 README 所称 Euclidean 也不完全一致，实际是 grid-index Manhattan heuristic 加 1.3 penalty。

### 18. 为什么 README 说 Euclidean frontier association 可能有问题？

[Paper]
直线/坐标距离不理解墙体和真实可通行拓扑。隔墙很近的 frontier 与 vertex 可能被错误关联，而沿走廊实际最近的 vertex 在坐标上更远。

[Code]
README 建议可用 A* 精确评估，但称逐一计算耗时；当前 C++ 实现使用 Manhattan heuristic 而非 A*，因此同类拓扑误关联风险仍存在。

## Execution

### 19. 高层 vertex 怎样变成小车真正的导航目标？

[Code]
`MyPlanner::getWaypointToGoal()` 把 prior vertex 的 meter 坐标换算成 occupancy-grid cell。若 vertex 还在当前 map bounds 之外，就沿机器人到 vertex 的方向把 cell 拉回 map 边界；若所得 cell 在当前 wavefront 中不可达，则退化为与该位置坐标最近的 frontier center。

[Code]
plugin 返回 goal cell 后，`RobotNavigator::createPlan()` 在膨胀 occupancy grid 上以 goal 为源做 Dijkstra，得到每个 cell 的 cost-to-go；`generateCommand()` 沿 cost 下降方向选前方 waypoint 并发布 `nav2d_operator::cmd`，Operator 再做低层避障与速度控制。

### 20. 当目标不可达时系统会发生什么？

[Code]
MyPlanner 在正常 region frontier 阶段会尝试：选择同 region 中第一个 reachable frontier；若该 region 无 reachable frontier，就跳到下一个可用 high-level vertex。

[Code]
但如果 plugin 返回的最终 goal 让 `RobotNavigator::createPlan()` 找不到从 robot 到 goal 的路径，Navigator 会打印 `No way between robot and goal!`，将 Explore action 设为 aborted，停止机器人并结束本次 exploration；没有自动切换下一 high-level goal 的恢复协议。

### 21. 当主动 loop-closing target 无法实现时系统怎样处理？

[Code]
Python 若能找到该 prior vertex 关联的历史 poses，就返回从最近 pose 开始最多 7 个 pose；否则 C++ 在 prior vertex 周围构造四个固定偏移 1.5 m 的点作为 fallback。

[Code]
`performReliableLooping()` 依次把这些点直接换算成 goal cell；没有对 map bounds、free/reachable 或实际 loop-closure 成功事件做显式确认。若 Navigator 无法为其中任一点建路，外层 Explore action 会 aborted。

[Inference]
当前代码把“走完一组历史/回绕 waypoint”当作 active loop 行为结束，不检查 Karto 是否真的新增了 loop edge。因此“计划了主动回环”和“SLAM 成功闭环”必须在 Phase 1 分开记录。

## 论文与当前开源实现的差异

[Paper]
论文 Sec. V-B 描述 region degeneracy matrix 由实际 pose-graph 附近 N=5 条边 covariance 更新，并用于更新抽象 graph edge covariance。

[Code]
当前 Python 代码接收并保存 Karto covariance，但初始 prior edge information 仍是固定常数，未发现把 `vertices_to_poses` 的实际 covariance 回写到 prior edge `information/d_opt` 的执行路径。

[Paper]
论文 Sec. V-C 描述 loop 后基于更新的 prior graph 做 SLAM-aware replanning，并选择现有路径与新路径中较好的路径。

[Code]
当前 `handle_replanning()` 对 loop vertex 分支是 `pass`，调用 `modify_existing_tsp_path()` 的代码被注释。

[Paper]
论文描述在线 connectivity update 与 subpath optimization。

[Code]
在线新 edge 的 A* 节点确实存在；local subpath optimization 也存在并在 `use_local_planner=true` 时被调用。但原 edge 不重新验证，实际 pose sequence 导出的 connectivity 更新函数没有接入。

[Inference]
因此 Phase 1 的目标应先定义为“复现当前公开 commit 的可执行行为”，再逐项判断是否达到论文所描述的趋势；不能预先承诺完整复现论文所有在线机制。
