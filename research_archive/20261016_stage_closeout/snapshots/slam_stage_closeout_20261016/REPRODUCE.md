# 复算范围

仅两个旧登记区间，27个原生sensor-update扫描。不得把命令改成新的SLAM运行。

1. ROS Python仅离线读取rosbag，不启动节点：

```bash
source /opt/ros/noetic/setup.bash
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 /home/wcqw/slam_stage_closeout_20261016/code/extract_two_windows.py
```

2. 使用已有Conda Python（numpy/scipy/pandas/matplotlib），旧native_probe.so只调用地图和观测函数：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/wcqw/anaconda3/bin/python3 /home/wcqw/slam_stage_closeout_20261016/code/analyze_two_windows.py
```

程序仅写本目录，重算会替换本轮衍生表/图；旧数据/源码/结论均只读。未启动PF/重采样/ROS服务。分析使用未经空间拟合的官方base_link GT、精确原生输出时刻、固定外参。区间端点来自旧连续误差，而图表仅显示区间内更新，不改原评价指标。

数值核验54组：独立numpy逐束加和与原生C++模型log评分最大差1.78e-15。GT的较高瞬时评分不证明实际PF包含GT附近粒子，也不证明全地图最优；图中全部有效束用于展示，统计只使用91个采样槽中的有效返回。
