# Phase 1B 三种 Code Baseline smoke run

记录日期：2026-08-21（Asia/Shanghai）

## 范围与证据等级

[Code]
三种方法各运行 1 次，均使用官方 map3、Stage Pioneer3AT、相同起点 `(-28,-28,0)`、相同传感器/Operator/Karto/Navigator 参数，以及 baseline commit `5a116671143611601736c3e4218a762a6a5a9263`。

[Inference]
这是行为 smoke test，不是统计实验。单次时间、路径和 map cell 数只能描述本次公开代码行为，不能据此宣称方法优劣。

运行目录：

```text
results/phase1/smoke_A_nearest_frontier_map3_run1/
results/phase1/smoke_B_prior_tsp_map3_run1/
results/phase1/smoke_C_slam_aware_map3_run1/
```

[Code]
每个目录保存 `manifest.json`、`roslaunch.log`、原始 `rosout.log`、action/service 结果、nodes/services/topics 快照、最终 map、GT/SLAM trajectory、pose graph、作者原始输出、`events.csv`、`events_summary.json`、`metrics.json` 和 `paths.json`。

[Code]
`tools/phase1_event_logger.py` 仅订阅 `/rosout`、Explore action、GT、map、pose graph 和 Karto marker，不发布 topic、不调用 service。它记录：`TSP_CREATED`、`SLAM_PATH_CREATED`、`LOOP_INSERTED`、`HIGH_LEVEL_GOAL`、`GOAL_REACHED`、`GOAL_FAILED`、`REPLAN_REQUESTED`、`LOOP_STARTED`、`LOOP_FINISHED`。logger 与后处理脚本位于 baseline repo 外，未改变 planner 行为。

[Code]
A 启动早期的 live logger 使用了本机不实时转发的 `/rosout_agg`，重启后只捕获 action 终态。原始表保留为 `events_live_partial.csv`；当前 `events.csv`/`events_reconstructed.csv` 从带仿真时间戳的 `Really visited vertices` 日志离线恢复，并在每行明确标记 `source=offline_reconstructed_from_roslaunch`。B/C 为实时 `/rosout` 观测。

## 运行结果

| 方法 | Explore | 时间 (s) | GT path (m) | final known cells | pose graph V/E | 规划主动 loops |
|---|---:|---:|---:|---:|---:|---:|
| A Nearest Frontier | SUCCEEDED | 832.4 | 379.83 | 475,702 | 495 / 740 | N/A |
| B Prior-TSP | SUCCEEDED | 946.7 | 396.42 | 477,401 | 520 / 743 | 0 |
| C Graph-Based SLAM-Aware | SUCCEEDED | 1355.9 | 547.57 | 478,666 | 706 / 1020 | 5 |

[Inference]
本次 B 相对 A 的时间/路径增加约 `13.7% / 4.4%`；C 相对 B 增加约 `43.2% / 38.1%`。由于 B 与 C 的 Concorde random seed 和初始 tour 不相同，且各只有 1 次，这些差值不是可归因的性能结论。

## A：Nearest Frontier

[Code]
`strategy=NearestFrontierPlanner` 成功加载，Explore action 最终 status `3`。结束条件为 `No Frontiers in the map!`，随后打印 `Exploration has finished.`。因此 Nearest Frontier 在默认 map3 上能够完成探索。

[Code]
最终 `Really visited vertices` 序列为：

```text
8 7 13 14 18 17 18 22 21 27 28 34 33 34 33 32 26 38 37 25 24
20 16 35 11 10 4 5 6 12 6 5 4 3 9 3 9 15 19 23 29
```

[Inference]
它与 Prior-TSP 的顺序明显不同。通用 launch 仍在后台生成 TSP，但 NearestFrontierPlanner 没有接收该路径；因此后台 TSP 不能被误认为 A 的实际策略。

## B：Prior-TSP

[Code]
本次 Concorde seed 为 `1787278254`。初始 `tsp_path`、`full_tsp_path` 和 Navigator 实际接收路径三者相同，长度 36：

```text
8 7 6 5 4 3 9 15 16 10 11 35 37 38 36 12 13 14 18 17 21 22 28
34 33 27 26 32 31 25 24 30 29 23 19 20
```

