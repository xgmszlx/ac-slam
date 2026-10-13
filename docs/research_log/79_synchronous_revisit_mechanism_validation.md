# 79 — 同步回访观测验证、历史约束机制审计与研究方向筛选

2026-10-13。本轮为 Doc 79 `DOC79_SYNCHRONOUS_REVISIT_OBSERVATION_VALIDATION`
（`BOUNDED_PROSPECTIVE_TECHNICAL_AND_MECHANISM_DIAGNOSTIC`）：在 8 个物理回合的
硬预算内，用一条**同步观测链**（原生扫描处理屏障 + 串行化 provenance 落盘 +
同步位姿图 dump）重测 Doc 77 的连续回访动作效应，并回答 Doc 78 提出的测量
缺口。基线提交 `cac55c4bb817705529bee6f39fbdf7cfb698677c`（分支
`research/phase4c-formal`）。

> 本轮所有产物位于新根目录
> `results/realizability_pilot/p1_doc79_synchronous_revisit_validation_20261012/`，
> 与 Doc 77/78 旧结果物理分离。旧实验记录、原始数据、冻结协议、生产二进制
> （`catkin_ws/devel`）均未被修改：生产 `mapper` 与 `libMultiMapper.so` 的
> SHA-256 在运行前后与基线一致（见 `audit/production_integrity*.json`）。
> 新代码全部隔离在 `tools/realizability_pilot/doc79_sync_validation/` 与
> overlay 工作区 `doc79_ws/`（观测补丁 diff 见
> `audit/observability_patch.diff`，188 行，仅新增只读遥测与导出服务）。

## 0. 结论与建议（最终）

**测量资格**：8 个预算回合中执行 8 次尝试、消耗全部预算；7 次成功且
**7/7 技术合格**（每个回合 4 条边界导出 = 28/28 全部 `all_checks_passed`；
原生扫描屏障全部满足、provenance 全部落盘且单一 run_id、无重复/乱序
`creation_sequence`、无扫描序号/时间戳重复或回退）。第 1 个回合（`D79_B_Lplus_1`
attempt_01）因**物理完成度**失败（`MoveTo history_03` 报成功但 GT 位置误差
0.771 m > 冻结阈值 0.75 m；TF 0.181 m/0.167 rad 在阈内），重试消耗预算，
导致第 8 个回合 `D79_C_Lminus_2` **从未执行**——这是本轮如实登记的
`TECHNICALLY_INCOMPLETE` 成分。

**旧 topic 图的漏失**（Doc 78 的核心疑问）：7/7 运行的 28 条边界中，旧
`/mapper/pose_graph` 话题缓存相对同刻同步 dump 的缺漏是 **0–4 个节点、0–10
条边**，且**全部为“尾部滞后”**：缺的节点一律是最后被接受的 0–4 个关键帧
（uid 尾部），缺的边全部与该尾节点相连；**旧节点之间 0 条缺失边**。缺的边中
包含尾节点携带的**历史/闭合链接**（如 `[55,137] [56,138] [59,139] [70,132]
[71,133] [72,136] [57,141] [58,140]`）。结论：topic 图不会“凭空丢中间结构”，
但边界时刻会系统性地漏掉**最新 1–4 次已接受扫描及其全部新链接**——正是机制
研究最关心的那些约束。

**同步观测下的科学结果**：方向反差**在 B、C 两处都完整重现**，且比 Doc 77
的话题口径更干净：

| 地点 | L+ 动作增益（各 run） | L− 动作增益（各 run） | L+−L−（各组） |
| --- | --- | --- | --- |
| place_B | 0.2833, 0.3494（n=2） | 0.0225, 0.0099（n=2） | 0.2608, 0.2734, 0.3268, 0.3394 |
| place_C | 0.1244, 0.1064（n=2） | 0.00237（n=1） | 0.1220, 0.1041 |

（增益 = 动作段 `J_T` 增量，来源列 `gain_source=SYNCHRONOUS_DUMP`；旋转幅度
3.40–3.83 rad，两组各 run 接近。）

**机制归属**：动作段增益**全部**来自历史链接——`closure_contribution` 与
`historic_contribution` 在每条运行中相等（差 < 1e-13）。L+ 在 B 创造 11 条
历史链接（L− 为 5 条）；在 C，L+ 以 4–6 条历史链接产生 0.106–0.124 增益，
L− 用 5 条历史链接只产生 0.0024。局部内向闭环（local-only closures）每段
0–2 条、贡献恒为 0（诊断口径 `FIXED_LINEARIZATION_FACTOR_DIAGNOSTIC`，
不计入主列）。

