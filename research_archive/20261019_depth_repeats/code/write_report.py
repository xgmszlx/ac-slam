"""Write a concise report from all run records, keeping unqualified outputs visible."""
from pathlib import Path
import json
import pandas as pd
P=Path(__file__).resolve().parents[1];x=pd.read_csv(P/'results/desk_six_runs.csv');s=pd.read_csv(P/'results/ranges_medians.csv').set_index('metric');d=json.loads((P/'results/decision.json').read_text())
assert d['status']=='B1_INCONCLUSIVE'
def table(cols,labels,fmt):
    z=['| '+' | '.join(labels)+' |','|'+'|'.join(['---']*len(cols))+'|']
    for _,r in x.iterrows():
        z.append('| '+' | '.join((r[c]+('†' if r.label=='B0_03' else '')) if c=='label' else (format(r[c],f) if f else str(r[c])) for c,f in zip(cols,fmt))+' |')
    return '\n'.join(z)
acc=table(['label','online_ATE','exported_ATE','online_RPEt','exported_RPEt','online_RPEr','exported_RPEr'],['运行','在线ATE m','导出ATE m','在线RPEt m','导出RPEt m','在线RPEr °','导出RPEr °'],['','.6f','.6f','.6f','.6f','.4f','.4f'])
state=table(['label','online_coverage','exported_coverage','public_OK','map_ids','map_count_max','longest_public_non_OK_s'],['运行','在线覆盖','导出覆盖','公开OK帧','Map ID','最大图数','最长非OK s'],['','.4f','.4f','d','','d','.3f'])
resources=table(['label','last_map_points','last_keyframes','exported_keyframes','retained_2d_mean','retained_3d_mean','preprocess_ms','track_ms','CPU_user_s','CPU_system_s','RSS_MiB','wall_s'],['运行','末帧地图点','末帧KF','导出KF','2D均值','3D均值','预处理ms','Track ms','用户CPU s','系统CPU s','RSS MiB','墙时s'],['','d','d','d','.2f','.2f','.2f','.2f','.2f','.2f','.2f','.2f'])
st=['| 合格精度指标 | B0范围〔中位〕，n=2 | B1范围〔中位〕，n=3 | B1−B0中位差 | 范围分离？ |','|---|---|---|---|---|']
for m in ['online_ATE','exported_ATE','online_RPEt','exported_RPEt','online_RPEr','exported_RPEr']:
    r=s.loc[m];st.append(f'| {m} | {r.B0_min:.6f}–{r.B0_max:.6f}〔{r.B0_median:.6f}〕 | {r.B1_min:.6f}–{r.B1_max:.6f}〔{r.B1_median:.6f}〕 | {r.B1_minus_B0_median:+.6f} | {"是" if r.worst_B1_below_best_B0 else "否"} |')
