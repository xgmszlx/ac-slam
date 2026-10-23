# 实际执行的估计器与度量

版本：2026-10-21，**事后**从已执行脚本重建（`protocol/design_frozen.json` 内 `frozen_before_run=false`）。这里描述的是**真正跑过的代码**，不是设计意图。

对应文件：`code/scanmatch.py`（几何与 Ground Truth）、`code/run_v3.py`（主实验）、`code/test_offset.py`（时间基偏移检验）。

---

## 1. 扫描预处理

npz 由 `code/extract.py` 从 bag 中 `/laser_scan_front/scan` 提取：`ts`、`ranges`（811×N）、`meta=(angle_min, angle_increment, range_min, range_max)`。

```
angle_min = -2.3562 rad (-135°), angle_increment = 0.00582 rad (0.333°)
视场 270.3°, 15.00 Hz, range_min 0.05 m, range_max 100 m（meta 原值）
```

`scans_to_pts(R, meta, rmax=8.0)`：只保留 `range_min ≤ r ≤ 8.0 m` 的束，转成传感器系 2D 点。**远点全部丢弃**；长度取 `min(len(ranges))` 截断，无补点。

**降采样 `pts[fi][::4]`**：每 4 束取 1，等效角分辨率 **1.33°**。真实系统用全 811 束，本实验是 1/4 密度。

## 2. 法向估计

`normals_from_scan(P, k=3)`：以跨越 `2k = 6` 束的差分作切线

```
t_i = (P_{i+k} − P_{i−k}) / ‖P_{i+k} − P_{i−k}‖ ,  N_i = (−t_iy, t_ix)
```

首尾 k 个点切线与法向为 0，随后被 `np.any(N0 != 0, axis=1)` 剔除。**法向来自本帧扫描的邻点差分，不来自地图。**

## 3. 位姿估计：点-线 ICP（scan-to-scan）

参数 `pose = (x, y, θ)`，迭代上限 20。第 n 次迭代：

```
P_n  = P_{fi} · R(θ)ᵀ + (x, y)ᵀ          # 当前扫描变换到上一帧系
N_n  = N_{fi} · R(θ)ᵀ
(idx, dist) = 体素哈希最近邻(Q = P_{fi−1}, cell = 0.3 m, 3×3 邻格)
保留 dist < 0.35 m 的对应；对应数 < 12 则中止
r_i  = N_i · (P_i − Q_idx)
J_i  = [ N_ix , N_iy , −P_iy·N_ix + P_ix·N_iy ]
w_i  = (1/σ_range²) · huber(|r_i|, δ=0.10)      # huber = 1 if |r|≤δ else δ/|r|
H    = Σ w_i J_iᵀ J_i                             # 3×3，落盘的就是这个 H
g    = Σ w_i J_iᵀ r_i
δ    = −(H + 1e-12 I)⁻¹ g                         # 正则项只进求解，不进落盘 H
收敛判据 max|δ| < 1e-8
```

`H` 的物理意义：**残差/信息矩阵**，其逆即该次扫描匹配的协方差估计 `Σ = H⁻¹`。

### 初值与每帧 4 次采样

```
init = true + N(0, (5 cm, 5 cm, 0.01 rad))    # rng = np.random.default_rng(1)，进程内连续
for pi in range(4):  # 同一帧跑 4 次，只有最后一次的行被落盘
```

> 每帧 4 行 = 4 次独立初始化。`rng` 在整个进程中共用一条流，因此**同一文件内第 k 帧的初值依赖前面所有帧**；不能把行当可自由重排的独立样本。

## 4. Ground Truth 与"真值"相对运动

`load_gt` 取 TUM 位姿列 `(t, x, y, *, qx, qy, qz, qw)`，yaw：

```
yaw = atan2( 2(qw·qz + qx·qy) , 1 − 2(qy² + qz²) )
```

`gt_at` 在扫描时间戳上线性插值（yaw 走最短弧）。"真值"相对运动由上一帧 GT 位姿表示：

```
Δw = p_fi − p_{fi−1}                        # 世界系
true = R(−yaw_a) · Δw  ,  true_θ = wrap(yaw_b − yaw_a)
```

GT 20 Hz、扫描 15 Hz → 中间帧靠插值，属**推导**而非直接测量。

