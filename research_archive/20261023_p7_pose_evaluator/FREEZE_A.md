# P7-A 冻结记录

冻结时间：2026-10-23T16:37:07+08:00
组件：位姿评价（TUM/Bonn GT、时间关联、SE(3)/Sim(3) 对齐、ATE、时间窗 RPE、双向覆盖率）

| 文件 | sha256 |
|---|---|
| pose_eval.py | 5f85863cb288ccff5f3adeb01a27adcd11da96de126075c94176f59c652db526 |
| test_pose_eval.py | bf5095cd2ef2331a5bc99c185647209d75de552aa043159d4ce5d455083be249 |

## 冻结的口径（改动即失效，须新版本号）

1. 文件为 TUM 格式 `t x y z qx qy qz qw`（秒）。
2. 每行位姿为 camera-to-world：`p_world = R p_cam + t`。
3. **对齐只作用在估计轨迹上，永不作用在 GT 上**。
4. 尺度默认关闭（SE(3)）。RGB-D/双目必须用 SE(3)；Sim(3) 需显式开启且报告必须写明。
5. RPE 用**时间窗**（默认 1.0 s），不用帧数；窗口不匹配的帧对**跳过并计数**，
   绝不跨缺口构造长基线。
6. ATE 同时报**对齐后**与**未对齐**两个数——对齐后的 ATE 会吸收常值偏移，
   而常值偏移对定位系统是真实故障。
7. 覆盖率**双向报告**：`coverage_est`（估计有多少帧找到 GT）与
   `coverage_gt`（GT 有多少被覆盖）。删掉一段轨迹时前者仍是 1.0，只有后者会掉。
8. Bonn 的 `bonn_camera_frame` 分支只对 Bonn 生效，永不作用于 TUM；报告的 options 字段记录实际分支。

## 单测（20 条断言，全部解析期望）

```
$ python3 test_pose_eval.py
ALL P7-A TESTS PASSED
```

## 已知限制

- Bonn 尺度因子的物理成因在上游归档中仍是 UNKNOWN，本组件**不**解决它。
- 无对齐失败检测（退化轨迹的 SVD 病态未单独处理）。
- 未做时间偏移搜索：若 GT 与估计存在系统性时移，需要调用者自行处理。
