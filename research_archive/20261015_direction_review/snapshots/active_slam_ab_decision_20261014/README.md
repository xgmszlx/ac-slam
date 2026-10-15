# 单一 A/B 审查交付目录

唯一综合报告：[REPORT.md](REPORT.md)。最近邻矩阵、运行数据、图表、源码和失败日志均是报告附件；没有建立两个完整工程项目。

首次冻结输出：`data/A_run01`、`data/B_core_run01`。复验应使用新编号，禁止覆盖首轮结果。本目录的Python使用已有NumPy、SciPy和matplotlib；没有安装依赖。

```bash
cd /home/wcqw/active_slam_ab_decision_20261014
python3 code/map_probe.py run --out A_independent_rerun01
g++ -std=c++14 -O2 code/registration_probe.cpp -o code/registration_probe \
  -I/opt/ros/noetic/include/rtabmap-0.21 -I/usr/include/eigen3 -I/usr/include/pcl-1.10 \
  $(pkg-config --cflags --libs opencv4) \
  -L/opt/ros/noetic/lib/x86_64-linux-gnu \
  -Wl,-rpath,/opt/ros/noetic/lib/x86_64-linux-gnu -lrtabmap_core -lrtabmap_utilite
python3 code/run_registration_probe.py --out B_independent_rerun01
python3 code/check_artifacts.py
```

`check_artifacts.py`核查的是首轮输出及旧目录保护。A重跑默认会重新生成同名汇总图；首轮图的冻结副本位于`figures/frozen_run01`。B绘图程序`code/plot_b.py`读首轮输出。复验前应明确输入/输出和图表版本；同一研究员再次运行不自动等同独立复验。

`sources/`保留成功/失败获取与作者代码片段，含SHA及HTTP状态。论文版权、源码许可证归原作者；此目录没有发布到GitHub。