[Code]
全部 36 个 `is_loop` 为 false。事件日志记录到的到达序列为：

```text
8 7 6 5 4 3 9 15 16 11 35 37 38 36 13 18 22 28 34 33 26 32 31
24 30 29 23 19
```

[Code]
缺少的高层顶点不是被替换成 nearest-frontier 顺序，而是出现 `No frontier at vertex ...` 或 repeated-visit skip 后继续推进；末尾到达 19 后跳过已访问的 20并正常完成。无 `GOAL_FAILED`、无 Explore abort。

[Inference]
因此 Prior-TSP 的确按 prior graph/TSP 改变区域访问顺序；planned high-level path 与 actual trajectory 大体一致，但不是逐项严格执行。

## C：Graph-Based SLAM-Aware

[Code]
本次 Concorde seed 为 `1787279337`。初始 TSP 长度 36；SLAM-aware optimizer 报告：

```text
tsp_d_opt = 46.41588833612801
tsp_dist  = 415.222222222222
candidate loop edges = [(8,14), (35,36), (22,18), (15,19), (26,38)]
```

[Code]
修改后的路径长度为 45，Navigator 接收路径与 `optimized tsp path` 完全一致：

```text
8 7 6 5 4 3 9 15 16 10 11 35 37 20 19 15(L) 19 23 29 30 24 25
31 32 26 27 33 34 28 22 21 38 26(L) 38 36 35(L) 36 12 13 17 18
22(L) 18 14 8(L)
```

[Code]
5 个 loop target 都进入 `LOOP_STARTED`，Navigator 都进入 `Exploration is waiting`，随后恢复 replanning 或结束 Explore。离线 GT 段统计如下：

| loop vertex | sim interval (s) | duration (s) | GT segment (m) | reliable path source | Karto 明确新增 loop 日志 |
|---:|---:|---:|---:|---|---|
| 15 | 439.3–497.4 | 58.1 | 17.45 | service success | 无 |
| 26 | 896.6–981.8 | 85.2 | 29.15 | service call failed；fallback path | 无 |
| 35 | 1035.6–1117.0 | 81.4 | 27.50 | service success | 无 |
| 22 | 1241.5–1279.8 | 38.3 | 16.54 | service success | 无 |
| 8 | 1360.6–1400.8 | 40.2 | 15.12 | service success | 1 次，发生于 1386.7 s |

[Code]
五段合计约 `303.2 s / 105.76 m`，分别占 C 本次总时间/路径的约 `22.4% / 19.3%`。因此 SLAM-aware 相对其 TSP 明确插入并执行了额外 informative loop actions。

[Code]
需要区分“执行 loop action”和“SLAM 确认新闭环”。Karto 原始日志只在最终 loop 8 期间明确打印一次 `Add one Loop closure. 1 loops have been added.`；前四段没有对应明确新增事件。`/Mapper/closure_edges` marker 的终值是所有非顺序 graph edges，不等价于新闭环成功次数，不能把 marker point 数当 loop closure statistics。

## planned path 与 actual trajectory

[Code]
B、C 均沿规划的 prior-region 主顺序推进，但无 frontier、已访问顶点和 reliable-loop 内部 waypoint 会使实际 visit stream 与高层数组不同。C 明确出现：

```text
Skip repeated visit to vertex 10
Skip repeated visit to vertex 19   # loop 15 后的返回顶点
Skip repeated visit to vertex 33
Skip repeated visit to vertex 38   # loop 26 前后
Skip repeated visit to vertex 36   # loop 35 后
Skip repeated visit to vertex 18   # loop 22 后
```

[Inference]
所以“planned high-level path 与 actual trajectory 大致一致”的答案是是，但不能把 optimized path 直接当真实执行轨迹。尤其 `current -> loop target -> current` 中的返回 vertex 会因 repeated-visit 检查被跳过；实际 loop 形状由 reliable-loop waypoint/fallback 决定。

## 已确认的论文—代码/计划—执行差异

