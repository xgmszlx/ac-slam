# 最小验证方案：执行反馈与路径可靠性失配

状态：`DESIGN_ONLY / CONDITIONAL_PROBLEM_PROBE`。本轮没有仿真、训练或正式算法。新工作区协议独立于已封存Doc81；不得续用它的runner、重置预算或把旧Q3计成新健康样本。未来启动前需登记本协议的最终hash和独立预算，本文件当前不构成已完成预注册。

**1. 基础系统**

RTAB-Map ROS1 0.21.13：`icp_odometry`处理2D scan，轮里程计只提供运动guess；RTAB-Map实际增量建图/graph。`Reg/Strategy=1`、`Reg/Force3DoF=true`作为配置候选；全部ICP、关键帧、闭环、图优化和退化保护参数须从安装默认/官方例子逐项登记，所有臂一致。当前不填未经运行资格的完整launch。不给GT odometry，不将`Memory/IncrementalMemory=false`的定位模式冒充SLAM。不开启视觉，避免相机类型未确认和新增渲染依赖；这只是低成本问题探针，2D迁移不是贡献。

采用Stage原Pioneer3AT和Hokuyo配置，原`localization=odom`、显式`odom_error`、地图和sensor rate不改。原GUI+近1:1 sim/wall时钟先资格；不能通过加噪/禁用保护扩大任务损失。若RTAB-Map短程资格不通过，停止并报告technical failure，不自动换多套后端寻找好结果。

**2. 探索/导航**

本轮编译通过的固定SHA explore_lite作为frontier detection；move_base的navfn+DWA作为实际导航。探针阶段增加记录/候选输出和单一goal arbiter，属于下一轮测量工程，不是正式方法开发。默认explore_lite距离cost不作为实际路径成本，需调用真实planner估计并核验路线。

目标先固定为同一个前沿，核心问题只比较去这个目标的路径承诺/切换；不同时学习frontier排序、mapping停止、速度控制、回环目标和局部旋转。候选选择与导航统一goal authority，避免两个节点抢控制。

**3. 地图/场景**

先用旧map3和map8，文件只读，记录world/png/inc、机器人/激光/控制参数SHA。两张地图由已有平台资产和几何范围选定，不由新方法效果选定。本轮不新增场景。旧map3全程有误差不保证本后端/局部路线有相同问题，map8可能全部健康，这一结果应保留。

如果两地图在决策时online map中无法形成足够不同的路径，不改地图制造优势：退出为`ACTION_SPACE_NOT_ESTABLISHED`。之后是否换公开地图另拟完整协议；最多一个新场景只能用于预先定义的测量资格，不能和失败旧场景互换后只报告新场景。

**4. 至少两条安全、可执行且观测不同的路径**

共同起点和同一前沿接近点。在**决策前**的SLAM occupancy/costmap已知free连通域内，通过不同的已知junction/via point形成两条路线：例如长平行墙走廊与有转角/横向墙段的绕行。只使用当时真实观测形成的地图，不读取Stage bitmap、GT或未来成功路线。没有两条合格路线就没有选择实验。

候选资格：机器人实际footprint的保守膨胀；未知/occupied单元不可穿越；沿每段以不大于半个cell的采样检查全footprint；转弯与DWA约束可执行；有效目标和途经点都在同一已知free连通域。底盘footprint来自模型/URDF并冻结。初始方案两条route长度比不大于1.20，避免用任意长绕路买精度；若不符合，不扩大门限。

“观测不同”在看GT结果前依据沿路线ray-cast的法向方向分布/归一化局部信息最弱方向、真实历史scan覆盖和创新区域比例判定并记录连续数值。不能事后挑选差异最大的route；候选提取规则、最多K=2和tie-break预先冻结。几何指数只叫可观测性代理。特征点数量/几何差异不作为定位改善PASS。

