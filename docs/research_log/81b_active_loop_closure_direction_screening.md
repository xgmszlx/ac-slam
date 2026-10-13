# Doc81b：主动回环候选决策与方法必要性审计

日期：2026-10-13。任务：`ALC_SCREEN01_REVISIT_DECISION_FEASIBILITY_AUDIT`。
输入基线：`4746834ffa44504443fd07214105fe850d6f94e6`。
独立 worktree：`/home/wcqw/ac-slam_alc_screen`；分支：`research/alc-revisit-screening`。
没有新仿真、ROS、后端重放、模型训练或生产planner修改。Doc81与旧实验保持原样。

## 1. 结论先行

| 关卡 | 判决 | 实际依据 |
| --- | --- | --- |
| G1 TASK_HEADROOM | **PASS，限完整探索上下文** | map3完整探索有0.24–1.93 m的独立轨迹误差；不是全部场景都只有厘米级误差 |
| G2 ACTION_CHOICE_SPACE | **UNRESOLVED** | 动作前图可产生不同几何候选，但无边界在线栅格，不能认证安全可达，也没有多候选实测结果 |
| G3 NOVEL_METHOD_NECESSITY | **UNRESOLVED** | 未证明固定重走/最近合格目标留下任务收益缺口；P-ALC、PDN、历史重走/PGS已覆盖基本思想 |

唯一正式建议：**C — ACTIVE_REVISIT_HYPOTHESIS_ONLY**。

当前发现还不足以形成一个可直接开发的普通SCI方法问题。不要从“后端测量影响图信息”
直接跳到“我们需要一个动作选择器”。A1在现有局部目标上连明确任务收益空间也不足；
A2有较合理的全局需求背景，但没有对照证明目标排序需要比简单基线更复杂。

**暂停ALC方法开发，不投入A1并行路线。** 如果之后愿意批准最后一项必要性验证，
只保留A2的三对照、两几何情形、最多12条原生连续episode小探针。本轮只写协议，
没有批准或启动采集。旧 `STOP_PURE_ROTATION_SELECTION` 不变。

## 2. 实际分析的数据与保护

主要结果根：`results/research_direction/alc_revisit_screening/`。

- 从Phase4C选择表定位45条真实目录，重算全部原始GT/SLAM轨迹和45张最终地图。
  map3、map8各15条完成运行；Mexico15条失败运行单列，不纳入完成效果比较。
  **map3的15条实际复用Phase4B目录，不能重复计作新增独立样本。**
- Doc79七条可信原生连续运行：28张同步图、native扫描/GT、UID接受日志和逐边
  provenance。从原图重算四阶段J_T；独立重算140条历史目标·阶段GT误差。
  失败的B_Lplus_1 attempt01保留；其成功attempt02才纳入；C_Lminus_2未启动。
- 108个已开始的旧主动动作作缓存端点诊断，区分启动、waypoint全部完成和早停。
  不将旧缓存差分包装为同步/因果边增量。
- 使用作者原始纯函数和保存的prior/TSP，45次重算初始优化路径，45/45与事件记录
  完全一致。没有修改目标函数、重解TSP或给新历史簇编造RA-L评分。
- 三个旧Karto阳性对照复核原JSON、图和g2o；其显式接受事件与marker端点证据仍
  支持“Karto能形成历史关联”，但旧图缓存滞后，不能单靠缓存测量效果。
- Doc76–80日志/审查包/旧gate与较早campaign做只读库存/SHA审计。Doc76的CD几何
  拼接、Doc77的错误阶段收益、Doc78固定最终线性化归属均不作真实动作因果证据。

原始大文件仍在主工作区，本次不复制进GitHub。发布前后核验实际读取文件SHA、
两个工作区HEAD/分支/status，以及用户两个未提交Python文件SHA。具体数量由
`audit/input_integrity.json`给出，不把未遍历的全仓库忽略文件宣称为已逐字核验。

## 3. G1：定位确有全程误差，但不等于局部回访可修正

### 3.1 独立重算完整探索

| 地图 | 完整运行数 | APE RMSE最小/中位/最大 [m] | 最终边界F1范围 |
| --- | --- | --- | --- |
| map3 | 15 | 0.2401 / 0.6226 / 1.9310 | 0.3159–0.5842 |
| map8 | 15 | 0.0680 / 0.1441 / 0.2454 | 0.5299–0.6734 |

