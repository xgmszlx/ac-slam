# Doc 78 复核包 — REVIEW_PACKET

连续回访实验（doc 77，`p1_continuous_revisit_actions_20261010`，48 主实验 + 8 重复性）
的事后测量修正与机制复核。所有内容均为**只读复核**：旧实验、原始数据、冻结协议与
生产代码未被修改；本目录中的所有结果是新增的、可单独追溯的修正产物。

- 复核分支：`research/phase4c-formal`
- 基线（doc 77 最终提交）：`95d0d1202cb21063c775c96087536b61222a9527`
- 复核版本：`p1_continuous_boundary_review_v1`（`summary.json` 内 `review_version`）
- 正式文档：`docs/research_log/78_continuous_boundary_and_mechanism_review.md`

## 0. 一句话结论

doc 77 的**记录数值**可独立复现，但其**阶段归属**存在系统性污染：返回段晚发布
的闭环边被计入了动作段；修正后 S1 的动作增量从 +0.08144 降到 +0.00946 nats、
L+ 从 +0.06485 降到 +0.04360、L− 从 +0.11562 降到 +0.04636（S0 仍恰为 0，12/12），
且 L+ 与 L− 的方向差异从 −0.05077 塌缩为 −0.00277（12 组中 6 组为正）。
信息收益与真实 GT 误差无对应改善。最终判决：
**D. PURE_ROTATION_SELECTION_NOT_SUPPORTED**；不启动在线诊断。

## 1. 文件清单与用途

| 文件 | 回答的问题 | 关键列 |
| --- | --- | --- |
| `boundary_event_audit.csv` | 每个快照边界真正覆盖了哪些已接受状态？ | `content_time_ros`、`content_lag_s`、`content_before_stage_motion_end`、`stage_states_in_snapshot / deferred`、`quiescence_satisfied`、`keyscan_missing_check_vacuous` |
| `recoverability_matrix.csv` | 未按时发布的关键帧能否恢复？ | `recoverability_class`∈{`DEFERRED_RECOVERABLE`,`NEVER_PUBLISHED_SUFFIX`,`NEVER_PUBLISHED_GAP`}、`recoverable_offline`、`needs_fixed_linearization_diagnostic` |
| `statistical_correction.csv` | 重复运行统计的正确口径与四类波动分解 | `row_type`：`REPEATABILITY_CONFIG` / `POOLED_SD_RECONCILIATION` / `POOLED_SD_ALL_FIVE_RUNS` / `ARM_REALISATION` / `ARM_ATTRIBUTION` / `PAIRED_CONTRAST_CORRECTED` / `VARIANCE_DECOMPOSITION` / `DIRECTION_DIFFERENCE_EXPLANATION` |
| `corrected_gt_metrics.csv` | 用明确身份链重算的 GT 指标（旧值同列对照） | `family`：`TARGET_MAP_ERROR` / `ROBOT_LOCALIZATION_ERROR` / `RELATIVE_POSE_ERROR` / `MAP_CONSISTENCY`；`value`/`value_old` |
| `historical_factor_mechanism.csv` | 每个阶段的边构成、闭环贡献与阶段归属偏移 | `new_edges`、`new_closures`、`effective_closures`、`deferred_attribution_edges`、`closure_contribution_sum`、`stage_gain_recomputed`、`gain_matches_closure_sum` |
| `stage_attribution_correction.csv` | **FIXED_LINEARIZATION_FACTOR_DIAGNOSTIC**：按“创建时间”而非“发布时间”重排后的阶段增量 | `recorded_*` 与 `created_*` 增量、每阶段闭环计数、`history_baseline_delta` |
| `gain_recomputation.csv` | 独立重算的 stage gain 与 doc 77 数值逐条对照 | `action_gain_recomputed` vs `action_gain_doc77` |
| `offline_evidence_gate.json` | 离线证据是否足以支持阶段归属 / 是否需要在线诊断 | `gates.G1..G5` |
| `final_research_decision.json` | 最终判决、理由、九问简答、唯一下一步 | `verdict`、`online_diagnostic`、`questions` |
| `figures/fig1..fig6` | 每图回答一个研究问题（见 §5） | PNG+SVG |

