# V3 cables_3受限问题验证：Phase 0数据资格未通过

2026-10-15。**DATA_NOT_QUALIFIED；本轮总决策TECHNICAL_INCOMPLETE。** 已完成实际磁盘/挂载检查、独立目录写入检查、官方数据源核查和有限ZIP元数据获取。由于官方数据连接TLS中断/超时，未取得压缩包中央目录，无法验收数据；按用户规定在Phase 0停止。B0 **0/3**、B1 **0/3**。

这是数据获取资格失败，**没有证据支持或否定深度边界导致ORB-SLAM3位姿损失，也没有证据判断简单深度拒绝是否足够**。不将它写成V3科学假设失败；不改用其他序列，不建设新后端。

证据标签：实测＝本机命令/文件与获取日志；文献支持＝官方目录说明；UNKNOWN＝未取得原始文件或未运行。状态ANALYZED，不是运行复验VERIFIED。

## 1. 实际执行内容

读取上轮REPORT、PAPER_MATRIX、SOURCE_AUDIT、NEXT_MINIMAL_TEST，以及合格基线的REPORT/REPRODUCE、格式诊断报告/冻结配置和运行入口。确认官方commit为`4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4`；原核心SO和无窗口入口保持，不重编译、不启动。

本轮沿用academic-research-suite的执行与记录检查流程，限定于分阶段资格验证。

旧walking、P2、主动实验、RTAB封装链与V2均继续冻结。没有获取权重、下载新图像数据、训练、安装、运行ROS/Stage/Gazebo或开发多表面优化器。

## 2. 存储检查：已有足够的非系统分区

| 实测项目 | 结果 |
|---|---|
| 根分区 | `/dev/sda7`，ext4，开始可用1,894,920,192字节，约1.76GiB |
| 保留的系统盘安全余量 | 1,073,741,824字节；未减少 |
| 已挂载非系统分区 | `/dev/sda1` → `/media/wcqw/KESU`，fuseblk，rw |
| 非系统盘可用 | 74,948,714,496字节，约69.80GiB |
| 新数据目录 | `/media/wcqw/KESU/slam_research/v3_cables3_20261015/` |
| 写入资格 | PASS：以新建独占文件写入55字节测试，文件保留；没有改动既有文件 |

实际挂载信息见[audit/mounts.txt](audit/mounts.txt)，阶段结果见[audit/phase0_metadata_result.json](audit/phase0_metadata_result.json)。**当前障碍不是找不到存储空间。** 但数据容量未知，所以不能称“完整下载＋解压峰值已验收”。本轮未挂载新分区、修改权限、清理或删除旧资料。

## 3. 官方来源与有限获取结果

