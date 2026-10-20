# 仅与NGD局部掩码决策相关的六项近邻

2026-10-20。完整作者稿、实际源码、出版社摘要/节选严格分开；未部署下列系统。论文作者的精度、帧率和显著性报告均不是本机实测。

| 工作/阅读范围 | 已有模块与真实决策 | 对候选改进的直接约束 |
|---|---|---|
| [NGD-SLAM，IROS2025作者稿](https://arxiv.org/html/2405.07392v2)，全文缓存；[固定作者源](https://github.com/yuhaozhang7/NGD-SLAM/tree/a93a14c4019efc7a209be5fbf9fefa46f5d1d90f)Tracking本地逐字节核验，YOLO/Frame为浏览源码 | RGB-D＋YOLO-fastest潜在动态person类，框内depth分割与连通域，LK/聚类预测mask；非关键帧光流，需关键帧时ORB＋常规优化。检测与跟踪异步。 | 掩码传播、depth辅助与混合跟踪本身均已存在。>80%检测mask清零实际存在，但下游可能保留历史mask再预测，不能从一行代码推断真实失效。 |
| [DIO-SLAM，Sensors2024](https://doi.org/10.3390/s24185929)，出版社索引的方法/结论段；全文直访失败，未宣称全文逐式审完 | YOLACT区分刚/非刚体，光流残差去除相机自运动，刚体motion一致性决定保留/剔除，运动帧传播应对漏检；可选动态刚体稠密建图。 | 刚体静止后保留特征、历史运动属性传播均有前例。作者结论明确大视野运动物体仍可能失败；不证明其与NGD80%分支同因。深度质量细节UNKNOWN。 |
| [SR-SLAM，RAS2026对应作者稿](https://arxiv.org/html/2509.01111v1)，§III全文；最终刊本未逐式认证 | detection/feature/depth及历史运动综合可靠性；按GOOD/BAD选择几何约束，depth辅助自适应DBSCAN；低可靠时直接法pose补偿、KF与优化权重变化。作者稿内部也称SRR-SLAM。 | 普通可靠性评分、按静态支持切换剔除策略、历史参考和depth质量已覆盖。不能将同类规则搬入NGD当作独立贡献。 |
| [DIF-SLAM，Results in Engineering2026](https://doi.org/10.1016/j.rineng.2026.111462)，出版社摘要/亮点；[作者仓入口](https://github.com/XueX258000/DIF-SLAM)未部署 | 开放实例标签互斥化、跨帧实例关联、3D静态补偿速度、两态HMM状态推断；动态mask影响tracking和dense mapping。 | 时间稳定实例状态/传播并非空白；本轮不引入其分割/HMM。精确mask年龄、静态地图支持策略未认证，UNKNOWN不等于不存在。 |
| [Measurement2026：mask propagation with optical flow residual threshold](https://doi.org/10.1016/j.measurement.2026.120960)，出版社摘要、亮点及方法/结论节选；完整PDF未得 | 刚/非刚体实例mask，按关键帧触发与光流残差变化更新；网格采样、DBSCAN/depth传播，Fisk分布自适应残差门与差异化特征删除。 | 自适应mask更新、光流阈值和保留静态特征的组合已有直接前例。不能仅在NGD加动态阈值或depth聚类就认领贡献；完整公式/代码复现UNKNOWN。 |
| [Discover AI2026：hybrid feature preservation](https://doi.org/10.1007/s44163-026-01578-5)，出版社全文HTML的摘要、方法/结论与data availability | 改进YOLOv8s；DBSCAN depth簇精炼mask＋极线运动分类恢复静态特征；另加自适应点线及dense/semantic mapping。 | “depth分割＋极线约束＋静态特征保留”明确重复。data availability列TUM；本轮未认证作者可运行代码入口，不能说代码不存在或其性能已获本机验证。 |

唯一可保留的待测问题是：**NGD检测mask过大时清零，经其历史传播后，是否真的造成当前mask与有效静态地图关联之间的失衡？** 目前没有本机NGD事件或收益证据，方法必要性与窄创新空间均UNKNOWN。保持上一mask/去掉清零只能算M1或普通实现改动。不能在M0未合格时先堆叠M2，更不能用旧失败冒充这条链条的科学依据。