复现命令（仓库根目录）：

```bash
PYTHONPATH=catkin_ws/python /usr/bin/python3 \
  tools/realizability_pilot/continuous_boundary_review/review.py \
  --suite results/realizability_pilot/p1_continuous_revisit_actions_20261010 \
  --out   results/realizability_pilot/p1_continuous_boundary_review_20261012
PYTHONPATH=catkin_ws/python /usr/bin/python3 \
  tools/realizability_pilot/continuous_boundary_review/figures.py \
  --out   results/realizability_pilot/p1_continuous_boundary_review_20261012
PYTHONPATH=catkin_ws/python /usr/bin/python3 \
  tools/realizability_pilot/continuous_boundary_review/test_boundary_review.py
```

## 2. 快照状态审查（阶段一 A）

实测证据（全部来自记录文件）：

1. **`wait_for_graph_boundary` 不是图内屏障**。它等待的是“全图话题静默 +
   keyscan 发布静默 ≥0.5 s”（`driver.py` 的 docstring 已如实声明），对
   “已接受但未发布”的状态不可见。224/224 个边界 `quiescence_satisfied=true`，
   但 198 个“本阶段创建的状态”并不在关闭该阶段的快照里（`stage_states_deferred`
   合计：`G_arrival` 117 个、`G_action_done` 81 个）；`G_arrival` 的内容时间
   **早于返回段运动结束**的有 56/56 条，`G_action_done` 有 44/56 条。
2. **`/others` 关键帧事件缺少 `state_id`**：`on_mapper_keyscan_pose()` 只记
   `stamp/received_ros_time/x/y/theta`，而 `snapshot()` 尝试读取 `state_id` →
   `keyscan_states_missing_from_graph` **恒为空**，224/224 行的
   `keyscan_missing_check_vacuous=true`。**不得把 missing=[] 当作图完整性的证据。**
3. **真实身份链存在**：`rosout.log` 中的
   `PHASE2C_KEYSCAN_ACCEPTED unique_id=U state_id=S sim_time=T` 给出每个关键帧的
   显式身份与接受时间；56/56 运行中每个 state 的 `sim_time` 都能与
   `keyscan_stream.jsonl` 的 `stamp` 精确对应（100%），且与快照节点
   `unique_id` 无一冲突（0/56 运行存在不一致）。这是本轮所有修正的基础。
4. **原生扫描链路**：driver 以 ~10 Hz 记录全部 `/base_scan`（含 TF 解算的
   odom/map 位姿）；mapper 仅在运动 ≥1.0 m 或朝向变化 ≥0.52 rad 时接受新状态
   （`MultiMapper.cpp` 的 `MinimumTravelDistance/Heading` 行为，接受点即打日志）。
5. **图消息发布时间 ≠ 图更新时间**：全图观测话题由 `sendMap()` 发出，其节奏由
   planner 的 get_map/地图变化驱动；机器人停住后不再有新消息。
   内容滞后中位数：`G_before_return` 4.4 s、`G_arrival` 5.4 s、
   `G_action_done` 5.4 s、`G_final` **32.1 s（最大 42.6 s）**。
6. **`G_action_done` 与 `G_final` 的定义差异**：两者都用同一套“静默边界+快照”
   机制，但 `G_action_done` 在动作指令序列完成时拍摄，`G_final` 在补满 347 帧
   （其主体是动作结束后的静止剩余）后拍摄；当全图发布早已停止时两者内容相同，
   这也解释了 doc 77 中 tail_gain 恒为 0。
7. **仪器缺口（如实记录）**：`karto_edge_provenance.jsonl` 与
   `pose_graph_dump.json` 在 56/56 条运行中**均未生成**——launch 中
   `instrumentation_flush_period_s=0.0` 使 provenance 只在析构时刷新，而 mapper
   被非优雅终止；dump 服务从未被调用。因此 doc 77 宣称的“边 provenance”实际
   不存在，本轮机制分析改用：接受日志（创建时间）+ 快照边差分（发布）+
   `/Mapper/loop_closed` 事件（15/48 条运行有事件，且**没有任何一次事件发生在
   最后内容时间之后**）。

