# A/B 主动 SLAM 科研决策报告

2026-10-14；独立审查目录 `/home/wcqw/active_slam_ab_decision_20261014`。本报告是唯一综合报告；矩阵、程序、原始输入、结果和失败日志为附件。判定标签：**已验证事实**＝本机文件/源码/实际运行可核对；**文献支持**＝所指原文支持；**合理推测**＝待验证解释或工程估计；**未知 / UNRESOLVED**＝证据缺失。运行结果状态为 `ANALYZED`，没有独立复验，不标 `VERIFIED`。

**1. 决策**

**本轮没有候选达到正式方法开发的 GO 条件。建议把 A 作为下一轮问题资格验证的主方向，B 作为备选；这不是推荐立即写两套算法。**

主方向的具体问题应收窄为：**在旧地图与新扫描发生大量冲突时，能否通过有预算的安全观测，区分整体定位偏差与局部持久地图变化，并决定是否提交局部更新；当两者同时出现或现有假设无法解释数据时，仍控制错误提交？** 首先验证强被动方法是否已经能解决，再判断主动选择是否必要。

选择 A 的依据是问题出处明确、作者 ROS1 代码可查、直接评价错误更新和冻结损失，资格实验较小。**文献支持**：Sensors 2023 讨论节明确承认大幅真实环境变化也会暂停更新，即使定位正确。[原文](https://www.mdpi.com/1424-8220/23/13/6066)。**已验证事实**：本轮 A 的简化主动消歧模型没有优于最近视点，不能作正向立项证据。**未知**：使用真实定位和强被动维护方法后，该任务损失是否仍存在、主动动作是否有额外价值、新机制是否未被覆盖。

B 的宽泛命题“根据真实匹配统计估计有效观测概率，再用于预期信息收益”已经有很强前例；单纯在线平滑、门限或概率乘收益不能成立为新增贡献。**文献支持**：Kim/Eustice 的 PDN 直接用历史 proposed/verified visual links 建立成功概率，并预测候选路径的信息和终端不确定性；P-ALC 也显式建模回环概率。[作者论文](https://robots.engin.umich.edu/publications/akim-2015a.pdf)、[P-ALC](https://cdn.amazon.science/7b/55/cb3dafd14b5ba7210870af299c8f/probabilistic-active-loop-closure-for-autonomous-exploration.pdf)。B 的主张必须进一步具体到现有概率模型无法表达的失配，否则新颖性不足。

| 资格项 | A | B |
| --- | --- | --- |
| 问题出处 | 文献支持，有作者明确限制 | 文献支持，理想观测假设有边界；真实本机任务损失未知 |
| 本轮运行 | 30 个合成 case × 5 个决策策略＝150 行；执行完成 | 6 组实际 RTAB-Map ICP 核心调用；执行完成 |
| 方法正收益 | 未证实，当前模型劣于简单基线 | 未测试任何主动策略；未证实 |
| 真实在线 SLAM 资格 | 未开展此新任务 | 现存目录为准备代码，RTAB-Map 完整闭环资格未通过/未运行 |
| 新颖性 | UNRESOLVED，主动消歧/地图核验已有强近邻 | 宽泛机制已有明显冲突；具体新增机制 UNRESOLVED |
| 决策 | `PRIMARY_PROBLEM_QUALIFICATION_ONLY` | `BACKUP_SIGNAL_QUALIFICATION_ONLY` |

**2. 当前仓库、平台与保护**

**已验证事实**：开始前检查了三个研究 checkout 的分支、HEAD、git status 和完整未提交 diff；结束后逐项比较相等。

| 目录 | 分支/HEAD | 当前内容 |
| --- | --- | --- |
| `/home/wcqw/ac-slam` | `research/phase4c-formal` / `4746834ffa44504443fd07214105fe850d6f94e6` | 两个用户修改：`tools/realizability_pilot/same_input_replay.py`、`se2_information.py`，均保留 |
| `/home/wcqw/ac-slam_alc_screen` | `research/alc-revisit-screening` / `c3f98f2bf0b6469041e441f4b0a836531732b941` | clean；旧负结果和资格边界保留 |
| `/home/wcqw/ac-slam_doc81` | `research/localization-recovery-phase0` / `7db448ff240d9633591f4187f58db399b3d409f9` | clean；Karto Q3 资格不是 RTAB-Map 资格 |

**已验证事实**：`active_slam_feedback_probe_20261014/status.json` 是 `PAUSED_BY_USER`，budget 的 attempts 是空数组；全部现存文件的 SHA256 前后相等。本轮没有修改暂停状态、借用旧预算、启动旧 12 条科学实验，或启动 ROS/Stage/Gazebo。已有候选路径、TF bridge、上游源码快照完整保留。早前 topic audit 只读复用。保护证据在 [开始快照](audit/workspace_before.json) 和 [结束核验](audit/protection_after.json)。旧 `STOP_PURE_ROTATION_SELECTION` 不变。

**已验证事实**：Ubuntu 20.04.6、ROS Noetic 的 Stage ROS 1.8.0、Gazebo 11.15.1、RTAB-Map 0.21.13、move_base/DWA 安装可查；本轮实际链接并运行 RTAB-Map core。GPU 是 RTX 4060 Laptop 8188 MiB，驱动 535.230.02；RAM 23 GiB，约 16 GiB 可用；根分区剩约 6.4 GiB、使用率 94%。见 [环境日志](audit/packages.log)、[GPU](audit/gpu.log)、[磁盘](audit/disk.log)。驱动报告不等于深度学习依赖兼容性。没有安装依赖、迁移 ROS2 或训练网络。

**已验证事实 / 边界**：已有 `explore_lite` 在独立 topic audit workspace 编译通过；完整导航运行不是本轮事实。Stage 原始 odom/GT frame 语义、TF 多父节点和严格时间同步仍需完整运行资格检查。Stage 的激光配置为 180°，不能把 RAS 2025 的 360° 观测假设直接继承。真实机器人相机是否 RGB-D、实机外部 GT、标定与轮式里程计质量均 **未知**。

**3. 最近邻文献排重**

完整可检索的 [矩阵](literature/nearest_neighbors.md)、[CSV](literature/nearest_neighbors.csv)、[JSON](literature/nearest_neighbors.json) 含 A1–A5 和 B1–B5 各五项，以及 OASIS-Map 补充。每项登记问题、核心算法、输入/传感器、动作、预测、反馈、假设、实验指标、对照、代码、重合、作者明确限制和未知。DA-BSP 同时是 A/B 的近邻；不为凑不同标题排除真正相似的经典工作。“最接近”是本轮针对机制的排序，不是数学上完整检索的保证。

| A 的五个主要近邻 | 关键机制与证据 | 对新增贡献的约束 |
| --- | --- | --- |
| Safe and Robust Map Updating，Sensors 2023 | 虚拟/实测 beam 比较，异常比例暂停更新，cell 计数，定位修正。出版站方法/讨论检索可读，本地直接下载 403；作者代码固定 SHA 可读 | 错误更新保护和定位恢复已经有。不能只做“发现冲突→停→重新定位”。[论文](https://www.mdpi.com/1424-8220/23/13/6066)、[代码](https://github.com/CentroEPiaggio/safe_and_robust_lidar_map_updating) |
| DA-BSP，IJRR 2018 | GMM belief、未来关联分支边缘化、期望歧义/不确定性、多步运动；作者全文、Gazebo/Pioneer | 多假设+选择消歧动作本身已经覆盖；新增对象应是 pose 与持久地图变化的竞争解释及更新决策。[全文](https://indelman.github.io/ANPL-Website/Publications/Pathak18ijrr.pdf) |
| PBD-AG，2026 预印本 | baseline/delta、可见性门控、graph 不确定性驱动 fixture 核验、安全视点、失败重试；全文3–4 | 稳定基底、主动核验、证据gate都已有。定量模拟器 pose 注册与 navigation proxy 不能视作真实漂移实验；实机为定性。[全文](https://arxiv.org/html/2608.10449v1) |
| Chamelion，RA-L 2026 | 双head 变化/visibility confidence、条件Bayes更新、真实与LiSTA数据、配准扰动消融；读预印本全文及代码，期刊身份另核 | “可靠性筛选后更新”已覆盖。原文承认配准误差和voxel mismatch影响；这不是我们发现的空白。[全文](https://arxiv.org/html/2602.08189v1)、[作者机构出版记录](https://pure.kaist.ac.kr/en/publications/chamelion-reliable-change-detection-for-long-term-lidar-mapping-i/)、[代码](https://github.com/url-kaist/chamelion) |
| Multi-session perception-aware coverage path planning…，Ocean Engineering 2026 | KDE/RRT、semantic SLAM、不同mission gain、主动重访和变化状态概率；作者20页全文，AUV实机 | “跨时段变化检测+主动补测+SLAM反馈”不是空白；仅换地面2D平台不能成立创新。[全文](https://flore.unifi.it/bitstream/2158/1464552/1/1-s2.0-S0029801826010048-main%20%281%29_compressed.pdf) |

**文献支持**：OASIS-Map 的 dense semantic correspondence 处理跨 session 部分观测、相似对象和持久 ID；Oxford 页当前标 `Code Soon`。它给 A 提供另一种强被动解释，代码缺失不能被写成“作者没有某机制”。[全文](https://arxiv.org/html/2607.14899v1)、[作者页](https://dynamic.robots.ox.ac.uk/projects/oasis-map/)。本轮未获得 PBD-AG 的完整可执行作者仓库，也未证实它从未有 joint pose/change 模块；仅能说所读方法没有给出这一明确竞争后验。不能据此宣布新颖性已通过。

| B 的五个主要近邻 | 关键机制与证据 | 对新增贡献的约束 |
| --- | --- | --- |
| Uncertainty Framework，RAS 2025 | UM/UF/SiREn、真实测量更新地图、改造RRT*；全文A.4/A.5和作者代码 | 已有反馈补测。A.5线性位置KF、已知航向、无matching errors是验证范围；不是论文没有反馈，也不是作者声称所有后端无误差。[全文](https://arxiv.org/html/2506.17775v1)、[代码](https://github.com/Seba-san/UncertaintyMap) |
| FIT-SLAM 2，RAS 2025 | Fisher/landmark、traversability/roadmap；论文方法实验片段及固定源码BT | `EvaluateFisherInformation → CancelAllNav2Goals → MarkLethalFOV → backward recovery` 已存在；健康监测、取消与改路并非新增贡献。[论文](https://doi.org/10.1016/j.robot.2025.105188)、[代码](https://github.com/suchetanrs/FIT-SLAM) |
| Active Visual SLAM for Robotic Area Coverage，IJRR 2015 | 历史link真实验证比例→saliency条件Bernoulli成功率→候选路径预期信息/终端协方差；本轮重读作者缓存4.3及结论 | 是B最强机制冲突之一。不能称旧主动SLAM全部把未来观测当必然成功。作者承认未知区saliency插值和one-step horizon边界。[作者论文](https://robots.engin.umich.edu/publications/akim-2015a.pdf) |
| Probabilistic Active Loop Closure，ICRA 2024 | 回环概率、cluster与不确定性/距离代理、成本和on-device探索；作者全文 | 概率×收益并非新机制；是否具体部署中持续校准不明确，不能填成“没有”。[全文](https://cdn.amazon.science/7b/55/cb3dafd14b5ba7210870af299c8f/probabilistic-active-loop-closure-for-autonomous-exploration.pdf) |
| DA-BSP，IJRR 2018 | 未来关联不确定和混合belief都进入动作评价 | 单纯加入匹配错误概率也不足够新；对照必须包括能表达关联歧义的模型。[全文](https://indelman.github.io/ANPL-Website/Publications/Pathak18ijrr.pdf) |

**已验证事实**：UM 代码快照 `7e5007307dc9525e3474cb6aaf1ac5ae65def811` 的 `kf_slam/slam2d.py:88` 订阅 `/gazebo/model_states` 取航向；本方案不能在线使用这个 GT 信号。FIT 快照 `8ca04125b75d873155de9e546b94abf52830ce7a` 的 active BT 包含上述取消/屏蔽/恢复流程。所核模块未见残差重估收益预测参数，不意味着整个系统或最终论文没有等价机制。FIT 最终完整正文仍未取得，所有未核全字段保留未知。

**排重结论**：A 尚有一个待验证的任务差别——正确地联合处理 pose error、地图变化和二者同时存在，并控制冻结/错误提交，而非泛化“主动变化核验”。B 的宽泛机制直接遭遇已有统计有效观测收益工作的冲突。**合理推测**：动作条件、方向相关的偏差/关联混淆，可能比单一成功概率更有意义；**未知**：它是否必要、是否已经被DA-BSP/其他可靠性规划覆盖、是否能在线估计。

**4. A 的实际最小实验**

**已验证事实**：执行了 [map_probe.py](code/map_probe.py)，配置在运行前写入 [A_frozen.json](protocol/A_frozen.json)。2个12×12m占据场景、0.1m栅格、121束180°扫描、10m量程、固定0.03m距离噪声；seeds 7/17/27。包括无变化、仅定位误差、仅真实变化、二者同时、超出假设库的误差五种条件；每种case运行四个选点基线和同输入被动控制，共150行。没有改地图/噪声/阈值重跑性能实验。

**实际在线信息**：旧图、估计起点和当前扫描。pose误差假设为 x∈{−0.6,0,0.6}m、y∈{−0.4,0,0.4}m、yaw∈{−0.04,0,0.04}rad；每个pose配“旧图不变”和“当前scan生成的局部改图proposal”，共54项。proposal不是由真值变化区域生成。Cauchy污染似然、固定有效束数及change prior形成belief。下一视点预测用自身belief的raycasting。策略只接收这些在线对象。

候选为8个平移位置×4个朝向，先按圆形半径0.35m和直线路径筛选；对所有pose假设的旧图检查安全，并用posterior支持的proposal否决。各case仍有20–32个候选，远近距离0.8m/2m。差速底盘可先转向、直移、再转到观察朝向；圆形净空只是运动几何资格，不是move_base执行验证。模拟器用隐藏pose偏差生成执行后的真实位置/扫描，离线记录路径安全；**GT没有用于选点或更新决定**。本轮全部选中路径在隐藏地图中安全，不代表对未知障碍具备完备安全保证。

| 策略 | 本轮实际实现 | 不能冒称的东西 |
| --- | --- | --- |
| nearest | 最近位置，确定性朝向tie-break | 全局最优核验 |
| uncertainty | 旧图与观测proposal分歧的预期可见端点/距离 | RAS2025 UF算法复现 |
| stable | 避开belief中的冲突端点，按法向分布最小特征值/距离选 | 已知真静态标签或位姿协方差 |
| discriminative | belief加权的预测range差异/距离 | 新的MI理论或正式方法 |
| passive | 同初始belief、不增加独立证据、不移动 | 作者最强被动维护系统 |

**更新决策**：change probability≥0.9且joint maximum≥0.15时更新；≤0.1时KEEP，否则DEFER。阈值是冻结的toy模型规则，不是论文安全保证。地图评价为修改的无变化cell数、真变化cell召回及最终binary cell错误；真值只在评价侧使用。`decision_correct`要求变化时UPDATE且错误修改不多于正确修改，无变化时KEEP；它不是标准分类accuracy，DEFER算未解决。三个seed共享几何，不是30个独立环境样本。

| 策略 | 解决case/30 | DEFER | 错误修改cell合计 | 更新后平均错误cell | 平均路程m |
| --- | ---: | ---: | ---: | ---: | ---: |
| nearest | 12 | 18 | 412 | 107.90 | 0.80 |
| uncertainty | 12 | 17 | 523 | 112.33 | 0.96 |
| stable | 3 | 12 | 1501 | 146.37 | 0.80 |
| discriminative | 0 | 12 | 1828 | 158.90 | 0.80 |
| passive | 8 | 18 | 588 | 120.10 | 0.00 |

数据：[逐case CSV](data/A_run01/results.csv)、[决策分数/后验](data/A_run01/decisions.json)、[原始地图/扫描/候选及每策略更新NPZ](data/A_run01/raw)、[所有未解决和危险更新case](data/A_run01/failures.json)。图：[汇总](figures/A_summary.png)、[both案例](figures/A_case.png)。

**已验证事实**：nearest与uncertainty在仅变化和both的12个case符合上述弱成功规则；discriminative没有。所有策略在无变化和pose-only都DEFER，说明这个简化推断器还不能可靠解除冻结。out-of-bank时，stable/discriminative在全部6个case提交错误较多的更新，nearest全部拒绝决定。观察方向改变了数据及本模型更新，但不能称为定位改善。

**合理推测**：预测分歧大不等于能区分正确解释；错误生成的map proposal、对未见区域的假设、似然失配和模型外pose会把主动观察变成确认错误地图。这些解释没有单模块因果消融，不称为已证明的失败原因。**已验证事实**：独立无噪声同位姿逆观测模型检查没有修改原图（0cell），不能简单归因于一个确定的无噪声绘图bug。

**重要边界**：toy中的冲突冻结阈值0.2，作者公开配置是异常beam比例0.8，而且分类方式不同。toy change-only的range冲突比例约0.38，未超过作者0.8。因此本轮**没有复现原作者系统在正确定位、大变化下停止的具体运行事件**；这个问题目前是文献支持，本机现实任务复验是UNRESOLVED。不会把较低阈值制造的冻结当作作者算法失败。没有持续多步运行，也不能声称证明“解除长期冻结”的能力。

另有坐标规范不可辨识的控制：同时平移整个环境及全部机器人pose，局部激光观测不变；缺少旧坐标中可信稳定锚点时，主动运动也不能解决这种规范歧义。数值检查对XY逆平移作1e−12m舍入以消除栅格边界浮点伪差，首次0.05m伪差检查失败日志保留在 [failures/checks01.log](failures/checks01.log)。这是可辨识性边界，不把一般重复结构场景冒称严格不可辨识。

**A判定**：运行完成；本轮模型机制不足；真实作者冻结问题尚未本机复现；主动新颖性未确认。四个结论分别成立，不能互相替代。

**5. B 的现有工程审查与必要轻量调用**

**已验证事实**：暂停目录已有 `frame_bridge.py`、`time_geometry.py`、`candidates.py`、执行预算/进程框架和上游RTAB ROS1源码；没有collector、完整runner、launch、RTAB运行bag/DB或技术资格结果。上游tag `0.21.13-noetic`、commit `364b7da750f3be3203863c7b913a69c4f6b0b59e`。用户已有工程成果保留；“技术资格已完成”不符合当前可查文件。

| 必需信号 | 安装系统/源码能否提供 | 现有collector/数据状态 |
| --- | --- | --- |
| 预测地图收益 | 需planner保存候选raycast/UM输出；有几何候选脚手架 | 没有真实在线预测收益日志；本轮仅partial-map geometric proxy |
| 配准统计 | `/odom_info` lost、correspondences、inlier ratio、complexity、covariance等；须订阅才发布 | 无既有RTAB运行日志；本轮core TSV提供实际统计 |
| ICP成功/拒绝 | returned Transform是否null、rejectedMsg；ROS侧lost | 本轮core可记录；不能等同图约束接受 |
| 真正图约束接受 | `/rtabmap/mapGraph`/Link需按node IDs、link type对齐snapshot，Info事件辅助 | 尚无collector和观测级归因；local ICP accepted不保证形成loop edge |
| 地图更新 | grid_map/mapData/DB与同坐标前后快照 | 本轮未测；occupied/known增加不等于地图精度改善 |
| 离线GT评价 | Stage truth严格时间、坐标审计；轨迹RPE/地图比对 | 完整RTAB链未知；本轮只有合成pair relative pose误差 |

**已验证事实**：installed `RegistrationInfo` 有 `icpRMS`，但本机ROS `OdomInfo.msg` 不导出该字段。本轮六组core结果 `icp_rms` 全为0；不得当作六组零残差或完美配准。covariance是后端估计量，也不能直接叫真实位姿不确定性或真实误差。

为避免建立第二个完整工程，仅用同一占据图生成六对901束180°、25m扫描，直接调用已安装RTAB-Map的 `Registration::create`/`computeTransformation`。配置固定 `Reg/Strategy=1`、`Reg/Force3DoF=true`、`Icp/PointToPlane=true`；其余ICP参数用installed defaults，实际是 `Icp/Strategy=1`、低复杂度strategy1、最大平移修正0.2m，逐次TSV保存。固定seed7、0.03m噪声、wheel surrogate guess误差[0.2m,0,0.02rad]。不让GT transform进入配准；GT只计算pair误差。预测新cell只从初始部分地图计算，未见区假设透明，不使用隐藏变化图。程序：[核心CPP](code/registration_probe.cpp)、[六对runner](code/run_registration_probe.py)。

| pair | 几何预测新cell | 实际core接受 | 离线平移误差m |
| --- | ---: | --- | ---: |
| corner | 24 | 是 | 0.1882 |
| structure_view | 3117 | 是 | 0.0357 |
| changed_front | 20 | 是 | 0.1842 |
| changed_side | 3120 | 是 | 0.1113 |
| symmetric_front | 7 | 否 | 不适用 |
| symmetric_side | 3034 | 否 | 不适用 |

原始XY扫描、resolved parameters、actual core输出和拒绝理由：[B_core_run01](data/B_core_run01)。[汇总图](figures/B_core_probe.png)、[失败/较大误差记录](failures/B_cases.json)。首次build因PCL include缺失失败，第二次pkg-config包名失败，第三次补入既有PCL include成功；全部日志保留，没有安装任何包。

**已验证事实**：core接受不保证本例正确配准，接收与offline error可以不一致。**边界**：两次拒绝是修正0.200418/0.203837m略越默认0.2m；guess恰在该边界，不能把这个阈值现象解释为稳定的可用观测不足。六pair只有一个seed，并非完整或公平的路径策略比较；不同case的初始噪声不完全相同、side含90°转向，不能因果归因于单独的地图收益项。没有graph、map update、累计RPE/ATE、真实active闭环。因此实际有效收益失配的可决策性和SLAM改善仍 **UNRESOLVED**。

**6. 十项比较与新机制边界**

| 问题 | A | B |
| --- | --- | --- |
| 1. 问题真实存在？ | 文献支持锚点；现代强被动系统/本机复验未知 | 文献支持理想观测边界；core示例支持accepted≠准确，持续任务损失未知 |
| 2. 有主动动作空间？ | 模拟中20–32个安全候选；实机/原更新系统可达资格未知 | 平移路线/朝向/回看可以不同；原脚手架尚无完整执行资格 |
| 3. 简单方法能解决？ | 本轮nearest优于消歧score；强被动多假设+buffer未对照，不能声称需要复杂方法 | threshold/default后端防护已存在；能否有必要的额外历史/方向信息未知 |
| 4. 可新增什么？ | 联合pose/change解释下选择证据，并以错误提交约束和拒绝决定管理更新；整个组合尚不是已证明新方法 | 区分接受、正确关联、方向可观测和地图贡献的动作条件收益模型；必要性/新颖性均未知 |
| 5. 直接改善SLAM？ | 直接目标是地图维护；是否改善后续定位必须独立测 | 需证明实际有效constraint与地图/未来RPE改善；本轮没有 |
| 6. 独立公开数据/代码？ | 作者ROS1代码、Chamelion代码/权重/数据、LiSTA、3RScan；固定数据不能执行反事实视点 | RTAB-Map/UM/FIT；公开固定轨迹只作模型评价，不能证明policy改进 |
| 7. 工程量？ | 合理推测：先接作者ROS1更新/AMCL与scan ledger，中等；安全动作+多假设标定增加工作量 | 合理推测：完整TF、odometry、planner、graph/map因果日志资格，中等偏大 |
| 8. 新颖性冲突？ | 高：DA-BSP、PBD-AG、Ocean2026；普通主动核验不新 | 很高：Kim2015、P-ALC、DA-BSP、FIT反馈门控 |
| 9. 任务归属？ | 首先 Active Mapping / lifelong map maintenance；只有联合定位且实测定位提升才谈ActiveSLAM贡献 | 可以ActiveSLAM，条件是实际SLAM后验/误差改善，不只是coverage更快 |
| 10. 正式开发？ | 暂不；先问题资格和强被动必要性 | 暂不；先信号与简单baseline必要性；作为备选 |

**合理推测**：A若值得继续，贡献应落在一个能被反例推翻的机制：避免“认为静态的结构其实也变了”时误纠正pose；允许two-cause hypothesis和unknown解释；在同一预算下决定先定位、先核验或继续冻结。不能仅把两个模块串联、加权score或经典Bayes/MI重新命名。错误提交风险应是校准后的实验保证或明确假设下的约束，不能凭后验0.9宣称安全。

**合理推测**：B若将来启动，机制必须解决“看似匹配成功但约束错误/方向无信息”与“被拒绝但观测有价值”的区别，并证明GT-free在线信号增加动作选择价值。若简单current-health、固定success model或nearest已经解决，退出B方法路线；不要用RTX4060的存在来倒推需要RL/大网络。

**7. 开源基础及下一阶段最小工程方案**

| 基础 | 公开 | 本机编译/运行 | 论文复现 | 作为基础的判断 |
| --- | --- | --- | --- | --- |
| Sensors2023作者更新代码，固定SHA `57e83ec…` | 是 | 本轮仅静态，未编译 | 否 | A首选最小锚点；ROS1/catkin、TF、scan/map/odom、PCL/OpenCV、ChangedCells/UpdateMap；要接AMCL及`/lost_localization`、`/publish_cmd_vel/stop`服务，清查header/dependency/配置与论文差异 |
| RTAB-Map0.21.13 | 是，已安装 | 实际core调用通过；完整ROS SLAM未知 | 无本轮active复现 | B基础保留；core probe不满足SLAM运行资格；A可后续作独立localizer，不必先绑定 |
| hrnr/m-explore explore_lite `712bdd4…` | 是 | 早前本机build通过，闭环未知 | 无相关论文复现保证 | 可选frontier基线；A维护任务先不需要未知区frontier系统 |
| UncertaintyMap `7e50073…` | 是 | 未编译 | 未复现 | 借数学和UF对照；已知heading/理想关联不适合直接当真实B后端 |
| FIT-SLAM `8ca0412…` | 是 | 本轮未编译；ROS2 Humble/Nav2/ORB-SLAM3/roadmap等 | 未复现 | 强近邻/算法参考；不迁移ROS2、不整套作为当前基础 |
| Chamelion `b03f6dd…` | 是，数据/权重链接 | 未编译，Docker GPU/cu128等依赖未资格审查 | 未复现 | 独立变化检测/维护对照，非主动控制框架；3D与2D不能直接等价；本轮不下载3.61GiB数据/构建重容器 |
| PBD-AG / Ocean2026 / OASIS-Map | 论文可读；完整代码未核实，OASIS Code Soon | 未尝试 | 否 | 必须排重；不依赖尚未核实代码启动主工程 |

**下一轮只推进A的资格，不开发新planner**，建议三个小工作包。下面是待实施方案，不是本轮已完成结果。

1. **原作者机制资格**：在新catkin目录编译固定作者版本，保留原参数；整理scan→异常beam→buffer→是否commit→processed_map的trace。先用无噪声同pose、不变化，确保不产生错误更新；再用一个冻结场景验证正常定位。接ROS1 AMCL或可读scan-to-map localizer。不要把toy0.2 gate直接搬过去替代0.8配置。
2. **四条件问题复验**：同一可解释场景固定四条件：无错无变、仅pose错、仅持久变化、二者同时。先用被动安全更新和被动多假设/稳健配准+buffer。变化区域来自预先登记的障碍增删，占比在看到结果前固定；不反复扩大直到冻结。若固定配置没有freeze，报告没有复现，不能倒调异常阈值。公开数据用于额外变化/错配输入验证；LiSTA/Chamelion是3D，3RScan是RGB-D，不能据此证明2D主动动作收益。
3. **有条件的主动必要性小试**：只有原机制出现正确定位却冻结、强被动baseline仍有损失时，再比较nearest、普通补测、历史稳定视点、联合假设区分视点；共享初始belief/map/odom、候选集、噪声序列、运动/观察预算。至少两条扫描条件不同的安全可执行动作，pose与change候选从真实scan提取。GT只离线评估，提交前不能靠GT筛选。先一组paired动作，再决定是否补一次重复；不恢复旧12条安排。

必须记录：定位候选及归一化权重、全体map proposals、预测扫描/似然、当前异常beam比例、cell buffer、所选动作、拒绝决定原因、实际pose输出和地图commit日志。离线只用GT计算pose偏差/未来RPE、错误更新cell、可见真实变化recall、冻结持续观测次数、后续localization成功率、路程/时间。不能以地图变化cell变多替代地图改善。

**公平性 / 判据**：主评价是变化更新延迟与错误提交的共同变化，pose-only及both不能删掉；被动基线用相同观测数，主动策略共享最大行驶/观察预算，额外转向也计时。先冻结基线参数、曝光的online变量、测试变化布局和决策阈值；不事后选择有利seed。未来至少要看到：两个可执行动作导致不同真实维护结果；主动方案在控制错误提交的同时减少freeze，而且超过nearest、稳定结构和强被动方法。只有一个toy score赢或只改善coverage均不进入正式开发。

B备选的最小工程包仅是补collector/资格：订阅严格时间的scan、wheel/ICP odom、OdomInfo、Info/mapGraph、grid_map；按scan stamp、node ID和link type关联，保存决策时快照。先一次短正常任务校验TF/GT/DB，再一对同目标、同预算路线；参数不贴着接受阈值设计。建立接受率、错误约束率和地图质量三个不同标签。这个包将来需用户重新启动备选路线，本轮没有实施或重启暂停实验。

**8. 风险、退出条件与交付完整性**

| 现象 | 应归类 | 处理/退出 |
| --- | --- | --- |
| 编译、TF、stamp、GT、路径不能执行 | 技术运行失败 | 修技术并留日志；不得说科学假设为假 |
| 作者原规则/现代强被动系统在固定场景没有冻结任务损失 | 问题真实性未证实 | UNRESOLVED，停止主动方法设计；不调场景制造结果 |
| 强被动/nearest已达到同等安全与更新速度，或选点只增数据不改善结果 | 方法必要性/机制不足 | 停止该主动选择器；保留问题来源与负结果 |
| 全文/代码已有joint pose/change/commit-aware等价机制 | 研究创新不足 | 停止同机制论文选题；有工程价值也不包装新方法 |
| 模型外误差仍高置信误提交、稳定结构也会变、绝对坐标无锚点 | 可辨识性/模型风险 | 明确拒绝/冻结范围；不能宣称普适安全恢复 |
| 只在自建图有效、固定数据不能支持反事实动作、真实GT缺失 | 外部效度不足 | 不进入SCI主结论；先补独立输入与真实在线闭环 |

已保留两个完整实验输入/输出、150行A运行数据、6组actual-core数据、三张图、全部A未解决case、B拒绝/大误差case、源码和固定SHA、HTTP403/编译失败/数值检查失败。代码可重新生成新编号输出目录；首次输出不覆盖。完整性检查见 [checks02.log](audit/checks02.log)，其中数据规模、GT变量隔离、候选安全、旧工作区保护均通过。GT静态变量隔离检查只是审计辅助，不能替代逐条数据流分析。

**最终建议仍是：A主方向、B备选，二者均不GO。** A当前值得的是一次原机制与强被动基线的问题资格审查；不是继续调本轮表现较差的区分score。若A下一轮资格失败，明确记录失败类型后再决定是否回到B，而不是用已做工程量要求保留某个方向。
