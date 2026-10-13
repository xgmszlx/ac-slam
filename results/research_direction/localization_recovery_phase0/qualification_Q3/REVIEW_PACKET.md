# Q3 独立审查包

## Material Passport

任务DOC81_Q3_RUNTIME_AND_TIMESTAMP_QUALIFICATION；AI辅助封装修复、取证与技术执行。
仅依据当前仓库、A2原raw与唯一新资格回合；不是算法/科学结果，不声明独立人工复现已完成。
参考HEAD c0f5d0d475ce015283522b191e81a268c38438c0，新结果与工具全在Q3目录。

## 判决与关键事实

QUALIFICATION_PASS；独立附加OLD_SCIENTIFIC_HYPOTHESES_UNRESOLVED。

| 资格 | 真实证据 |
|---|---|
| Stage/原生话题 | 原map3.world、无-g/-u，资源无错误，Stage/scans/GT/odom可用 |
| clock | 232条，23.1sim秒/23.099915wall秒，严格单调，比例1.000004 |
| 初始化/MoveTo | GetFirstMap状态3、完整map链、实际actionlib连接、MoveTo状态3 |
| 历史时间TF/GT | 资格77/77、任务53/53，均100%；无latest兜底、无seq缺口 |
| 对齐 | 初始化完成13.7s，固定静止15.8–17.8s，21对，残差0m，任务18.2s开始 |
| 短运动 | 预定相对2m，离线GT净位移2.173m；没有用GT生成或终止目标 |
| 有效测量 | technical_pose_error.csv 77行，估计来自对应时间在线TF，不是最终graph反推 |
| 清理 | 16个owned PID/create_time身份全部退出、端口释放、文件关闭 |
| 保护 | 163项旧文件及依赖哈希不变；原postmortem另有141项检查一致 |
| 次数 | Q3唯一一次，累计4/15、基线4/9，不进入科学统计 |

## A2 原因：已证实与未证实

完整map→offset→odom→base_footprint→base_link链已证实；不是根本没有map TF。
793/1648扫描具有原始精确TF链；252时间范围外，603跨度>0.15s。原在线结果全缺失，
所以“链不存在”被排除。高时钟速率、接收延迟超过原10s cache、阻塞扫描回调和记录背压
是有根据的机制线索，但A2没有scan收到/查询异常日志，无法逐条唯一归因。
Q3同时修复多个封装条件，成功不是单因素因果消融，不能宣称已隔离唯一根因。

## INDEPENDENT_REVIEW_HANDOFF

1. 原A2取证：A2_tf_edges.csv、A2_scan_tf_availability.csv、A2_tf_coverage.json与forensics.md。
2. 启动前冻结：protocol/Q3_qualification_preregistration.json、Q3_qualification_hashes.json、
   protected_pre.json、native_Q3.launch；25新+16旧离线测试日志。
3. 不放宽标准：动态TF跨度≤0.15s，GT括夹≤原0.15s，至少原90%覆盖，无外推/latest替代。
4. GT隔离：driver只序列化；analysis子进程从关闭的静止窗口文件离线计算并冻结变换，
   导航只用估计TF/预定2m/action状态。核对对齐event wall时间<goal wall时间。
5. 数据身份：原232scan与232显式TF评价记录逐index/seq/stamp/stamp_ns一致，
   查看audit/independent_postflight.json和本地raw SHA。
6. 实际版本：本地raw/loaded_mapper_libraries.json确认mapper executable hash与原Doc79一致；
   未重编译生产或observer后端。mapper_params及核心节点/动作topics在ros_diagnostics.json。
7. 生命周期：process_states_before_cleanup、process_cleanup、raw_close_report、最终端口复核。
8. 预算：原protocol/budget_ledger.json仍3条、原SHA不变；新physical_attempt唯一一条，
   reconciliation明确4总/4基线，不把Q3改称科学健康对照。

## 边界与唯一下一步

一次正常环境短资格，不证明多seed数值重复性、长任务误差、真实退化或恢复收益。
日志中的原URDF root inertia/KDL与pre-Hydro costmap提示仍存在，未影响十二项通过；未为美化日志修改。
不创建主动恢复方法、预测器、科学确认性结论或Doc82。

原方案无法在剩5基线名额完成3健康+3走廊。唯一建议：另拟清楚公开的**探索性筛选协议**，
保留旧4次消耗，明确是否增加新预算及比较范围，交用户确认；本轮不启动、不擅自扩大预算。
