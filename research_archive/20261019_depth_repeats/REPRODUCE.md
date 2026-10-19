# 第二轮desk重复记录

本轮预算4/4时禁止重跑。现有运行入口在旧目录`passive_rgbd_depth_screen_20261019/build/rgbd_screen`，没有编译新估计器或复制数据。

已执行的顺序：`B1_02 → B0_02 → B0_03 → B1_03`。命令、实际B0/B1参数、库/配置hash及耗时见各run.json。运行标签不是传入C++的条件字符串，B1标签仍精确传`B1`。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 code/freeze.py
PYTHONDONTWRITEBYTECODE=1 python3 tests/test_evaluate.py
PYTHONDONTWRITEBYTECODE=1 python3 code/run_repeats.py > audit/execution.log 2>&1
PYTHONDONTWRITEBYTECODE=1 python3 code/summarize.py
PYTHONDONTWRITEBYTECODE=1 python3 code/verify.py
```

freeze.py仅供首次登记；已有design_frozen/protection_before不可覆盖重建。run_repeats.py检测现存台账后拒绝再次执行。分析脚本只读旧结果和本轮结果，不启动估计器。路径在本机固定，异机需恢复相同依赖和合法TUM数据，再单独授权实验预算。

复用ORB-SLAM3官方4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4、同一诊断System对象/27个原估计器对象、BGR+Camera.RGB=0、TUM1内参与畸变、depth/5000、原ORB和后端配置。B1为3×3有效深度max−min > max(0.05m, 0.03×有效中心深度)，至少2个有效样本，无膨胀；仅置无效depth，不删除2D特征或改RGB。

评价文件逐字节复用首轮evaluate.py：在线与最终导出分别一次SE3旋转/平移对齐，无自由尺度；GT匹配<20ms，1s±20ms RPE排除>100ms输出缺口。GT只在进程结束后评价使用。

完整stdout、Camera/KeyFrame/OnlineTrajectory、frame_states、原始资源与评价结果保留本机。GitHub仅发布紧凑轨迹/标量和协议代码，不包含输入RGB/depth/GT、模型/词典、编译库、原数据压缩包或大缓存。旧_01轨迹留首轮归档，本轮汇总CSV将其明确标为_01。

原生Shutdown及异步后台行为完全沿用；没有认证全部后台优化已排空。地图点/KF为末次Track返回快照，导出KF数量另列。retained_2d/3d是返回时非空且!outlier的地图关联，非全部优化/BA边数。公开OK状态不穷尽内部状态转移，也不保证定位精度。
