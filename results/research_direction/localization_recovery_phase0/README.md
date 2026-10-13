# Doc81：定位退化与恢复可行性

独立worktree `/home/wcqw/ac-slam_doc81`，分支 `research/localization-recovery-phase0`；
基线 `4746834ffa44504443fd07214105fe850d6f94e6`。原工作区及Doc76–80只读保留。

本轮不是纯旋转选向续作，不实现正式方法。先检验原Karto/轮式机器人在固定任务中
是否有真实定位退化；最多9次基线、6次干预，失败也扣预算。已有Doc79观测二进制
以隔离运行环境只读复用，没有替换或重编译生产后端。

种子只生成预先冻结的起点x/y±3cm、heading±0.01rad微扰。明确不保证Stage调度或
Karto内部数值确定性，也不把旧TSP seed冒充物理seed。保留原Stage显式odom_error；
不加噪，不破坏基线。

```bash
cd /home/wcqw/ac-slam_doc81
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m unittest discover \
  -s tools/research_direction/localization_recovery_phase0 -p 'test_phase0.py' -v
/usr/bin/python3 tools/research_direction/localization_recovery_phase0/runner.py prepare
/usr/bin/python3 tools/research_direction/localization_recovery_phase0/runner.py run
/usr/bin/python3 tools/research_direction/localization_recovery_phase0/runner.py analyze
```

`prepare`只允许一次；`run`保留已完成记录，从未启动条目继续。失败或中断不会自动重试、
不会覆写原attempt。ROS master独占11481端口，不接管主工作区ROS进程。
每次启动Stage之前预算已原子登记。健康3回合用于校准阈值，阈值只创建一次且在退化场景前冻结。
GT仅在离线误差计算和只读记录中使用；Nav2D的控制只依赖估计位姿与固定路线。

原始LaserScan、GT、TF、odom、控制、provenance和日志留本地并登记SHA256。
核心表、协议、代码、关键图与审查包可提交版本管理。未知和未执行阶段不伪造结果表。

## 封存状态（2026-10-13）

R0、A1、A2均在资格阶段失败，3次尝试全部计入baseline预算；没有主要科学端点。
现有`prepare/run`命令仅展示原运行方式，**不得将它们用于继续已封存套件**。
包括原`analyze`在内的历史套件命令可能覆写gate，均不应在封存后执行。
R0/A1/A2代码与协议不可修改后重跑。新的技术资格修正需要独立登记并经用户确认。
完整交接：[REVIEW_PACKET.md](REVIEW_PACKET.md)。原始资格数据约56.5MB，逐文件SHA清单在audit/。

仅离线复核封存证据（不导入ROS、不计算科学指标、不更新原gate）：

```bash
/usr/bin/python3 tools/research_direction/localization_recovery_phase0/postmortem.py
```

加`--write`仅重建三个post-hoc审计输出：qualification_attempts.csv、
postmortem_verification.json和runtime_library_manifest.json。该工具是停止后的取证代码，
不是原预注册运行源文件。GitHub不包含原始采集和PDF缓存；必须从本地SHA清单定位原文件后复核。
