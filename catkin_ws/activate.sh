#!/usr/bin/env bash

_acslam_ws="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source /opt/ros/noetic/setup.bash
if [[ -f "${_acslam_ws}/devel/setup.bash" ]]; then
    source "${_acslam_ws}/devel/setup.bash"
fi

export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="${_acslam_ws}/python${PYTHONPATH:+:${PYTHONPATH}}"
export PATH="${_acslam_ws}/tools/concorde:/opt/ros/noetic/bin:/usr/bin:${PATH}"
export ROS_HOME="${_acslam_ws}/.ros"
export ROS_LOG_DIR="${_acslam_ws}/.ros/log"
export ROS_IP="127.0.0.1"
export AC_SLAM_CATKIN_WS="${_acslam_ws}"

unset _acslam_ws