使用最近GT、0.05 s容差、无新对齐/缩放。作者两条TUM都针对laser；用raw world-base
GT、记录起点和0.2 m外参验证转换，残差约7.1e-5 m。重算APE与旧表差 <5e-7 m。
native state/UID接受时间与TUM时间也逐项一致到1e-6 s。源代码链与限制在
`audit/map_and_frame_audit.md`，不是靠报告标签确认。

旧before图缓存中确有历史位姿误差，map3的缓存历史RMSE范围约0.05–1.92 m；
不过before缓存距动作开始可滞后数秒甚至483 s，**这些值不作为精确回访前因果状态**。
最终修正轨迹仍有米级误差，足以证明map3存在任务级改善空间，而不是证明某个
回访目标、某条路线或ALC机制必然能消除它。

地图F1用保存的栅格/参考图、identity registration、0.2 m容差复算，45/45差为零。
它受到未覆盖区域与GT厚墙/估计薄墙影响；不能把低IoU/F1全部认作地图重影，更
没有同步前后地图可证明主动动作改善了墙面。Stage图只作离线评价，不用于候选。

### 3.2 当前局部探针缺少任务收益空间

Doc79五个旧目标的均值：before_return 1.53 cm → arrival 1.58 cm → action_done
1.65 cm → final 1.65 cm。独立重算与Doc80修正一致。最大目标误差约6.1 cm；动作
带来的节点移动最多14.2 mm，没有一致GT改善。转换舍入误差不是全部评估噪声，
这些小值必须连同native接受时间、TF延迟和前置拟合口径解释。

所以：完整探索的G1 PASS，不能替当前局部A1探针颁发“需要多走一条路”的PASS。
图信息改善也不能替代这个任务关卡。

## 4. 真实历史关联：机制很清楚，选择器必要性仍不清楚

| Doc79 episode | 实际动作 | action ΔJ_T [nats] | 新首次历史交叉边 | 目标平均误差变化 [mm] |
| --- | --- | --- | --- | --- |
| B_Lminus_1 | L- | 0.02253 | 4 | +0.091 |
| B_Lminus_2 | L- | 0.00993 | 2 | -0.473 |
| B_Lplus_1 a02 | L+ | 0.28332 | 6 | +1.634 |
| B_Lplus_2 | L+ | 0.34938 | 6 | -1.051 |
| C_Lminus_1 | L- | 0.00237 | 1 | +0.001 |
| C_Lplus_1 | L+ | 0.12441 | 6 | +4.583 |
| C_Lplus_2 | L+ | 0.10642 | 4 | +0.100 |

creation_sequence−1与同步edge index逐条对应，端点state/UID核验；来源实际包含
`NEAR_CHAIN`、`RUNNING_SCAN_CHAIN`。首次历史交叉边共29条，其集合删除诊断贡献
约0.89719 nats，复现Doc80机制线索。**固定最终线性化删除贡献不等于同步阶段增益**，
更不等于真实定位改善。删除返回桥导致图断开时明确NOT_EVALUABLE，不伪报零增益。
逐边响应/协方差/来源写入 `historical_constraint_edges.csv`，不以边数排序替代信息价值。

347有效帧预算的总动作观测约34.6 s；实际旋转完成约5.9–8.9 s，另有完成/导出等待。
`G_action_done`到`G_final`图没有继续变化，额外静止未新增关键帧。
这能解释阶段与观测预算，却**没有测量“提前停止”的策略效果**：D0/STAY/skip也不能
被改称已执行的立即停止或不回访臂。

七次都是各自的历史和G_pre，不能将L+/L-差异读成严格匹配反事实。
没有建立可预测的动作前规律，没有训练任何模型。

## 5. 旧0/21到底支持什么

`analyze_phase4c_formal.py:attribute_run`只将显式闭环事件按native scan时间和历史
目标集合交集归属。map3 Original的0/21是该口径的结果，不覆盖全部近邻/运行链
历史约束。因此“机器人完成waypoints但显式事件没归属”成立；“根本没有历史信息”
不能从这里推出。

108个实际开始动作中，map3 63个、map8 45个；完整waypoint序列分别61/36个，其余
包含早停。缓存非顺序新旧交叉边诊断在map3 24/63、map8 39/45为正，但旧缓存
可能覆盖动作窗外的边；不能把这些分子追认为active success rate。

这是一项**测量解释缺口**，不是已确认的新目标选择算法缺陷。Doc79的同步provenance
解决了后续观测问题，不能追溯修补旧缓存缺失的创建时刻。

