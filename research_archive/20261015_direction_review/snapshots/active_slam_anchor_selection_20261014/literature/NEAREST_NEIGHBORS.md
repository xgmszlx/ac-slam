# C1/C2 定向最近邻矩阵

2026-10-14。事实＝本轮源码/环境核查；文献支持＝直接全文、作者稿或明确标注的官方摘要；推测＝拟议机制/场景；UNKNOWN＝尚无直接证据。旧缓存只读复用，并非本轮重新下载最终出版社版本。引用章节/公式，不使用未经检查的 PDF 页码。

## C1：失跟后的恢复

| 工作、证据层级 | 信息与控制；真实 SLAM 边界 | 已证实局限、实验/基线、重合 | 代码与尚未确认 |
|---|---|---|---|
| [One Step Back, Two Steps Forward, Advanced Robotics 2024](https://doi.org/10.1080/01691864.2024.2319144)，38(5):307–322。[作者源码](https://github.com/ans-qureshi/SLAM-Recovery/tree/64a0e9ec968e98747a8c2cd53966c2fce4c8c449)。**官方摘要＋固定源码；全文 UNKNOWN** | 实现把 Tracking.jpg 和 TrackLost.png 灰度图放入两个通道，ResNet34 分类。输出前进/后退/左转/右转/左右侧移六类；MINOS 与原 ORB-SLAM 在线交互。恢复分类器不直接输入精确位姿；外层导航却使用仿真 shortest_path_to_goal 的方向/距离与 collision。 | 出版社摘要：50 次导航完成13次，基线约1次；失败任务行进距离约两倍。能说明尚有失败，不能归因为动态遮挡/缺代价模型。源码提供无恢复、随机恢复；两种恢复脚本的尝试上限分别6和10，不能自行宣称公平完整复现。**后退、学习恢复、利用成功/失败图像对均直接覆盖**。 | 本轮核读关键调用路径；旧 MINOS/Kinetic/ORB-SLAM、外部权重、Matterport/SUNCG。读取成功图像是否严格为最后关键帧、图像文件生成时序、训练标签、论文等待/固定后退基线、安全与可恢复性建模、原文失败分类均 UNKNOWN。源码局部没有这些输入，不等于整篇论文没有。 |
| [Help Me Through, T-RO 2025](https://doi.org/10.1109/TRO.2025.3582817)，41:4236–4252。[官方机构摘要](https://pure.kaist.ac.kr/en/publications/help-me-through-imitation-learning-based-active-view-planning-to-/)。**仅摘要** | 人监督模仿学习解决视觉低纹理转场中 RL 难以越过转场、难以获得训练经验的问题；另有在线无监督微调。不能把其名称直接解释成故障后恢复控制器。 | 摘要给出约50h监督，或20h监督＋45h无监督。防失跟与执行反馈学习已覆盖；本文没有取得足以核定动态等待/回退竞争、最近关键帧利用、可恢复性预测或动作代价的正文。最强基线 UNKNOWN。 | 作者声明发布实现和多模态数据，本轮未定位可认证的2025仓库/数据。早期 Deep-Introspective-SLAM 仓库不能替代。输入/动作、精确位姿依赖、运动安全、遮挡时长、训练/数据体量、复现命令 UNKNOWN。获取失败不是“作者没有实现”。 |
| [Mutual Information-Based Hierarchical NBV…Under Dynamic Environments, Scientific Reports 2026](https://doi.org/10.1038/s41598-026-36259-x)。**出版社全文旧缓存** | RGB-D ORB-SLAM2；YOLOv8s/BoT-SORT及几何一致性；占用地图全局MI、局部FPM、恒速KF动态遮挡预测；DWA执行位置/朝向，10Hz反馈。跟踪可用时避开不良未来视图。 | Experimental results：nearest-frontier/TARE/RNE/global-only；局部模块消融比较真实后端 tracking loss。Conclusion 明确大部分FOV突遭遮挡仍可能失跟，恢复列为未来工作。**动态预测＋可靠性视点调整已覆盖**；其局限不能视为整个领域空白。 | 没有核实完整作者源码；不是“无代码”结论。是否完整处理失跟后安全控制、等待与退回策略 UNKNOWN。 |
| [ActLoc, CoRL 2025](https://arxiv.org/html/2508.20981v1)，[作者代码](https://github.com/cvg/ActLoc)。**全文＋固定源码旧缓存** | 已知SfM地图输入，预测位置/yaw/pitch的LocMap；沿waypoint序列选择朝向，考虑转动连续性/代价。已知地图视觉定位，不是未知图增量SLAM恢复。 | §4：HM3D/ScanNet，FIF/LWL/前向基线；§6：SIFT跨特征域未优于LWL、动态环境为未来。**定位成功率预测＋代价视点选择已有覆盖**。 | SHA 8614dc4a9c470736871d24cf92dde8f8e7f45cf9；推理公开，完整训练/测试资产未核齐；参考4090 24GB、Ubuntu22.04/CUDA12.4。8GB未资格认证。失跟后未知位置上的LocMap查询、安全与旧图恢复不是可直接套用接口。 |
| [Perception-Aware Planning…Feature-Limited Environments, IROS 2025](https://arxiv.org/html/2503.15273v1)，[LA-Planner](https://github.com/Robotics-STAR-Lab/LA-Planner)。**全文＋固定源码旧缓存** | 视点转移图维持特征共视；localizable yaw corridor＋MINCO轨迹；四旋翼位置/yaw。实机RGB-D ORB-SLAM3，OptiTrack离线评价。 | V/VI：Zhang/APACE-R/APACE-E；仿真可见特征阈值不等于真实前端失跟；实机有估计误差。公开map3特征不足失败。**沿历史共视结构选路线已有覆盖**；无法据此证明通用失跟恢复未覆盖。 | SHA fe85a7840c4304326f66d035a024dd3bb0b69739；Noetic20.04较接近，但需要nlopt等、四旋翼独立yaw动作和RGB-D系统。普通差速底盘移植须重做动作可行性；不是低成本原文复现。 |

### 对2024恢复器的逐项回答

| 核查项 | 能确认的边界 |
|---|---|
| 在线输入 | 公共Inference代码的成功图像＋失跟图像；abc.txt状态字符串。没有直接地图点/关键帧ID/协方差输入。 |
| 实际动作 | 六类模拟动作；不是只预测后退距离。左右侧移不可由差速车直接执行。 |
| 精确位姿 | 分类器无需位姿；外层导航使用仿真最短路方向/距离，因此不能称完整任务无需仿真先验。 |
| 运动安全 | 正常导航分支发现collision后随机改变动作；失跟分类动作没有单独前置碰撞检查。仿真collision是反馈，不能认证实机失跟后安全。整篇安全论证 UNKNOWN。 |
| 遮挡持续时间 | 被审Inference没有时长/运动历史输入；论文机制 UNKNOWN。 |
| 最近成功关键帧 | 使用Tracking.jpg成立；谁何时写文件、是否最后关键帧 UNKNOWN。使用成功图像并非新增贡献。 |
| 实际代价 | 六类argmax，不输出距离/动作时长/成本；论文成本建模 UNKNOWN。 |
| 等待/固定回退基线 | README/脚本有随机与无恢复；原文是否比较等待/固定回退 UNKNOWN。 |
| 置信度/可恢复性 | Softmax对象定义但Inference实际输出argmax类别；并非校准的恢复概率。全文其他预测机制 UNKNOWN。 |
| 失败条件 | 公开脚本6次分类后要求人工恢复；37/50未完成只是摘要总数，不能指定原因。 |
| 行动前信息 | 已有图像对可获得；未来动作图像不能从固定离线轨迹反事实取得。 |

## C2：实际有效观测收益

| 工作、来源与全文资格 | 原目标、收益预测与反馈 | 真实估计/动作/基线 | 明确限制与创新冲突 |
|---|---|---|---|
| [Optimizing Exploration with a New Uncertainty Framework for Active SLAM Systems, RAS2025](https://doi.org/10.1016/j.robot.2025.105059)，193:105059。[作者稿](https://arxiv.org/html/2506.17775v1)，[原代码](https://github.com/Seba-san/UncertaintyMap/tree/7e5007307dc9525e3474cb6aaf1ac5ae65def811)。**作者稿全文＋源码** | 目标是UM/UF/SiREn表达和补测决策。测量dispersion probability经log-odds机制更新地图；UF选局部不确定性突变处；RRT*传播位置/landmark协方差预测路径收益；实际估计地图用于下次决策。源码还打印predicted/current divergence。 | 2D激光差速机器人，CF/UF＋RRT/修改RRT*四组合。A.5：线性位置KF，已知朝向，无matching errors。已运行作者的特定SLAM模型，不能当一般真实前端鲁棒性验证。 | 反馈与主动补测已存在。**无匹配错误是明确实验假设，不是证明其方法在普通SLAM中失败**。代码GT朝向＋初始位置依赖；移除会改变论文条件。没有匹配失败概率模块的局部证据，不能据全文缺字词宣布整个框架不支持扩展。 |
| [FIT-SLAM2, RAS2025](https://doi.org/10.1016/j.robot.2025.105188)，194:105188，[作者代码](https://github.com/suchetanrs/FIT-SLAM)。**最终正文节选＋源码，连续全文未取得** | adaptive roadmap/frontier/通行性；FI监测感知条件。BT明确：EvaluateFI→CancelGoals→MarkLethalFOV→BackwardRecovery。执行状态会改变导航。 | RGB-D/ORB-SLAM3＋VLP16；FIT1/NBVP/GB-Planner2/FAEL。正文区分GT规划实验和SLAM/FI实验。 | **健康监测＋恢复重规划已覆盖**。FIM查表用Identity噪声是模块事实，不是整系统无噪声模型证据。作者最终完整关联/反馈校准机制 UNKNOWN。ROS2Humble/22.04，不采用迁移作为本轮基础。 |
| [Active Visual SLAM for Robotic Area Coverage: Theory and Experiment, Kim/Eustice, IJRR2015](https://doi.org/10.1177/0278364914547893)，[作者全文](https://s3.us-east-2.amazonaws.com/publications.perl.engin.umich.edu/akim-2015a.pdf) | §4.3.1/Eq3：按两端saliency、历史proposed/verified链接统计Bernoulli匹配成功概率；候选路径累积概率加权视觉信息与里程信息，预测末端协方差/覆盖，选探索或重访。 | iSAM视觉SLAM；仿真和船体实机；open-loop/deterministic-revisit。实际成功统计参与模型。 | **历史成功率、匹配概率×收益直接覆盖**。结论承认单步贪心；未知区域saliency插值。完整可用运行代码 UNKNOWN。 |
| [DA-BSP, IJRR2018](https://doi.org/10.1177/0278364918759606)，[作者全文](https://indelman.github.io/ANPL-Website/Publications/Pathak18ijrr.pdf) | 联合位姿/关联Gaussian mixture；对未来观测和关联边际化，选择降低歧义/任务代价的动作。错误但接受的关联不是新问题。 | Gazebo与Pioneer实机激光混淆场景；BSP-uni/BSP-mul；路线可改变后验模式与关联。 | **关联风险＋主动消歧已有方法**；§7.2承认多步分支爆炸。完整公开运行包未定位，不能将承诺开源当实际已发布。 |
| [Probabilistic Active Loop Closure, ICRA2024](https://assets.amazon.science/7b/55/cb3dafd14b5ba7210870af299c8f/probabilistic-active-loop-closure-for-autonomous-exploration.pdf)，18048–18054。**作者全文** | 视觉/漂移推断keyframe回环成功率、聚合邻近keyframe；Eq9–10：概率×预期图不确定性下降−运动成本；branch-and-bound选重访位置。 | 实机视觉/深度探索，多平面；ALCv1/ALCv2；w100仿真NeighborD-opt。实机使用distance proxy，不能假称完整协方差验证。 | **概率乘收益直接覆盖**。作者承认概率模型数据驱动改进、机上NeighborD-opt与局部/全图等价性待验证。完整代码 UNKNOWN。 |

额外必须排除：[ARAS, IROS2020作者全文](https://robots.et.byu.edu/jmangelson/pubs/2020/Hsiao20iros.pdf)，当前状态/地图多假设、主动探索与重访剪枝已存在；未来ambiguities尚未预测、预算剪枝有损，是该文明确局限，不能未经后续排重认领为空白。真实RGB-D部分为人携式辅助建图，不能称全自主实机验证。

**排重结论**：C1普通恢复动作/图像对学习为NOVELTY_CONFLICT；遮挡时长条件下等待与回退的停止决策为UNKNOWN。C2普通有效成功概率收益/反馈规划为NOVELTY_CONFLICT；把错误接受关联加入补测目标与DA-BSP/ARAS高度重叠，当前未获得独立新增机制证据。
