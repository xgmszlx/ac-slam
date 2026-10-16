# 六篇以内的定向审查

2026-10-15。FULLTEXT指实际取得的方法/实验全文；CODE指逐文件读取；README不是运行认证。只深入检查以下六篇；经典工作仅作为冲突提醒，不扩展综述。2026检索没有筛出比这些工作更适合当前预算且已核验的作者平台，不能据此称2026没有相关方法。

| 论文、年份与入口 | 问题、输入→输出及机制 | 数据与真实评价 | 原文限制、推测和未知 | 代码、训练、硬件与ORB-SLAM3复用 | 对选题的影响 |
|---|---|---|---|---|---|
| [AirSLAM](https://arxiv.org/html/2408.03520v4)，T-RO 2025；[作者代码](https://github.com/sair-lab/AirSLAM) | 双目/可选IMU→VO地图；离线优化地图→单图重定位。PLNet联合点线检测，匹配和几何优化，结构图筛重定位候选。方法§V-D只匹配当前帧和最近关键帧。 | EuRoC、OIVIO、UMA-VI及合成降亮度EuRoC；TartanAir昼夜地图复用。轨迹RMSE、完成/失败、重定位召回、耗时。 | **FULLTEXT §VIII明确**：依赖足够直线，非结构环境退化为纯点。§VII-C讨论局部照明和描述子变化。降亮度实验是图像变换，不能等同真实曝光噪声。**未知**：缺线时哪一种新增约束有独立价值。 | **CODE**：CMake强链接TensorRT，点/线残差和Huber已存在。有模型推理，无须为原生复现重新训练；PLNet训练另列。双目建图，不能直接用现有TUM RGB-D入口。不是现成本机已认证基础。 | 点线融合、换学习特征、一般光照鲁棒性均已覆盖。缺线→任意边缘/密集先验的迁移还要面对FPEVO/COMO；不推荐重建AirSLAM来寻找问题。 |
| [4Seasons](https://link.springer.com/article/10.1007/s11263-024-02230-4)，IJCV卷133，2025；在线2024-10-13 | **基准而非新估计器**。双目/IMU/RTK采集，建立VO、地点检索、6DoF地图定位评价。 | 同路线不同昼夜/天气/季节；DPVO、DM-VIO、ORB-SLAM3、Basalt。§6.1/Fig10–11比较真实轨迹，低光/高速/条件变化下性能下降。 | **FULLTEXT §4.2.1**：依赖GNSS可用性，不能承诺全程厘米GT；仅符合质量条件的pose参加相应评价。参考序列有公开GT，查询GT部分保留。阴影带来纹理是作者假说，不是因果证明。 | 作者数据/标定和基线入口公开，不是统一即用SLAM包。不需要训练来评ORB3；大体量原始遍历和双目/IMU适配不适合当前空间。未验证小包容量。 | 支持问题真实存在；既不证明某个不确定性模型不足，也不提供我们的新机制。V4需要参考图构建、查询和几何验证，当前不是低成本首选。 |
| [MAC-VO](https://arxiv.org/html/2409.09479v2)，ICRA 2025；[代码](https://github.com/MAC-VO/MAC-VO) | 双目→度量VO。联合预测匹配/深度不确定性；筛点；局部深度统计传播为每点完整3×3协方差并优化。 | TartanAir v2、EuRoC、KITTI、ZED；相对平移/转动误差及消融。§IV明确没有回环/GBA，不能把VO比较当完整SLAM闭环。 | **FULLTEXT §III-C**：匹配位置扰动跨深度边界会放大3D误差；以局部统计校正。**CODE**：MatchCovariance以及GaussianMixtureCovariance都输出每点单个3×3矩阵，后者计算混合均值/方差。**推测**：多表面压缩是否仍造成位姿损失。作者没有据此报告自己的确定失败。 | 公开推理/评价/demo命令；当前Python≥3.10、CUDA runtime≥12.4、PyPose/xformers等。论文测试4.2GB显存，当前README普通≥6GB/fast约2.7GB，口径不同；均非本机实测。原生推理不要求重训，但模型/环境未下载。 | 普通质量筛点、完整协方差、边界方差、GMM统计都已覆盖。仅保留“表面模式压缩后是否丢失必要几何信息”作为待证问题。移植RGB-D不是贡献。 |
| [COMO](https://arxiv.org/html/2404.03531v2)，ECCV 2024；[代码](https://github.com/edexheim/como) | 单目RGB→VO和密集几何。3D锚点跨帧共享，GP深度协方差解码几何；光度对齐联合优化pose/geometry；可见性检查和条件方差选点。 | Replica、TUM、ScanNet；ATE、失败/累计曲线、深度准确与一致性、运行时间。RGB输入的评价不能与使用depth的ORB3直接作算法胜负。 | **FULLTEXT §6**未来工作包括更广泛训练、用更鲁棒学习对应替换光度约束、加入完整地图重定位。§3.3全局每帧仿射亮度；§4.2已有遮挡检查及深度边界裁剪。局部照明导致其本机失败仍**未知**。 | **CODE**：Python3.10、Torch/CUDA、Open3D、lietorch扩展、预训练DepthCov。默认tracking cuda:0/mapping cuda:1，需要为单GPU调整配置；存在CPU扩展分支，不等于整链CPU可实时运行。无需新训练才能用既有权重，但资源未认证。 | 可借鉴“可见性/几何一致性先于观测使用”，不能把GP、共享锚点或可见性门重新认领。部署新密集平台成本高。 |
| [I²-SLAM](https://arxiv.org/html/2407.11347v1)，ECCV 2024；[作者项目](https://changwoonchoi.github.io/i2slam/) | RGB/RGB-D→轨迹与HDR地图。显式曝光内多位姿积分、曝光/白平衡/相机响应，与NeRF或3DGS联合优化。 | 自建合成退化数据、TUM、ScanNet；轨迹误差和渲染质量，不能只用PSNR证明定位改善。 | **FULLTEXT 结论**明确多相机渲染和优化较慢。不能将参数化成像模型等同于已解决任意局部照明；也不能因摘要未写局部模型就断言不存在。 | 作者项目当前仍显示“Code (soon)”，本轮未认证可运行官方实现。不是证明网络上绝无实现。需要在线场景优化；并非普通预训练前端的一次前向。8GB端到端资格**UNKNOWN**。 | 光照/模糊物理建模已有直接先例。将类似模型缩到稀疏系统仍需证明差异与必要性；目前只作机制和冲突参考，不作为平台。 |
| [FPEVO](https://doi.org/10.1016/j.jvcir.2025.104599)，JVCIR 112，2025；[作者机构记录](https://repository.up.ac.za/items/db30d9f4-dcea-4dbe-96bb-2480290f13c0) | RGB-D→VO。边缘分组，点描述子建立组间对应，结构约束筛选，再估计运动；不局限直线。 | TUM、ICL-NUIM、TartanAir；ATE、平移/转动RPE。 | **PARTIAL_METHOD_VERIFIED**：出版商可检索方法节说明边缘处深度稀疏，因此不在分组/关联阶段用depth。完整PDF访问403；不能推断它没有深度可信度或其他保护。 | 未认证公开可运行作者仓库/小例程；机构与出版商标“Data available on request”，不是可下载代码证明。训练/完整依赖/本机成本**UNKNOWN**。 | 虽非优先venue，但与“用任意边缘补足AirSLAM缺线”直接相近，必须保留。该宽泛扩展没有可认领的新颖性。 |

## 经典近邻冲突提醒（摘要级，不作为第七篇深入分析）

[Proença & Gao, RAS 2018，Probabilistic RGB-D odometry based on points, lines and planes under depth uncertainty](https://www.sciencedirect.com/science/article/abs/pii/S0921889017303378)的出版商摘要明确已有高斯混合时空深度融合、概率传播和位姿估计。这里只核查摘要/引言，没有认证其混合分量在全部位姿求解阶段的保留方式。因此“加GMM/时序融合/深度加权”属于直接冲突；“表面条件似然”是否已完整覆盖为**UNKNOWN**，不能以未读全文作新颖性保证。

## 阅读边界

AirSLAM v4、4Seasons出版商全文、I²-SLAM v1有本地HTML与hash；MAC-VO v2、COMO v2经网页全文读取，其本地文本获取失败记录保留。FPEVO仅方法节可检索内容、机构摘要和出版信息，不标全文已读。API 403、错误猜测文件路径404均记录；后者不能解释成作者整仓缺文件。没有把浏览器缓存内容与本机成功下载混同。