`test_offset.py` 另做时间基检验：把 GT 对齐帧平移 −3…+3，匹配对不变，看位移误差是否在偏移 0 处最小。归档结论为 0 帧处最小（0.77 cm），±3 帧约 7.5 cm。

## 5. 一致性度量

```
e    = (x, y, θ) − true ,  θ 分量 wrap 到 (−π, π]
NEES = eᵀ · H · e
```

自由度 = 3 → 若 `Σ = H⁻¹` 正确，`NEES ~ χ²₃`，**中位 2.366、均值 3**。

有效噪声反解：

```
σ_eff = σ_range · sqrt( median(NEES) / 3 )
```

## 6. 几何度量：两种定义

| 符号 | 定义 | 尺度不变？ |
|---|---|---|
| `γ_mixed` | `λmin(H)/λmax(H)`，H 为**混合单位** 3×3（列单位 m, m, rad） | ❌ **否**，见 REPORT §4.1 |
| `γ_xy` | `λmin(H_xy)/λmax(H_xy)`，H_xy 为平移 2×2 块 | ✅ 是 |

`results/per_frame.csv` 同时给两列：`gamma_lmin_over_lmax_mixed_units` 与 `gamma_xy_translation_only`。**今后一律以 `γ_xy` 作退化度量。**

## 7. 尾部与相关性统计

- 尾部：`NEES ≥ p90(该条件)`。
- 相关：Hessian 侧由 `corr(Σ)`，`Σ = H⁻¹`（本次用"逐帧算再取平均"）；经验侧由样本 `e` 的 Pearson 相关（全行与"每帧首初始化"两种）。
- 所有统计不做显著性检验（n=2 序列）。

## 7b. 尺度无关判据（2026-10-21 审计新增）

### σ 扫描为何不构成实验（推导）

```
w_i(σ) = (1/σ²) · huber(|r_i|) ,  Huber 权重与 σ 无关
⇒ 正规方程 (Σ w JᵀJ) δ = −Σ w Jᵀ r 两边同乘 σ² 后不变
⇒ 解 (x, y, θ) 与 σ 无关；只有 H 整体乘 1/σ²
```

因此 `NEES = eᵀH e` 与 `1/σ²` 成正比是**恒等式**；三档 σ 是同一份结果的三种写法。实测验证：三档间 `max‖e‖` 差 ≤ 4.1e-16，`H` 比值恒为 `(0.02/σ)²`。

### 判据 A：归一化尾部 `u = NEES / median(NEES)`

`Σ → kΣ` 使 `NEES → NEES/k`，中位同比缩小，**`u` 完全不变**。若"Hessian 协方差正确、最多差一个未知标量"，则 `u` 必须服从 χ²₃ 除以自身中位的形状：

| 分位 | χ²₃ 值 | 归一化参考 `u` |
|---|---:|---:|
| P50 | 2.366 | 1.000 |
| P90 | 6.251 | 2.642 |
| P99 | 11.345 | 4.795 |
| P99.9 | 16.266 | 6.875 |

膨胀倍数 = `u(p) / u_ref(p)`。**任何 `k` 都不能改变这个倍数** → 可证伪"标量膨胀足够"。

### 判据 B：相关结构

`corr(Σ)` 在 `Σ → kΣ` 下不变，故尺度无关。

### 判据 C：模型是否知道哪帧会坏

```
预测 σ_xy = sqrt( trace( (H⁻¹)[:2,:2] ) )
```

比较尾部帧与其余帧的 `σ_xy` 中位之比（尺度无关），并计算 `NEES` 与 `σ_xy` 的 rank 相关。比值 ≈ 1 且 rank 相关 ≈ 0 ⇒ 模型对"坏帧"零信息，即"自信地错"。

### 退化度量

`γ_mixed`（混合单位 3×3）**不是尺度不变量**：同一几何改用 cm 后 γ 从 0.0603/0.0826 降到 < 1e-4。一律改用 `γ_xy`（平移 2×2 块）。


## 8. 未做的处理（必须保留）

1. 未做 scan-to-submap、未建图、无协方差传播、无回环修正。
2. 未使用全分辨率；未做运动畸变校正；未做动态滤波。
3. 未修 2DLIW-SLAM 的任何数学；`code/native_export/PATCH_laser_info.md` 仅为只读导出补丁说明，**未执行**。
4. `code/not_executed/merge_imu.py` 未运行，仅记录当时的中间产物思路。
