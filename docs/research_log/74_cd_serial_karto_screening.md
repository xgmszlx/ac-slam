# 74 — CD-A0/A1 隔离单线程 Karto 技术筛选

日期：2026-10-08
Task ID：`CD_A0_A1_SERIAL_KARTO_SCREENING`
任务类型：`TECHNICAL_ARCHITECTURE_SCREENING_ONLY`
最终 gate：**`SERIAL_KARTO_SCREENING_FAIL`**

## 1. 基线、边界与冻结来源

起始本地及远端 `research/phase4c-formal` 均为 `32b295d7599531bc913d7a19fb0c7de09a1ce495`，开始时无旧文件的工作区改动。CD-F2 保持 `MULTISTABILITY_CONFIRMED_CAUSE_UNRESOLVED`；旧 CD、Amendment 1、v14 的正式判决不变。本轮只使用冻结 qualification manifest 中的 canonical prefix 和 mapper 参数，从未读取 CD Amendment 1 的 post-treatment scientific endpoint、计算 CD 科学指标或发布 treatment suffix。

所有构建、raw replay 和技术分析在 `results/realizability_pilot/p1_cd_serial_backend_screening_20261008/`。两个 catkin 工作区及 24 次运行 raw 保留在本地并被该目录的 `.gitignore` 排除；提交的是源补丁、运行工具、冻结协议、哈希清单、ledger 和分析。`analysis/raw_artifact_manifest.json` 列出本地 24-run raw 的 **504 个文件**及各自 SHA-256；它不是旧实验 ignored raw 的总哈希。

## 2. A0：源码和链接审计

生产 `MultiMapper.cpp:71` 调用 `OpenMapper(true)`。独立纯串行副本仅改为 `false`；`OpenMapper.h` 将构造参数存入 `m_MultiThreaded`。`false` 同时切换 `ScanMatcherGridSetBank` 分配/checkout、`CorrelateScan` 的 TBB `parallel_for` → Y/X/angle 串行回退、`LinkNearChains` 并行匹配后链接 → 串行即时链接、以及 correlation/search grid 访问。详见 `audit/source_execution_path.md`。因此它是**新技术后端**，不能沿用旧多线程图作为串行数值门槛。

CMake 将同一 `KARTO_SOURCE_FILES` 同时编入 `libOpenKarto.so` 和 `mapper`，而 `libMultiMapper.so` 链接 `libOpenKarto.so`。`nm/readelf` 确认重复导出；实际 `LD_DEBUG=bindings` 表明该启动方式下 `libMultiMapper.so` 的 OpenMapper 构造函数引用绑定到**隔离 mapper 可执行文件**中的定义；若干 `libOpenKarto.so` 自身引用亦如此。`ldd`、RUNPATH 和运行中 `/proc/<pid>/maps` 均证实 mapper/MultiMapper/OpenKarto/SelfLocalizer 来自隔离目录，无生产共享库混入。此为**已观测符号来源**，不是 ODR bug 的证明。见 `audit/build_dependency_graph.json`、`audit/symbol_and_library_audit.md`、`audit/runtime_library_provenance.json`。

## 3. A0：隔离构建、运行真实性与 smoke

纯串行版：`isolated_catkin`，mapper SHA-256 `14ee1688c828ebc152aef2932697ba8ab0300d40b0cde48e9cd9e5b7cd955b70`。独立观测版：`isolated_catkin_observed`，mapper SHA-256 `d5fe41a093669d62608667895591912c282c1e4e89f32f53362340c5df207ee0`。观测版只额外报告 `IsMultiThreaded`、`doSPA(40)` 已实际调用，并将 graph JSON 的 double 用 `max_digits10` 输出；它与纯版**不是同一二进制**。两者的 `libMultiMapper.so`、`libOpenKarto.so`、源码 SHA、编译器、CMake、TBB、ROS/catkin、实际映射的系统库及原始补丁见 `audit/isolated_build_manifest.json`、`audit/serial_candidate.patch`、`audit/observed_candidate.patch` 和 `audit/observability_diff.md`。`USE_TBB` 仍为 ON；已观测 `IsMultiThreaded=0`，不是靠“只设一个线程”的推断。

