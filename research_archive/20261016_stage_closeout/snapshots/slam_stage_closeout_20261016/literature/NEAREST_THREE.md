# 三篇最近邻：只用于判定剩余能力需求

2026-10-16。本轮经网页工具阅读以下三篇方法/实验全文；没有部署作者系统。未知能力不写成不存在。V3引用沿用先前六篇矩阵，不扩展为新综述。

| 工作与原文入口 | 问题、输入与实际机制 | 地图变化/恢复能力 | 对本轮两段残差的覆盖边界 | 公开实现与成本 |
|---|---|---|---|---|
| Akai，[Reliable Monte Carlo localization for mobile robots](https://arxiv.org/pdf/2205.04769)，JFR 2023，40(3):595–613，[DOI](https://doi.org/10.1002/rob.22149) | 激光、运动输入、占据地图→位姿/可靠性；§4.5.1按候选位姿边际化已知/未知观测类别；另有可靠性估计和全局假设融合。 | 不要求在线提供变化真值图；§6.3.1明确讨论偏差很大时过多观测判成未知、纠偏能力下降的取舍。不是任意长期变化已彻底解决的保证。 | “抑制过时观测又保留纠偏”已是直接先例。尚未在这27次更新上运行，不能声称它解决或不能解决当前残差。粒子支持不足也不能仅靠更改观测类别解决。 | [als_ros](https://github.com/NaokiAkai/als_ros)，现有launch固定433f3b…；类别条件模型、可靠性、全局采样是独立开关。固定默认launch关闭可靠性/全局采样、默认非全向且另有随机粒子，不能原样称全文框架或公平基线。本机未编译；作者CPU实验不等于本机运行资格。 |
| Trekel等，[Benchmark for Evaluating Long-Term Localization in Indoor Environments Under Substantial Static and Dynamic Scene Changes](https://www.ipb.uni-bonn.de/pdfs/trekel2025iros.pdf)，IROS 2025 | 激光/里程计与历史地图，提供共同坐标GT和tracking/global评价；比较AMCL、SRRG、LocNDF、ENM，不是一种新的鲁棒观测模型。§IV按相同初始化条件比较跟踪。 | 长期结构变化条件下出现定位退化；不同方法/条件优胜者不同。基准并不提供可在线使用的逐束变化真值。 | 文献支持长期定位问题真实存在；论文结果不证明本机A0两段由过时结构造成，也不证明现有方法不足。地图构建使用去畸变扫描，不能据此假定本次定位扫描无畸变影响。 | [代码](https://github.com/PRBonn/LILocBench)/地图/GT/轻量bag已本机验收，可复用，不需重建平台。神经基线在论文中离线评价，不能把论文整体速度当当前AMCL速度。 |
| Kuang等，[Improving Indoor Localization Accuracy by Using an Efficient Implicit Neural Map Representation](https://www.ipb.uni-bonn.de/pdfs/kuang2025icra.pdf)，ICRA 2025（ENM-MCL） | 激光建图训练稠密特征格＋浅MLP；结合非投影/方向相关投影SDF的粒子观测，与轮式预测定位。针对地图表达与观测建模。 | 有全局与tracking实验；不能从未提供本机变化标签就推断其没有鲁棒能力。LILocBench也已将其作为竞争者。 | 地图离散/方向表达是成熟竞争解释；没有证据表明当前残差需要新的区域可靠性模型。该系统也没有在本机两段残差上认证。 | [作者代码](https://github.com/PRBonn/enm-mcl)，有预训练资产和运行说明；README环境Python3.10/Torch/CUDA，不是当前Noetic原生替换。论文硬件含16GB GPU，8GB本机未验证；新增训练/地图模型及公平对照有成本。本轮不下载或部署。 |

结论：第一篇已覆盖宽泛问题机制，第二篇给出真实损失与现成基准，第三篇给出更强地图表达竞争者。它们均不支持由“AMCL还剩0.45m RMSE”直接推出新方法必要性。未完成这些竞争方法的本机对照是证据缺口，不是本轮自动扩建平台的理由。

V3边界沿用[旧六篇矩阵](../../passive_visual_slam_v2_v3_screen_20261015/literature/PAPER_MATRIX.md)：MAC-VO是双目VO；单点协方差输出不是作者失败证据；2018概率RGB-D混合深度融合也是直接先例。不能将简单GMM、边界拒绝、完整协方差认领为创新。
