# REVIEW_PACKET — ALC-Screen 01

`ALC_SCREEN01_REVISIT_DECISION_FEASIBILITY_AUDIT` (`OFFLINE_RESEARCH_DIRECTION_SCREENING`)。

- 研究基线：`4746834ffa44504443fd07214105fe850d6f94e6`（`research/phase4c-formal`）
- 本分支：`research/alc-revisit-screening`（worktree `/home/wcqw/ac-slam_alc_screen`）
- 研究日志：`docs/research_log/81b_active_loop_closure_direction_screening.md`
- 全部命令只写本结果根；无 ROS/Stage/Gazebo、无 Karto 修改、无新数据采集。

## 0. 判决速览

| 关卡 | 判决 | 一句话依据 |
| --- | --- | --- |
| G1 TASK_HEADROOM | PASS（完整探索上下文）/ 局部探针无空间 | map3 完整运行 APE 0.24–1.93 m 独立重算；Doc79 局部目标误差仅 ~1.5–6 cm |
| G2 ACTION_CHOICE_SPACE | UNRESOLVED | 有 35 条局部/147 条全局几何假设，但 0 条安全认证移动路线、0 个已观测候选结果 |
| G3 NOVEL_METHOD_NECESSITY | UNRESOLVED | P-ALC/RA-L/Zhang/Region/Lighthouse/OSM/Kim 覆盖基本思想；固定基线未被证明不够 |
| A1 | A1_UNRESOLVED | 两种走廊几何但无安全认证；局部任务收益未证明 |
| A2 | A2_HYPOTHESIS_ONLY | 全局需求背景合理；候选收益全部未观测 |
| **最终** | **C — ACTIVE_REVISIT_HYPOTHESIS_ONLY** | 不授权方法开发；仅保留 A2 必要性探针协议 |

旧结论 `STOP_PURE_ROTATION_SELECTION` 保持不变。

## INDEPENDENT_REVIEW_HANDOFF

1. **研究基线 SHA**：`4746834ffa44504443fd07214105fe850d6f94e6`。本次全部日志、
   数据与代码均可从该提交 + 未提交的本任务新文件复现；上传后以分支
   `research/alc-revisit-screening` 的提交记录为准。
2. **实际可用的旧数据**：Phase4C 选择表定位的 45 条正式运行（map3 15 条复用
   Phase4B 目录——**不得重复计为新增独立样本**；map8 15 条；Mexico 15 条失败运行
   单列比较）；Doc79 7 条可信运行（28 张同步图 + native 扫描/GT/UID/provenance）；
   108 个旧主动动作缓存端点；3 个 Karto 阳性对照；作者 prior/TSP/离线目标函数
   （45/45 精确复现保存路径）。
3. **只有摘要、没有原始文件的数据**：LAEG2022 仅出版预览（执行机制未知，不作
   新颖性依据）；Pathak2018 仅作者文本、无可信 PDF 页锚；Region v3 与
   Retroactive 经 HTML 读取（PDF 获取失败，`literature/acquisition_manifest.json`
   登记 `acquired=false` 与错误）；Zhang v3 正式发表状态未核实；Mexico 15 条为
   未完成运行；旧 campaign 文档以 `audit/archived_document_inventory.csv` 登记。
4. **A1 决策状态与候选**：决策状态 = `G_arrival_sync` 及此前已知数据（7 个前置
   bundle）；候选类型 SKIP / 5 s STAY / ~2 m 同侧 FIXED_RETRACE / ~4 m 出入
   LOCAL_PATH_A/B；共 35 条几何假设（`local_path_candidates.csv`）；**0 条安全
   认证**（无动作前 occupancy，拒绝用 Stage 地图）。
5. **A2 决策状态与候选**：`G_before_return_sync`（严格早于回访执行）；每状态 19 个
   历史区域 medoid + continue/no-ALC，共 147 条（`global_target_candidates.csv`）；
   B0 最近代理（非 A* 可达最近）、B1 原 RA-L 目标函数（仅原空间离线复现，不对
   新簇打分）、B2 CONCEPTUAL_BASELINE_ONLY（无可靠概率模型，不造数）、B3 1 m
   姿态计数代理、B4 不回访（无同初态结果）。
