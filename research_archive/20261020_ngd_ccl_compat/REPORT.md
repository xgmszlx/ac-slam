# NGD-M0-compat：OpenCV四连通缺陷复现与单点兼容修复

2026-10-20。**Issue #21366在本机复现；YOLO单点SAUF补丁通过有限语义检查，真实前两帧TrackRGBD通过。但短序列第三帧附近再次SIGSEGV，定位到Tracking中的另一处默认四连通调用；完整walking未启动，基线仍BASELINE_NOT_QUALIFIED。** 未开发新算法或M1/M2。

## 1. 已知缺陷确实复现

已读取[OpenCV官方Issue #21366](https://github.com/opencv/opencv/issues/21366)：维护者确认4.5.5的四连通调用崩溃，给出10×10全零C++输入及Bolelli4CParallel栈。本轮直接链接既有**隔离OpenCV4.5.5 C++库**，没有安装/切换OpenCV，未用Python cv2执行待测连通域。独立进程运行，信号与GDB栈保留。

事前固定6类掩码×线程1/4×默认/SAUF，共24次原语测试：10×10全零、480×640全零、10×10对角点、不同大小矩形、等大区域、触边区域。没有根据失败追加掩码。结果见[完整原语结果](results/ccl_tests.json)。

| 调用 | 成功 / 测试数 | 崩溃 |
|---|---:|---|
| 默认四连通，CV_32S | 8 / 12 | 10×10全零及对角点，在1/4线程下均SIGSEGV，共4次 |
| 显式CCL_SAUF，四连通，CV_32S | **12 / 12** | 0 |

本机GDB同时取得**串行LabelingBolelli4C**和**并行LabelingBolelli4CParallel**故障栈；四个失败病例均有独立stack日志。说明单线程并非完整规避，也说明问题与输入有关，不能说每次四连通都会崩溃。此前NGD检测线程进入Bolelli4CParallel的栈与此缺陷一致，**仍不意味着所有历史崩溃都来自同一调用点**。

## 2. 只有一个源码表达式变化

在新外置副本`/media/wcqw/KESU/slam_research/ngd_ccl_compat_20261020/NGD-SLAM`中，仅将YOLO.cc:128改为：

```cpp
cv::connectedComponentsWithStats(localMask, labels, stats, centroids,
                                4, CV_32S, cv::CCL_SAUF);
```

[单点补丁](audit/yolo_sauf.patch)。保持四连通、32位标签、检测网络、所有depth阈值、最大区域逻辑、膨胀、80%清零、roll判断与优化器不变。原源码/原二进制保留并登记hash，另复制二进制至新外置目录`original_binaries`。新副本对428个作者文件比较，**只有src/YOLO.cc变化**。

只重新编译YOLO.cc一个估计器翻译单元，复用其他全部原对象和原无窗口入口对象，再链接新库/程序。私有OpenCV和系统4.2均未重建或修改。`ldd`及短运行进程maps确认新程序加载新compat库和既有OpenCV4.5.5，没有混用4.2。[构建与链接记录](audit/compat_build.json)。这是**兼容修复，不是SCI贡献，也不是字节级作者原版**。

## 3. 没有用“不崩溃”代替语义验证

对所有原语结果，以独立四邻域BFS核对前景连通域集合，先规范化标签，**不直接比较不同实现的标签编号**。SAUF的12个结果全部与BFS一致；默认成功返回的8组，修复前后**连通域集合、最大区域像素集合、最终二值掩码全部逐像素相同**。无前景时保留作者`largestLabel=0`的背景回退及随后80%清零，不把该背景叫作前景最大区域。最终掩码核查保留原最大label选择、7×7膨胀及>80%清零过程，没有另造门限。

还在评分前固定walking索引0、206、413、620、826，分别独立运行原版/compat作者YOLO::Detect，线程均1，网络、depth/5000、BGR和输入完全相同：**5对真实最终掩码差异像素全部为0**。非零像素数依次82438、33694、58264、69357、84002。[真实掩码结果](results/real_mask_comparison.json)。这些是直接检测输出，不是SLAM传播后的最终掩码或运动真值。

边界必须保留：[OpenCV4.5.5文档](https://docs.opencv.org/4.5.5/d3/dc0/group__imgproc__shape.html)说明SAUF有行优先标签顺序，其他实现不保证同序。等大最大区域时，按最小label解平局可能产生差别。本轮等大测试和上述五帧未发现差异，**不能承诺所有未来掩码或标签编号完全相同**。默认崩溃的4例也没有可用原结果可供逐像素等价声明；仅有SAUF对BFS的独立正确性证据。

## 4. 真实短序列与准确的新故障

相同walking关联的前12张连续真实RGB-D，原Freiburg3标定、BGR、depth/5000、同一无窗口入口、OpenCV运行线程1。使用**NGD-M0-compat**标识，运行前登记在[短运行冻结](results/short/frozen.json)，输出目录拒绝覆盖；没有复用上轮登记路径。

| 结果 | 实测 |
|---|---|
| 原生TrackRGBD完整返回 | **2 / 12**，stdout含Frame 0 end、Frame 1 end |
| 地图 | 创建map0，初始526点；没有后续重置日志，不认证完整生命周期 |
| 第三次调用附近 | SIGSEGV，time包装器返回139 |
| 过程成本 | 管理墙时3.758s；用户/系统CPU3.43/0.13s；峰值RSS503272KiB，约491.5MiB |
| 轨迹、ATE/1s RPE、有效轨迹覆盖 | **未导出 / N/A**；不拿两帧或启动耗时冒充整段结果 |

首次真实帧确已通过，不只是模型推理。但短运行没有合格完成，**完整walking预算0/1，未启动**，没有执行轨迹评价。逐帧公开状态未加钩子记录，不能宣称全部正常跟踪；只确认已记录的两次函数完成。

对同一12帧前缀仅做一次GDB复查，复现两帧返回后主线程SIGSEGV。新栈为：

```
Thread 1 / main: SIGSEGV
LabelingBolelli4C
 -> connectedComponentsWithStats
 -> Tracking::CreateMaskFromClusters
 -> Tracking::PredictCurrentMask
 -> Tracking::GrabImageRGBD
 -> System::TrackRGBD
```

[准确新栈](audit/compat_short_gdb.log)。首个相关作者调用是**src/Tracking.cc:4565**，该函数中唯一的`connectedComponentsWithStats(...,4,CV_32S)`。Release二进制无逐行debug信息，这个源码位置由已定位函数和唯一调用对应取得，未冒称GDB直接显示了行号。

故障从此前YOLO检测线程，转到主线程的mask传播构造调用，**仍是默认Bolelli4C路径**；现场检测线程正在DNN前向计算。该栈没有指向Frame初始化或优化器，也没有证据将其改写为YOLO共享输入/输出生命周期故障。但上游内存损坏是否完全排除仍UNKNOWN，不能仅凭栈断言整个系统只有这一类缺陷。

依照本轮“单点修复后若出现其他崩溃，只取准确栈、不连续改模块”的边界，**Tracking.cc未修改，没有替换其他调用或继续启动完整序列**。

## 5. 决策与唯一下一步

**FIRST_FRAME_PASS；SHORT_SEQUENCE_FAILED；BASELINE_NOT_QUALIFIED。** 已证明本机存在官方描述的低层缺陷，并验证一个局部兼容补丁；尚无完整轨迹或任何SCI方法收益结论。

**下一步唯一建议：另行限定把同一SAUF四连通兼容调用应用到已定位的Tracking.cc:4565，然后沿用短前缀→一次完整walking的顺序。** 这是同一底层兼容问题的另一调用点，不是新动态算法。本轮不自动实施，不改8连通、不修80%/roll、不开发M1/M2或增加序列。

原NGD428项源码、原核心库与旧二进制、旧报告/失败结果、主仓HEAD/status/diff及未提交源码复核保持不变，见[保护结果](audit/protection_after.json)；该证明限列出的10项保护文件、428项作者源文件和Git状态，未冒称重哈希所有历史数据。所有大构建/测试掩码在外置盘，新报告与紧凑记录独立保存。无新数据/模型下载、系统安装、ROS、训练或新后端。
