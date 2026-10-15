# RTAB-Map ROS1 最终技术资格审查

2026-10-14。本轮**没有启动新的ROS/Stage运行**，没有A实验、主动路线实验或正式算法。旧两次技术失败保持原状态。一次新运行的前置门未通过，预算0/1。

**最终判断**：

| 项目 | 结果 | 判断范围 |
|---|---|---|
| TECHNICAL_QUALIFICATION | **FAIL** | 当前封装链不能取得可认证的完整扫描处理事件与严格时间覆盖。失败发生在资格运行之前，不能写成第三次运行失败。 |
| SIGNAL_PROVENANCE | **INCOMPLETE** | 旧283帧的内部事件未记录；新增真实ICP调用追踪在一组既有输入上引入数值回归，未验证无影响。 |
| MAP_METRIC_VALIDITY | **UNRESOLVED** | 坐标、unknown及边界语义可审计，但精确binary错误混合表示/覆盖/位姿/融合，不能独立代表SLAM失败。 |
| SCIENTIFIC_HYPOTHESIS | **UNRESOLVED** | 本轮没有独立科学证据。技术通过也不等于主动方法可行。 |

**建议停止当前自建RTAB-Map实验封装链的进一步实验投入，不启动成对路线科学实验。** 这个建议针对当前实现及有限工程预算；不能据此判定RTAB-Map后端算法或硬件平台本身不适合主动SLAM。A保持`STOP_ACTIVE_MAP_VERIFICATION_AS_PRIMARY`。

证据标签：**事实**＝实际源码、数据、离线重算或测试；**推测**＝尚未验证解释；**UNKNOWN/UNRESOLVED**＝缺少直接证据。分析状态ANALYZED，没有独立团队复验。

**1. 读取、版本与保护**

完整读取最新REPORT、b_attempts/b_frozen、b_run/b_collect/b_evaluate、第二次结果、审计记录和family2；复用此前feedback准备源码、AB核心测试输入及相关ac-slam研究状态。旧主仓HEAD `4746834ffa44504443fd07214105fe850d6f94e6`，两个未提交修改保留。没有覆盖旧结果、改旧台账、重调toy或清理磁盘。

Noetic安装版本0.21.13。固定ROS1源码为commit `364b7da750f3be3203863c7b913a69c4f6b0b59e`；codeload获取2.67MB，仅提取odom/slam两个包。OdometryROS/ICP/CoreWrapper与此前固定源码逐字节一致，两份odom公开header与安装目录逐字节一致；dpkg版本检查及校验未发现安装文件变更。[版本核验](audit/source_version_match.json)。不是ROS2最新版替代。

新诊断和原始包副本在catkin_ws/src；原始归档及pristine子包在sources。编译使用现有依赖，最终编译通过；初次包email/依赖拓扑配置错误及修正记录在build01–06.log。编译尝试不是ROS资格启动。Git克隆TLS失败后改用固定提交的小型codeload归档；未安装软件。

**2. 全部283帧的逐scan事件表**

[scan_events.csv](results/old_283/scan_events.csv) 含283行，保存原seq、整数stamp_ns、接收monotonic wall、odom身份、精确时间TF结果、OdomInfo/lost/实际诊断、node身份、邻接边及首见发布、地图快照与local grid信息。

前端callback进入、slot/queue接受、lock drop、实际ICP开始等内部事件，旧数据没有直接记录，**全部为UNKNOWN**。有OdomInfo输出也不被伪装成直接callback日志。`used_in_global_map`仍UNKNOWN；有local grid或同stamp地图消息不是逐节点cache使用证明。表中的first_edge_publications不是内部创建时刻。

**事实**：仍为scan283、OdomInfo217、严格配对199（70.318%）；无OdomInfo66；有odom/OdomInfo但map correction TF超记录范围18。没有修改这些结果。[重建summary](results/old_283/summary.json)。