c=s.loc['track_ms'];u=s.loc['CPU_user_s'];mem=s.loc['RSS_MiB']
text=f'''# desk深度边界拒绝：第二轮受限重复

2026-10-19，ANALYZED。**最终状态：B1_INCONCLUSIVE。** B1三次本身相近，但不能确认它持续优于B0：新增B0_02在线ATE/RPE优于全部B1，导出ATE落入B1范围。另一次B0_03自然失跟、建新图并合并，原始导出时间身份不合格；完整保留，不补跑或用其较差原始误差制造稳定收益。

## 1. 执行和固定条件

新增顺序严格为`B1_02 → B0_02 → B0_03 → B1_03`，4/4均完整处理573个关联输入、进程退出0。旧desk B0/B1本文标_01，旧目录和结果不改；cabinet B0/B1仍各一次，本轮未运行。项目累计8次完整执行，预算已关闭。**退出0/输入完成不等于跟踪、轨迹身份合格。**

复用官方ORB3 **4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4**、同一入口9e6d9752…及诊断核心c9f08e6c…、相同TUM1内参/畸变、BGR/Camera.RGB=0、depth/5000、ORB/后端参数和评价。未编译、下载、安装、训练、启动ROS/仿真或B/C开发。远端起点34b9669bcec369bf1b447e2ebfef1c248b9e5c30在运行前核验。

B1规则未变：**3×3有效depth邻域至少2个有效样本，max−min > max(0.05m,0.03×有效中心depth)，将有效中心置0，无膨胀。** 不改RGB或2D提取/描述子、不改变优化公式。新入口将标签与实际条件分开，B1_02/B1_03传入原生程序的条件仍为B1。[运行前冻结](protocol/design_frozen.json)、[独立台账](protocol/attempts.jsonl)、[预算结算](protocol/attempts_final.json)保留。

## 2. desk全部6次真实结果

{acc}

**† B0_03以上全为未经修复的原始评价数值，不具备可信全程精度解释资格。** 不能与其余行当同规范精度作三次平均或中位结论。在线跨两个地图且未认证历史位姿的统一坐标规范；导出572行、仅489个不同stamp，83个重复stamp。唯一时间戳覆盖489/573（原GT唯一配对492行并不修复重复输出身份）；没有去重改stamp、分段GT对齐或覆盖原始结果。导出RPE419对、在线417对；其余五次各524对。

{state}

覆盖以573个完整关联输入为分母。B0_03有OK487、RECENTLY_LOST85、NO_IMAGES1；最长公开非OK约3.032s。日志明确出现新地图1、之后merge回地图0；缺失的1个原生Frame快照发生在重建时。其余五次均OK573、Map ID0/一张图、573条唯一在线/导出位姿。公开状态不穷尽内部瞬时转移，不保证精度。

统一评价为在线/导出分别单次SE3刚性对齐、无自由尺度，GT匹配<20ms，1s±20ms RPE并沿用原缺口规则。GT只在进程结束后评价，不参与边界选择。

{chr(10).join(st)}

这里B0的合格精度n=2、B1 n=3，不能冒称三对合格重复。全部3次/条件的**原始数值**范围/中位另保留[含不合格输出的辅助CSV](results/all_run_raw_ranges_UNQUALIFIED_INCLUDED.csv)，不作为精度证据；六次逐项值见[完整表](results/desk_six_runs.csv)。故障次数B0=1/3、B1=0/3也不足以推断可靠性概率。

![完整运行值；B0_03原始数值用红字保留，点和中位线仅代表合格精度](figures/01_accuracy_repeats.png)

**图1结论：** 在线ATE、导出ATE、在线平移RPE均有重叠/逆转；不能把第一次B0较差当作稳定基线。只有导出平移RPE在合格样本中完全分离，最佳B0与最差B1间距仅约0.000437m，单项不足以满足预登记联合门。在线结果并非稳定改善，不能只展示导出收益。n很小，不把视频帧或相关RPE对当独立重复，不报告显著性。

## 3. 真实干预与地图/运行代价

全部输入索引和stamp相同；可取得Frame时原生N与边界目标数均一致。B0_03重建时1帧N=-1表示快照不可取，**不声称该帧原生ORB提取完全相同**。三次B1各**22,909次**目标原生depth观测全部实测成为`mvDepth=-1、mvuRight=-1`，保留2D特征，其他有效depth特征平均由857.55降至817.57/帧；B0没有该规则造成的无效化。22,909是逐帧观测次数，不是独立地图点数量，也不是已证明错误的depth。

{resources}

成本和地图快照按全部3次/条件报告，不因B0_03精度不合格删掉其运行成本。B0_03的关联/有效depth均值在完整573帧返回记录上计算，含重建时1个零快照；不是三次一致的实际深度供给。

Track均值：B0 {c.B0_min:.2f}–{c.B0_max:.2f}〔中位{c.B0_median:.2f}〕ms，B1 {c.B1_min:.2f}–{c.B1_max:.2f}〔中位{c.B1_median:.2f}〕ms，中位变化**{c.B1_median_relative_change_percent:+.1f}%**；用户CPU中位变化{u.B1_median_relative_change_percent:+.1f}%。RSS中位B0/B1为{mem.B0_median:.2f}/{mem.B1_median:.2f}MiB。按原时间戳节奏处理让墙时接近，不能掩盖Track计算开销。Track P95、CPU/system及完整/usr/bin/time -v均保留，不声称实时资格或独立模块耗时因果。

![全部重复的地图快照、关联和耗时；同编号不是配对随机反事实](figures/02_maps_cost.png)

**图2结论：** 地图与保留关联随运行变化，B1成本也有波动。2D/3D为返回Frame中非空且!outlier的MapPoint关联，依mvuRight分类，非全部优化或BA边数。地图点/KF为末Frame快照，导出KF另列；后台仍会增删，不能称地图压缩/未来定位改善。原生Shutdown未改，未认证全部后台优化排空。

## 4. 判断及唯一下一步

**B1_INCONCLUSIVE。** 三次B1在线ATE为0.020996–0.026594m、导出ATE为0.016398–0.017617m，说明其在本次重复中没有明显大波动；但B0_02达到在线0.020435m、导出0.017595m，足以否定“每次B1均优于B0”的本轮主张。B0_03失败是需保留的任务结果，不能用无资格的大误差证明B1稳定有效。平台输入/代码资格仍成立，这是自然跟踪与地图重建的结果，不据此报数据/平台TECHNICAL_INCOMPLETE。

尚未证明错误表面深度是原因、简单边界拒绝具有特异性或复杂方法有必要。RGB-D关联时差/运动、混合像素、初始化地图、描述匹配、异步局部BA/回环与线程调度仍是竞争解释。没有逐点depth真值或被污染优化约束身份，不从地图点减少逆推消除了错误观测。

**下一步唯一建议：归档B1_INCONCLUSIVE，暂停A方向追加运行与方法原型，降低其优先级。** 本轮没有通过稳定收益门，不自动执行匹配数量的随机/非边界拒绝基线，不扩大种子/序列/阈值搜索；B/C也不在本轮启动。接受当前证据不足，不用新模块挽救结论。未来若重新获得独立问题证据，再单独决策；不是预先预约后续实验。

## 5. 保护和复查

旧入口/预算/四次结果不变。前后核验131项首轮文件、1146张desk关联RGB/depth、24个冻结项及主仓HEAD/status/diff，主仓两个未提交修改保留；保护范围不冒称全部历史数据。始终保留5GiB空间余量。[保护结果](audit/protection_after.json)。无新SLAM进程残留。

首版汇总脚本错误地假设全部运行均是单地图/完整身份，断言在B0_03停止；修正为保留所有输出并显式区分自然失败与合格精度。首版及说明保留audit，没有重跑、修复轨迹或放宽评价阈值。[复查命令](REPRODUCE.md)。发布仅含代码/协议和紧凑派生结果，输入数据、GT、编译库不上传；推送后的真实SHA见本机PUBLISHED.json及最终交付，不预填自引用SHA。
'''
(P/'REPORT.md').write_text(text);print(d['status'])
