# 最近邻工作矩阵

所有方法结论为“文献支持”，代码行为为“已验证事实”；未知字段禁止填成否定。重合按候选反馈校准的路径可靠性问题审查，不能理解为论文质量评分。

## 身份与证据

| id | title | year_venue | paper_url | read_scope |
| --- | --- | --- | --- | --- |
| P01 | Graph-Based SLAM-Aware Exploration With Prior Topo-Metric Information | RA-L 2024 | https://arxiv.org/html/2308.16522v2 | 方法IV/V、实验VI全文；当前本地源码 |
| P02 | Optimizing Exploration With a New Uncertainty Framework for Active SLAM Systems | RAS 2025，193:105059 | https://arxiv.org/html/2506.17775v1 | 方法3、实验5、附录A.4/A.5全文+代码 |
| P03 | FIT-SLAM 2: Efficient 3D Exploration With Fisher Information and Traversability-Based Adaptive Roadmap | RAS 2025，194:105188 | https://doi.org/10.1016/j.robot.2025.105188 | 出版摘要+方法实验节选；固定SHA当前核心源码；未完整最终全文 |
| P04 | Perception-Aware Planning for Quadrotor Flight in Unknown and Feature-Limited Environments | IROS 2025 | https://arxiv.org/html/2503.15273v1 | 方法V/实验VI全文+PDF页7+代码 |
| P05 | ActLoc: Learning to Localize on the Move via Active Viewpoint Selection | CoRL 2025 | https://arxiv.org/html/2508.20981v1 | 方法3/实验4/限制6全文+PDF页9+代码 |
| P06 | Help Me Through: Imitation Learning Based Active View Planning to Avoid SLAM Tracking Failures | T-RO 2025，41:4236-4252 | https://doi.org/10.1109/TRO.2025.3582817 | IEEE/KAIST摘要+Crossref元数据；全文未获取 |
| P07 | Mutual Information-Based Hierarchical NBV Decision for Active Semantic Visual SLAM Under Dynamic Environments | Scientific Reports 2026，16:5847 | https://www.nature.com/articles/s41598-026-36259-x | 方法和实验全文 |
| P08 | Degradation-Aware Perceptual Path Planning for Robust LiDAR Localization | CIS-RAM 2026，2026-08-05至08，IEEE DOI 11668505 | https://doi.org/10.1109/CIS-RAM71614.2026.11668505 | IEEE摘要/出版元数据；全文和代码未取得 |
| P09 | Active Visual SLAM Using Potential Fields and Model Predictive Control | Control Engineering Practice 2026，172:106897 | https://doi.org/10.1016/j.conengprac.2026.106897 | 出版摘要/作者机构记录；全文未取得 |
| P10 | Probabilistic Active Loop Closure for Autonomous Exploration | ICRA 2024 | https://cdn.amazon.science/7b/55/cb3dafd14b5ba7210870af299c8f/probabilistic-active-loop-closure-for-autonomous-exploration.pdf | 方法IV-VI和实验VII作者全文 |
| P11 | Uncertainty-Aware Autonomous Robot Exploration Using Confidence-Rich Localization and Mapping | TASE online 2024；volume22 2025:1124-1138 | https://doi.org/10.1109/TASE.2024.3360442 | IEEE摘要；未取得可信作者全文 |
| P12 | Region Based SLAM-Aware Exploration: Efficient and Robust Autonomous Mapping Strategy That Can Scale | arXiv 2504.10416v3，2026-09-30；正式venue未知 | https://arxiv.org/html/2504.10416v3 | 方法IV/实验V正文 |
| P13 | SEER: Safe Efficient Exploration for Aerial Robots Using Learning to Predict Information Gain | ICRA 2023 | https://arxiv.org/html/2209.11034 | 方法和实验正文+作者仓库 |
| P14 | Active Visual SLAM for Robotic Area Coverage: Theory and Experiment | IJRR 2015 | https://s3.us-east-2.amazonaws.com/publications.perl.engin.umich.edu/akim-2015a.pdf | 当前只读作者缓存文本方法4.2/4.3及实验 |
| P15 | Exploration With Active Loop-Closing for FastSLAM | IROS 2004 | https://www.ipb.uni-bonn.de/papers/stachniss04iros.pdf | 当前只读作者缓存文本方法IV/实验V |
| P16 | Robot Active Vision-Based Path Planning for Localization Improvement in Indoor Environments | IROS 2024 | https://doi.org/10.1109/IROS58592.2024.10802041 | 作者论文索引正文片段/机构列表，全文获取阻断 |
| P17 | A Bayesian Exploration-Exploitation Approach for Optimal Online Sensing and Planning With a Visually Guided Mobile Robot | Autonomous Robots 2009 | https://webdiis.unizar.es/~rmcantin/papers/MartinezCantin09AR.pdf | 作者全文索引摘要、机构元数据；PDF下载超时 |
| P18 | Multi-Robot Autonomous Exploration and Mapping Under Localization Uncertainty With Expectation-Maximization | 2024 arXiv 2403.04021；ICRA条目，版本元数据需再核 | https://arxiv.org/html/2403.04021 | 方法IV/实验V正文 |

