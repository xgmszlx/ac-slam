# 16 方向 E0 资格判决（基于本机真实资产，非计划）

生成：2026-10-23 · `CONTROL/` 单写 · 只读引用了既有归档，未改动任何旧文件
上游协议：`SLAM 多方向隔离实验执行手册`（用户提供，作参考）
**本文件的判决一律以本机实际存在的文件、分支、二进制为依据；无依据者标 `UNKNOWN`。**

---

## 0. 一句话结论

> **16 个方向里，11 个已被本仓自己的 `DECISION`/`REPORT` 关闭，2 个缺数据，1 个缺平台。
> 只有 1 个（L1）同时具备"真实数据 + 真实第三方实现 + 预注册判决门 + 未执行"，
> 并且它的判决门已经写死。本轮只做它。**

这不是"保守"，是**避免重演前三轮**：前三轮（NGD 动态、RGB-D 深度、主动 SLAM）
各自烧掉数周后以 `NO_INDEPENDENT_METHOD_OPPORTUNITY` / `INCONCLUSIVE` / `DO_NOT_START` 收场，
而收场原因**全部**是"机制证据不足"，不是"工程跑不通"。

---

## 1. 判决总表

| ID | 方向 | 旧判决（真实文件） | 本机数据 | 本机平台 | **E0 判决** |
|---|---|---|---|---|---|
| P1 | DOG 风格预剔除/特征预算 | `20261021_ngd_method_opportunity/REPORT.md` → `NO_INDEPENDENT_METHOD_OPPORTUNITY`，候选 A/B/C 均"不立项" | Bonn box ✅ | NGD 源码 ✅（已建过） | **STOP_THIS_HYPOTHESIS** |
| P2 | 类别外动态物体 | 同上；NGD v4 作者自陈不处理类别外动态，但"局限≠相邻扩张必需" | Bonn box ✅ | ✅ | **STOP_THIS_HYPOTHESIS** |
| P3 | 动态观测风险预警 | 同上；`20261021_ngd_event_mechanism` → `ONLY_CORRELATION_FOUND` | ✅ | ✅ | **STOP_THIS_HYPOTHESIS** |
| P4 | MapPoint 生命周期 | 同上："未取得被删点静态标签/MapPoint 身份/事件原 mask/LBA 约束历史" | ✅ | ✅ | **STOP_THIS_HYPOTHESIS** |
| P5 | RGB-D 深度边界 | `20261019_passive_rgbd_depth/DECISION.json` → `CONTINUE_SIMPLE_BASELINE_REPLICATION_ONLY`；`new_method: METHOD_PROTOTYPE_NOT_JUSTIFIED`；追加 4 次运行**未授权** | TUM desk/cabinet ✅ | ORB_SLAM3 `libORB_SLAM3.so` ✅，但 **Examples 可执行缺失** | **HOLD**（唯一动作已写死，需授权；见 §3） |
| P6 | 动态 RGB-D TSDF（非 3DGS） | **本仓从未做过**（`results/` 无 TSDF 产物） | TUM + Bonn ✅ | ❌ **无 open3d、无 torch**；需建 venv 装 open3d | **HOLD**（可开工但新颖性弱，见 §4） |
| P7 | 在线/导出轨迹一致性评价设施 | 已作为基础设施存在：`tools/` 全套 + `20261021_ngd_bonn_frame_audit/ERRATA.md`（Bonn GT 坐标勘误） | ✅ | ✅ | **ADVANCE（作为设施，非论文）** |
| P8 | 异步 YOLO 预算与 mask 年龄 | `20261021_ngd_method_opportunity` §"A：异步 mask 时效" → "原 YOLO 每帧输出/时间戳缺失，不能离线伪造固定回放" | ❌ 无 mask 年龄日志 | ✅ | **STOP_THIS_HYPOTHESIS**（缺证据，非缺代码） |
| A1 | 主动回环信息收益 | `research/phase4c-formal` → `REOPEN_EXECUTION_HYPOTHESIS`；`20261021` doc80 追加 `STOP_PURE_ROTATION_SELECTION` | Stage/Karto 旧运行 ✅ | catkin_ws ✅ | **STOP_THIS_HYPOTHESIS** |
| A2 | 探索停止/漏房间（旧 D1） | `20261015_direction_review/snapshots/active_map_author_validation/REPORT.md` → **`REVISE`**，原话"实际工程决策仍是**暂停主动选择器**"；`ACTIVE_ACTION_VALUE = 未执行 / UNRESOLVED`；`NOVELTY = UNRESOLVED` | ❌ 无新的合格漏房间事件 | ✅ | **STOP_THIS_HYPOTHESIS**（`NO_QUALIFYING_EVENT`） |
| A3 | MapEx/PIPE 预测信息收益 | 无本仓判决；**从未做** | ❌ 无作者预测地图样本 | ❌ 需大模型 | **STOP（无数据）** |
| A4 | 遮挡后等待/退回 | 无合格 LOST 事件真值 | ❌ | 真机不可无人值守 | **STOP（无事件）** |
| A5 | 长期变化主动核验 | LILocBench 线已归到 AMCL/聚合，非主动 | lt_changes_0 ✅（但无动作） | 无合法动作接口 | **STOP（无动作真值）** |
| X1 | 语义/开放词汇主动核验 | 从未做 | ❌ 本机无语义标注数据 | ❌ 无 torch/VLM，GPU 8 GB | **STOP（无数据无模型）** |
| L1 | 2D 扫描匹配协方差一致性 | `20261021_lidar_covariance_consistency` → `SCALE_FREE_MISMATCH_REPRODUCED / DECISIVE_NATIVE_TEST_NOT_EXECUTED` | LILocBench static_0 + lt_changes_0 + GT ✅ | **hector_mapping ✅（G0 已通过）** | **ADVANCE_E1（本轮执行）** |
| L2 | RGB-D + 2D LiDAR 轻量融合 | 从未做 | ❌ **无同步 RGB-D+激光数据** | — | **STOP（DATA_GATE 失败，见 §5）** |

