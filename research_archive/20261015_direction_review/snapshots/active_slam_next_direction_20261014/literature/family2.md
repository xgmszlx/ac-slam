# 家族 2：实际有效测量收益与主动探索（定向排重）

审查日期：2026-10-14。结论：宽泛的“接受概率×信息收益”“观测后更新目标”“利用实际测量统计评估路径”已有直接前例，属于 **NOVELTY_CONFLICT**。本轮最多保留一个问题资格候选，状态 **CANDIDATE_ONLY**；不存在已经成立的新算法贡献。本文不以六组核心 ICP 调用作为真实主动 SLAM 证据，也不从全文或实现缺失推断作者没有实现某功能。

## 读取范围与证据边界

本轮只读复用旧缓存：topic_audit 的 `uncertainty2025.txt`、`p_alc2024.txt`、UM/FIT 固定提交源码；AB 的 `pathak2018.txt`；ac-slam 的 `kim2015.txt`。方法引用采用章节/公式锚定，不引用未经本轮 PDF preflight 确认的页码。

新检索补充 FIT 正式出版社的长正文节选，保存为 `sources2/fit_publisher_indexed_excerpt*.txt`：涵盖 §3 总览、§3.6 部分 FIM 推导、§4 实验设置、§4.2 及 Fig.14 讨论。直接正文访问返回 403，SSRN 访问也失败，**没有获得连贯的最终全文**；阈值细则、完整 §4.3、结论与全部消融依然未知。保存的是出版社搜索索引提供的节选，不是假称下载了全文。UM arXiv HTML 与作者 FIT GitHub 页面本轮在线可访问；DA-BSP 作者 PDF 页面可在线打开。Kim 作者 PDF 通过本机 HTTP 下载成功，保存 `sources2/kim_author.pdf/.txt` 和 `kim_preflight.json`，重核 §4.3.1 与结论与旧缓存相符；浏览工具失败不等于本机下载失败。所有新文件均在本轮独立目录。

## 五篇最近邻矩阵

