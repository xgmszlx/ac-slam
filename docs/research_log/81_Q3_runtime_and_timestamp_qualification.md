# Doc81-Q3：有限运行资格与同时间戳采集修复

2026-10-13，任务DOC81_Q3_RUNTIME_AND_TIMESTAMP_QUALIFICATION，TECHNICAL_QUALIFICATION_ONLY。
工作区/home/wcqw/ac-slam_doc81；branch research/localization-recovery-phase0；参考c0f5d0d4。

## 结论

**QUALIFICATION_PASS。OLD_SCIENTIFIC_HYPOTHESES_UNRESOLVED。**
本轮只启动一次Stage物理回合；原GUI正常环境的初始化、严格TF/GT采集、静止对齐、短导航
和进程清理全部通过。没有继续原矩阵、走廊、重复环境、恢复动作或Doc82。

这一结果修复的是我新增封装的技术缺陷，不能用于评价主动恢复或推翻任何旧科学判决。
原R0/A1/A2及旧预算文件、用户主工作区两处改动保留，旧Doc76–80无改动。

## 1. 原A2缺失原因

先完整读取已登记SHA的原/tf、scan、GT、odom、cmd及日志，未启动ROS/Stage。
TF实际有map→offset→odom→base_footprint→base_link→base_laser_link；“没有map链”不成立。

在不外推、最大动态TF跨度0.15s的严格SE(2)重建下：

| 原A2扫描 | 数量 | 技术解释 |
|---|---:|---|
| 精确时间完整TF链 | 793（48.12%） | 每条边有原stamp，重建时间误差0 |
| 超出完整链记录范围 | 252 | 不以最新TF补齐 |
| 插值区间过宽 | 603 | 拒绝跨度>0.15s |
| 合计 | 1648 | 在线map_base全部缺失 |

base相关TF接收ROS时间比header中位数晚17.5–17.6s，峰值约124.5s；原TF默认缓存10s。
Mapper两边最大记录时间缺口11.6s。阻塞扫描查询、高速clock和缓存/背压是可信线索，
但原A2没有scan_received_wall_time或查询异常明细，不能唯一分解“查询过早/过晚/淘汰”。

A2整个attempt12.320wall秒，GT跨度1275.9sim秒，跨窗口比例下界103.56；
已安装actionlib以rospy.get_rostime判断Duration(30)截止，不是30wall秒。
没有完整Stage同一callback的wall记录，不把上述比例当精确Stage速度。

原scan仅42.6–597.1s；bootstrap613.7s；GetFirstMap goal945.9s/result996.6s；失败1322.7s。
没有一个有效科学任务，严格重建不把原A2升级为科学episode。
机器人1可在显式StartMapping前已有map链；旧对齐截止仍不符合初始化后静止的目标时序。

## 2. 修复范围与冻结

所有工具新增qualification_q3/，所有结果新增qualification_Q3/；原源码与三次失败不修改。
启动前登记新协议/源码/原依赖SHA，25项Q3测试及原16项测试全通过。

- 直接使用原map3.world所在目录，嵌套p3at/hokuyo/floorplan与bitmap可解析。
- 使用已证明的GUI模式，无-g/-u；实测图形环境可用，无headless物理备用尝试。
- Mapper/Operator/Navigator参数、噪声、机器人/传感器/地图不变，Doc79 binary只读复用。
- 所有关键readiness用单调wall时限，action资格核验完整status/goal/cancel/result/feedback连接。
- 扫描原身份立即写入，非阻塞待配对队列容量200、超时2wall秒；观测TF缓存20sim秒、每边4096条。
- 动态TF只能原时间戳或已知区间≤0.15s插值；原GT≤0.15s、覆盖≥90%标准不变。
- 初始化后按odom确认静止，再封存2sim秒窗口；ROS-free离线子程序从该窗口冻结对齐。
- 导航从不读GT位置或对齐变换生成目标；失败取消私有master内动作，精确owned进程清理。

这不是后台读取mapper graph、后端迁移、阈值调整或planner修正。

## 3. 唯一回合的实际结果

episode NORMAL_GEOMETRY_Q3_QUALIFICATION；完整attempt28.8996wall秒。

| 项目 | 实测 |
|---|---|
| 原生scan与显式评价记录 | 232/232，身份index/seq/stamp/stamp_ns一致 |
| 记录clock跨度 | 23.1sim秒 / 23.099915wall秒，比例1.000004，单调 |
| GetFirstMap | 成功，初始化完成13.7sim秒 |
| 静止窗口 | 15.8–17.8s，21对，最大对齐残差0m |
| 对齐冻结/任务发送 | 两者ROS时间均18.2s，goal wall事件严格在冻结事件后 |
| MoveTo | 预定相对2m，状态3；离线GT净位移2.173m |
| 资格区间GT/TF配对 | 77/77，100% |
| 任务区间GT/TF配对 | 53/53，100% |
| 扫描缺口 | seq缺失0，最大stamp gap0.1s |
| 同stamp TF解决延迟 | 中位0.01145wall秒，最大0.02464wall秒 |
| 主要技术误差序列 | 77行有效在线估计/同stamp GT，未用最终graph反推或运动后拟合 |
| 清理 | 16个owned身份全部退出，端口释放，文件/worker关闭，无强制清理兜底 |

十二项A–L资格条件全部成立；不因局部节点启动或内部信息值宣布通过。
独立postflight检查15个本地raw文件SHA、所有scan身份、对齐时序、实际mapper hash与端口。
163项旧文件/依赖哈希不变，原postmortem141项复核仍一致。

仍有原URDF root inertia/KDL和pre-Hydro costmap启动提示，不影响本次资格；没有美化日志修复。
同时改变GUI、待配对回调和对齐时序的资格成功，不是确定唯一A2根因的单变量消融。

## 4. 预算及不能自动续跑的理由

原3条账本不可变；Q3在任何master/Stage启动前独立原子预留一次，引用旧账本SHA。
新账本是增量，不是绕开总额：累计4/15、基线4/9、干预0/6。
剩11总、5基线、6干预。Q3仅技术资格，不算科学健康样本。

**ORIGINAL_SCIENTIFIC_MATRIX_NOT_EXECUTABLE_UNDER_REMAINING_BASELINE_BUDGET。**
原3健康+3走廊至少需6次有效科学任务，5个剩余基线名额不足，不能把5次包装成6次。
本轮没有新的科学结论，更没有在通过资格后自动扩大预算。

## 5. 交付与唯一下一步

- [独立审查包](../../results/research_direction/localization_recovery_phase0/qualification_Q3/REVIEW_PACKET.md)
- [运行/封存说明](../../results/research_direction/localization_recovery_phase0/qualification_Q3/README.md)
- Q3协议、hash、前/后保护表，A2逐边/逐scan取证表，全部资格gate及预算核算。
- 本地raw15文件4,281,705bytes，逐SHA在Q3 audit/local_only_capture_manifest.json；不上传大型raw。
- 新源码：tools/research_direction/localization_recovery_phase0/qualification_q3/。

离线测试命令在README，结果25+16全部通过；不需要再次启动ROS。
这只证明一个正常环境短任务的技术可用性，不证明长任务、走廊、多seed稳定性、退化或恢复效果。

唯一下一步：**另拟公开记录历史4次消耗的探索性科学筛选协议，明确新的预算与覆盖范围，
交用户确认。** 不续跑封存旧方案，不开发方法，不训练模型，不启动Doc82。
