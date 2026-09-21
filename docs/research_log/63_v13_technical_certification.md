# Phase v13-T Technical Certification

日期：2026-09-20
范围：技术认证；不进行新的 scientific endpoint 分析，不给出方向性结论。

## 0. Repository provenance and implementation inventory

[MEASURED OBSERVATION] 分支为 `research/phase4c-formal`；本轮开始与结束时 local
HEAD、remote branch HEAD 均为
`87185ca6dcf3e4f9219c6ea08ae193b61d9b68cf`。按任务要求，本轮没有 commit 或 push；
worktree 保留可审查的 v13-T changes。fresh collection 使用的代码内容 SHA 在运行前写入
`preregistration/v13T_preregistration.json`。

修改文件：

- `nav2d_karto/{CMakeLists.txt,package.xml,MultiMapper.h,MultiMapper.cpp}`：同步
  snapshot/count services，移除 background graph dump；
- `se2_information.py`：新增 v13 fixed-root estimator 并澄清 primary 定义；
- `test_confirmatory_v12b.py`：collection 后仅更新旧源码断言，使其验证 v13 synchronous
  service，而不是已经被禁止的 polling thread；该测试文件不在 collection code bundle。

新增文件：

- `v13_prefix_equivalence.py`、`v13_replay_publisher.py`、
  `v13_unified_replay.py`；
- `v13_target_selector.py`、`v13_technical_protocol.py`、
  `v13_history_qualification.py`、`test_v13_technical.py`；
- 本日志与独立结果根
  `results/realizability_pilot/p1_v13_technical_20260920/`。

[MEASURED OBSERVATION] `/usr/bin/python3` 全测试为 130 passed、4 skipped、0 failed；
4 个 skip 是缺少直接 `rospy` import 的既有 driver unit tests。`catkin_make --pkg
nav2d_karto` exit 0。真实 ROS smoke 中 35 条输入发布后 processed callback count 精确为
35，同步 graph dump 成功且 JSON 可解析。

## 1. Measurement/protocol architecture change

[CODE FACT] `MapperNode.cpp` 使用单一 ROS callback queue：主循环依次执行
`publishTransform()`、`ros::spinOnce()` 和 rate sleep。v13-T 新增私有服务
`/MultiMapper/get_processed_localized_scan_count` 与
`/MultiMapper/dump_pose_graph_now`。scan callback、count callback 和 dump callback
在同一 callback thread 串行执行。

[CODE FACT] `processed_localized_scan_count` 在每个 `/karto_in` callback 完整返回时
递增，含被 Karto 丢弃但 callback 已处理的输入。它不是 accepted-keyscan count。

[CODE FACT] v13 unified prefix-cut 顺序固定为：fresh master → fresh mapper → 等待
node/service → publisher 等待 `/karto_in` subscriber connection → 发布 exact stream →
publisher 正常退出 → 等待 processed count 精确等于期望数 → 同步 service dump。
后台 maintenance thread 不再读取或 dump graph；固定 sleep 不再作为 drain barrier。

[INFERENCE] 这改变的是观测和 protocol architecture，而不是 target、action、matcher、
planner 或 scientific hypothesis。同步 callback barrier 消除了“teardown dump”和“live
mid-stream dump”生命周期不同这一混杂。

## 2. Frozen v12b B/H2 forensic regression

[MEASURED OBSERVATION] 旧 B/H2 `combined_stream[:44]` 与 canonical prefix
byte-identical；stitch report 的两个 SHA-256 相同。

[MEASURED OBSERVATION] canonical standalone teardown graph 与两个 live-cut A2
preprobe graph 的 node count、state IDs、unique IDs、edge count、edge endpoint
insertion sequence 全部一致。两次 live-cut graph numerical exact equal；canonical 与
live-cut 最大差异为：node translation 0.004407 m、node heading 0.000015 rad、edge
translation measurement 0.003871 m、edge heading measurement 0.000012 rad、edge
covariance element 0.000504。

[INFERENCE] 旧 failure 分类为
`STRUCTURALLY_IDENTICAL_NUMERICALLY_DIFFERENT`，且证据与 lifecycle-dependent dump
差异一致，不支持 input prefix 不同这一解释。