## 3. 事件时间线与可恢复性（阶段一 B/C）

- 未按时发布关键帧共 **98 个**：94 个为**从未出现在任何快照**的“后缀子树”
  （43/56 条运行，其中主实验 77 个/35 条），另有 4 个属于中间阶段延迟
  （`DEFERRED_RECOVERABLE`，可在后续快照中恢复）：`0023_place_B_r3_L-` s133、
  `0024_place_B_r3_S0` s108、`0037_place_D_r1_S1` s109、`0038_place_D_r1_L+` s128。
- 从未发布的后缀状态全部位于运行末尾（状态号连续后缀），其接受速度中位数为 0
  （就地旋转/已停），且这些运行中没有任何迟到的 loop 事件 → 图上它们只能通过
  链边树挂接，**不产生任何环**，对 J_T 的贡献可解析证明为 0（单元测试同构）。
  为最坏情形另做 `FIXED_LINEARIZATION_FACTOR_DIAGNOSTIC`：为每个未发布状态注入
  一条“到最近已发布状态”的合成闭环（中位观测协方差），得到上界；该上界
  单独存放（`historical_factor_mechanism.csv` 的
  `diagnostic_delta_jt_worst_case`/`diagnostic_name`），**绝不与真实阶段 J_T 混合**。
- 四个重点案例（详见 `historical_factor_mechanism.csv` 与
  `stage_attribution_correction.csv`）：

| 案例 | 记录动作增益 | 创建时间归属后的动作增量 | 机制读数 |
| --- | --- | --- | --- |
| `0005_place_A_r2_S1` | +0.09570 | **+0.00000** | 动作期未创建任何边；0.0957 全部来自返回段闭环 25→127、26→128 的晚发布 |
| `0016_place_B_r1_L+`（r1） | −0.00000 | −0.00000 | 动作期仅 1 条内向环（130→132），贡献 0；133/134 号状态接受于旋转末段、从未发布（诊断上界 ≈5.8e-14） |
| `0016_…_L+_rep2`（同一配置重执行） | +0.43548 | **+0.42035** | 动作期自发创建 5 条**有效**闭环（连到旧图），信息收益真实存在 |
| `0025_place_C_r1_L+` | +0.08733 | +0.08733 | 动作期 6/6 条闭环有效（含 67→134、69→132 等连旧图），归属无偏移 |

- **阶段归属偏移**已经在机制表中量化（`deferred_attribution_edges`，
  例：`0004_place_A_r1_L-` 记录动作 +0.24703，实际为返回段创建
  （创建归属：返回 +0.24737、动作 +0.09258）；`0005` 的 4/4 条动作差分边均为
  返回段创建）。

## 4. 统计勘误（阶段二）

四个配置的三次同配置完整运行（r1 + 两次重执行），action_gain（独立重算）：

| 配置 | 三次原始值 | 样本 sd (ddof=1) | 运行前状态差异（min–max spread） |
| --- | --- | --- | --- |
| A L+ (`0003`) | 0.16818 / 0.06212 / 0.19648 | 0.07083 | 动作前状态 129–133；动作转角 3.60–4.10 rad；返回时长 31.4–32.4 s |
| A L− (`0004`) | 0.24703 / 0.10576 / 0.14328 | 0.07318 | 状态 129–134；转角 3.44–3.64；返回 31.4–33.6 s |
| B L+ (`0016`) | −0.00000 / 0.11905 / 0.43548 | 0.22507 | 状态 132–134；转角 3.40–3.80；返回 75.4–77.4 s |
| B L− (`0013`) | 0.01630 / 0.00126 / 0.11040 | 0.05915 | 状态 135–142；转角 3.34–3.55；返回 77.4–81.4 s |

- **正确口径（新）**：同配置三运行的等权合并组内 sd（ddof=1）=
  **0.12701144341701123**（与任务给定参考值逐位一致；单元测试覆盖）。
