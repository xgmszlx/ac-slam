# L1 G1 · 预注册协议（冻结于测量之前）

`direction_id`: L1
`stage`: E1（G0 已通过 → G1）
`frozen_at`: 2026-10-23（工作机时钟）
`authority`: 本文件继承 `research_archive/20261021_lidar_covariance_consistency/NEXT_MINIMAL_ACTION.md`
§3 的**判决门与统计口径**，逐条照抄，不新增、不修改阈值。凡与本文件不符的后续改动一律视为
protocol violation，结果只能登记为 `EXPLORATORY`。

---

## 0. 本轮要回答的唯一问题

> 一个**真实** 2D 激光扫描匹配系统自己算出的逐帧信息矩阵 `H`，
> 能否描述它自己的实际误差？能否预警它自己的失败帧？

**不是**"证明 2D 激光 SLAM 过度自信"，**不是**"提出新的协方差模型"。

---

## 1. G0 结论（已执行，见 `../audit/G0_QUALIFICATION.md`）

| 候选真实系统 | laser+odom 够吗 | 有逐帧信息矩阵吗 | 本机可跑 | 判决 |
|---|---|---|---|---|
| 2DLIW-SLAM | ❌ 需 IMU，LILocBench 无 IMU | — | ❌ | 排除（硬阻塞） |
| `laser_scan_matcher` | ✅ | ❌ `position_covariance`/`orientation_covariance` 是 **launch 固定参数**，非逐帧计算 | ✅ | 排除 |
| AMCL | ✅ | ⚠️ 粒子云协方差，非扫描匹配 Hessian，口径不同 | ✅ | 排除（口径） |
| slam_toolbox / cartographer | — | — | ❌ 本机未安装 | 排除 |
| **hector_mapping** | ✅ **不需要 odom** | ✅ **`/hector_debug_info` 给出 `iterData[].hessian`（float64[9]），逐 LM 迭代** | ✅ | **✅ 通过** |

G0 判决：`QUALIFIED_NATIVE_INFO_SOURCE = hector_mapping`。
（`laser_scan_matcher` 的排除依据：`liblaser_scan_matcher.so` 中只存在 `position_covariance`、
`orientation_covariance` 两个参数名，无逐帧协方差计算路径。）

---

## 2. 数据与运行

| 项 | 值 |
|---|---|
| 序列 | LILocBench `static_0`（598.757 s）、`lt_changes_0`（435.955 s） |
| 原始 bag | `static_0.bag` 141,839,376 B；`lt_changes_0.bag` 103,773,946 B |
| GT | `gt/<seq>/gt_poses.txt`，TUM 格式 7 列，20 Hz，11929 / 8700 行 |
| 扫描 | `/laser_scan_front/scan`，811 束，270°，`range_max` 100 m |
| 系统 | `hector_mapping`（ROS Noetic 二进制），`map_resolution=0.05`，`map_size=2048`，`map_update_distance_thresh=0.4`，`map_update_angle_thresh=0.9`，`pub_debug_output=true` |
| GT 用途 | **仅离线评价**，无在线 GT 流 |
| 预算 | 每序列 1 次，失败保留不重跑 |

**rosbag 回放速率固定 `-r 1.0`**（不提速，避免丢帧改变 Hessian 序列）。

---

## 3. 测量定义（口径适配，明确声明）

### 3.1 `H` 的来源

`H_k` = 第 k 个匹配扫描的 **最后一次 LM 迭代**（`iterData[-1].hessian`）3×3 矩阵，
世界（map）坐标系，参数化为 `(x, y, θ)`。

首帧 Hessian 全零（尚无地图），按 `n=0` 排除，不插补。

### 3.2 口径适配（与冻结 ICP 口径的差异，**必须写进报告**）

冻结 ICP 的 `H` 是 **scan-to-reference** 的信息矩阵，参考位姿来自 GT 相对位姿。
hector 的 `H` 是 **scan-to-map** 的信息矩阵，作用于**绝对** map 坐标系位姿。

因此本轮 `e` 必须与 `H` 处于同一坐标系与同一线性化对象：采用
**绝对位姿误差（map 系）**，而不是逐帧相对位移。

### 3.3 对齐规则（冻结）

