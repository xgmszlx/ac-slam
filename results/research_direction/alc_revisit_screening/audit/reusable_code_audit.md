# 可复用代码与实质缺口

| 资产 | 本轮核验 | 复用边界 |
| --- | --- | --- |
| author `utils.py` / `offline_tsp_evaluation.py` | AST 抽取原函数，保存 TSP+prior 原样重算；45/45 初始优化路径与 SLAM_PATH_CREATED 完全相同 | 是原生先验/TSP评分，不是新历史区域簇的评分；不导入 ROS 或重新解 TSP |
| `path_planner.py:update_prior_graph_attributes` | 初始 Cov diag(0.1,0.1,0.001)，统一 prior d_opt | 不是实时 matcher 接受概率；记录而不修复旧接线 |
| `handle_reliable_loop` V0 | 找 prior vertex 所属最近历史 pose，然后至多七个后继关联 pose 的 x/y | 未选择历史路径方向，未发送完整历史朝向；其他 oracle_mode 是旧实验变体，不能叫作者原方法 |
| `continuous_revisit/analysis.py` | 精确抽取 jacobian/information/target_score，重算七条同步四阶段 J_T | gauge 为最低 state_id，五目标十五自由度；新边数量不能替代这个值 |
| Doc79 同步导出/水位屏障 | graph SHA、state/UID、端点与 creation_sequence 一一核验 | 新前瞻采集可复用，但旧发布缓存不能追认为同步图 |
| Doc80 GT 修正实现 | 本轮独立实现前置对齐、接受时间配对、laser→base；140 行复现 | 不调用旧 run_all/旧输出写入器 |
| `nav2d_navigator/src/RobotNavigator.cpp:createPlan` | 原实现有占据栅格 Dijkstra 全搜索，非本轮新 A-star | 需在线地图、机器人膨胀/goal校正；保存的轨迹/图不足以离线证明可达 |
| `evaluate_slam_run.py` | 冻结 evo 1.31.1、0.05 s、SE(2)零对齐协议；独立重算平移 APE | 本轮不重跑 ROS 或调参；当前统计不是随机同初态因果效果 |
| `evaluate_mapping.py` / v2 | 原栅格采样/F1独立重算45张；既有v2含局部距离和覆盖口径 | Stage GT仅评价；v1 F1不能代替局部真实墙面改善 |

A1：历史扫描足够，两个动作前同步图足够，在线导航 occupancy 与经过足迹审计的
稠密可执行历史路径不够。A2：历史图/候选区域几何足够，候选可达距离和与作者
prior graph 的状态映射不够；校准的 P-ALC 概率、visual view score 也不存在。
可以不修改 Karto 完成本轮全部分析，但不代表已具备部署选择器的完整输入。

没有更改这些旧源文件。对主工作区未提交的 `same_input_replay.py` / `se2_information.py`
只核验 SHA，不导入其修改版本，也没有覆盖用户改动。
