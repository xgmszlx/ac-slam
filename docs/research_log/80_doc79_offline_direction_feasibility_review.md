# 80 — Doc 79 的离线方向可行性复核：GT 修正、历史关联机制与动作前可预测性

2026-10-13。本轮为 Doc 80 `DOC80_POSTHOC_DIRECTIONAL_OBSERVABILITY_AND_UTILITY_AUDIT`
（`POST_HOC_OFFLINE_RESEARCH_CONVERGENCE_AUDIT`）：在**不运行任何新实验**的前提下，
对 Doc 79（提交 `4f290fc0691324e13158d72fa77c18278e28b71e`）的数据做最后一次
科研价值审计，回答「局部旋转方向与实际历史约束实现之间，是否存在执行前可识别、
且具有真实定位价值的规律？」。全部新代码位于
`tools/realizability_pilot/doc80_offline_review/`，全部新产物位于
`results/realizability_pilot/p1_doc80_offline_research_convergence_20261013/`；
Doc 76–79、v14、CD 系列与两处旧结果根目录**只读未动**；Doc 79 的冻结判决、
`final_gate.json` 与全部分析表未被修改（修正结果只出现在 Doc 80 的新根目录）。

## 0. 结论（三层判决）

1. **测量与 GT 有效性**：`SYNC_MEASUREMENT_REUSED_VALID`、
   `TARGET_GT_CORRECTION_VALID`、`PREACTION_FEATURE_INPUT_VALID` 全部通过。
2. **机制判断**：`A HISTORICAL_ASSOCIATION_MECHANISM_SUPPORTED`——动作段信息
   增益由**首次历史区重关联边**承载（A 类贡献合计 0.897 nats，占三类总和的
   94%；7 条运行中 6 条以 A 类为主导）；"方向可见性控制收益"（H1）未获得证据。
3. **唯一下一步**：`A STOP_PURE_ROTATION_SELECTION`——正式停止把"纯旋转选向"
   作为独立论文主线：不存在动作前判别量；所有观察到的地方/方向对都偏向 L+
   （固定策略解释无法排除）；修正后的目标 GT 没有显示定位收益。

**Doc 79 的旧结论不需要推翻**：同步测量与方向反差数值保持有效；本轮新增的
是（i）目标冻结机制与坐标外参的独立验证，（ii）目标 GT 的正确阶段口径，
（iii）历史关联的类别分解，（iv）严格冻结的动作前方向特征——最后一项给出了
负结果（不可判别），这正式终结"按地点切换旋转方向"的动机。

## 1. 输入完整性（§3.1/3.2）

- 账本：预算 8/8 消耗，7 条 `MEASUREMENT_VALIDATED`，1 次物理失败
  （`D79_B_Lplus_1` attempt_01 保留全部证据、重试为新 attempt），
  `D79_C_Lminus_2` 为 `NOT_STARTED`；尝试编号连续无缺口；磁盘目录数与
  套件簿记数一致（无隐藏补跑、无选择性删除）。交叉相减（B 4 组、C 2 组）
  在统计中**按描述性差值**登记，不是独立试验。
- 本地专有文件：登记表 99 条，逐文件 SHA-256 复核 **99/99 通过**
  （381 MB；含 8 份 `scan_stream.jsonl`、全部 `*.jsonl`/日志/`*.pgm`/pickle）。
  逐文件结果见 `audit/local_only_file_verification.csv`，无缺失、无损坏。

## 2. 目标冻结机制审计（§3.3，最高优先级）

Doc 79 中 `freeze_target` 使用**旧 topic 图**（`G_before_return` 话题缓存）
作为目标冻结输入，且参考位姿是 `map→base` 而图节点是 `map→laser` 位姿。
本轮复刻冻结算法（逐行等价）并做四重比较：

1. **复现**：在 topic 图上重跑冻结规则，7/7 与 `frozen_target.json` 完全一致
   （anchor、segment、5 个 target 全同）——复刻保真；
2. **同步图等价**：在 `G_before_return_sync` 上用同一参考重跑，7/7 全同；
3. **坐标系修正**：把参考位姿换算到激光系（+0.2 m 前向）重跑，7/7 全同；
4. **缺节点影响**：4 条运行的 topic 图在冻结时刻缺 1 个节点，但缺失节点
   从未进入 anchor/segment/target 选择结果。

