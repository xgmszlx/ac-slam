# P5 冻结实验环境身份链（2026-10-23 核实）

## 0. 关键发现：冻结实验**没有**用 sources 里那个库

`REPRODUCE.md` 记录运行时 `LD_LIBRARY_PATH=/home/wcqw/passive_rgbd_depth_screen_20261019/build:...`，
`run_four.py:12` 证实。所以真正被加载的是**诊断重建库**，不是
`sources/ORB_SLAM3-.../lib/libORB_SLAM3.so`。两者的 SHA256 不同：

| 文件 | size | sha256 |
|---|---:|---|
| `passive_rgbd_depth_screen_20261019/build/libORB_SLAM3.so`（实际使用） | 5,018,752 | `c9f08e6c3998c00d1f1d5272c045ff5b70c40e33458a6bc996cff493e8c56b66` |
| `sources/ORB_SLAM3-.../lib/libORB_SLAM3.so`（原始，未使用） | 5,018,696 | `a20db0416fc54ca5949e6b6ac834c12f59dc0bae5f08dc2945e46943a3532c46` |

> 上一轮我说"二进制存在且链接冻结库"——那只对 sources 那份成立，而 P5 实际用的是诊断库。
> 结论方向（情况 A 可恢复）不变，但**等价性证明的对象必须是诊断库，不是 sources 库**。

## 1. 入口链路（run_four.py:11-13）

```
binary : /home/wcqw/passive_rgbd_depth_screen_20261019/build/rgbd_screen
         sha256 9e6d97523fc32e1b15791ab3ea29ded1583876b7587b2b402646d800391efb25
core   : .../build/libORB_SLAM3.so   sha256 c9f08e6c...（上表）
env    : LD_LIBRARY_PATH=<build>:<passive_visual_slam_qualification_20261015>/local/lib
args   : <ORBvoc.txt> <config/<seq>.yaml> <dataset_dir> <associations.txt> <condition> <out>
```

每次运行的 `run.json` 自行记录 `binary_sha256 / core_sha256 / yaml_sha256 /
association_sha256 / frames_expected / start_unix / GT_online=false`。

## 2. 已存在的 4 次运行

`results/desk/{B0,B1}`、`results/large_cabinet/{B0,B1}` ——与原冻结协议
`B1_02 → B0_02 → B0_03 → B1_03` 的追加计划一致（当前每条件 2 次，计划补到 3 次）。

## 3. 等价性证明还缺什么（本轮未做）

1. 逐个比对现存 `run.json` 里的 `*_sha256` 与当前磁盘文件是否一致（文件未被改动）。
2. 用 `rgbd_screen` 做一次**最小运行回归**，确认退出码、输出轨迹帧数、坐标系口径。
3. 回归不通过 → 转情况 B（新基线），不与旧结果拼接。

## 4. 结论

`P5 = 情况 A（环境可等价恢复）`，**不需要任何编译**，`BASELINE_BUILD` 全部留给 P1。
追加运行仍受原冻结协议约束，且预登记须为独立 commit。
