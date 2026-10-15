# 本轮交付

综合决策见 [REPORT.md](REPORT.md)，矩阵见literature/family1.md、family2.md。状态ANALYZED。

技术资格预算2次已耗尽；不要直接再次调用b_run.py，它会拒绝。没有科学实验资格，没有主动收益结论。新预算与正常资格复核属于下一轮工作。

只读重算命令（指定新的输出位置；该位置已存在时会拒绝，保留所有原记录）：

```bash
source /opt/ros/noetic/setup.bash
source /home/wcqw/active_map_author_validation/catkin_ws/devel/setup.bash
cd /home/wcqw/active_slam_next_direction_20261014
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/home/wcqw/ac-slam/catkin_ws/python:$PYTHONPATH
/usr/bin/python3 code/a_residual.py --output results/A_review_new
/usr/bin/python3 code/b_evaluate.py results/B_technical_02 --output results/B_review_new
```

首次运行时的日志在results/；失败解释在failures/。原始数据不删、不重索引、不覆盖。原90%门槛未调整。原作者buffer审计只导出count>0，语义补充见results/A_residual/semantics_and_subtypes.json。
