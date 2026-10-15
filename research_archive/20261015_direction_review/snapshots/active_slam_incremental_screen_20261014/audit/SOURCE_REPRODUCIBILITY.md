# 源码、资产、保护与有限补证

本轮只做读取、版本固定、AST、CSV重组和代数检查。没有安装、编译大型平台、运行作者模型、训练或启动ROS。新工作区未修改旧文件。

## C1：一次定向补证到此结束

[tinyurl审计](c1_entry.json)显示两次301后到达：
https://github.com/ImitationDQN/Imitation-based-DQN-to-avoid-tracking-failures-in-ORBSLAM3-with-released-dataset

固定commit `36c8fdb94981044d615883285bf25a2e8683f678`。不再称实现入口未发现。认证范围是用户给出的短链→公开仓库，仓库内容与论文主题一致；没有取得全文来进一步认证其与最终实验的版本对应。

| 有限问题 | 结论 |
|---|---|
| 2024是否比较等待/主动恢复？ | **UNKNOWN**。上一轮全文未得，本轮不重复无限下载。公开随机/无恢复脚本不排除正文有其他基线。 |
| 遮挡时间历史/恢复成本？ | 2024公开Inference为成功/失跟图像对的六类分类器，全文其他机制**UNKNOWN**。 |
| 2025是否覆盖故障后恢复？ | **UNKNOWN**。公开标题/README是avoid tracking failures；不足以推断正文没有恢复。DOI本轮一次返回IEEE202/0bytes，停止获取。 |
| 完整可运行实现？ | **未资格**。固定root仅README、Minos.yaml、dataset.jpg、merger_node.cpp、start.sh；README要求imitation_agent.py和agent.pt，未随此commit提供。外部发布位置/可用性未核齐。 |
| 适合本机小资产？ | **UNKNOWN**。公开的是50小时多模态数据链接，没下载。虽然README列Ubuntu20.04/ORB-SLAM3，仍需MINOS/图像接口。没有认证小型自主示例。 |

merger_node.cpp当前读编号的本地Freiburg图像，15Hz发布默认Header；start.sh使用MINOS另一组硬编码路径，且包含rm/roscore。没有执行。不能把视频、权重声明、ROS集成说明称为完整可运行闭环。**C1继续NO_GO，本轮不再检索它。**

## 新锚定：Completeness

