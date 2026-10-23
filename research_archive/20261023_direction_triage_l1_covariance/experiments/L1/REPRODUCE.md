# REPRODUCE · L1 G1

全部命令在本机原样可执行。前置：ROS Noetic（`/opt/ros/noetic`）、Python 3.8.10、numpy 1.17.4。
**不需要** GPU、Open3D、torch、scipy、网络。

## 0. 数据（只读，路径固定）

```
/home/wcqw/lilocbench_amcl_validation_20261016/data/static_0.bag      141,839,376 B
/home/wcqw/lilocbench_amcl_validation_20261016/data/lt_changes_0.bag  103,773,946 B
/home/wcqw/lilocbench_amcl_validation_20261016/data/gt/static_0/gt_poses.txt     11,929 行
/home/wcqw/lilocbench_amcl_validation_20261016/data/gt/lt_changes_0/gt_poses.txt   8,700 行
```

SHA-256 见 `MANIFEST.json`。原始数据**未被修改**。

## 1. 环境

```bash
export ROS_DISTRO=noetic
source /opt/ros/noetic/setup.bash
export ROS_MASTER_URI=http://localhost:11355      # 隔离端口，不用默认 11311
export ROS_HOME=/home/wcqw/slam_multi_direction_research/logs/ros_home_l1
roscore -p 11355 &
```

## 2. 正式运行（两条序列各 1 次，不可重跑替换）

```bash
cd /home/wcqw/slam_multi_direction_research/experiments/L1
bash run_g1.sh          # ≈ 17 min（两条序列 1.0× 实时回放）
```

每条序列产出 `runs/L1_G1_hector_<seq>_<UTCSTAMP>/`：
`measure.bag`（原始 `/hector_debug_info` + `/slam_out_pose` + `/poseupdate`）、
`hector_{stdout,stderr}.log`、`play.log`、`record.log`、`play_exit_code`、`measure_bag_info.txt`。

## 3. 分析与复算

```bash
cd /home/wcqw/slam_multi_direction_research/experiments/L1
python3 analysis/l1_g1_analysis.py runs/L1_G1_hector_static_0_*      static_0
python3 analysis/l1_g1_analysis.py runs/L1_G1_hector_lt_changes_0_*  lt_changes_0
```

写出 `summary.json` / `per_frame.csv` / `dropped_frames.csv`。

## 4. 声明式敏感性（**不是结果**）

```bash
python3 analysis/l1_sensitivity_dt100.py runs/L1_G1_hector_static_0_*     static_0
python3 analysis/l1_sensitivity_dt100.py runs/L1_G1_hector_lt_changes_0_* lt_changes_0
```

只写 `sensitivity_dt100_*`，**不覆盖**预注册产物。

## 5. 事后诊断（`REPORT.md` §4–5）

分别对应 `analysis/coverage_stats.json`、`per_axis_decomposition.json`、
`drift_vs_white.json`、`scale_vs_shape.json`、`posthoc_relative_kouji.json`。
这些是一次性内联脚本的产物；重算所需输入仅为 `per_frame.csv` 与 `measure.bag`（Hessian）。

## 6. 已知限制（复现时必须一并声明）

1. 只有 **1 个系统**（hector_mapping）、**1 个平台**（Dingo/LILocBench）、**2 条序列**。
2. 预注册口径（绝对位姿 + 一次性 SE(2) 对齐）被偏航漂移污染
   （`e_θ` 一阶自相关 0.977/0.974），其判决**不可**归因于协方差失效。
3. `posthoc_relative_kouji.json` 是事后诊断，**非确认性**。
4. `MAX_DT=20 ms` 剔除 27% 的帧（GT 20 Hz vs 扫描 15 Hz）；100 ms 敏感性结论一致。
5. hector 的 `H_xx` 比归档 ICP 的 `H_xx` 小约两个数量级，**只使用尺度无关判据**。
6. 无独立第三方复算。本轮由同一执行者完成运行与分析。
