# P1 · A/B 特征层对照结果（2026-10-23）

## 0. 判决：`MECHANISM_CONFIRMED_AT_FEATURE_LEVEL`

**A 组只用到名义特征预算的 ~79%，B 组稳定打满；同一输入帧上 B 一致多于 A。**
但**几何质量是否随之改善尚未测量**，因此这不是方法收益的结论（见 §4）。

## 1. 机制实现（同二进制、环境变量切换）

| 组 | 行为 |
|---|---|
| **A 原生** | `nFeatures*1.5` 提取 → 八叉树在**整幅图**上分配预算 → 事后按 mask 删除（`Frame.cc` 原逻辑） |
| **B 预剔除** | 掩码按各层金字塔尺寸缩放 → FAST 候选**进入 `DistributeOctTree` 之前**逐点过滤 → 预算只落在有效静态区 |

切换开关：环境变量 `NGD_ORB_PRECULL`。**A 与 B 是同一个二进制**，只有这个变量不同，
因此不存在编译差异污染。掩码来自在线管线真实使用的 `mImMask`（已独立核验，见
`MASK_CAPTURE_AND_NONDETERMINISM.md`）。

## 2. 单测：7/7 通过（`tests/test_precull.cc`）

```
PASS  empty mask: flag on/off give the same count | 1004 vs 1004
PASS  full mask: zero keypoints survive (pre-cull active) | n=0
PASS  pre-cull: zero keypoints inside a half-image mask | inside=0
PASS  native path: extractor itself still returns keypoints inside the mask (it is ignored there) | inside=507
PASS  pre-cull still fills most of the nominal budget from the valid half | n=1009 target=1000
PASS  pre-cull symmetric: zero inside a right-half mask | inside=0
PASS  mask of a different size does not crash (resized per level)
```

### 单测抓到的两个真实缺陷（都已修）
1. **`static const bool` 缓存了首次调用的环境变量值**，导致同一进程内开关永远保持第一次的状态。
   已改为每次调用都读。**这个 bug 不会在 A/B 正式运行中暴露**（两组是两个进程），
   只有单测能抓到。
2. **关键点坐标是相对 `minBorderX/Y` 的**（循环只加 `j*wCell`，不加 `iniX`），
   索引掩码时不补这个偏移会**在边界漏掉关键点**。表现为**左右不对称**：
   左半掩码看起来正常，右半掩码漏 93 个点。已补 `+ minBorderX/Y`。

## 3. A/B 配对比较（同一输入帧，非同一序号）

因两组的关键帧集合不同（A 21 帧 / B 28 帧），按**帧时间戳**配对，得 9 个共同帧：

| 量 | A 原生 | B 预剔除 | 差 |
|---|---:|---:|---:|
| 每帧特征中位 | **1186** | **1502** | **+316** |
| 范围 | 1043 – 1387 | 1496 – 1509 | — |
| 总特征数增幅 | — | — | **+24.85%** |
| B 多于 A 的帧 | — | — | **9 / 9** |

逐帧（A → B）：
```
1106 -> 1502  +396
1105 -> 1496  +391
1043 -> 1499  +456
1186 -> 1502  +316
1215 -> 1502  +287
1172 -> 1501  +329
1262 -> 1509  +247
1354 -> 1506  +152
1387 -> 1504  +117
```

### 解读
- 名义预算 = `nFeatures*1.5`。B 稳定落在 ~1500 → **几乎完全打满**。
- A 落在 1043–1387 → **只用到 79% 左右**，损失量随动态区角点多少而变。
- 这与假设完全一致：**1.5× 过采样并不能补偿事后删除**，因为被删的特征已经占用了
  八叉树的分配预算。
- A 随帧波动、B 几乎恒定，这个对比是结构性的，不是噪声。

## 4. **不能**据此主张的（必须一起引用）

1. **特征更多 ≠ 几何约束更好**。本报告只测数量与分布，**没有**测：
   几何一致匹配数、匹配正确率、PnP 成功率、位姿误差、有效三角化比例。
2. 只有 **9 个配对帧**、**一条序列**（fr3_sitting_xyz 前 120 帧）。无跨序列重复。
3. 跨运行噪声底是**位姿** 0.404 cm 中位 / 3.263 cm 最大；特征数本身也受关键帧选择影响，
   所以配对只是"同一帧上"的比较，不是端到端重复。
4. **C 组（后置补提取）尚未实现**，所以还不知道"简单补提取"能否达到 B 的效果。
   如果 C 等效，则结论是 `SIMPLE_BASELINE_SUFFICIENT`，不是新机制。

## 5. 下一步

1. 实现 **C**：事后删除后，在有效静态区做一次受限补提取；
2. 三组同帧、同 mask、同预算对照；
3. **几何层指标**：静态支持数、PnP 内点、位姿误差——这才是判据；
4. 多序列重复（walking_halfsphere / walking_xyz）+ 与噪声底对照。
