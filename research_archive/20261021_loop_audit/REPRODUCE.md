# 复现说明（只读审计）

本目录不含 SLAM 运行，只含**复算脚本 + 表 + 报告**。所有输入都来自本仓库既有的历史归档，未修改、未覆盖。

## 1. 环境

- Python 3.11（Anaconda 环境已满足），依赖：`numpy`、`scipy`（仅 `analyze_*` 用 numpy；`evaluate.py` 的复算不在此目录重复实现）
- 无需 ROS、无需 OpenCV、无需 GPU
- 全部脚本默认路径写死为 `D:\py\_audit\ac-slam\research_archive`（Windows 本地审计副本）；在 Linux 上运行时改文件头部的 `BASE` / `ARCH` 变量即可

## 2. 输入（相对仓库根，sha256 见 `MANIFEST.json`）

| 用途 | 路径 |
|---|---|
| M2 在线/导出/关键帧轨迹 | `research_archive/20261021_ngd_region_prototype/results/M2/{Online,Camera,KeyFrame}Trajectory.txt` |
| M2 逐帧状态 | `research_archive/20261021_ngd_region_prototype/results/M2/frame_states.csv` |
| M2 原始日志 | `research_archive/20261021_ngd_region_prototype/results/M2/stdout.log` |
| M2 评价输出 | `research_archive/20261021_ngd_region_prototype/results/M2/evaluation/{online,exported}/` |
| M0 同上 | `research_archive/20261021_ngd_region_prototype/results/M0/` |
| M1 失败记录 | `research_archive/20261021_ngd_region_prototype/results/M1/failure_note.json` |
| 同条件基线 4 次 | `20261020_ngd_scientific_baseline/results/M0_05`、`20261020_rgbd_combo_e2e/results/S0`、`20261020_rgbd_deletion_ablation/results/S0`、`20261021_ngd_region_prototype/results/M0` |
| 图合并先例 | `20261019_depth_repeats/results/B0_03/` |
| 配置（4 份完全一致） | `*/config/bonn.yaml`，sha256 `972bc2bc…` |

GT（`groundtruth.txt`）**不在仓库内**，位于 Linux 机器的 `passive_rgbd_combo_20261019/e2e_20261020/data/rgbd_bonn_moving_obstructing_box/`，其 sha256 记录在各 run 的 `frozen.json` 中（`84d3420a…`）。本审计不重算 ATE/RPE，只读取既有 `metrics.json`/`ate.csv`/`rpe.csv`。

## 3. 命令

```bash
python scripts/analyze_loop.py       # 表：在线/导出相邻跳变、Online↔Exported 差、1s RPE 跨窗
python scripts/analyze_segments.py   # 表：分段 ATE（读 ate.csv）、导出轨迹跳变、导出 RPE 跨窗
python scripts/analyze_residual.py   # 表：导出→在线残差刚性检验、阶跃帧定位
python scripts/analyze_kf.py         # 表：关键帧边界与相对运动一致性
python scripts/analyze_kf2.py        # 表：关键帧步进 + Δt（用于折算 m/s、°/s）
python scripts/analyze_align.py      # 表：前后段刚体拟合残差、隐含坐标系差
python scripts/analyze_speed.py      # 表：关键帧链速度、与在线同区间对比
python scripts/scan_history.py       # 产物：tables/historical_loop_gba_audit.csv（22 运行）
python scripts/build_tables.py       # 产物：tables/baseline_repeatability.md（§6）
```

## 4. 产物

| 文件 | 生成者 | 内容 |
|---|---|---|
| `tables/historical_loop_gba_audit.csv` | `scan_history.py` | 22 个历史运行的帧数/Loop/Merge/STOP/GBA/路径比/在线-导出差 |
| `tables/baseline_repeatability.md` | `build_tables.py` | §6 的同条件重复性表与极差统计 |

## 5. 断言（任一不成立 ⇒ 输入被改动，报告结论作废）

1. `M2/OnlineTrajectory.txt` 行数 = 589；帧 493 相邻位移 ∈ [0.82, 0.84] m、旋转 ∈ [28.5, 28.9]°
2. `M2/KeyFrameTrajectory.txt` 行数 = 101；帧 265 处步进 ∈ [0.85, 0.88] m、[33.0, 33.6]°
3. 路径比：M2 = 1.519 ± 0.001；M0 = 0.976 ± 0.001
4. 四个同条件基线 ATE 集合 = {0.3401, 0.3647, 0.5323, 0.5461} ± 0.0005 m
5. 22 个历史运行中 `*Loop detected` 出现次数 = 1（仅 M2）
6. `M2/stdout.log` 中 `Local Mapping STOP` 计数 = 2，`Local Mapping RELEASE` 计数 = 2

## 6. 与原始归档的关系

- `research_archive/20261021_ngd_region_prototype/`、`20261020_*`、`20261019_*` 一律**只读**；
- 本目录新增文件不改变任何既有结论，§2 修正的三条结论在 `REPORT.md` 内显式声明；
- 状态标记：`M2 = ARCHIVED — CAUSAL BENEFIT NOT ESTABLISHED`、`M1 = BLOCKED`、`M0 = READY AS BASELINE (LC-OFF)`。
