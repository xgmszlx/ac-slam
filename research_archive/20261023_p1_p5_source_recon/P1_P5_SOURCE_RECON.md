# P1 / P5 只读源码勘察结果（2026-10-23）

只读勘察，未编译、未修改任何上游源码。所有结论带行级证据。

---

# P5：**不需要编译** —— 冻结环境可等价恢复

## 0. 结论先行

上一轮我报"ORB-SLAM3 只有 `libORB_SLAM3.so`，Examples 可执行缺失"。**这个判断是错的。**
Examples 二进制存在，链接的正是冻结核心库。因此 P5 属于指令 §6.2 的**情况 A**：
原环境可等价恢复，**不需要 `BASELINE_BUILD` 锁**，`BASELINE_BUILD` 可全部留给 P1。

## 1. 证据

```
Examples/RGB-D/rgbd_tum            98,760 B   2026-10-15 10:47
Examples/RGB-D/rgbd_tum_headless   98,768 B   2026-10-15 10:56
Examples/RGB-D/rgbd_tum_trace             (同批)
```

`ldd rgbd_tum_headless` 解析到：

```
libORB_SLAM3.so => <src>/lib/libORB_SLAM3.so     (冻结核心库, 5,018,696 B, 2026-10-15 10:47)
libDBoW2.so     => <src>/Thirdparty/DBoW2/lib/libDBoW2.so
libg2o.so       => <src>/Thirdparty/g2o/lib/libg2o.so
```

- `find src include -newer lib/libORB_SLAM3.so` 返回空 → **源码不比库新，源码与被链接的库一致**。
- `CMakeLists.txt` 相对 `pristine_CMakeLists.txt` 只有两处差异：
  1. `find_package(OpenCV 4.4)` → `4.2`（适配本机系统 OpenCV）
  2. 追加 `rgbd_tum_trace`、`rgbd_tum_headless` 两个 target，并设
     `CMAKE_RUNTIME_OUTPUT_DIRECTORY=${PROJECT_SOURCE_DIR}/Examples/RGB-D`

## 2. 但仍需先做的是"实测等价"，不是"看起来一样"

二进制在 ≠ 能跑。P5 正式追加运行之前必须做一次**最小基线回归**：

- 用 `rgbd_tum_headless` 跑一段已知序列（少量帧），确认
  (a) 进程正常退出，(b) 输出轨迹帧数 > 0，(c) 轨迹坐标系与旧实验同口径。
- 与旧实验 `20261019_passive_rgbd_depth` 的已存轨迹比较**入口一致性**（不是比较 ATE 好坏）。
- 回归不过 → 转情况 B（新基线），不拼接旧结果。

**注意**：这一步是回归，不是重复实验，不能用它的数值做任何科学结论。

## 3. P5 状态

`technically_on_disk_ok` / `equivalence_not_yet_measured`。
追加运行仍须遵守原冻结协议（`B1_02 → B0_02 → B0_03 → B1_03`，不改阈值/ORB 数/初始化），
且必须先把预登记做成独立 commit。

---

# P1：`_mask` 是**死参数** —— 真正预剔除确实不存在（行级确认）

## 0. 结论先行

指令 §5.1 的六项勘察问到了核心，答案很干净：

> **`ORBextractor::operator()(image, _mask, ...)` 里的 `_mask` 在整个文件中只出现一次——
> 就是函数签名那一行。它不参与 FAST，不参与八叉树分配，完全不参与提取。**

所以 NGD 的动态处理是：**先按 1.5× 预算在含动态区的整图上提取，事后按 mask 删除关键点**。
被删除的那些特征**已经占用了八叉树分配预算**，静态区域拿到的只是剩余额度。
这正是 P1 假设的浪费，**且与 `ngd_method_opportunity` 审过的三个候选（异步 mask 时效 /
剔除后几何支持保护 / LK-ORB 协调）是不同的实验对象**。

## 1. 证据：1.5× 动态配额

```
Tracking.cc:596   mpORBextractorDyna = new ORBextractor(nFeatures*1.5, fScaleFactor, nLevels, fIniThFAST, fMinThFAST);
Tracking.cc:1285  mpORBextractorDyna = new ORBextractor(nFeatures*1.5, ...);
```
两处均确认：动态帧使用 `nFeatures × 1.5` 的提取配额。

