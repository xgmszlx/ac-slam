# 20261023 · 16 方向 E0 资格判决 + L1 原生信息矩阵一致性（G0→G1）

**决策：`L1 = HOLD`；其余 15 个方向 `STOP`/`HOLD`（详见 `CONTROL/DIRECTION_TRIAGE.md`）。
本轮无 SCI 方法资格，不是论文结果。**

---

## 0. 这一轮做了什么

把用户提供的《SLAM 多方向隔离实验执行手册》的 16 个候选方向（P1–P8、A1–A5、X1、L1、L2）
逐条对本机真实资产做 E0 资格审查，并对**唯一具备条件**的 L1 真实执行了
G0（资格门）→ G1（科学门），**只用了 2 次正式运行、纯 CPU、零新数据下载、零 GPU**。

## 1. 三条实质结论

### 1.1 16 个方向里 12 个不该做（有据，不是保守）

| 类别 | 方向 | 依据 |
|---|---|---|
| 本仓自己已关闭（机制证据不足） | P1 P2 P3 P4 P8 A1 A2 | `research_archive/20261021_ngd_method_opportunity/REPORT.md` → `NO_INDEPENDENT_METHOD_OPPORTUNITY`；`20261015_direction_review/.../active_map_author_validation/REPORT.md` → `REVISE` |
| 无数据 / 无平台 | A3 A4 A5 X1 L2 | 见 §1.3 的 L2 实测 |
| 可做但未授权 / 新颖性未排重 | P5 P6 | P5 的追加 4 次运行已写死但需授权；P6 需先做 `NOVELTY_MATRIX` |

> 手册把旧 D1 记为 `DO_NOT_START`；本机实际文件写的是 **`REVISE`**（"暂停主动选择器"）。
> 结论一致但理由不同：不是"已证伪"，而是"必要性链未闭合"。本归档按事实登记。

### 1.2 L1 的关键结果：**先推翻了自己**

| 判据（预注册，尺度无关） | static_0 | lt_changes_0 | 门 |
|---|---:|---:|---|
| `NEES_rel` 中位（相对/增量口径） | 1.54（0.65×） | 1.01（0.43×） | 一致值 2.366 → **量级正确、略保守** |
| 尾重比 `R = u(P99)/4.7959` | **8.28** | **12.23** | ① ≥ 5 → **双双通过** |
| Spearman(σ_xy, ‖e_xy‖) | **+0.086** | **+0.063** | ② ≥ 0.3 → **双双失败** |
| 五分位误差比 | 1.14 | 1.12 | ② ≥ 2 → **双双失败** |

→ **`HOLD`**：不做基于 Hessian 的在线可靠性/降级信号（②双否）；
但**尾部确实重 8–12 倍**，这是唯一留下的可立项问题。

**容易被得出的错误结论已被本归档自己的数据阻断**：绝对位姿 NEES 给出"过度自信 63×"，
看似重大发现，实为**口径伪影**——偏航误差一阶自相关 **0.977/0.974**、四分位绝对值近似常值，
是**无回环系统的累计偏置**，逐帧 Hessian 按构造无法预测。换相对口径后结论**反向**。
详见 `experiments/L1/REPORT.md` §4。

### 1.3 两条可独立复算的负结果

1. `hector_mapping` 发布的 `/poseupdate.covariance` **不能当协方差用**：
   实测 `sd_x` 中位 **6.85 m**、`sd_θ` 中位 **569 rad**（同时段机器人总位移仅 12.96 m 且跟踪正常）。
   矩阵对称半正定，所以是**尺度未文档化的内部量**，不是填错槽位。
2. `laser_scan_matcher` 的 `position_covariance` / `orientation_covariance`
   是**launch 常数**（二进制里只有这两个参数名），不是逐帧计算。
   **话题名带 `covariance` 不等于有逐帧不确定性。**

## 2. 目录

```
CONTROL/                      方向总控（仅本轮写入）
  DIRECTION_TRIAGE.md          16 方向 E0 判决表 + 每条的真实依据
  MASTER_MATRIX.csv            跨方向统一矩阵
  TASK_REGISTRY.csv            任务登记
  ROOT_MANIFEST.json           仓库/分支/未提交状态快照
  DATA_REGISTRY.csv            数据只读登记（含 sha256）
  ASSET_REGISTRY.csv           二进制/源码/模型登记
  RESOURCE_LOCKS.md            独占资源锁与隔离实况
experiments/L1/
  protocol/PREREG.md           预注册（测量前冻结；阈值承自 20261021 归档）
  audit/G0_QUALIFICATION.md    G0：合格原生信息矩阵源鉴定（4 排除 + 1 通过）
  REPORT.md                    主报告：问题→方法→结果→口径伪影→边界
  REPRODUCE.md                 复现命令
  decision.json / MANIFEST.json
  analysis/                    分析脚本 + 各诊断 json
  runs/<run_id>/               逐运行冻结证据（per_frame.csv / summary.json / 日志 / 退出码）
REVIEW/
  REPRODUCTION_AUDIT.md        同人独立复算（PASS）+ 3 处自身失误记录
  FINAL_DECISION.md            五问定案 + 唯一主线/备选
  recomputation.json
LOCAL_ONLY_MANIFEST.json       未入库的原始 .bag 与回放日志的 sha256
```

## 3. 继承与边界

- 本分支基于 `research/ngd-bonn-frame-audit-20261021`（`ed5fbbf6`），
  并**导入** `research_archive/20261021_lidar_covariance_consistency`（自 `0da315c8`）
  以便 L1 的上游协议在本分支内可直接读取。导入目录**逐字节未改动**。
- 旧归档 `20261015…20261021` 全部**只读**，本归档未修改任何一个旧文件。
- **不发布**第三方代码、权重、数据集与原始 bag；`.bag` 与回放日志按本仓库既有约定
  只登记 sha256（见 `LOCAL_ONLY_MANIFEST.json`）。

## 4. 已知限制（必须与结论一起引用）

1. 只测了 **1 个系统**（hector_mapping）、**1 个平台**（Dingo/LILocBench）、**2 条序列** → 无外推能力。
2. 预注册的绝对口径被漂移污染，其判决**不可**归因于协方差失效。
3. `analysis/posthoc_relative_kouji.json` 是**事后诊断，非确认性**。
4. 预注册门在 `R ∈ [1.5, 5)` 未枚举（`static_0` 的 3.889 落在其中）→ 已标 `GATE_UNENUMERATED_REGION`，未自行解释。
5. `MAX_DT = 20 ms` 剔除 27% 帧；100 ms 声明式敏感性结论一致（`R=3.54/8.33`，`ρ=−0.098/−0.058`）。
6. **同人复算**：排除算错，不排除口径选错；无独立第三方复验；无文献排重。

## 5. 唯一下一步

把相对口径正式预注册（Amendment 1），并在**一个带回环闭合的 2D SLAM** 上重测尾重比，
以区分"漂移残差"与"扫描匹配尾部"。在此之前禁止：改参数、加序列、开发新协方差模型、写方法章节。