- **旧值 0.104576… 的来源**：`report_tables.py` 第 168–179 行对每个
  (place, action) 单元取“三次主重复 + 两次重执行”共 5 个值，用
  `statistics.pstdev`（ddof=0）后对四个配置 **等权平均** → 0.10458。
  即旧值混入了不同重复（r1/r2/r3 的路线偏移不同）并使用了有偏估计量。
  5 个样本、ddof=1 的对应值为 0.126363。
- **四类波动必须分开**（`VARIANCE_DECOMPOSITION` 行）：
  1. *完整系统重执行*：0.127011（上表）；
  2. *同输入后端数值波动*：**本协议未测量**（重执行是完整 Stage+Karto 重跑；
     旧 v12 试点回放属另一协议，不可迁移）。其角色由“闭环实现”的离散性间接
     界定：同配置内 0 与 0.435 的跨度为系统重复的一部分；
  3. *动作平均效应不确定性*：48 条主实验的修正动作增量 mean 0.02485、
     sd 0.04696（12 条/臂时均值的标准误 ≈0.0136）；
  4. *地点间条件差异*：四地点均值 0.0257 / 0.0265 / 0.0264 / 0.0208
     （sd 0.0027）——远小于单次运行散布。
- **不得把 0.12701 当作效果门槛**：它是“单次运行的可复现性尺度”，不是统计
  显著界；但也不得用“均值差 < 单次 sd”直接宣布无效。正确做法是成对设计 +
  实现率分解（见 §6）。
- 方向差异解释（12 组成对，修正后 L+−L− 与动作前特征）：
  转角差 r=0.55、动作前状态数差 r=−0.02、锚点朝向误差差 r=−0.39；
  均值差 −0.00277（6/12 为正）→ 方向差异在均值上消失，剩余的不对称是
  **实现率**层面的（见 §6）。

## 5. 图表索引（每图一个问题）

1. `fig1_boundary_coverage`：快照真的覆盖了本阶段已接受的状态吗？（A：各运行
   从未发布关键帧数；B：各边界发布滞后及“内容早于运动结束”标记）
2. `fig2_gain_mechanism`：收益从哪来？（A：动作期有效闭环数 vs 修正动作增量；
   B：每条主实验记录值与创建时间的对照）
3. `fig3_statistics`：统计修正改变了什么？（A：四个三元组及新旧散布；
   B：记录/修正的臂均值；C：L+−L− 成对差在修正前后的塌缩）
4. `fig4_ground_truth`：动作带来实际定位改善了吗？（目标误差变化、机器人 SLAM
   误差分层、相对位姿误差）
5. `fig5_timeline_case`：边界时序如何造成 0016 的错分？（运动/发布/接受/闭环
   时间线）
6. `fig6_diagnostic_bounds`：从未发布关键帧的最坏影响上界（labeled diagnostic）。

## 6. 机制结论（阶段四）

1. **阶段增益 = 该阶段差分中新增闭环边的边际贡献之和**：168 个阶段行中
   0 个超出相对容差（1e-3；原始最大偏差 ≤8e-5 nats，属数值条件数）。
2. **链边（叶子子树）对 J_T 贡献恒为 0**（解析 + 单元测试）；因此“图变大”不等于
   “信息增加”。
3. **零增益运行 = 该阶段没有产生任何有效闭环**。S0：12/12 恰为 0（对照成立）；
   L+ 主实验 5/12 为零（A r2/r3、B r1/r2/r3），其动作期闭环全部是“新状态之间
   的内向环”（贡献 0）；L− 主实验 0/12 为零。B L+ 三次主实验全零，而其两次
   重执行都产生有效闭环（0.119、0.435）→ 零簇是运行级实现差异，而非该配置
   几何上不可能。
4. **方向差异的真实结构**：修正后 L+−L− 在均值上消失；剩下的差异是
   *有效闭环实现率*：L− 12/12 成功、L+ 7/12（5 次零）、S1 10/12。该实现率按
   地点成簇（A: L+ 1/3、B: L+ 0/3、C/D: L+ 3/3），无法由动作前特征解释。
