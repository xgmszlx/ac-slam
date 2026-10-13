# 81 — 几何退化下定位可靠性与主动恢复：文献审计及资格筛选

2026-10-13。任务 `DOC81_LOCALIZATION_DEGRADATION_RECOVERY_FEASIBILITY`。

## 结论先说

**这次没有取得可判断新方向的科学结果，不能把它解释成“主动恢复又失败了”。**
实际止于新运行封装的技术资格：3次启动尝试全部保留，0条有效科学episode，恢复测试0次。
本轮停止继续仿真，不开发正式方法。它与Doc80停止纯旋转选向的科学/研究判断是两件事。

文献核验已经足以修正选题期待：

- “几何谱弱不一定是真实位姿不可用”已有OCE直接实验，不是新观点。
- “主动改变观测位置/朝向保持定位”已有LA-Planner、ActLoc及2026 LiDAR风险路径工作。
- “弱方向受限更新、外部先验辅助”已有X-ICP、GenZ、2DLIW等；改成二维不构成新意。

仍值得小规模验证的只剩一个具体必要条件：**现有二维Karto的真实任务误差是否在合理弱几何中
持续超出正常范围，并且有安全、低成本、真正改变约束几何的恢复机会？** 当前对此尚无合格数据。
不能据现有信息提出“可靠性+信息+成本”的正式方法或论文标题。

## 1. 仓库、冻结与工作区

开始时本地和远端 `research/phase4c-formal` 均为 `4746834ffa44504443fd07214105fe850d6f94e6`。
最新提交已包括Doc77连续原生任务、Doc78边界复核、Doc79同步观测与Doc80离线收敛审计。
Doc80的 `STOP_PURE_ROTATION_SELECTION` 保留：没有方向前置信号、固定L+解释不能排除、
修正GT未显示定位收益。这不被新问题的兴趣覆盖。

主工作区的 `same_input_replay.py` 和 `se2_information.py` 存在用户未提交改动；保留不动。
独立worktree **`/home/wcqw/ac-slam_doc81`**，新分支 **`research/localization-recovery-phase0`**。
采用稀疏检出减少磁盘复制；没有切换主工作区、reset/clean/force push。

旧Doc76–80、v14/CD及技术筛选没有成为新工具的输出目标。登记的34项旧关键文件、
生产/Doc79二进制和用户改动在结束时哈希不变；新分支仅新增本任务目录/报告。
这个核验不是旧ignored raw全树逐字节认证，保护还依赖独立写入路径与旧tracked diff不变。

## 2. 可复用资产和真实任务模式

复用了Stage原地图/机器人、Nav2D MoveTo/Operator、Doc79原生水位、串行同步graph导出与provenance。
**没有替换或重编译Karto**。第三次实际/proc/maps证实MultiMapper和OpenKarto来自旧Doc79 overlay；
SelfLocalizer来自旧underlay，但robot1运行模式为ST_MAPPING，不是已知地图定位。

map3位图只定义模拟环境，不给Karto或Nav2D加载静态全图。本轮任务是在线建图SLAM的固定导航任务，
不是“是否前往回访目标”或旧旋转选向实验。

采集代码继承提交版Doc79记录/导出，但覆盖控制路径，**删除继承旧GT到达判断的可能性**。
新控制只读map TF、冻结路线、MoveTo状态；GT只作只读记录及离线评价。严格同stamp TF失败保留缺失，
不拿最新TF冒充历史位置。

组件、潜在污染、是否编译/新增依赖分别见 `audit/reusable_component_audit.md`。
系统仍ROS Noetic/Python3.8；没有sudo安装或大规模重构。

## 3. 方法层面的文献结论

覆盖提示词12项；最接近的五项是LA-Planner、ActLoc、2026 Degradation-Aware Path Planning、OCE、X-ICP。
全文可用时核对方法/评价位置，全文不可用的两项不从摘要补全执行机制。

