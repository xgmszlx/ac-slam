# 本轮真实执行与恢复边界

状态BASELINE_NOT_QUALIFIED；0次真实NGD序列、0模型推理、M1/M2均未实现。

- 固定作者提交：a93a14c4019efc7a209be5fbf9fefa46f5d1d90f，https://github.com/yuhaozhang7/NGD-SLAM 。已有Git元数据和三个认证文件不代表所需文件已完整checkout。
- 需要src、include、Thirdparty（包括YOLO的cfg/weights/classes）、RGB-D入口与原构建文件；无需重复下载旧数据关联列表。正常网络下可用Git sparse checkout，仅获取这些路径；本轮实际TLS失败，未认证全仓。
- OpenCV选择4.5.5，官方OpenCV源：https://github.com/opencv/opencv/tree/4.5.5 。本轮备用官方opencv-python4.5.5.64源码包：https://pypi.org/project/opencv-python/4.5.5.64/#files ，期望89,920,521字节，SHA256 f65de0446a330c3b773cd04ba10345d8ce1b15dcac3f49770204e37602d0b3f7；现有9,216,549字节不可使用。
- 大型文件/构建均在external链接到的独立目录；旧依赖、库与源码不改。不再执行本轮下载尝试，也不运行无界build.sh。

实际原生配置探针（未修改作者CMake版本要求）：

```bash
/usr/bin/cmake -S /media/wcqw/KESU/slam_research/ngd_slam_20261020/NGD-SLAM \
  -B /media/wcqw/KESU/slam_research/ngd_slam_20261020/configure_native_gate \
  -DCMAKE_BUILD_TYPE=Release \
  -DPangolin_DIR=/home/wcqw/passive_visual_slam_qualification_20261015/local/lib/cmake/Pangolin
```

exit1：OpenCV4.2被4.4版本门拒绝；未到达核心编译。native_configure.log保留原输出。

软件语义控制：`g++ -std=c++14 -O2 -Wall -Wextra code/semantics_probe.cc -o external/semantics_probe`，然后执行并记录audit/semantics_probe.csv。它仅测试C++布尔/角度和>80%谓词，不使用图像、GT或SLAM，不是模拟科研结果。

若未来完整资料到位，先校验Git版本/模型内容、私有OpenCV及链接无4.2混入，再按原生作者处理运行walking、sitting、Bonn各一次；保留BGR/真实标定、原关联与GT离线SE3评价。只有真实掩码/约束行为证据成立才讨论M1/M2，不自动开展方法工程。
