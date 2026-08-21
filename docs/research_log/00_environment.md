# Phase 0 环境审计

审计日期：2026-08-20（Asia/Shanghai）

## 审计范围与版本

[Code]
主 baseline 已安全克隆到：

```text
/home/wcqw/ac-slam/baseline/Graph-Based_SLAM-Aware_Exploration
```

固定版本：

```text
remote: https://github.com/bairuofei/Graph-Based_SLAM-Aware_Exploration.git
branch: master
commit: 675299330dff0460d42c0ffd87a2f1f7f9f959da
```

[Code]
README 指定的作者版 `navigation_2d` 已单独克隆到：

```text
/home/wcqw/ac-slam/dependencies/navigation_2d
```

固定版本：

```text
remote: https://github.com/bairuofei/navigation_2d.git
branch: main
commit: 96b3e1fed08823dd1dd11ddb0eeead3bd24dd686
```

[Code]
两个仓库均保持原样；Phase 0 没有修改 planner、SLAM、frontier、TSP 或导航代码。

## 主机环境

[Code]

| 项目 | 当前值 | Phase 0 判断 |
|---|---:|---|
| Ubuntu | 20.04.6 LTS (focal) | 与 README 的测试平台一致 |
| ROS | Noetic | 与 README 一致 |
| 系统 Python | `/usr/bin/python3` 3.8.10 | 与 Noetic 兼容 |
| 当前 shell 的 Python | `/home/wcqw/anaconda3/bin/python3` 3.12.7 | 会干扰 catkin/ROS Python |
| CMake | 3.16.3 | 可以配置该工程 |
| GCC / G++ | 9.4.0 | 可以编译该工程的 C++11 代码 |
| Eigen | 3.3.7 | 已安装 |
| OpenCV | 4.2.0 | 已安装并被 CMake 找到 |
| SuiteSparse / TBB / LAPACK | 已安装 | `navigation_2d` 构建所需基础库可用 |
| Stage ROS | 已安装 | `stage_ros` 可被 `rospack` 找到 |

## 是否能直接运行

[Inference]
**当前不能直接运行官方 demo。** 硬件和 ROS 大框架基本匹配，但启动前仍有多个确定的环境/源码路径阻塞项。

### 已通过的验证

[Code]
在 `/tmp/acslam_catkin.J8FG3k` 建立了不污染源码的临时 catkin 工作区，并显式指定：

```bash
catkin_make -DPYTHON_EXECUTABLE=/usr/bin/python3 -DCMAKE_BUILD_TYPE=Debug
```

该命令成功完成，生成了 `mapper`、`navigator`、`operator`、`pub_path`、`updateDistance` 和两个 exploration plugin library 等构建产物。

[Code]
C++ 编译只有警告，没有编译错误。已观察到的警告包括：

- `src/graph/graph.cpp` 的赋值运算符缺少 `return *this`；
- 多个 ROS printf 风格日志用 `%d` 输出 `size_t`。

[Inference]
这些警告不阻止构建，但第一项属于潜在未定义行为，不能在尚未运行前断言它一定无害。

### 确定缺失或错误的项目

[Code]
默认执行 `catkin_make` 时，CMake 选中了 Conda Python 3.12.7，并因该环境缺少 `em`/`empy` 在配置阶段失败。强制 `/usr/bin/python3` 后构建通过。

[Code]
系统 Python 3.8 当前具有 `rospy`、`rospkg`、`empy`、NumPy、Matplotlib，但缺少：

- `networkx`；
- `scipy`；
- `tsp_solver`（dmishin/tsp-solver）；
- `concorde` Python 模块（pyconcorde）。

[Code]
Conda Python 3.12 具有 NetworkX、NumPy、SciPy、Matplotlib，但缺少 ROS Python 基础模块 `rospkg` 和 `empy`，也缺少 `tsp_solver` 与 `concorde`。

[Code]
系统 PATH 中没有 `concorde` 和 `linkern` 可执行文件。

[Code]
`p2os_urdf` 未安装。对默认 `exploration.launch` 做 ROS launch 解析时，首个确定错误为：

```text
Resource not found: p2os_urdf
```

[Code]
`rosdep` 尚未初始化，因此当前不能用 `rosdep check --from-paths ...` 自动给出完整依赖闭包。

[Code]
主仓库没有 `results/` 目录，而 launch 文件把规划时间和轨迹写到该目录。

[Code]
`scripts/path_planner.py:81` 在节点初始化期间无条件写入作者机器的绝对路径：

```text
/home/ruofei/code/cpp/catkin_cpp_ws/src/cpp_solver/scripts/prior_map.pickle
```

该路径在当前机器不存在。由于写入发生在三个规划服务创建之前，这会导致 `path_planner` 抛出 `FileNotFoundError` 并退出。

## 最可能遇到的三个环境问题

1. [Code] **Conda 劫持 catkin Python。** 当前 PATH 让 CMake 优先找到 Python 3.12.7；Noetic 的 Debian Python 模块安装在系统 Python 3.8 下。

2. [Code] **TSP Python 栈不完整。** `path_planner.py` 会间接无条件导入 `concorde`；即使把 launch 参数改成 `tsp-solver`，缺少 pyconcorde 仍可能在模块导入阶段使节点退出。

3. [Code] **launch 与本机资源不闭合。** 缺少 `p2os_urdf`，且源码内有作者绝对路径、缺失的 `results/` 目录；这三项都会在正式探索前暴露。

## 下一阶段前的环境门槛

[Inference]
进入 Phase 1 前至少应完成以下兼容性工作，并分别形成独立 checkpoint：

- 固定 catkin 使用 `/usr/bin/python3`，避免把 ROS Noetic 混入 Conda 3.12；
- 安装系统 Python 3.8 下的 NetworkX、SciPy、tsp-solver、pyconcorde，并确认 Concorde 后端可调用；
- 提供 `p2os_urdf/defs/pioneer3at.xacro`；
- 将作者绝对输出路径改为 ROS 参数或仓库内可写路径；
- 创建规范结果目录，并在启动前检查可写性；
- 初始化 `rosdep` 后重新检查依赖；
- 在永久 catkin 工作区构建并运行 launch 解析测试。

[Inference]
这些都属于环境、路径或实验记录修复，不改变论文的核心规划方法。

## Phase 0 边界

[Code]
本轮没有安装依赖，没有启动 Stage 探索，没有运行三种 baseline，也没有修改核心算法。当前结论仅覆盖环境审计、静态代码审计和临时编译验证。
