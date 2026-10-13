# 最接近方法：不是按关键词判断重复

核读边界见 `literature_matrix.csv`：九篇指定工作，加 Pathak 2018 与 Stachniss 2004。
本轮未找到 LAEG 可读全文，只有出版方预览；其局部执行、具体评价和代码不下结论。
两篇2026 v3更新由 arXiv 原页面确认，但没有核实正式期刊发表，不能称其已发表顶刊。
Region/retroactive 的完整方法使用 primary HTML，PDF下载失败；Pathak PDF的xref
完整性预检为 UNAVAILABLE，采用章节/算法定位，不给可信PDF页码。其余七份相关
PDF预检PASS；P-ALC p4和RA-L p6还做了渲染核读。全文缓存留本地，不发布论文副本。

## A2最直接的重叠

[P-ALC](https://cdn.amazon.science/7b/55/cb3dafd14b5ba7210870af299c8f/probabilistic-active-loop-closure-for-autonomous-exploration.pdf#page=4)
§V-B/C、Eq9/10、Alg1–3 已用簇回环概率、预计不确定性下降和占据图路程选目标。
§VI到目标后固定360°旋转；§VII-B实机用距离代理，不是已部署的neighbor D-opt。
因此“考虑能否闭环”“概率×信息−成本”不是新的A2方法；缺少我们的Karto概率模型
也不代表其没有考虑实现不确定性。

[Kim & Eustice 2015](https://s3.us-east-2.amazonaws.com/publications.perl.engin.umich.edu/akim-2015a.pdf)
§4.2、4.3.1/2从显著历史waypoint生成往返路径；以经验视觉链接概率加权沿途Fisher
信息，估计终端协方差，并与继续覆盖比较。它早已包含“不同路径形成不同预期测量”
这个基本思想，而不只是旋转角选择。实机比较OPL/DET；仿真还比较Active-SLAM-only。

[OSM ALC](https://arxiv.org/pdf/2407.17078v1) §III-A、Alg2则在当前不确定性高时，联合
评价历史路网节点、到达路线与剩余覆盖，收益基于加权图D-opt。其
[官方代码](https://github.com/IMRL/ActiveLoopClosure) 依赖FAST-LIO、LiDAR-Iris、GTSAM
与terrain/OSM管线，不能仅换传感器就宣布自己的目标评分新颖。

## A1最难绕开的固定路径机制

[原 RA-L](https://arxiv.org/pdf/2308.16522v2) §V-A 已明确到回访区域后重走历史轨迹。
本文§IV-C自己区分 loop edge 与真实loop closure，不应指控其“以数学边保证后端
必定接受”。真实问题只能来自执行/评价不足的证据。

[Zhang v3](https://arxiv.org/pdf/2503.17005v3) §IV结构与IV-C的polyline导航、历史junction
重走、全局frontier/航点顺序优化已经通过重复观测促进闭环；§V-C有禁用retracing
的消融。历史重走本身不是创新，但它也不是“到一个给定区域后比较多条局部路线”
的完全同一设计。

[Lighthouses](https://arxiv.org/pdf/2306.10463v1) §III-B/C使用信息丰富的全景历史簇和最近
lighthouse返回；§III-D沿图的凸包双向走以连接外缘。[Region v3](https://arxiv.org/html/2504.10416v3#S4.SS2)
§IV-B进一步把P-ALC限定在当前region，并在区域完成后顺/逆时针走convex hull稳定化。
局部路径、双向视角、区域图稳定化已经存在；仅组合它们并不能说明固定策略不好。

## 反馈控制不是自动解围

[Stachniss 2004](https://www.ipb.uni-bonn.de/papers/stachniss04iros.pdf) §IV、Alg1从metric
近/topology远的入口重走历史，依据当前和历史入口的不确定性决定停止，§V-D比较
单阈值和其准则。一般“闭环反馈停止”并非新思想，而且FastSLAM粒子退化原因不是
Karto图增益问题。

[Pathak 2018](https://indelman.github.io/ANPL-Website/Publications/Pathak18ijrr.pdf) Alg1/2、
§4.4–4.7对候选动作模拟观测、关联假设和后验成本；它解决更广的数据关联不确定性，
不是低成本局部回访路径组件的直接同款。不能说前人都假定关联完美。

## 不应混入的后端“回访”

[Retroactive 2026](https://arxiv.org/html/2607.13516v1#S3.SS5) §III-E利用优化后的轨迹几何
重新关联**已保存**local maps/submaps；Eq13–18与fine registration是后端数据回查，
不是机器人去哪里/怎么走。§IV-C评估重访地图一致性，并说明ATE收益可能很小：
这支持独立地图评价，但没有验证主动策略。

[LAEG 2022 出版预览](https://www.sciencedirect.com/science/article/pii/S092188902200104X)
确认occupancy+visited map、inner frontiers与显式loop hypotheses；完整算法/执行
无法核实。因此既不能用其未知局部执行宣称我们重复，也不能用它未知的缺项宣称新颖。

## 最小方法比较表

| 方法 | 决策对象/时刻 | 事前输入/预计收益 | 实际动作/终止 | 与当前问题关系 |
| --- | --- | --- | --- | --- |
| RA-L2024 §IV/V | 区域序列、插入回访边 | prior图、TSP、D-opt/距离 | 到区域后历史段；走完继续 | A2强基线；A1固定历史段基线 |
| P-ALC §V/VI | 行进前选历史簇 | view score、图/地图距离；概率收益−成本 | 到点360°；阈值触发，否则frontier | A2直接重叠，A1执行形式固定 |
| Kim2015 §4.2/4.3 | 出发前选waypoint往返/继续 | saliency、链接概率、沿路终端协方差 | 往返release点、恢复覆盖 | 路径条件测量收益已存在 |
| Zhang v3 §IV-C | 搜索/导航时选frontier与重走序列 | 已访问junction、栅格/运动一致性 | polyline逐段，失败重规划/skip | A1 retrace与motion shaping重叠 |
| Region v3 §IV-B | region内ALC、完成后PGS | 一致snapshot、P-ALC；regional图 | 固定双向凸包，后续marginalize | 固定区域观察路线强基线 |
| Lighthouse §III | 触发后最近lighthouse/最终PGS | 图、view score、timer/uncertainty | 固定全景/双向凸包 | 最近/固定基线不可忽略 |
| OSM §III-A Alg2 | 高uncertainty时选历史路网目标 | visited图权、coverage路程、D-opt | Dijkstra到目标+剩余RPP | A2 global target/path基础重叠 |
| Stachniss Alg1 | 机会出现时重走/执行中停止 | particle图、历史入口H | 跟历史路线，H条件终止 | 反馈停止早已有基础 |
| Retroactive §III-E | 优化后选存储数据关联 | 新图几何/历史submaps | 重新配准，无物理运动 | 相关但不是A1/A2决策 |
| Pathak Alg1/2 | 执行前比较动作序列 | 多假设belief/观测likelihood | 执行并更新belief | 基本思想已有，系统成本不同 |
| LAEG preview | 下一探索region | visited/occupancy/loop graph | 全文未核实 | 不据摘要判断完整执行机制 |

结论：还没有一个被现有数据验证的、超越固定重走/最近合格历史目标/P-ALC的具体
缺陷。没有提出“新信息公式”或把geometry support count改名成实现概率。