**定位/成本价值**：目标点在动作前的地图误差 0.031–0.091 m（全部 < 0.1 m）；
动作段相对位姿误差平移 0.011–0.094 m、旋转 0.061–0.085 rad；动作前后机器人
GT 误差变化为 −0.011…+0.060 m（符号混杂）。**没有可测的定位价值变化**可
归因于方向；差异存在于“信息/约束结构”层面，而不是轨迹误差层面。

**动作前可解释性**：两个冻结前置特征（历史段航向重合比例、关键帧门残余角）
在 L+/L− 之间**交错、不分离**（B: 0.66–0.70 vs 0.66–0.70；门残余 0.063–0.352
rad；C: 重合 0.22–0.25）。预测关键帧数对所有运行恒为 6。即：以当前可计算
的前置特征**无法事前判别**方向结局。

**判决**：`A CONDITIONAL_EFFECT_CANDIDATE`（带限制）——测量合格、效应在
两处重现、机制可归属；但“条件性”的要义（不同地点给出不同方向偏好）**未
被观察到**（两处均为 L+ > L−），故它目前更像**方向不对称现象**而非地点
条件现象；并且 C 的 L− 只有 1 条运行、第 8 个回合未执行。
**是否值得开发最小规则**：**尚不值得**——没有任何可计算的前置判别量，
现在设计“基于局部几何的动作切换”将是事后拟合。
**单一下一步**：`MECHANISM_OBSERVATION_ONLY`（只做机制观察，不开发方法；
见 §4）。

### 0.1 交付物

- 冻结协议：`protocol/preregistration.json`、`frozen_run_manifest.json`、
  `frozen_hashes.json`（10 项代码哈希，含运行后冻结的 `analysis.py`/
  `figures.py`/`checks.py`）、`frozen_analysis_plan.md`；
- 审计：`audit/source_execution_path.md`、`native_scan_pipeline.md`、
  `snapshot_barrier_design.md`、`provenance_integrity_design.md`、
  `observability_patch.md`、`observability_patch.diff`、`build_manifest.json`、
  `production_integrity.json`、`production_integrity_after.json`、
  `runtime_provenance.json`；
- 运行：`runs/<episode>/attempt_NN/`（规格、双流、同步+话题图、provenance、
  ledger、清单、rosout 副本、结果）；
- 分析：`analysis/*.csv`（13 张）+ `final_gate.json` + `local_only_files.csv`；
- 图表：`figures/fig1..fig6`（png+svg）；
- 复核包：`REVIEW_PACKET.md`；状态：`STATUS.md`。

## 1. 修正了什么（相对 Doc 77/78 的测量缺口）

Doc 78 证明 Doc 77 的边界快照存在“话题静默”污染（停住后无新消息，晚发布
的边被错分类），并指出 provenance 文件当场缺失。本轮把观测链整体替换为
**同步**链，全部为新增只读代码：

1. **原生扫描处理屏障**：驱动在边界前记录最后一个原生 `/base_scan` 的
   `(seq, stamp)` 水位；随后轮询 mapper 侧遥测服务
   `/Mapper/get_native_scan_telemetry`，直到
   `last_native_scan_stamp ≥ watermark.stamp` 且 `native_scan_processed > 0`
   才继续。该服务与扫描回调在**同一单线程节点**中串行执行
   （`MapperNode.cpp`: `ros::Rate(10){publishTransform(); ros::SpinOnce();}`），
   因此“遥测已见”严格蕴含“该扫描的 `Process()` 已返回”。
2. **串行化 provenance 落盘**：边界服务
   `/Mapper/doc79_sync_boundary_export` 在**同一回调串行域**内先
   `FlushEdgeProvenance()`（互斥保护的缓冲一次性写盘），再请求同步
   `WritePoseGraphJson()` 到 `/Mapper/pose_graph_dump_path`，返回
   written/path/计数/flush 标志。结束时 `pending_edge_provenance=false`。
3. **同步 dump 校验**：驱动对每份 dump 验证 9 项
   （屏障、mapper 接收数、接受数与 keyscan 流一致、服务成功、路径匹配、
   flush 完成、文件可解析、run_id 匹配、计数与服务一致）。
4. **旧话题缓存**：同一时刻快照 `/mapper/pose_graph` 最后消息，作为对照，
   不参与主口径。

技术资格（7 条合格运行 × 4 边界 = 28 条）全部通过；典型一条边界的遥测：
`mapper_received == mapper_processed`（无等待地图丢弃计入）、
`mapper_accepted == driver_keyscans`（142 = 142）、`provenance_records 459`、
`topic_message_count 69`。失败尝试（`D79_B_Lplus_1` a01）保留全部证据
（1649 帧流、71 keyscan、216 MB 前的完整目录），未被挑选或删除；
重试为新 attempt（a02），两版并存。

## 2. 发现了什么

### 2.1 旧话题图漏掉的是“尾部一串”，不是随机孔洞

