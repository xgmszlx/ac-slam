# 与本轮问题直接相关的机制核查

“所读方法未给出”不是“作者所有版本没有”。下表不构成新颖性通过证书。全文缓存优先复用旧审查目录，不修改旧矩阵。

| 工作 / 已读证据 | 联合定位与变化 | 主动获取证据 | 地图提交及决策损失 | 对本方向的约束 |
| --- | --- | --- | --- | --- |
| [Stefanini，Sensors2023](https://www.mdpi.com/1424-8220/23/13/6066)；本轮最终出版JATS5.2/5.5/5.6、固定作者代码 | 冲突阈值→保护及恢复，非联合竞争假设后验 | 停止/恢复，不是所读公开代码中的区别能力NBV | buffer+暂停；原文双阈值和公开代码单阈值不同 | 保护、恢复、时间累计已有；源码问题不能直接升级为方法新颖性 |
| [DA-BSP，IJRR2018](https://indelman.github.io/ANPL-Website/Publications/Pathak18ijrr.pdf)；作者全文3–7 | 联合状态/关联belief；动态地图变化专用变量在所读公式中未给出 | 明确有，按候选动作边缘化未来关联和观测 | 不确定性、歧义及控制成本；不是所读方法中的occupancy commit损失 | “多假设+主动消歧”已覆盖，换成地图变化假设也不能自动称新 |
| [PBD-AG，2026预印本](https://arxiv.org/html/2608.10449v1)；全文3.1–3.4/4 | posed RGB-D的T输入；object中心Sigma不是robot pose belief，joint pose/change未获证实 | graph不确定性fixture核验、覆盖/安全/距离、失败排除与bounded retry | visibility-gated存在log-odds、confirm/demote/remove、baseline/delta | 主动核验、稳定基底和证据gate已覆盖；模拟器pose注册不能证明定位故障消歧；完整代码/补充版本未知 |
| [Chamelion，RA-L2026](https://arxiv.org/html/2602.08189v1)；预印本3/4.3/5和公开代码快照 | 有错配扰动消融；不是已核的joint pose/change滤波器 | 所读核心不是运动规划；不能以摘要缺失推断全部代码/版本 | 双head change/cross-visibility与Bayes map更新，低可信区域不写 | 可靠证据控制更新并非新增；承认固定visibility、配准及voxel mismatch边界 |
| [Multi-session perception-aware coverage planning，Ocean Engineering2026](https://flore.unifi.it/bitstream/2158/1464552/1/1-s2.0-S0029801826010048-main%20%281%29_compressed.pdf)；作者全文4–7 | iSAM2 pose/object与变化概率；显式错误定位vs真实变化竞争解释未知 | 明确有，mission-specific gain、重访及semantic SLAM反馈 | OPI状态概率与coverage/识别不确定性；错误occupancy commit约束未知 | 跨时段主动变化核验与反馈已有，二维移植不新；代码未核实 |
| [OASIS-Map，2026预印本](https://arxiv.org/html/2607.14899v1)；全文III/IV及Oxford项目页 | 多session对象对应与变化，posed前端；显式pose/change竞争未知 | 所读方法没有可执行NBV对照；项目Code Soon | dense semantic confidence、geometry/object association、Unknown保留 | 被动对应/可见性解释必须考虑，不能仅按几何diff宣布新变化 |
| [Lifelong localization in changing environments，IJRR2013](https://journals.sagepub.com/doi/10.1177/0278364913502830)；出版摘要及作者预印本全文索引，最终全文下载失败 | RBPF+动态occupancy HMM，联合机器人pose与环境状态是明确已有机制 | 主动动作机制未核实，不能作不存在断言 | 动态地图管理、EM、Markov mixing等；主动commit loss未知 | 连“联合估计pose和变化地图”也不是一个新贡献；实现/主动扩展信息仍未知 |
| [Olson，ICRA2009](https://april.eecs.umich.edu/papers/details.php?name=olson2009icra)；作者PDF | 非地图维护，鲁棒配准/弱prior问题 | 不要求新增运动 | plausible transform region的correlative search | B1是普通correlative baseline适配，不是该论文完整复现，更不是新算法 |

结论：没有取得足以宣布“某个新增完整机制被全部覆盖”的证据；但宽泛的联合估计、主动消歧、主动核验、概率反馈和证据提交都已有研究。具体新增机制尚未定义，NOVELTY仍为UNRESOLVED，不能给GO。
