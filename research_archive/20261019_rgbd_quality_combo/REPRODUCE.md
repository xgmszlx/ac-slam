# 原型构建与后续数据接入

当前数据未合格，S0/S1/S2真实运行0/3。不得重复执行获取脚本，下载尝试已经停止。所有当前构建/软件测试独立保存在本目录build与audit，未覆盖旧源或库。

## 已完成

- `code/build.py`：从固定ORB3源生成Frame前端补丁、只读Optimizer/System追踪；25个原估计器对象继续只读复用，另编Frame/Optimizer/System/Combo。Overlay System.h复用首轮非虚只读getter，类布局不改。
- `code/build_entry.py`：编译headless统一入口。
- `code/test_combo.cc`：无动作一致性、描述子子集、简单PnP、S1删除、S2准确−1置位；独立软件控制。
- `code/test_frame.cc`：真实Frame构造及depth/描述子/grid索引软件检查，使用合成输入，未启动System/序列。
- `tests/test_evaluate.py`：复用既有3项SE3/时间/RPE控制。
- `code/run_three.py`：已验证数据门会在System启动前拒绝不完整ZIP；未消耗科学预算。

实际编译命令和测试输出见audit。运行需优先加载本目录build/libORB_SLAM3.so及原local Pangolin，不得覆盖旧SO。当前入口未取得真实序列端到端资格，不把编译和Frame测试说成完整SLAM测试通过。

## 唯一待补资料

从[官方链接](https://www.ipb.uni-bonn.de/html/projects/rgbd_dynamic2019/rgbd_bonn_moving_obstructing_box.zip)使用正常浏览器/网络取得完整文件。期望320,845,314字节；已有最近副本316,669,952字节，不能改名当完整文件。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 code/accept_complete.py /path/to/rgbd_bonn_moving_obstructing_box.zip
PYTHONDONTWRITEBYTECODE=1 python3 code/prepare.py
```

离线验收检查已通过HTTPS取得的原始前缀一致性、完整大小、全部ZIP CRC和安全路径/磁盘余量。prepare解码全部输入、原20ms唯一时间关联和真实Bonn标定。不会因获取文件就自动运行SLAM。

先检查固定30/50/70%时刻的3组RGB帧对，冻结箱体/静态/UNKNOWN标签，再确认至少存在可信动态箱体与静态背景2D对应；2D/双depth分别计数，不再要求全部点有depth。该人工观察和对应资格尚未执行，不能伪造`audit/observation_qualification.json`为通过。当前完整数据缺失，不预填标签，也不增窗口。

通过后沿用本轮已授权、尚未使用的3次预算：S0→S1→S2，每种一次。入口按实际输入/代码hash重冻，保留全部轨迹与失败，禁止自动重试。GT只在离线evaluate读取，SE3无尺度、原1秒RPE规则。当前config/bonn.yaml是按官方参数准备的配置，不是已运行认证；其中Stereo.b=.0747是相同虚拟RGB-D参数，不冒充真实双目基线。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 code/run_three.py
```

上述命令不是宣称本轮已取得3条轨迹。运行后必须另做全序列在线/导出误差、身份/多map、真实fallback边及成本比较；不能用本轮软件测试数值代替。
