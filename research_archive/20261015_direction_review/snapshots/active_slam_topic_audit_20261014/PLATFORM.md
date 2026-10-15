# 平台与源码审查

**已验证事实**，2026-10-14。本轮没有启动 ROS master、Stage 或 Gazebo。

| 对象 | 状态与证据 | 实际可用边界 |
| --- | --- | --- |
| 主工作区 | `/home/wcqw/ac-slam`，`research/phase4c-formal`，HEAD `4746834ffa44504443fd07214105fe850d6f94e6`；两处未提交修改 | `same_input_replay.py`、`se2_information.py`保留；不能切分支覆盖它们 |
| ALC worktree | `/home/wcqw/ac-slam_alc_screen`，HEAD `c3f98f2bf0b6469041e441f4b0a836531732b941`，clean | 本地HEAD等于本轮`git ls-remote`；G1限全程任务PASS，G2/G3未决，0条认证安全新路线 |
| recovery worktree | `/home/wcqw/ac-slam_doc81`，HEAD `7db448ff240d9633591f4187f58db399b3d409f9`，clean | 本地HEAD等于远端；Q3资格PASS，科学episode=0，旧科学假设未决 |
| OS/ROS | Ubuntu20.04.6；Noetic；Stage4.3.0、stage_ros1.8.0 | 符合现有ROS1代码；本轮不迁移ROS2 |
| Gazebo | Gazebo11.15.1及gazebo_ros相关deb已安装 | 已安装≠本轮验证相机渲染、传感器噪声、物理GT、完整闭环 |
| Karto | vendored nav2d_karto源码，生产与Doc79 overlay均有mapper二进制；查ldd未见缺失库 | 原有探索闭环有历史完成记录；Q3只新近资格了正常短任务 |
| RTAB-Map | ROS1 0.21.13 deb；icp/rgbd/stereo/rgbdicp odometry与rtabmap SLAM二进制 | ICP二进制ldd未见缺失库；未跑本机Stage闭环，不称已复现 |
| 其他后端 | Gmapping已安装；AMCL已安装 | AMCL是已有地图定位，不是SLAM。apt核查未发现Cartographer，不能宣称其它目录不存在源码 |
| 导航 | Nav2D Navigator+Operator已有历史闭环；move_base1.17.3、navfn、DWA已安装 | 原插件有NearestFrontierPlanner；move_base组合仍需独立运行资格 |
| Frontier | 固定hrnr/m-explore SHA的explore_lite2.1.4已在新workspace编译通过 | 只是可编译，未运行导航、未取得安全可达路径证据 |
| GT | Stage原生`/base_pose_ground_truth`；现有地图bitmap/world尺寸与laser/base外参工具 | Q3同stamp配对100%只覆盖一次短任务；全程和RTAB-Map须重验；实机独立GT未知 |
| 内存/CPU | 23GiB RAM，约16GiB available；i7-12850HX、24逻辑CPU | 足够轻量2D/ROS1审查；不能据此保证多传感器实时性 |
| GPU | RTX4060 Laptop 8GiB，驱动535.230.02，驱动报告CUDA12.2 | 不是已安装兼容CUDA toolkit/PyTorch的证据；ActLoc官方CUDA12.4/RTX4090配置未资格 |
| 磁盘 | `/dev/sda7`根分区108G，94%已用，初检剩6.5G | 足够本轮小缓存；FIT的Docker/ROS2和HM3D训练不适合当前空间；未做删除、清理或分区操作 |
| 实物传感器 | 用户有相机、2D LiDAR | 相机是否RGB-D/双目、模型/内参、编码器、底盘footprint、硬件时间同步、实机GT均未知 |

**在线信号的来源和限制**

- Karto `MultiMapper.cpp` 实际有graph发布、完整graph观察开关、同步dump服务、accepted scan身份以及constraint covariance。边协方差不是当前机器人位姿边缘协方差。初始化prior在`path_planner.py:218`给全部边相同`Cov=diag(0.1,0.1,0.001)`；有后续pose graph处理，不能概括成永远不读后端，但也不能把初始预测称为已校准实现概率。
- RTAB-Map安装的`OdomInfo.msg`包含lost、ICP inlier ratio、structural complexity/distribution、correspondences、covariance、估计时间；`Info.msg`包含loop/proximity IDs和stats；`Link.msg`提供information。字段存在≠所选配置每帧都有效，也不等于可信后验。必须检查发布开关、零值/NaN含义、刷新频率、关联的sensor stamp。
- 安装头文件`Parameters.h`已经包含低结构复杂度的ICP策略：拒绝、仅在约束方向修正、或接受。**不能禁用它制造方法需求**；本方向必须对照这个内建保护仍开启的强后端。
- 真实coverage增长、inlier、accepted constraints是不同信号；它们不自动等于ATE降低。若评价图logdet，必须固定锚、同一状态集并边缘化新状态、同一参考线性化/规范与预算；不可对维度不断增长的整图直接做前后差。本轮推荐先用tracking/registration与离线轨迹端点，不把复杂图信息诊断做主目标。