| 阶段，按旧控制事件冻结划分 | 输入 | OdomInfo | 严格有效 | 覆盖 |
|---|---:|---:|---:|---:|
| 初始化，原stamp<2.9s | 28 | 16 | 0 | 0% |
| 静止，运动区间以外且初始化之后 | 105 | 86 | 84 | 80.0% |
| 运动，7.9≤stamp<22.9s | 150 | 115 | 115 | 76.667% |
| 全回合 | **283** | **217** | **199** | **70.318%** |

分阶段没有降低全回合90%门槛。此表说明运动期间仍有明显缺口，不能把全部失败解释为启动阶段。

**3. 丢帧与TF缺口归因**

**66帧缺OdomInfo。** 源码`OdometryROS::processData()`使用`dataMutex_.lockTry()`；失败时只有DEBUG“Dropping image/scan data”。mainLoop从读取共享slot开始持有同一mutex，期间还执行guess TF等待、估计器、发布及其他工作。callback queue_size20不能改变这个内部slot的非阻塞丢弃规则。TF等待在slot接收前的laser变换和slot处理期间的guess查询两处发生。[ROS1原源码](sources/OdometryROS.cpp)、[ICP回调](sources/icp_odometry.cpp)。

**其他缺输出路径也真实存在**：ICP callback收到cloud后可能关闭scan订阅、paused、laser TF失败或deskew失败；mainLoop可因IMU等待、非连续stamp、速率门控、guess TF失败等提前返回；OdomInfo只在有订阅者时发布。第一帧初始化没有对应点，不等于ICP拒绝。217个旧OdomInfo均nonlost；216有correspondences。不能把无消息的66帧归入任何单一内部原因。

有前序输出可比较的61个缺失帧中，**59个紧随前一输出延迟≥0.1s**；旧输出延迟90分位约112.9ms，ICP timeEstimation均值仅13.68ms。**推测**：TF等待/预处理与持锁使处理超扫描周期，是可信原因链。**未知**：每一帧是否真正进入callback、是否lock drop、callback backlog和TF等待各自占多少。旧数据缺这些事件，因此不能给唯一根因。[前序延迟表](results/old_283/missing_context.json)。

**18帧TF缺口。** 精确stamp为0.6、0.7、0.9、1.0、1.1、1.3、1.5、1.6、1.8、2.0、2.1、2.2、2.3、2.4、2.5、2.7、2.9、3.0s；map→icp_odom实际记录区间**3.1–28.4s**。原wrapper的odom_frame_id为空、没有odom_frame_id_init；源码publishLoop在odomFrameId_非空后才广播，帧名在首批图处理确定，TF header还加0.1s tolerance。这支持启动时发布晚于可用odom造成缺口的解释。不能把首张图后identity变换向过去外推，以取得更高覆盖。

**拟议修复，未运行认证**：用已有`odom_frame_id_init=icp_odom`按新SLAM初始规范提前发布初始correction；先启动后端、订阅和诊断，再启动Stage；保留odom topic及covariance输入。其初始规范必须明确、不能由GT在线初始化。没有部署或验证该配置，所以不称已修复18帧。

**4. 新增诊断、行为改变与回归失败**

只读ROS1补丁记录：CALLBACK_ENTER、LASER_TF_OK/FAIL、PREPROCESS_COMPLETE、SLOT_ATTEMPT/ACCEPTED、LOCK_DROP、PROCESS_LOOP_ENTER、GUESS_TF_BEGIN/OK/FAIL、ESTIMATOR_BEGIN/SUCCESS/FAILED、ODOMINFO_PUBLISHED和MAIN_END；后者的scope guard在dataMutex析构解锁后发出。图侧记录GRAPH_PROCESS_BEGIN/SUCCESS以及传给MapsManager的node ID集合与publish返回。消息首见边仍应与实际内部创建区分；尚未建立完整约束创建事件。[odom补丁](patches/rtabmap_odom.patch)、[slam补丁](patches/rtabmap_slam.patch)。

