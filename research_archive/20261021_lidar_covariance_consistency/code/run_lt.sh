#!/bin/bash
source /opt/ros/noetic/setup.bash
D=/home/wcqw/lilocbench_amcl_validation_20261016/data
/usr/bin/python3 extract.py "$D/lt_changes_0.bag" lt_changes_0.npz /laser_scan_front/scan
for s in 0.02 0.04 0.06; do
  /usr/bin/python3 run_v3.py lt_changes_0.npz "$D/gt/lt_changes_0/gt_poses.txt" $s lt$s 60
done