| 工作 | 已做到什么 | 与本轮问题的边界 |
|---|---|---|
| [LA-Planner，IROS2025](https://arxiv.org/html/2503.15273v2)，§III–V、§VI | 未知环境中用特征可见/共视图选局部position+yaw，再生成localizable corridor；比较Zhang/APACE-R/E | 仿真“失定位”用特征数持续低于门槛，真实RGB-D ORB-SLAM3实验另有OptiTrack APE。它不是只做静态地图避让；未显示本文所需的已退化后有限恢复对照 |
| [ActLoc，CoRL2025](https://proceedings.mlr.press/v305/li25b.html)，§3.2–3.5、§4 | 已知SfM地图+建图视点，预测相机yaw/pitch定位表现，沿waypoint序列兼顾平滑选视点 | 基本“历史观测感知可靠视点”已覆盖；我们无SfM相机链，不能靠二维传感器差别宣布创新 |
| [Degradation-Aware Perceptual Path Planning，CIS/RAM2026](https://ieeexplore.ieee.org/abstract/document/11668505/authors) | 摘要提出Hessian风险、compact 2D directional risk map、Hybrid A*惩罚 | DOI/会议收录已核实，**全文未获得**；地图假设、触发/恢复机制、最强基线及具体任务评价均未知，不将其不足当论文证据 |
| [OCE，2026-10-09](https://link.springer.com/article/10.1007/s43684-026-00144-1)，§3.3–3.4、§4.2 | 用LM梯度收缩区别半退化可用与实际位姿不可用；真值标签用0.5s相对误差及健康P99×3；有估计源切换与恢复滞回 | 直接覆盖“谱弱≠真实失败”。它的recovery是估计通道恢复，不是机器人换位置；3D GICP/LM诊断不能直接塞进相关性Karto |
| [X-ICP，T-RO2024](https://arxiv.org/abs/2211.16335)，§V–VII | 对应对投影到弱方向，约束配准更新；以APE/RPE/端点误差评价 | 是估计更新，不是主动位移；二维约束投影也属于成熟思路应用 |

另有两个重要核对结果：

1. [Informed, Constrained, Aligned，2025](https://arxiv.org/html/2408.11809v3#S2.SS3)的“active”
   是ICP优化内部利用退化信息，不是机器人主动运动。关键词会造成重复性误判。
2. [2DLIW-SLAM，MST2024](https://doi.org/10.1088/1361-6501/ad3ea3)已明确处理二维相似几何退化，
   融合IMU/轮速、点线约束与回环。这证明二维任务不是空白，但本轮不会迁移其后端。

完整矩阵含传感器、触发/动作、地图、目标、指标、基线、代码/依赖、读取范围和未知项。
Help Me Through仅确认T-RO2025元数据，完整方法未知。GenZ预印本接受时间为2024，用户的2025
需区别在线/卷期，不混写。Uncertainty Map工作已发表于RAS2025而非仅预印本。
扩展检索还发现AWARE2026主动旋转LIO可能更直接重叠，但只有出版社摘要，未下具体方法判定。

**新颖性判定：NOVELTY_NOT_ESTABLISHED。** 现有二维平台可以度量任务误差，但还不能验证这些
论文是否留下可利用的恢复策略缺口。不会把“风险、收益、成本融合”当贡献。
资料与方法review在 `literature/`；PDF提取/渲染只本地缓存，未上传全文。

## 4. 启动前冻结的最小设计

原计划最多9次基线，3次健康、3次走廊、3次重复/过渡，另保留最多6次恢复额度。
正常和重复结构复用map3；已有地图没有明确长平行墙最小控制，因此仅新增一张100m长、
内宽3.1m的直走廊，起点在中段、终点仍距两端超过25m雷达量程。不是连续筛选地图或为动作加侧门。

三类计划任务长度均30m，路线/种子/初态在看结果前登记。机器人、碰撞、FOV、Karto和原
`odom_error [0.05,0.05,0.1,0]`未改，没有追加噪声或压力搜索。
seed271001/271002/271003只控制起点x/y±3cm、yaw±0.01rad微扰，不控制Karto线程数值状态。
Stage显式odom_error与旧TSP seed不等同，不能把同seed说成完全相同的SLAM初态。

主要评价预先规定：在线map-base/GT-base平移/朝向误差、1s RPE、持续超限、任务完成、时间与路径。
首次运动前静止段固定单一SE2规范；GT最短角插值，括夹≤0.15s，正确配对覆盖≥90%，不动作后重拟合。
健康三个有效episode先决定 `max(0.15m,3×max健康episode P95)`，然后冻结，超限持续≥2s才记事件。
**当前没有健康数据，门槛尚未完成校准，不能用0.15m擅自对失败启动定性。**

辅助几何模型是point-to-local-line Jacobian，归一化状态为 `[dx,dy,L·dtheta]`，L=1m，unit weights，
H除以对应数量；报告平移子块谱和弱方向。它是可解释代理，不是Karto实际相关性matcher Hessian，
不是完整后验，也没有根据结果调几何阈值。理想平行墙的轴向秩亏单元测试只证明模型数学行为，
不证明机器人真实失定位。

还有一个不能忽略的可恢复性限制：对只看见两条平行墙的理想point-to-line模型，法向都垂直于
走廊轴，平移信息子块沿轴仍秩亏。仅在这段同质走廊内横移或转向，不会凭空创造沿轴几何约束。
当前最小走廊在计划任务中看不到端墙，因此它适合筛查“弱几何是否导致真实误差”，
**不适合直接承诺小位移一定能恢复**。这是模型/场景设计的限制，不是已经测得的Karto失败。
后续若通过问题关，恢复机会必须来自实际可达的非平行结构/几何过渡，不能把继续积累同质扫描
或碰巧走出任务区域包装成有限局部恢复。

## 5. 实际尝试和为何停止

三次使用同一个冻结seed271001，为资格/修正尝试，不是三个独立实验。

| 尝试 | 已发生的事 | 科学任务/主要端点 |
|---|---|---|
| R0，44.90wall秒 | Stage嵌套hokuyo.inc路径未解析；clock等待失败 | 未开始/无 |
| A1，25.64wall秒 | 加入等内容include别名后加载成功；误用`-u`导致/robot命名空间和TF树分裂 | 未开始/无 |
| A2，12.32wall秒 | 改用官方`-g`后有原生数据；GetFirstMap成功；MoveTo连接等待失败 | 未开始/无 |

第一次错误来自我的新封装，不是作者SLAM；第二次也是封装CLI错误，不是几何或matcher拒绝。
二次修正均在没有科学扫描/GT端点时单独冻结协议，原失败、原source/prereg/gate未覆盖。
修正不调物理/SLAM参数；为了9次基线总额，预先削减重复结构的有效覆盖，不默默补样本。

A2有1648条扫描、12760条GT、12716条odom及原始TF/控制/provenance相关记录；仍不是一个有效
30m任务。GT记录跨1275.9sim秒，而完整尝试仅12.32wall秒；bootstrap_clock为613.7s，driver
停止时报1322.7s。连接等待用30ROS秒，在该运行节奏下不能视为30wall秒。

更关键的是，1648条扫描的map_base字段全部缺失，扫描最大sim时间缺口26.7s。
**即使跳过连接判断也不能正确计算主要定位误差。** 快时钟是直接观测到的时间条件，
但尚未证明它是所有TF缺失的唯一根因，所以没有继续放宽门槛或使用最新TF兜底。

按A2事先声明的最后修复停止条件，停止第三次后的物理尝试。自己的一个残留Stage子进程按精确
cmdline识别后停止，结束时无本任务ROS/Stage进程。没有进入走廊、重复结构或恢复任务。

16项离线测试通过，却未覆盖实际Stage CLI、嵌套include和sim/wall生命周期资格。
这是本轮工程检查不足；不能将测试通过包装成系统资格通过，也不能用三次启动错误支持科学假设。

## 6. 三层判断、研究假设与方法必要性

| 层次 | 当前判断 | 含义 |
|---|---|---|
| 技术资格 | TECHNICAL_GATE_FAIL | 新运行链还不能产生可信主要端点 |
| 问题真实性 | SCIENTIFIC_MEASUREMENT_INCOMPLETE | 不能判有/无真实退化，也不能判只有几何弱而任务健康 |
| 恢复必要性 | RECOVERY_NOT_TESTED | 没有恢复收益、成本或相对继续原路线的对照 |

H1几何风险与真实误差关系、H2弱而仍健康、H3位移恢复、H4旋转不足、H5恢复值得付出成本，
本轮均是 **未评估/UNRESOLVED**。没有任何一项被新数据证实或否定，没有实际科学反例。
理论上平行墙难以约束沿轴运动是机制候选；没有可复核任务误差就不能升级为“可信实际失败机制”。

目前不选择方法开发A，不选择检测B（没有风险-vs误差对照），不选择被动鲁棒筛选C（没有本平台
明确约束问题）。唯一执行决定为 **D STOP_THIS_DIRECTION，范围是停止当前Doc81封存运行**；
这不是科学上否定整个定位恢复方向。纯旋转旧方向仍按Doc80停止，新方向不靠换标签自动成立。

文献使研究问题真实，但没有使本项目的方法必要性成立。最有价值的本轮认识是：
必须同时证明“实际误差”“局部可恢复机会”“超出强固定/成熟方法的空间”，不能用几何proxy
或已有同步dump服务跳过这些条件。恢复机会若不存在，也应接受负结论。

## 7. 预算、交付与唯一下一任务

预算已用 **3/15总尝试，3/9基线，0/6干预**。剩余12额度中基线至多6；不自动使用。
有效科学episode=0，健康资格=0；没有ATE/RPE/超限统计或恢复成本结果表，没有空表假装完成。
资格原始本地文件约56.5MB，SHA见 `audit/local_only_capture_manifest.json`。

主要路径：

- [完整交接包](../../results/research_direction/localization_recovery_phase0/REVIEW_PACKET.md)
- [运行与封存说明](../../results/research_direction/localization_recovery_phase0/README.md)
- `protocol/`：原方案、A1/A2独立协议与哈希、原子预算账本。
- `audit/qualification_attempts.csv`、失败诊断、初/末保护清单、实际library maps本地登记。
- `literature/research_literature_matrix.csv`、closest review、novelty风险。
- `tools/research_direction/localization_recovery_phase0/`：纯误差/事件/几何函数、驱动、runner、tests。

测试命令（只离线测试，不启动ROS）：

```bash
cd /home/wcqw/ac-slam_doc81
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m unittest discover \
  -s tools/research_direction/localization_recovery_phase0 -p 'test_phase0.py' -v
/usr/bin/python3 tools/research_direction/localization_recovery_phase0/postmortem.py
```

第二条命令只读复核封存协议、源文件、旧文件保护、raw SHA、流计数和缺失端点；
`--write`仅再生成post-hoc审计，不启动ROS、不计算科学误差，也不覆写R0/A1/A2 gate。
实际加载库的本地快照及逐库SHA另见 `audit/runtime_library_manifest.json`。

**唯一建议下一任务**：由用户确认一个新的、仅一回合的技术资格协议，先复用已证明可用的原Stage
GUI/wall节奏，运动前确认完整TF与MoveTo连接，量化同stamp map-base/GT配对，检查全部子进程清理。
不改Karto、不迁移后端、不训练预测器、不放宽误差/同步指标。通过后再在剩余额度内重新冻结
科学覆盖范围；失败就停。**不是直接重启当前9回合矩阵，更不是Doc82方法开发。**

局限：二维模型尚未得到任务级验证；原里程计误差不是实机标定；三个健康seed未完成；已知地图
与未知环境文献不是同任务；2026路径规划与Help Me Through全文未知；没有新颖性穷尽检索。
本报告由AI辅助核验与实现，不声明独立研究者已验证数据或论文已经可发表。
