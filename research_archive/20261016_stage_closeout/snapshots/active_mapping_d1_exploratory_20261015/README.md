# D1受限探索性资格工作区

主报告：[REPORT.md](REPORT.md)。实际决定：[DECISION.json](results/DECISION.json)。

CNN最终提取通过；原生停止事件/实际遗漏入口/合法共同状态未资格。ROS技术0/1，科学0/8。不要直接启动旧或新任务凑预算。

- [V2协议](protocol/D1_EXPLORATORY_PROTOCOL_V2.md)、[最终封存](audit/protocol_freeze.json)，历史版本另存。
- [权威推理输出](results/phase0_qualified_extraction.json)、[观测CSV](results/cnn_observations.csv)。
- [全数组检查](audit/loaded_weights.json)、[计算图提取证明](audit/forward_graph_extraction.json)。
- [候选几何](results/phase1_candidates.json)、[事件审查](results/phase2_event_opportunity.json)。
- [CNN概率图](figures/phase0_p_ex.png)、[原生地图几何图](figures/phase1_native_candidates.png)。

**不要引用`results/phase0_inference.json`为原模型结果**：它是weights=None变体，虽444数组加载全等，却遗漏无参数缩放层；等价性已否定，见audit/weights_none_equivalence_rejection.json。

CPU运行库仅在runtime/tf；作者H5、已取得原始小图、失败日志保留。原始输入不是Grad-CAM图。Phase0模型没有训练/微调。原构造计算保留，仅省去完整H5加载之前冗余的ImageNet初始化I/O。

只读轻量复核（不启动ROS/模型）：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 code/test_geometry.py -v
```

完整推理执行命令、退出码与失败记录见audit/cnn_attempt01—04.json及对应log。现有推理脚本拒绝覆盖结果；复验应建立新输出根和单独账本，不在此目录直接重跑。不得把工程复验称为独立团队科学验证。