**历史时空问题与复用边界**

Doc81原A2记录的TF链实际存在，失败原因不能写成“没有map链”。原callback阻塞、sim/wall速度、缓存/接收延迟使同时间配对大量缺失；Q3以原GUI、非阻塞队列、wall readiness、初始静止对齐资格通过。Q3不是长任务稳定性证据。冻结旧方案累计4/15消耗，旧原矩阵预算不足，本轮不续跑、不另记成新科学样本。

旧CD拼接suffix不满足物理坐标连续性，旧graph cache可滞后数秒甚至483s，历史显式TryCloseLoop为零不等于没有near/running-chain历史约束。新协议禁用后缀拼接，必须用完整连续原生运行，并收集决策时online occupancy，不能用Stage world填充在线候选。

**公开、编译、论文复现、研究基础四级审查**

| 系统 / 本轮固定提交 | 实际依赖 | 本机编译/论文复现 | 方法基础适用性与核心改动 | 工程难度（合理推测） |
| --- | --- | --- | --- | --- |
| FIT-SLAM `8ca04125b75d873155de9e546b94abf52830ce7a` | Ubuntu22.04、ROS2 Humble、Nav2、ORB-SLAM3 wrapper、roadmap-explorer子模块、traversability、lookup、Gazebo配套/Docker | 代码公开；未编译；未复现。master含deprecated旧实现，核查的是fit-slam2当前BT | 适合作强最近邻；本轮不作基础。若未来部署需相机地图点接口、底盘与导航、风险监测/校准模块 | 高，不应在Noetic上直接搬整套 |
| UncertaintyMap `7e5007307dc9525e3474cb6aaf1ac5ae65def811` | ROS1 Noetic/Gazebo11、Pioneer模型/控制插件、NumPy/SciPy/sklearn/ruamel.yaml等，Docker里有未钉版本pip | 代码公开；未编译/运行；未复现。package.xml很多依赖被注释 | UM/UF/SiREn可研究；完整基础不优先。必须替换SLAM/已知航向接口并检验map uncertainty；不能保留Gazebo真航向作为在线输入 | 中高，清理隐含路径、依赖与运行契约 |
| LA-Planner `fe85a7840c4304326f66d035a024dd3bb0b69739` | Ubuntu20.04/Noetic、nlopt2.7.1、Armadillo/Eigen/PCL、MINCO/FUEL类模块；本机Armadillo/Eigen已有，nlopt开发包未发现 | 代码公开；未编译；未复现论文SLAM实验 | 可借鉴共视约束，但需真实SLAM特征输入，改四旋翼position+yaw为差速SE(2)，替换公开仿真里合成特征及动力学位姿 | 高，整套不是地面机器人直接基线 |
| ActLoc `8614dc4a9c470736871d24cf92dde8f8e7f45cf9` | Python3.10、NumPy2.2+、torch2.5–2.6/CUDA12.4、flash-attn2.8.3、Open3D0.19、SfM/hloc/COLMAP/HM3D相关数据 | 代码/示例权重公开；未下载权重，未创建conda；未复現训练/论文评估 | 固定地图定位强近邻；本轮基础不选。需online landmark bridge、真实底盘动作可行性、替代pitch自由度、域校准 | 高；训练管线与机器人系统不同 |
| explore_lite `712bdd41027b645c9c876a4c0071478f090825ea` | catkin、roscpp/actionlib/tf/costmap_2d/map_msgs/move_base_msgs；C++14 | **本轮实际编译成功**；未启动；无“论文实验复现”声称 | 最合适轻量frontier层。源码默认frontier距离/大小cost，不是严格navfn实际最短路径；需候选输出、footprint/planner安全检查与目标仲裁 | 低到中，工程资格仍要做 |
| rrt_exploration `3ec97a78c09f0382364e4dd0d4b4b9e0096a4790` | ROS1、move_base、gmapping、Python2时代cv2/NumPy/sklearn，RRT detectors | 公开；未编译/运行；未复现 | 次选：需Python3移植、namespace/TF、random seeds、frontier过滤/assignee；多余随机性不利最小研究 | 中，当前不优先 |
| 已安装RTAB-Map ROS1 0.21.13 | 现有PCL/GTSAM等shared libs、ROS messages；scan ICP不要求模型训练/GPU | 二进制/库确认，闭环未运行；远端0.21.13路径获取404，未把错误页作源码 | **建议新最小实验后端**：扫描ICP+online map/graph/odom diagnostics；新collector、独立launch、move_base桥、冻结配置 | 中，避免改后端；若短程资格失败停止迁移探针 |

`explore_lite::makePlan()`根据frontier search结果发送centroid并blacklist失败/无进展目标；它自身没有证明连续轨迹满足本机器人footprint，更不产生两条可控路径。move_base可临时改局部路由，记录实际路线是必需步骤。

本轮验证：Q3离线测试25项、原phase0工具测试16项均通过；独立explore_lite Release编译通过。日志在`audit/verification.json`及对应log。它们验证软件/采集契约，不给科学假设PASS。
