#!/usr/bin/python3

"""Run roslaunch in the local-only Phase 1 sandbox.

The managed execution sandbox blocks netifaces from enumerating host network
interfaces.  roslaunch performs that enumeration even for an all-local launch.
Pre-populating ROS's address cache keeps the launch local without changing any
SLAM, planning, or navigation code.
"""

import sys

import rosgraph.network
import roslaunch


rosgraph.network._local_addrs = ['127.0.0.1']
roslaunch.main(sys.argv)
