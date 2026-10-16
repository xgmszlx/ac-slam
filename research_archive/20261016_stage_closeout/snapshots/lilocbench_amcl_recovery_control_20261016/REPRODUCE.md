# 复查与复算

旧只读基础：`/home/wcqw/lilocbench_amcl_validation_20261016`。

本轮两次科学运行已完成，预算关闭。以下运行命令为实际执行记录，不授权重新执行；结果目录使用exclusive mkdir防止覆盖：

```bash
source /opt/ros/noetic/setup.bash
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 code/run.py A1_R0
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 code/run.py A2_R0
```

`protocol/design_frozen.json`登记顺序、唯一参数变化、seed1702、误差起点与三秒持续规则。`run_inputs_frozen.json`在任何科学运行前登记数据、执行程序、库、配置、代码hash。runner仅访问旧map和topic别名bag、原先冻结的初始化参数，不读GT流。采集器不访问GT。

构建：`python3 code/prepare_pf.py`，只编译PF的pf.c，链接原五个其他PF object。`audit/build.json`保存完整编译/链接命令；`audit/recovery_readonly.patch`是相对旧v2的全部变化；原v2来源与两轮所有源码不变。`audit/ldd.txt`记录新PF库路径。无需安装或网络。

离线复算命令（已执行）：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 code/evaluate_one.py A1_R0
PYTHONDONTWRITEBYTECODE=1 python3 code/evaluate_one.py A2_R0
PYTHONDONTWRITEBYTECODE=1 python3 code/analyze.py
```

使用已有Anaconda Python3.12、numpy/scipy/matplotlib及原目录局部Typer依赖。旧官方评价模块只读复用，不改数学；path-only diff见audit。命令会改写本轮派生评价文件，原始trajectory/log/parameters和旧结果不改。

软件数值控制：`tests/pf_fixture.c`在旧/新PF库两个独立进程，比较所有粒子pose/weight及随机流；stdout/stderr原件与hash在audit。夹具不是真实bag运行，不提供旧ON的恢复事件证据。

主数据：`results/comparison_metrics.csv`、`onsets.json`、`recovery_summary.json`、两个逐更新recovery_events.csv，以及每个运行目录的原始trajectory/observations/launch/resource/run/parameters。旧ON与A0由绝对reference路径和旧manifest固定；没有复制或覆盖它们。