| 工作、出处与来源 | 原始问题与实际机制；动作/信息来源 | 实验、强基线与实际 SLAM 边界 | 重合、作者明确不足、未知/代码成本 |
|---|---|---|---|
| **Optimizing Exploration with a New Uncertainty Framework for Active SLAM Systems**, RAS 2025, 193:105059。[全文](https://arxiv.org/html/2506.17775v1)，[作者代码](https://github.com/Seba-san/UncertaintyMap) | UM 以 dispersion probability 的 log-odds 更新表达地图测量不确定性；UF 提出补测目标，SiREn 联合衡量覆盖与不确定性；修改 RRT* 传播位置/landmark 协方差。实际测量持续更新地图和后续目标，已构成观测反馈。二维 LiDAR 地面机器人选择目标和路径。 | §5 比较 CF/UF 与 RRT/改进 RRT* 的四个组合。A.5 明确线性位置 KF、已知朝向、无 matching errors；不能据其协方差/SiREn 改善推断真实配准后端错误减少。 | **文献支持**：普通不确定性补测和反馈已被覆盖。A.5 明确实验限制。固定代码 SHA `7e5007307dc9525e3474cb6aaf1ac5ae65def811`；旧源码显示 orientation 来自 simulator，须移除这一依赖才能用于当前在线实验。公开/ROS1 不等于可信普通 SLAM 复现。 |
| **FIT-SLAM 2: Efficient 3D Exploration with Fisher Information and Traversability-Based Adaptive Roadmap**, RAS 2025, 194:105188。[出版社](https://doi.org/10.1016/j.robot.2025.105188)，[代码](https://github.com/suchetanrs/FIT-SLAM) | 自适应路网、局部/全局 frontier 排序、地形通行性和 FI 安全监测；控制地面机器人路线。 | 本轮补读正式正文节选确认 RGB-D/ORB-SLAM3 与 VLP-16 地形传感，且区分 GT 规划效率实验和 SLAM/FI 定位实验。比较 FIT1、NBVP、GB-Planner2、FAEL；作者报告不使用 FI 经常丢跟踪。 | **已验证源码**：SHA `8ca04125b75d873155de9e546b94abf52830ce7a` 的 BT 执行 FI 检测、取消导航、屏蔽视场并后退；普通健康触发改路已重合。尚不能确认最终论文/其他模块是否校准执行偏差；完整限制章节未知。ROS2 Humble/Ubuntu22.04，当前阶段只借鉴，禁止迁移。 |
| **Active Visual SLAM for Robotic Area Coverage: Theory and Experiment**, Kim & Eustice, IJRR 2015, 34(4–5):457–475。[作者稿](https://s3.us-east-2.amazonaws.com/publications.perl.engin.umich.edu/akim-2015a.pdf)，[DOI](https://doi.org/10.1177/0278364914547893) | §4.3.1 对 proposed/verified 视觉链接的经验频率按两端 local saliency 分箱并拟合 Bernoulli 成功概率；沿候选往返路径累积预期视觉信息与里程信息，评估末端协方差和覆盖，选择继续探索或重访。不是假设所有预测约束均实现。 | iSAM 视觉 SLAM、相机/水下惯性与深度等导航传感；合成/真实图像混合仿真及船体实机。对照 open-loop、deterministic revisit。 | **文献支持**：“用实际成功统计修正预期 SLAM 收益”有直接前例。结论明确单步贪心；未知空间 saliency 使用线性插值，多步预测未来特征/测量概率仍困难。完整可迁移作者系统代码未知。 |
| **A Unified Framework for Data Association Aware Robust Belief Space Planning and Perception**, Pathak et al., IJRR 2018, 37(2–3):287–315。[作者全文](https://indelman.github.io/ANPL-Website/Publications/Pathak18ijrr.pdf)，[DOI](https://doi.org/10.1177/0278364918759606) | DA-BSP 以 Gaussian mixture 同时推断位姿/关联，规划阶段边际化未来观测和 plausible associations；信念可增减模式，采用预期消歧/任务代价选择动作，不要求单一完全消歧观测。 | §6 有 Pioneer 实机与 Gazebo 激光强混淆办公室。BSP-uni/BSP-mul 基线；机器人选择路线而非仅改变后端阈值。比较关联正确性/模式数/规划推断成本。其任务与未知区域完整主动探索应区分。 | **文献支持**：关联歧义导致的错误接受/错误信念问题、主动去不同位置消歧已覆盖，传感器换为 2D ICP 不能形成新颖性。§7.2 明确非近视分支爆炸。全文说 opensource code will be provided；本轮未定位可直接运行的完整原系统，故代码可用性未知，不把 promised 当 released。 |
| **Probabilistic Active Loop Closure for Autonomous Exploration**, ICRA 2024, 18048–18054。[作者全文](https://assets.amazon.science/7b/55/cb3dafd14b5ba7210870af299c8f/probabilistic-active-loop-closure-for-autonomous-exploration.pdf) | 视觉得分/相对漂移预测单 keyframe 成功概率，聚合邻近 keyframe 的回环概率；Eq.10：概率×预期图不确定性下降−行驶成本；branch-and-bound 选择目标，随时间改变触发阈值。 | 实机窄 FOV 视觉/深度建图，多平面，ALCv1/ALCv2 对照；w100 仿真测试 Neighbor D-opt。实机因协方差获取成本用 distance-based proxy，不是完整图协方差实验。 | **文献支持**：概率加权收益直接重合。作者明确未来改进数据驱动回环概率、验证局部/全图 D-opt 等价、在机上用 Neighbor D-opt。完整作者代码本轮未核实。论文的地图质量图示/探索速度不证明任何具体新增的错误接受建模能力。 |

### 实现中可定位的排重证据

FIT 固定源码：`FisherInfoBTPlugin.cpp` 中 `tick()` 调用 `isPoseSafe()`；`active_slam_exploration.xml` 32–42 行依次有 `EvaluateFisherInformation`、`CancelAllNav2Goals`、`MarkLethalFOV`、`ExecuteRecovery backward_recovery_only=true`。`FisherInfoManager.cpp:isPoseSafe()` 获取候选视场 landmark、累加查表信息、与阈值比较；查表生成使用 `Q=Identity`。这是核读模块的事实，**不能据此断言全部代码或最终论文没有另一处 measurement model / uncertainty update**。几何 FI 也不能直接称作真实误差或经校准位姿协方差。

Kim §4.3.1 Eq.3 与 Fig.4 是最直接的新颖性冲突；P-ALC §V Eq.9–10 是概率乘收益的另一直接冲突。DA-BSP 导言明确讨论被前端遗漏的 false data associations，§6.5 比较不同路线的消歧效果；因此“把 incorrect-but-accepted 纳入动作评价”的问题级宣称也已有覆盖。

## 新增近邻警报

**ARAS: Ambiguity-aware Robust Active SLAM Based on Multi-hypothesis State and Map Estimations**, IROS 2020，[作者全文](https://robots.et.byu.edu/jmangelson/pubs/2020/Hsiao20iros.pdf)。这是比单纯 DA-BSP 消歧更接近“错误 accepted 约束＋未知区域探索＋地图改善”的邻居：§III.B 使用 ambiguous odometry（相同两位姿的多个测量）和 ambiguous loop validity 因子，MH-iSAM2 联合多个状态/地图解；§IV–VII 做多假设探索、主动重访剪枝与在线障碍安全验证。§VIII 有仿真和真实 RGB-D **人携式辅助建图**，不能冒称其全部实机结果是自动移动机器人执行。作者 §VI.A 明确尚未预测 future ambiguities，仅按当前 hypothesis 数触发，超预算会剪枝；§VIII.D 明确资源/鲁棒性权衡。此局限是否仍未被后续工作解决，本轮未知；简单改为预测触发也不能自动成立创新。完整当前作者代码本轮未知。

因此，将“联合状态/地图多假设”添加到候选机制，也不足以避开新颖性冲突；其后端/验证工程成本明显高于当前 RTAB-Map 信号资格。

**Visual Active SLAM Method Considering Measurement and State Uncertainty for Space Exploration**, Aerospace 2025, 12(7):642，[出版社](https://doi.org/10.3390/aerospace12070642)。本轮取得出版社索引长方法/实验节选，保存 `sources2/aerospace2025_publisher_indexed_excerpt.txt`；连贯全文访问失败，代码未知。

§4.2.1 基于 ORB 特征金字塔噪声、FIM/CRLB 和 D-opt 阈值选择前端测量；§4.3 构建局部 BA 状态不确定性并规划主动回环；有 NBVP/U-NBVP、ALCP/U-ALCP 比较。**文献支持**：一般“测量不确定性＋有效测量筛选＋主动路径规划”已存在，不能当新增贡献。是否处理系统性错误关联/在线执行校准未能确定，不能由其文字未提及直接作否定结论。

另检索到 IEEE/ION PLANS 2025 的 [Gaussian Process Regression for Learning Environment Impacts on Localization Accuracy of a UAV with Respect to UGV for Search Planning](https://www.ion.org/plans/abstracts.cfm?paperID=11854)，摘要称学习环境引起的 outliers/漏测并调整路径；仅摘要、页面日期存在不一致，**未知**，不作为已证实的完全覆盖，但“在线学习实际收益”不能在未核全文时宣布新颖。

## 唯一保留的问题资格候选

**同一探索目标存在两条安全且代价接近、几何预测信息相近的路径时，观测方向/重叠的差异能否稳定改变“错误但 accepted”的约束比例及最终地图误差，而合理被动鲁棒配准/图优化和现有几何感知规划仍不能消除该差异？**

这是 **CANDIDATE_ONLY** 的资格问题，不是已立项的论文方法。若仅观察到 ICP accepted 数变化、信息指标提高或较长路径更准，都不成立。

| 用户问题 | 证据限定的回答 |
|---|---|
| 1. 哪篇明确证明原始问题？ | **文献支持**：DA-BSP 证明混淆关联会导致错误信念且不同路线有不同消歧能力；FIT 正文报告低感知信息造成失跟踪。**未知**：本机 RTAB-Map 中同类任务损失与路径差异尚未证明；旧六组注册输出不够。 |
| 2. 现有方法解决什么？ | Kim 的成功概率/信息路径；FIT 的几何 localizability 安全路线；DA-BSP 的关联混合信念与消歧动作；P-ALC 的概率回环。故本研究必须与其思想等价基线比较。 |
| 3. 它们缺少什么？ | 可确认的只是 UM 实验不含 matching errors、Kim 单步/未知 saliency 插值、DA-BSP 多步分支成本、P-ALC 概率模型与 covariance 的实验限制。**没有证据证明这些缺陷在本机仍造成合理基线不能处理的损失。** |
| 4. 什么主动动作补充被动观测？ | **合理推测**：从目标同侧/另一侧经过安全侧移路线，改变有限空间的扫描重叠与混淆结构；动作需平移并获得实测扫描。全向二维 LiDAR 的原地纯旋转不能预设增加几何证据。 |
| 5. 动作安全吗？ | **未知**：先由在线 occupancy+膨胀障碍检验两条路线、同起终点及控制可执行性。不得用 GT 生成线上安全路径。现有 Stage 只提供技术条件，未证明候选路线资格。 |
| 6. 决策前预测有效吗？ | 已知局部 map/scan 的重叠、几何谱、候选关联差距、wheel/ICP 一致性可在线获取。**合理推测**：候选歧义程度有预测力。错误约束的 GT 真值不可在线用；association margin/后续一致性都未被证实是正确性标签。 |
| 7. 简单规则足够吗？ | **未知**，应先比较最短路线、保重叠/FI 简单路线、经验成功概率路线，以及相同输入下被动鲁棒前后端。如果其中之一解决问题，停止复杂预测器。 |
| 8. 可新增机制？ | 只有待验证需求：动作条件下的关联错误/偏差分布与延迟一致性校准，而不是 scalar accept probability。若能产生独立可信在线一致性信息，可再研究如何将其进入预测任务损失。**当前没有可宣称的新机制**，不开始算法开发。 |
| 9. 与最近邻是否重复？ | 泛化描述与 DA-BSP/Kim 高度重合。仅“工程更轻/二维实现/新反馈量”不足。必须核实能否改进 DA-BSP 既有近似的特定失败，而不是换术语。新颖性 **UNRESOLVED，风险高**。 |
| 10. 公开数据＋有限仿真能否验证？ | **合理推测**：已有 ROS1 RTAB-Map/Stage 可做短路线配对，公开原始 bag/配置/图节点关联和离线指标。固定轨迹公共数据可验证在线信号，但不能证明反事实主动路径收益。FIT 原路线代码公开却属 ROS2，大规模迁移成本不接受。 |

## 最小成本、门槛与停止条件

本轮只等待真实 SLAM 信号资格，不启动新增科学矩阵。需要 scan 时间戳→OdomInfo→图节点/边→地图版本→离线 GT 的可信对应；不能把 `accepted` 或 `covariance` 当真实正确性。

资格通过后，下一轮可以**设计并冻结**一个现成场景中同起终点、两条安全路线的最小配对。参数在第一条科学任务前冻结，报告所有失败与成本；不寻找特定坏地图/噪声/threshold。评价约束错误只用离线 GT，同步报告地图误差、RPE、行驶时间/距离及扫描数量。采样数应预先固定，结果不清晰时保留 UNRESOLVED，不自动扩大到 12 路线。

若只在独立配准函数存在差异，或无法关联图约束与地图结果，或被动稳健方法/简单路线足够，或在线信息不能预判路径差异，或归一化运动/观测成本后差异消失，均停止该候选方法开发。若功能实质已被 DA-BSP/Kim/后续工作覆盖，则 **NOVELTY_CONFLICT**，即使仿真工程可运行也不能 GO。

**投入等级**：当前日志关联与离线评价小；后续短路线资格小至中；实现可信候选关联信念并比较 DA-BSP 中至高。训练模型、完整 FIT ROS2 复现、重建船体视觉系统不属于最低成本路径。
