# NGD-SLAM技术恢复与首次真实启动

2026-10-20。**构建已恢复；原生基线仍为BASELINE_NOT_QUALIFIED。** 已完成固定源码/模型验收、私有OpenCV4.5.5构建、NGD原生链接和CPU模型推理。但两次walking真实启动均在首帧完成前SIGSEGV，没有轨迹，不能给出有效ATE/RPE，也不是算法性能负面证据。M1/M2未开发，旧组合原型继续停止。

## 已恢复的环境

用户提供的固定NGD ZIP为621,831,544字节，归档comment为`a93a14c4019efc7a209be5fbf9fefa46f5d1d90f`。提取构建所需428个源码/配置/模型文件，全部CRC读取通过，**与此前已取得的固定提交Git树逐文件blob一致**；未声称展开全部无关历史关联列表。作者源码本轮结束时428项hash仍全相同。

| 必要模型文件 | 实际字节 | 固定Git blob验收 |
|---|---:|---|
| coco.names | 625 | ca76c80b5b2cd0b25047f75736656cfebc9da7aa，PASS |
| yolo-fastest-xl.cfg | 9700 | 59255c2a9e7a3628061d21d632ba0fb704828385，PASS |
| yolo-fastest-xl.weights | **3650764** | **9180f4fb2c97d8acbb94ed0936849847c936b454，PASS** |

OpenCV使用用户提供的完整4.5.5官方源码归档：89,879,893字节，SHA256 `a1cfdcf6619387ca9e232687504da996aaa9f7b5689986b8331ec02cb61d28ad`。这是本地登记hash，不冒称独立官方校验值。源码版本头、CMake实际选择、C++运行版本均为**4.5.5**。

所有展开/构建/安装/临时文件位于：

`/media/wcqw/KESU/slam_research/ngd_native_recovery_20261020/`

该分区为rw的fuseblk，C++编译、执行和共享库symlink加载测试通过。私有安装前缀`opencv-install`，`OpenCV_DIR=.../opencv-install/lib/cmake/opencv4`。OpenCV以4线程、NGD/DBoW2/g2o以2线程构建；不执行作者无界make，不安装系统包。排除了Conda/OpenJPEG路径干扰；没有覆盖系统OpenCV4.2，dpkg校验无差异。新增外置工作目录约546MiB；根分区仍约3.6GiB可用，未清理旧资料。

**原作者NGD库、DBoW2、g2o、原始rgbd_tum均已编译/链接成功。** 首次CMake因未提取Examples_old依赖失败，补取同ZIP文件后通过；首次目标链接缺预构建g2o，按作者顺序补建后通过。不是源码编译缺陷，未修改作者CMake或算法文件。全部失败日志保留。

`ldd`和两次真实进程`/proc/.../maps`均确认OpenCV只来自私有4.5.5路径，未混入4.2。[动态链接记录](audit/runtime_linkage.json)。随仓YOLO-fastest用首张真实RGB做CPU前向推理通过，输出300×85和1200×85；这只认证模型格式/推理，不代表检测精度或SLAM通过。

## 唯一序列与真实启动结果

沿用既有walking827组关联，28.824169s，所有RGB/depth解码、逐图hash登记通过，最大时间差6.168ms。使用Freiburg3内参535.4/539.2/320.1/247.6、depth/5000；配置只将作者TUM3.yaml的`Camera.RGB`从1改为实际BGR的0，其余标定/ORB参数不变。GT仅离线验收，没有进入SLAM。

原始作者入口已成功构建并保留。实际启动使用其**独立无窗口副本**，唯一差异为`System(...RGBD,true)`改为`false`：旧合格ORB平台曾记录同类viewer退出生命周期崩溃，故不重复这个已知UI问题。[入口补丁](audit/headless_entry.patch)和[运行前选择](protocol/entry_choice_before_run.json)保留。没有增加跟踪/掩码日志钩子，未改变估计器、80%掩码清零、roll判断或动态策略。