导航可执行性另做短程技术资格。planned path、DWA实际轨迹、离计划走廊距离和途中改路都要记录。未经完整审计不能把两个waypoint列表称为两个执行动作。如果实际路线趋同，则`ACTION_NOT_REALIZED`；以实际可控的2D移动路径作选择，不要求独立相机pitch/yaw、不重启原地旋转选向。

**5. 最基本的强基线**

| 基线 | 行为 | 必需意义 |
| --- | --- | --- |
| B0 | 标准frontier/同目标最短安全路线 | 任务效率与现有系统参照 |
| B1 | 固定几何门限/最弱几何方向风险筛选，再选最短合格route | 排除“简单几何规则就够用” |
| B2 | 真实当前健康阈值+滞回；降低后取消goal、沿已走安全段回退、选另一条B1合格route；同预算 | 排除“检测变差马上改路就够用”；必须统计回退和静止成本 |
| B3（后续） | 同输入的离线冻结小模型或条件统计，预测动作结果，不在部署时更新 | 隔离在线校准价值；首个12回合阶段不训练或声称已部署 |

P-ALC是在历史目标/闭环任务中的最近邻，LA-Planner是独立yaw的四旋翼近邻。不能把自己实现的二元路径规则冒称这些论文的完整基线。进入发表实验前需合格的同任务强近邻实现，或说明为何不可直接对照并加入相应机制消融；当前B0–B2足够拒绝无必要性思路，不足以最终支持顶刊优越性。

**6. 在线变量与反馈**

决策输入严格截至sensor-time t：online occupancy及版本/age；scan ranges与valid ratio、法向分布；候选长度/turns/遮挡预测；当前RTAB odom状态、有效ICP correspondences/inlier ratio、structural complexity/distribution、lost；covariance可记录但不可假设已校准；backend实际接受的neighbor/proximity/loop事件；处理延迟、CPU与stale-signal标志。topic存在、默认0和有效测量必须分开。

分别记录“预测可能被看到的结构”“实际有效配准”“任务误差”。后续可考虑把短时真实registration failure/accepted correspondence不足当在线延迟监督，使用同一帧集合更新动作条件的测量成功概率及预测误差范围。`lost`只是backend状态，不是真实误差标签；即便在线标签可预测，也必须离线验证其与任务损失相联。

严禁decision/predictor读GT、未来error、final optimized graph、执行后地图、oracle最佳route。回合内信号按照**接收时刻**和sensor stamp同时审计：晚到的旧数据不冒充决策时已知。候选trace输入和预测在动作前序列化/哈希。

**7. GT只允许离线评价**

Stage GT pose、world bitmap与障碍几何独立存档，collector和evaluator与在线planner分开。初始化完成后静止窗口确定评价坐标变换并冻结；控制目标以估计map坐标和在线路线生成。不用运动后全轨迹SE(2)拟合掩盖漂移，不使用最终优化graph代替当时online pose。

主端点：统一1s窗口平移RPE的route-level p95；次端点：固定评价坐标APE、任务完成率、tracking loss/有效估计缺口、到达后的相同固定30s连续任务段误差。成功回合与失位回合都报告，缺失不能填零。窗口跨数据缺口的不计算；“只算存活帧”可能幸存者偏差，因此缺口与失败单列。

地图：相同分辨率/固定对齐，评价共同覆盖区域的边界精度/完整性及距离误差，同时报告各臂完整覆盖率，避免减少覆盖换漂亮地图。占据图的unknown消失、binary-map熵减和constraint数量不能代替地图质量/位姿精度。

**8. 公平性与小预算**

初次问题筛选：2地图 × 2固定可行route × 3预先登记随机区组 = **12条完整连续科学episode**。另最多4次技术资格/故障尝试，总新尝试上限16；每次在任何仿真启动前登记，失败也扣额度，无自动重试。此为建议的新协议预算，与旧Doc81历史4次公开并列，绝不改旧账本。单episode上限180sim秒，原sensor/velocity噪声固定；资格选定限长task，而非全74m场景巡游。