6. **实际改善空间**：map3 完整探索 APE RMSE 0.24–1.93 m（中位 0.62），map8
   0.068–0.245 m（中位 0.144）；最终地图 F1 map3 0.32–0.58、map8 0.53–0.67
   （identity registration、0.2 m 容差，受未覆盖区/墙厚影响，只作评价）；
   Doc79 局部目标地图误差 ~1.5–6 cm、动作节点位移 ≤14.2 mm。完整探索的米级误差
   证明全局需求存在，但不证明回访可修复、更不证明局部探针需要多走一条路。
7. **实际执行过的候选**：Doc79 只执行了 B/C 点的旋转动作；正式 45 条只执行了各自
   策略选中的目标/路径（Original/Always-Trace/Selective 各 5×3 组）。平移路线候选、
   非选中区域全部**未执行**。B0 与 B3 首选 7/7 不同——这是代理排序冲突，不是
   已观测决策错误。
8. **只有理论预测的候选**：所有移动路径候选与所有非选中全局区域，均标
   `COUNTERFACTUAL_OUTCOME_UNOBSERVED`；`screening_summary.json` 记录
   `observed_new_candidate_counterfactuals=0`。
9. **前置信息泄漏检查**：候选生成/评分模块不导入 GT/地图评价模块、不读
   `G_action_done/G_final`、不使用动作后约束；Stage 地图仅离线评价；
   测试 7–9/26/29/37 覆盖（防火墙合同）。`gt_check.py` 只在评价与身份核对中使用 GT。
10. **episode 混用检查**：测试 32 拒绝跨 episode 图拼接；bundle 按 episode 冻结；
    旧 CD 后缀拼接实验不作为因果证据（沿用 Doc80 结论）。
11. **与前沿工作的具体重叠**：P-ALC §V Eq9/10 + Alg1–3（概率-收益-成本目标评价；
    §VI 固定到点 360°）；RA-L2024 §V-A（历史段重走）；Zhang v3 §IV（航点重走/减
    急转）；Region v3 §IV-B（区域双向凸包稳定化）；Lighthouse §III-C/D（最近历史簇、
    全景/GGS）；OSM Alg2（全局历史节点/剩余覆盖重规划）；Kim2015 §4.2/4.3（路径-
    条件测量/终端协方差）；Retroactive §III-E（存储数据重看，不涉物理目标选择）；
    LAEG（图式 loop-aware 下一区域选择，仅预览）。逐篇细节见
    `literature/literature_matrix.csv` 与 `closest_prior_work_review.md`。
12. **简单固定基线无法解释的现象**：**未发现**。B0/B3 的 7/7 冲突可由代理口径差异
    解释；旧缓存的 24/63 与 39/45 正差分不能追认为主动成功率；没有"基线必然做错"
    的任务级证据。
13. **机制解释类结果**：同步阶段 ΔJ_T、首次历史交叉边 29 条及 0.897 nats 集合
    删除贡献、`creation_sequence` 与边 index 逐条对应、来源枚举（含
    `NEAR_CHAIN`/`RUNNING_SCAN_CHAIN`）。这些**不是**任务效果。
14. **任务效果类结果**：45 条完整运行 APE/F1 重算（45/45 与旧表一致到 <5e-7 m /
    全等）；Doc79 独立重算目标 GT 误差与 Doc80 修正一致；无任何 ALC 动作被证明
    改善任务指标。
15. **仍不能验证的假设**：当前 Doc79 局部探针的任务收益空间；A2 目标排序的必要性；
    P-ALC 概率模型在 2D Karto 上的校准；无 occupancy 下的可达/安全认证。
16. **实现成本**：A1 若重启 ≥16 episode（4 臂×2 区域×2 区组）+ 动作前 occupancy
    记录 + 足迹级安全认证；A2 必要性探针 12 episode（3 对照×2 几何×2 区组）+
    同步图/provenance/occupancy 记录；当前**没有**可直接部署的选择器代码。
17. **最小下一步实验**：仍为设计态 `protocol/minimal_A2_prospective_plan.md`
    （`DESIGN_ONLY / NOT_AUTHORIZED`）：两几何情形 × {B4 继续任务, B0 最近合格目标,
    B1 原 RA-L} × 两随机区组、连续原生运行、在线权限一致、GT 仅评价。A1 计划
    `protocol/minimal_A1_prospective_plan.md` 明确"本轮不建议启动"。
