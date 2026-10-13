# ALC-Screen 01 — 主动回环候选决策与方法必要性审计

`ALC_SCREEN01_REVISIT_DECISION_FEASIBILITY_AUDIT`
(`OFFLINE_RESEARCH_DIRECTION_SCREENING`) 的结果根。

- 基线：`4746834ffa44504443fd07214105fe850d6f94e6`（旧研究分支 `research/phase4c-formal`）
- 本工作区：`/home/wcqw/ac-slam_alc_screen`（独立 worktree，分支 `research/alc-revisit-screening`）
- 隔离：未启动 ROS/Stage/Gazebo，未修改 Karto/overlay，未触碰 Doc81 worktree
  （`/home/wcqw/ac-slam_doc81`，head `7db448ff` 全程不变），主仓库两个未提交用户文件
  的原 SHA 在运行前后一致（见 `audit/workspace_protection.json`）。
- 研究日志：`docs/research_log/81b_active_loop_closure_direction_screening.md`

## 结果（判决）

| 关卡 | 判决 |
| --- | --- |
| G1 TASK_HEADROOM | PASS（完整探索上下文）；当前 Doc79 局部探针无已证明任务收益空间 |
| G2 ACTION_CHOICE_SPACE | UNRESOLVED（有几何候选假设，但 0 条安全认证路线） |
| G3 NOVEL_METHOD_NECESSITY | UNRESOLVED（强基线未被证明不够用；前人覆盖度高） |
| A1 | A1_UNRESOLVED（本轮不投入） |
| A2 | A2_HYPOTHESIS_ONLY |
| 最终 | **C — ACTIVE_REVISIT_HYPOTHESIS_ONLY**（唯一条件性保留：A2 必要性探针设计） |

旧结论 `STOP_PURE_ROTATION_SELECTION` 保留；本轮不授权任何新采集、新 planner 或预测器。

## 目录结构

```
literature/  literature_matrix.csv, closest_prior_work_review.md,
             novelty_risk_assessment.md, *_integrity.json, acquisition_manifest.json
             （cache/ 为本地 PDF/文本缓存，不入库）
audit/       dataset_inventory.csv, data_provenance_matrix.csv,
             available_decision_states.csv, input_integrity.json, input_hashes.json,
             map_and_frame_audit.md, reusable_code_audit.md,
             workspace_protection.json, archived_document_inventory.csv,
             positive_control_raw_verification.csv,
             pre_state_bundles/<episode>/{A1,A2}.json（动作前决策 bundle；
             scans_pre.jsonl 本地留存，不入库）,
             test_results.json, offline_tests.log
analysis/    task_headroom_audit.csv, revisit_candidate_inventory.csv,
             local_path_candidates.csv, global_target_candidates.csv,
             baseline_score_comparison.csv, historical_constraint_value.csv,
             historical_constraint_edges.csv, actual_revisit_cost.csv,
             pre_state_proxy_conflicts.csv, whole_run_outcomes_and_cost.csv,
             whole_run_summary.json, formal_*.csv/json, native_RAL_utility_diagnostic.csv,
             legacy_loop_endpoint_diagnostic.csv, map_quality_audit.csv,
             independent_doc79_target_GT.csv, counterfactual_limitations.md,
             A1_A2_research_decision_matrix.csv, final_gate.json, screening_summary.json
protocol/    minimal_A1_prospective_plan.md, minimal_A2_prospective_plan.md
             （均为 DESIGN_ONLY / NOT_AUTHORIZED）
figures/     01_task_headroom, 02_graph_gain_and_task_error,
             03_candidate_geometry_only, 04_native_utility_and_actual_outcome (png+svg)
```

## 复现

```bash
cd /home/wcqw/ac-slam_alc_screen
export PYTHONPATH=/home/wcqw/ac-slam/catkin_ws/python
export PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
/usr/bin/python3 tools/research_direction/alc_revisit_screening/analyze.py
/usr/bin/python3 tools/research_direction/alc_revisit_screening/summarize.py
/usr/bin/python3 tools/research_direction/alc_revisit_screening/figures.py
/usr/bin/python3 tools/research_direction/alc_revisit_screening/run_tests.py
```

所有命令只写本结果根；不要运行旧 analysis 入口（可能写回旧实验目录）。
依赖：系统 Python 3.8 + 现有 `catkin_ws/python` 离线依赖目录
（NumPy 1.24.4 / SciPy 1.10.1 / NetworkX 2.8.8 / Pillow / YAML / Matplotlib）。

## 数据完整性

`audit/input_integrity.json`：登记的 1101 个旧输入文件全部未变（`all_unchanged=true`，
`missing=[]`），两个工作区与用户文件哈希见 `audit/workspace_protection.json`。
大体量原始文件（旧结果目录、laser 流、PDF 缓存）保持在本工作区/主仓库本地，
不因上传 GitHub 而复制或改写。

## 审查入口

`REVIEW_PACKET.md`（含 `INDEPENDENT_REVIEW_HANDOFF` 20 项 + Q1–Q8 回答）。
