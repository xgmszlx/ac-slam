# 作者源码与原生框架审查

只读下载固定提交的小型源码和目录HTML，不clone大仓、不安装、不启动系统。可复核路径与SHA见 repos.json/recovery_fetch_code.json/extra_fetch.json；旧UM缓存的metadata.json与本轮相同SHA。源码片段结论只限定核查模块，不能自动上升为整篇论文的缺失。

## SLAM-Recovery 2024

固定 `64a0e9ec968e98747a8c2cd53966c2fce4c8c449`。关键证据：

- [Inference.py](../sources/recovery/CNN/Inference.py): ResNet34，6类；Tracking.jpg和TrackLost.png转换灰度后与零通道合成RGB；256像素输入；load checkpoint.pt；argmax写abc2.txt。模型每次独立加载、数据强制cuda.FloatTensor。未核实权重字节大小/可下载性；不能仅由网络规模认证8GB显存可运行整链。
- [MINOS_Recovery_SLAM.py](../sources/recovery/SLAM-Recovery/MINOS_Recovery_SLAM.py): classifier()调用绝对路径SingleImageClassifier.py；实际仓库文件名Inference.py。需要确认安装重命名/配置约定。正常导航从simulator读shortest_path_to_goal方向/距离；恢复读字符串、选择模拟动作；6次后人工介入。随机恢复脚本上限10。它们是公开代码现状，不是全文实验的完整公平性结论。
- [merger.cpp](../sources/recovery/merger/src/merger.cpp): 循环读取同一color_.jpg，5Hz发布，Header()没有赋capture stamp，queue1000，可能重复读同一文件。没有仿真帧ID与捕获时间关联契约；无运行，不能推断实际发生多少重复/读写竞态。CV_LOAD_IMAGE_COLOR需核查OpenCV4兼容，未编译不能断言编译失败。
- [MINOS-SLAM.sh](../sources/recovery/MINOS-SLAM.sh): 硬编码/home/romi、清空abc、rm图像、启动ROS/模拟器。**本轮没有执行此脚本**。其入口启动pygame_client，不足以说明三个恢复脚本的完整注册替换步骤。
- root tree只有CNN、Dataset Generator、SLAM-Recovery、merger及README/shell/license；未随附修改过的ORB-SLAM Tracking源码/补丁。README给出的订阅修改不能单独解释谁写abc.txt/Tracking.jpg/TrackLost.png。公开文件协议来源与生成时序 UNKNOWN。

README依赖ROS Kinetic、Python3.5、旧原版ORB-SLAM/Eigen3.2、MINOS的Node8/10＋yarn。Matterport3D/SUNCG外部数据、外部checkpoint；没有固定全套requirements/镜像与完整评测台账。CNN训练和数据整理notebook存在，本轮流式读取到超过1MB停止，没保存或执行，完整训练标签/流程UNKNOWN。数据生成脚本公开不等于训练数据全部可获取。所需数据总量/最小合法子集大小UNKNOWN，不用一般数据集全量大小代替作者需求。

结论：**代码公开=是；当前环境编译/运行=NOT_TESTED；全文复现=未资格；直接作为方法基础=不推荐当前采用。** 单独图像对模型可以审查，不等于恢复控制系统可复现。改用ORB-SLAM3/Gazebo会构成新工程与新的比较条件，不能称无成本复现。

## UncertaintyMap 2025

固定 `7e5007307dc9525e3474cb6aaf1ac5ae65def811`。原生ROS1而非RTAB封装，存在实际SLAM/地图/规划/控制入口：

`Gazebo模型及带强度标记激光 → slam2d.py(KF状态/P) → /slam/states_cova + /slam/laser → map_server.py → /exp_map,/obstacle_map,/divergence → active_slam_core_rrt.py(UF/RRT与模拟收益) → /path_rrt_star → way_point_manager.py → /dot_command → path_following及避障 → 电机命令`。

**不能因该数据流存在，就写成已在本机闭环跑通。**

[slam2d.py](../sources/uncertainty/kf_slam/slam2d.py): `/gazebo/model_states`获取朝向，run()还查询`odom_groundtruth→base_link`最新TF；首次位置从该TF初始化。激光intensities==1选择cone landmarks，KMeans分簇，欧氏最近邻阈值关联。普通机器人激光是否有可用反射强度/同语义标记UNKNOWN。GT朝向实际进入在线估计，不能用于我们要求GT离线隔离的真实SLAM实验。

[KF.py](../sources/uncertainty/kf_slam/KF.py): 状态位置＋landmarks，块矩阵H/R，联合P。不把它误称“完全无相关性协方差”，不把已有完整P传播认领为新增贡献。其前提与论文A.5线性已知朝向一致；不存在本轮真实匹配正确率资格。

[map_server.py](../sources/uncertainty/kf_slam/map_server.py): bayesian_update使用`old+k*(new-old)`的log-odds插值，并另有方向性条件更新；**不是盲目逐帧log-odds相加**，不能据宽泛描述断言重复观测必然过度自信。状态P/扫描用于测量散布、地图和SiREn；native源码已经具备实际反馈。

[active_slam_core_rrt.py](../sources/uncertainty/kf_slam/active_slam_core_rrt.py): 每轮读当前状态/P和地图，计算frontiers/路径/预测divergence，打印执行后预测与当前差异，再生成目标。**预测误差打印不等于已学习校准器；已读到反馈不等于缺反馈。** `simulated_2d_slam2_test`导入在本轮核查的root kf_slam tree未找到同名文件，是否由别处PYTHONPATH提供UNKNOWN，需原作者启动环境才能断言运行故障。没有“安装即可运行”结论。

[instructions.md](../sources/uncertainty/instructions.md)有Docker和分模块命令。Dockerfile基于noetic-robot-focal，复制ws/models、catkin_make，pip安装scipy/sklearn/ruamel/pynput/matplotlib但无版本锁，get-pip使用3.6路径；当前ROS Python3.8相应依赖缺失，Docker也未发现可执行文件。run.sh挂载kf_slam到pioneer2dx/scripts；prepare会改launch；master会改parameters且`rosnode kill --all`。**没有执行这些脚本**。复現若获授权必须副本与隔离master。

`data/`公开树49个.mat文件（audit/extra_trees.json可重数），是作者simulation输出；没有下载，字节规模/内容字段/原始传感器轨迹完整性UNKNOWN。不是已认证真实SLAM数据集。原图/模型尺寸与最小Docker增量大小未测，不承诺6.3GiB能容纳镜像。

结论：**代码公开=是；本机可编译/运行=NOT_TESTED；全文复现=未资格；适合作为UM公式/原假设下离线模块参考=是；适合作为候选真实匹配可靠性系统=否，需替换GT朝向、标记landmark依赖、关联器并补齐评价，成本中等以上。** 这会重新建设平台，当前不授权实施。

## 轻量检查结果

15个已下载Python文本AST语法检查通过；未运行作者SLAM、模型、控制代码，不创建pyc。此检查只能排除这些文件的语法错误。ROS Python3.8的find_spec：rospy/numpy/matplotlib/yaml存在；scipy/sklearn/ruamel/pygame/torch/torchvision/torchsummary/pynput缺失。不是对所有虚拟环境的穷尽检查。

Noetic确认，dpkg Gazebo11=11.15.1；`gazebo --version`返回255，未据此认证Gazebo运行资格。GPU4060 Laptop 8188MiB、RAM约23.2GiB、根空余约6.29GiB。完整原始输出environment.json/static_audit.log。没有安装、训练或新ROS科学运行。
