# L1 · 源码级结案：hector 的 `/poseupdate.covariance` 就是 Hessian（2026-10-23）

## 0. 结论：悬案结案，`HESSIAN_PUBLISHED_AS_COVARIANCE_CONFIRMED`

`/opt/ros/noetic/include/hector_mapping/matcher/ScanMatcher.h` 第 172–184 行（实际编译版本）：

```cpp
covMatrix = Eigen::Matrix3f::Zero();
//covMatrix.block<2,2>(0,0) = (H.block<2,2>(0,0).inverse());   // 逆 Hessian：注释掉
//covMatrix.block<2,2>(0,0) = (H.block<2,2>(0,0));             // 裸 H：注释掉
/*
covMatrix(0,0) = 1.0/(0.1*0.1);                                // 固定噪声：注释掉
covMatrix(1,1) = 1.0/(0.1*0.1);
covMatrix(2,2) = 1.0/((M_PI / 18.0f) * (M_PI / 18.0f));
*/
covMatrix = H;                                                  // ← 实际生效
```

**三个候选写法里，唯一生效的是把 Hessian 直接赋给 covariance。**
这解释了 G0 阶段实测到的荒谬数值（`sd_x` 6.85 m、`sd_θ` 569 rad）：
那些数不是标准差，是**信息矩阵的元素**。

## 1. 三条被本源码直接回答的问题

| 问题 | 答案 |
|---|---|
| `/poseupdate.covariance` 是什么？ | **就是 LM 的 Hessian（信息矩阵）**，未做求逆、未做缩放 |
| hector 论文的 `Σ ≈ σ²H⁻¹` 在本实现里成立吗？ | **不成立**。逆 Hessian 的写法存在但被注释掉；没有任何 σ² 标定 |
| L1 的"结构性未知量 σ²"能从这个系统标定吗？ | **不能**。代码路径里根本没有 σ²，作者把固定噪声方案也注释掉了 |

## 2. 因此对我此前两处表述的最终处置

1. **我最初说"这不是填错槽位，而是尺度未文档化的内部量"** —— 推理方法错（对称半正定不能判别），
   **但结论方向的猜测恰好相反于真相**：它**确实是**把信息矩阵填进了协方差槽位。
   原始判断与结论都不成立，以本节为准。
2. **2016 年社区报告（hector_slam Issue #35）的判断是正确且充分的**。
   本轮不是"新发现"，而是**为其提供源码级确认**，并顺带解释了为什么 NEES 会离谱。

## 3. 对 L1 G1 统计的最终定位

- 我在 G1 里用 `NEES = eᵀ H e`（把 H 当信息矩阵）**恰好是这个源码事实下的正确用法**；
  用 `H⁻¹` 当协方差则会产生完全不同的结果。
- 但**这不足以救回 G1 的结论**：有效样本量 `n_eff` 只有 15.8 / 32.0，
  预注册门要求 ≥200，判决仍未通过（见 `ERRATA.md`）。
- 而且既然本系统**没有 σ² 标定路径**，任何"协方差是否标定良好"的绝对判断都无法在本系统内完成。

## 4. L1 最终判决

```
technical_status : BASELINE_READY      (G0 资格 + 两条序列真实运行，均已完成)
event_status     : EVENT_UNRESOLVED    (门未通过，事件未被检验)
mechanism_status : INCONCLUSIVE        (测量设计无效，非机制缺失)
novelty_status   : NOVELTY_CONFLICT    (Issue #35 2016 已报告；不能作为负结果主张)
decision         : STOP_THIS_HYPOTHESIS
```

### 停止理由（不是"领域没价值"）
1. **决定性源码事实已取得**，且早已被社区报告 → 这部分不构成研究贡献。
2. **σ² 在本系统内不可标定** → L1 想做的"一致性检验"缺一个必要的标定量，
   只能靠外部噪声模型，而那需要另立课题。
3. **原 G1 判决未过自己写的门**，且样本量差一个数量级。
4. 若要重启，必须先解决"独立样本单位"与"σ² 外部标定"两件事，
   并换一个**带回环**的系统（否则漂移与逐帧误差不可分）。

## 5. 仍然成立、可被引用的东西

- `hector_mapping` 经 `/hector_debug_info` 每帧给出 11 次 LM 迭代的 **Hessian**（`float64[9]`），
  参数化为世界系 `(x, y, θ)`。
- `laser_scan_matcher` 的 `position_covariance`/`orientation_covariance` **是 launch 常量**。
- 2DLIW-SLAM 需要 IMU，LILocBench 精简 bag 无 IMU。
- 跨运行噪声底：位姿层面中位 0.404 cm / 最大 3.263 cm（同一二进制、同一输入）。
