# 原生观测公式、坐标和数值核对

来源：本机已固定navigation tag1.17.3 / f13af47ee2bca6c3bf99db2965e46e55303f6e66。使用旧diagnostic_ws_v2库及其只读源码；未修改任何作者库或估计器。

1. LikelihoodFieldModel的step=max(1,(range_count-1)/(max_beams-1))，整数除法。811、100得到8，共102个物理位置。LikelihoodFieldModelProb的step=max(1,ceil(range_count/double(max_beams)))，得到9，共91个位置。本轮主要比较使用索引0,9,...,810。
2. amcl_node先将range<=range_min改为range_max；range>range_max改为double最大值；其余保留（包括NaN）。两个模型均忽略range>=range_max和NaN。故91个物理位置不等于91个有效返回。本轮不使用此前Stage参数。
3. 激光平移在base frame下经机器人yaw旋转；SetLaserPose中的yaw为0。外参方向先用于转换扫描angle_min及angle_min+increment；原float32相加、tf2四元数乘积/getYaw及fmod展开由C++探针复现。避免双重添加1.1005°。
4. map_server原生loadMapFromFile以官方image/yaml参数TRINARY加载；不自行用PIL阈值推断occupancy。按原convertMap逻辑，0→free(-1)，100→occupied(+1)，其他→unknown(0)。Unknown不被当作occupied种子，但可继承附近occupied的距离场。
5. 使用旧libamcl_map的map_update_cspace，而非scipy近似距离变换。OccupancyGrid.resolution是float32，传入AMCL为0.05000000074505806；1000×1000地图的AMCL中心origin为[3.725290298461914e-7,同]，不是强行设为0。地图世界原点仍[-25,-25]。
6. 索引为floor((x-map.origin_x)/scale+0.5)+size_x/2；不是普通world-to-cell floor。离图距离2m。端点不进行新去畸变或ray casting；不因机器人底盘位置处于occupied/unknown而在评分中新增拒绝。候选底盘occupancy仅作辅助记录。
7. p_i=.95*exp(-d_i²/(2*.2²))+.05/range_max。没有1/(sqrt(2pi)*sigma)归一化项，不补加它；所有未知/离图处理沿用原码。A0式S=1+sum(p_i³)，A1式L=sum(log(p_i))。主比较使用完全相同的p_i，无beam skip。保留S的log和L，避免下溢；A0启发式归一化评分不冒称校准概率。
8. A2仅提供历史位姿候选。本轮没有历史逐束mask及精确粒子集，不能重现当时的A2跳束似然，也未用候选网格替代真实粒子来生成mask。

数值认证：native_probe.cpp仅是离线函数调用适配器，使用header访问控制宏调用已编译库的静态sensor函数，不修改其实现/类布局。每次单个测试sample权重为1，直接读取native原始评分；没有调用UpdateSensor、pf_update_resample、AMCL节点或任何完整滤波器。

同91束A0原生函数在探针里使用max_beams=91以产生stride9；这只是离线采样控制，不是新增AMCL运行/配置变更。A1原生max_beams=100同样stride9；另以原生A0 max_beams=100核对102位置支路。42个可用中心×3项聚合核验，最大log绝对差1.4211e-13，低于事前1e-10。无单独完整原生逐束trace，因此不宣称逐束内部打点全等；逐束Python概率可从固定地图和原生预处理结果重算。

候选位姿以原时间插值取得，非实际粒子。GT用官方intrinsic ZYX yaw；首版lowercase zyx在任何评分之前改正并重新冻结。首版代码/中心登记保留，不将其当实验。首0s附近没有AMCL输出，不外推。

约10s的配对可能使用稍晚于10s的右侧历史轨迹插值端点，只用于构造<=10s的候选；没有对10s之后扫描/误差作新分析。candidate_manifest中uses_after10s_bracket_only_for_inrange_time首版是未计算占位值，不能当事实；以results/interpolation_audit.json真实时间戳为准。约2s的A1插值跨越近20m/176°输出跳变，不能当已存在的粒子或物理运动；明确限制该样本的滤波器解释。