**行为改变的队列方案**：[scan_gate.py](code/scan_gate.py) 在wheel/laser精确时间TF就绪后投递一帧，等待MAIN_END或显式失败再投下一帧。原始packet通过AnyMsg发布，避免rospy重编号seq。这样预计减少持锁期间新输入被丢弃，但会把原本被丢弃的扫描送入估计器、增加等待/排队时间，**明确改变实际处理序列，不是“无影响日志修复”**。容量200、有明确overflow/identity错误；未做真实ROS运行，不宣称有效或实时性通过。

**并发写入方案**：SingleWriter将callback/service输出交给唯一线程，并在seal后拒绝新输入、排空后结束。解决方案需配合实际subscriber关闭；该原语通过测试，但没有安装进新运行链，因此不是已证明新bag运行安全。

为记录真正的`RegistrationIcp::computeTransformationImpl`调用，另建立动态拦截库，只调用安装库的原方法，不改ICP阈值/保护/odom/地图参数。**离线回归失败**：使用AB已有六组XY输入，在非ROS进程比较不拦截/拦截输出，五组逐字节相同，changed_side发生变化：

| 字段 | 不拦截 | 拦截 |
|---|---:|---:|
| accepted | 1 | 1 |
| x | 0.111270 | 0.120661 |
| y | 0.396638 | 0.395657 |
| yaw | 1.57260 | 1.57470 |
| correspondences | 117 | 119 |
| inliers_ratio | 0.183386 | 0.186520 |

额外两个不拦截对照均保持x=0.111270，拦截重复保持0.120661。因此不能简单称随机波动，不能以accepted相同认证诊断无影响。减小依赖、move转发、限制只导出目标符号后，差异仍在。最终六组回归为4组全等、2组有差异：changed_side仍如上，corner还出现x=0.588155→0.588613等较小差异；接受/拒绝状态均相同，回归仍FAIL。**精确原因UNRESOLVED**，可能涉及包装/ABI、额外对象/库绑定或其他副作用；没有将任何可能性冒称已证明根因。native库的配准参数未改，也不能由此判断native ICP算法失败。[首轮差异](results/core_trace_tests/initial_validation_failure.json)、[重复对照](results/core_trace_tests/nondeterminism_control.json)、[最终六组回归](results/final_core_regression/result.json)。

六组core调用只是既有数据的诊断单元控制，不是新科学实验，不是完整SLAM，不改变旧六组结果。初始失败脚本的全等断言未通过，原日志保留；没有用宽松数值容差把它变成PASS。

**5. 测试与是否启动一次资格运行**

| 检查 | 状态 |
|---|---|
| 固定ROS1源码/安装header核验 | PASS |
| 283帧重建与旧199配对复核 | PASS |
| 队列单inflight、乱序ACK、duplicate、overflow显式处理 | PASS，ROS-free |
| TF原stamp插值、无外推、GT anchor逆变换 | PASS，单元范围 |
| AnyMsg完整LaserScan序列化字节/seq保留 | PASS，使用本机rospy序列化实现 |
| 8个并发producer＋service单写线程，seal后拒绝写入 | PASS，单元范围 |
| 并发JSONL记录完整 | PASS |
| 真实ICP调用追踪的数值等价回归 | **FAIL；初轮changed_side，最终changed_side/corner** |
| 新ROS资格运行/逐TF发布者实测/清理运行验证 | **NOT_RUN** |

10项测试日志见 [unit_tests01.log](audit/unit_tests01.log)，代码见 [test_events.py](tests/test_events.py)。通过其中部分检查不能替代整链资格。C++编译通过也不等于诊断等价或ROS可运行。

你规定“如果没有可信的修复方案，不要启动新的ROS实验”。由于核心追踪回归失败、完整事件认证仍不可信，**本轮未使用一次新预算**。[独立台账](protocol/budget.json)最大1、attempts空、used0；旧两次仍TECHNICAL_FAIL，没有第三次启动，也没有为了PASS调整90%阈值。

**6. 位姿图、地图、GT评价语义**