两个隔离构建使用 `/usr/bin/python3` 3.8.10、GCC 9.4.0、CMake 3.16.3、Release `-O3 -DNDEBUG`。唯一构建依赖例外是从生产 `devel/include` 引用已有的 `cpp_solver/PoseGraph.h` **头文件**；生产二进制及共享库没有被覆盖或运行时加载。

A0 使用与 A1 三历史无关的 v13 技术输入 `target_A/seed_81001`：33/33 scan callback、同步 snapshot、33 节点、38 边和 38 条 constraint provenance（32 previous-scan、6 running-chain）。观测版日志有 `IsMultiThreaded=0`，且 `SpaSolver::Compute` 真正执行 `doSPA(40)`；同一技术输入下观测版 graph 四舍五入到旧六位小数语义与纯串行版一致。此 smoke **没有** `TRY_CLOSE_LOOP` 成功约束，不能说已验证真正闭环行为。原始图/provenance SHA 分别在纯版为 `714e6105...`/`2f06f318...`，观测版最终 smoke 为 `d5b32c3c...`/`6a2357ed...`；完整哈希可用 `sha256sum` 复核本地 `technical/smoke_pure/`、`technical/smoke_observed_final/`。见 `audit/serial_mode_evidence.md`。

观测版 33-scan smoke 的 replay wall time 7.199 s、mapper CPU 0.47 s user + 0.01 s system、峰值 RSS 47,013,888 bytes。F2 生产 24 次技术 replay 历史记录 wall median 7.596 s，但历史输入不同、CPU/RSS 测量口径不一致，**不能据此宣称速度改善或恶化**。见 `audit/serial_backend_performance.md`。

## 4. A1：运行前冻结的协议

A0 通过运行来源、serial flag、同步 barrier、约束/provenance 与实际优化调用的最低技术条件后，先运行 8 项静态回归测试，**8/8 通过**，再写入只创建一次的协议：

- `protocol/a1_preregistration.json` SHA-256 `c942937abeecc449309314a6f2ab066199034fefe76e20a8e64f8cd07af0a8c5`
- `protocol/frozen_run_manifest.json` SHA-256 `d64ca330b1cd3eead49e9b6399ddacfa8a4254f2d44426ec971445fdd30f5c57`
- `protocol/frozen_hashes.json` SHA-256 `264697615d783af34b4402ace1648b6b84aaa06dd6607f34e393bcccde7f38c4`

预指定三个 histories：`target_A_H1` seed 101002（35 条），`target_A_H2` seed 101003（35 条），`target_B_H1` seed 102001（33 条）。每个 history 的 session1/P/repeat1 是**唯一**新串行参考图（ordinals 1/2/3）；没有改选。固定顺序为 3 histories × P/B × 2 sessions × 2 repeats = 24。B 使用同一新串行参考、同一六位小数零容差判断；隔离 runner 在入口**拒绝任何 combined stream**，未发送 suffix；不读取旧 Q 图作为 gate。预先规定任何有效结构或六位小数分叉即 `FAIL`，若仅高精度分叉则 `REVIEW`，不从失败样本反推容差。完整停止规则和输出路径在冻结 JSON。

静态测试命令：

```bash
CD_SERIAL_WS=/home/wcqw/ac-slam/results/realizability_pilot/p1_cd_serial_backend_screening_20261008/isolated_catkin_observed /usr/bin/python3 -B -m unittest discover -s results/realizability_pilot/p1_cd_serial_backend_screening_20261008/technical -p 'test_a1_screen.py' -v
```

## 5. A1：实际执行、参考图与比较

两个独立 runner 会话分别完成 12 次，合计 **24/24**；每次 fresh ROS master、fresh mapper、独立 output。所有 24 次都满足前缀 byte/semantic SHA、publisher/subscriber 连接、各自 expected count = published = processed callback、同步 dump、库路径/文件 SHA 与 A0 相同、edge provenance 数 = graph edge 数，且 **0 suffix**。独立 `analysis/a1_postcheck.json` 对上述各项逐 run 核验：24/24 全通过。`technical/a1_run_ledger.csv`、`technical/prefix_input_inventory.json` 和 `analysis/raw_artifact_manifest.json` 给出索引及各 raw 哈希。