作者入口从出版社全文→project→[aislabunimi/exploration-aware](https://github.com/aislabunimi/exploration-aware)，fixed `010e03248ed633e755c84dc4686c6d00e6bb23c8`。正式文章online2025-12-26、Autonomous Robots50:6(2026)；项目与代码仍引用2024预印本，因此不能认证最终论文全部扩展实验已经复现。

源码：Code/CNN_EfficientNet_GradCAM.ipynb已下载约703KB，仅提取代码阅读，**没有运行notebook**。B1(include_top=False)→Conv2D1280→global pool→dropout0.4→2-class softmax。输入500×500 RGB，明确class0=NOT_EXPLORED，class1=EXPLORED。权重load路径指weights_old.h5；public元数据31.7MB。不下载权重，不声明本机推理PASS。

README错误/成本：clone命令写robot-aware-exploration而实际repo名exploration-aware；environment.yml在Code；原requirements混有ROS apt包、TensorFlow、Torch/CUDA、Jupyter等环境冻结记录，不是最小运行依赖。独立推理只需核定CPU TensorFlow2.13.1、图像预处理/h5和作者架构，禁止直接pip整个清单。ImageNet初始权重能否由已保存h5全部覆盖必须资格核验，不能偷偷另训模型。

小资产事实：取得3647行作者classification CSV（186680bytes）、regression CSV（680760bytes）和4张Grad-CAM结果图（总约171KB）。classification有TN2274/FP44/TP1176/FN153，FP跨24环境。按filename数值顺序重组281个run，23个run首次满足p_EX≥.8的记录为FP；这只是作者输出的离线重组，时间单位未认证，不是实时运行/新模型推理。**不能把raw44/23换成最终论文§5.2的21/15**，数据筛选、版本对应尚未认证。

结果PNG叠加Grad-CAM，不能直接喂模型或当原始二值occupancy。最初按CSV basename请求4个raw路径404，失败保留；另取得实际raw目录中的4张4-0环境小图，总约48KB，见actual_raw_small_images.json；与上述CSV误判子集的对应未认证。完整数据集、全部原始扫描/GT/图版本没有下载。

继续轮对相同作者CSV补做简单停止规则重组，见author_stop_baselines.json：θ=.8首次停止正确/错误/无停止240/23/18；θ=.95为216/8/57；θ=.8相邻两张保存快照满足为256/5/20。脚本核查重复身份、type标签和合成控制，不运行模型。**相邻保存快照不等于连续原始scan**，无法据此计算实际等待/运动成本。这个结果削弱复杂主动核查的必要性，已把时序确认纳入下一轮强基线，不隐藏有利于简单方法的证据。

CPU推理有原文依据；Stage/Karto/导航/严格时间基础可复用已有Doc81-Q3名义工程资格，53/53任务TF/GT配对。但本轮没有把新CNN/停止控制器接入平台，所以只给**探索性工程可行**，不写整链已PASS。下一轮须有硬资源/时间上限，失败即止。

## MapEx / PIPE：明确版本与代码差异

MapEx fixed53636bd1…，PIPE main dadde414…；PIPE README还推荐init-import，不能用main结果冒充推荐分支复现。代码与完整作者稿均核到。

Both simple_mask_utils.py:get_free_points 在每个cell循环内重设accum_hit_prob=0；因此公开实现不会按原文累计整条ray的occupancy。本文没有修改源码。**修正累计变量位置是实现一致性修复，不是创新**；未来比较须同时保留release版和与原文一致版，避免把bug修复收益计给相关性机制。

moment_loss_check.py只证明逐格均值/方差无法恢复联合first-hit分布。输出命名paper_intended_*，不是原生完整调用；有限三模型、1D、不校准概率、未运行flood-fill、没有动作收益。相关性考虑也不是首次MI/首次概率规划。最近邻PIPE已覆盖路径积分；BatchBALD已有联合信息避免冗余。

作者weights.zip公开目录列**3.08GB**，只取目录HTML，没有下载。4个LaMa模型、Torch/LaMa/range_libc环境及解压空间当前不合理低成本；experiments/pretrained_models在MapEx固定tree仅.gitkeep，没有可复用prediction缓存。因此D2暂不授权完整实验。

## Graph2024：原作者机制与本地改动分清

fixed675299330…的MyPlanner.cpp，allocateFrontierToVertex约625–753行实际以Manhattan近似＋未知顶点倍率分配，不应只照README写“Euclidean”。注释称A*却没调用；visited归属时直接-1/continue，小frontier尺寸条件被注释。原方法其他位置有prior更新/重规划，不能说没有。源码风险与真实性需分别审查。

graph_source_match.json：本地baseline整个MyPlanner包含旧科研改动，**不是pristine**；allocation函数与author fixed源码相等。没有复活旧闭环科学假设、没有改这个函数。若研究该问题，去除ignore、允许重开visited区域和经典reachable-frontier必须是基线；仅这类修复就解决时不做论文机制。

## 其他作者代码与证据

八篇主筛中原作者SHA均记录；EPIC/FALCON/metricsemantic/ActiveSplat关键源、参数/依赖/示例核读，但没有构建运行。计分器/covisibility/FI/coverage不能称实际位姿误差。14份下载Python AST通过，只排除语法错误，不是依赖/科学资格。

FAEL预筛误取一个不对应题目的arXiv PDF；核对标题即在papers.json标usable=false，未纳入论文矩阵。此失败保留，不以它支持任何FAEL方法判断。