[ETH3D官方目录](https://www.eth3d.net/slam_datasets)将`cables_3`列为313帧training数据，场景为快速移动拍摄桌面线缆，明确提示可靠RGB特征可能困难。**快速运动是既有混杂因素，不能仅凭序列名称认定它暴露了深度归属错误。**

预定官方文件：

- `https://www.eth3d.net/data/slam/datasets/cables_3_mono.zip`
- `https://www.eth3d.net/data/slam/datasets/cables_3_rgbd.zip`

仅请求尾部最多65,536字节，以获取EOCD和中央目录；未发起完整包下载。若服务器忽略Range，脚本会在读取正文前拒绝；ZIP64/多卷/超限中央目录也拒绝。实际没有走到ZIP解析路径，因此该解析器的真实服务器兼容性**未认证**，不把无数据的执行写成ZIP验证PASS。

| 本轮官方请求路径 | mono | rgbd |
|---|---|---|
| Python Requests，`www.eth3d.net` | SSL EOF，约3.78s | SSL EOF，约3.79s |
| Python Requests，`eth3d.net` | 超时，约5.01s | 超时，约5.01s |
| Python Requests，`eth3d.ethz.ch` | SSL EOF，约4.83s | 超时，约5.01s |
| 最后核查：curl IPv4/HTTP1.1，`www.eth3d.net` | exit28，SSL连接超时，0字节正文 | exit28，SSL连接超时，0字节正文 |

原始记录：[metadata_requests.json](audit/metadata_requests.json)、[final_curl_metadata_probe.json](audit/final_curl_metadata_probe.json)。每个客户端/域名/文件组合只尝试一次，curl `--retry 0`，不关闭证书校验、不使用未认证镜像。Requests异常字符串中的“Max retries exceeded”是库异常名称，不能解释成程序执行了多轮隐蔽重试。

网页工具也未取得实时文件；检索缓存可以支持官方目录内容，**不能作为本机已有压缩包的证明**。非系统盘顶层两级定向检查未找到ETH3D目录；没有进行全盘无限搜索，也没有声称所有位置都没有数据。

## 4. Phase 0逐项资格

| 要求 | 结果/证据边界 |
|---|---|
| 合法公开来源 | 官方目录支持，目标URL已登记；尚无实际包内容来源验收 |
| 压缩包实际字节数 | **UNKNOWN**，没有取得可信Content-Range/Length |
| 解压后字节数 | **UNKNOWN**，没有中央目录 |
| 存储资源 | 外置分区可写、充足余量实测；精确任务峰值仍未知 |
| RGB/depth目录及实际帧数 | **NOT_AVAILABLE**；313只是官方标称，不是本地实数 |
| calibration.txt / ETH3D内参 | **NOT_AVAILABLE**；没有套用TUM3.yaml |
| groundtruth.txt / GT有效段 | **NOT_AVAILABLE** |
| associated.txt / 时间唯一性/同步 | **NOT_AVAILABLE** |
| 官方depth/5000规则 | [官方格式入口](https://www.eth3d.net/slam_documentation)及既有规范支持；本轮没有PNG来检验尺度/无效值 |
| 数据hash、CRC与文件完整性 | **NOT_AVAILABLE** |
| Phase 0 | **DATA_NOT_QUALIFIED** |

没有读取GT进行在线处理，没有按GT挑选输入或边界。

## 5. 后续阶段与科学预算

| 交付对象 | 本轮实际状态 |
|---|---|
| 原生ORB深度边界暴露/分布 | NOT_RUN，数据门未过；不能判NO_BOUNDARY_EXPOSURE |
| 边界/特征图、局部深度簇、跨视图可见性 | NOT_AVAILABLE，没有图像，不能生成真实证据图 |
| B1逐像素与Frame传播验证 | NOT_RUN，没有编写/部署B1处理实现 |
| 全部科学参数与数据/标定hash冻结 | **未完成，不能伪造**；只有范围与预算登记，不等同科学设计已冻结 |
| B0完整运行 | **0/3** |
| B1完整运行 | **0/3** |
| ATE/RPE/覆盖/失跟/关键帧/运行变异 | **NOT_RUN**，不填0或复用旧walking指标 |
| B1实际使用depth的干预效果 | **UNKNOWN**，不能从预计输入变化冒称科学干预 |
| 简单方法是否足够 | **UNRESOLVED** |
| 具体剩余失效机制 | **UNRESOLVED** |

[protocol/scope.json](protocol/scope.json)和[budget.json](protocol/budget.json)保存上限3＋3、拟议交错顺序和停止门；attempts为空。没有消耗一次新的SLAM运行，没有失败后重跑。范围中的3×3边界规则来自原建议，尚未投入数据分析；没有根据实验结果修改规则。

## 6. 决策与唯一后续建议

**最终：TECHNICAL_INCOMPLETE，具体原因DATA_NOT_QUALIFIED。**

不能给出NO_MEANINGFUL_BASELINE_LOSS、SIMPLE_DEPTH_REJECTION_EFFECTIVE、NO_METHOD_JUSTIFIED或RESIDUAL_FAILURE_CANDIDATE的实验结论。本轮没有轨迹或边界样本，不能比较深度错误、相机运动、低纹理、模糊、初始化与后台变异，也不能对MAC-VO作失败判断。

**下一项只建议：当网络条件确实改变，或同一官方cables_3完整文件已合法到位时，恢复Phase 0数据验收。** 保存到已核实的新非系统盘目录，先取得压缩容量/中央目录和完整性信息，再解压核查标定、313帧与GT。条件未改变时暂停，不继续自动重试，不改序列或重建获取/检测平台。通过数据门后才可按原授权进入Phase 1；本报告不把未完成阶段写成已经具备资格。

## 7. 保护与原始交付

新报告与日志位于本独立目录；非系统盘只新建上述独立目录和写入检查文件。旧五份MANIFEST涉及的文件及五份清单自身共546项在开始与结束逐项hash核对；另核查主仓HEAD/status/diff与原核心SO/入口。结果见[audit/protection_after.json](audit/protection_after.json)。该证明只覆盖登记文件，不冒称重hash全部旧原图与所有历史目录。

原始网络失败、挂载与资源数据、范围和未使用预算、元数据获取脚本均保留。交付是一次**实际数据资格检查及其失败记录**，没有用文献讨论、占位图或旧轨迹伪装完成B0/B1。

Material Passport：V3-cables3-Phase0；type=code/data qualification；status=ANALYZED；raw_dataset=NOT_OBTAINED；science_runs=0；GT_online=false；independent_replication=false。