| History | 新串行参考 ordinal | 结构（所有 8 次） | 六位小数与参考一致 | 高精度与参考一致 | 六位小数数值簇 |
|---|---:|---|---:|---:|---|
| `target_A_H1` | 1 | 35 节点 / 41 边，8/8 一致 | **2/8** | 2/8 | `[1,7]`、`[4,10,13,16,19,24]` |
| `target_A_H2` | 2 | 35 节点 / 42 边，8/8 一致 | 8/8 | 6/8 | 单簇 |
| `target_B_H1` | 3 | 33 节点 / 38 边，8/8 一致 | 8/8 | 6/8 | 单簇 |

H1 的六次非参考图相互一致；与参考图相比，最大 node XY 分量差 3×10⁻⁶ m，edge translation 分量差 2×10⁻⁶ m，协方差元素差 3.6×10⁻⁵，角度测量无变化。H2/B 的四个仅高精度差异最大约 1.78×10⁻¹⁵ m（B 另有约 2.17×10⁻¹⁹ rad 和 4.24×10⁻²² 协方差元素差）；这类差异**没有被事后当成通过容差**。H1 的六位小数分叉出现在 P 和 B、两会话中；固定顺序不能建立模式因果解释。

同 history 全对全共 84 对，精确端点顺序、节点/边属性和五项数值差异见 `analysis/graph_pairwise_comparison.csv`。新参考路径及图 SHA 在 `analysis/serial_reference_manifest.json`；数值簇见 `analysis/serialized_numeric_clusters.json`；高精度差异见 `analysis/high_precision_differences.csv`。`max_digits10` graph JSON 是可往返的**导出 double**，仍不是所有 Karto 内部状态的 bitwise snapshot。

24-run wall median 7.174 s，范围 6.968–7.380 s；mapper 峰值 RSS 最高 47.38 MB。性能仅描述这批新技术 replay，不能与旧 F2 的不同输入直接构成性能实验。见 `analysis/performance_summary.json`。

## 6. 判决、局限与冻结完整性

因为 24 次有效运行中同一 H1 前缀产生两个不同六位小数数值图，严格预注册 gate 为 **`SERIAL_KARTO_SCREENING_FAIL`**；不是 `PASS` 或只需高精度 review。此判决回答的是“当前隔离观测版单线程候选，在这三历史上能否通过零容差技术筛选”，答案为否。它**不证明**旧 TBB、动态符号重复或某个 matcher 分支是根因；也不证明纯串行版在 24-run 矩阵会作出相同结果。观测版与纯版只做过一条 A0 smoke 的六位小数等价验证，仪器化的时序影响仍可能存在。未把任何新结果用于旧 CD 缺失的三条 replay，也未改旧 gate。

原 CD 冻结聚合仍为 **3,881 文件 / `0725778cbcd223cea69384350bcedefc965c2bb8c75a32a484e1e7e4d747fd4b`**；v14 的 14 个既有 critical SHA 全相同；v14、v14-H、CD-T、原 CD、Amendment 1、CD-F2 的 tracked diff 均为空。该核对范围**不等于**对这些目录全部 ignored raw 的独立哈希。生产 `mapper`、`libMultiMapper.so`、`libOpenKarto.so` 的任务前后 SHA 分别固定为 `7ab54496...`、`a5338a33...`、`4a01ec77...`。见 `audit/protected_frozen_integrity.json`、`audit/production_integrity_before_after.json`。

## 7. 唯一建议的后续任务（未执行）

按冻结 `FAIL` 分支，**仅建议单独立项一次状态恢复型后端的最小可行性审计/PoC**：审查 ROS 1 `slam_toolbox` 在当前环境的兼容性，以及能否恢复完整匹配状态而非仅 pose graph。不要自动迁移，也不要启动新的 CD 科学 cohort。
