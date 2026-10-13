# 环境资格（启动前与运行后分开）

启动前：Ubuntu20.04/ROS Noetic；系统Python3.8与已安装NumPy/Matplotlib。
rospack确认nav2d_karto来自原Doc79 overlay；nav2d_navigator来自原catkin underlay；
Stage来自/opt/ros/noetic。Python ROS消息导入通过。roslaunch --nodes仅解析新launch、
不启动仿真，返回Stage/Operator/Mapper/Navigator/GetMap/robot_state_publisher/publisher。

继承原参数：扫描10Hz、180°FOV、901束、0–25m；0.626×0.505m碰撞机器人；
mapper MinimumTravelDistance1m、Heading0.52rad、loop搜索/接受参数保持原值；
Operator频率10Hz/max_velocity1.0；导航控制器仍原参数。本实验MoveTo goal请求0.25m/0.1rad，
三场景与所有策略相同。world运动上下限仍原p3at；实际频率/速度/TF与加载库以新回合记录为准。

隔离不需要重新编译。不安装新系统依赖。ROS master使用11481，日志/ROS cache全在新结果根。
原production与Doc79 mapper/lib的SHA已冻结；任务只读运行旧Doc79观测版，不替换任何旧二进制。
sha清单：environment_source_hashes.json、protected_input_hashes.json；原p3at参数保留，未注入压力噪声。

启动前测试不等于运行技术资格。只有新回合的GT/TF配对、水位、同步图、provenance、
原始时间与正常任务通过，才能写TECHNICAL_GATE_PASS。
