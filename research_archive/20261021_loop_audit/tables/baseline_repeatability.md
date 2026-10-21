### A. 同条件重复：Bonn `moving_obstructing_box`，589 帧，mode 0

同序列、同 `associations.txt`（sha256 `c30faa1d…`）、同 `bonn.yaml`（sha256 `972bc2bc…`）、同 `OPENCV_FOR_THREADS_NUM=1`；差别只有构建/入口二进制。

| 运行 | 入口 | ATE (m) | RPEt (m) | RPEr (°) | KF | 关键帧最大速度 | 路径比 导出/在线 |
|---|---|---|---|---|---|---|---|
| M0_05  20261020 ngd_scientific_baseline | rgbd_tum_headless | 0.3647 | 0.3243 | 18.74 | 101 | 3.242 m/s | - |
| S0     20261020 rgbd_combo_e2e | rgbd_combo mode0 | 0.5323 | 0.3552 | 19.60 | 72 | 1.121 m/s | 0.98 |
| S0     20261020 rgbd_deletion_ablation | rgbd_combo mode0 | 0.5461 | 0.3605 | 19.34 | 69 | 1.049 m/s | 0.982 |
| M0     20261021 ngd_region_prototype | rgbd_region mode0 | 0.3401 | 0.3153 | 18.89 | 100 | 1.033 m/s | 0.976 |

- ATE：min=0.3401  max=0.5461  range=0.2060  相对=60.6%
- RPEt：min=0.3153  max=0.3605  range=0.0452  相对=14.3%
- RPEr：min=18.7427  max=19.5960  range=0.8532  相对=4.6%
- 关键帧数：min=69 max=101 range=32
- **M2 相对 M0 的 ATE 变化 = 0.068 m，仅为本条件基线极差 0.2060 m 的 33%**

### B. 同条件重复：`walking`，827 帧，mode 0

| 运行 | ATE (m) | RPEt (m) | RPEr (°) | KF |
|---|---|---|---|---|
| M0_02 | 0.01537 | 0.02006 | 0.608 | 75 |
| M0_03 | 0.01570 | 0.01987 | 0.606 | 79 |

- ATE：min=0.0154  max=0.0157  range=0.0003  相对=2.2%
- RPEt：min=0.0199  max=0.0201  range=0.0002  相对=0.9%
- RPEr：min=0.6057  max=0.6085  range=0.0028  相对=0.5%

`20261020_ngd_scientific_baseline/results/comparison.csv` 另含第三次同条件重复 `M0_01`（轨迹文件未入库，ATE 0.01577、RPEt 0.01970、RPEr 0.587、KF 75），故 walking 实际有 3 次同条件重复，ATE 极差 0.0004 m（2.5%）。
