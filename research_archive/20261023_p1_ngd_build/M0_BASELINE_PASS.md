# P1 · M0 原生基线跑通（2026-10-23）

## 0. 结论：`M0_BASELINE_PASS`

`rgbd_tum_headless` 在 TUM `fr3_sitting_xyz` 前 120 帧上**完整跑完**（Frame 119 end → Shutdown），
退出码 0，输出 120 行位姿。P7-A（冻结版）评价：

| 指标 | 值 |
|---|---|
| 关联对 | 117 / 120（coverage_est 0.975） |
| ATE **对齐** rmse | **0.0132 m**（median 0.0083，max 0.0486） |
| ATE 未对齐 rmse | 3.3273 m（ORB-SLAM3 从原点起，属预期） |
| RPE(1 s) 平移 rmse | 0.0162 m |
| RPE(1 s) 旋转 rmse | 0.3785° |
| 关键帧 | 21 |
| 平均单帧处理 | 10.6 ms |

## 1. 打通 M0 的关键：OpenCV 4.5.5 的 4 连通缺陷

### 缺陷本体（已独立复现，与 NGD 无关）
`cv::connectedComponentsWithStats(..., connectivity=4, ...)` 在**同一进程内第二次调用时**
崩溃（SIGBUS/SIGSEGV），栈顶为 `LabelingBolelli4CParallel`。

最小复现（不带任何 NGD 代码）：
```
两次连续 connectedComponentsWithStats(m, ..., 4, CV_32S)  -> 第二次 abort
同图 8 连通连调 9 次 -> 全部正常
单次调用：4 连通与 8 连通给出相同连通域计数（n=1186）
CCL_DEFAULT 与 CCL_SPAGHETTI 两种 ltype 都会崩
单线程（OPENCV_FOR_THREADS_NUM=1）仍崩 -> 不是竞态
```

### 规避方式
NGD 有**两处** 4 连通调用，都必须改：
- `src/YOLO.cc`（YOLO 后处理）
- `src/Tracking.cc:4565`（`CreateMaskFromClusters` ← `PredictCurrentMask`）

改为 8 连通，并在源码里写明 `ENV_WORKAROUND`。原始文件保留为 `src/YOLO.cc.orig`。

### 这个变通的边界（必须随结果一起引用）
- 它**不是**算法改动，但**是**与原作者的运行不完全一致的行为差异；
- 因为 A/B/C 三组共用同一条 YOLO 与 mask 路径，**组间比较仍然有效**；
- 但**不能**把本次 M0 的绝对数值当作"官方 M0"的复现值，只能当作"本机环境下的原生基线"。

## 2. 走到这里之前失败过三次（全部保留）

| 尝试 | 失败点 | 处置 |
|---|---|---|
| 1 | cmake 卡在 `IPPICV` 下载（>5 min 无进展） | `-DWITH_IPP=OFF` |
| 2 | `cvNamedWindow` 抛异常（highgui 无后端） | `-DWITH_GTK=ON` 重编 OpenCV |
| 3 | 主工程 make 立即失败：无规则制作 `libDBoW2.so` | 先建 Thirdparty/DBoW2 与 g2o |
| 4 | SIGBUS @ YOLO::postprocess | 4 连通 → 8 连通（YOLO.cc） |
| 5 | SIGSEGV @ Tracking::CreateMaskFromClusters | 4 连通 → 8 连通（Tracking.cc） |

## 3. 下一个门：A/B/C 对照的前置

1. 冻结本 M0（二进制哈希见 `MANIFEST` 段）；
2. 采集**冻结的逐帧 mask**（现有 `frame_states.csv` 只有标量，无 mask）；
3. 实现 B（FAST/OctTree 前置剔除）与 C（后置补提取）；
4. 单测：空/满 mask、金字塔尺度映射、OctTree 前过滤的证据、A 组逐位回归。
5. 通过后才做 A/B/C 对照。

## 4. 产物身份

```
libORB_SLAM3.so        （见下方 sha256）
rgbd_tum_headless      （见下方 sha256）
```
0db4fb6bbccafb66560c957abbcaa5159b5d09db688220b89d93e672e92f8c5b  NGD-SLAM/lib/libORB_SLAM3.so
579c3f3888678fc5d38d23e369430a5e7bf08ed575e91e164f6fa883eb78bfb1  NGD-SLAM/Examples_old/Stereo-Inertial/rgbd_tum_headless