## 2. 证据：`_mask` 不被使用

```
$ grep -n "_mask" src/ORBextractor.cc
1086:    int ORBextractor::operator()( InputArray _image, InputArray _mask, ...)
```
**仅此一处**（签名）。函数体内：

```
1097:  ComputePyramid(image);              // 无 mask
1100:  ComputeKeyPointsOctTree(allKeypoints);  // 无 mask
 826-856: FAST(mvImagePyramid[level].rowRange(...).colRange(...), ...)  // 无 mask
 877:  keypoints = DistributeOctTree(vToDistracteKeys, ...)             // 无 mask
```

`ComputeKeyPointsOctTree`、`DistributeOctTree`、全部 `FAST(...)` 调用**都不接受 mask 参数**。

## 3. 证据：删除发生在提取之后

```
Frame.cc:333   // Delete those ORB points that fall in Mask borders (Included by Berta)
Frame.cc:343   int val = (int)imMask.at<uchar>(mvKeys[i].pt.y, mvKeys[i].pt.x);
```
即对已提取的 `mvKeys` 逐点查 mask 并删除——**后置删除**，不是预剔除。

## 4. 对 P1 方案的含义

| 组 | 实现落点 | 是否需要改 `ORBextractor` 核心 |
|---|---|---|
| A 原生 | 现状 | 否 |
| B 真预剔除 | 在 `ComputeKeyPointsOctTree` 内把 mask 下采样到每层金字塔，作为 FAST 掩膜 + 只在有效区做 `DistributeOctTree` | **是**，需改核心并保证 A 组逐位回归 |
| C 后置补提取 | 在删除后按剩余预算在有效静态区再跑一次受限 FAST | 否（可在 Frame 层实现） |

- B 的最小改动点已定位到 `ORBextractor::ComputeKeyPointsOctTree`（781–877 行）。
- **必须**保证 A 组在 mask 全零输入下与原二进制逐位一致（回归门槛）。
- 金字塔各层 mask 需按 `1/fScaleFactor^level` 缩放，边界需按 `EDGE_THRESHOLD` 裁剪。

## 5. P1 阻断项（比预想的大）

**本机当前没有任何已构建的 NGD 二进制。** `find` 全盘无 `rgbd_tum`（NGD 版）等可执行；
9 个 `ngd_*` 归档目录里只有探针脚本与日志，没有构建产物。
NGD 源码只在 621 MB 的 `NGD-SLAM-a93a14c....zip` 中；**OpenCV 4.5.5 只有 tar.gz，未构建**
（系统 OpenCV 是 4.2，NGD 需要 4.5.5，二者 ABI 不兼容）。

因此 P1 的实际链路是：

```
解压源码 → 隔离构建 OpenCV 4.5.5 → 隔离构建 NGD（含 YOLO/onnx）
→ A 组回归（必须先于任何修改）→ 实现 B/C → 单测 → A/B/C 对照
```

这是一条**长链路**，且第一步（A 组基线回归）本身就依赖完整重建成功。
按指令 §5.1"勘察完成后不需要再次请求许可，自动编译"，我将在取得 `BASELINE_BUILD` 锁后推进；
但此处必须先记录一个风险：**OpenCV 4.5.5 从源码构建 + NGD 依赖（Eigen/Pangolin/onnxruntime）
是否能在本机无网络或受限网络下完成，尚未验证**。这不改变计划，只改变预期。

---

# 记录在案的两处自身失误

1. **上一轮"Examples 缺失"的判断错误**：当时的 `find -executable` 过滤条件把可执行文件漏掉了，
   据此得出的"需要重建"结论不成立。已在本文件中更正，并已实际核对 `ldd` 链接关系。
2. **进程隔离违规**：本轮第一次 P6 Stage 2 调用被工具超时终止，但 `timeout` 的孙进程未回收，
   导致后台 job 启动后**同时有两个 P6 实例**在跑（1424% + 979% CPU）。
   已按 PID 核对后终止较旧的一个，保留后台 job 的实例。
   教训：`timeout` 只对直接子进程生效；长任务必须一开始就用后台 job，且启动后必须回头核对实例数。