统计：`STOP` 12 · `HOLD` 2 · `ADVANCE` 2（其中 P7 是设施、L1 是实验）。

> **一处必须纠正的转述**：手册初稿把旧 D1 记为 `DO_NOT_START`。
> 本机实际文件写的是 **`REVISE`** + "实际工程决策仍是暂停主动选择器"，
> 并明确 **不**宣称"被动已经充分解决"（S3 仍有 92 个错误 cell 修改）。
> 判决结论（暂停）一致，但**理由不同**：不是"已证伪"，而是"必要性链未闭合"。
> 本轮按事实登记 `REVISE`，不按转述登记 `DO_NOT_START`。

---

## 2. 为什么 P1–P4、P8 不能"换个名字重开"

`20261021_ngd_method_opportunity/REPORT.md` 的判决不是"跑失败了"，而是**"没有可立项的问题"**：

- 三个候选（A 异步 mask 时效、B 剔除后几何支持保护、C LK–ORB 异常协调）的
  "为何已有方法不足"一栏，全部填的是 **`UNKNOWN`**；
- 五篇直接近邻里，CC-DPMS（SSRN 2026-06-17 预印本）被判 **`HIGH_NOVELTY_OVERLAP`**，
  其摘要已明确"短时 TG-DSN 策略、动态风险与局部覆盖、保留/降权/支持保护/抑制，嵌入 ORB3"；
- 结论原话：**"没有给宽泛组合取新名字，没有设计网络、HMM、新 BA 或复杂协方差。本轮不推荐任何主算法方向。"**

**重开条件（写死）**：必须出现**新的独立问题证据**，而不是从旧混合指标里挑一个 ATE 改善。
本轮没有出现。因此 P1–P4、P8 一律 `STOP_THIS_HYPOTHESIS`，不是"暂缓"。

> 注：`20261021_ngd_bonn_frame_audit/ERRATA.md` 是一个**独立成立**的正面产出——
> 历史 Bonn RPE 混用了 GT/optical 坐标系，已按官方常数推导并公开刚体化处理。
> 这个勘误本身就是 P7 设施价值的证据，不随 NGD 线关闭而失效。

---

## 3. P5 的唯一合法下一步（已写死在归档里，**未授权**）

`20261019_passive_rgbd_depth/NEXT_MINIMAL_ACTION.md`：

> 追加 desk `B1_02 → B0_02 → B0_03 → B1_03`，共 4 次；总完整运行数 8（不扩大到 12 或更多）。
> large_cabinet 不追加。同一已冻结规则/数据/标定/核心/诊断/评价，不改阈值、ORB 数或初始化。
> 先比较 3 次/条件 ATE 与 1s RPE 的**全部范围**、在线/导出、覆盖/图身份、观测干预数量与成本。
> 若区间重叠或收益只在后台导出，保持 `INCONCLUSIVE` 并降低 A 优先级。

**本轮的资格核查结论**：这条动作在**工程上当前不可直接执行**——
ORB-SLAM3 只有 `lib/libORB_SLAM3.so`（4.9 MB，2026-10-15 构建），
`Examples/RGB-D/rgbd_tum` 等**可执行文件不在**（`find -executable` 只命中数据文件）。
需要先重建 Examples（Pangolin 源码在 `sources/Pangolin-1c620ff...`）。
这是一个**可完成的工程动作**，但不在本轮预算内，且它买到的是 `INCONCLUSIVE` 的概率很高
（归档已四次运行、区间宽）。

---

## 4. P6 值得单列说明（唯一"从没做过且本机能做"的被动稠密方向）

- **本仓无 TSDF 任何产物**，`results/` 只有轨迹/图评估。
- 数据齐：TUM `fr3_walking_xyz`（551 MB）、`fr3_sitting_xyz`（807 MB）、`fr1_desk`、
  `fr3_large_cabinet`；Bonn `moving_obstructing_box` 已解压在
  `/home/wcqw/passive_rgbd_combo_20261019/e2e_20261020/data/`。