结论：**旧 topic 图缺漏与 base/laser 混用均未改变冻结目标**
（`ORIGINAL_FROZEN_TARGET_ESTIMAND` 不变；敏感性结果仅登记，
`audit/target_freeze_consistency.csv`、`target_freeze_sensitivity.json`）。

## 3. 坐标系、外参、身份（§3.4/5.2）

- Karto 节点位姿 = **map→laser**：`MultiMapper` 用 `odom→laser`（
  `offset_frame`/`laser_frame` 来自 `cpp_solver/param/ros.yaml`：
  `offset`、`base_laser_link`）作为 odometric pose，dump 输出 corrected pose。
- 外参从记录反推：`base-in-laser` x = **−0.1993 … −0.2000 m**（sd ≤ 0.0067），
  与 Stage world `hokuyolaser(pose [0.2 0 −0.2 0])` 及
  `geometry.py LASER_OFFSET_X=0.20` 一致 → 0.20 m 硬编码**被验证**，非假设。
- 模型校验：节点位姿 ∘ `T_LASER_BASE(−0.2,0,0)` 与记录 `map_base` 在
  接受时刻的残差：均值 0.025–0.048 m、最大 0.152 m（≈ TF 发布滞后，
  `map_base_age_s≈0`，机器人在运动中）。
- 身份：dump `index == state_id`、state id 连续、跨阶段 `unique_id→state_id`
  映射稳定，7/7 运行全部成立；激光真实参数：FOV **180.0°**、901 束、
  距离 0–25 m（读取真实 LaserScan 字段，未预设）。

## 4. 边界水位与 provenance 身份（§4.1/4.2）

- **水位语义**：水位只断言驱动已见扫描的完成，不含"之后无扫描"。实测
  **28/28 边界**在同步图中的节点**零个**晚于水位（停留段不产生新关键帧），
  因此各阶段图无跨阶段污染（`audit/boundary_watermark_sensitivity.csv`）。
- **provenance 身份**：7/7 运行 0 个重复 `(source,target)` 端点键；
  终图边 171–187 条**全部**能对应唯一创建记录（覆盖率 100%）——Doc 79
  的字典索引在本数据上无损（`audit/provenance_identity_audit.csv`）。

## 5. 目标地图 GT 的修正（§5，本轮核心）

**旧口径的缺陷**：Doc 79 `corrected_gt_rows()` 的 `TARGET_MAP_ERROR` 对四个
阶段复用目标**接受时刻**记录的 `map_base`，所以该值跨阶段恒定（表中确实
逐阶段重复），无法反映后续图优化。

**修正实现**：对每个冻结目标，从四张同步图分别读取节点位姿
（map→laser），按经验证的外参换算为 map→base，再与目标接受时刻的 GT
（线性 x/y + 最短角 yaw 插值，记录括夹间隔）在**动作前拟合**的单一
map→GT 刚体对齐下比较（对齐输入严格早于动作开始，测试第 10 项保证）。

**结果**（35 个目标·阶段，7 运行 × 5 目标）：

| 阶段 | 修正均值误差 | 最大 | 节点位移（相对上一阶段）|
| --- | --- | --- | --- |
| before_return | 0.0153 m | 0.0612 m | — |
| arrival | 0.0158 m | 0.0612 m | 均 1.4 mm / 最大 5.9 mm |
| action_done | 0.0165 m | 0.0601 m | 均 3.2 mm / 最大 14.2 mm |
| final | 0.0165 m | 0.0601 m | 0.0 mm |

- 与 Doc 79 原值之差为 **−0.018 … +0.001 m**，量级与"驱动 TF 记录 vs 图节点"
  的 2–5 cm 滞后带一致；
- **关键回答**：新增历史约束之后，目标节点**几乎不动**（≤14.2 mm，多数
  ≤6 mm），目标地图误差没有阶段意义上的改善（变化 ≤0.5 mm 均值，且非单调）；
  因此 Doc 79 原指标数值上接近正确，但它的口径无法证明这一点——本轮把它
  变为可证明的事实（`analysis/corrected_target_map_gt.csv`、
  `target_gt_original_comparison.csv`）。

## 6. 机器人边界 GT（§5.6）

在 `G_arrival` 与 `G_action_done` 两个边界（机器人回到同一位置）比较：

- GT 真实位姿差：6/7 运行 = 0.0000 m（含 B_Lplus_2 = 0.31 m，列为
  "可比性较弱"）；航向差 0.0–0.33 rad（动作回收角未完全归零的残余）；