28 条边界逐一比对（`analysis/topic_vs_sync_graph.csv`）：

- `G_before_return`：缺 0–1 节点 / 0–1 边；
- `G_arrival`：缺 0–4 节点 / 0–8 边；
- `G_action_done`、`G_final`：缺 2–3 节点 / 4–10 边。

缺失集**永远**是最后被接受的关键帧（uid 尾部）及其入射边；
`nodes_only_in_topic` 恒为空。缺的边包含**历史链接**的物种
（跨新旧区域的闭环），例如 B 运行中 `[55,137] [56,138] [59,139]`、C 运行中
`[70,132] [71,133] [72,136]`。由于 Doc 77 的边界增益就取自这些话题缓存，
“Doc 77 的动作增益会受此影响”在结构上成立；本轮**不**声称影响量级
（见 §3）。

### 2.2 同步观测下，方向反差在 B、C 两处都完整重现

| 运行 | 动作 | 旋转 rad | 动作段 ΔJ_T | 历史链接数 | 归因贡献 |
| --- | --- | --- | --- | --- | --- |
| B_Lminus_1 | L− | 3.401 | +0.02253 | 5 | +0.02253 |
| B_Lminus_2 | L− | 3.745 | +0.00993 | 5 | +0.00993 |
| B_Lplus_1 (a02) | L+ | 3.800 | +0.28332 | 11 | +0.28332 |
| B_Lplus_2 | L+ | 3.429 | +0.34938 | 11 | +0.34938 |
| C_Lminus_1 | L− | 3.447 | +0.00237 | 5 | +0.00237 |
| C_Lplus_1 | L+ | 3.831 | +0.12441 | 6 | +0.12441 |
| C_Lplus_2 | L+ | 3.404 | +0.10642 | 4 | +0.10642 |

每组 L+−L−（B 4 组：0.2608/0.2734/0.3268/0.3394；C 2 组：0.1220/0.1041）
**全部为正**。B 的 L+/L− 组均值 0.300（组间散布 0.079）；
C 的组均值 0.113。行动段其余指标（动作时长恒 34.6 s）不随方向变化。

### 2.3 差异的机制是“旋转方向改变了回访链接的创造”

对每段动作做 provenance 归因（`karto_edge_provenance.jsonl` 的
`constraint_created` 记录 + `constraint_provenance_audit.csv`）：

- 动作段新增边 8–19 条：`PREVIOUS_SCAN`（链内相邻）、`RUNNING_SCAN_CHAIN`、
  `NEAR_CHAIN` 三类；其中“历史链接”（一端指向动作前的历史状态）B-L+ 11、
  B-L− 5、C-L+ 4–6、C-L− 5；
- ΔJ_T 与历史链接贡献**逐运行完全相等**（< 1e-13）：动作的信息价值
  = 历史链接的信息价值；链内边与 local-only 闭环贡献为 0（诊断口径）；
- 返回段（动作前）也存在方向间不对称（C_Lplus_2 的返回段单独贡献 +0.1772，
  C_Lminus_1 只有 +0.0298），说明两条运行在动作前的图状态并不相同——这也是
  §3 不给因果结论的原因。

### 2.4 事后几何：方向差异“发生在旋转过程中”，前置统计量看不见它

动作前冻结特征（`analysis/pre_action_feature_audit.csv`）与结局无分离：
历史段航向重合（B: L+ 0.678/0.692 vs L− 0.659/0.699；C: L+ 0.225/0.247 vs
L− 0.238）、关键帧门残余（0.063–0.471 rad，交错）、预测关键帧数（恒 6）。
GT 侧（`corrected_gt_metrics.csv`）：目标点地图误差 0.031–0.091 m；动作段
相对位姿误差平移 ≤0.094 m、旋转 ≤0.085 rad；动作前后 GT 误差变化
−0.011…+0.060 m。即：效应存在于信息结构，而不是现有可测的定位误差。

## 3. 不能得出什么结论

1. **不能给出因果/剂量结论**：L+/L− 不是对“匹配的动作前状态”的操纵
   （返回段贡献不同，见 §2.3），n=2/格、C-L− n=1，且无显著性或泛化声明。
2. **不能得出“地点条件效应”**：两处都是 L+ > L−，没有任何地点出现反向偏好；
   因此“按地点切换方向”的动机目前**没有观测支撑**。
3. **不能得出定位收益**：GT 误差量级小、方向间混杂；“信息增益”没有转化
   为可测定位/地图价值（本轮样本下）。
4. **不能量化 Doc 77 数值偏差**：本轮只给出“结构缺漏”（尾部 0–4 扫描 /
   0–10 边）；把它换算成 Doc 77 增益的具体漂移量不在本轮口径内（话题图
   只用于结构对照，不用于主值）。
