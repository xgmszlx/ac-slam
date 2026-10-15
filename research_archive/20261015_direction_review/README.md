# 主动 SLAM 多轮选题与实验审查汇总

2026-10-15。此分支归档八个独立研究目录的报告、协议、分析代码和小型证据。**目前没有正式通过SCI方法立项的候选；最新决定是建议一次有上限的探索性实验，尚未执行。** 本次GitHub上传不构成新实验授权，也没有恢复任何停止分支。

## 最终状态

| 路线 | 最终决定 | 事实与证据边界 |
|---|---|---|
| 纯旋转主动回环 | **STOP_PURE_ROTATION_SELECTION** | 不恢复旧方向，不把技术修复/图信息变化当主动精度收益 |
| A：主动地图变化核验 | **STOP_ACTIVE_MAP_VERIFICATION_AS_PRIMARY** | 原系统定位错误污染成立，但正确定位＋持久变化下未复现目标冻结；被动定位已明显改善，剩余误差没有证明主动必要性 |
| B：实际有效观测收益 | **SCIENTIFIC_HYPOTHESIS_UNRESOLVED** | 六组核心配准不是主动SLAM；完整封装链的信号资格不足，不能把工程失败当科学假设失败 |
| 当前RTAB-Map自建封装链 | **FROZEN / TECHNICAL_QUALIFICATION=FAIL** | 旧扫描严格配对不足；新增诊断存在数值回归。最后一轮没有新的ROS运行，不再修复拦截或前端追踪 |
| C1：失跟后等待/主动恢复 | **NO_GO** | 2024已有主动恢复；两个关键全文仍缺，2025入口已找到但完整可运行资产未资格；有限补证结束 |
| C2：概率/反馈修正收益 | **NO_GO_FOR_METHOD_DEVELOPMENT** | Kim/Eustice、P-ALC、DA-BSP等已有强机制近邻；UncertaintyMap原生理想化假设与替换成本不利 |
| D1：停止前遗漏入口核查 | **RECOMMEND_BOUNDED_EXPLORATORY_TEST** | 新门槛G1—G4探索性通过，有保留；主动必要性、增益、新颖性仍待试验，不等于正式SCI立项 |
| D2：布局相关预测收益 | **HOLD** | 有表示限制线索，未证现实任务收益；LaMa模型/依赖成本不适合当前磁盘 |

以上是跨轮次的**最终汇总**，不覆盖旧报告。早期“建议A做资格验证”“下一轮B技术资格”等阶段性安排已被后续停止/冻结决定替代。所有研究证据状态为ANALYZED，没有宣称独立团队复验。

## 这几轮实际得到了什么

**1. 从广泛选题转向可证伪问题。** 初轮文献与平台审查确认：信息增益加权、概率乘收益、普通健康监控和反馈重规划已有直接前例。公开仓库、可以编译、复现论文和适合作方法基础是四件事，不能混用。

**2. A的toy没有支持复杂主动评分器。** 150条记录＝30个case×5策略。nearest、uncertainty、stable、discriminative正确分别12/30、12/30、3/30、0/30；passive为8/30。discriminative错误修改1828个cell，高于nearest的412。没有调参挽救；负结果保留。

**3. 原作者地图更新系统验证否定了当时的主问题资格链。** Stefanini公开ROS1代码名义运行成立，但不等于最终论文复现。原公开YAML阈值0.58、README 0.8、最终论文0.75/0.90不同，不能混用。S1定位偏差错误修改1251；S2正常定位＋持久变化没有目标冻结；S3错误修改609。被动重估使S1降为0、S3降为92。

**4. A残差不能继续包装为主动需求。** B1-S3最终830个错误＝92错误修改＋738未改变化；未改部分混合遮挡/未观测及提交证据不足。B0/B1虽同样输入506帧，实际分别处理33/31帧、共同处理stamp只有6个，不能把全部差异因果归于位姿重估。未完成后续主动任务损失证明，因而停止A主线。

**5. B遇到的是工程证据不足。** 旧正常任务283输入scan、217 OdomInfo、199严格配对，覆盖70.318%，低于预先90%门槛；66帧无OdomInfo不等于ICP拒绝，另18帧缺地图TF时间覆盖。已有25图节点、29约束和15地图快照，不等于全链信号可认证。604个binary错误cell混合表面、边界、unknown和融合误差，不能直接叫SLAM失败。

**6. 最终RTAB审查没有进行第三次ROS运行。** 共享slot/lockTry等丢弃通道有源码依据，但旧66帧的逐帧内部原因仍UNKNOWN。新ICP诊断最终六组控制有两组数值不等价，前置门关闭，新预算0/1。应停止当前封装投入，不能推断RTAB后端或整个硬件平台不适合SLAM。

**7. 新一轮接受适度增量创新，降低的是探索门槛，不是证据标准。** 八篇有代码论文筛选后，D1锚定《Estimating map completeness in robot exploration》，借鉴FUEL视点/可见性机制。拟议差异是停止前的有效观测证据状态与有预算核查；“CNN＋门检测”已被原作者建议，必须作为直接组合基线。该问题更准确属于Active Mapping，不能承诺位姿精度创新。