[UNKNOWN] 冻结的旧 artifact 不能单独定位 teardown 中哪一个 Karto/OpenMapper 内部
操作产生了 numerical delta。

旧 v12b gate 保持 `CONFIRMATORY_EXPERIMENT_TECHNICALLY_INCOMPLETE`，不追溯纳入、
删除或重分类任何旧 block。旧 4.407 mm 仅为 forensic 描述，没有用于 v13 tolerance。

## 3. Unified-lifecycle repeatability and full-branch preservation

[MEASURED OBSERVATION] 在旧 B/H2 canonical input 上进行了 3 次 fresh-master、
fresh-mapper、同步 callback-cut prefix-only replay。3 个 all-pairs comparison 的
structural fields 与所有 dump 数值均 exact equal。因此 v13 numerical tolerance 按
预注册规则冻结为所有指标 0。

[MEASURED OBSERVATION] 同一旧 B/H2 A2 combined stream 的 unified branch regression
处理了 44 prefix + 542 suffix callbacks。final graph 保留全部 prefix `(state_id,
unique_id)`，并保持 prefix edge endpoint insertion sequence；未比较 suffix 优化后的
历史 corrected poses。

## 4. Block-local target-state definition

[CODE FACT] target identities 保持 `map3_grid_anchor_01` 和
`map3_grid_anchor_03`。每个 fresh canonical history 独立使用固定 waypoint；action
anchor 是 post-route-start 合法 scan 中距离该 waypoint 最近者，tie 使用更小 state
ID。target segment 是 anchor 周围最多 10 个 predecessor 与 10 个 successor 的连续
state-order slice。沿 segment 计算累计空间弧长并归一化，在固定 quantiles
`0.1, 0.3, 0.5, 0.7, 0.9` 取最近的五个不同 state，要求严格递增。

[INFERENCE] 该定义不构成 outcome-driven target replacement：target waypoint、segment
rule、quantiles 和 failure behavior 都在 fresh candidate 结果前冻结；selector 只读
history/prefix/route，不能读取 branch constraints、`J_T`、`Delta U` 或 action outcome。
不同 canonical-history block 不再被迫复刻相同 Karto state discretization，但同一 block
未来三个 action arms 必须共享同一五状态集合。

## 5. Immutable history qualification

[CODE FACT] candidate pools 在 fresh history 运行前冻结：Target A 为
81001--81008，Target B 为 82001--82008。每个 candidate 只有一次 history attempt，
无 reserve、无 runtime reordering/substitution、无 51/52/71/72 pool reuse。只有完整
8+8 pool 评估后，才按预注册顺序冻结每个 target 的 first-four eligible histories。

[HYPOTHESIS] 至少四个 candidate/target 能通过 history、五状态 selector、exact unified
prefix repeatability 和 provenance completeness gate。该假设是技术稳健性检查，不是
planner/backend 的 scientific hypothesis。

## 6. Primary estimator certification

[CODE FACT] v13 primary 定义为 fixed-first-pose、fixed-linearisation 的 local
linear-Gaussian joint marginal covariance，不是 exact nonlinear posterior，也不是以
Moore-Penrose pseudoinverse 作为 primary。五个 SE(2) target states 时
`J_T = -logdet(Sigma_T) / 15`。

[MEASURED OBSERVATION] 6 个 deterministic synthetic tests 全部通过：SE(2) analytic
Jacobian 对 finite difference、fixed-root reduced inverse 对 direct anchored Hessian、
新增 SPD constraint 的 covariance/information monotonicity、connected invertibility、
disconnected fail-closed，以及 exact-repeat zero-tolerance comparator。

## 7. Why v12/v12b are not pooled

[CODE FACT] v13 使用新的 callback barrier、统一 graph-cut lifecycle、block-local state
definition、immutable eligibility screen 和 fixed-root primary estimator。v12/v12b 没有
同时满足这些 measurement rules。

[INFERENCE] 将旧 blocks 与未来 v13 blocks 合并会混合不同 measurement protocol 和
target-state estimand。旧结果只能作为 forensic regression/descriptive prior evidence。

[INFERENCE] technical failure 只说明当前数据不能在预注册 protocol 下支撑可解释比较；
它不能自动解释为 planner hypothesis 或 Active-SLAM direction 的 scientific failure。

