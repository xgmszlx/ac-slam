# 最终技术审查交付

见 [REPORT.md](REPORT.md)。TECHNICAL_QUALIFICATION=FAIL，SIGNAL_PROVENANCE=INCOMPLETE，MAP_METRIC_VALIDITY/SCIENTIFIC_HYPOTHESIS=UNRESOLVED。

本轮没有ROS/Stage启动。不要自动运行scan_gate或加载icp_call_trace；真实ICP拦截数值回归尚未通过。预算仍0/1，前置门关闭。

只读离线命令：

```bash
cd /home/wcqw/active_slam_b_final_qualification
source /opt/ros/noetic/setup.bash
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/home/wcqw/ac-slam/catkin_ws/python:$PYTHONPATH
/usr/bin/python3 tests/test_events.py -v
# 输出目录必须是新的，旧结果不覆盖：
/usr/bin/python3 code/offline_events.py /home/wcqw/active_slam_next_direction_20261014/results/B_technical_02 results/old_283_review_new
```

sources/upstream为固定提交原包；catkin_ws/src为最终诊断副本；patches含两包的完整差异。prepare_source.py是最初机械补丁生成记录，后续onInit/CMake/export隔离改动以最终源码和patch为准，不应直接重新执行来覆盖最终副本。结果标记ANALYZED。
