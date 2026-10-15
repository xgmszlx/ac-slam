# 主动 SLAM 研究选题重新审查

日期：2026-10-14，Asia/Shanghai。范围：真实文献、指定研究分支、公开代码、当前平台和最小实验设计；不运行新科学实验，不开发正式方法。

**1. 结论与当前研究状态**

**尚无法证明任何候选值得直接立项为SCI方法论文。** 值得做一次有上限的问题验证的是：**探索路径的几何/可见性预测与真实SLAM配准可靠性发生失配时，执行反馈能否比固定风险门限和即时健康规则更早、更正确地决定继续当前路线还是切换到另一条安全路线？** 这是A/B家族里的具体、可否证问题，状态`CONDITIONAL_PROBLEM_PROBE`。没有“新颖性已确认”“方法有效”或“稳定正收益”结论。

选择它的原因是成本与可证伪性：本机已有可读诊断的ROS1后端、2D仿真GT和可编译frontier；不需要先训练网络或建立语义动态仿真。**合理推测**：残差/实际配准有效性可能提供几何代理缺失的信息。**未知**：当前场景是否有持续任务损失、替代路径是否改变结果、反馈是否比简单规则增加决策价值、最接近全文是否已经覆盖这套机制。

各重点分支本轮本地/远端SHA一致；主目录两处未提交修改保留。Doc81-Q3 `QUALIFICATION_PASS`只涵盖一条正常环境短任务，`scientific_episode_count=0`；ALC审查仍为`ACTIVE_REVISIT_HYPOTHESIS_ONLY`，G2动作空间/G3方法必要性未决。旧纯旋转`STOP_PURE_ROTATION_SELECTION`不变。没有把旧全程误差、图信息变化或技术修复重新解释为新方法收益。[本地分支日志](../ac-slam_alc_screen/docs/research_log/81b_active_loop_closure_direction_screening.md)、[Q3报告](../ac-slam_doc81/docs/research_log/81_Q3_runtime_and_timestamp_qualification.md)。

**2. 文献审查的具体发现**

本轮建立18篇/项近邻矩阵，每项分别登记论文身份、方法、传感器、真实SLAM、动作、未来收益、反馈、实验指标、代码、重合、作者明确限制及未知。见[矩阵](literature/nearest_neighbors.md)和[CSV](literature/nearest_neighbors.csv)。表格中的“未确认”不代表作者没有实现。

