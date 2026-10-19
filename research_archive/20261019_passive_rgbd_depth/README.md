# 被动RGB-D深度观测：4次真实运行与下一步

2026-10-19。**原生观测干预成立，单次简单基线有收益；尚无新方法原型资格。** 所有4次完整运行退出0，无丢失输出或地图重建。不是旧V3多表面方法验证，更不恢复旧主动/AMCL方向。

| 数据/条件 | 导出ATE m | 1s平移RPE m | 在线ATE m | 位姿覆盖 |
|---|---:|---:|---:|---:|
| fr1_desk B0 | 0.046584 | 0.045384 | 0.065174 | 573/573 |
| fr1_desk B1 | **0.016398** | **0.022727** | **0.024673** | 573/573 |
| fr3_large_cabinet B0 | 0.037390 | 0.029414 | **0.035814** | 984/984 |
| fr3_large_cabinet B1 | **0.031888** | **0.026612** | 0.037143 | 984/984 |

B1只将固定3×3局部深度不连续处的有效depth置0，保持RGB/ORB不变。真实Frame的81,596个逐帧目标观测均变成mvDepth=mvuRight=-1；首帧初始化地图点分别精确减少40和39。它确实作用于原生SLAM，不只改变边缘像素统计。

但没有逐点depth真值，不能把边界都标成错误观测。每条件只有1次，也不能排除异步优化与运行变异。cabinet导出ATE略改善而在线ATE略增加，两个结果均保留。固定边界删除本身不是SCI创新。

**唯一建议**：下一轮若获授权，仅补desk B0/B1各2次，总运行数到8；不调阈值、不自动增加序列、不写新优化器。用重复结果决定是保留简单方案还是降低A优先级，不能因单次改善就开发复杂方法。

B只做保存/重载/定位API静态检查：源码支持Atlas .osa和定位模式，但加载后创建新图，独立冻结地图query未认证。C仅完成近邻与成本检查，未搭建新系统。

- [完整报告](REPORT.md)
- [实际观测与全部指标CSV](results/summary.csv)
- [七篇最近邻矩阵](literature/MATRIX.md)
- [B/C实施边界](literature/B_C_FEASIBILITY.md)
- [下一轮唯一建议](NEXT_MINIMAL_ACTION.md)
- [复查与原始命令说明](REPRODUCE.md)
- [固定设计](protocol/design_frozen.json)、[4次运行台账](protocol/attempts.jsonl)

![完整轨迹与误差](figures/trajectory_error.png)

![原生ORB与深度边界](figures/native_depth_boundary.png)

本归档包含原样报告、配置、诊断补丁/代码、紧凑自生成轨迹和逐帧标量计数。原始RGB/depth/GT、下载包、编译产物、作者源码缓存和完整stdout留在本机；不是开箱即用的新SLAM发行版。源码中的原绝对路径保持，需按REPRODUCE恢复本机环境。`publication/inventory.json`记录原样副本hash；纯数值评价单元测试和归档核验不是独立科学复验。

上游ORB-SLAM3衍生源/补丁保持GPL-3.0约束，见LICENSE.ORB_SLAM3；TUM数据和图表来源见报告官方链接，不另行授予数据许可。旧历史见[2026-10-16收口](../20261016_stage_closeout/README.md)。
