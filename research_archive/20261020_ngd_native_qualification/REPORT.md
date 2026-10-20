# NGD-SLAM独立复现与增量原型：本轮技术收口

2026-10-20，ANALYZED。**BASELINE_NOT_QUALIFIED。本轮没有完成NGD核心编译或真实序列运行，未开发M1/M2。** 主要阻碍是作者必要源码/模型和隔离OpenCV源码未完整取得，以及原生CMake不接受已安装OpenCV4.2；不是已证明NGD算法无效或作者系统不可复现。到此停止获取和移植，不用模拟结果代替真实结果。

## 已接受的旧结果与保护

核查当前仓库/worktree最新提交`129524efc102f5db6e5145290c5b8ed703e26f35`，未将旧固定归档当作最新。接受desk重复B1_INCONCLUSIVE、Bonn S0/S1/S2无增益、删除消融STOP_CURRENT_COMBINATION_PROTOTYPE；不继续修补旧S1/S2/E1/E2。主工作区的两处已修改文件、用户1.md和完整Bonn ZIP保持原样。

新目录`/home/wcqw/ngd_slam_incremental_20261020`。根盘仅约6GiB空闲，保留5GiB余量；已挂载非系统盘约70GiB可用，独立源码/partial与配置构建放在`/media/wcqw/KESU/slam_research/ngd_slam_20261020`，本目录external链接到它。只测试了新目录内文件与symlink，不更改挂载/旧文件。

## 固定作者版本及真实构建结果