| 用户指定工作 | 最重要的判别 | 对选题的约束 |
| --- | --- | --- |
| RA-L 2024 Graph-Based | prior拓扑、D-opt/长度、回访与重规划；真实Karto/Stage和实机 | 拓扑信息/回环成本排序非新；本地初始化相同协方差不是后端实现概率模型。[全文](https://arxiv.org/html/2308.16522v2) |
| RAS 2025 Uncertainty Framework | UM/UF/SiREn已直接处理不确定地图补充观测；附录线性KF、已知航向、不考虑匹配错误 | “增加uncertainty frontier并回访”重合很高；作者代码从Gazebo取航向，不能直接作为本方案online输入。[全文](https://arxiv.org/html/2506.17775v1) |
| FIT-SLAM 2 | RAS2025正式发表；Fisher监测/低信息区域剔除与adaptive roadmap；当前BT有取消目标、屏蔽区域、后退 | “低信息就改路”已有代码；ROS2/Humble整套本轮不适合部署。未完整取得最终全文。[论文](https://doi.org/10.1016/j.robot.2025.105188)、[代码](https://github.com/suchetanrs/FIT-SLAM) |
| LA-Planner/IROS2025 | 共视约束和localizable yaw corridor兼顾未知区域感知；实机用ORB-SLAM3 | 可靠性约束本身已覆盖；公开模拟位姿/特征不足失败与真实tracking必须区分；地面底盘没有独立yaw。[全文](https://arxiv.org/html/2503.15273v1) |
| ActLoc/CoRL2025 | 已有SfM地图条件下预测方向定位成功率；不是未知地图在线SLAM实验 | 学习视点收益已覆盖；已承认SIFT域泛化和多分类改进限制；当前硬件/动作不直接适配。[全文](https://arxiv.org/html/2508.20981v1) |
| Help Me Through/T-RO2025 | 针对过渡区域tracking failure，有模仿学习与online-learning微调 | 主动视觉避免失位、学习反馈不是空白；全文未得，不能说没有我们设想机制。[作者机构摘要](https://pure.kaist.ac.kr/en/publications/help-me-through-imitation-learning-based-active-view-planning-to-/) |
| Dynamic hierarchical NBV/2026 | ORB-SLAM2、动态物体预测、feature probability map和local NBV，仿真+实机 | 普通“语义过滤+预测动态物体+NBV”缺乏新增机制；作者明确突然大遮挡仍会tracking loss。[全文](https://www.nature.com/articles/s41598-026-36259-x) |
| Degradation-Aware/2026 | 已有Hessian谱、方向2D risk map与Hybrid A* | 纯几何退化地图加规划代价直接被覆盖；全文/代码/后端反馈未知。[IEEE](https://doi.org/10.1109/CIS-RAM71614.2026.11668505) |
| Potential Fields+MPC/2026 | ORB-SLAM3、probabilistic grid、势场、非完整MPC和真实轮式探索 | 拼APF和MPC不新；精确位姿收益模型/统计/代码尚不明确。[出版方](https://doi.org/10.1016/j.conengprac.2026.106897) |

补充近邻改变了对“缺口”的理解：

- **文献支持**：P-ALC已经把闭环概率、预期不确定性下降、成本组合；Kim2015已预测沿路径可能实现的视觉约束。不能把“考虑观测成功概率”或“沿途观测质量”当新增思想。[P-ALC](https://cdn.amazon.science/7b/55/cb3dafd14b5ba7210870af299c8f/probabilistic-active-loop-closure-for-autonomous-exploration.pdf)、[Kim2015](https://s3.us-east-2.amazonaws.com/publications.perl.engin.umich.edu/akim-2015a.pdf)。
- **文献支持**：Stachniss2004已用在线不确定性决定历史重走何时停止；Region Based v3已有区域质量稳定化、双向路线和失败checkpoint。执行反馈或反馈停止本身不新。[2004](https://www.ipb.uni-bonn.de/papers/stachniss04iros.pdf)、[Region v3](https://arxiv.org/html/2504.10416v3)。
- **文献支持，摘要范围**：UCRMI已把pose与map uncertainty共同用于探索；SEER已学习预测未来覆盖增益。前者反驳“此前只顾覆盖”，后者反驳“收益预测本身是空白”。[UCRMI](https://doi.org/10.1109/TASE.2024.3360442)、[SEER](https://arxiv.org/html/2209.11034)。
- **合理推测**：仍可能有价值的是**一个明确的模型失配类型，及在真实后台保护仍开启时，用部署时真实反馈校准该失配，产生额外可验证的路径选择价值**。本轮核读的FIT信息监测模块未见这类校准，但全文未全得、其他论文细节未知，因而不能从未见推断全球不存在。

**3. 候选排名**

| 排名 | 具体候选 | 问题证据 | 新机制状态 / 创新风险 | 建议 |
| --- | --- | --- | --- | --- |
| 1 | B并受A约束：反馈校准的路径配准可靠性预测与承诺/切换 | 文献证明预测/真实观测可能受匹配和环境影响；本机存在在线信号，但未证明该反馈必要 | 高风险；必须区别FIT监测、P-ALC概率和既有online learning | 仅有限问题探针；未立项 |
| 2 | D：针对可解释地图缺陷的补充建图，区分缺覆盖和定位错误造成的缺陷 | 文献UM/UF、P-ALC、region stabilization；旧地图指标混合覆盖和误差 | 高风险；只提出uncertainty map和重访已被覆盖；“缺陷归因→哪种观测能修复”仍是未知假设 | 需先取得可信地图缺陷和在线归因；暂缓 |
| 3 | A独立：几何退化/可定位性约束探索 | 文献与代码最充分 | 基本思路已被FIT/LA/UCRMI/2026 degradation覆盖；只做风险cost/阈值缺乏创新 | 作为强基线，普通版本不立项 |
| 4 | C：动态场景剩余静态特征的时空可定位性约束主动视觉SLAM | 真问题；2026 NBV及Help Me Through直接竞争 | 高风险+更多依赖/GT/动态可控性；普通语义NBV组合缺乏创新 | 不作为本机首个方向 |
| 不保留 | 原地旋转回环选向、历史图增益选择器续作 | 旧STOP/任务headroom和候选安全未决 | 没有新证据支撑改变结论 | 保持冻结 |

上述排名是**验证投入优先级**，不是估计SCI录用概率。当前没有任何候选获GO_FOR_METHOD。

**4. Q1—Q10逐方向筛选**

以下A为独立几何可靠性约束，B为推荐的反馈校准路线，C/D按用户定义。标签简写：F=已验证事实，L=文献支持，H=合理推测，U=未知。

| 问题 | A | B | C | D |
| --- | --- | --- | --- | --- |
| Q1 真实问题存在？ | L：弱结构会损害配准；U：本后端任务损失 | F：旧预测/约束实现不同；U：造成持续错选和任务损失 | L：遮挡/语义剔除导致可用静态特征少；U：本机器人 | F：旧map质量不一；U：缺覆盖和畸变各占多少 |
| Q2 最强相似？ | 最近邻FIT、LA、UCRMI、degradation；没有统一可比排行榜 | 最近邻FIT监测、P-ALC、Kim、FastSLAM停止、Help Me Through online learning | dynamic hierarchical NBV；Help Me Through；LA | UM/UF、P-ALC、Region stabilization、EM virtual map |
| Q3 有证据不足？ | L：LA仿真用feature proxy；U：更好的geometry cost能弥补多少 | L：ActLoc域变化有限制，UM没有关联错误；U：部署残差校准的具体缺口 | L：2026 NBV承认突然大遮挡lost；U：可执行干预能否防住 | L：UM线性/已知航向设定；U：普通SLAM地图不确定性是否可信 |
| Q4 新机制？ | H：方向/时间相关风险约束；已知重合高，未保留独立新公式 | H：在线校准“预测结构→有效配准”的动作条件误差；用其决定承诺/切换；非简单加权 | H：可持续静态特征的短时风险预测及安全绕行；与既有FPM高度近似 | H：先识别缺陷原因和可修复性，再选补充观测；不是UF本身 |
| Q5 简单规则够？ | H：很可能；已有后台退化保护/B1必须先比 | U：B1/B2可能已够；若够则STOP，Beta统计/固定权重不得包装方法 | U：绕行、限速/阈值可能够；须做无需网络基线 | U：固定重扫/均匀补图可能够；须同预算比较 |
| Q6 真动作？ | 选择安全通路/途经点；不假设独立pitch | 同目标2条安全移动route，继续/取消/回退/切换 | 固定相机随底盘运动/转弯观察；独立云台U | 安全可达的补图移动route/历史段；不只是转动 |
| Q7 改实际SLAM？ | L：别人的实机可；U：本机选择因果收益 | U：旧方向差不等于可比反事实；必须新连续route实验 | L：2026 NBV有真实SLAM；U：当前机器人 | L：文献可改善地图；U：哪些缺陷由可控观测修复 |
| Q8 事前预测信息？ | F：online map/scan；H：raycast结构风险；不是真协方差 | F：odom diagnostics字段+map；U：路线上预测力、迟到/条件变化 | H：静态特征/对象轨迹/遮挡；U：物体未来和可见深度 | F：online map可取得；U：不依赖GT的畸变检测/uncertainty |
| Q9 真实online决策？ | 可用map/scan/odom；GT仅评价，几何proxy需验证 | 延迟监督可用实际配准失败/内点；GT不进学习或决策；真实损失关联U | 可用图像/跟踪/分割；不能读取sim actor未来轨迹 | 当前确定占据图不能充当posterior；得先建立可靠online质量变量 |
| Q10 最小实验？ | 2map×2route×3区组，强后台保护保持；不同路线是否改变RPE | 同左先做真实性；G2过后比较B0/B1/B2，再谈反馈模型 | 2静态场景固定行人事件、相同RGB-D后台和route，真实tracking/GT及B0/规则/NBV | 2冻结地图缺陷、fixed resurvey/质量选择/继续，实际误差与覆盖/成本；不把GT缺陷给planner |

**5. 推荐问题、可能贡献和新颖性风险**

具体RQ：**在相同探索目标、移动预算和SLAM后台参数下，当候选路径的几何可观测性代理高估有效配准时，过去执行中得到的配准反馈，能否改善下一路径的可靠性预测，减少后续真实轨迹误差或任务失败，且优于固定几何门限和即时健康触发改路？**

这个RQ同时要求三个条件：存在稳定且可解释的模型失配；事前有非GT信息能辨别失配；这种辨别改变真实动作并带来额外任务收益。缺一个都不能开发“新选择器”。最强反对意见是：**你只是把普通健康监测加上风险cost，或者多走一点买更好扫描**。实验必须直接能证伪这两种解释。

若通过关卡，可能的方法贡献（全部H/U）：

1. 建立动作条件的**有效配准**预测，而非把可见几何直接当成位姿posterior；明确假设、失配范围和在线延迟标签契约。
2. 将预测误差/可信范围反馈给下一次路径承诺决策，有限信号不足时退回冻结强规则；保留后台本身的退化处理。单独加Beta计数、EWMA或contextual bandit不是充分贡献。
3. 在保持任务覆盖/运动预算时证明：动态校准比冻结同模型和即时阈值拥有额外价值，同时说明在哪些健康场景没有收益。价值应在真实轨迹端点、failure和cost下体现，不能只在内点、entropy或预测AUC上成立。

数学研究目标可暂写为：在名义安全可达路径集合中最小化时间，约束下一短时窗的配准失效预测风险≤预算；但当前没有校准概率、没有valid risk bound、没有满足约束的执行证明。该约束式是问题描述，**不是新方法/保证**，不在本轮编码。机会约束、信息增益加权及MPC重规划早已有研究基础。

新颖性判定必须先补P06/P08最终全文、核查FIT完整实现和TASE测量假设；已有研究完全覆盖“低信息避险”“估计成功概率乘收益”“按当前状态重规划”“execution反馈停止重走”这些泛化思路，本轮直接否决它们作为创新点。只有具体失配校准的增量证据才可能改变这个判决。

**6. 最合适的开源基础**

建议首个新问题探针使用**已安装RTAB-Map ROS1扫描ICP + 本轮编译通过的explore_lite + move_base(navfn/DWA) + Stage**。这是H级工程选择；RTAB-Map完整本机运行尚未资格。选它因为诊断接口现成、2D scan无需训练，并能在独立workspace保持旧Karto结果不变。它不是最先进SLAM的宣称，也不是把后台更换当科研贡献。

已有Karto/Nav2D体系继续只读作为工程阳性参照、已知GT/时间配对工具来源；不再把复杂回环实现实验作为当前主要动作设计。FIT/LA/ActLoc分别作为近邻和机制对照，不承诺当前环境能完整复现。见[平台表](PLATFORM.md)。

**7. 最小实验设计**

完整设计在[protocol/minimal_probe.md](protocol/minimal_probe.md)。从map3、map8开始，不改地图、噪声或后台保护；同一个前沿形成两条已知free路线，长度比≤1.20，名义footprint安全与实际执行均资格。在线使用map/scan/实际配准诊断；GT/world只进入隔离评价。

第一步科学筛选仅12条连续episode（2map×2route×3区组），另最多4技术尝试；新预算与旧Doc81独立、公开。它只回答动作是否改变任务损失和是否存在预测失配；不生成正式方法结果，也不能冒称在线B2策略已经跑过。随机区组不等于同G_pre反事实，首轮小样本不给显著性/跨场景校准保证。

主要评价是固定1s窗口RPE的route-level p95，辅以APE/任务失败、有效估计缺口、共同后续段误差和地图边界质量。全部统计实际路径、时间、回退和计算成本，完整保留失败。只有问题真实性过关，才新开B0最短route、B1固定几何规则、B2即时健康改路的闭环必要性检查；B1/B2够用就退出。

**8. 风险、四类失败和退出**

最主要风险为：后台保护已经解决问题；两条真实安全route不存在；几何proxy失配只在不可预测噪声里出现；在线label与真实位姿错误脱钩；改路响应太晚；改善来自额外观察/绕行成本；最接近论文已经覆盖；磁盘/时钟资格不足。

明确区分：**技术失败**不给科学否定；**问题未证实**只否定当前平台/任务的headroom；**机制不足**表示反馈预测/控制没有额外价值；**创新不足**表示前人或简单方法已覆盖。不得互相转换。没有问题/动作空间或只有GT能决策时，不再加噪、换地图、加旋转角度或降低效果门限。

**9. 下一轮工程任务（可直接开工的测量阶段）**

1. 在新独立workspace封存所有输入和配置，取安装RTAB-Map官方scan例子的真实依赖，建立无GT在线输入的launch；不碰旧overlay。先完成短程建图、导航、诊断有效性资格。
2. 从Q3只读复用时间戳/TF配对合同，新建collector记录scan、odom、OdomInfo/Info/links、occupancy/costmap、planned/actual route、decision wall/sensor time与候选哈希；GT单独存。参数/消息为明确接口，AI生成代码必须以日志证据验收。
3. 给固定frontier层增加候选导出和单控制authority；生成两条名义安全SE(2)路线，做footprint与实际路线一致性检查。不能执行则退出而非继续设计预测模型。
4. 先发布/封存一份12回合问题筛选配置和随机顺序、预算、continuous endpoints、测量误差界；完成后按四类失败作结，不自动开发算法。
5. 文献侧取得P06/P08/FIT完整全文，并把同输入/动作/反馈/代价的逐机制重合审查补齐。若近邻覆盖或强规则够用，取消本选题，保留collector和公开基线成果。

这些任务的本轮状态均是设计，未授权后的大规模实验/训练/方法部署均未执行。**最终科研判决：当前无候选可确认立项，保留一个可解释、可停止、低工程成本的真实性与必要性探针。**
