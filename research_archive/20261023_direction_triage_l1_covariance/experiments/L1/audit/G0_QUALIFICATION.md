# L1 G0 可行性门：合格原生信息矩阵源鉴定

执行时间：2026-10-23（工作机时钟）
性质：**只做资格鉴定**，不是科学测量。正式测量见 `../protocol/PREREG.md` 与 `../runs/`。

---

## 0. 结论

`QUALIFIED_NATIVE_INFO_SOURCE = hector_mapping`。

依据：`hector_mapping` 在本机给出**逐帧、逐 LM 迭代的扫描匹配 Hessian**
（`/hector_debug_info` → `hector_mapping/HectorDebugInfo.iterData[].hessian`，`float64[9]`），
只需要 `laser` + TF，**不需要 IMU**、不需要 odom，可在 LILocBench 上原生运行。

这正是 `NEXT_MINIMAL_ACTION.md` §0 要求的东西——"**一个真实系统自己算出的协方差/信息矩阵**"。
在此之前该线一直停留在"本仓自己的简化 ICP"上，判决实验 `DECISIVE_NATIVE_TEST_NOT_EXECUTED`。

---

## 1. 逐候选排除过程（实测，非推测）

### 1.1 2DLIW-SLAM —— 硬阻塞，排除

沿用归档已核实事实（`NEXT_MINIMAL_ACTION.md` §1）：`src/lvio_2d_node.cpp:12` 无条件订阅
`sensor_msgs/Imu`；LILocBench `static_0.bag` 实际 topic **无 IMU**。本轮用 `rosbag info`
复核（见 §3 bag 清单），确认无 IMU 类消息。不使用合成 IMU、不使用作者平台外参。

### 1.2 `laser_scan_matcher` —— 有协方差话题，但**不是逐帧计算**，排除

排除依据是二进制符号，不是文档：

```
strings /opt/ros/noetic/lib/liblaser_scan_matcher.so | grep -E '^(position_covariance|orientation_covariance|alpha1|...)$'
  → fixed_frame, max_iterations, orientation_covariance, position_covariance,
    publish_pose, publish_pose_with_covariance, use_imu
```

`position_covariance` / `orientation_covariance` 是 **ROS 参数名**（launch 里填写的常数），
不存在由 Hessian 逐帧计算的路径。它确实发布 `/pose_with_covariance_stamped`
（`laser_scan_matcher.h:96` 有该 publisher，`position_covariance_`/`orientation_covariance_` 成员），
但发布的是**固定参数值** → 无法用于逐帧一致性检验。

> 这一条是易踩的坑：话题名字里带 `covariance`，不等于有逐帧不确定性。

### 1.3 AMCL —— 口径不同，排除

已资格验证、可直接跑，但它发布的是**粒子云后验协方差**（全局定位后验），
不是扫描匹配 Hessian。口径不同，NEES 不可比。承自 `NEXT_MINIMAL_ACTION.md` §2。

### 1.4 slam_toolbox / cartographer —— 本机未安装，排除

`ls /opt/ros/noetic/share/` 无 `slam_toolbox`、`cartographer`。
（存在的是 `gmapping`、`hector_mapping`、`rtabmap`、`openslam_gmapping`。）

### 1.5 `hector_mapping` —— 通过

符号证据：

```
strings /opt/ros/noetic/lib/hector_mapping/hector_mapping
  → hector_debug_info, HectorIterData[] iterData,
    hector_mapping/HectorDebugInfo,
    hector_mapping::HectorDebugInfoProvider::addHessianMatrix(...),
    hector_mapping::ScanMatcher<...>::estimateTransformationLogLh(...)
```

消息定义（`/opt/ros/noetic/share/hector_mapping/msg/HectorIterData.msg`）：

```
float64[9] hessian
float64 conditionNum
float64 determinant
float64 conditionNum2d
float64 determinant2d
```

---

## 2. 实测确认（qualification replay，40 s，**非正式测量**）

