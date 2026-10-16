# 作者源码与现有平台的实际审查

只读，2026-10-15。`git ls-remote HEAD`得到如下当前版本；这些是本轮代码快照，**不是已认证的论文发表版本**。下载仅选定文本文件，失败保留于source_acquisition等JSON。没有clone整仓、下载模型或执行安装脚本。

| 仓库 | 固定SHA | 实际读取 |
|---|---|---|
| sair-lab/AirSLAM | d1265771026091db97ee8f7a6d80692f0edd5fef | CMakeLists、g2o_optimization.cc；README网页核查，本机raw失败 |
| MAC-VO/MAC-VO | 8683b532d6f6e8981f6b1a646fb5f52f02c1ea61 | README、requirements、KeypointSelector、Covariance/Project2to3、Optimization包入口 |
| edexheim/como | 56e421a70f8863d9c446d46f52246e4357193346 | README、install.sh、setup.py、config/como.yml |

## AirSLAM

固定[CMake](https://github.com/sair-lab/AirSLAM/blob/d1265771026091db97ee8f7a6d80692f0edd5fef/CMakeLists.txt)要求catkin、OpenCV4.2、CUDA、g2o/gflags/glog，链接nvinfer/nvonnxparser；不是去掉ROS显示就能直接链接旧ORB3的轻量模块。[优化源码](https://github.com/sair-lab/AirSLAM/blob/d1265771026091db97ee8f7a6d80692f0edd5fef/src/g2o_optimization/g2o_optimization.cc)已给点、线边设置information并使用Huber；部分point为identity，line有pixel_sigma或固定比例，不能概括为“整个系统没有观测权重”。完整学习前端与本机兼容性未测。

本机nvcc11.8；作者README测试CUDA12.1/TensorRT8.6.1.6。系统ldconfig未见TensorRT、Ceres或独立g2o缓存条目；不排除其他自定义路径。TensorRT未认证，不启动移植。当前依赖差异是工程负面因素，不是GPU算力不足的证明。

## MAC-VO

固定[Project2to3.py](https://github.com/MAC-VO/MAC-VO/blob/8683b532d6f6e8981f6b1a646fb5f52f02c1ea61/Module/Covariance/Project2to3.py)：

- `ICovariance2to3.estimate`接口明确输出N×3×3。
- `MatchCovariance`使用二维位置不确定性核，对局部depth求加权均值/方差再传播。
- `GaussianMixtureCovariance`调用`gaussian_mixture_mean_var`，最终仍返回N×3×3。它已实现混合统计；不能把类名当作位姿优化保留了离散模式的证明。
- `wavg_depth`在此用于协方差传播；模块只返回协方差。**不能据此断言真实配准点的坐标被替换成混合均值，更不能称已观察到“均值落在两个面之间”的作者运行失败。**
- 本轮没有取得具体TwoFramePGO实现，不能从一条404推断包缺失或优化器不能运行。关于论文优化目标的判断来自§III-D，不伪装成完整后端源码认证。
- [KeypointSelector](https://github.com/MAC-VO/MAC-VO/blob/8683b532d6f6e8981f6b1a646fb5f52f02c1ea61/Module/KeypointSelector.py)已有NMS、几何/深度资格和不确定性筛选。当前代码还设最大协方差上限；不能只照论文的“1.5倍中位数”描述全部当前逻辑。

无需训练即可使用作者权重，但尚未获取任何权重。4.2GB论文测试与当前README 6GB/fast2.7GB是不同模式/版本，不据此判8GB一定足够或不够。真正现实障碍是Torch、CUDA运行时、xformers、模型和磁盘预算，非必然需要训练。

## COMO

[install.sh](https://github.com/edexheim/como/blob/56e421a70f8863d9c446d46f52246e4357193346/install.sh)创建新Python3.10、安装Torch/CUDA12.4、Open3D、lietorch等；没有执行。[setup.py](https://github.com/edexheim/como/blob/56e421a70f8863d9c446d46f52246e4357193346/setup.py)有CPU/CUDA扩展分支；[默认config](https://github.com/edexheim/como/blob/56e421a70f8863d9c446d46f52246e4357193346/config/como.yml)mapping指定cuda:1、tracking指定cuda:0，模型为scannet.ckpt。单GPU可配置但未测，不冒称必须双GPU。训练既有DepthCov模型是原工作成本，复现不必自动重训。

以上四个实际取得的Python文本AST通过；仅为静态语法检查，未导入依赖、未编译、未运行。公开代码、语法成立、本机可运行、复现论文四者没有合并。

## 可直接复用的ORB-SLAM3

官方commit仍为4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4，原核心SO SHA256仍为a20db0416fc54ca5949e6b6ac834c12f59dc0bae5f08dc2945e46943a3532c46；既有rgbd_diagnostic二进制hash见environment_and_static.json。没有重编译或启动。

本轮只读核查`Frame.cc:984`：RGB-D在关键点坐标读取单个depth值，正值生成mvDepth与虚拟右目坐标。`Optimizer.cc:892`附近RGB-D/stereo pose边用3维观测、层级权重和Huber。**这是表示/实现事实，不是错误depth已经进入某次真实优化的日志证据。** 不扩建内部追踪，不恢复walking约束审计。

现有源码没有ETH3D RGB-D专用yaml；未来需要按该序列标定写新配置。不得套用Freiburg3内参。RGB-D的`bf`是虚拟右目度量和残差设置的一部分，不能冒充ETH3D外参给出的真实RGB基线；应预先说明沿用哪份官方RGB-D规则，所有方法保持一致。若不能确认，标技术不完整，不能通过GT调参。

## 实机限制

environment_and_static.json记录：OpenCV4.2/Python3.8可用；默认Anaconda Python3.12未找到torch；GPU8188MiB，读取时空闲约7881MiB；总RAM24,910,815,232字节，可用约16.1GB。只检查这些环境，不声称遍历所有虚拟环境。

开始root可用1,896,042,496字节，约1.77GiB；保留1GiB后仅约0.77GiB可用于新任务峰值。现有OpenLORIS cafe1-1.bag约2.56GB已在另一旧目录，office只有不完整归档；未将它们当作已认证新低光数据链，也没有解包。无需为“复用”而重启旧RTAB平台。
