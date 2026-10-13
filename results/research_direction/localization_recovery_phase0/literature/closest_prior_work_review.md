# 最接近工作的核验与方向风险

检索日2026-10-13，优先原文方法、官方代码、出版社/作者元数据。覆盖用户给定12项，
另检索2024–2026 active localization recovery、localizability-aware planning、scan matching degeneracy。
这是有范围的选题审计，不是证明全领域不存在同类工作。AI辅助检索/核对；未声称用户已读完论文。

## 五项关键比较

**LA-Planner（IROS2025）**：§III明确碰撞/定位错误/超时任务失败；§V-A构造同时保持特征可见、
共视的viewpoint transition graph，Dijkstra选择有利于到达目标的局部视点；§V-C构造yaw的localizable
corridor；§VI-A比较Zhang及APACE-R/E。它在未知环境在线维护特征/占据图，选择position+yaw，
不是仅全局静态地图上绕开危险；“保持可定位性并改变行为”已经覆盖。官方实现失败时终止并hover，
不是本任务所设的已退化后的有限局部恢复验证。该区别尚无我们自己的效果证据。
原文：[§V](https://arxiv.org/html/2503.15273v2#S5)，[官方代码](https://github.com/Robotics-STAR-Lab/LA-Planner)。

**ActLoc（CoRL2025）**：§3.2假设已有SfM地图，输入landmarks、建图相机位姿及当前位置，
预测yaw/pitch的定位成功分布；§3.5将其与相邻视点平滑代价合并，在既定waypoint序列中选方向。
§4比较FIF与LWL、全轨迹还含forward-facing参考。不能把“结合历史观测选可靠视点”说成新思想，
也不能因它用视觉、我们用二维LiDAR就宣布创新。它不是在线扩图的Karto恢复器，代码不能直接迁入。
来源：[论文与版本](https://proceedings.mlr.press/v305/li25b.html)，[官方仓库](https://github.com/cvg/ActLoc)。

**Degradation-Aware Perceptual Path Planning（CIS/RAM2026）**：IEEE确认2026-08会议、09-01收录，
DOI有效且作者/题目对应。摘要介绍Hessian谱/条件数、compact 2D directional risk map与Hybrid A*风险
惩罚。这是直接的LiDAR/路径避退化重叠压力。**完整方法未获得**：已知地图假设、触发时刻、具体风险
编码、任务指标、最强基线、实验证据限制和开放代码均不能从摘要补写。未以其“缺乏恢复”作为已证明不足。
来源：[IEEE官方记录](https://ieeexplore.ieee.org/abstract/document/11668505/authors)。

**OCE（Autonomous Intelligent Systems，2026-10-09）**：§3、式(5)–(10)用LM迭代梯度收缩评估GICP
优化有效性；§3.4用NORMAL/DEGENERATE/RECOVERY状态及连续健康帧滞回切换估计来源。
§4.2式(12)(13)用0.5s轴向相对误差、健康P99×3定义真实不可用标签，而非以环境类别当真值。
“弱谱不必等于真实失败”在其受控实验中已直接研究；因此不是本项目新颖性。这里的recovery是
估计通道恢复/滞回，不是让机器人换位置。它使用3D GICP/LM与外部估计，Karto相关性matcher
不提供相同梯度序列，不能把新几何代理冒称OCE。源码尚待后续论文接受后公开，数据需请求。
来源：[§3–4及代码可用性](https://link.springer.com/article/10.1007/s43684-026-00144-1)。

**X-ICP（T-RO2024，在线DOI2023）**：§V分析scan-to-map对应对在优化主方向上的支撑，§VI把
fine-grained localizability约束直接放入ICP；不可靠方向受控更新或保持，§VII以APE/RPE和端点
误差评价。它做的是配准更新，不是机器人主动动作。改成二维约束投影属于成熟思路应用，
不能单独当方法贡献。[作者原文](https://arxiv.org/abs/2211.16335)，DOI10.1109/TRO.2023.3335691。

## 必须避免的关键词误判

Informed, Constrained, Aligned 的§II-C/IV中“active degeneracy mitigation”指在**ICP优化内部**
使用退化信息改变约束/更新，不是机器人主动换观测位置；“passive”指外部估计辅助等。
把标题中的active当机器人规划会误判方向重叠。
[原文定义](https://arxiv.org/html/2408.11809v3#S2.SS3)。

2DLIW-SLAM（MST2024）已明确研究二维LiDAR相似几何的退化，并融合IMU/轮速及线约束。
我们的低成本传感器背景并不是无人研究的空白；本平台无该IMU融合链，也不在本轮替换后端。
[出版社](https://doi.org/10.1088/1361-6501/ad3ea3)，[作者代码](https://github.com/LittleDang/2DLIW-SLAM)。

## 当前可回答的问题

问题筛选仍有必要：原Karto是否真的有超过正常对照的、持续的在线GT误差？几何变化是否给出
任务级恢复机会？但“观测风险+信息+代价”“退化触发动作”“二维版本”本身均不建立新意。
只有先有真实问题、简单干预的持续收益、并排除强固定/时间增加解释，才值得精确限定新模块。
当前判定 **NOVELTY_NOT_ESTABLISHED**，不是SCI选题或方法已成立。
