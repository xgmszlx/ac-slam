# GT与坐标审计：预先约定

激光在base前方0.20m，Stage world `hokuyolaser(pose [0.2 0 -0.2 0])`，
与Doc80独立验证一致。实时评价使用map→base与Stage GT base，不把laser pose直接比较base GT。
同步图节点仍是map→laser；若使用节点需要右乘[-0.2,0,0]。

每条新episode：记录首次初始化前的静止段，用最早可正确配对的map-base/GT-base pose固定
一个SE2规范；**不在任务后或恢复后再拟合**。该静止段必须发生在StartMapping运动之前，
至少两个正确配对样本，静止规范残差不能超过3cm。GT仅用于离线评价及只读观测记录。

扫描stamp查询精确TF；查询失败记录None，不用ros::Time(0)的新位置伪装历史位置。
GT x/y线性插值，yaw沿最短角插值，括夹最大0.15s；任务配对不足90%停止科学判断。
scan、GT时间均须严格递增。1s RPE用1.000±0.025s可配对区间。

主要误差是在线估计误差，不是最终优化后轨迹的retroactive ATE。
同步边界图、水位、provenance只辅助机制判断；不把闭环日志或边数当准确度改善。
控制路径是map TF + 固定路线 + MoveTo状态；GT没有进入目标、触发、取消或到达判断。