1. [Paper/Code] 论文描述实际 pose-graph covariance 驱动 region degeneracy/D-opt update；当前 commit 虽接收 covariance，但 prior-edge information 初始化为常数，未接入动态回写。C 只在启动时生成一次 D-opt 优化路径。
2. [Paper/Code/Runtime] 论文描述 loop 后的 SLAM-aware 全局 replanning；当前 loop 分支为 `pass`，`modify_existing_tsp_path()` 被注释。C 的五次 loop 后均继续同一 45-entry path，没有第二次 `SLAM_PATH_CREATED` 或新 optimized path。
3. [Paper/Code] 论文要求 metric-closure TSP 恢复为 prior connectivity walk；纯 TSP 分支发送 `tsp_path` 而不是 `full_tsp_path`。本次 map3 两者恰好相同，因此差异已静态确认但没有产生本次行为差异。
4. [Plan/Runtime] optimizer 输出的 loop 返回顶点在 runtime 被 repeated-visit 逻辑跳过；公开代码实际 loop 轨迹由 reliable waypoint/fallback 构成，不严格执行输出数组中的返回 leg。
5. [Intent/Runtime] 完成 reliable-loop waypoint 后系统恢复探索，不等待“每个主动 action 都新增 Karto loop edge”的确认。本次 5 个 action 中只有 1 个有明确 Karto 新闭环日志。

## Observed anomalies

- Concorde 每次按当前时间生成 seed；B/C 即使同图同起点也得到不同但等价最优的初始 TSP，削弱单次方法间配对比较。
- C 在 loop 26 时 `/reliable_loop_service` 调用失败一次，Navigator 自动使用 fallback loop path，Explore 未 abort。
- `TF_REPEATED_DATA` 在 A/B/C 分别出现 35/34/62 条；TF 未中断。
- `Missed desired rate` 在 B/C 出现 3/22 条；C 的运行负载和 pose graph 更大，但无节点死亡。
- B/C 分别出现 28/24 条 `No frontier at vertex`；这是路径跳项的直接来源。
- Phase 1A 短探针曾出现两次 local-replan 起终点错误；三次完整 smoke run 未再次出现。
- APE/RPE 未计算：当前固定环境没有 `evo`，且本阶段不临时引入未固定评价依赖。GT、SLAM TUM trajectory 已完整保存，可在 Phase 2 固定 evo 版本后统一计算。

## Candidate failure modes（3–5）

1. Concorde seed 不受实验配置控制，导致同配置 high-level tour 不配对，掩盖或夸大方法差异。
2. `No frontier`/repeated-visit skip 使 optimized path 与真实路线分离，尤其可能删除理论 loop 的返回 leg。
3. reliable-loop service 偶发失败后 fallback waypoints 未做完整 bounds/free/reachability 校验，复杂地图可能 abort。
4. active loop 完成不等于 Karto 新增 loop constraint；可能付出额外时间/路程却没有定位收益。
5. periodic local replanning 的起终点不一致和 1 Hz overrun 可能在更大 pose graph/地图上演变为持续错误或超时。

## Phase 2 最小实验建议

1. map3 每种方法至少重复 3 次，保存 Concorde seed/initial path；在 seed 未受控前不做显著性或因果比较。
2. 固定一个 evo 版本，对现有和重复运行统一计算 time-aligned SE(2) APE、RPE，并同时报告路径、时间和 coverage。
3. 对每个 active loop 保存前后 Karto graph edge snapshot、明确新增-loop日志、GT 段和 service/fallback outcome，区分 planned/executed/successful closure。
4. 针对 `No frontier`、repeated skip、local-replan mismatch 做纯观测计数和路径对齐；不修改 baseline。
5. map3 重复稳定后只增加一个官方次级地图（优先 map4）做同样 smoke/repeat，不同时改变算法和环境。

## 非 baseline 启动错误记录

[Code]
B 正式 run 前曾把 launch 的 `map_name` 误写成 `map3` 而非 `map3/map3`，Stage 在 exploration 开始前因 world 文件不存在退出。该编排错误没有计入 B，也未静默删除，日志保存在：

```text
results/phase1/failed_pre_run_B_bad_map_argument_20260821/
```
