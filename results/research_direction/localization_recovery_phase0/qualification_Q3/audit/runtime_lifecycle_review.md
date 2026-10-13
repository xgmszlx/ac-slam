# 限定进程生命周期

使用独占ROS master端口11481与Q3独立ROS_HOME/LOG_DIR；已有master或端口占用时不接管。
先原子预留唯一Q3条目，之后才允许启动master和Stage。原3条账本不更新，累计用独立reconciliation表达。

每个Popen及其子进程按PID+create_time登记；观察线程不接触SLAM图。
退出时对本次子进程发SIGINT，有限等待后仅对仍匹配身份的owned进程TERM/KILL。
不使用全局pkill/killall。ROS/导航失败保留readiness、动作topics、节点/服务、模拟与wall时间、日志。
独立master内的动作在driver失败时取消，不延长运行寻找科学正结果。

结束必须证明owned进程无残留、端口释放、记录文件关闭、worker已退出。
Dummy软件子进程退出测试不启动ROS/Stage，不消耗物理预算。
真实Stage与导航的生命周期证据只由唯一资格回合提供，不用单元测试替代。