- 环境：**无 open3d、无 torch、numpy 1.17.4、cv2 4.2.0**。需在 venv 里装 open3d（CPU）。
- **为什么仍列 HOLD 而不是 ADVANCE**：新颖性边界不清。动态 RGB-D TSDF/重建已有
  ReFusion、DMSG-SLAM(TSDF)、DynaFusion 等；"原始 TSDF 在动态场景有鬼影"是**已知现象**。
  能立住的**唯一**形态是：在**固定 GT 位姿**下，比较"简单 mask 过滤 / 运动补偿几何过滤 /
  时序一致融合"在**同一资源预算**下的质量—成本折中，且能给出简单策略无法覆盖的残余机制。
  这需要先做一次**新颖性排重**（`NOVELTY_MATRIX`），否则就是重复已知工作。
- 建议：**在有 L1 结果之后再决定**是否投入。理由见 §6。

---

## 5. L2 的 DATA_GATE 失败是硬结论（本轮实测）

| 需要 | 本机有吗 | 证据 |
|---|---|---|
| RGB-D + 2D 激光 **同平台同步** | ❌ | `rosbag info LILocBench/static_0.bag`：topic 仅 `cmd_vel`/`odom`/`joint_states`/`laser_scan_front`/`laser_scan_rear`/`tf`/`tf_static`。**零图像、零 IMU**。`/tf_static` 里只有 `camera_*_link` 的**坐标系声明**（无数据） |
| TUM/Bonn 补出激光 | ❌ 不可 | 二者无 2D 激光；"TUM/Bonn RGB-D 序列本身不能凭空补出同位姿的真实 2D 激光"（手册 §L2.1） |

判决：`DATA_GATE = FAIL` / `NO_QUALIFYING_EVENT`。
**不能**用"把相机深度图投影成伪激光"顶上——那是同一传感器的重参数化，
不是互补性测量，会让"融合收益"变成恒等式。

---

## 6. 本轮唯一的实验选择：L1

选择理由（逐条对应手册的资格要求）：

1. **有真实未解决问题**：归档明确 `DECISIVE_NATIVE_TEST_NOT_EXECUTED`；
   且首版三处统计被自己撤回（`REPORT.md` §0），说明这条线的**口径仍在修正中**。
2. **本机有合格的真实系统**：G0 实测通过 `hector_mapping`
   （逐帧 LM Hessian，laser-only，无需 IMU）。见 `experiments/L1/audit/G0_QUALIFICATION.md`。
3. **判决门已预注册且尺度无关**：`R = u(P99)/4.7959`（尾重比）、
   `Spearman(σ_xy, ‖e_xy‖) ≥ 0.3`、五分位比 ≥ 2。全部与 `H` 的整体尺度无关，
   因此**绕开了归档自己承认的结构性未知量**（真实测距噪声未标定）。
4. **成本可控**：CPU-only，2 条序列各 1 次，无 GPU 争用、无 ROS 冲突（独立 master 端口 11355）。
5. **结果三种都有价值**：`🟢` 开方法线；`🟡` 只做诊断；`🔴` 关线——
   **`🔴` 是最省钱的结局**，因为它终结一条已经占用多轮的线。

**同时必须承认的局限（先写死，防事后滑移）**：
hector 的 `H` 是 **scan-to-map** 的绝对位姿信息矩阵，冻结 ICP 的 `H` 是 **scan-to-reference**；
两者口径不同。本轮因此改用"绝对位姿误差 + 一次性冻结 SE(2) 对齐"，
并在 `PREREG.md` §3.2/§3.3 显式声明。**这个差异不能被写成"两者一致"。**

---

## 7. 给"想加方向"的人的三条硬约束

1. **不许两个 `NO-GO` 合并成 `GO`**（手册 §7）。本仓已出现过多起"旧线失败 → 加一个模块再试"，
   无一例外以 `NO_INDEPENDENT_METHOD_OPPORTUNITY` 收场。
2. **不许把评价错误当算法发现**。本仓已知的评价类事故清单：
   Bonn GT/optical 坐标系混用（已勘误）、LILocBench 排行榜只看差基线（R8 因此作废）、
   单次 ATE 讲故事（R4 因此作废）、把 `σ_eff` 当中位 NEES 的换写当独立发现（已撤回）。
   **每次开新方向前，先问：这次的指标自己会不会又算错？**
3. **不许用"跑通了"代替"机制成立"**。P5 的四次 desk 运行全部技术成功、
   ATE/RPE 均改善，判决仍是 `METHOD_PROTOTYPE_NOT_JUSTIFIED`——因为 n=1 的改善
   与异步自然变异不可分。这是本仓最该保持的习惯。

---

## 8. 下一步唯一动作

- **现在**：等 L1 G1 两条序列跑完 → 按冻结门判决（`R`、②、三档）。
- **然后**：`REVIEW/` 独立复算 → `FINAL_DECISION.md`。
- **只在 L1 判 🟢 时**，才讨论 P6 的新颖性排重；`🔴` 时直接归档并考虑 P5 的授权追加运行。