**8. 简单方法已有很强反证。** 作者已有CSV按序号离线重组281组：单次θ=.8错误首次停止23组；θ=.95为8组但无停止57组；相邻两张保存快照满足θ=.8为5组、无停止20组。保存快照间隔未认证，不等于线上连续两帧，不能据此计算真实等待成本。此结果要求D1先赢过时序确认、静态入口否决和最近安全补扫。

## 最新唯一建议

只建议下一轮讨论[D1最小协议](snapshots/active_slam_incremental_screen_20261014/protocol/D1_MINIMAL_EXPERIMENT.md)：既有Stage/Karto/导航，冻结CNN，最多1次技术启动＋8个科学任务；同场景、同底座、同成本比较原停止、强简单组合、最近补扫与证据覆盖核查。不训练、不引入新SLAM后端、不恢复旧12条任务。

如果简单基线已经充分解决、主动核查只有代理分数提升、成本匹配后收益消失、没有安全差异动作、固定预算不出现相关事件，或最近邻完全覆盖，则停止。有限预算没有触发问题应记检验能力不足，不能通过改地图/噪声/阈值制造失败。

## 各轮原报告与证据入口

| 轮次 | 原报告/状态 | 关键附件 |
|---|---|---|
| 初始定向审查 | [topic报告](snapshots/active_slam_topic_audit_20261014/REPORT.md) | [平台](snapshots/active_slam_topic_audit_20261014/PLATFORM.md)、literature与protocol |
| A/B比较 | [AB报告](snapshots/active_slam_ab_decision_20261014/REPORT.md) | [150条结果](snapshots/active_slam_ab_decision_20261014/data/A_run01/results.csv)、[汇总](snapshots/active_slam_ab_decision_20261014/data/A_run01/summary.json) |
| 作者代码验证 | [author报告](snapshots/active_map_author_validation/REPORT.md) | S0—S3/B1 evaluation、science/passive冻结协议、[近邻矩阵](snapshots/active_map_author_validation/NOVELTY_MATRIX.md) |
| 暂停的反馈准备 | [实际status](snapshots/active_slam_feedback_probe_20261014/status.json) | 原目录无REPORT.md；0次尝试，不虚构报告 |
| A残差/B资格 | [next报告](snapshots/active_slam_next_direction_20261014/REPORT.md) | [残差汇总](snapshots/active_slam_next_direction_20261014/results/A_residual/summary.json)、b_attempts/b_frozen |
| B最终技术审查 | [final报告](snapshots/active_slam_b_final_qualification/REPORT.md) | [283帧事件表](snapshots/active_slam_b_final_qualification/results/old_283/scan_events.csv)、[回归失败](snapshots/active_slam_b_final_qualification/results/final_core_regression/result.json) |
| C1/C2排重 | [anchor报告](snapshots/active_slam_anchor_selection_20261014/REPORT.md) | [近邻矩阵](snapshots/active_slam_anchor_selection_20261014/literature/NEAREST_NEIGHBORS.md)、作者源码审查 |
| 最新增量选题 | [incremental报告](snapshots/active_slam_incremental_screen_20261014/REPORT.md) | [八篇筛选](snapshots/active_slam_incremental_screen_20261014/literature/SCREENING.md)、[简单基线](snapshots/active_slam_incremental_screen_20261014/audit/author_stop_baselines.json) |

## 归档范围、复核与复现限制

`snapshots/`为选中文件的逐字节副本，没有修订冻结结论。报告保留原路径和历史命令；某些链接指向**仅本地保留**的bag、第三方全文/源码、构建树和日志，GitHub并非完整运行环境。历史启动脚本只供审查，不能因它们被上传就重新执行。

上传报告、近邻矩阵、冻结协议、分析/测试代码、诊断patch、150条toy结果、283帧事件表、小型汇总和自制图。未上传bag/db、扫描原始流、逐帧JSONL、构建产物/二进制、论文PDF/HTML缓存、作者源码/权重/数据集、包含无关工作区diff的保护快照。原件保留，没有清理或删除。

- [文件来源及排除清单](publication/source_inventory.json)：包含原文件SHA256，不等于未上传原始数据已公开。
- [冻结快照链接审计](publication/link_audit.json)：缺少附件链接如实列出，不改写原报告造成“已发布全部数据”的假象。
- [发布前验证结果](publication/verification.json)：完整性/关键数字/代码语法及有限单元测试；不替代SLAM复现。
- [主工作区保护复核](publication/workspace_protection.json)：HEAD/status/diff及原未提交文件未变。

只做无ROS的归档复核：

```bash
python3 research_archive/20261015_direction_review/publication/verify_archive.py
# Noetic环境下的已有独立单元检查；不启动master、Stage或ICP：
source /opt/ros/noetic/setup.bash
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 \
  research_archive/20261015_direction_review/snapshots/active_slam_b_final_qualification/tests/test_events.py -v
```

原作者CSV没有重新分发。离线停止基线若需重组，应从固定作者commit取约187KB的[原CSV](https://raw.githubusercontent.com/aislabunimi/exploration-aware/010e03248ed633e755c84dc4686c6d00e6bb23c8/Results/predictions_labelled_KTH%2BMIT_08.csv)，核对来源清单hash，另建输出目录执行；不要改写本归档快照。模型推理、原始ROS评价与正式实验仍未通过本次上传自动取得资格。