| 真实启动 | OpenCV线程环境 | 完成帧调用/输入 | 原始退出 | 管理墙时s | 用户+系统CPU s | 峰值RSS MiB |
|---|---|---:|---|---:|---:|---:|
| walking01 | 默认 | 0 / 827 | **SIGSEGV，time包装器139** | 5.015 | 4.34+0.23 | 484.4 |
| walking02 | OPENCV_FOR_THREADS_NUM=1 | 0 / 827 | **SIGSEGV，time包装器139** | 4.512 | 4.21+0.14 | 483.5 |

两次均加载词典、创建map0、初始化YOLO、宣布827张输入后，在首个TrackRGBD完成前退出；原生`Frame ... end`记录均为0。**没有CameraTrajectory或KeyFrameTrajectory**；已保存位姿覆盖0/827，ATE、1s平移/旋转RPE、逐帧失跟率均**N/A/UNKNOWN**，不是误差0。上述耗时主要是启动，不是有效跟踪速度。原生只记录了初始map0，没有后续重建证据；不据此认证完整地图生命周期。

`resource.txt`记录“Command terminated by signal 11”，即使其尾行Exit status显示0，也不能认定成功；以包装器返回139与信号记录联合判断。[两次完整日志与命令](results)、[机器可读汇总](results/summary.json)。没有删除失败或用旧ORB轨迹替代。

## 崩溃定位与停止边界

一次受限只读定位包含两个GDB启动：首版在PLT/真实函数入口间提前停下、未得到故障；修正版最多运行首帧，**捕获SIGBUS，栈在`cv::connectedcomponents::LabelingBolelli4CParallel` → `connectedComponentsWithStats` → 原作者`YOLO::postprocess/Detect/Run`**。这不是首次SIGSEGV的同一份栈，不能保证两次信号的完整根因相同；也不能由此宣称OpenCV普遍有错。

随后仅检验OpenCV源码支持的环境开关`OPENCV_FOR_THREADS_NUM=1`：独立调用作者YOLO::Detect，在同一首张真实RGB-D上成功得到640×480、82,438个非零像素的掩码。没有替换连通域算法或修改掩码定义。这一局部通过后，**事前登记一次技术重试**；walking02仍首帧崩溃，所以线程设置**不足以解决集成运行问题**。重试故障栈仍UNKNOWN，不将前一次并行分支的栈直接套用。

计数清楚区分：**2次真实序列启动、0次完整运行、2次首帧以内GDB前缀启动、独立模型/Detect软件探针**。首次运行的原始stdout/resource/run/started记录未覆盖。归档检查发现重试脚本误复用了首次协议路径：`first_run_frozen.json`及`attempts_final.json`现存内容实际属于walking02；已原样另存明确命名的重试文件，并将首次登记单独标为**事后重建、原始登记字节缺失**，不宣称两份事前冻结原件都保留。见[登记修正](protocol/initial_registration_reconstructed.json)。技术重试有[修订](protocol/thread_runtime_amendment.json)；其事前登记内容可核对，但存在上述记录路径缺口。没有扩大序列或继续换配置尝试。

**剩余障碍是首帧集成崩溃，不再是源码、模型缺失或OpenCV版本门。** 作者后处理与实际并发/输入状态的交互、运行时内存错误仍需定位；不能从独立Detect通过推断完整线程链通过。当前没有证据将其归因80%规则、roll表达式或定位质量。

**下一步唯一建议：仅定位walking02的单线程首帧崩溃，先取得准确故障栈及内存/输入状态，再判断是否属于最小兼容或初始化修复。** 当前不再启动完整序列，不做M1/M2，不改动态规则；只有修复具有明确依据且技术通过后，才讨论恢复一次完整基线。暂不运行sitting/Bonn。

## 交付与保护

原始ZIP/partial、旧NGD目录、历史报告、主仓HEAD及两处未提交源码/diff均保留。[保护检查](audit/protection_after.json)范围为列出的5项旧文件与主仓Git状态，不冒称重哈希全部历史数据。实际使用输入另有逐图hash；本轮未写旧RGB-D。

复查入口[REPRODUCE.md](REPRODUCE.md)。私有OpenCV及所有大构建文件仍在外置盘，不上传模型、原始图像、ZIP、词典、SO/object。Git归档只含报告、构建/运行脚本、紧凑日志、hash与实际失败结果。无新方法、无ROS/仿真/训练、无下载；源代码和模型均使用用户到位文件。状态ANALYZED，未独立团队复验。
