# 必要近邻矩阵（2026-10-19）

仅检查指定七篇，不以摘要未提及判定功能不存在。A=深度观测，B=地图保留与后续定位，C=计算预算。代码公开不等于本机认证。

| 论文 / 核查范围 | 处理环节、观测/状态及实际决策 | 重叠与需实验判定的部分 | 作者实现与当前成本 |
|---|---|---|---|
| [ORB-SLAM3，T-RO2021](https://arxiv.org/abs/2007.11898)，本机固定源码全文与原生基线 | RGB-D特征→原始像素depth读取、虚拟右目、地图点建立、跟踪/局部BA/回环/Atlas；按匹配、视差、观测次数等增删点/关键帧。 | 无效depth保留2D特征，但不能据此直接由depth建立3D点；2D特征仍可关联已有3D地图点或经多视图建立点。简单depth拒绝不是新贡献；此次检验拒绝是否损伤真实支持或改善轨迹。 | [官方代码](https://github.com/UZ-SLAMLab/ORB_SLAM3)，commit4452a3…已运行合格。复用，不建新后端。 |
| [Proença/Gao，Probabilistic RGB-D Odometry，RAS2018](https://arxiv.org/html/1706.04034)，全文§3–4 | RGB-D空间/时间深度样本→高斯混合融合、不确定性传播；点/线/面加权运动估计；由位姿不确定性限制时间窗口，并用距离一致性抑制遮挡融合。 | 直接覆盖“边界噪声＋深度不确定性＋混合融合”的宽机制。本文的简单局部拒绝只作基线；是否存在其不能处理的任务损失尚未证明。 | [作者出版页](https://pedropro.github.io/publication/)提供代码入口；本轮未部署，不能称全文本机复现或任意RGB-D均已解决。 |
| [MAC-VO，ICRA2025](https://arxiv.org/html/2409.09479v2)，沿用已读方法与固定源码审查 | 学习式双目VO；匹配位置/深度不确定性→完整3D协方差、筛点及加权优化；含MatchCovariance与GaussianMixtureCovariance。 | 已显式处理图像位置与depth耦合。单个协方差输出不是作者失败证明；RGB-D迁移不构成贡献。本轮不以MAC-VO失败为假设。 | [代码](https://github.com/MAC-VO/MAC-VO)，需要额外模型/CUDA环境；本轮不部署、不训练。 |
| [MS-SLAM，JFR，2024在线/2025卷期](https://onlinelibrary.wiley.com/doi/full/10.1002/rob.22431)，全文§4及LocalMapping源码 | 局部点暂保，非局部点滑窗稀疏化；关键帧—点可见性、点价值、图像分格分布→MILP/K-cover式保留集合。 | B的固定预算/覆盖/保留策略已有直接近邻；不能将每帧覆盖代理称后续定位能力。尚需独立query验证，不可假定它没有重定位保护。 | [代码](https://github.com/fishmarch/MS-SLAM)基于ORB3，源码确有移交稀疏化线程；Gurobi额外依赖。API限流，main分支猜测404后读到master单文件，未认证发表版本或编译。 |
| [Good Feature Matching，T-RO2020](https://arxiv.org/html/2001.00714)，全文§III–VII | 运动/结构Jacobian与逐步揭示的2D–3D匹配→Max-logDet、随机加速贪心选择，将预算用于优先匹配而非全匹配后筛选。 | 直接覆盖C的预算—定位质量与普通几何价值选择；不是运动主动规划。预算策略是否影响当前RGB-D残差需实验，不能因后端不同排除重叠。 | [作者GF-ORB-SLAM2](https://github.com/ivalab/gf_orb_slam2)，不同系统/接口，迁移有成本，本轮不部署。 |
| [SlimSLAM，ASPLOS2024](https://doi.org/10.1145/3620666.3651361)，会议/机构信息；全文和官方可运行仓库未认证 | 视觉惯性SLAM运行时自适应调度/计算—准确性权衡；作者机构说明支持调度器定位。具体可控参数与全机制 **UNKNOWN**。 | C的一般“按输入质量/负载调整预算”不能直接认领。因全文未取得，不能断言它缺少某种质量约束或预测器。 | 当前不能给开箱复现/训练/接口结论，成本UNKNOWN；不为它重建VIO运行时。 |
| [PKS，ISPRS JPRS2022](https://doi.org/10.1016/j.isprsjprs.2022.07.003)，摘要＋作者Tracking.cc实际源码 | 视觉惯性关键帧选择；匹配保持、可见性/视角变化、图像网格分布→是否选关键帧，影响三角化及地图几何。 | 关键帧选择与地图点保留不同，但均会改变未来可用约束；不能仅换名为“地图质量管理”。对固定地图预算的真实query表现未知。 | [代码](https://github.com/arashazimi0032/PKS)，公开片段有可见性/角变化和3×3分格计算；本轮未编译。全文未得，不用代码片段否定全部机制。 |

B实施边界：固定ORB3源码有System.SaveAtlasFromFile/LoadAtlasFromFile、二进制.osa及词典checksum校验，也有ActivateLocalizationMode。**但是加载后会CreateNewMap，Tracking的NOT_INITIALIZED分支仍执行StereoInitialization。保存/加载入口存在不等于独立冻结地图query定位已合格。** 本轮只静态核查，不启动B系统或多次遍历。C只文献/成本检查，不写调度器。