## 方法、传感器与实际动作

| id | problem | algorithm_core | sensors | real_slam | controlled_action |
| --- | --- | --- | --- | --- | --- |
| P01 | 有先验拓扑时兼顾覆盖和图可靠性 | prior图TSP；加权约化Laplacian的D-opt/路径长度；贪心插入和剪枝 | 2D LiDAR/轮式底盘 | 是，Stage/Karto和实机 | 区域访问序列、主动重访；低层前沿和历史段 |
| P02 | 地图覆盖与测量不确定性量纲、frontier和停止问题 | dispersion probability log-odds更新；UM梯度UF；signed KL SiREn；改造RRT* | 360度2D LiDAR/差速底盘 | 受限：线性位置KF-SLAM，航向已知，无匹配错误假设 | UF/CF目标、RRT/RRT*路径 |
| P03 | 地面机器人在复杂3D地形高效探索并维持定位 | SLAM/frontier adaptive roadmap、traversability、local/global frontier与TSP；Fisher查表监测 | 视觉landmarks用于信息；RGB-D/点云用于地形；全部硬件配置未核全 | active模式集成ORB-SLAM3；论文另有GT规划计时实验，需分开 | frontier/路径；低信息触发取消目标、区域屏蔽及后退 |
| P04 | 未知弱特征环境分配定位与未知区域观测资源 | viewpoint transition graph、co-visibility约束、localizable yaw corridor、MINCO轨迹 | 前视RGB-D；实机D455 | 实机ORB-SLAM3；公开simulator.xml用动力学位姿，不是同样的视觉SLAM闭环 | 四旋翼位置轨迹和独立yaw |
| P05 | 已有地图中不同方向的视觉定位可靠性差异 | SfM landmarks及建图camera poses；attention预测yaw-pitch LocMap；定位分数与朝向连续性 | 相机/SfM地图 | 定位真实图像计算；不是未知地图在线SLAM构建实验 | 给定waypoint的camera yaw/pitch方向序列 |
| P06 | 房间过渡、低纹理墙/大厅造成视觉tracking失败 | 人监督RL/模仿学习；少量监督后在线学习微调 | 相机；其余未知 | 摘要明确视觉SLAM任务；具体后端未知 | active view planning；角度/底盘精确动作集合未知 |
| P07 | 动态遮挡及语义剔除后可用静态特征减少导致tracking失败 | global occupancy Shannon MI；YOLOv8/BoT-SORT+几何动静判断；anisotropic object prediction与feature probability map的local NBV | RGB-D，实机D435i | 是，ORB-SLAM2 | 全局frontier/viewpoint；底盘可达局部运动/视点 |
| P08 | 几何退化中LiDAR配准病态/不可观测 | Hessian谱和condition number；方向Compact 2D Risk Map；Hybrid A*风险惩罚 | LiDAR；2D/3D完整配置未知 | 定位任务；是否在线建图及后端未知 | 底盘路径/Hybrid A* |
| P09 | 施工场景未知环境自主探索与可执行运动 | ORB-SLAM3生成dense 2D probabilistic grid；Gaussian势场；非线性多阶段MPC | 视觉；精确相机配置未知 | 摘要明确ORB-SLAM3和实机 | 六轮skid-steering机器人的非完整约束轨迹 |
| P10 | 低计算量下选择真正有价值的历史目标 | cluster loop probability ×预计不确定性下降－行驶成本；neighbor D-opt/距离代理；branch-and-bound | 低算力窄FOV视觉/深度移动机器人 | 是，真实on-device | 历史keyframe cluster目标、到点固定360度观察 |
| P11 | 稀疏测量下地图收益高而定位困难 | RBPF-CLAM粒子权重；UCRMI同时考虑pose与map uncertainty | range-sensing robot/2D LiDAR相关 | 摘要明确真实SLAM和real-world exploration | 未来control actions |
| P12 | 大地图探索的质量、时间和图规模 | region内P-ALC、双向凸包稳定化、快照和NFR marginalization/checkpoints | stereo/IMU/encoder、深度栅格 | 作者报告on-device vSLAM | 区域前沿、历史目标、双向凸包路线 |
| P13 | 未知室内的高效安全3D探索 | 预测unseen occupancy→raycasting视点gain；门语义状态机；位置/yaw规划 | RGB-D/视觉辅助飞行 | 真实机器人；位姿来源与SLAM误差实验需进一步核实 | frontier及位置/yaw轨迹 |
| P14 | 水下区域覆盖中的定位漂移 | saliency路径、Bernoulli visual-link success、预期终端协方差、探索/重访选择 | 相机、水下odometry/姿态/深度 | 是，iSAM视觉SLAM | 历史waypoint、往返路径或继续覆盖 |
| P15 | 探索中漂移和粒子多样性下降 | 拓扑远/度量近的回环机会；历史轨迹重走；在线pose uncertainty停止 | 2D laser/Pioneer II | 是，FastSLAM | 前沿或历史entry/retrace，反馈决定停止 |
| P16 | 弱纹理/重复结构/光照下室内导航定位 | 预建3D模型的visual richness和fiducial markers评分→APF路线 | 视觉+marker；完整硬件未知 | 定位导航；在线建图设定未核全 | 移动机器人路径 |
| P17 | 实时部分可观测机器人感知规划 | belief-state POMDP、Bayesian optimization探索policy space | 视觉移动机器人 | 摘要确认视觉感知规划；后端细节未核全 | 有限时域路线/感知动作 |
| P18 | 多机器人建图精度与分工 | 虚拟landmarks及历史/未来不确定性传播；EM-inspired下一目标评价 | range sensors；模拟唯一ID landmarks | factor graph在线模拟；不是本机真实backend复现 | exploring/revisiting/rendezvous frontier |

