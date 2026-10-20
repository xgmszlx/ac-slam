# 本次真实执行记录（预算已关闭）

父原型及固定源码/库来源见 ../REPRODUCE.md 和 ../protocol/design.json。
本子目录build是指向上一轮原型build的只读复用链接，未重建后端。全部运行已完成，不再执行run_three.py；它也会因attempts.jsonl已存在而拒绝重跑。

实际顺序：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 code/accept_complete.py /home/wcqw/ac-slam/rgbd_bonn_moving_obstructing_box.zip
PYTHONDONTWRITEBYTECODE=1 python3 code/prepare.py
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 code/qualify_input.py
PYTHONDONTWRITEBYTECODE=1 /home/wcqw/anaconda3/bin/python tests/test_evaluate.py
PYTHONDONTWRITEBYTECODE=1 /home/wcqw/anaconda3/bin/python code/run_three.py
PYTHONDONTWRITEBYTECODE=1 /home/wcqw/anaconda3/bin/python code/summarize.py
PYTHONDONTWRITEBYTECODE=1 /home/wcqw/anaconda3/bin/python code/illustrate.py
```

系统Python/OpenCV4.2验收输入；现有Conda Python提供scipy/matplotlib评价。没有安装依赖。真实SLAM为C++原入口，每次命令/环境路径/耗时/exit保存在results/S*/run.json、resources.txt、stdout.log。LD_LIBRARY_PATH显式加载父目录原型核心，ldd.txt有核验。

资格分离见protocol/revision_before_runs.json；原始协议未改。guard只移除人工静态/动态点标签对技术运行的阻断；方法、阈值、后端、评价保持。prepare仅补入原本有效为0的显式k3配置，保留Bonn标定。运行前已登记新脚本hash。

冻结评价逐在线/导出单SE3、尺度1、1s±20ms、GT端点20ms、缺口>100ms排除。summary.json/CSV保留原始分项；真实frame_states.csv对应43个字段，计数不冒充独立样本。fallback边只计每帧最后一次PoseOptimization，保留关联另列；所有帧输出OK不是几何正确性保证。

发布归档仅含自有代码、协议、精度/资源/动作记录、轨迹、必要图。完整RGB-D/GT、ZIP、partial、第三方完整源码及二进制留本机。重建路径依赖前一轮固定ORB3及已有环境，不称独立可移植发行包。官方数据与标定来源：https://www.ipb.uni-bonn.de/data/rgbd-dynamic-dataset/
