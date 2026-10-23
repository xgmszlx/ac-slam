# P1 构建链与 M0 基线状态（2026-10-23）

## 0. 结论

**构建链全部打通**；**M0 基线尚未跑通**，卡在 NGD 的 YOLO 后处理里一个 OpenCV 段错误/SIGBUS。
这是**运行时缺陷**，不是编译问题，也不是模型文件问题。

## 1. 构建链（全部成功，可复现）

| 组件 | 结果 | 关键约束 |
|---|---|---|
| OpenCV 4.5.5 | ✅ 隔离安装到 `p1_ngd/opencv_install` | **必须 `-DWITH_IPP=OFF`**（否则 configure 阶段卡在 ippicv 网络下载，已实测 5 分钟无响应）；**必须 `-DWITH_GTK=ON`**（否则 highgui 无后端，`Viewer.cc:207` 的 `cvNamedWindow` 直接抛异常） |
| Thirdparty/DBoW2 | ✅ `Thirdparty/DBoW2/lib/libDBoW2.so` | 必须先单独构建；主工程 `make` 会因"没有规则可制作目标 libDBoW2.so"立即失败 |
| Thirdparty/g2o | ✅ `Thirdparty/g2o/lib/libg2o.so` | 同上 |
| Thirdparty/Sophus | ✅ (header-only) | — |
| 主库 | ✅ `lib/libORB_SLAM3.so` = `98eab51389c96b1e5ab5650bc0f064b27aaff1dd85afa91fa28fc9186efba898` | — |
| 入口 | ✅ `Examples/RGB-D/rgbd_tum` = `4ed3e5fdd36aaa284a14e6e00e739223f3f835775521866000f71ae8d704f5ae` | — |
| headless 入口 | ✅ `rgbd_tum_headless`（仅把 `bUseViewer` 改为 false） | 只改入口，估计器零改动 |

OpenCV 版本隔离已核实：`ldd` 显示 `libopencv_core.so.405` / `libopencv_dnn.so.405`
指向隔离目录，**未混入系统 4.2**。

## 2. 走过的两次弯路（已修正，保留记录）

1. **跳过 Thirdparty 构建**：直接 `cmake && make` 主工程 → 立刻失败于
   `没有规则可制作目标 ../Thirdparty/DBoW2/lib/libDBoW2.so`。
   官方 `build.sh` 的顺序（DBoW2 → g2o → Sophus → 主工程）是必需的。
2. **`rm -rf build` 丢进度**：第一次构建被中断后，重跑脚本会清空已有 56 个目标文件。
   正确做法是**在原 build 目录续跑 `make`**。

## 3. 当前的硬阻塞：M0 段错误

### 症状
`rgbd_tum_headless` 打印 `Images in the sequence: 120` 后 **SIGBUS / 段错误**，无轨迹输出。

### 回溯（gdb）
```
SIGBUS in cv::connectedcomponents::LabelingBolelli4CParallel<int,unsigned char,CCStatsOp>::operator()
  ← cv::connectedComponentsWithStats
  ← ORB_SLAM3::YOLO::postprocess
  ← ORB_SLAM3::YOLO::Detect
  ← ORB_SLAM3::YOLO::Run          (YOLO 工作线程)
```

### 已排除的原因
| 假设 | 检查 | 结论 |
|---|---|---|
| 视图器 GTK 线程崩溃 | 关掉 viewer（headless 入口） | **仍崩**，排除 |
| OpenCV 并行标注线程竞争 | `OPENCV_FOR_THREADS_NUM=1 OMP_NUM_THREADS=1` | **仍崩**，排除 |
| 模型文件截断 | 与 zip 内条目逐字节比对：coco.names 625、cfg 9700、weights 3650764 **全部一致** | 排除 |
| 混用系统 OpenCV 4.2 | `ldd` 核实为隔离的 `.so.405` | 排除 |

### 尚未排除
- `readNetFromDarknet` 对该 cfg 的解析是否完整（未遂的探针程序因链接到系统 4.2 而未跑成，
  我的 g++ 命令行里 `pkg-config` 取了系统 4.2，需显式把隔离 include/lib 放在最前）。
- OpenCV 4.5.5 的 Bolelli 并行标注在特定输入尺寸下的缺陷。

## 4. 建议的下一步（按成本排序）

1. **修正探针**：显式 `-I<isolated>/include/opencv4 -L<isolated>/lib` 放在系统路径**之前**，
   打印 `getLayerNames().size()` 与 `forward()` 的输出维度，判断是模型解析问题还是标注函数问题。
2. 若属 OpenCV 4.5.5 缺陷：试 OpenCV 4.5.4 或 4.6（darknet 导入器与标注实现都变过）。
3. 若属该 cfg 的解析问题：考虑用 NGD 作者同一版本的 OpenCV（`Dependencies.md` 里可能写明）。

**在 M0 跑通之前，不做任何 B/C 实现**——否则无法建立"未修改算法"的基线。
