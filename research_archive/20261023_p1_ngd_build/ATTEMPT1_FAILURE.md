# P1 构建尝试 1 失败记录（2026-10-23）

## 现象
`cmake ../opencv_src` 在 `IPPICV: Download: ippicv_2020_lnx_intel64_20191018_general.tgz`
处**停滞 >5 分钟**，`cmake.log` mtime 不再更新，cmake 进程仍存活。

## 原因
OpenCV 的 IPPICV 依赖在 configure 阶段**从网络下载**预编译归档。本机网络受限/不可达时
cmake 会长时间阻塞而非快速失败。

## 处置
1. 用 `SIGTERM` 终止 `lock.py run` wrapper（PID 27582），
   验证锁的**信号转发**在真实场景下生效：cmake 子进程随之退出，`BASELINE_BUILD` 释放。
2. 重新配置时加 `-DWITH_IPP=OFF`，绕开下载。
3. 原始 cmake 日志保留为 `cmake_attempt1_ippicv_stall.log`，不删。

## 教训
OpenCV 从源码构建在离线环境不是"可选项"问题，是**默认会卡住**的问题。
任何后续 OpenCV 构建都必须显式关闭 IPP（以及 ICV/FFMPEG 等带下载的组件）。
