#!/usr/bin/python3
"""Passive Phase 2 observer for paired active-SLAM experiments.

This node only subscribes to ROS topics/logs and writes experiment artifacts.
It never publishes, calls a service, or changes planner state.
"""

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
from nav_msgs.msg import OccupancyGrid, Odometry, Path
from nav2d_navigator.msg import ExploreActionResult
from rosgraph_msgs.msg import Log
from visualization_msgs.msg import Marker

from cpp_solver.msg import LoopClosureEvent, PoseGraph


class Phase2Observer:
    def __init__(self, output_dir):
        self.output_dir = os.path.abspath(output_dir)
        self.snapshot_dir = os.path.join(self.output_dir, 'loop_snapshots')
        os.makedirs(self.snapshot_dir, exist_ok=True)
        self.lock = threading.RLock()

        self.events_file = open(os.path.join(self.output_dir, 'events.csv'), 'w', newline='', buffering=1)
        self.events = csv.writer(self.events_file)
        self.events.writerow(['timestamp', 'event', 'data'])
        self.gt_file = open(os.path.join(self.output_dir, 'ground_truth_samples.csv'), 'w', newline='', buffering=1)
        self.gt_writer = csv.writer(self.gt_file)
        self.gt_writer.writerow(['timestamp', 'x', 'y', 'yaw', 'exploration_active', 'loop_id'])
        self.pg_updates_file = open(os.path.join(self.output_dir, 'pose_graph_updates.jsonl'), 'w', buffering=1)

        self.explore_active = False
        self.explore_start = None
        self.explore_end = None
        self.explore_status = None
        self.prev_gt = None
        self.current_gt = None
        self.total_distance = 0.0
        self.map_summary = {}

        self.pose_nodes = {}
        self.pose_edges = {}
        self.latest_slam_path = []
        self.closure_edges = []
        self.karto_closure_events = []
        self.loop_closed_events = []
        self.gate_events = []
        self.repair_events = []
        self.early_stop_events = []

        self.plan_history = []
        self.current_path = []
        self.initial_planned_path = []
        self.initial_loop_flags = []
        self.actual_visited_sequence = []
        self.goal_reached_sequence = []
        self.loops = []
        self.active_loop = None
        self.pending_after_loop = None

        self.counts = {
            'no_frontier_at_vertex': 0,
            'no_frontier_reachable': 0,
            'repeated_visit_skip': 0,
            'goal_skip_seen_no_frontier': 0,
            'local_replanning_calls': 0,
            'replan_requests': 0,
            'goal_failures': 0,
        }

        rospy.Subscriber('/rosout', Log, self.on_rosout, queue_size=1000)
        rospy.Subscriber('/Explore/status', GoalStatusArray, self.on_explore_status, queue_size=20)
        rospy.Subscriber('/Explore/result', ExploreActionResult, self.on_explore_result, queue_size=5)
        rospy.Subscriber('/base_pose_ground_truth', Odometry, self.on_ground_truth, queue_size=200)
        rospy.Subscriber('/map', OccupancyGrid, self.on_map, queue_size=2)
        rospy.Subscriber('/slam_pose_graph', PoseGraph, self.on_pose_graph, queue_size=100)
        rospy.Subscriber('/Mapper/closure_edges', Marker, self.on_closure_edges, queue_size=20)
        rospy.Subscriber('/Mapper/loop_closed', LoopClosureEvent, self.on_loop_closed, queue_size=20)
        rospy.Subscriber('/slam_path', Path, self.on_slam_path, queue_size=10)
        rospy.on_shutdown(self.close)

    @staticmethod
    def wall_time():
        return datetime.datetime.now(datetime.timezone.utc).isoformat()

    @staticmethod
    def parse_ints(text):
        return [int(value) for value in re.findall(r'-?\d+', text)]

    def emit(self, event, data, timestamp=None):
        if timestamp is None:
            timestamp = rospy.get_time()
        payload = dict(data)
        payload['wall_time_utc'] = self.wall_time()
        with self.lock:
            self.events.writerow([
                '{:.9f}'.format(float(timestamp)), event,
                json.dumps(payload, sort_keys=True, ensure_ascii=False),
            ])

    def new_loop(self, vertex, planned_start):
        loop = {
            'loop_id': len(self.loops) + 1,
            'loop_vertex': int(vertex),
            'planned_start_time': float(planned_start),
            'actual_start_time': None,
            'actual_end_time': None,
            'extra_distance': None,
            'extra_time': None,
            'extra_cost_definition': 'actual GT distance/time while the inserted loop waypoint sequence executes',
            'reliable_loop_service_success': None,
            'fallback': None,
            'planned_loop_path': [],
            'actual_loop_trajectory': [],
            'waypoints_planned': None,
            'waypoints_reached': [],
            'executed_loop': False,
            'execution_finished': False,
            'all_planned_waypoints_reached': False,
            'early_stopped': False,
            'execution_policy': None,
            'successful_slam_loop': False,
            'karto_closure_events_during_execution': 0,
            'accepted_closure_events_during_execution': 0,
            'accepted_closure_events': [],
            'accepted_active_loop': False,
            'snapshot_before': None,
            'snapshot_after': None,
        }
        self.loops.append(loop)
        return loop

    def snapshot(self, loop, phase, timestamp=None):
        if timestamp is None:
            timestamp = rospy.get_time()
        filename = 'loop_{:02d}_{}.json'.format(loop['loop_id'], phase)
        path = os.path.join(self.snapshot_dir, filename)
        data = {
            'loop_id': loop['loop_id'],
            'loop_vertex': loop['loop_vertex'],
            'phase': phase,
            'timestamp': float(timestamp),
            'wall_time_utc': self.wall_time(),
            'pose_graph_node_count': len(self.pose_nodes),
            'pose_graph_edge_count': len(self.pose_edges),
            'pose_graph_nodes': self.pose_nodes,
            'pose_graph_edges': list(self.pose_edges.values()),
            'identifiable_nonlocal_edges': [
                edge for edge in self.pose_edges.values()
                if abs(edge['start'] - edge['end']) > 1
            ],
            'karto_closure_edge_count': len(self.closure_edges),
            'karto_closure_edge_endpoints': self.closure_edges,
            'trajectory_estimate': self.latest_slam_path,
        }
        with open(path, 'w') as output:
            json.dump(data, output, indent=2, sort_keys=True)
            output.write('\n')
        loop['snapshot_' + phase] = os.path.relpath(path, self.output_dir)
        return data

    def finalize_loop_graph_evidence(self, loop, after_snapshot):
        before_path = loop.get('snapshot_before')
        if not before_path:
            return
        with open(os.path.join(self.output_dir, before_path)) as input_file:
            before = json.load(input_file)
        before_indices = {e['index'] for e in before['pose_graph_edges']}
        new_edges = sorted(
            (e for e in after_snapshot['pose_graph_edges'] if e['index'] not in before_indices),
            key=lambda edge: edge['index'],
        )
        new_nonlocal = [edge for edge in new_edges if abs(edge['start'] - edge['end']) > 1]
        new_beyond_running_buffer = [
            edge for edge in new_edges if abs(edge['start'] - edge['end']) > 70
        ]
        closure_delta = (
            after_snapshot['karto_closure_edge_count'] - before['karto_closure_edge_count']
        )
        loop['pose_graph_node_delta'] = (
            after_snapshot['pose_graph_node_count'] - before['pose_graph_node_count']
        )
        loop['pose_graph_edge_delta'] = (
            after_snapshot['pose_graph_edge_count'] - before['pose_graph_edge_count']
        )
        loop['new_pose_graph_edges'] = new_edges
        loop['new_identifiable_nonlocal_edges'] = new_nonlocal
        loop['new_edges_beyond_70_scan_running_buffer'] = new_beyond_running_buffer
        loop['karto_closure_edge_delta'] = closure_delta
        # Karto's closure_edges marker also contains ordinary near-chain links.
        # Count an accepted SLAM loop only when OpenKarto reports the accepted
        # loop and the graph adds an edge outside its default 70-scan running
        # buffer. Marker deltas remain auxiliary raw evidence.
        loop['successful_slam_loop'] = (
            loop.get('karto_closure_events_during_execution', 0) > 0
            and bool(new_beyond_running_buffer)
        )
        loop['successful_slam_loop_criterion'] = (
            'Karto accepted-loop event during execution AND a new pose-graph edge '
            'with node-index gap > default ScanBufferSize 70'
        )
        loop['accepted_active_loop'] = bool(
            loop.get('accepted_closure_events_during_execution', 0) > 0
        )
        loop['accepted_active_loop_criterion'] = (
            '/Mapper/loop_closed Karto-accepted event timestamp inside active-loop interval'
        )

    def on_rosout(self, msg):
        text = msg.msg.strip()
        timestamp = msg.header.stamp.to_sec() or rospy.get_time()
        with self.lock:
            if text.startswith('Receive tsp path:'):
                path = self.parse_ints(text.split(':', 1)[1])
                self.current_path = path
                if not self.initial_planned_path:
                    self.initial_planned_path = list(path)
                self.plan_history.append({'timestamp': timestamp, 'source': text, 'path': path})
                self.emit('SLAM_PATH_CREATED', {'path': path, 'node': msg.name}, timestamp)
                return

            if text.startswith('Receive loop index:'):
                flags = self.parse_ints(text.split(':', 1)[1])
                if not self.initial_loop_flags:
                    self.initial_loop_flags = list(flags)
                for index, flag in enumerate(flags):
                    if flag:
                        self.emit('LOOP_INSERTED', {
                            'path_index': index,
                            'vertex': self.current_path[index] if index < len(self.current_path) else None,
                        }, timestamp)
                return

            if text.startswith('Really visited vertices:'):
                sequence = self.parse_ints(text.split(':', 1)[1])
                if len(sequence) >= len(self.actual_visited_sequence):
                    self.actual_visited_sequence = sequence
                return

            match = re.search(r'Next target is loop vertex\s+(-?\d+)', text)
            if match:
                if self.pending_after_loop is not None:
                    after = self.snapshot(self.pending_after_loop, 'after', timestamp)
                    self.finalize_loop_graph_evidence(self.pending_after_loop, after)
                    self.pending_after_loop = None
                self.active_loop = self.new_loop(int(match.group(1)), timestamp)
                self.emit('LOOP_PLANNED', {
                    'loop_id': self.active_loop['loop_id'], 'vertex': self.active_loop['loop_vertex']
                }, timestamp)
                return

            match = re.match(
                r'PHASE2_LOOP_PLANNED vertex=(-?\d+) source=(\S+) waypoints=(\d+) path=(.*)', text
            )
            if match:
                vertex, source, waypoint_count, path_text = match.groups()
                if self.active_loop is None or self.active_loop['loop_vertex'] != int(vertex):
                    self.active_loop = self.new_loop(int(vertex), timestamp)
                points = []
                if path_text:
                    for item in path_text.split(';'):
                        x_value, y_value = item.split(',')
                        points.append([float(x_value), float(y_value)])
                self.active_loop['reliable_loop_service_success'] = source == 'reliable_loop_service'
                self.active_loop['fallback'] = source == 'fallback'
                self.active_loop['waypoints_planned'] = int(waypoint_count)
                self.active_loop['planned_loop_path'] = points
                self.emit('LOOP_PATH_OBSERVED', {
                    'loop_id': self.active_loop['loop_id'], 'vertex': int(vertex),
                    'source': source, 'path': points,
                }, timestamp)
                return

            match = re.match(
                r'PHASE3A_ORACLE_V1 vertex=(-?\d+) window_poses=(\d+) '
                r'trace_len_m=([0-9.]+) waypoints=(\d+)', text
            )
            if match:
                vertex, window_poses, trace_len, waypoints = match.groups()
                record = {
                    'timestamp': timestamp, 'vertex': int(vertex),
                    'policy': 'ALWAYS_TRACE', 'window_poses': int(window_poses),
                    'planned_length_m': float(trace_len), 'waypoints': int(waypoints),
                }
                self.repair_events.append(record)
                if self.active_loop is not None and self.active_loop['loop_vertex'] == int(vertex):
                    self.active_loop['execution_policy'] = 'ALWAYS_TRACE'
                    self.active_loop['repair_plan'] = record
                self.emit('REPAIR_PLANNED', record, timestamp)
                return

            match = re.match(
                r'PHASE4A_SELECTIVE_REPAIR vertex=(-?\d+) span_m=([0-9.]+) '
                r'planned_len_m=([0-9.]+) waypoints=(\d+)', text
            )
            if match:
                vertex, span, planned_len, waypoints = match.groups()
                gate = {
                    'timestamp': timestamp, 'vertex': int(vertex),
                    'span_m': float(span), 'gate_m': 4.0, 'decision': 'REPAIR',
                }
                repair = {
                    'timestamp': timestamp, 'vertex': int(vertex),
                    'policy': 'SELECTIVE_REPAIR', 'span_m': float(span),
                    'planned_length_m': float(planned_len), 'waypoints': int(waypoints),
                }
                self.gate_events.append(gate)
                self.repair_events.append(repair)
                if self.active_loop is not None and self.active_loop['loop_vertex'] == int(vertex):
                    self.active_loop['execution_policy'] = 'SELECTIVE_REPAIR'
                    self.active_loop['gate_decision'] = gate
                    self.active_loop['repair_plan'] = repair
                self.emit('GATE_DECISION', gate, timestamp)
                self.emit('REPAIR_PLANNED', repair, timestamp)
                return

            match = re.match(
                r'PHASE4A_SELECTIVE_DECISION vertex=(-?\d+) span_m=([0-9.]+|None) '
                r'gate=([0-9.]+) decision=(REPAIR|NO_REPAIR)', text
            )
            if match:
                vertex, span, gate_value, decision = match.groups()
                record = {
                    'timestamp': timestamp, 'vertex': int(vertex),
                    'span_m': None if span == 'None' else float(span),
                    'gate_m': float(gate_value), 'decision': decision,
                }
                self.gate_events.append(record)
                if self.active_loop is not None and self.active_loop['loop_vertex'] == int(vertex):
                    self.active_loop['execution_policy'] = decision
                    self.active_loop['gate_decision'] = record
                self.emit('GATE_DECISION', record, timestamp)
                return

            match = re.match(
                r'PHASE4A_SELECTIVE_REPAIR_FAILED vertex=(-?\d+) span_m=([0-9.]+)', text
            )
            if match:
                record = {
                    'timestamp': timestamp, 'vertex': int(match.group(1)),
                    'span_m': float(match.group(2)), 'policy': 'REPAIR_FAILED_FALLBACK',
                }
                self.repair_events.append(record)
                self.emit('REPAIR_FAILED', record, timestamp)
                return

            match = re.match(
                r'PHASE4A_EARLY_STOP vertex=(-?\d+) at_waypoint=(\d+) of (\d+)', text
            )
            if match:
                vertex, waypoint, planned = map(int, match.groups())
                record = {
                    'timestamp': timestamp, 'vertex': vertex,
                    'at_waypoint': waypoint, 'planned_waypoints': planned,
                    'saved_waypoints': max(0, planned - waypoint),
                }
                self.early_stop_events.append(record)
                if self.active_loop is not None and self.active_loop['loop_vertex'] == vertex:
                    self.active_loop['early_stopped'] = True
                    self.active_loop['early_stop'] = record
                self.emit('EARLY_STOP', record, timestamp)
                return

            match = re.match(r'PHASE2_LOOP_EXECUTION_STARTED vertex=(-?\d+) waypoints=(\d+)', text)
            if match:
                vertex, waypoint_count = (int(match.group(1)), int(match.group(2)))
                if self.active_loop is None or self.active_loop['loop_vertex'] != vertex:
                    self.active_loop = self.new_loop(vertex, timestamp)
                self.active_loop['actual_start_time'] = timestamp
                self.active_loop['waypoints_planned'] = waypoint_count
                self.active_loop['_start_karto_events'] = len(self.karto_closure_events)
                self.active_loop['_start_loop_closed_events'] = len(self.loop_closed_events)
                self.active_loop['_distance'] = 0.0
                self.active_loop['_prev_gt'] = self.current_gt
                self.snapshot(self.active_loop, 'before', timestamp)
                self.emit('LOOP_STARTED', {
                    'loop_id': self.active_loop['loop_id'], 'vertex': vertex,
                }, timestamp)
                return

            match = re.match(r'PHASE2_LOOP_WAYPOINT_REACHED vertex=(-?\d+) waypoint=(\d+)', text)
            if match and self.active_loop is not None:
                waypoint = int(match.group(2))
                self.active_loop['waypoints_reached'].append(waypoint)
                self.emit('LOOP_WAYPOINT_REACHED', {
                    'loop_id': self.active_loop['loop_id'], 'waypoint': waypoint,
                }, timestamp)
                return

            match = re.match(r'PHASE2_LOOP_EXECUTION_FINISHED vertex=(-?\d+) waypoints=(\d+)', text)
            if match and self.active_loop is not None:
                self.active_loop['actual_end_time'] = timestamp
                self.active_loop['extra_time'] = timestamp - self.active_loop['actual_start_time']
                self.active_loop['extra_distance'] = self.active_loop.pop('_distance', 0.0)
                self.active_loop.pop('_prev_gt', None)
                self.active_loop['all_planned_waypoints_reached'] = (
                    len(set(self.active_loop['waypoints_reached'])) >= int(match.group(2))
                )
                # Preserve the historical field while exposing early-stop-aware execution
                # separately for the Phase 4B denominator.
                self.active_loop['executed_loop'] = self.active_loop['all_planned_waypoints_reached']
                self.active_loop['execution_finished'] = True
                self.active_loop['karto_closure_events_during_execution'] = (
                    len(self.karto_closure_events) - self.active_loop.pop('_start_karto_events', 0)
                )
                start_index = self.active_loop.pop('_start_loop_closed_events', 0)
                accepted = self.loop_closed_events[start_index:]
                accepted = [event for event in accepted if event['stamp'] <= timestamp + 1e-9]
                self.active_loop['accepted_closure_events'] = accepted
                self.active_loop['accepted_closure_events_during_execution'] = len(accepted)
                self.active_loop['accepted_active_loop'] = bool(accepted)
                self.emit('LOOP_FINISHED', {
                    'loop_id': self.active_loop['loop_id'],
                    'vertex': self.active_loop['loop_vertex'],
                    'executed_loop': self.active_loop['executed_loop'],
                }, timestamp)
                self.pending_after_loop = self.active_loop
                self.active_loop = None
                return

            if 'Add one Loop closure.' in text:
                self.karto_closure_events.append({'timestamp': timestamp, 'message': text})
                self.emit('KARTO_LOOP_CONSTRAINT', {'message': text}, timestamp)
                return

            if text.startswith('Replanning request.'):
                self.counts['replan_requests'] += 1
                self.emit('REPLAN_REQUESTED', {'message': text}, timestamp)
            elif text.startswith('Call local replanning'):
                self.counts['local_replanning_calls'] += 1
                self.emit('LOCAL_REPLAN', {'message': text}, timestamp)
            elif text.startswith('Skip repeated visit to vertex'):
                self.counts['repeated_visit_skip'] += 1
                self.emit('REPEATED_VISIT_SKIP', {'message': text}, timestamp)
            elif text.startswith('Skip currGoal') and 'no frontier' in text:
                self.counts['goal_skip_seen_no_frontier'] += 1
                self.emit('GOAL_SKIP', {'message': text}, timestamp)
            elif text.startswith('No frontier at vertex'):
                self.counts['no_frontier_at_vertex'] += 1
                self.emit('NO_FRONTIER', {'message': text}, timestamp)
            elif text.startswith('No frontier reachable at vertex'):
                self.counts['no_frontier_reachable'] += 1
                self.emit('NO_FRONTIER_REACHABLE', {'message': text}, timestamp)

            match = re.search(r'Reach vertex\s+(-?\d+)', text)
            if match:
                vertex = int(match.group(1))
                self.goal_reached_sequence.append(vertex)
                self.emit('GOAL_REACHED', {'vertex': vertex}, timestamp)

            failure_patterns = (
                'No way between robot and goal', 'Exploration has failed',
                'Navigation failed', 'Planning failed', 'could not get current position',
            )
            if any(pattern in text for pattern in failure_patterns):
                self.counts['goal_failures'] += 1
                self.emit('GOAL_FAILED', {'message': text}, timestamp)

    def on_explore_status(self, msg):
        if not msg.status_list:
            return
        status = msg.status_list[-1]
        with self.lock:
            if status.status == 1 and not self.explore_active:
                self.explore_active = True
                self.explore_start = status.goal_id.stamp.to_sec() or rospy.get_time()
                self.prev_gt = None

    def on_explore_result(self, msg):
        with self.lock:
            self.explore_end = msg.header.stamp.to_sec() or rospy.get_time()
            self.explore_status = int(msg.status.status)
            self.explore_active = False
            self.emit('EXPLORATION_RESULT', {
                'status': self.explore_status, 'text': msg.status.text,
            }, self.explore_end)

    def on_ground_truth(self, msg):
        timestamp = msg.header.stamp.to_sec() or rospy.get_time()
        orientation = msg.pose.pose.orientation
        yaw = math.atan2(
            2.0 * (orientation.w * orientation.z + orientation.x * orientation.y),
            1.0 - 2.0 * (orientation.y * orientation.y + orientation.z * orientation.z),
        )
        point = (msg.pose.pose.position.x, msg.pose.pose.position.y, yaw, timestamp)
        with self.lock:
            self.current_gt = point
            loop_id = self.active_loop['loop_id'] if self.active_loop is not None else ''
            self.gt_writer.writerow([
                '{:.9f}'.format(timestamp), point[0], point[1], point[2],
                int(self.explore_active), loop_id,
            ])
            if self.explore_active:
                if self.prev_gt is not None:
                    self.total_distance += math.hypot(point[0] - self.prev_gt[0], point[1] - self.prev_gt[1])
                self.prev_gt = point
            if self.active_loop is not None and self.active_loop.get('actual_start_time') is not None:
                previous = self.active_loop.get('_prev_gt')
                if previous is not None:
                    self.active_loop['_distance'] += math.hypot(point[0] - previous[0], point[1] - previous[1])
                self.active_loop['_prev_gt'] = point
                self.active_loop['actual_loop_trajectory'].append([
                    timestamp, point[0], point[1], point[2]
                ])

    def on_map(self, msg):
        with self.lock:
            known = sum(value >= 0 for value in msg.data)
            self.map_summary = {
                'stamp': msg.header.stamp.to_sec(), 'resolution': msg.info.resolution,
                'width': msg.info.width, 'height': msg.info.height,
                'known': known, 'free': sum(value == 0 for value in msg.data),
                'occupied': sum(value > 50 for value in msg.data),
                'unknown': len(msg.data) - known,
            }

    def on_pose_graph(self, msg):
        timestamp = rospy.get_time()
        with self.lock:
            for index, node in enumerate(msg.vertices):
                self.pose_nodes[str(node)] = {
                    'id': int(node), 'x': float(msg.vertex_x[index]),
                    'y': float(msg.vertex_y[index]), 'theta': float(msg.vertex_theta[index]),
                }
            added_edges = []
            for index, start in enumerate(msg.edges_start):
                end = int(msg.edges_end[index])
                edge_index = int(msg.edge_start_idx + index)
                key = str(edge_index)
                edge = {
                    'index': edge_index, 'start': int(start), 'end': end,
                    'covariance_upper_triangle': msg.covariance[index],
                }
                self.pose_edges[key] = edge
                added_edges.append(edge)
            self.pg_updates_file.write(json.dumps({
                'timestamp': timestamp, 'vertex_start_idx': int(msg.vertex_start_idx),
                'edge_start_idx': int(msg.edge_start_idx),
                'vertices': [int(value) for value in msg.vertices], 'edges': added_edges,
            }, sort_keys=True) + '\n')

    def on_closure_edges(self, msg):
        timestamp = rospy.get_time()
        with self.lock:
            self.closure_edges = [
                [[msg.points[i].x, msg.points[i].y], [msg.points[i + 1].x, msg.points[i + 1].y]]
                for i in range(0, len(msg.points) - 1, 2)
            ]
            if self.pending_after_loop is not None:
                after = self.snapshot(self.pending_after_loop, 'after', timestamp)
                self.finalize_loop_graph_evidence(self.pending_after_loop, after)
                self.pending_after_loop = None

    def on_loop_closed(self, msg):
        event = {
            'seq': int(msg.seq),
            'loop_count': int(msg.loop_count),
            'current_scan': int(msg.current_scan),
            'chain_start': int(msg.chain_start),
            'chain_end': int(msg.chain_end),
            'stamp': float(msg.stamp.to_sec()),
            'received_ros_time': float(rospy.get_time()),
            'received_wall_time_utc': self.wall_time(),
        }
        with self.lock:
            self.loop_closed_events.append(event)
            if self.active_loop is not None and self.active_loop.get('actual_start_time') is not None:
                if event['stamp'] + 1e-9 >= self.active_loop['actual_start_time']:
                    self.active_loop.setdefault('accepted_closure_events', []).append(event)
            self.emit('KARTO_LOOP_ACCEPTED', event, event['stamp'])

    def on_slam_path(self, msg):
        with self.lock:
            self.latest_slam_path = []
            for item in msg.poses:
                pose = item.pose
                self.latest_slam_path.append({
                    'x': pose.position.x, 'y': pose.position.y,
                    'qx': pose.orientation.x, 'qy': pose.orientation.y,
                    'qz': pose.orientation.z, 'qw': pose.orientation.w,
                })

    def close(self):
        with self.lock:
            if self.events_file.closed:
                return
            if self.explore_active and self.explore_end is None:
                # A runner timeout or navigation failure can end the process before an
                # Explore result message. Preserve the observed interval without
                # relabelling it as a successful action.
                self.explore_end = rospy.get_time()
                self.explore_active = False
            if self.pending_after_loop is not None:
                after = self.snapshot(self.pending_after_loop, 'after', rospy.get_time())
                self.finalize_loop_graph_evidence(self.pending_after_loop, after)
                self.pending_after_loop = None
            if self.active_loop is not None and self.active_loop.get('actual_start_time') is not None:
                self.active_loop['actual_end_time'] = rospy.get_time()
                self.active_loop['executed_loop'] = False
                self.active_loop['incomplete_reason'] = 'observer shutdown during loop execution'

            for loop in self.loops:
                loop.pop('_distance', None)
                loop.pop('_prev_gt', None)
                loop.pop('_start_karto_events', None)
                loop.pop('_start_loop_closed_events', None)
            loops_payload = {'loops': self.loops}
            with open(os.path.join(self.output_dir, 'loops.json'), 'w') as output:
                json.dump(loops_payload, output, indent=2, sort_keys=True)
                output.write('\n')
            summary = {
                'explore_start_sim_time': self.explore_start,
                'explore_end_sim_time': self.explore_end,
                'total_exploration_time': (
                    self.explore_end - self.explore_start
                    if self.explore_start is not None and self.explore_end is not None else None
                ),
                'total_path_length_gt': self.total_distance,
                'explore_result_status': self.explore_status,
                'pose_graph_node_count': len(self.pose_nodes),
                'pose_graph_edge_count': len(self.pose_edges),
                'karto_closure_edge_count': len(self.closure_edges),
                'karto_closure_events': self.karto_closure_events,
                'loop_closed_events': self.loop_closed_events,
                'gate_events': self.gate_events,
                'repair_events': self.repair_events,
                'early_stop_events': self.early_stop_events,
                'initial_planned_high_level_path': self.initial_planned_path,
                'initial_loop_flags': self.initial_loop_flags,
                'plan_history': self.plan_history,
                'actually_visited_high_level_vertices': self.actual_visited_sequence,
                'goal_reached_sequence': self.goal_reached_sequence,
                'counts': self.counts,
                'loops_planned': len(self.loops),
                'loops_executed': sum(loop['executed_loop'] for loop in self.loops),
                'successful_slam_loops': sum(loop['successful_slam_loop'] for loop in self.loops),
                'accepted_active_loops': sum(loop.get('accepted_active_loop', False) for loop in self.loops),
                'final_map': self.map_summary,
            }
            with open(os.path.join(self.output_dir, 'observer_summary.json'), 'w') as output:
                json.dump(summary, output, indent=2, sort_keys=True)
                output.write('\n')
            self.events_file.flush()
            self.gt_file.flush()
            self.pg_updates_file.flush()
            self.events_file.close()
            self.gt_file.close()
            self.pg_updates_file.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args(rospy.myargv()[1:])
    rospy.init_node('phase2_observer', anonymous=False)
    Phase2Observer(args.output_dir)
    rospy.spin()


if __name__ == '__main__':
    main()