5. **不能推断扫描被拒绝的原因**：拒绝原因在源码中不可观测
   （`REJECTION_CAUSE_NOT_OBSERVABLE`），本轮不将“未接受”解释为任何具体
   原因。
6. **屏障语义的边界**：屏障覆盖“水位扫描已处理完成”；它不声称所有扫描
   都被处理，也不声称无等待地图丢弃（这些另有计数，逐边界登记）。
7. **不声称最小规则可行**：没有可计算的前置判别量；任何“选择方向”的
   规则在当前证据下都是事后拟合。

## 4. 单一下一步建议

四个备选（`TEST_MINIMAL_PRE_ACTION_RULE` /
`STOP_PURE_ROTATION_AND_EXPLORE_LOCAL_RECOVERY` / `MECHANISM_OBSERVATION_ONLY` /
`TECHNICAL_STOP`）中的选择：**`MECHANISM_OBSERVATION_ONLY`**。

理由：测量链已经可信（§1），效应已确认（§2.2），机制已部分定位（§2.3）——
动作段的全部价值来自“旋转带来的历史链接”，而它**不被**现有前置特征预测
（§2.4）。要开发任何“最小规则”，先需要一个可计算、动作前可见、且与历史
链接创造有稳定关系的信号。因此下一步只做**机制观察**：

- 目标问题：历史链接的创造由什么局部几何量控制（例如旋转扫过的方向扇区
  与旧地图/旧扫描集的重叠结构、`NEAR_CHAIN` 端点在旧图中的角色）；
- 边界：不改协议、不加动作规则、不调参；观察量仅来源于同步 dump 与
  provenance（本轮的链路直接复用）；
- 触发条件：只有当观察量能在**动作前**稳定区分“高/低历史链接结局”时，
  才讨论 `TEST_MINIMAL_PRE_ACTION_RULE`；否则研究线保持观察态或转为
  `STOP_PURE_ROTATION_AND_EXPLORE_LOCAL_RECOVERY`。

`TECHNICAL_STOP` 不适用：观测链已通过 28/28 边界资格，故障只有一例物理
完成度事件。`STOP_PURE_ROTATION_...` 暂不采纳：证据不支持“旋转方向无效”，
恰恰相反；但也不支持立即开发切换规则。

## 5. 运行账本与保护声明

| # | 回合 | 尝试 | 结果 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | D79_B_Lplus_1 | a01 | FAILED（物理） | GT 0.771 m > 0.75 m；证据完整保留 |
| 2 | D79_B_Lplus_1 | a02 | SUCCEEDED | 4/4 边界合格 |
| 3 | D79_B_Lminus_1 | a01 | SUCCEEDED | 4/4 边界合格 |
| 4 | D79_C_Lminus_1 | a01 | SUCCEEDED | 4/4 边界合格 |
| 5 | D79_C_Lplus_1 | a01 | SUCCEEDED | 4/4 边界合格 |
| 6 | D79_B_Lminus_2 | a01 | SUCCEEDED | 4/4 边界合格 |
| 7 | D79_B_Lplus_2 | a01 | SUCCEEDED | 4/4 边界合格 |
| 8 | D79_C_Lplus_2 | a01 | SUCCEEDED | 4/4 边界合格 |
| — | D79_C_Lminus_2 | — | NOT_STARTED | 预算耗尽（8/8），如实登记 |

保护：Doc 77（`p1_continuous_revisit_actions_20261010`）、Doc 78
（`p1_continuous_boundary_review_20261012`）、v14/CD 系列、两处旧结果根目录
只读未动；生产二进制与三个 launch/param 文件哈希运行前后一致；本轮全部
代码为新增（`tools/realizability_pilot/doc79_sync_validation/`、`doc79_ws/`），
无参数、阈值、协议对旧实验的回写。

本地专有文件（受仓库 `.gitignore` 惯例覆盖、不入库，SHA-256 登记于
`analysis/local_only_files.csv`）：共 99 个文件、381 MB——包括 8 份
`scan_stream.jsonl`（含完整 LaserScan 载荷，22–52 MB/份）、全部
`gt_stream.jsonl`/`keyscan_stream.jsonl`/`loop_events.jsonl`/
`karto_edge_provenance.jsonl`/`native_processing_ledger.jsonl`、全部运行日志
（`rosout.log`、`roslaunch.log`、`roscore.log`、`driver.log`、`map_saver.log`）、
7 份 `final_map.pgm` 与 7 份 `author_outputs/prior_map_*.pickle`。未对任何
文件使用 `git add -f`。其余全部运行证据（同步/话题图、边界清单、规格、
轨迹、`pose_graph.g2o`、`final_map.yaml`、分析 CSV 与图表）随提交入库；
原始流的逐文件 SHA-256 使本地归档可被独立核验。
