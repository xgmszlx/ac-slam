# D1_EXPLORATORY_PROTOCOL_V2

2026-10-15；本文件在任何新ROS/科学任务之前登记。承接GitHub固定提交7209fa55903bc30ddbeb0ec21e2b2dde47bb0de5，不修改V1或旧记录。研究结果仅可能为EXPLORATORY_SIGNAL_ONLY，不作统计显著/跨图泛化结论。

## V1问题与本轮修订

1. map3为74m×74m；300秒是运行上限，不是有停止事件的证据。先读取原生地图与时间记录；缺乏300秒内可信停止事件时不启动科学矩阵。
2. 原协议没有证明遗漏入口可在线发现。先固定最小free/unknown候选和几何视点检查，不能从GT标注生成目标。
3. 原图预处理涉及crop、padding、INTER_AREA、生成器加载；须逐步对应作者源码，不将Grad-CAM叠图当原图，也不为适配Stage重新训练/调阈值。
4. 仅保存近完成地图不足以恢复Karto内部状态、导航与位姿，不允许直接以该PGM作为合法共同前缀。只有真实可审计的状态恢复或相同原生前缀才可分叉；本轮不为此建新后端。
5. 将“两张确认”作为独立影子基线，B1/B2/P均保留；拒判不计完成。

## 前置数据和固定选择

- 固定作者commit010e03248ed633e755c84dc4686c6d00e6bb23c8，weights_old.h5原样下载并登记hash。CPU TensorFlow2.13.1；EfficientNet-B1＋Conv2D1280＋GAP＋dropout0.4＋dense2softmax。采用原作者weights=imagenet计算分支；只剥离最终初始化下载/加载分支，前向图AST保持，避免下载随后必被完整H5覆盖的ImageNet初始化文件，恢复freeze_until=200；参数层与无参数预处理层都须对应。按legacy HDF5的trainable/non-trainable排列逐个核对全部数组；禁止skip_mismatch。
- 作者四张已取得的4-0原始处理图全部使用，不依预测结果筛选。它们不是原FP子集。作者已处理图只做RGB加载，不再次crop；Stage原生PGM依作者crop_image→uint8→OpenCV INTER_AREA到500×500。推理按作者生成器RGB/nearest/efficientnet.preprocess_input，额外rescale关闭。
- 读取固定既有Phase1 map3的A nearest、B prior-TSP、C SLAM-aware三张final_map.pgm作输入分布审查，旧方法结果不作为新主动收益。Phase1候选只用A nearest原生PGM及原分辨率0.1m，不用重缩放后的CNN图片做导航几何。
- 对应原FP地图/GT只允许一次固定仓库树查询；取不到不重试、不以叠图代替。入口召回/假阳性无对应真值时写UNKNOWN。

## Phase 0：冻结推理资格

验证类别顺序0 NOT_EXPLORED / 1 EXPLORED、完整H5数组、原图加载与预处理。记录冷启动/逐图耗时、warm耗时、峰值RSS、输出有限性和p_EX。不以4张表现认证泛化。若源码有互不一致推理路径，分别记录而不择优；无法确认分类链则TECHNICAL_INCOMPLETE，禁止在线。

新增依赖/数据/结果总计≤1.2GiB，根剩余≥2GiB；CPU进程RSS≤4GiB。安装只在新runtime/target，禁止修改系统/旧环境；无训练、无CUDA依赖。一次依赖安装最多600wall秒，失败记录，不自动换版本重装。

## Phase 1：不使用GT的候选可发现性

A类为已知free/unknown边界连通簇；B类为边界有两侧占用结构的几何线索；C类在在线图完全无线索，不能保证发现。

固定使用4邻接free/unknown边界、8邻接簇，至少4个原生栅格。仅作开口几何提示：簇长轴两端距离占用≤0.3m记B，否则A；不能称语义门检测。