- 定位误差变化（action_done − arrival）：+0.0069、**+0.0634**、+0.0074、
  +0.0017、−0.0076、−0.0028、−0.0001 m——1 例改善、3 例恶化（阈值 ±5 mm）、
  均值 +0.0098 m；
- **GT_EFFECT 不构成收益**：没有一致改善；B_Lminus_2 的 +6.3 cm 恶化与
  信息增益无关联证据。用于"整段平均值之差"的因果声明被明确禁止。

## 7. 历史关联机制细分（§6）

**类别定义**（按端点阶段，新增非顺序边）：A = 触及首次历史区；B = 触及
仅返回段状态；C = 两端均在动作后创建。端点阶段由接受时间与阶段窗口判定
（`analysis/historical_link_classes.csv` 逐边列出 edge_index、
端点、provenance、creation_sequence、match_response、协方差迹）。

- 边数：A 29 / B 18 / C 10（合计 57 条新增非顺序边）；
- **集合级联合贡献**（固定线性化诊断口径）合计：A **0.897** /
  B 0.025 / C 0.029 nats；**6/7 运行 A 类主导**；
- **C 类并非无价值**（如 B_Lplus_2 的 C 贡献 0.023），类别只表示时间来源，
  不表示闭合有效性；低度节点也不自动等于高价值；
- **两种比较分别报告**（§6.3 要求）：`closure_contribution == historic_
  contribution` 复现到 ≤5×10⁻¹⁴；而 `delta_J_action_sync − historic_
  contribution` 为 **−3.0×10⁻⁶ … +1.8×10⁻⁵**（C_Lplus_1 最大 1.8×10⁻⁵），
  两者不是同一项，`analysis/doc79_contribution_comparisons.csv` 精确登记；
- 贡献分析含**逐类单独删除**与**A→B→C 层级删除**（顺序依赖已注明）。

**机制含义**：方向反差 = "旋转后是否与首次建图区域建立历史链接"的差异；
C 地 L+ 连接首次历史区（0.1244/0.1064 全部来自 A），C 地 L− 只产生
0.0024；B 地同理（0.283/0.349 全部来自 A，L− 仅 0.0225/0.0099）。

## 8. 动作前方向可观测性（§7，严格冻结）

**防火墙**：`feature_construction.py` 只接受 `slice_pre_action` 生成的
bundle（规格、冻结目标、路线、协议标记、两张动作前同步图、动作前扫描切片），
对任何含 `action_done/final/gt_stream/provenance/rosout/scan_stream` 的路径
直接拒绝；outcome 侧独立模块；测试 17–21 覆盖。

**几何**：真实雷达 FOV 180°，旋转 ±π/2 后的扫过扇区各 270°，**共同扇区
180°、各自独有 90°**（角度绕环测试覆盖）。历史/返回阶段节点（108–114 个）
在两个方向下的"几何可见"数量几乎相同：L+ 94–101、L− 95–99；**独有扇区
只有 0–7 个节点**；可见性差值与观测方向结果**不对应**（可见性差为正的
运行里既有 L+ 也有 L− 执行）。

**代理指标**：`GRAPH_NOVELTY_PROXY`（非链度数倒数之和）差值 +2.0…−3.5，
同样不分离——已明确标注为几何代理，**不是 Karto 匹配概率**。

**反事实边界**：每个状态 s0 只观测到被执行方向的结果；`V(L+|s0)` 与
`V(L−|s0)` 无法从现有数据同时取得，**没有**逐状态最优动作准确率可言；
本轮只做特征可计算性、几何合理性、已执行动作解释与描述性对照。

**竞争假设**（`analysis/directional_competing_hypotheses.csv`）：
H1 方向可见性（HYPOTHESIS_ONLY，几何无分离）；
H2 动作前图状态（DIAGNOSTIC，部分协变量无法识别）；
H3 固定 L+ 优势（OBSERVED：7/7 运行 L+>L−，**无法排除**）；
H4 信息增益无定位收益（OBSERVED：修正 GT 无改善、机器人边界误差混合）。

同时说明两个既有的概念性缺陷：Doc 79 的 `direction_overlap_fraction` 是全
历史航向重叠而非方向专属扇区；`gate_predicted_keyframes` 使用绝对值转角，
对 ±π/2 天然不可分——两者在本轮都**不再被当作充分的方向选择特征**。

## 9. 统计与取值修正（§8）

- 独立单位 = episode：7 条运行的实测量逐条列出（增益、真实转角、动作位移、
  观测时长、GT 变化）；交叉差值 4（B）/2（C）组仅作描述性差值。
