# 独占资源锁与隔离实况

更新时间：2026-10-23

## 1. 锁表

| 锁 | 持有者 | 状态 | 说明 |
|---|---|---|---|
| `ROS_MASTER :11355` | L1 实验 | **HELD** | 独立 master，**不是**默认 11311。`ROS_HOME=logs/ros_home_l1`，`ROS_LOG_DIR` 独立 |
| `GPU_SLAM` | — | FREE | 本轮未用 GPU（RTX 4060 8 GB 空闲） |
| `GAZEBO_SIM` | — | FREE | 本轮未启动仿真 |
| `ROBOT_REAL` | — | FORBIDDEN | 无人值守禁止真机运动 |
| `BASELINE_BUILD` | — | FREE | 本轮未编译任何上游代码 |
| `DATA_MUTATION` | — | FREE | `datasets`/归档**只读**，未写入一个字节 |

## 2. 隔离实况（可核验）

### 2.1 源码隔离
- 上游仓库 `/home/wcqw/ac-slam`：HEAD `4746834f`，分支 `research/phase4c-formal`，20 个本地分支，7 个既有 worktree。
- 本轮**未**在该仓库创建新分支/worktree，**未** commit，**未** `reset`/`clean`/`stash`。
- 用户既有未提交修改**原样保留**（`ROOT_MANIFEST.json` 记录了 6 条 `git status` 条目）。
- 本轮全部新文件只写在 `/home/wcqw/slam_multi_direction_research/`。

### 2.2 数据隔离
- `datasets` 全部只读引用（`DATA_REGISTRY.csv` 逐项记 SHA-256）。
- 派生文件（`runs/*.bag`、`*.npy`、`*.csv`）全部写在 `experiments/L1/runs/`，**不回写**数据目录。

### 2.3 进程隔离
- 只有一个 ROS master（11355），只有一个 `hector_mapping` 实例同时运行。
- 序列之间**显式重启** hector（新地图），不跨序列复用状态（见 `run_g1.sh`）。
- 无 GPU 争用、无仿真、无真机。

### 2.4 输出隔离
- 每次运行写入不可复用目录 `runs/L1_G1_hector_<seq>_<UTCSTAMP>/`。
- 目录内容：`measure.bag`（原始消息）、`hector_{stdout,stderr}.log`、`play.log`、
  `record.log`、`play_exit_code`、`measure_bag_info.txt`。
- **失败同样保留**，不删、不补跑。

## 3. 与旧归档的关系

`research_archive/20261015..20261021` 的 9 个归档目录**全部只读**，本轮未修改任何文件。
新增结论一律写入新目录，旧 `REPORT.md` / `DECISION.json` / `final_gate.json` 保持原字节。
