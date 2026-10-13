# 改动边界

基线c0f5d0d475ce015283522b191e81a268c38438c0。
所有实现新增于tools/research_direction/localization_recovery_phase0/qualification_q3/，
所有取证/资格输出新增于qualification_Q3/。旧Doc81文件、协议、失败门控、预算和源码均不修改。
没有生产二进制重编译，没有Karto参数、里程计、传感器、地图、导航约束变化。

最小功能改动：原GUI/world路径、wall-time action readiness、异步有界的scan/TF观测配对、
初始化后静止段离线对齐冻结、owned进程清理和独立累计预算核算。
不加入信息收益、退化评价、恢复动作、planner、predictor或新的科学统计。

源码及原依赖在物理启动前登记SHA；最终Git diff必须仅包含Q3和新增Q3报告。
软件测试覆盖用户16项资格要求，并重新运行原16项测试。所有旧hash与主工作区用户改动
在结束时再次核验。原始A2重建结果不回写原scan_stream或map_base。
