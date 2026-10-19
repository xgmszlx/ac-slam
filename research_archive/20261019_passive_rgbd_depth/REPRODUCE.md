# 执行记录与复查

不是新运行授权。4次预算已用完，run_four.py按台账拒绝重复条件；不能原目录自动重跑。数据准备脚本也是首次准备用，不要对已存在数据再次解压。

## 固定环境/输入

- ORB3官方4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4，原工程只读复用；诊断改动见audit/read_only_system.patch。
- 原构建/链接命令在audit/compile_commands.json、entry_build.json。仅重编System对象，另编小入口及独立Frame软件测试；其他估计器原对象未动。
- 运行时`LD_LIBRARY_PATH=/home/wcqw/passive_rgbd_depth_screen_20261019/build:/home/wcqw/passive_visual_slam_qualification_20261015/local/lib`，实际ldd加载新诊断库，CPU执行。
- 每次完整词典/YAML/数据/关联/条件/工作目录命令见results/<sequence>/<B0|B1>/run.json。GT只在进程完成后的evaluate读取，未传入TrackRGBD或用于选择边界。

## 已执行命令

```bash
PYTHONDONTWRITEBYTECODE=1 python3 code/prepare_datasets.py
PYTHONDONTWRITEBYTECODE=1 python3 code/run_four.py
PYTHONDONTWRITEBYTECODE=1 python3 code/analyze.py
PYTHONDONTWRITEBYTECODE=1 python3 tests/test_evaluate.py
```

数据准备/数值评价复用既有Conda numpy/scipy/PIL；因该环境无cv2，代表图像颜色证明仅调用系统Python/OpenCV4.2并与PIL原始RGB哈希比较。没有安装软件。C++估计器与Frame探针均链接OpenCV4.2。

## 结果解释

- 相同RGB、ORB参数、内参、depth/5000、帧序。B0与B1都计算同一边界供诊断，只有B1将选中depth置0。规则冻结在protocol/scope.json，未按ATE调整。
- frame_states.csv为真实返回Frame的标量计数，非逐MapPoint身份/全部优化轮次trace。retained_2d/3d需要非空关联且!outlier，再按mvuRight分类。初始化不等于已经执行普通位姿优化。
- 地图点/KF为每次跟踪返回的Atlas快照；导出KF可在此后变化。没有保存可供独立query的Atlas，本轮B只有源码检查。
- OnlineTrajectory.txt是公开TrackRGBD的OK返回位姿；CameraTrajectory.txt是原生Shutdown后导出。两者按同一SE3无尺度协议分别对齐，不能混作一条轨迹。
- 边界图使用独立**原生Frame**探针的首/中/末帧，不是OpenCV ORB替代，不冒充运行内点身份。真实干预总数来自实际SLAM Frame，不从该图推算。
- 完整4次轨迹/日志/时间/资源均保留本机；GitHub仅发布选定研究记录和紧凑结果，原始RGB/depth/GT/压缩包/编译产物不再分发。