## 6. A1候选：有两种走廊几何，没有已认证的选择空间

严格使用G_arrival，以及之前已知的历史state/UID。先冻结输入、生成候选，才读取
动作结果；候选函数不导入GT/地图评价模块，不读取G_action_done/G_final。

每个状态列出SKIP、5 s STAY、同侧约2 m历史段FIXED_RETRACE，以及前后约4 m
历史段的LOCAL_PATH_A/B（出后返回）。移动候选从真实历史节点顺序提取、laser→base，
航向按前进切线/原地转向估计；不把历史输出朝向直接复用于反向行驶。

实际几何长度范围：FIXED_RETRACE约4.12–6.58 m；LOCAL_PATH_A约8.73–10.32 m；
LOCAL_PATH_B约8.31–10.50 m。**FIXED_RETRACE和B共用同侧走廊，只是长度不同**，
因此不是三种独立路线几何，只能说每次有两种方向的几何假设。

它们是关键帧弦线而非通过footprint审计的连续驱动走廊。缺少前置online occupancy，
本轮全部移动候选安全/可达性NOT_CERTIFIED，0条可部署认证路线；没有借Stage地图
填这个缺口。预估时间采用明示的v=0.4 m/s、ω=0.5 rad/s，不是实际导航时长。
历史邻近/朝向/端点与已有边数量只是代理，不是scan overlap或实现概率。

**A1_UNRESOLVED，当前不值得优先投入。** 路线几何不同不证明其任务收益不同，更
不证明固定重走不够好。

## 7. A2候选与原方法评分

严格使用G_before_return，不带已选B/C目标、arrival图或GT。按固定4 m格聚合既有
历史节点，选择实际节点medoid而非空白几何中心；每个状态19个区域，另列continue/noALC。
没有把不同episode图拼成同一次决策。

- B0：欧氏最近代理，不是已经运行的A-star最近可达目标；最近簇可能是刚经过的
  区域，保留其accepted_state_gap，不事后删除来扩大复杂选择空间。
- B3：目标附近1 m内既有姿态数量。与B0首选7/7不同，但只说明两种代理排序
  冲突；没有真实候选收益证明其中谁对谁错。
- B1：新历史簇不是原prior/TSP顶点空间，缺少状态映射，不填自创“RA-L分数”。
  另在原空间运行精确原函数，45/45重现保存的初始优化路径：map3 utility比TSP
  高5.68%–6.59%；map8高6.18%。所有prior边初始d_opt一致，实际代码没有校准
  的backend measurement接受概率。这是模型范围，不自动等于“代码有bug”。
- B2：`CONCEPTUAL_BASELINE_ONLY`；缺少可靠概率模型/view score，没有造概率值。
- B4：没有同初态不回访的真实结果，仍是未观测对照。

实际旧策略的全程结果只是描述性：

| 地图/策略，各5次 | APE中位 [m] | active路程均值 [m] | active时间均值 [s] | 狭义目标闭环 |
| --- | --- | --- | --- | --- |
| map3 Original | 0.802 | 88.87 | 257.34 | 0/21 |
| map3 Always-Trace | 0.603 | 173.54 | 604.12 | 0/21 |
| map3 Selective | 0.605 | 104.93 | 328.68 | 1/21 |
| map8 Original | 0.117 | 68.82 | 150.02 | 5/15 |
| map8 Always-Trace | 0.103 | 106.56 | 314.22 | 5/15 |
| map8 Selective | 0.172 | 63.73 | 148.16 | 4/15 |

不是相同G_pre的目标选择实验；不声称更长trace使APE因果改善，也不将显式事件
之外的约束记为失败。其波动和缺少B0/B4，足以阻止“有新选择方法必要性”的结论。

**A2_HYPOTHESIS_ONLY**。A2较A1更接近已经出现的全程任务需求，但新区域的真实
收益都是 `COUNTERFACTUAL_OUTCOME_UNOBSERVED`，没有“选择器成绩”。

## 8. 文献核对后，缺口仍不是一个新公式

完整对照表与来源在 `literature/literature_matrix.csv` 和
`closest_prior_work_review.md`。核心位置：

