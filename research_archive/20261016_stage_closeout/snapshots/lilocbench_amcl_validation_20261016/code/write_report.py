from pathlib import Path
import json,csv
p=Path(__file__).resolve().parents[1];rows=list(csv.DictReader((p/'results/all_run_metrics.csv').open()));table=[]
for seq in ['static_0','lt_changes_0']:
 for model in ['A0','A1','A2']:
  g=[r for r in rows if r['binary']=='diagnostic' and r['sequence']==seq and r['config']==model]
  def rg(k,n=3):v=[float(r[k]) for r in g];return f'{min(v):.{n}f}–{max(v):.{n}f}'
  seed='1、1（非独立种子）' if seq=='static_0' and model=='A0' else '1、1702'
  table.append(f"| {seq} | {model} | {seed} | {rg('official_position_RMSE_m')} | {rg('official_yaw_RMSE_deg',2)} | {rg('position_p95_m')} | {rg('position_max_m')} | {rg('position_high_over_0p2m_duration_s',1)} |")
text='''# LILocBench地图辅助二维激光定位：原生基线与跳束审查

2026-10-16。**最终决策：BASELINE_READY。** 数据、官方评价和原生AMCL对照已取得可信结果。长期变化序列存在重复定位损失，beam skipping未充分缓解；但**观测权重、原生随机恢复和地图别名的作用尚未隔离**，当前不认领新的观测处理机制，不开发SCI方法。

状态ANALYZED，非独立团队复验。标签：实测＝原始文件/本机执行/离线复算；源码支持＝固定作者实现；推测/UNKNOWN＝未经干预确认。不同轨迹的静态/变化序列不是严格因果配对；本轮没有改变环境、噪声、阈值寻找失败。

## A–C．数据、官方评价与真实配置

按最新指示使用系统盘独立目录。开始可用约16.3GiB，预留5GiB；没有扩容、挂载新分区、删除资料或恢复旧研究。数据来自[LILocBench官方页](https://www.ipb.uni-bonn.de/html/projects/localization_benchmark/)，未下载RGB-D或补充序列。

| 数据资格（实测） | static_0 | lt_changes_0 |
|---|---:|---:|
| 原始无相机bag字节 | 141,839,376 | 103,773,946 |
| 完整遍历消息数 | 117,093 | 85,117 |
| 前置LaserScan | 8,982 | 6,540 |
| GT行数 / GT时长 | 11,929 / 598.757s | 8,700 / 435.955s |
| 时间戳 | 严格递增 | 严格递增 |

消息总数以[audit原始数据](audit/static_0_bag.json)及[变化序列](audit/lt_changes_0_bag.json)为准；所有包完成Content-Length验收、SHA256登记、ROS1完整读取，map/GT/example ZIP通过CRC。地图分辨率0.05m、原点[-25,-25,0]。GT是官方共同全局坐标下base_link，Z约−1.45m不用于二维误差；不做SE2/SE3最佳对齐。

真实数据流：官方前置扫描＋原始odom→base_link TF＋原始base_link→scan_front_link外参 → 官方AMCL → `amcl_pose`、粒子云、map→odom。轮式里程计在包中另有nav_msgs/Odometry；AMCL实际消费对应的**TF**，不是另接一套里程计。外参全程恒定：[0.30455923,−0.00597687,0.165]m，偏航约1.1005°。扫描811束、约15Hz、270°、原消息range_min≈0.05m/range_max=100m；没有套用Stage值。未发现输入map→odom或全局GT位姿TF；`base_link→gt_camera`只是传感器外参，不是在线GT。

[官方评价代码](https://github.com/PRBonn/LILocBench)固定`68e86f33ae3ff660444b92093fb98ca4d5633b46`。先运行未修改官方CLI，成功复算作者示例12条轨迹，**总分23.1566563316**；独立XY/yaw数学与12条结果一致。作者没有给出本轮可核对的预期金标准分数，因此不声称与某个已发布分数完全相同。示例三个run代表不同起点，不是随机重复；示例初始估计可偏离GT十余米，不能当本轮近初始位姿tracking结果。见[作者结果专用表](results/author_example_metrics.csv)、[官方HTML](results/official_example/detailed_results.html)。

官方评价没有空间对齐，但会在首尾缺口重复端点位姿；另报告不外推、原生输出时刻误差及时间支持。官方收敛图角度转换存在源码/控制测试证实的问题，**评分计算正确**；不使用该图认证收敛，源码和原输出不改。[评价检查](audit/evaluation_checks.json)。仅安装45KB量级Typer包至本目录，未改系统Python、未安装大型依赖。

AMCL官方Noetic包`1.17.3-1focal.20250521.001518`，固定官方源码tag1.17.3、commit`f13af47ee2bca6c3bf99db2965e46e55303f6e66`；dpkg校验无变更，9份公开header逐字节一致。这不是对安装二进制完整构建来源的逐字节证明。[版本](audit/amcl_version.json)。共同配置：

- 全向`omni-corrected`；五个odom_alpha均0.2；粒子预算1000–10000；max_beams=100；sigma_hit=0.2m，z_hit/rand=0.95/0.05。
- update_min_d=0.2m、update_min_a=π/6，resample_interval=1；原生恢复slow/fast=0.001/0.1保持开启；初始化均值只取一次官方初始GT的XY/yaw，标准差0.2m/0.2m/10°。没有全局初始化服务或在线GT纠偏。
- A0=likelihood_field；A1=likelihood_field_prob且skip=false；A2同A1但skip=true。skip distance/threshold/error threshold=0.5m/0.3/0.9，不调参。
- A0实际floor步长8、102个采样槽；A1/A2 ceil步长9、91个采样槽。相同max_beams参数不等于不同原生模型实际使用相同束数；**A0/A1不能隔离成beam skipping效果**。A1/A2实际束数及每个种子的708个变化序列sensor-update身份均相同。

完整参数、命令、资源、轨迹和退出状态分别保存在每次results目录；[冻结协议](protocol/runs_frozen.json)及后续工程修正登记全部保留，[执行说明](REPRODUCE.md)。

## D–E．A0/A1/A2实际结果

先完成4次安装二进制原生资格运行；另12次官方源码副本运行用于观测诊断/重复，**以下主表仅汇总后者，不混合二进制版本**。原生资格位置RMSE：static A0/A1=0.119158/0.037254m；变化A0/A1=0.541211/10.336049m。全部16条有效离线运行退出0，完整输入，未挑最佳。

| 序列 | 配置 | 实际初始化种子 | 位置RMSE m | 航向RMSE ° | 位置P95 m | 最大误差 m | >0.2m时长 s |
|---|---|---|---:|---:|---:|---:|---:|
'''+ '\n'.join(table)+'''

[逐次16条指标表](results/all_run_metrics.csv)含全部原始指标、CPU时间和内存。所有运行观测到全部8,982/6,540输入扫描；有效位姿时间跨度覆盖GT约99.908%/99.621%。这是跨度覆盖，**不是逐扫描成功定位率**。受运动阈值控制，每次只输出约967/707–708条AMCL位姿；最长输出间隔约2.733/2.534s，不据此称为失跟。1s和2s的严格插值支持覆盖另列CSV；官方首尾填充值不伪装为原生返回。

A0静态用户CPU49.18–73.55s、变化41.90–42.19s；A1/A2静态约5.36–5.63s、变化约4.55–4.87s。相同粒子预算下KLD实际粒子数可不同，不能把这些差别单独归为跳束加速。RSS约几十MiB；日志/采集、原生离线TF重复发布开销计入。没有宣称实时机器人资格或GPU加速。

![完整误差、离线地图冲突及原生跳束时间线](figures/main_timelines.png)

**实测**：静态A1/A2健康；长期变化中A1/A2两种实际初始化都出现米级损失。A2并未通过减少困难输出得到低误差，但改善不一致：种子1位置10.336→7.275m，种子1702为6.900→6.726m，而后者航向95.47→106.83°恶化。A0是现成更稳健的竞争者，变化位置约0.43m，仍有1.60–1.69m最大误差。**不能跳过A0/简单参数，直接宣称需要新模型。**

## F–G．真实案例与beam skipping行为

A2静态实际跳束963/967及964/967个更新；变化为656/708及657/708。这里指启用事件，不是跳过束的比例。静态物理采样槽跳过比例中位0、P95约3.30%；变化中位约5.49%/2.20%、P95约27.47%/28.79%、最大57.14%/58.24%。采样槽可能包含invalid/max-range读数，不能全叫有效返回束；另9个未采样分配槽不计入这个物理槽分母。[beam_summary](results/beam_summary.json)及逐次beam_events.json。

**四次A2的全部观测回退均为0。** 不支持“这组数据已复现过度跳束触发全部回退”的说法。固定源码有未使用零槽进入回退积分的潜在实现问题，但本轮没有触发，不能用来解释当前损失，也没有为它修改原算法。

原生converged只是粒子XY集中判据，不是定位正确。变化A2两个种子分别有539/656、448/657个有效跳束更新发生于离线位置误差>0.2m时。**支持‘错误位姿也可能被标记收敛并继续跳束’的共现事实，不证明跳束导致了初始错误。**

固定每10帧一次的OFFLINE_DIAGNOSTIC：GT位姿下前置端点距旧占据地图>0.5m的比例，静态中位0/P95 0.77%，变化中位2.47%/P95 21.09%。这支持观测与旧地图一致性分布不同，但不是变化真值标签；不同路径、扫描畸变、地图离散和GT误差仍有影响。

![两个事后诊断案例；不是在线GT选择](figures/changed_map_cases.png)

案例按登记规则事后选取，完整曲线不删：①约84.05s，GT端点不一致仅1.36%，A1仍偏22.50m、A2偏2.77m，说明**当前地图冲突少不等于历史定位错误已消除**；②约258.71s，A2最大跳束事件附近，GT不一致约6.17%，A1/A2偏8.76/8.24m。所示扫描是固定抽样中最近者，与目标事件差0.293/0.066s；不伪装精确同一时刻的粒子内点或原生观测分类真值。[案例原始记录](results/case_records.json)。

## H．重复、工程失败与证据限制

首次修补只在pf_alloc设种子，遗漏了原生Gaussian分配时再次设种子。因此名为1701的运行及已经开始的1702-static-A0，实际初始Gaussian种子均1；**目录名不改、结果不改，不能当独立1701/1702重复**。暂停后仅修正5个未运行预算槽，独立v2库保留v1；实际Gaussian种子1702有直接日志和分配器随机流单元测试。静态A0两个都是seed1，这是明确缺口，不追加补跑。[种子账本](audit/effective_seed_register.json)、[分配器测试](audit/gaussian_seed_test.json)。

静态A0相同初始种子两次也有48个sensor-update时间身份不同，RMSE差约1.0mm；这属于运行/阈值选帧变异，不是纯随机种子效应。变化A1/A2同种子对的708个更新身份完全一致，是真实同输入更新的跳束对照。n=2仅报告范围，不给显著性、置信区间或跨场景推广。

两次较早ROS尝试均完整保留：绝对路径launch解析失败（未送扫描）；修正后8倍外部回放虽然完成，却有TF积压，原始3.065m误差**只作技术失败记录，不作为科学结果**。随后使用官方现成`--run-from-bag`，没有重写滤波器：仅把原bag的`/tf`和前置扫描别名为它硬编码的`tf/base_scan`，逐消息原始字节、顺序、header/record时间回读hash完全一致。完整离线16次没有时间外推错误。原生函数重复发布/插入相同TF导致的重复数据警告不是冲突发布者；实际观测到每条所需TF只有同一父节点/发布节点。[源/时间审查](audit/SOURCE_AUDIT.md)。

该原生离线模式**不使用模拟时钟**：ROS壁钟只用于管理、耗时和粒子云标头，估计传播/输出使用原始扫描与odom TF时间。粒子分布按实际壁钟采样存储，不冒充逐scan GT配对。没有声称在线实时回放已合格。诊断只加计数日志及随机实现控制；不修改权重/运动/重采样公式，但不宣称与安装二进制普遍逐位等价。小型补丁、两份库、日志和冻结版本均保留。

## I–J．机制冲突、未解决问题和唯一下一步

[Akai JFR2023作者稿§4.5.1/6.3.1](https://arxiv.org/pdf/2205.04769)已经联合处理已知/未知观测与位姿，并明确讨论鲁棒抑制与初始偏差纠正的取舍。宽泛‘降低过时观测权重且保留纠偏’**不是新问题/新机制**。当前实验没有证明超过这类方法的独有需求。

在AMCL证据通过后，仅核查[als_ros固定launch](https://github.com/NaokiAkai/als_ros/blob/433f3b920245979f40ad5cd198293d256434365e/src/als_ros/launch/mcl.launch)：类别条件模型默认2、全向默认false、可靠性估计默认false、全局采样默认false，额外随机粒子默认true。README对默认可靠性的描述不能替代实际配置；本机Noetic编译/运行仍UNKNOWN，没有部署它或把默认模型称完整重定位框架。[launch审查](audit/als_launch_audit.json)。

**仍为UNKNOWN**：简单参数能否消除损失；全局随机粒子注入是否是大跳变主因；具体跳过的束是否属于过时结构还是位姿偏差；scan去畸变/地图表示/运动噪声各自贡献；类别条件MCL是否已充分解决。当前slow/fast=0.001/0.1会启用原生augmented-MCL恢复，虽非全局初始化，却允许全局随机粒子，未记录逐次注入数量。这是必须先控制的竞争解释。

**下一步唯一建议：只做原生恢复注入的参数反证，不接als_ros、不设计新权重。** 复用当前seed1702、lt_changes_0的A1/A2作为恢复开启对照；若另获下一轮授权，各追加一次相同输入/种子/配置，只将recovery_alpha_slow和fast都设0，共2次。若损失随此简单设置消失，优先接受现有方法/配置足够，不开发复杂模型；若仍有重复残差，再决定是否值得引入类别条件MCL。两次都不自动执行。

**BASELINE_READY的边界**：已得到可信、可复查的原生定位基线；不是MECHANISM_CANDIDATE立项、不是新算法有效或SCI新颖性结论。目标中的‘大量跳束再全量纳回’未观测；继续科学投入应先通过上述一个低成本反证，不能为保留投入而增加模块。

保护范围：旧11份顶层报告、主仓HEAD/status/diff及两个未提交文件前后校验；本轮所有新数据/代码/结果在独立目录。没有声称重哈希全部旧图像和子项目。最终[audit/protection_after.json](audit/protection_after.json)、MANIFEST.json和进程清理检查可复核。
'''
# Exact observed total, not an estimate from nominal 15Hz.
bag=json.loads((p/'audit/static_0_bag.json').read_text());text=text.replace('117,093',f"{bag['messages_read']:,}")
(p/'REPORT.md').write_text(text)
