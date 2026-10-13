# Doc79/Doc81/Q3 启动差异

Doc79使用`cpp_solver/exploration.launch`，Stage无CLI flag，加载既有map3.world，GUI有效；
Doc81 R0/A1错误用-u（模型名字命名空间），A2用-g（无GUI高速）。Q3只用原绝对world路径、无flag，
图形环境通过xdpyinfo只读检查，不创建新的物理地图或改变噪声。

核心Mapper/Operator/Navigator及ros.yaml、mapper.yaml、operator.yaml、costmap.yaml、navigator.yaml
全部复用原文件；Doc79观测overlay不重编译。robot_state_publisher的30Hz和空tf_prefix恢复原launch设置。
StartMapping仍触发原GetFirstMap引导，MoveTo仍由原Navigator执行。

不运行与短资格任务无关的Explore/SetGoal/Graph-Based path_planner/TSP、已知全地图发布器、RViz
及GT转发工具，避免启动旧科学路线、产生旧输出或引入GT在线控制。这些不是SLAM/导航算法改动。
Stage world来自原目录，嵌套p3at→hokuyo和floorplan/bitmap同目录可解析；不复制或改写include。

先master、Stage/native数据/clock、核心节点与GetFirstMap真实连接，再StartMapping；
初始化结果成功、真实map-base链和MoveTo连接之后，才开始静止对齐与短目标。
所有readiness有单调wall-clock上限，不以固定sleep宣称通过。没有headless备用物理尝试。
