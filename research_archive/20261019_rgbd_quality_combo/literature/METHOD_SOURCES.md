# 只用于本原型的来源与差异

| 来源/证据范围 | 借鉴与实际差异 |
|---|---|
| [SInDSLAM，TCSVT2025](https://github.com/qimao7213/SInDSLAM/tree/be770cdafa1d4ae4e5fde0537fa3c3da73f76cdc)，前轮已读作者PDF和DynaDetect.cc | 借鉴相机运动补偿、几何/光流一致性及depth质量处理思想。其主要运动证据为单应补偿的稠密流残差与重聚类，不是我们的稀疏PnP＋3D固定门。S1不称作者方法复现。其>6m深度排除已经是成熟简单机制。 |
| [NGD-SLAM，IROS2025](https://arxiv.org/html/2405.07392v2)，作者稿及固定Tracking源码 | 光流跟踪、有效深度参与动态掩膜预测；我们不装YOLO、不做语义掩膜/完整双阶段NGD。当前本机OpenCV4.2，NGD README要求≥4.4；没有改系统依赖或引入新系统。 |
| [SR-SLAM，RAS2026](https://arxiv.org/html/2509.01111v1)，作者稿§III、刊物元数据；最终实现未认证 | 已使用depth覆盖/方差/梯度与场景可靠性指导动态筛选和pose修正。我们仅在局部观测上做固定、可解释的门控与2D退回，没有声称“质量感知筛选”是空白。 |
| [DynaPix，GCPR2024](https://arxiv.org/html/2309.09879v2)，前轮全文及tracking/optimizer/motion源码 | 已将像素运动概率用于地图点选择及加权BA，并保留可动物体的静止部分；我们不实现背景生成、软概率、加权BA，也不把一般保留有用观测当独立贡献。 |
| [DIF-SLAM，Results in Engineering2026](https://www.sciencedirect.com/science/article/pii/S2590123026024886)，本轮出版摘要及[公开仓库](https://github.com/XueX258000/DIF-SLAM)入口 | 已用实例关联、3D静态补偿残差构造速度，再用两态HMM推断动态状态并影响tracking/dense mapping。我们不实现实例分割或HMM。其是否采用本原型的逐点depth门/2D退回细节UNKNOWN，不能当不存在。 |

实际原型差异仅是可检验的**3D运动证据与约束维度选择的耦合**：两端depth质量满足固定规则时按3D残差筛选；depth不可信但2D匹配通过检查时，仅无效化当前depth，交由原生2D匹配和优化处理。它可能保留动态2D观测或误删有效depth，必须看真实轨迹。普通深度门、光流残差、二维保留本身都不是新颖性；现阶段只是一组待比较的成熟模块组合。
