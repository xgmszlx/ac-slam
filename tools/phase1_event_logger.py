#!/usr/bin/python3

"""Read-only ROS event logger for Phase 1 baseline smoke runs."""

import argparse
import csv
import datetime
import json
import math
import os
import re
import threading

import rospy
from actionlib_msgs.msg import GoalStatusArray
from nav_msgs.msg import OccupancyGrid, Odometry
from nav2d_navigator.msg import ExploreActionResult
from rosgraph_msgs.msg import Log
from visualization_msgs.msg import Marker

from cpp_solver.msg import PoseGraph


class Phase1EventLogger:
    def __init__(self, output_path):
        self.output_path = os.path.abspath(output_path)
        self.summary_path = os.path.splitext(self.output_path)[0] + '_summary.json'
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        self.lock = threading.Lock()
        self.file = open(self.output_path, 'w', newline='', buffering=1)
        self.writer = csv.writer(self.file)
        self.writer.writerow(['timestamp', 'event', 'data'])

        self.current_path = []
        self.loop_active = False
        self.explore_active = False
        self.explore_start = None
        self.explore_end = None
        self.explore_result_status = None
        self.prev_gt = None
        self.exploration_path_length = 0.0
        self.pose_graph_vertices = 0
        self.pose_graph_edges = 0
        self.loop_closure_edges = 0
        self.map_summary = {}
        self.last_signature = None

        # Subscribe to the raw ROS logging bus. On this Noetic host /rosout_agg
        # did not forward messages continuously, while /rosout did.
        rospy.Subscriber('/rosout', Log, self.on_rosout, queue_size=200)
        rospy.Subscriber('/Explore/status', GoalStatusArray, self.on_explore_status, queue_size=20)
        rospy.Subscriber('/Explore/result', ExploreActionResult, self.on_explore_result, queue_size=5)
        rospy.Subscriber('/base_pose_ground_truth', Odometry, self.on_ground_truth, queue_size=50)
        rospy.Subscriber('/map', OccupancyGrid, self.on_map, queue_size=2)
        rospy.Subscriber('/slam_pose_graph', PoseGraph, self.on_pose_graph, queue_size=20)
        rospy.Subscriber('/Mapper/closure_edges', Marker, self.on_closure_edges, queue_size=5)
        rospy.on_shutdown(self.close)

    @staticmethod
    def wall_time():
        return datetime.datetime.now(datetime.timezone.utc).isoformat()

    def emit(self, event, data, timestamp=None):
        if timestamp is None:
            timestamp = rospy.get_time()
        payload = dict(data)
        payload['wall_time_utc'] = self.wall_time()
        signature = (event, json.dumps(payload, sort_keys=True, ensure_ascii=False))
        with self.lock:
            if signature == self.last_signature:
                return
            self.last_signature = signature
            self.writer.writerow([
                '{:.9f}'.format(float(timestamp)),
                event,
                json.dumps(payload, sort_keys=True, ensure_ascii=False),
            ])

    @staticmethod
    def parse_ints(text):
        return [int(value) for value in re.findall(r'-?\d+', text)]

    def on_rosout(self, msg):
        text = msg.msg.strip()
        timestamp = msg.header.stamp.to_sec() or rospy.get_time()

        if text == 'Find initial tsp path.':
            self.emit('TSP_CREATED', {'node': msg.name}, timestamp)
            return

        if text.startswith('Receive tsp path:'):
            self.current_path = self.parse_ints(text.split(':', 1)[1])
            self.emit('SLAM_PATH_CREATED', {'path': self.current_path, 'node': msg.name}, timestamp)
            return

        if text.startswith('Receive loop index:'):
            flags = self.parse_ints(text.split(':', 1)[1])
            for index, flag in enumerate(flags):
                if flag:
                    data = {'path_index': index, 'node': msg.name}
                    if index < len(self.current_path):
                        data['vertex'] = self.current_path[index]
                    self.emit('LOOP_INSERTED', data, timestamp)
            return

        if text.startswith('Replanning request.'):
            if self.loop_active:
                self.emit('LOOP_FINISHED', {'inferred_from': text, 'node': msg.name}, timestamp)
                self.loop_active = False
            self.emit('REPLAN_REQUESTED', {'message': text, 'node': msg.name}, timestamp)
            return

        match = re.search(r'Next target is loop vertex\s+(-?\d+)', text)
        if match:
            vertex = int(match.group(1))
            self.loop_active = True
            self.emit('HIGH_LEVEL_GOAL', {'vertex': vertex, 'is_loop': True, 'node': msg.name}, timestamp)
            self.emit('LOOP_STARTED', {'vertex': vertex, 'node': msg.name}, timestamp)
            return

        match = re.search(r'Set newGoal\s+(-?\d+)', text)
        if not match:
            match = re.search(r"Explore Goal\s+(-?\d+)", text)
        if match:
            self.emit('HIGH_LEVEL_GOAL', {
                'vertex': int(match.group(1)),
                'is_loop': False,
                'message': text,
                'node': msg.name,
            }, timestamp)
            return

        match = re.search(r'Reach vertex\s+(-?\d+)', text)
        if match:
            self.emit('GOAL_REACHED', {'vertex': int(match.group(1)), 'node': msg.name}, timestamp)
            return

        failure_patterns = (
            'No way between robot and goal',
            'Exploration has failed',
            'Navigation failed',
            'Planning failed',
            'could not get current position',
        )
        if any(pattern in text for pattern in failure_patterns):
            self.emit('GOAL_FAILED', {'message': text, 'node': msg.name}, timestamp)

    def on_explore_status(self, msg):
        if not msg.status_list:
            return
        status = msg.status_list[-1]
        if status.status == 1 and not self.explore_active:
            self.explore_active = True
            self.explore_start = status.goal_id.stamp.to_sec() or rospy.get_time()
            self.prev_gt = None

    def on_explore_result(self, msg):
        self.explore_end = msg.header.stamp.to_sec() or rospy.get_time()
        self.explore_result_status = int(msg.status.status)
        self.explore_active = False
        event = 'GOAL_REACHED' if msg.status.status == 3 else 'GOAL_FAILED'
        self.emit(event, {
            'scope': 'exploration_action',
            'status': int(msg.status.status),
            'text': msg.status.text,
        }, self.explore_end)

    def on_ground_truth(self, msg):
        if not self.explore_active:
            return
        point = (msg.pose.pose.position.x, msg.pose.pose.position.y)
        if self.prev_gt is not None:
            self.exploration_path_length += math.hypot(
                point[0] - self.prev_gt[0], point[1] - self.prev_gt[1]
            )
        self.prev_gt = point

    def on_map(self, msg):
        known = sum(value >= 0 for value in msg.data)
        self.map_summary = {
            'stamp': msg.header.stamp.to_sec(),
            'resolution': msg.info.resolution,
            'width': msg.info.width,
            'height': msg.info.height,
            'known': known,
            'free': sum(value == 0 for value in msg.data),
            'occupied': sum(value > 50 for value in msg.data),
            'unknown': len(msg.data) - known,
        }

    def on_pose_graph(self, msg):
        self.pose_graph_vertices = max(
            self.pose_graph_vertices, msg.vertex_start_idx + len(msg.vertices)
        )
        self.pose_graph_edges = max(
            self.pose_graph_edges, msg.edge_start_idx + len(msg.edges_start)
        )

    def on_closure_edges(self, msg):
        # nav2d_karto publishes a LINE_LIST marker: every two points are one
        # detected loop-closure edge. Reading the latched marker is passive.
        self.loop_closure_edges = max(self.loop_closure_edges, len(msg.points) // 2)

    def close(self):
        with self.lock:
            if self.file.closed:
                return
            summary = {
                'explore_start_sim_time': self.explore_start,
                'explore_end_sim_time': self.explore_end,
                'total_exploration_time': (
                    self.explore_end - self.explore_start
                    if self.explore_start is not None and self.explore_end is not None
                    else None
                ),
                'total_path_length_gt': self.exploration_path_length,
                'explore_result_status': self.explore_result_status,
                'pose_graph_vertices': self.pose_graph_vertices,
                'pose_graph_edges': self.pose_graph_edges,
                'loop_closure_edges': self.loop_closure_edges,
                'final_map': self.map_summary,
            }
            with open(self.summary_path, 'w') as summary_file:
                json.dump(summary, summary_file, indent=2, sort_keys=True)
                summary_file.write('\n')
            self.file.flush()
            self.file.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args(rospy.myargv()[1:])
    rospy.init_node('phase1_event_logger', anonymous=False)
    Phase1EventLogger(args.output)
    rospy.spin()


if __name__ == '__main__':
    main()
