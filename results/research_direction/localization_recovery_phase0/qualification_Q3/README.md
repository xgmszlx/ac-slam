# Doc81-Q3：最后一次有限运行资格

任务DOC81_Q3_RUNTIME_AND_TIMESTAMP_QUALIFICATION，仅技术资格。
工作区/home/wcqw/ac-slam_doc81，branch research/localization-recovery-phase0；参考c0f5d0d4。

**唯一物理回合已经完成：QUALIFICATION_PASS。禁止重跑、自动重试或续跑科学矩阵。**
附加OLD_SCIENTIFIC_HYPOTHESES_UNRESOLVED。旧R0/A1/A2及原3次预算记录均原样保留。

## 结果入口

- results/qualification_status.json：十二项通过条件，全部true。
- results/readiness_report.json：每阶段的模拟/wall时间和真实readiness。
- results/clock_pacing_report.json：23.1sim秒/23.099915wall秒，比例1.000004。
- results/tf_coverage_report.json：资格77/77、任务53/53严格GT/TF配对，覆盖100%，无scan seq缺口。
- results/gt_alignment_report.json：初始化13.7s，静止15.8–17.8s，21对；18.2s时先冻结再发送任务目标。
- results/navigation_report.json：原MoveTo成功，预定相对2m目标；离线GT净位移2.173m。
- results/technical_pose_error.csv：77行在线估计/同时间GT的有效误差，**不作为科学健康对照**。
- results/process_cleanup_report.json：28.900wall秒完整尝试，16个owned身份全部退出，端口释放。
- results/budget_reconciliation.json：累计4/15、基线4/9；剩11总、5基线、6干预。
- audit/independent_postflight.json：独立raw SHA、身份、时序、实际加载mapper和清理复核。

原3次账本不修改；protocol/physical_attempt.json是Q3唯一条目，引用原账本SHA，
与其合并核算而不是复制一套不扣预算的运行。Q3不冒充科学正常样本。

## 离线复核命令

```bash
cd /home/wcqw/ac-slam_doc81
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m unittest discover \
  -s tools/research_direction/localization_recovery_phase0/qualification_q3 -p 'test_q3.py' -v
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m unittest discover \
  -s tools/research_direction/localization_recovery_phase0 -p 'test_phase0.py' -v
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 tools/research_direction/localization_recovery_phase0/postmortem.py
```

源码在tools/.../qualification_q3/；取证工具forensics.py只读取原A2并写Q3派生审计。
历史命令`runner.py freeze/run/report`记录运行实现，**不是封存后的续跑命令**。
run的单一原子reservation会拒绝第二次尝试；不要删除这个标记。

## 原始数据与限制

raw/和runtime/仅本地，15个主要原始文件4,281,705bytes，逐SHA在audit/local_only_capture_manifest.json。
包含原始scan身份和ranges、GT、TF、odom、控制、clock、初始静止输入、日志及实际mapper maps。
原A2的扫描未修改；793条严格可重建仅技术取证，不补成科学轨迹。

这里只证明一次原GUI正常环境短任务可运行/可测量，不能证明长任务、走廊、跨seed或恢复有效。
没有旧科学假设结论。原3健康+3走廊需6次，剩5个基线名额不足；后续必须另拟探索性协议，
公开旧4次消耗与新预算，交用户确认；不自动扩预算，不启动Doc82。
