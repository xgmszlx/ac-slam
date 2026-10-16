# 被动 RGB-D 视觉 SLAM：问题资格验证

2026-10-15。**最终建议：GO_TO_MINIMAL_DIAGNOSTIC_COMPARISON，仅进入简单对照，不进入SCI方法开发。** 两条完整序列的无窗口原生估计器运行及离线评价已完成。walking定位误差明显高于sitting，但动态错误关联、几何退化及“简单方法不够”均未获证实。本文不认领新方法，也不恢复任何已停止的Active SLAM路线。

| 决策项 | 结论 | 资格范围 |
|---|---|---|
| BASELINE_REPRODUCIBILITY | **PASS** | 官方估计器＋关闭viewer的示例，walking/sitting均退出0；默认viewer失败不能抹去。 |
| TRAJECTORY_EVALUATION | **QUALIFIED** | 已导出相机轨迹的时间配对、SE(3) ATE、RPE与完整输入覆盖；不认证后台优化队列排空。 |
| DYNAMIC_FAILURE_EVIDENCE | **PARTIAL** | 动态数据中大误差与低动态参照差异已见；动态因果未隔离，失跟NOT_OBSERVED。 |
| SIMPLE_METHOD_SUFFICIENCY | **UNRESOLVED** | 本轮未做色序控制或掩膜干预。 |
| NOVELTY_SPACE | **UNRESOLVED** | 尚无具体剩余机制；通用动态加权/特征质量已有直接近邻。 |

已验证事实＝本机代码、命令、输入或输出；文献支持＝已阅读原文/作者代码；推测＝待对照的解释；UNKNOWN/UNRESOLVED＝缺直接证据。

## 1. 唯一系统、版本与构建范围

