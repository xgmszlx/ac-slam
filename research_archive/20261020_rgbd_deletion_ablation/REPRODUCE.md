# 删除消融执行记录

父原型：`/home/wcqw/passive_rgbd_combo_20261019`；完整Bonn与旧真实对照：其`e2e_20261020`子目录。旧文件只读复用，本轮没有下载、安装或复制原始数据。

实际步骤：

1. 从父Combo/入口复制，只增加mode3(E1)、mode4(E2)两个删除开关；父S0/S1/S2模式保留。
2. `python3 code/build_ablation.py`仅编译Combo和小型入口，链接父28个只读对象。原库不覆盖。
3. 以现有g++/pkg-config opencv4编译并运行`code/test_combo.cc`及`code/test_switches.cc`；合成软件控制不启动System。记录见audit/test*.log。
4. `/home/wcqw/anaconda3/bin/python tests/test_evaluate.py`：原3项SE3/时间/RPE控制通过。
5. `PYTHONDONTWRITEBYTECODE=1 /home/wcqw/anaconda3/bin/python code/run_ablation.py`：E1→E2→S0各一次，完整589组。每次/usr/bin/time -v记录资源；GT只供离线evaluate，未传入SLAM。LD_LIBRARY_PATH优先本目录build，正确库见audit/ldd.txt。
6. `PYTHONDONTWRITEBYTECODE=1 /home/wcqw/anaconda3/bin/python code/summarize.py`：读取旧S0/S1及三条新结果，生成五条比较和S0两次范围；旧评价不覆盖。

完整预算3/3关闭；已有protocol/attempts.jsonl会阻止自动重复，不再执行run_ablation。运行前参数/代码/二进制hash见protocol/run_inputs_frozen.json。最初相对object清单失败及检查完成时间见audit/preflight_path_failure.md，不隐瞒为“所有预检均先通过”。

原始地图/估计器/图像/标定/时间匹配、1秒RPE与SE3无尺度规则不变。前端帧统计累计是观测事件，不是独立样本。原生保留2D/3D关联不是物理正确性真值。S0只有两次、其余一次，没有显著性/稳定收益结论。

发布归档包括小型开关代码、构建命令/补丁、统计、三次紧凑原始轨迹/资源及必要图；不含完整RGB-D/GT/ZIP、编译对象或SO。脚本使用已验收工作站的固定路径，非独立可移植SLAM发行包。未授权进一步科学运行。
