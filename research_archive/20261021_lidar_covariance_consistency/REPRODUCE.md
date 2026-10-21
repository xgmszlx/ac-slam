# 复现这份归档

本归档**不含** 15–142 MB 级的原始数据（npz/bag）与上游源码。要重跑匹配，需先按 §1 准备数据；只复核本报告数字，则只需 §2。

环境：Ubuntu 20.04，`/usr/bin/python3` 3.8.10，numpy 1.17.4（**无 scipy**），matplotlib 3.1.2（仅画图用），ROS Noetic（仅 `extract.py` 需要 `rosbag`）。

---

## 1. 数据准备（若本机已有 npz 可跳过）

```bash
export D=/home/wcqw/lilocbench_amcl_validation_20261016/data
source /opt/ros/noetic/setup.bash

/usr/bin/python3 code/extract.py "$D/static_0.bag" static_0.npz /laser_scan_front/scan
/usr/bin/python3 code/extract.py "$D/lt_changes_0.bag" lt_changes_0.npz /laser_scan_front/scan
```

应得到
`static_0.npz` sha256 `fe8e5cebdcabb3270dde5970e10df5851e3ca7ac904acc2f3858c98955ce1a13`、
`lt_changes_0.npz` sha256 `b1c33783dbaa321e2f5a12abac3393c3b3ba4cc50a004d76737290cb8d015927`。

原始 bag 与 GT 哈希见 [REPORT.md](REPORT.md) §2；数据按 LILocBench 官方条款使用，不随归档分发。

## 2. 只复核本报告的数字（无需数据）

```bash
cd research_archive/20261021_lidar_covariance_consistency
/usr/bin/python3 code/audit_consistency.py
```

读 `results/v3_*.json` → 重写 `results/summary.json`、`results/per_frame.csv`、
`results/correlation_check.json`、`audit/independent_check.json`。**应逐位复现 `results/` 下的现有文件。**

画图（可选，需要 matplotlib）：

```bash
/usr/bin/python3 code/plot_figures.py      # 读 per_frame.csv，写 figures/*.png
```

## 3. 重跑全部 6 个条件（需要 §1 的 npz）

```bash
/usr/bin/python3 code/run_v3.py static_0.npz     "$D/gt/static_0/gt_poses.txt"     0.02 s0.02     60
/usr/bin/python3 code/run_v3.py static_0.npz     "$D/gt/static_0/gt_poses.txt"     0.04 s0.04     60
/usr/bin/python3 code/run_v3.py static_0.npz     "$D/gt/static_0/gt_poses.txt"     0.06 s0.06     60
/usr/bin/python3 code/run_v3.py lt_changes_0.npz "$D/gt/lt_changes_0/gt_poses.txt" 0.02 lt0.02    60
/usr/bin/python3 code/run_v3.py lt_changes_0.npz "$D/gt/lt_changes_0/gt_poses.txt" 0.04 lt0.04    60
/usr/bin/python3 code/run_v3.py lt_changes_0.npz "$D/gt/lt_changes_0/gt_poses.txt" 0.06 lt0.06    60
```

（`code/run_lt.sh` 是当时实际使用的批量脚本，路径写死，可直接对照。）

**注意**：`run_v3.py` 的随机流是进程级的（`default_rng(1)`），每帧 4 次初始化共用同一条流。因此**必须按上表顺序、单进程逐个条件执行**，否则行内容会变。这是该脚本的既有性质，本轮未修改。

预期输出（行级）：`static_0` 200 行 / 50 帧，`lt_changes_0` 240 行 / 60 帧；中位 NEES 分别 2×(26.30, 6.57, 2.92) 与 (24.17, 6.04, 2.69)（σ=0.02/0.04/0.06 顺序）。

## 4. 时间基检验（可选）

```bash
# test_offset.py 内写死读 ./static_0.npz
/usr/bin/python3 code/test_offset.py
```

预期：GT 偏移 0 帧处位移误差中位最小。

## 5. `results/legacy/` 的说明

`res_static_0.json`（240 行，含 `e_along`/`e_lat`/`lmin`/`lmax`/`gamma`）与
`consistency_static_0.json`（60 行）是**更早的变体**，不参与本报告的复算，也没有被任何归档脚本读取。其中 `consistency_static_0.json` 首行 `nees ≈ 7e-19`，说明该次运行的误差近似为零，属异常样本。**据此文件得出的任何统计都不应采用**；保留它只为记录当时的中间状态。

## 6. 未执行的文件

- `code/native_export/PATCH_laser_info.md`：2DLIW-SLAM 只读信息矩阵导出补丁的**说明**，从未编译、从未运行。
- `code/not_executed/merge_imu.py`：accel/gyro 合并脚本，从未运行。
- `code/cov_consistency.py`、`code/sim_cov_consistency.py`、`code/analyze_laser_info.py`、`code/run_consistency*.py`：**未产出本报告中任何数字**。它们分别属于更早的 CSV 分析、仿真、以及等待 `laser_info.csv` 的分析器。保留以记录工具状态。