- `final_gate.json` 的 `measurement_validated=false` 语义澄清：其判据是
  `valid_attempts == total_attempts`，被 1 次物理重试打破；实际
  `VALID_RUN_MEASUREMENT_PASS = true`（7 条），`SUITE_COMPLETE = false`
  （7/8 计划回合）——旧文件未被覆盖，语义在新报告中说明。
- 行动成本并非完全一致：实际累计转角 3.40–3.83 rad（计划 π），
  B_Lplus_2 另有 0.31 m 位移路径、时长恒 34.6 s；信息/角度比只作辅助。

## 10. 研究价值问答（§9，含证据等级）

- **Q1**（信息增益是否受冻结/阶段定义影响）：冻结目标对 topic/坐标系不敏感
  （§2）；阶段归属无水位后污染（§4）→ **OBSERVED：不受影响**。
- **Q2**（修正 GT 后历史目标地图是否改善）：无实质改善（≤0.5 mm 均值、
  混合方向、≤14.2 mm 节点位移）→ **OBSERVED：没有**。
- **Q3**（增益是否主要来自首次访问区）：是（A 类 94% 联合贡献，
  6/7 主导）→ **DIAGNOSTIC（固定线性化口径）**。
- **Q4**（同一前置状态下两方向的潜在可见性是否不同）：几何上几乎相同
  （独有扇区 0–7/110）→ **OBSERVED：无实质差异**。
- **Q5**（是否有明确物理解释）：方向差异的物理载体（哪一束激光打到哪里）
  未被现有特征分辨；H1 缺物理证据 → **NOT_IDENTIFIABLE（在当前数据）**。
- **Q6**（能否排除"固定 L+ 就足够好"）：**不能**——所有组 L+>L−，
  无任何反向地点 → **OBSERVED：无法排除**。
- **Q7**（即使能预测更多历史关联，是否有定位/成本收益）：本轮没发现
  可测定位收益；成本近似恒定 → **OBSERVED（限于本任务尺度）**。
- **Q8**（继续纯旋转选向 vs 转向定位退化主动恢复）：见 §0 判决 A。

## 11. 最终判决与下一步（§10）

- 三层判决与证据见 `analysis/final_research_gate.json`；
  备选 B/C/D 未采纳的理由逐条登记其中。
- **唯一下一步：`A STOP_PURE_ROTATION_SELECTION`**。
  会改变该判决的最小证据链（若未来重开）：同初态反事实配对显示方向依赖的
  历史链接效应；或存在可样本外预测历史链接的动作前观测量；或更长时域内
  出现任务级（定位/成本）收益。
- **下一阶段选题建议（§10.4）**：
  - 旧方向继续投入的必要性：**低**——决策相关的"条件性"没有证据，
    固定策略解释无法排除，且无任务收益；
  - 转向"定位退化主动恢复"的理由：本平台已有完整同步观测链（原生扫描
    屏障、provenance、同步图导出）与边界分析管线，可直接度量恢复动作的
    定位效果；这是有清晰任务收益指标的 Active SLAM 子问题；
  - 可复用部分：`doc79_ws` 观测补丁、边界导出服务、ledger/清单约定、
    Doc 80 的冻结特征与 GT 修正管线、回归测试；
  - **不应再重复**：无前置信号的地方条件旋转切换；基于 topic 缓存的边界
    归因（尾滞后已知）；把交叉差值当独立试验；把信息增益当任务收益。

## 12. 测试、保护与复现

- 新增离线测试 27 项（覆盖要求的 24 个失败模式 + 真实数据检验）：
  `PYTHONPATH=catkin_ws/python /usr/bin/python3 tools/realizability_pilot/doc80_offline_review/test_doc80.py`
  → **27/27 OK**（含冻结复现、真实外参残差、防火墙、插值、绕环、统计语义）。
- 旧测试回归：`test_doc79.py` 31/31、`test_continuous_revisit.py` 19/19、
  `test_boundary_review.py` 13/13 全部通过——Doc 79 结果未受影响。
- 复现流水线：
  `PYTHONPATH=catkin_ws/python:tools/realizability_pilot /usr/bin/python3 -m doc80_offline_review.run_all`
  → 全部 audit/analysis 输出；`figures.py` 生成 4 张图（PNG+SVG）。
- 保护：两个既有的用户修改文件未被触碰；Doc 76–79 与旧结果根目录只读；
  本轮无 ROS 运行、无 Karto 修改、无参数扫描、无模型训练。
