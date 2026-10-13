# STATUS — ALC-Screen 01

State: **COMPLETE（离线筛选审计结束）** — 2026-10-13。

## 已完成

- 全量离线分析（无新仿真/ROS/后端重放/模型训练/生产 planner 修改）：
  - 45 条正式运行（map3/map8 各 15 完成 + Mexico 15 失败单列）独立重算 APE 与
    最终地图 F1；作者离线目标函数 45/45 精确复现保存路径；
  - Doc79 7 条可信原生运行：28 张同步图、独立重算四阶段 J_T、140 条历史目标·阶段
    GT 误差、逐边 provenance/端点核验；
  - 108 个旧主动动作缓存端点诊断（不包装为因果边增量）；
  - 3 个旧 Karto 阳性对照原始 JSON/g2o 复核。
- 文献审计：11 篇（矩阵 + 最近工作评述 + 新颖性风险评估），其中 10 篇获得全文或
  方法原文；LAEG 仅出版预览（如实登记）；Region v3/Retroactive 经 HTML 读取
  （PDF 获取失败如实登记）。
- 交付物齐全：`literature/`、`audit/`（含 `test_results.json`、`offline_tests.log`、
  `pre_state_bundles/`）、`analysis/`（含 `A1_A2_research_decision_matrix.csv`、
  `final_gate.json`）、`protocol/`（A1/A2 均为 DESIGN_ONLY/NOT_AUTHORIZED）、
  `figures/`（4 张）、根级 `README.md`/`STATUS.md`/`REVIEW_PACKET.md`。
- 测试：`run_tests.py` → **38/38 OK**（离线合同回归，含真实决策 bundle；
  变异输入仅作防火墙合同测试）。

## 判决（唯一）

`final_gate.json`：G1 PASS（限完整探索上下文）/ G2 UNRESOLVED / G3 UNRESOLVED；
A1_UNRESOLVED，A2_HYPOTHESIS_ONLY；**最终 C — ACTIVE_REVISIT_HYPOTHESIS_ONLY**。
不授权新采集、不开发选择器；仅保留 A2 必要性探针协议（12 条上限，需另行批准）。
旧 `STOP_PURE_ROTATION_SELECTION` 保留；旧 gate/CD/v14/F2 未修改；Doc81 未修改。

## 明确未做（避免误读）

- 未执行任何新 episode、未启动 ROS/Stage、未训练模型；
- 未为新历史簇编造 RA-L 评分（B1 只作原空间离线复现；B2 标 CONCEPTUAL_BASELINE_ONLY）；
- 移动候选安全可达性 **0 条认证**（缺动作前 occupancy，拒绝用 Stage 地图冒充在线输入）；
- 未生成任何新候选的反事实结果（`COUNTERFACTUAL_OUTCOME_UNOBSERVED`）；
- 未把旧缓存差分改写为 active success rate。

## 保护

`audit/workspace_protection.json`（before/after 一致）：主仓库 HEAD `4746834f` 与两个
用户未提交文件 SHA 不变；Doc81 worktree head `7db448ff`、status 空；本 worktree 仅
新增本任务的三条路径。禁止在上传后修改本结果根；如需修正，另立新根。
