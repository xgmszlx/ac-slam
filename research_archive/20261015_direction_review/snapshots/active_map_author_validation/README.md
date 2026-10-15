# 原作者验证工作区

主交付：[REPORT.md](REPORT.md)，决策REVISE；[新颖性矩阵](NOVELTY_MATRIX.md)。

旧目录只读，首轮输出保留。使用源码`57e83ec…`及公开YAML的0.58；README0.8和论文0.75/0.90不同。数值阈值不可混用。

复查已有数据（不要重复覆盖已存在的CSV）：

```bash
source /opt/ros/noetic/setup.bash
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/home/wcqw/ac-slam/catkin_ws/python:$PYTHONPATH
/usr/bin/python3 code/final_audit.py
python3 code/plot_results.py
```

物理回合入口`code/run_episode.py`使用私有master11531、原ROS1作者模块和owned清理，启动前登记台账。当前工作已经停止，不应为凑样本继续运行。若下一轮授权复验，先核查冻结参数、剩余预算和新输出编号；S0–S3每类目前仅一次。

B1是同scan的ROS节点replay，不是新增运动；B2仅是因果commit shadow，没有改地图后的定位反馈复现。报告详述这些边界。所有GT评价在`code/evaluate_ros.py`及最后的shadow评价块中，定位器不读GT。