旧图25节点与scan/OdomInfo/Info按整数scan ns及Node.stamp对应，29边可追溯到端点node。24个type0 neighbor主要由里程约束形成；5个type2局部空间匹配是另外一类约束。不能叫29次独立ICP成功，也不能叫accepted就正确。节点公开时间不等于内部创建/优化完成时间；边首见发布不等于真实创建时刻。

mapData含local grid和graph；mapGraph可被latching抑制，grid_map也只在地图有更新/订阅需求时发布。原15次直接地图快照均有对应stamp的Info/graph；25节点不要求25张新图。MapsManager用过滤后的pose/node集合，非每个raw scan直接更新地图。旧日志没有精确cache成员事件，不能把全部输入scan称mapper-used。

fresh SLAM gauge初始identity；原world起点[-3,-2,0]只在离线转成map GT，平移[3,2,0]，地图反向平移[-3,-2,0]。未拟合最终图/任务后GT。Stage GT标头写odom，但源码GetGlobalPose是world；这一点用源码而非标头猜测。原map TF重复相同值不等于冲突，多父0、冲突重复0；逐TF caller未写入bag，因此发布者完整认证仍有缺口。采集receipts只保存按topic的caller，不能伪造到每条边。

**604精确binary错误保持。** 它由已知且原射线visible区域的539 false occupied＋65 false free组成；unknown visible671另列。539的距离至GT occupied中位0.05m、90分位0.05m、最大0.1118m，65的GT内部深度中位0.05m、最大0.10m。辅助539中超过0.05/0.10/0.15m的分别45/1/0，不替代原539或604。[空间诊断](audit/old_map_geometry.json)。

原GT重投影scan端点在GT binary free区域落入652个cell；其中**402个与地图539 false occupied重合**。支持位图/Stage表面/端点栅格表示差异参与了误差；不能证明402全部无害，也不能把剩余137都判作SLAM错误。旧15张地图按原forward栅格映射均未发现多个输出cell映射到同一truth cell（duplicate=0），但floor采样相位仍影响边界。[表示审查](audit/map_review.json)。

评价还混合了厚实心位图vs激光表面、float32 origin/resolution、visible延伸端点后5cm、所有采集扫描visible而非mapper-used，以及未覆盖区域。**所以MAP_METRIC_VALIDITY=UNRESOLVED作为独立地图质量主指标。** 可复算的计数和坐标审计有价值；不能直接用正常任务中的604宣称SLAM失败或主动改进空间。

GT只在offline_events/map_review中用于归因；新未运行的gate不订阅GT。本轮没有在线GT使用，没有新的物理过程，不能冒称新运行已通过GT隔离/TF发布者资格。

**7. 修复成本、退出及交付**

已明确的工程缺口：共享slot非阻塞drop不可见、初始化map TF发布晚、旧collector逐TF caller缺失、完整原语虽通过单元但尚无端到端运行认证。新增的核心拦截回归说明当前诊断路线也不能投入科学实验。**66帧逐一内部根因和拦截数值差异根因仍UNKNOWN/UNRESOLVED**。

若继续，单纯提前发布/单写队列成本小；可靠端到端扫描终结事件、native core只读打点且保持数值行为、map cache/边创建身份以及map指标表示隔离的成本中等，当前不能承诺“一次启动就能修好”。更不应扩大科学矩阵来摊薄这些不确定性。**本轮停止当前封装链进一步实验投入，不提出/启动候选路线对协议；先前技术资格失败不变。** 这个工程出口不推翻主动SLAM问题本身，也不产生任何论文新颖性结论。

交付：283行原scan事件表、TF/延迟分解、固定源码与补丁、编译失败/成功日志、10项单元测试、核心追踪失败及重复对照、地图指标审查、未使用的新预算和旧数据保护检查。原bag只读；本轮没有新运行bag，不能假称已取得新增原始ROS数据。

根分区开始6.4GB、编译后约6.3GB；新目录约23MB，未安装或删除。没有新ROS进程、master或TF发布者；编译及离线测试进程已结束。旧五个独立目录及主仓/两个研究checkout的保护结果见 [protection_after](audit/protection_after.json)。文件manifest与最终检查见audit。