## 收益预测、反馈与实验

| id | future_gain | execution_feedback | experiments_metrics |
| --- | --- | --- | --- |
| P01 | 抽象未来图边及协方差，拓扑信息增益 | 有图/连接更新、重规划；不能称没有反馈；未核实残差驱动概率校准 | Stage多地图、Pioneer3AT；路程时间、轨迹误差、图可靠性 |
| P02 | 传播机器人及landmark不确定性；UF能否消除 | 实际测量更新UM/UF，规划器再选择；这已是反馈 | Gazebo简化走廊/开阔场；四planner、覆盖、SiREn及估计不确定性 |
| P03 | 候选可见landmark信息、路网和可通行性 | 已验证BT调用isPoseSafe，取消Nav2目标、MarkLethalFOV；核读模块未见执行残差更新预测模型 | corridor/cave/marsyard及作者实机展示；时间覆盖、定位与计时；正式摘要33%不作独立结论 |
| P04 | 增量已观测特征共视、可见frontier cells、转移时间 | 特征图/未知图更新与重规划；没有证据否定所有校准机制 | 三仿真各100任务：可见特征不足作失定位；两实机暗场OptiTrack/APE、目标误差、时间、runtime |
| P05 | 训练得到的定位成功概率图 | 核查的planning.py用冻结预测和前一视点；在线权重更新未确认 | HM3D/ScanNet；定位成功阈值、平移/旋转误差、runtime、稀疏化和输入消融 |
| P06 | 学习策略；确切奖励和输入未知 | 摘要明确online learning微调；是否部署时残差校准未知 | 摘要给出约50h监督，或20h监督+45h无监督；完整指标未知 |
| P07 | 栅格熵减及短时像素特征可观测性/动态物体预测 | 在线地图/物体轨迹/特征分布更新；不能称仅开环 | 两个Gazebo场景、Meerkat实机；ATE/RPE、ERR、距离时间、tracking loss/near collision、模块runtime |
| P08 | 风险图查表预测方向退化 | 未知；不能从摘要推断没有在线更新 | 摘要报告鲁棒性；具体仿真/实机和指标未知 |
| P09 | frontier/unexplored吸引与occupied排斥；是否预测位姿收益未知 | 在线MPC、动态变化反应；收益模型校准未知 | 真实施工类场景；详细精度/GT/重复指标未知 |
| P10 | 观测匹配概率与relative graph/map distance；预期图不确定性减小 | 最新图驱动trigger/目标；本轮未确认每次执行残差校准参数 | 多个floorplan；地图质量、探索时间，和全图D-opt离线比较 |
| P11 | 粒子pose uncertainty与confidence-rich MI | 滤波观测后更新belief；模型校准细节未知 | dataset RMSE；实机pose uncertainty和时间；误差/公平性全部细节未知 |
| P12 | 继承概率ALC和区域图稳定化 | 在线图/map快照、uncertainty trigger、失败checkpoint恢复 | 地图质量IoU/距离误差、探索和优化时间/内存 |
| P13 | 学习补全占据图得到未来覆盖收益 | 实际地图和door确认更新；并不等于在线学习实际SLAM改善 | Gazebo/实机；信息增益预测、探索距离时间/成功率 |
| P14 | 沿路径可能获得的视觉约束和概率 | 更新SLAM/saliency后再次决策；不是静态假设所有边必实现 | 仿真/真实船体；覆盖、导航精度、open-loop/固定回访对照 |
| P15 | 拓扑和粒子不确定性；非未来factor oracle | 已经依据实时不确定性决定重走长度 | 真实地图/相对位置误差；frontier和constant stopping阈值对照 |
| P16 | 预建模型localizability score | 论文future work提到temporal persistence在线更新；不可推断其他反馈均缺失 | 摘要称定位误差/导航表现；完整GT与统计未知 |
| P17 | belief-dependent utility和BO评估 | 随任务推进replanning；是否实际残差校准未知 | 视觉mobile robot；指标/协议未知 |
| P18 | 后续动作对virtual map covariance影响 | 新SLAM结果重建virtual map，异步新目标选择 | 大/小simulated map；uncertainty、效率、协作/CE/BSP |

