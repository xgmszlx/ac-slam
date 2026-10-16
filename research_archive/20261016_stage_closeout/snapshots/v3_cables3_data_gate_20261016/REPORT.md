# V3 cables_3：有限数据获取结果

2026-10-16。**本轮STOP（数据门）；DATA_NOT_QUALIFIED / TECHNICAL_INCOMPLETE。V3科学假设仍UNRESOLVED，不作科学否定，不进入方法开发。**

| 要求 | 实际结果 |
|---|---|
| 1. 数据真实到位 | **否**。在`/home/wcqw`和既有外置科研目录内、最多6层的定向搜索未找到目标ZIP或cables_3标定文件；不声称搜索了所有磁盘位置。 |
| 2. 本轮网络障碍 | 两个官方文件各请求一次，SSL验证开启、retry=0。mono约7.58s、rgbd约6.53s后均curl退出35：`OpenSSL SSL_connect: SSL_ERROR_SYSCALL`。HTTP状态0、正文0字节，未完成TLS握手。 |
| 3. 数据合格性 | **未通过**。没有可检查的ZIP、CRC、实际帧数、相机标定、GT、关联或深度实值。官方标称313帧不是本地验收结果。系统盘约14.9GiB可用，当前障碍为获取路径，非已证空间不足。 |
| 4. 原生ORB边界暴露 | **NOT_RUN / UNKNOWN**，不判NO_BOUNDARY_EXPOSURE；没有图像，不能检查原生特征有效depth及地图点建立资格。 |
| 5. 示意图 | **0张**，没有以占位图或旧TUM图伪装ETH3D证据。 |
| 6. 是否执行B0/B1 | **不执行**，新增SLAM运行0次，旧预算未消耗。 |
| 7. 竞争解释 | A：可靠二维对应下的跨表面depth归属；B：快速运动/模糊/薄结构导致二维对应不可靠；C：标定、配准、尺度错误。目前三类均无法据本地数据区分。 |
| 8. GO/STOP | **STOP本轮后续步骤；V3暂停待数据，不是V3科学失败。** |

已读取既有V2/V3筛选、cables_3 Phase0报告/协议、原生ORB3基线和源码审查。固定ORB3 commit `4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4`；保持正确BGR约定，不套用TUM内参；未来必须验收ETH3D标定、depth/5000及原评价规则。未编译或启动估计器。

[ETH3D官方目录](https://eth3d.ethz.ch/slam_datasets)列出以下两份文件；本轮使用其官方`www.eth3d.net`文件下载地址，无镜像或SSL绕过：

- [cables_3_mono.zip](https://www.eth3d.net/data/slam/datasets/cables_3_mono.zip)
- [cables_3_rgbd.zip](https://www.eth3d.net/data/slam/datasets/cables_3_rgbd.zip)

**唯一下一步：用浏览器或其他正常网络环境从上述官方链接下载，将两份完整ZIP原样传入：**

`/home/wcqw/v3_cables3_data_gate_20261016/data/`

到位后才恢复完整性、容量、标定与时间资格，再检查原生ORB的深度边界候选。不要把下载成功直接视为边界机制已证实。当前不会重试、改序列或新增下载工具。curl记录的连接remote_ip为127.0.0.1，故不能把本地网络路径中的握手错误直接判作远端服务器故障、文件不存在或证书过期；本轮不再排查代理链。

创新边界保持：2018概率RGB-D混合融合、MAC-VO协方差/混合统计、COMO可见性与一致性、ORB3无深度保留二维特征均为既有机制。简单边界检测/删除、可靠性权重、GMM或延迟建点不单独构成创新。本轮没有产生支持新算法的科学结果。

原始命令、stderr、curl统计：[audit/download_results.json](audit/download_results.json)。旧四份正式报告、登记核心库及主仓HEAD/status/diff保护核查见[audit/protection_after.json](audit/protection_after.json)。未修改旧源码、数据或冻结结论；未恢复AMCL、主动SLAM、walking/P2；未训练、安装或生成新平台。本文为简短数据门记录，不替代尚未开展的科学分析。