命令见 `../run_g1.sh` 先生成的 `../runs/g0b_*.bag`；节点参数：
`pub_debug_output:=true`，其余同 PREREG §2。

记录结果：`/hector_debug_info` 597 条，每条 `iterData` 长度恒为 **11**（LM 迭代上限），
第 2 条消息起 Hessian 非零。示例（第 2 条消息，`iter10` = 收敛迭代）：

```
H = [[  4.688, -2.922,   482.1 ],
     [ -2.922, 61.51,    977.7 ],
     [  482.1, 977.7, 126200.0 ]]
condNum = 3043   det = 3.01e8
```

全序列（597 帧）统计：

| 量 | 值 |
|---|---|
| 可用 Hessian 帧数 | 597 |
| `median |H_xx|` | 52.53 |
| `median |H_yy|` | 78.73 |
| `median |H_θθ|` | 2.930e5 |
| `median λmin(H)` | 96.85（> 0，半正定） |

**与冻结 ICP 归档的量级对照**（仅量级，不作统计结论）：
归档 `H_θθ` 约 1.4e5–3.5e5，本轮 hector `H_θθ` 中位 2.93e5 —— **旋转方向量级一致**；
归档 `H_xx` 约 5.6e3–3.9e4，本轮 hector `H_xx` 中位 52.5 —— **平移方向约小两个数量级**。

> 这个差异必须保留在报告里，不得抹平：**两者的平移信息尺度不可直接比较**。
> 这也是全程只使用**尺度无关**判据（尾重比 `R`、秩相关）的原因。

---

## 3. hector 发布的 `poseupdate.covariance` —— 实测**不可当协方差用**

同一 40 s replay 记录 `/poseupdate`（671 帧）。实测：

| 字段 | 范围 | 中位 |
|---|---|---|
| `sd_x = sqrt(cov[0][0])` | 0 – 15.46 m | **6.853 m** |
| `sd_y = sqrt(cov[1][1])` | 0 – 17.84 m | **9.219 m** |
| `sd_θ = sqrt(cov[5][5])` | 0 – 1096 rad | **568.9 rad** |

同一次运行中 hector 实际位姿在 44 s 内累计位移 12.96 m，且 40 s 内跟踪正常（未发散）。
σ_θ 中位 569 rad 在物理上不可能是一个可用协方差；σ_x 中位 6.85 m 与同序列冻结 ICP
实测的 ~cm 级相对误差相差三个数量级以上。

矩阵本身**是对称半正定的**（`max|C−Cᵀ| = 0`；(x,y,θ) 3×3 主块 `λmin ≥ 0` 占 99.9% 帧），
所以它不是"填错槽位"，而是**尺度/口径未被文档化的内部量**。

**结论**：本轮 G1 **不使用** `poseupdate.covariance`，只用 `/hector_debug_info` 的 `H`。
这一条同时是一个可独立复算的负结果：**ROS 生态里一个常用 2D SLAM 包发布的
"协方差"字段不能直接喂给 NEES 检验。**

---

## 4. 数据清单复核（`rosbag info` 实测）

`static_0.bag`：135.3 MB / 110,812 msgs / 598 s
topic：`/cmd_vel`(22092)、`/odom`(8714)、`/joint_states`(8715)、
`/laser_scan_front/scan`(8982)、`/laser_scan_rear/scan`(8982)、`/tf`(53323)、`/tf_static`(4)。
**无 camera、无 IMU。**

TF 树：`odom → base_link → {scan_front_link, scan_rear_link, camera_*(仅声明)}`。
`base_link → scan_front_link` 存在于动态 `/tf`（90/800 抽样），TF 完整。

> 附带的资格结论（对 L2 方向）：**LILocBench 不含任何图像数据**，
> `/tf_static` 里只有相机坐标系的**声明**。因此"RGB-D + 2D 激光"在本机**无同步真值数据**，
> L2 不能开工（见 `../../CONTROL/DIRECTION_TRIAGE.md`）。