5. 修正后的臂均值（主实验）：S0 0.00000（12/12 零）、S1 0.00946（2/12 零）、
   L+ 0.04360（5/12 零）、L− 0.04636（0/12 零）；成对对比
   L+−S1 = +0.0341（8/12 正）、L−−S1 = +0.0369（9/12 正）、L+−L− = −0.0028。

## 7. GT 复核（阶段三）

- **身份链**：`state_id → unique_id → keyscan stamp → scan/GT time`，56/56 运行
  完整且无冲突；不再使用空间最近邻。TF 外参沿用记录中的实时 TF 解算；
  GT 以 ≤0.15 s 容差插值；对齐变换只用动作前的历史+返回段拟合。
- A（冻结历史目标状态误差，mean）：before 0.09546 → arrival 0.09548 →
  action_done 0.09558 → final 0.09558 m；变化 +0.000124 m（中位 0，最大
  0.0094 m）。与 doc 77 的局部拟合值逐条一致（|diff| ≤ 2.8e-17），但按任务
  要求仅作为**局部拟合误差**，不再称“完整定位精度”。
- B（机器人定位误差，SLAM 图位姿 vs GT，动作前对齐）：history 0.0339、
  return 0.0343、action 0.0418、tail 0.0410 m；tail−history 均值 +0.0070
  （中位 −0.0010）→ **无动作驱动的改善**。
- C（机器人相对锚点状态位姿误差，动作段）：平移 mean 0.1146 m、朝向
  mean 0.0091 rad（中位 0.1087 / 0.0098）。
- D（一致性）：全程轨迹 ATE mean 0.0344 m（中位 0.0275）；动作前对齐参数
  逐条存于 CSV；目标状态对齐样本恒为 5。
- NOT_EVALUABLE：0 行（所有目标/锚点状态的身份均可解析）。

## 8. OFFLINE_EVIDENCE_GATE（阶段五）与在线决定

`offline_evidence_gate.json` 的要点：

- G1：`quiescence_failures = 0` 与 `keyframe_missing_from_all_snapshots = 94` 同时成
  立 → 静默判据不是集成判据；`unexpected_gap_states = 0`（后缀结构成立）；
  224/224 行为空检查。
- G2：`gain_equals_closure_sum_failures = 0`；创建时间归属与记录归属的差额逐条
  存档。
- G3：统计修正表（§4）。
- G4：GT 指标族（§7）。
- G5：诊断上界单独命名存放；聚焦运行的典型上界 ≪ 实测增益（如 0025 上界
  0.015 vs 实测 0.087），S0 类零增益运行的上界不改变“记录值恰为 0”的事实
  （无任何迟到 loop 事件支持合成闭环存在）。

**在线诊断决定：不运行。** 理由：阶段归属在离线数据中已可完全重建（接受日志
给创建时间、快照给发布时间、4 个中间延迟状态可恢复、后缀状态可证树性质并给出
上界）；在线同步接口只能复核已修正的量，不能解决“为什么某些运行不产生有效
闭环”的问题——后者需要仪器修复后的新观测（周期 provenance 刷新 + 每边界
`/Mapper/dump_pose_graph_now` 屏障 + 扫描队列计数），并受任务给定的预算约束
（首轮 place_A r2 S0/S1 2 条；链路验证后至多再加 B r1 L+/L−、C r1 L+/L− 4 条；
硬上限 8 条）。若未来重启，`final_research_decision.json` 的
`online_diagnostic.preconditions_if_revived` 列出了必须先行确认的事项。

## 9. 最终判决

**D. PURE_ROTATION_SELECTION_NOT_SUPPORTED**（详见
`final_research_decision.json`；九问简答同文件 `questions` 字段）。

唯一下一步建议：关闭纯旋转动作选择路线；若继续回访课题，则以“闭环实现机制”
为新问题、以修复后的观测链为工具，从 place_B L+ 零簇的有界复现（≤4 条）开始，
而不是继续评估选择器。
