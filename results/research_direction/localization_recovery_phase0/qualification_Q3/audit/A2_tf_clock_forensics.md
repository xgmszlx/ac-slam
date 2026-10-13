# A2 TF_AND_CLOCK_FORENSICS

本阶段没有启动ROS master、Stage或导航。读取已登记SHA256的A2原始流；输出只在Q3。
旧A2不升级为科学episode。重现命令：

```bash
/usr/bin/python3 tools/research_direction/localization_recovery_phase0/qualification_q3/forensics.py
```

## 真实TF链与严格可重建性

原始/tf确有`map→offset→odom→base_footprint→base_link→base_laser_link`，不是假设的帧。
map/offset的时间范围67.8–1322.7s；base相关动态边47.7/47.8–1322.8s。
逐边次数、频率、最大缺口、接收ROS时间与header差、scan范围重叠在A2_tf_edges.csv。

1648条扫描42.6–597.1s，在线map_base全缺失。严格SE(2)重建结果：

- 793条（48.1189%）：完整链各边均有该精确时间戳，未借用最新TF。
- 252条：查询时刻在完整链的记录范围外，不能外推。
- 603条：缺少精确样本且至少一边插值跨度>0.15s，拒绝。

有效重建的插值跨度和查询时间误差均为0；没有使用GT补链。
重复TF采用先收到的同edge/stamp，与TF2重复数据拒绝相符；不同值冲突数为0。
这是原raw的技术取证，不是对全部扫描的轨迹“补齐”。A2仍无任务端点，也不足90%覆盖。

因此排除A“map链根本不存在”。一部分是B“时间支持不足”；对793条离线可重建却在线失败的
扫描，C“回调查询时机/缓存状态”是合理机制，但A2没有scan_received_wall_time及异常明细，
不能将每条失败唯一分为查询过早、过晚或调度背压。数据缺口必须保留。

## 时钟、缓存和初始化证据

整个attempt为12.320118wall秒，而GT记录跨度1275.9sim秒，二者比值103.56为保守跨窗口比值，
不是从同一Stage callback测得的精确速度。完整ROS日志的wall/sim范围另见A2_clock_forensics.json。
bootstrap_clock=613.7s；GetFirstMap goal=945.9s、result=996.6s；driver失败=1322.7s。
扫描记录全部早于bootstrap截止，也全部早于显式导航初始化动作。这显示记录背压/生命周期问题，
不是一个完成30m任务的结果。

base相关TF接收ROS时间-header的中位数17.5–17.6s、峰值124.4–124.5s；Mapper两边中位数约3s，
最大缺口11.6s。Noetic TF默认缓存10s；旧扫描回调串行做三个阻塞等待，在高速时钟下时间支持
会被淘汰、等待预算会迅速耗尽。Mapper日志还直接出现past-extrapolation/skipping scan。
但没有observer逐查询异常记录，不能声称“单一根因已证实”。

已安装`actionlib/action_client.py:589–631`：超时截止由`rospy.get_rostime()+timeout`决定，
循环`time.sleep(0.01)`。所以`Duration(30)`是30sim秒，不是30wall秒；不能证明服务器不存在。
机器人1在MultiMapper构造时即ST_MAPPING，map链可早于StartMapping存在；StartMapping调用的是
Navigator的GetFirstMap引导运动。不能把“初始化前没有map TF”作为本次发现。

旧analysis在bootstrap_clock之前取对齐，与要求的初始化后静止窗口不一致。
无论旧时间点有无TF，Q3均显式冻结初始化后的静止段，不读取运动后的GT重拟合。

主要本地源码：tf/listener.py、tf2_ros/buffer.py、actionlib/action_client.py；
仓库MapperNode.cpp、MultiMapper::publishTransform、RobotNavigator::receiveGetMapGoal。
