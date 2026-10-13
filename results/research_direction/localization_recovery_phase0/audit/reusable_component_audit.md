# 可复用组件审计（启动前）

资产来源为 `4746834`。主工作区两处未提交改动不复用、不提交。新worktree为
`/home/wcqw/ac-slam_doc81`；旧数据从未成为新工具的写入目标。

| 原路径 | 复用方式与关联 | 污染风险/最小调整 | 编译/新增依赖 |
|---|---|---|---|
| baseline/.../world/map3/{map3.png,p3at.inc,hokuyo.inc} | 原地图作为正常/重复结构物理环境，原机器人与180°激光 | 新world仅改变冻结起点，保留原odom_error、尺寸/碰撞/FOV；不使用地图GT操纵估计 | 无编译/无依赖 |
| baseline/.../world/map4,map7,map8 | 看过几何，未选作新试验 | 未提供25m视距内长平行墙的明确最小控制，因此只新增一个100m、内宽3.1m直走廊；不筛选多个地图 | 原生Stage矩形墙，无新软件 |
| dependencies/navigation_2d/nav2d_navigator、nav2d_operator | 原Nav2D MoveTo任务及避障 | 固定任务，不启动探索/TSP/path_planner；plan_time写新目录 | 原二进制只读复用 |
| /home/wcqw/ac-slam/doc79_ws/devel/{mapper,libMultiMapper,libOpenKarto} | 同步图导出、水位、provenance | 它是旧观测overlay，不替换生产Karto；新ROS master/日志/输出路径隔离，记录实际/proc/maps | 不重编译 |
| tools/.../doc79_sync_validation/driver.py（提交版本） | 继承扫描/GT/关键帧记录与同步边界导出 | 新驱动覆盖全部控制路径，不继承旧GT到达门槛；严格stamp TF，不用最新TF冒充同时间 | Python3.8/ROS现有依赖 |
| tools/.../doc80_offline_review/common.py、target_gt.py | 复核SE2、插值、0.2m外参经验 | 不调用旧run_all；新指标用初始静止规范，而非用全条/后段轨迹再拟合 | NumPy、Matplotlib已安装 |
| tools/.../continuous_revisit/runner.py、Doc79 runner | 参考fresh进程、正常停止、账本 | 不调用旧plan/run；新预算先登记，再启动，失败不自动重试 | 无新增依赖 |
| same_input_replay.py、stitch_probe_stream.py、se2_information.py | 不用于新实验 | 用户工作区改动保留；原H+C拼接、图J不作为新主指标 | 无 |

系统模式是**在线建图SLAM**（robot1立即ST_MAPPING），不是给定地图上的定位。
map3图像只用于Stage生成物理墙，未给Nav2D或Karto加载静态地图。

源码审查发现Stage的 `srand48(time(NULL))` 与显式 `odom_error` 不等同于TSP seed。
`p3at.inc` 明确加载 `[0.05,0.05,0.1,0]`；上游ModelPosition.Load直接读这组比例。
本轮不改变它；三个种子只控制事前登记的起点微扰，不能声称控制Karto数值分叉。
来源：[Stage Init](https://github.com/rtv/Stage/blob/master/libstage/stage.cc)、
[ModelPosition](https://github.com/rtv/Stage/blob/master/libstage/model_position.cc)。
上游master用于解释实现路径；实际系统误差还要从运行记录核查，不把master当已安装二进制逐字认证。