视点在已知free内，离全部nonfree至少0.5m（沿用原robot_radius），采样间距0.5m、距入口代表点0.75—3m；预测可见射线中间格全部free，终点是边界free格。先检查栅格连通性和可见簇集合是否不同。最大保留256个确定性候选，按坐标排序，不依GT/后验结果挑选。两个视点至少相距0.5m。

离线“最大自由连通分量内可达”只给GEOMETRIC_FEASIBILITY，不当作机器人当前安全资格。实际在线还须估计位姿、合法地图坐标、导航costmap和现有规划器接受；没有这些时写RUNTIME_ACTION_SAFETY_UNQUALIFIED，不把未知写成已证明不可行。

记录候选数、几何提示数、自由空间可行比例、可见集合不同的视点数。实际遗漏入口召回/假阳性没有对应原始GT时UNKNOWN。几何不足两视点写ACTION_SPACE_INSUFFICIENT；仅缺在线costmap/姿态时保留技术未知，不能作科学否定。

## Phase 2：事件与共同状态

先检索既有map3原生占用图序列和时间元数据，对取得的序列按原stamp推理。只有final地图时只报告该终点p_EX，不声称推断此前首次停止时间。

保持300sim秒上限。若原记录无法支持事件资格，允许在首次科学启动前提出已有小场景或明确压力测试，但必须预先固定、不得按GT/预测输赢筛场景。本轮不自动新增场景、重复参数搜索或追加启动。

近完成状态必须包含合法在线map/估计pose、Karto/导航状态和明确时刻；PGM、最终graph或GT位图不单独满足。不能恢复则不启动分叉，不声称因果可比。

Phase0—2任一前置未通过，预算保留0/1与0/8，输出具体TECHNICAL_INCOMPLETE或NO_QUALIFYING_EVENT证据边界。数据不足不等于科学假设失败。

## Phase 3—4：仅当前置通过才执行

最多一次正常ROS技术启动，最多60sim秒/300wall秒；Stage/Karto/Nav2D、原参数/噪声，不接RTAB。检查真实map、CNN、共享候选、costmap、两安全差异视点、scan身份、map版本、估计TF、GT离线隔离、停止接口和owned清理。严格TF/GT覆盖≥90%。失败不重试、不启动科学任务。

最多8个科学任务，4策略×2事前固定初始条件；正式任务列表、顺序、所有hash须先登记。每任务300sim秒/900wall秒。首次停止提议后B1/B2/P共用≤30sim秒、≤5m、≤2视点；失败导航、等待、扫描处理全部计成本。

- B0：θ=.8即停止。
- B1：两张真实不同地图版本连续满足，再按静态入口否决决定停止/普通探索。
- B2：B1＋最近尚未核查安全视点，同样可用2视点预算。
- P：B1＋有效观测证据状态，有限视点覆盖未核查入口；仍遮挡保持未知；预算耗尽可ABSTAIN_PARTIAL。
- 影子基线：仅两张确认，不额外运行，用同输入记录其停止时刻；不能把停止后的未执行轨迹当反事实结果。

轨迹/map/观测前缀明显不同则报告PREFIX_INCOMPARABLE；无动作差异NO_ACTION_DIFFERENCE；无停止NO_QUALIFYING_EVENT。禁止为跑满8次换图、障碍、噪声或seed。

主要指标是实际整房遗漏、GT可观测free覆盖、最大连续遗漏、正确/错误停止、拒判、距离/时间/扫描数与预算-覆盖。GT只离线；入口预测、真实可见、有效扫描、地图更新、任务完成分别记录。ATE/RPE/边界/unknown为守护指标，不因面积增长宣称精度改善。

## 决策

简单时序/静态否决/最近补扫已足够，P只增成本/拒判，成本匹配无增益，在线无法发现入口，无安全差异视点，需在线GT，或与现有NBV无可区分机制，则停止正式方法开发。正向也仅EXPLORATORY_SIGNAL_ONLY。

本协议以audit/protocol_freeze.json的SHA封存；Phase0—2实测结果另写结果文件，不根据输赢修改本文。本轮若前置不成立，不创建可执行科学任务矩阵，也不占用旧任何预算。