18. **结论的三个最强反例**（最可能推翻"C/不投入"）：
    a) map3 完整运行米级 APE → 全局任务需求真实存在，若某个回访策略能显著修复，
       方法必要性会回摆；
    b) 旧缓存非顺序交叉边在 map3 24/63、map8 39/45 为正 → 主动动作可能确有真实
       实现增益，只是旧观测口径无法归属；
    c) B0/B3 排序 7/7 冲突 → 简单基线并不彼此一致，"更复杂评价"未必毫无余地。
    三者的共同弱点：a) 未证明回访可修复且非局部探针问题；b) 缓存滞后/动作窗外
    污染未排除；c) 冲突仅是代理口径差异，非决策错误证据。故均不构成 GO 依据。
19. **唯一推荐方向**：**C — ACTIVE_REVISIT_HYPOTHESIS_ONLY**：暂停 ALC 方法开发；
    不并行投入 A1；仅当另行批准时执行 A2 必要性探针（12 条上限）。旧
    `STOP_PURE_ROTATION_SELECTION` 保留。
20. **重要路径**：数据与结论
    `results/research_direction/alc_revisit_screening/{analysis,audit,literature,protocol,figures}/`；
    代码 `tools/research_direction/alc_revisit_screening/`（`analyze.py` 重建
    analysis/audit 主体、`summarize.py` 生成 A1_A2 决策矩阵与汇总、`figures.py`
    出图、`run_tests.py` 测试与日志）；研究日志
    `docs/research_log/81b_active_loop_closure_direction_screening.md`。

## 特别问题回答（Q1–Q8）

- **Q1（是否存在实际任务需求，还是只有图信息收益）**：全局存在真实误差
  （map3 米级 APE），但**没有证据**表明额外回访能修复它；当前局部探针（Doc79）
  的误差远小于评估噪声带。图信息收益确实存在，但它是机制量，不是任务需求证明。
- **Q2（候选动作是否真有区别）**：几何上每状态两种走廊方向与若干长度，
  FIXED_RETRACE 与 B 同侧同走廊（只是长度不同）；**没有**已认证的安全可达差异，
  也**没有**移动候选的执行结果。不能凭几何生成宣称"候选空间成立"。
- **Q3（现有数据能否判断未执行候选的收益）**：不能。未执行目标的真实约束不可观测；
  本任务拒绝用最终图/GT 为它们赋予收益（`COUNTERFACTUAL_OUTCOME_UNOBSERVED`）。
- **Q4（是否存在可预测的真实历史关联规律）**：未建立。动作前特征（可见性/新颖性
  代理）不分离观测结局；旧缓存差分不能归属到决策时刻。
- **Q5（固定回访路径或最近目标是否已经足够）**：**无法排除其足够**——没有对照
  证明固定重走/最近合格目标造成任务损失；这是不支持新选择器的核心理由。
- **Q6（与 P-ALC 及历史重走方法的实质差异）**：目前找不到"同等输入权限下、
  强简单基线会系统性做低贡献决策且事前可解释"的具体缺陷；概率-收益-成本、
  历史重走、区域稳定化、最近历史簇均为已有覆盖。
- **Q7（A1 还是 A2 更值得投入）**：都不达"值得开发"；A2 比 A1 多一项理由——
  全局任务需求背景真实且 A2 存在干净的决策点，因此仅 A2 保留条件性必要性探针；
  A1 在现有局部目标上连任务收益空间都不足。
- **Q8（是否正式退出主动回环方法研究）**：以本筛选为准——**退出方法开发投入**
  （暂停），研究方向判决保持 C：不是证明领域无价值，而是现有数据不支持把
  A1/A2 直接立为 SCI 方法问题。若要重开，必须先出现第 18 项中的可证伪反例证据。

## 测试证据

- `audit/test_results.json`：**38/38 通过**（真实 bundle 合同回归；变异输入仅作
  单元 fixture；无 ROS/仿真命令；无真实碰撞认证——该项如实标为未实现）。
- 复现命令见 `README.md`；所有输出限定在本结果根。

## 已知限制（如实登记）

- 移动候选 0 条安全认证；G2 因此保持 UNRESOLVED，而不是 PASS/FAIL。
- 局部与全局候选的真实收益都不可观测（各自只有一个已执行动作）。
- 旧缓存端点诊断不能替代同步 provenance；完整探索与局部探针不共享同一 G_pre。
- 文献中 LAEG 仅预览；Region v3 / Retroactive 为 HTML 读取；Zhang v3 发表状态未核实。
