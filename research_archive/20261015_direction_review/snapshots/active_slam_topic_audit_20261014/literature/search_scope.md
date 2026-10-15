# 检索与证据范围

用户日期：2026-10-14，Asia/Shanghai。重点为 2024—2026，另追溯直接相关经典方法。采用指定标题检索、作者仓库、全文参考文献追踪与反向近邻检索；这是有边界的选题审查，不是穷尽检索或 PRISMA 系统综述，不声称证明任何机制全球首次。

实际查询包含指定九个标题，以及：`active SLAM online utility prediction`、`robot exploration information gain online learning`、`active SLAM prediction error planning`、`localizability online feedback planning`、`Uncertainty-Aware Autonomous Robot Exploration confidence rich`、`SEER learning predict information gain`、`Robot Active Vision-Based Path Planning temporal persistence`、`Martinez-Cantin online path planning Bayesian`。二手聚合站只用于发现线索，方法判断采用作者论文、机构、出版方和作者代码。

**取得并核读方法与实验的主要正文**：RA-L 2024（arXiv v2）；UncertaintyMap（arXiv v1，尤其附录 A.4/A.5）；LA-Planner（arXiv v1 HTML、8 页 PDF，实验页7渲染）；ActLoc（arXiv v1 HTML、22页 PDF，第9页限制节渲染）；动态语义 NBV（Nature 正文）；P-ALC（Amazon 作者 PDF）；Region Based v3（2026-09-30 arXiv 正文）；SEER（arXiv 正文）；Multi-Robot EM（arXiv 正文）。Kim2015 与 Stachniss2004 当前核查使用旧审查目录中的作者论文文本，未重跑旧分析；原来源 URL 在矩阵。

**全文未取得或未完整核读**：

| 工作 | 本轮实际证据 | 限制 |
| --- | --- | --- |
| FIT-SLAM 2 | RAS出版摘要、方法/实验节选、作者仓库当前代码 | ScienceDirect本地返回403；SSRN下载失败，不能称最终全文已完整核读；早期摘要34%与正式摘要33%不混用 |
| Help Me Through | IEEE、KAIST作者机构摘要、Crossref元数据 | 存在与T-RO发表确认；全文未取得，确切动作空间、SLAM版本、指标、训练反馈细节未知；摘要声称发布实现，具体作者代码仓库尚未定位 |
| Degradation-Aware 2026 | IEEE出版摘要、venue、DOI | 全文与作者代码未定位；不能推断没有在线更新或实机实验 |
| Potential Fields + MPC 2026 | 出版摘要、作者机构元数据 | 全文未取得，确切代价、误差评价和代码未知；不能把未见校准模块写成不存在 |
| UCRMI TASE | IEEE出版摘要 | 未取得可信作者全文，实机与算法核心由摘要确认；内部公平性、限制细节未知 |
| Robot Active Vision IROS2024 | 作者上传论文的索引正文片段、机构发表列表 | OpenReview取文被验证页阻断；APF与预建模型可确认，全部实验和实现细节不作确认 |
| Bayesian online sensing 2009 | 作者论文检索文本、机构记录 | 作者PDF下载超时；不能据摘要断言它已实现实际SLAM残差的在线校准 |
| AIPP survey 2024 | 作者arXiv摘要、机构正式PDF条目 | 用于检索覆盖提醒，不把综述当某个缺口的直接实验证据 |

PDF预检 ActLoc、LA-Planner 均 PASS，仅代表页锚和读取完整性合格，不代表论文结论独立复现。未进行人工已读认证、引文数量推断、期刊分区/影响因子判断。对利益冲突和作者自评，保留“作者报告结果”，不冒充独立复验。

GitHub匿名API出现限流后改用稀疏的无checkout Git元数据和固定SHA raw文件读取；没有运行仓库安装脚本。少量并发抓取曾超时/连接重置，后续关键代码通过固定SHA raw重取成功，错误保留为获取缺口。`sources/acquisition.json`只记录首批抓取，完整本地文件SHA在最终 `audit/artifact_manifest.json`，不可据首批清单把后来成功下载的PDF遗漏或把失败HTML当论文。