## 代码、新颖性风险与未决

| id | code | candidate_overlap | author_stated_limitations | unknowns |
| --- | --- | --- | --- | --- |
| P01 | https://github.com/bairuofei/Graph-Based_SLAM-Aware_Exploration | A高；B未来边评价高，反馈校准部分未定 | 结论限定rich topology且需要prior topo-metric信息；future work在线构图和多机器人 | 论文/公共代码全球重规划等价性；预测边实现率未获保证 |
| P02 | https://github.com/Seba-san/UncertaintyMap | D非常高；A/B地图反馈高 | 正文明确简化环境与子系统；附录明确已知航向、不考虑匹配错误 | 普通非线性SLAM、关联错误和实机有效性；当前源码航向取/gazebo/model_states，不能直接用于本方案在线决策 |
| P03 | https://github.com/suchetanrs/FIT-SLAM | A非常高；B在线监测改路高 | 未取得完整限制章节，不填推断 | 论文版本与当前代码差异；最终全文的统计/消融；校准反馈是否另处实现 |
| P04 | https://github.com/Robotics-STAR-Lab/LA-Planner | A非常高；迁移到地面/2D本身无创新 | 未发现单列限制章节；共视/可行corridor是方法条件，不冒称作者承认的实验证据不足 | 公开仿真不能证明真实tracking失败；差速底盘没有独立yaw/pitch控制 |
| P05 | https://github.com/cvg/ActLoc | 已有地图active localization近邻很强；预测视点质量非新；任务与A不同 | 多分类未提升；SIFT域下不优于LWL，跨域泛化受限 | 本机器人固定相机可执行性；训练复现数据管线；RTX4060显存适配 |
| P06 | 摘要声称发布实现/数据；具体作者仓库未核实 | A/C主动避免tracking failure非常高；B学习反馈不可忽略 | 摘要指出纯RL难跨过渡区域、监督耗时；提出减少监督 | 全文、代码URL、动作/指标/机器人、GT训练角色均未知；不能以未知宣称无该机制 |
| P07 | 未定位作者完整代码；data availability只指论文和supplement | C非常高；B执行条件变化下视点预测高 | 作者明确大部分视野突然被动态物体占据仍会lost；恢复是future work | 实现/原数据、所有对照统计、部署时收益模型学习机制；单目没有由此获验证 |
| P08 | 未知，未定位作者代码 | A几何退化避险直接覆盖；新加权cost或改2D不新 | 全文不足，无法确认作者明确限制 | 全部实验细节、风险图构建权限、反馈机制和代码 |
| P09 | 未定位作者代码 | A/C/D系统集成中度；APF+MPC不能作为新组合 | 全文不足，无法确认作者明确限制 | 全部评价、公平性、测量收益项、代码 |
| P10 | 未核实完整作者代码发布 | B概率/收益/成本目标排名非常高；本方案必须证明额外反馈信息价值 | 作者说明距离代理进一步减少计算；近邻D-opt验证与on-device代理不是同一实现 | 全系统/模型更新细节；不能以传感器迁移作新颖性 |
| P11 | 相关https://github.com/Shepherd-Gregory/CRMI；完整UCRMI实现未确认 | A联合位姿/地图不确定性直接覆盖；B未来收益很近 | 仅摘要，作者明确限制未知 | 全状态不确定性可校准程度、完整代码、对照后端公平性 |
| P12 | 完整作者代码未核实 | D/A/B区域反馈/补图很高 | future work：语义region、distinct feature覆盖、已识别畸变区域的进一步处理与submap级marginalization | 正式发表/代码/独立复验；预印本不能自动写成顶刊成果 |
| P13 | https://github.com/tyuezhan/SEER | B收益预测已覆盖；覆盖收益与定位收益需要区分 | 公开仓库明确不含训练数据、数据生成与训练代码 | SLAM精度贡献、部署权重自适应；完整训练复现 |
| P14 | 完整可执行作者系统未核实 | B动作条件关联概率和实际SLAM收益预测直接前例 | 完整作者明确limitations未本轮逐段重读，不把审查推测写成作者承认 | 现代在线执行校准是否必要；无可移植完整系统保证 |
| P15 | 完整当前作者执行系统未确认 | B“执行反馈决定继续/停止”已经是经典；旧旋转方向不可借此重启 | 原滤波框架限制；本轮未全面确认明确limitations | 向graph SLAM转移不是新增贡献；局部协方差和真实error关系 |
| P16 | 未核实作者完整代码 | A路径可定位性非常高；B模型更新是已明确前人方向 | future work自动判断失定位替代阈值及temporal persistence分数更新 | 全文、标记依赖/公正对照、代码 |
| P17 | 未核实当前完整代码 | B泛化的online utility optimization非新 | 原文完整limitations未知 | BO内部评估与物理执行反馈不同，不能混为已经覆盖具体校准 |
| P18 | https://github.com/RobustFieldAutonomyLab/Multi-Robot-EM-Exploration | A/D地图及位姿联合规划高；多机器人非本轮优先 | 正文承认小场景探索效率低于CE/BSP，用效率换精度 | 真实传感器匹配失效的外推、部署与发表版本核对 |
