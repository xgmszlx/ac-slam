# B/C最小实施成本检查：不运行第二个系统

固定ORB3 commit4452a3…的实际源码，而非只看System.h内过时的TODO注释。

| 能力 | 源码事实 | 本机资格/成本 |
|---|---|---|
| 保存/加载Atlas | System.cc构造器读取System.SaveAtlasFromFile/LoadAtlasFromFile；Shutdown调用私有SaveAtlas，Boost二进制.osa保存词典名/checksum与Atlas；加载执行PostLoad | 依赖已链接，无须新后端。未在本轮4次A运行中开启保存，不能宣称已验证持久化。 |
| 停止建图只跟踪 | ActivateLocalizationMode在后续Track调用停LocalMapping并设置InformOnlyTracking(true) | 公共接口存在，尚未做冻结地图独立query。 |
| 独立query初始状态 | 加载后System仍CreateNewMap；Tracking::NOT_INITIALIZED会进入StereoInitialization，不能凭打开localization开关就假定已在旧地图定位 | **主要技术门**：需要认证查询进入旧地图重定位且不悄悄建新图、增点；原生保存/加载存在并非B实验即刻可执行。 |
| 现成保留策略 | 原生点淘汰已有观测率/观测次数/年龄判断；MS-SLAM已有非局部滑窗、可见性与格覆盖稀疏化 | 先比较同一原始Atlas下固定K的现成随机/观测数/覆盖保留，不开发新压缩器；SetBadFlag会影响关键帧关联，须保持数据库一致性。MS作者框架有Gurobi额外成本。 |
| 后续定位评价 | 必须独立query的真实pose正确性/失败时间/覆盖/RPE，配合点数、RSS、序列化大小和计算量 | 不用静态覆盖代替成功率；不能用不同A运行的不同地图直接当相同原始地图下的公平压缩对照。 |
| 多次访问数据 | OpenLORIS可作为后续候选；本轮未下载、未验收多次轨迹GT与共同坐标 | 不能宣称数据即刻可用。先用已有短序列做工程资格，正式能力比较须真实独立查询和统一参考图坐标。 |

B结论：**PARTIAL_SOURCE_SUPPORT / QUERY_RUNTIME_NOT_QUALIFIED**。一个保存—重载—短query资格可复用现有依赖，但加载状态和map身份处理预计需1–3工作日（估计，不是已验证工期）。本轮没有B运行，也不把A的地图点减少称为未来定位改善。

C结论：Good Feature Matching直接针对匹配预算；SlimSLAM针对VIO运行时。当前不开发调度器/自适应特征数；不同平台不消除机制重叠。C未取得独立问题资格。

本轮唯一优先后续仍是NEXT_MINIMAL_ACTION里的desk受限重复；没有并行B/C工程任务。
