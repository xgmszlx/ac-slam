# 新运行封装的资格失败：不是科学负结果

三次尝试均已保留；同一个冻结seed271001，属于技术资格尝试，不是三个独立科学样本。
各次run_state、日志、raw capture均不可覆写。没有一次创建phase_markers/episode_result/metrics科学端点。

| 尝试 | 根因证据 | 实际范围 |
|---|---|---|
| R0 | Stage worldfile.cc提示在新world目录找不到hokuyo.inc；clock查询超时 | 全部扫描/GT/TF/odom流0条，Stage没正确加载 |
| A1 | Stage加载成功，但TF树为/robot/odom→/robot/base_footprint；GetFirstMap status4 | 584条TF记录，无根话题扫描/GT；`-u`是模型名字前缀 |
| A2 | `-g`后原生数据出现，GetFirstMap成功；driver_failure为MoveTo unavailable | 有1648扫描/12760GT/12716odom，仍未进入任务 |

第二项通过实际TF与上游stageros main交叉核查：`-u`令use_model_names=true；`-g`令gui=false。
[官方代码](https://github.com/ros-simulation/stage_ros/blob/master/src/stageros.cpp)。
不能从这些错误推断Karto在走廊发生真实失败。

A2在12.32s总wall时间中，GT记录跨度1275.9个sim秒；bootstrap_clock读到613.7s，
driver停止时1322.7s。actionlib的连接等待设为30个ROS sim秒，不是30个wall秒。
因此无GUI运行的时间基准与原GUI流程不同，连接/TF可用性不能靠同样的ROS timeout认定。
尚未用额外仿真证明单一根因；**不能把“快时钟”写成所有TF异常的已证根因**。

A2扫描记录的map_base字段1648/1648均缺失；原生GT连续，扫描有最大26.7s的sim时间缺口。
即使跳过MoveTo等待也不能可靠算主要定位误差。本轮不改用最新TF伪装历史TF，不放宽GT同步门槛。

R0关闭launcher后发现一个自己的Stage子进程残留（PID74202，cmdline指向本结果根），
只对该确切进程发送TERM并核查已退出。最终无本任务ROS/Stage进程残留。
这属于新launcher生命周期缺口，不是用户原工作区故障。

## 当前封存与预算

原prereg、A1/A2独立协议及各自失败gate全部保留。预算3/15，baseline3/9，intervention0/6。
尚余12总尝试额度，其中基线至多6；**剩余额度不是自动启动许可**。
按A2预先声明的最后修复停止条件，停止新物理尝试，不继续修到通过。

## 唯一后续技术任务（未执行）

若用户确认继续，先做一个单独的outcome-blind、wall-clock pacing与readiness资格协议：
复用旧已证明可用的Stage GUI运行节奏或显式、可验证的wall节奏，不改变sim physics、Karto或误差指标；
在运动前确认clock、原生话题、完整TF、MoveTo连接，并量化同stamp TF/GT覆盖率；
对所有子进程做精确生命周期检查。一次资格失败就止，不开启新的科学路线或后端重建。
必须重新分配剩余预算/场景覆盖并冻结，不能直接调用已封存的R0/A1/A2 run命令补跑。