同区组从相同初始参数、初始化前缀和任务入口规则独立启动；两路线随机交叉顺序。没有已资格的完整SLAM状态序列化/恢复，**不声称exact paired G_pre**。记录动作前graph/map/state差异，作策略级区组比较；不把异步Stage seed当严格物理确定性。禁止bag suffix拼接和把某次动作后的状态拿给另一路径。

首12条执行固定路线用于问题真实性和动作效应筛选；B0/B1在动作前冻结的选择可记录，但不能用这批固定route数据冒称B2/B3闭环策略已被验证。没有任何counterfactual的真值。12条若全部合格仅给探索性方向，不给显著性或概率校准保证。

统一总时间/距离预算、odom guess、后端保护、keyframe阈值、observation rates、collision limits、GT评估与记录开销；成本统计包含候选计算、额外观测、等候、回退和实际path length。局部route和共同后续段原生连续；不能额外给某臂最终backend静置/重优化时间。

**9. 值得进入方法开发的条件**

- G0 `TECHNICAL_QUALIFIED`：原生scan/odom身份可追踪；至少90%任务帧同stamp GT/TF可配对，动态插值区间≤0.15s、无外推；clock单调近1:1，关键在线诊断实际有效；完整mapper/导航运行与owned进程清理。0.15s来自既有采集契约，并非用来调科学效果。
- G1 `ACTION_SPACE_ESTABLISHED`：2条nominal collision-free可执行路线、前置观测代理差异已记录、实际route分离；两地图均有可重复不同动作。不能用GT证明候选生成器事前安全。
- G2 `REAL_TASK_HEADROOM`：较高风险route存在真实任务损失，另一route能减少它；仅geometry变差/inlier变化不够。探索性量级门限建议：route-level p95 1s平移RPE差异中位数≥0.05m，且大于2倍独立测量误差界；两地图各至少2/3区组方向一致；无安全/覆盖或20%路线成本界违例。此数值是拟预注册的任务效应门限，必须在采集前固定，若footprint/task tolerance不能支持它则在首次采集前修订并留版本，不看结果后改。
- G3 `SIMPLE_BASELINE_INSUFFICIENT`：B1/B2的独立闭环复核仍系统性错选/太迟，而不是仅B0差；需要有事前可用且低延迟的解释信号。首12条无法证明B2闭环不足，所以G2通过后下一轮最先做B0/B1/B2的同预算验证，不能直接训练/开发正式方法。
- G4 `NOVELTY_UNRESOLVED_TO_BOUNDED`：取得P06/P08等最接近全文，排除已有同输入、同动作、同反馈机制；不能靠“未找到代码/作者没写”认定新颖。

只有G0–G4均满足才设计正式反馈校准机制。样本不足只能`WEAK_GO_FOR_FURTHER_PROBE`，不能SCI证据。以连续端点和全失败记录为主，不在12条上做帧级t检验。

**10. 四类失败与退出**

| 类型 | 典型触发 | 可得结论 |
| --- | --- | --- |
| 技术运行失败 | TF/GT不同stamp、ICP字段无效、goal争用、导航不按route执行 | 测量或工程失败；不能判断科学问题不存在 |
| 问题真实性未证实 | 基线始终健康、不同观测不改变RPE/任务 | 当前平台/场景没有显示可操作损失；停该probe，不说主动SLAM无价值 |
| 方法机制不足 | 有task loss，但在线信号无预测力或校准并不比B1/B2好 | 停反馈校准机制；不改噪声找结果 |
| 研究创新不足 | 强简单规则已解决；全文近邻覆盖同机制 | 停该方法选题，保留工程工具，不换名字/传感器重包装 |

其余退出：无多个安全动作、收益只能用GT/oracle排序、失配只是TF延迟、改善只来自更长路/更多观测、忽略最坏回合、需要大模型/ROS2重构才能开始、只有内生uncertainty变化没有真实误差收益。全部保留失败日志。
