# 原生恢复逻辑与最小计数审查

固定官方 navigation 1.17.3 / f13af47ee2bca6c3bf99db2965e46e55303f6e66。只读复用上一轮 diagnostic_ws_v2；不修改旧源码或库。

- `amcl_node.cpp`读取recovery_alpha_slow/fast，传入pf_alloc；UpdateSensor之后按resample_interval调用pf_update_resample。selective_resampling=false，关闭恢复不关闭普通重采样。
- `pf_update_sensor`：sensor_fn返回未归一化总权重total；total>0时归一化，w_avg=total/N；零初值令w_slow=w_fast=w_avg，之后按各自alpha做指数更新。alpha均0时，在本次实际非零首更新之后，两者一直保持相等的首值。
- `pf_update_resample`：w_diff=max(0,1-w_fast/w_slow)。每个新粒子仍执行原有drand48()<w_diff判断；成立才调用random_pose_fn，AMCL将其绑定到地图空闲位置均匀抽样。否则按原累计归一化权重抽样，KLD停止规则不变。w_diff>0时原码重置slow/fast，未改。
- A0的LikelihoodFieldModel使用1+sum(pz^3)及floor步长；A1/A2的LikelihoodFieldModelProb使用exp(sum(log(pz)))及ceil步长。不是同一模型的skip开关。本轮仅A1/A2恢复开关对照，A0保留为强参照。

## 本轮补丁

仅重新编译pf.c。旧AMCL executable、amcl_sensors、amcl_map及pf_pdf/kdtree/vector/eig3/draw对象逐字节复用；实际Gaussian seed逻辑完全沿用已修正的v2。LD_LIBRARY_PATH仅用新pf库覆盖旧pf；实际RECOVERY_*输出及ldd登记证明其加载。没有新增动态拦截。

新增sensor后读统计：total、N、原生pre-resampling ESS、slow/fast、最大归一化权重、权重和、零值/非有限标志。新增resample前后日志及随机分支中的整数计数；不加随机数调用，不改判断、抽样、归一化或停止公式。额外O(N)只读统计和日志有开销，已计入资源，不能宣称普遍时序无影响。

`prepare_pf.py`撤销全部新增文本可精确还原v2源码；fixture在恢复开/关两种配置中，各12次sensor/resample之后的所有粒子位置/权重、slow/fast及下一随机数逐字相同。包含零total分支，恢复开启的夹具实际进入随机生成分支（见counter_positive_control.json）。夹具不是新LILocBench运行，不能补写历史ON事件。未作完整ROS逐位等价承诺。

## 新出现的全量回退/零总权重

本轮A2-R0在198.911742s一次回退，之前A2 ON为0次，这两个事实同时保留。811 ranges、step9仅填写91个物理槽，但分配和回退积分遍历100槽；额外9槽初始化为0且未在物理循环填写。回退执行log(0)使积分为负无穷并指数为0，是源码支持的零总权重路径，与实测total=0一致，不归因于“新的地图变化机制”。

pf_update_sensor的零total分支把粒子权重设为1/N，却没有补算n_effective的平方和；随后1/0保存为inf。这是原生ESS记账边界，不是有效样本数真的无穷。归一化粒子权重仍有限，selective_resampling=false，普通重采样实际继续执行。没有修复该工程行为，没有放宽阈值或重跑。

当次错误已经12.84m，前一更新12.85m；不能解释最初失准，更不能覆盖旧报告的“无回退”结果。