[官方 ORB-SLAM3](https://github.com/UZ-SLAMLab/ORB_SLAM3) 固定 `4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4`；原始 codeload 归档及 SHA256 保留。Pangolin v0.6 固定 `1c620ff72a93854d1ab3cb42c6b7360073926673`，仅编译到本目录 `local/`，关闭示例/测试/视频/Python模块，没有系统安装。

本机 Ubuntu20.04.6、g++9.4、CMake3.16.3、OpenCV4.2.0、Eigen3.3.7、i7-12850HX、约23.2GiB RAM。无窗口 SLAM 使用 CPU；没有部署神经网络。构建复用了已安装的可选 RealSense SDK 链接库，没有连接设备或启动 ROS。详见 [环境](audit/environment.json)、[动态链接](audit/native_ldd.txt)。

必要构建修改只有根 CMake 的 OpenCV 查找版本 4.4→4.2。[补丁](patches/build_opencv42.patch) 不改变相机标定、提取阈值、配准或优化。对213个原始估计器/第三方核心/示例/标定源文件的比对无差异：[完整性](audit/estimator_source_integrity.json)。DBoW2、g2o与RGB-D目标编译通过；未执行全部传感器示例或修改优化公式。

运行入口分开保存：`rgbd_tum` 为未修改官方示例；`rgbd_tum_trace` 为公开 getter 诊断入口；`rgbd_tum_headless` 只把官方 `System(...RGBD,true)` 的 viewer 参数改为 false。[无窗口补丁](patches/headless_example.patch)。不能把这三次输出当作某个算法改进的正反实验。

## 2. 真实技术失败与修复边界

| walking 运行 | 输入/导出相机位姿 | 退出 | 用途与边界 |
|---|---:|---|---|
| native01：官方示例 | 827/827 | **-11，SIGSEGV** | 原生失败保留；导出数据只作失败附件。 |
| observer01：公开 getter＋GDB | 827/827，逐帧状态827条 | **GDB返回255，Viewer::Run中SIGSEGV** | 诊断重放；不是成功运行或方法效果实验。 |
| headless01：只关闭viewer | 827/827 | **0** | 首条正常完成的基准；后续主指标以它为准。 |

原作者固定源码 `Shutdown()` 的 viewer结束与后台完成等待块被注释。诊断重放在所有轨迹写出后，调试器直接捕获 `ORB_SLAM3::Viewer::Run()` 崩溃。首轮没有堆栈，故“首轮也是完全相同堆栈”仍是推测；相同退出阶段与源码支持同一解释。关闭viewer后正常退出，未再重构生命周期或后台线程代码。

原始[崩溃日志](results/walking_xyz/native01/stdout.log)、[GDB记录](results/walking_xyz/observer01/stdout.log)、[正常运行记录](results/walking_xyz/headless01/run.json)均保留。关闭viewer会改变并发负载，不能声称数值行为严格不变。仍未认证后台优化队列在导出前完全排空；本文评价的是官方导出的轨迹文件，不声称是同步冻结后的全局最优图快照。

本机最低运行资格限定为**官方估计器＋无窗口示例入口**；原始默认viewer运行仍然失败。内部初始运行计划3次保留不改，发现退出错误后另有[技术修订](protocol/technical_amendment01.json)，增加一次无窗口兼容运行并替换第二序列入口，最多4次完整序列调用；没有参数搜索或追加科学矩阵。

## 3. 数据、标定与时间资格

数据来自[TUM官方](https://cvg.cit.tum.de/data/datasets/rgbd-dataset/download)。[文件格式/标定说明](https://cvg.cit.tum.de/data/datasets/rgbd-dataset/file_formats)与原始 `Examples/RGB-D/TUM3.yaml` 一致：fx535.4、fy539.2、cx320.1、cy247.6，Freiburg3已去畸变、零畸变参数，PNG深度除5000得到米，fr3不再额外做深度尺度修正。标定文件哈希随每次运行保存，未改以改善结果。

walking：859条RGB、833条depth，以TUM式最小时间差优先的一对一关联、最大差严格小于20ms，得到827组完整输入；RGB/depth最大差6.168ms、中位约0.021ms。未关联32条RGB是输入配对损失，不能叫SLAM丢帧。827组输入图像均通过完整读取，640×480，深度16bit。归档SHA256为 `1459e9488ac0e61a2ec80dfbc35cfb77942f6d8eabded1c8d26a70be650d0e1d`。[原始审查](audit/dataset_walking_xyz.json)。

关联输入时间1341846313.592026～1341846342.416195；GT共2884条，时间1341846313.6378～1341846342.4702。首个关联输入在GT支持范围之外，因而只有826个可严格配对GT的输入。SLAM命令只接收词典、标定、序列和RGB/depth关联文件；不接收GT。准备脚本读取GT只用于离线可用区间审查，不据GT删选SLAM输入。

sitting：1261条RGB、1231条depth，1219组关联输入，最大差6.917ms；同一标定，全部输入可读取。GT4251条，时间1341845820.8614～1341845863.3610，严格GT可评价输入1216组。平均无效深度37.31%。归档SHA256 `05c071672cda22a668860a935124737a4eb4fa772cbad372e73d5a99ce4be205`。[数据审查](audit/dataset_sitting_xyz.json)。

**输入约定混杂因素已验证**：原示例使用OpenCV `imread`，本机读入与PIL RGB反序完全相等，即BGR；`Camera.RGB=1`使跟踪器按RGB转灰度。首帧两种解释平均差4.374灰度级。[色序审查](audit/color_order.json)。本轮遵守官方原参数，未做色序对照；它对轨迹的实际影响UNKNOWN，不能忽略也不能假定它解释全部动态误差。

## 4. 实际轨迹结果与低动态参照

| 运行 | ATE RMSE，m | 1s RPE平移RMSE，m | 1s RPE旋转RMSE，度 | 导出关键帧 |
|---|---:|---:|---:|---:|
| native01，退出失败的附件 | 0.690379 | 0.404102 | 7.866682 | 501 |
| observer01，退出失败的诊断附件 | 0.812509 | 0.440176 | 8.633252 | 505 |
| **headless01，正常主运行** | **0.915863** | **0.446205** | **8.656633** | **540** |
| **sitting/headless01，正常低动态参照** | **0.009668** | **0.012171** | **0.499673** | **50** |

前三行属于walking，全部保留，没有选择0.690作为主结果，也没有把观察器差异解释为某种方法收益。不同并发配置/GDB/诊断与原生多线程变异的贡献未分离，数值等价性**未验证**。sitting是第四次、最后一次完整序列调用，退出0，没有再次修复或扩大预算。

主运行完整827位姿，覆盖关联输入100%、原始RGB96.275%；826位姿配到GT，占全部输入99.879%、GT可评价输入100%。时间加权输入覆盖100%，无重复/非递增导出时间戳，无导出缺失区间。RPE使用768对1秒±20ms端点，匹配GT最大20ms；未因>100ms轨迹缺口排除任何一对。关键帧数不参与输入帧成功率分母。

ATE对相机位置只做一个SE(3)对齐，尺度固定1；RPE使用相机到世界变换的相对运动，不拟合尺度。ATE中位0.646836m、90分位1.378692m、最大2.102728m；1s平移RPE中位0.246032m、90分位0.757749m。完整[指标/误差CSV](results/walking_xyz/headless01/evaluation/)与[评价代码](code/evaluate.py)保留。3项测试覆盖已知刚体变换、尺度错误、唯一时间关联、解析1m RPE与缺失帧分母，见[测试](audit/evaluation_tests_final.log)。

sitting导出1219/1219相机位姿，关联输入/时间覆盖100%、原始RGB覆盖96.669%；1216位姿配到GT，占全部输入99.754%、GT可评价输入100%。无缺失输出/重复时间戳；1140对1秒RPE，无间隙筛除。ATE中位0.007514m、90分位0.013233m、最大0.065504m。[完整指标](results/sitting_xyz/headless01/evaluation/metrics.json)。既有evo1.31.1仅只读复用核心模块并禁写pycache，独立时间匹配与无尺度对齐复算：walking差0、sitting差5.2e-18m，见两条序列的 `evaluation/evo_crosscheck.json`。

![walking正常运行的轨迹、误差及导出覆盖](results/walking_xyz/headless01/evaluation/trajectory_errors.png)

![sitting正常运行的轨迹、误差及导出覆盖](results/sitting_xyz/headless01/evaluation/trajectory_errors.png)

墙时40.28s，包含词典载入、原生按输入时间间隔等待与退出；跟踪调用均值16.966ms、中位17.0145ms，峰值RSS826892KiB。不能把墙时或调用均值单独当成整系统实时吞吐承诺。

sitting墙时61.87s，跟踪调用均值12.542ms、中位12.4867ms，峰值RSS558668KiB。两条数据运动不同：已评价1秒窗口的GT平移中位walking0.227m、sitting0.143m，不能把跨序列差异当作动态因素的受控效应。对walking全部768个RPE窗口的核查中，最大错误窗口1341846336.241891～1341846337.250087：GT平移0.172m、旋转4.782度，估计平移1.340m、旋转29.929度。这确认了实际运动估计偏差，而非仅一个ATE对齐偏移；仍不能单独证明错误关联来源。

![全部已评价窗口的实际与估计运动，GT仅离线](results/walking_xyz/headless01/evaluation/motion_comparison.png)

## 5. 跟踪状态及可解释诊断

公开 `GetTrackingState/GetTrackedMapPoints/GetTrackedKeyPointsUn` 在锁下返回快照，无估计器写入；诊断仅在 `TrackRGBD` 返回后读取，在关闭估计器后写CSV。[语义审查](audit/NATIVE_SEMANTICS.md)、[示例补丁](patches/example_observer.patch)。三个运行的SLAM动态库SHA256均为 `a20db0416fc54ca5949e6b6ac834c12f59dc0bae5f08dc2945e46943a3532c46`。

诊断读调用均值6.38µs、最大76.01µs，但加GDB重放数值与原生不等价，不能宣称完全无时序影响。状态时间线仅归属于 **observer01这一回放**，不能冒充headless01的逐帧直接日志。

该回放827帧全部状态2/OK，无RECENTLY_LOST或LOST。首帧在公开getter读取前已经初始化成功；不能说系统不存在初始化过程。没有取得失跟→重定位/重建事件。官方代码仍有Huber核、多轮卡方剔除、局部地图内点判断和重定位机制，不能把基准描述成“无任何鲁棒保护”。

![失败退出诊断重放的输入时间状态与误差](results/walking_xyz/observer01/diagnosis/tracking_timeline.png)

提取特征1000～1014、中位1007；非空地图点关联46～715、中位183。非空指针**不是经过独立验证的静态特征或内点**。关联点8×6图像网格占用中位77.08%、最小39.58%；二维坐标协方差特征值比中位0.623、最小0.244。没有观察到可由这些量直接支持的全面空间坍缩；它们也不能代替三维可观测性/Hessian或位姿协方差。

![预先规则选取的诊断帧，绿色仅表示非空关联](results/walking_xyz/observer01/diagnosis/diagnostic_examples.jpg)

样例由首帧/中间/末帧/最大离线ATE/最少关联点规则选取，非事后只挑失败截图。frame648，22.686s为该回放最大ATE附近；frame662，23.154s有46个非空关联。图像显示部分关联位于人的纹理上，但没有逐对应真实运动/重投影残差标签，**不能从截图判定这些关联错误**。主运行与此回放不混用帧级统计。

## 6. 对动态失效问题的逐项判断

| 问题 | 当前证据与边界 |
|---|---|
| 动态场景是否增加ATE/RPE | walking0.916m ATE/0.446m RPE，sitting0.00967m/0.01217m，差异明显；不是同轨迹静态反事实，动态因果仍PARTIAL。 |
| 遮挡期间失跟 | **NOT_OBSERVED**，诊断回放全部OK。不能沿失跟恢复叙事写论文。 |
| 静态特征不足 | **UNKNOWN**：有大量提取特征及较少非空关联，但未标注静态/动态与真实内点。 |
| 剩余点空间集中 | 有时图像分布较差；没有由本轮统计支持的统一严重集中机制，三维几何仍UNKNOWN。 |
| 特征多但几何弱 | “特征多且误差大”已见；“原因是几何弱”**未证实**。 |
| 动态错误关联 | 有关联落在人的图像区域的线索；逐关联错误、优化实际接纳和错误传播链未证实。 |
| 相机运动/初始化/数据质量解释 | 仍需考虑：walking/sitting运动不同、平均40.23%无效深度、色序约定、初始画面有人、执行变异。不能把全部归因动态。 |
| 原系统鲁棒能力 | 鲁棒匹配/优化/重定位已存在；本轮没有禁用它们。持续OK不能证明定位正确。 |
| 简单动态掩膜是否足够 | **UNRESOLVED**，本轮没有掩膜干预。 |
| 仍缺什么 | 同后端格式控制与可靠简单掩膜对照；必要时再取得关联标签/残差，不能直接提出概率加权或几何质量新算法。 |

## 7. 最近邻与方法必要性

五篇[最近邻矩阵](literature/NEAREST_NEIGHBORS.md)保存原文/代码证据边界。DynaPix、DynoSAM、DROID-W取得作者全文与少量源码；QualiSLAM仅认证摘要，DGO-VINS全文与官方实现未认证，不能以未提及推断没有机制。

[DynaPix](https://arxiv.org/html/2309.09879v2)已经结合背景差分/光流、地图点选择和加权BA；本轮核查的TUM代码使用GT与前后帧，原文有估计位姿消融，不能作为未经说明的在线基线。[DynoSAM](https://arxiv.org/html/2501.11893v3)联合估计物体/相机，当前代码演进与论文版本需区分。[DROID-W](https://arxiv.org/html/2603.19076v1)已经处理多视图特征不一致与不确定性优化，参考硬件RTX3090，本机8GB可用性未验证，没有安装。

普通动态概率、时序识别、特征数/质量自适应、鲁棒核、图像空间几何评价均不构成这里可认领的创新。没有提出新方法贡献；没有证明此数据上的剩余损失超出了已有简单方法。

## 8. 下一轮唯一任务

仅建议**同后端的“色序控制＋简单人像排除”诊断对照**，见[有限协议](NEXT_MINIMAL_COMPARISON.md)。优先复用已具备的原生系统和现有827组输入，P0官方约定、P1只修正输入通道约定、P2加既有简单人像排除。考虑本轮变异，建议各2次完整运行；本轮未执行，也不自动授权。

若P1即可消除问题，停止动态方法叙事；若合理简单掩膜已足够，停止新增机制；若掩膜漏检多，不能把失败当新算法必要性。只有真实、可归因且未被简单对照解决的残差才值得继续排重。下一阶段也不建设新SLAM后端、不恢复RTAB链或Active SLAM旧实验。

## 9. 资源、保护与交付状态

开始可用5636288512B，已在下载前登记压缩、解压、构建、结果及1GB保留预算。官方源归档599777562B；仅选择性解压，未展开约1.2GB无关TUM惯性时间表。walking归档527550055B、展开文件572286621B。sitting归档775406859B、tar展开预算842199040B，独立[空间预算](protocol/disk_sitting_before.json)通过；完整性检查通过后才启动。没有继续下载其他序列/大型模型。

全部新结果写在本独立目录。旧Active SLAM与D1/D2维持用户给定结论，没有写入旧仓库、修改冻结结果或删除未提交文件。[保护复核](audit/protection_after.json)确认原HEAD/status、两处未提交文件hash及既有研究正式报告hash相等；这不是对全部旧bag的新一轮逐字节manifest承诺。evo只读引用不写旧目录。没有自动GitHub发布。

[最终台账](protocol/attempts_final.json)共4次完整调用，包含2次viewer退出失败与2次正常无窗口运行；没有掩膜/新方法科学实验。收尾可用约1.84GiB，仍高于预留1GB，没有删除旧资料。[资源检查](audit/final_resources.json)中本项目SLAM/GDB/下载进程均已结束。没有新ROS/Stage/Gazebo进程、训练或软件包安装。

**最终科研边界**：已找到值得低成本反证的定位误差现象，但**没有证明它尚未被简单方法充分解决，也没有找到合格的新方法贡献**。推荐一次格式控制与简单人像排除对照，目的是尽快证伪方法必要性；不开发正式算法、不恢复冻结路线、不把技术通过写成SCI立项通过。
