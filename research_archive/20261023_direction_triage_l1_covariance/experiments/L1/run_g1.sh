#!/usr/bin/env bash
# L1 G1 full measurement runner (frozen config, see protocol/PREREG.md §2)
# One run per sequence; no retries.
set +u
export ROS_MASTER_URI=http://localhost:11355
export ROS_HOME=/home/wcqw/slam_multi_direction_research/logs/ros_home_l1
export ROS_DISTRO=noetic
source /opt/ros/noetic/setup.bash

ROOT=/home/wcqw/slam_multi_direction_research
EXP=$ROOT/experiments/L1
DATA=/home/wcqw/lilocbench_amcl_validation_20261016/data
STAMP=$(date +%Y%m%dT%H%M%S)

run_seq () {
  local SEQ="$1"
  local RUN_ID="L1_G1_hector_${SEQ}_${STAMP}"
  local OUT="$EXP/runs/$RUN_ID"
  mkdir -p "$OUT"
  echo "=== [$RUN_ID] start $(date -Is) ==="

  # fresh hector instance (new map)
  pkill -x hector_mapping 2>/dev/null; sleep 2
  rosrun hector_mapping hector_mapping \
      _map_frame:=map _odom_frame:=odom _base_frame:=base_link \
      _pub_map_odom_transform:=true _map_resolution:=0.05 _map_size:=2048 \
      _map_update_distance_thresh:=0.4 _map_update_angle_thresh:=0.9 \
      _scan_topic:=/laser_scan_front/scan _pub_debug_output:=true _use_sim_time:=true \
      > "$OUT/hector_stdout.log" 2> "$OUT/hector_stderr.log" &
  sleep 6

  rosbag record -O "$OUT/measure.bag" /hector_debug_info /poseupdate /slam_out_pose \
      __name:=l1rec > "$OUT/record.log" 2>&1 &
  sleep 3

  rosbag play -r 1.0 --clock "$DATA/${SEQ}.bag" > "$OUT/play.log" 2>&1
  local PLAY_RC=$?
  sleep 2
  rosnode kill /l1rec 2>/dev/null; sleep 3
  pkill -x hector_mapping 2>/dev/null; sleep 2

  echo "$PLAY_RC" > "$OUT/play_exit_code"
  rosbag info "$OUT/measure.bag" > "$OUT/measure_bag_info.txt" 2>&1
  echo "=== [$RUN_ID] done $(date -Is) play_rc=$PLAY_RC ==="
  echo "$RUN_ID" >> "$EXP/runs/run_ids.txt"
}

run_seq static_0
run_seq lt_changes_0
echo "ALL_DONE"
