# P5 最小运行回归（2026-10-23）

## 0. 判决：`TECHNICAL_REGRESSION_PASS`

冻结环境可等价恢复 → 属指令 §2 的**情况 A**，可直接执行原冻结追加（B1_02 → B0_02 → B0_03 → B1_03）。

## 1. 身份核对（先于运行）

对 4 个历史 `run.json` 逐项比对当前磁盘文件：

| 运行 | binary | core | yaml | association |
|---|---|---|---|---|
| desk/B0 | OK | OK | OK | OK |
| desk/B1 | OK | OK | OK | OK |
| large_cabinet/B0 | OK | OK | OK | OK |
| large_cabinet/B1 | OK | OK | OK | OK |

**16/16 全部吻合**。被核对的文件：

| 文件 | sha256 |
|---|---|
| `build/rgbd_screen` | `9e6d97523fc32e1b15791ab3ea29ded1583876b7587b2b402646d800391efb25` |
| `build/libORB_SLAM3.so` | `c9f08e6c3998c00d1f1d5272c045ff5b70c40e33458a6bc996cff493e8c56b66` |

## 2. 最小运行（独立目录，**不计入 4 次预算**）

输入：`rgbd_dataset_freiburg1_desk` 的**前 120 条关联**（从原 associations.txt 截取，
原文件未改动），输出到 `p5_regression/out/`。

```
LD_LIBRARY_PATH=<build>:<local/lib> rgbd_screen \
  ORBvoc.txt config/desk.yaml <desk_dir> associations_120.txt B0 <out>
```

| 检查 | 结果 |
|---|---|
| 退出码 | **0** |
| 日志结尾 | `COMPLETE 120` |
| OnlineTrajectory.txt | **120 行**（输入 120 → 覆盖 100%） |
| CameraTrajectory.txt | **120 行** |
| KeyFrameTrajectory.txt | 34 行 |
| frame_states.csv | 已生成，120 行 |
| `state` 取值 | 全部为数值码 **2**，`pose_valid` 全部 **1** |
| 与历史一致性 | 历史 `results/desk/B0/frame_states.csv`（573 行）同样是 state=2 / pose_valid=1 **全部行**，分布一致 |
| 坐标系 | TUM 格式 `t x y z qx qy qz qw`，首帧位于原点 |

> 一次自查更正：我最初把 `state` 当作字符串与 `'OK'` 比较，得到"0 帧 OK"，差点据此误判回归失败。
> `state` 是数值状态码，历史运行同样是 2，**所以这是吻合而非异常**。

## 3. 发现的一个复现陷阱（新知识）

`rgbd_screen` 把 `CameraTrajectory.txt` / `KeyFrameTrajectory.txt` /
`OnlineTrajectory.txt` / `frame_states.csv` **全部写到进程当前工作目录**，不是写到最后一个
参数指定的目录。历史运行能对，是因为 `run_four.py:17` 用了 `cwd=out`。

**复现时必须显式设置 cwd**，否则轨迹会散落到调用者的工作目录（本轮第一次运行就踩到了，
产物已回收至本目录）。这条已写入 `REPRODUCE` 注意事项。

## 4. 仍待办

- 本回归只验证"能跑、覆盖完整、坐标口径一致"，**未**验证数值可复现（那需要重跑冻结条件，
  与 4 次预算冲突）。
- 4 次冻结追加尚未执行；执行前须先冻结 P7-A 位姿评价器（指令 §2/§4）。