作者[NGD-SLAM仓库](https://github.com/yuhaozhang7/NGD-SLAM)固定commit **`a93a14c4019efc7a209be5fbf9fefa46f5d1d90f`**，本次ls-remote与本地Git元数据相符。README、原始CMake和已有Tracking.cc缓存的Git blob均逐字节核对相同提交。**这只认证三个已取得文件，不是完整checkout已通过。** [版本记录](audit/source_version.json)。

作者README/CMake要求OpenCV≥4.4，C++14、Eigen≥3.1、Pangolin、随仓DBoW2/g2o/Sophus及YOLO-fastest。机器为Ubuntu20.04、g++9.4、CMake3.16.3、系统OpenCV4.2、Eigen3.3.7；旧本地Pangolin0.6仍可只读复用。原系统/库未安装、覆盖或重编译。没有不安全地降低作者版本门。

| 实际操作 | 结果 |
|---|---|
| 固定commit整包获取 | 发现大量无关旧IMU关联文本，停止整包传输，partial保留 |
| Git稀疏获取 | Git2.25.1的clone --sparse组合先失败；常规filtered clone取得元数据/根文件；必要src/include/Thirdparty/RGB-D检出遇curl56 GnuTLS -9、early EOF、index-pack失败 |
| 隔离OpenCV4.5.5源码（官方opencv-python PyPI source） | 180s取得9,216,549 / 89,920,521字节，未完整；直接官方连接亦超时 |
| 官方OpenCV Git备用路径 | GnuTLS握手异常终止；未取得可编译依赖，不追加新获取路径 |
| **未修改的作者原生CMake配置** | **exit1：找到OpenCV4.2但版本不兼容，报OpenCV≥4.4 not found** |
| NGD核心/模型推理/序列 | **NOT_REACHED / NOT_RUN / 0次** |

完整失败及取消记录见audit，未关闭SSL验证、用不明镜像或训练模型。一次read-only git status意外触发不必要lazy fetch，已仅取消本轮status子进程树；必要检出自身的TLS失败分开保留。不将这些工具失败归因算法。

**随仓模型元数据确实存在**：Thirdparty/YOLO下coco.names、yolo-fastest-xl.cfg、yolo-fastest-xl.weights；预期weights的Git blob为`9180f4fb2c97d8acbb94ed0936849847c936b454`。但文件内容未完成checkout，完整性、格式、CPU推理耗时均UNKNOWN。没有“有仓库就等于模型可用”的认证。未运行作者包含无限make -j的build.sh。

## 源码行为：已知与未知

- [YOLO::postprocess](https://github.com/yuhaozhang7/NGD-SLAM/blob/a93a14c4019efc7a209be5fbf9fefa46f5d1d90f/src/YOLO.cc)：检测person类、框内depth统计/最大连通域、膨胀后，mask非零比例**严格大于80%**即清零。源码事实成立；是否实际触发、触发后误差如何，本轮UNKNOWN。
- Tracking.cc的GrabImageRGBD调用InsertInput/GetOutput，接收图像＋mask；GetOutput无原始时间戳。当前路径会对新mask/历史mask作条件处理，再经PredictCurrentMask的腐蚀、动态点采样、LK、depth聚类重建当前mask。**检测mask清零不必然等于当前最终mask立刻全零**，不能直接宣称动态点因而污染优化。
- 缓存已与固定Git blob核对的Tracking.cc确有`std::abs(rollDeg > 10)`。它对布尔值取绝对值，不是对角度幅值判断。C++软件语义控制在−20°得到false，而幅值门为true；这没有证明其在真实序列中造成错误，普通修复也不是SCI贡献。
- [Frame的RGB-D mask构造路径](https://github.com/yuhaozhang7/NGD-SLAM/blob/a93a14c4019efc7a209be5fbf9fefa46f5d1d90f/src/Frame.cc)在原ORB提取后按mask保留零区关键点/描述子，再建立N、depth和grid。Tracking在非关键帧采用光流，需关键帧时建立带mask的ORB Frame。因此不能只看单一ORB数量衡量所有实际定位约束。
- mask年龄、检测/传播更新、80%事件、真实MapPoint/优化内点均未实测；不能把旧独立几何匹配、旧S2内点或图像人物存在充作NGD事件。

[semantics_probe.csv](audit/semantics_probe.csv)仅是两个源码表达式的C++语言/阈值边界控制，不是作者检测器推理、合成SLAM或方法收益实验。没有提交任何改动NGD估计行为的补丁。

## 作者基线及原ORB参考

| 序列 | 已有ORB在线ATE m | 已有ORB导出ATE m | 本轮NGD |
|---|---:|---:|---|
| TUM walking_xyz，正确色序3次 | 0.441545–0.475774 | 0.413644–0.437544 | NOT_RUN |
| TUM sitting_xyz，正确色序1次 | 0.009108 | 0.009186 | NOT_RUN |
| Bonn moving_obstructing_box，S0两次 | 0.554072–0.557452 | 0.532349–0.546061 | NOT_RUN |

数值来自旧原始summary/run文件，只作历史参照，见[previous_ORB_reference](results/previous_ORB_reference.json)。作者fork、跟踪模式、特征预算、模型线程和构建版本未与旧系统完成等价认证；没有NGD数据，**不能计算本机NGD相对ORB收益**。

NGD在线/导出ATE、1s RPE、覆盖、重置/地图身份、CPU/Track耗时、mask与实际约束表全部NOT_RUN。**两张要求的真实科学图未能交付**：无NGD轨迹/真实mask记录，未用模拟图或旧ORB曲线冒充NGD结果。

## 窄候选、文献边界与决定

[六项直接近邻矩阵](literature/METHOD_MATRIX.md)区分全文、源码和出版社摘要/节选。DIO已有刚/非刚体光流与传播，SR已有历史可靠性/depth/筛选协调，DIF已有实例时序状态，Measurement2026已有mask传播＋自适应流门，Discover AI2026已有depth聚类＋极线静态恢复。普通传播、阈值、静态特征保留或质量评分都不能直接认领贡献。

**仅保留一个未验证问题**：NGD检测mask>80%清零，经已有历史传播后，是否真的造成当前掩码与静态地图有效支持的突变？这不是已确认方法不足。M1“保留上一mask”和普通roll表达式修复均不新；当前没有M0行为证据支持设计M2，更没有声称超越2026近邻。

**决定：BASELINE_NOT_QUALIFIED，暂停这一NGD实例的算法开发。** 有限隔离获取未就绪，停止追加下载、移植和文献扩展。不将技术阻碍当科学否定，也不因此重启旧原型。

**下一步唯一建议：在正常网络条件下取得可离线验收的固定NGD必要源码/随仓模型，以及完整OpenCV≥4.4源或匹配开发包；资料到位后只恢复作者M0三条单次基线。** 当前不自动重试，不先实现M1/M2。官方源与验收要求见[REPRODUCE](REPRODUCE.md)。

旧登记文件、原核心库与已安装OpenCV包校验见[audit/protection_after.json](audit/protection_after.json)。新分支仅发布小型核验代码、版本/失败记录与本报告；不上传原始数据、partial、第三方模型/整包或未提交代码。推送后本地PUBLISHED.json记录真实SHA与远端核验。