- [P-ALC](https://cdn.amazon.science/7b/55/cb3dafd14b5ba7210870af299c8f/probabilistic-active-loop-closure-for-autonomous-exploration.pdf#page=4)
  §V Eq9/10与Alg1–3：已有概率、信息和成本目标评价；§VI固定到点360°。
- [Kim2015](https://s3.us-east-2.amazonaws.com/publications.perl.engin.umich.edu/akim-2015a.pdf)
  §4.2/4.3：已有沿路径的不确定视觉链接与终端协方差，不能说“路径条件测量”是新思想。
- [RA-L2024](https://arxiv.org/pdf/2308.16522v2) §V-A的历史段执行、
  [Zhang v3](https://arxiv.org/pdf/2503.17005v3) §IV的航点重走、
  [Region v3](https://arxiv.org/html/2504.10416v3#S4.SS2) §IV-B双向凸包稳定化，
  都是A1固定路线强基线，而不只是“地图/传感器不同”。
- [Lighthouse](https://arxiv.org/pdf/2306.10463v1) §III-C/D已有最近历史簇与全景/GGS；
  [OSM ALC](https://arxiv.org/pdf/2407.17078v1) Alg2已有global历史节点/剩余覆盖重规划。
- [Retroactive](https://arxiv.org/html/2607.13516v1#S3.SS5) §III-E重看存储数据，不是机器人
  物理目标选择；[LAEG](https://www.sciencedirect.com/science/article/pii/S092188902200104X)
  仅出版预览，不据未知执行细节判断重复或新颖。

“实现概率”“信息/成本”“历史重走”“图拓扑”“在线反馈”本身都不是可发表的新增
部分。目前缺的是：**同样输入权限下，强简单基线会系统性做出低真实贡献且造成
任务损失的决策，并有事前可用的解释信息**。本轮没有证明这件事。

## 9. 唯一下一步及其退出条件

不做新算法。设计的A2必要性探针：两种真实几何情形×B4继续任务/B0最近合格
历史目标/B1原RA-L×两个随机区组，最多12条连续原生运行。先冻结资格、安全图、
观测预算和顺序；在线输入权限一致，GT仅评价。不拼后缀，不调matcher，不迁移后端。

现有完整生产分支重复性没有因本轮离线/串行技术前缀而获证明。若不能恢复同一
SLAM状态，只能按随机区组讨论探索性策略层结果，不能叫exact paired G_pre。
新采集必须记录同步graph/provenance与occupancy，冻结旧状态GT/后续固定段误差及
运动/总观察成本，保留所有失败。

如果最近合格目标/不回访已达到同样质量且更便宜，停止选择器方向；如果出现
稳定任务损失且简单策略无法解释，才重新核对P-ALC等方法的具体缺口。若没有
明显前置误差或没有多个可达目标，直接停止，不能为了延续研究人为制造需求。

**本轮没有启动上述12条，也没有自动推进Doc81。**

## 10. 复现、测试与交付

依赖：系统Python3.8、NumPy1.24.4、SciPy1.10.1、NetworkX2.8.8（现有catkin/python
只作为离线Python依赖目录）、Pillow/YAML/Matplotlib。不要运行旧analysis入口，它们
可能写回旧实验目录。新命令只写本结果根：

```bash
cd /home/wcqw/ac-slam_alc_screen
export PYTHONPATH=/home/wcqw/ac-slam/catkin_ws/python
export PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
/usr/bin/python3 tools/research_direction/alc_revisit_screening/analyze.py
/usr/bin/python3 tools/research_direction/alc_revisit_screening/summarize.py
/usr/bin/python3 tools/research_direction/alc_revisit_screening/figures.py
/usr/bin/python3 tools/research_direction/alc_revisit_screening/run_tests.py
```

最终实际测试数与结果存 `audit/test_results.json` / `offline_tests.log`。测试以真实
前置bundle为主，变异输入仅测防火墙合同，不当科学样本。地图不可达排除是fail-closed
合同测试；真实路线碰撞认证由于地图缺失没有实现，明确保留G2 UNRESOLVED。

四张小图：全程/局部误差、同步图增量与GT变化、候选几何、原utility与实际成本。
输入SHA/来源表、逐组信息/GT/成本、候选与基线代理、15项门控矩阵全部可重算。
科研/PDF核读流程用于控制测量口径、全文缺口和反例；没有扩成大综述或新方法开发。

独立审查入口：`results/research_direction/alc_revisit_screening/REVIEW_PACKET.md`。
发布分支为 [research/alc-revisit-screening](https://github.com/xgmszlx/ac-slam/tree/research/alc-revisit-screening)，
本轮提交HEAD以最终上传核验回复和GitHub提交记录为准；无force push、旧分支不变。