GT 世界系与 hector map 系相差一个刚体 SE(2) 变换。

- 取**前 `N_align = 50` 个有效匹配帧**，用 **Horn/Umeyama SE(2)（无尺度）** 估计
  `T_gt→map`。
- **此后永久冻结**，不再对任何后续帧重新对齐、不做 per-frame 自由配准、
  不做尺度拟合（**SE(2)，无尺度自由度**）。
- 该规则只服务于"把两条轨迹放到同一坐标系"，**不用于**在误差计算中抹掉局部畸变。

### 3.4 误差与 NEES

```
e_k = log_SE2( (T_gt→map · ξ^gt_k)⁻¹ · ξ^hector_k )   ∈ R³, (x, y, θ) 世界系
NEES_k = e_kᵀ H_k e_k                    (DOF = 3)
```

**只使用** `H`，不使用 hector 发布的 `poseupdate.covariance`
（该字段在 G0 中已实测**不可作为协方差使用**：σ_x 中位 6.85 m、σ_θ 中位 569 rad，
见 `../audit/G0_QUALIFICATION.md` §4）。

### 3.5 有效帧筛选（不看结果，只看可行性）

- 丢弃 `H_k` 非有限、非对称（`max|H−Hᵀ| > 1e-6`）、或 `λmin(H) ≤ 0` 的帧；
- 丢弃 `e_k` 非有限的帧；
- 丢弃与 GT 时间配对误差 > 20 ms 的帧；
- 每个被丢弃帧写入 `audit/dropped_frames.csv`，**给出原因，不静默删除**。

---

## 4. 判决门（**逐字承自 NEXT_MINIMAL_ACTION §3，禁止改动**）

独立有效帧 `n ≥ 200` 才做判定。**所有量均为尺度无关量**。

**尾部度量**：`u_k = NEES_k / median(NEES)`，`R = u(P99) / 4.7959`。

> `4.7959 = χ²₃(0.99)/χ²₃(0.50) = 11.34487/2.36597`，即"一致模型下尾部应有的倍率"。
> 因此 `R` 是纯粹的**尾重比**，与 `H` 的整体尺度无关。

**预测力度量 ②**：

- (a) `Spearman rank corr( sqrt(tr(Σ_xy,k)), ‖e_xy,k‖ ) ≥ 0.3`，其中 `Σ_k = H_k⁻¹`；
- (b) 且 `σ_xy` **最高五分位**帧的平均 `‖e_xy‖` ≥ **2 倍** **最低五分位**帧的平均值。

**判决表**（照抄）：

| 条件 | 判决 | 后续 |
|---|---|---|
| `R ≥ 5` **且** ② 成立 | 🟢 `COVARIANCE_CANNOT_DESCRIBE_NOR_WARN` | 允许进入方法设计 |
| 只命中其一 | 🟡 `PARTIAL` | 先补真实测距噪声标定，只做诊断，不写主张 |
| `R < 1.5` 且 ② 不成立 | 🔴 `SIMPLIFIED_ICP_ARTIFACT` | 立即关闭本线 |

`R` 与 ② 的实际取值无论落在哪一格，都**按实际登记，不重跑、不换阈值、不换序列**。

---

## 5. 禁止事项（承自 §4）

1. 看到结果后不许调 `map_resolution`、`map_update_*`、LM 迭代数、对齐帧数 `N_align`。
2. 不许用一条序列的结论外推到"2D 激光 SLAM"整体。
3. 不许把 `σ_eff` 当独立发现。
4. 不许用部分日志算 NEES；异常退出保留原样。
5. 不许改动 hector 的匹配、优化、地图更新行为（只加只读订阅）。

---

## 6. 本轮**不能**支持的主张（先写下来，防止事后滑移）

- 不能支持"hector 的协方差模型不可靠"→ 只能说"在其发布的信息矩阵口径下，观测到的尾重比是 R=x"。
- 不能支持"2D 激光 SLAM 过度自信"。
- 不能支持任何**方法**贡献：本轮是**机制测量**，不是方法。
- `lt_changes_0` 含长期地图变化；hector 无回环闭合，其漂移属**已知系统行为**，
  不得把漂移本身当作"协方差失败"。
