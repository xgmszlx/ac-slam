# 2026-10-10 独立探索性再分析

本次由用户明确授权读取 CD Amendment 1 的成功科学分支。不是旧预注册分析的解锁或续跑。输入为既有 CD、v14、F2 与 v8 文件；没有 ROS 运行、后端迁移或模型训练。原锁、判决与数据未修改。

主要报告：[研究日志 76](../../../docs/research_log/76_local_observation_action_selection_exploratory.md)。

运行环境为离线 Python 3.12.7 / NumPy 1.26.4 / SciPy 1.13.1 / Matplotlib 3.9.2，**不改变 ROS 的 Python 环境**。从仓库根目录运行：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=tools/realizability_pilot \
  /home/wcqw/anaconda3/bin/python3 tools/realizability_pilot/test_action_selection_exploratory.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=tools/realizability_pilot \
  /home/wcqw/anaconda3/bin/python3 tools/realizability_pilot/action_selection_exploratory.py
```

脚本重新生成本目录 `analysis/` 和 `figures/`；不调用旧 gated pipeline。`analysis/environment.json` 保存版本，`input_integrity_manifest.json` 保存每个读取文件的 SHA256 与运行结束后的不变核验。JSON 写入函数拒绝旧结果目录；全部写入目标在新的分析目录。CSV 保留完整精度，报告显示舍入值。

关键输出：

- `cd_paired_history_results.csv`：15组，三个最终 J_T、三个配对差值与事后上界。
- `cd_branches.csv`：45分支的实际累计转角、动作完成时间、总观测时间、关键帧及坐标拼接审计。
- `cd_new_factor_details.csv`：137条新增边的端点、来源、协方差、匹配响应、连接范围与固定线性化删边贡献。
- `information_construction_audit.csv`、`common_historical_linearization_sensitivity.csv`：指标构造与敏感性核查。
- `v14_paired_results.csv`、`v14_recomputed_factors.csv`：不同协议的单独机制核查，不与CD合池。
- `historical_target_GT_sanity.csv`：历史目标状态的既有GT核查；不是新后缀或整条分支ATE。
- `existing_repeated_graph_J_T.csv`：已有生产图的重复性；不把串行前缀当作CD完整分支认证。
- 三张图：逐组收益、实际预算、后缀坐标拼接。
- `literature/method_sources.json` 与 `*_integrity.json`：七篇原文的方法位置、链接、版本和PDF读取说明。PDF/全文提取/局部渲染仅本地缓存，不入版本管理。

本机旧数据齐备，脚本本轮正常完成。若其他机器缺失旧 ignored capture/combined stream/trajectory 文件，需要取得同一SHA256的归档；不能把缺失数据默认为零结果。
