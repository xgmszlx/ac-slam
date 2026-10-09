#!/bin/bash
# Isolated overlay only: no writes to /opt/ros or the production catkin workspace.
source /opt/ros/noetic/setup.bash
export CD_B0_WS=/home/wcqw/ac-slam_cd_b0_ws
export CMAKE_PREFIX_PATH="$CD_B0_WS/devel:$CD_B0_WS/apt_root/opt/ros/noetic:$CD_B0_WS/apt_root/usr:/opt/ros/noetic"
export LD_LIBRARY_PATH="$CD_B0_WS/devel/lib:$CD_B0_WS/apt_root/opt/ros/noetic/lib:$CD_B0_WS/apt_root/usr/lib:$CD_B0_WS/apt_root/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="$CD_B0_WS/apt_root/opt/ros/noetic/lib/python3/dist-packages:${PYTHONPATH:-}"
export ROS_PACKAGE_PATH="$CD_B0_WS/src/slam_toolbox:$CD_B0_WS/apt_root/opt/ros/noetic/share:${ROS_PACKAGE_PATH:-}"
export PATH=/usr/bin:/bin:/opt/ros/noetic/bin