## 8. Final technical gate

[MEASURED OBSERVATION] 完整 16-history pool 已按 frozen order 结束：

| Target | Candidate | Eligible | Yield | Frozen first-four |
| --- | ---: | ---: | ---: | --- |
| A | 8 | 5 | 62.5% | 81001, 81002, 81003, 81005 |
| B | 8 | 7 | 87.5% | 82001, 82002, 82003, 82005 |

逐 candidate technical status（括号内为 `anchor; five state IDs`）：

| Target | Seed | Status | Anchor; target states |
| --- | ---: | --- | --- |
| A | 81001 | ELIGIBLE | 15; 12,15,17,20,24 |
| A | 81002 | ELIGIBLE | 15; 12,15,17,20,24 |
| A | 81003 | ELIGIBLE | 16; 13,16,18,21,25 |
| A | 81004 | INELIGIBLE: numerical non-exact | 16; 13,16,18,22,25 |
| A | 81005 | ELIGIBLE | 16; 13,16,18,22,25 |
| A | 81006 | ELIGIBLE | 15; 12,15,17,21,24 |
| A | 81007 | INELIGIBLE: numerical non-exact | 17; 12,15,18,21,26 |
| A | 81008 | INELIGIBLE: numerical non-exact | 16; 12,15,18,21,25 |
| B | 82001 | ELIGIBLE | 21; 14,17,20,24,28 |
| B | 82002 | ELIGIBLE | 21; 13,16,20,24,28 |
| B | 82003 | ELIGIBLE | 21; 13,16,20,25,28 |
| B | 82004 | INELIGIBLE: numerical non-exact | 21; 14,17,20,25,28 |
| B | 82005 | ELIGIBLE | 21; 13,16,20,25,28 |
| B | 82006 | ELIGIBLE | 20; 13,16,19,24,27 |
| B | 82007 | ELIGIBLE | 21; 14,17,20,24,27 |
| B | 82008 | ELIGIBLE | 20; 13,16,19,23,27 |

四个 ineligible histories 为 81004、81007、81008、82004，原因均为 repeated
same-input replay 未满足预注册的 exact/zero numerical envelope。它们的 structure、
history route 和五状态 selector 均通过；没有基于结果放宽 tolerance。

[MEASURED OBSERVATION] 16 个 candidates 均只生成一个 attempt，合计 48 个 prefix
replay graphs；16/16 的 required structural fields 在各自 3 次 replay 中 exact，12 个
eligible histories 的数值也 exact。所有 selector 均产生恰好 5 个 distinct、strictly
ordered states。没有 action branch、`pose_graph_after.json`、reserve substitution、seed
reuse 或 fresh scientific endpoint read。

[MEASURED OBSERVATION] raw `mapper.launch` SHA 在 repeat 间不同。逐行审计表明差异仅为
`pose_graph_dump_path` 与 `edge_provenance_path` 中预期不同的 repeat 输出目录；mapper
parameters hash、binary hash、git head 和所有 required structural signature fields exact。
该项分类为已解释 artifact-path variance，而不是 behavior/config mismatch。

最终技术 gate：

`V13_TECHNICAL_READY_FOR_CONFIRMATORY`

这只授权在审查确认后进入新的 v13-C collection；它不是 scientific support 或方向判决。

## 9. Remaining UNKNOWN

[UNKNOWN] 旧 standalone teardown 与 live callback-cut 之间 numerical delta 的确切 Karto
内部触发点仍未定位。

[UNKNOWN] 4/16 fresh histories 在相同输入、配置、callback lifecycle 下仍出现非零数值
repeatability 差异；其中 81007 达到 0.01 m，其余较小。TBB/solver scheduling 是可能解释，
但本轮没有证据确认原因。预注册 zero tolerance 已将这些 histories 排除，因此该 unknown
不污染冻结的 eight selected histories；它仍应作为 confirmatory collection 的运行期技术
监控项，不能当作科学结果解释。

[UNKNOWN] 本轮只认证 map3、当前 binary/config 和 history-prefix lifecycle；没有证明该
技术 repeatability 会自动外推到其他环境、backend 或硬件。
