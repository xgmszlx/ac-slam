#!/usr/bin/python3
"""Independent MoveTo positive control for Karto loop-closure detection.

The driver is deliberately outside the planner.  It waits for the ordinary
Nearest-Frontier exploration action to finish, freezes a before snapshot, and
then revisits a contiguous early segment of the saved Karto trajectory with
tight MoveToPosition2D tolerances.  It never changes Mapper parameters.
"""

import argparse
import json
import math
import os
import threading

import actionlib
import rospy
from nav_msgs.msg import Odometry, Path
from nav2d_navigator.msg import (
    ExploreActionResult,
    MoveToPosition2DAction,
    MoveToPosition2DGoal,
)
from rosgraph_msgs.msg import Log
from visualization_msgs.msg import Marker

from cpp_solver.msg import PoseGraph


def yaw_from_quaternion(q):
    return math.atan2(
        2.0 * (q.w * q.z + q.x * q.y),
        1.0 - 2.0 * (q.y * q.y + q.z * q.z),
    )


class PositiveControlDriver:
    def __init__(self, output_dir, first_history_index, target_count, target_stride,
                 target_timeout=420.0):
        self.output_dir = os.path.abspath(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)
        self.first_history_index = first_history_index
        self.target_count = target_count
        self.target_stride = target_stride
        self.target_timeout = float(target_timeout)
        self.lock = threading.RLock()

        self.pose_nodes = {}
        self.pose_edges = {}
        self.slam_path = []
        self.closure_marker_edges = []
        self.karto_events = []
        self.matcher_debug = []
        self.current_gt = None
        self.revisit_gt = []
        self.revisit_active = False
        self.explore_result = None
        self.done = threading.Event()
        self.result = {
            'status': 'WAITING_FOR_EXPLORATION',
            'positive_control_definition': (
                'accepted Karto loop log during the revisit window and at least one '
                'new pose-graph edge linking the new scan to historical trajectory'
            ),
            'move_tolerance_m': 0.25,
            'heading_tolerance_rad': 0.1,
            'targets': [],
        }

        rospy.Subscriber('/slam_pose_graph', PoseGraph, self.on_pose_graph, queue_size=100)
        rospy.Subscriber('/slam_path', Path, self.on_slam_path, queue_size=20)
        rospy.Subscriber('/Mapper/closure_edges', Marker, self.on_marker, queue_size=20)
        rospy.Subscriber('/rosout', Log, self.on_rosout, queue_size=2000)
        rospy.Subscriber('/base_pose_ground_truth', Odometry, self.on_gt, queue_size=200)
        rospy.Subscriber('/Explore/result', ExploreActionResult, self.on_explore_result, queue_size=5)

    def graph_snapshot(self, phase):
        return {
            'phase': phase,
            'sim_time': rospy.get_time(),
            'pose_graph_node_count': len(self.pose_nodes),
            'pose_graph_edge_count': len(self.pose_edges),
            'incremental_pose_graph_node_count': len(self.pose_nodes),
            'incremental_pose_graph_edge_count': len(self.pose_edges),
            'pose_graph_nodes': self.pose_nodes,
            'pose_graph_edges': list(self.pose_edges.values()),
            'closure_marker_edge_count': len(self.closure_marker_edges),
            'closure_marker_edges': self.closure_marker_edges,
            'trajectory_estimate': self.slam_path,
            'slam_path_node_count': len(self.slam_path),
        }

    def write_snapshot(self, phase):
        data = self.graph_snapshot(phase)
        path = os.path.join(self.output_dir, 'pose_graph_{}.json'.format(phase))
        with open(path, 'w') as output:
            json.dump(data, output, indent=2, sort_keys=True)
            output.write('\n')
        return data

    def on_pose_graph(self, msg):
        with self.lock:
            for index, node_id in enumerate(msg.vertices):
                self.pose_nodes[str(int(node_id))] = {
                    'id': int(node_id),
                    'x': float(msg.vertex_x[index]),
                    'y': float(msg.vertex_y[index]),
                    'theta': float(msg.vertex_theta[index]),
                    'last_update_time': rospy.get_time(),
                }
            for index, start in enumerate(msg.edges_start):
                edge_index = int(msg.edge_start_idx + index)
                self.pose_edges[str(edge_index)] = {
                    'index': edge_index,
                    'start': int(start),
                    'end': int(msg.edges_end[index]),
                    'covariance_upper_triangle': msg.covariance[index],
                    'observed_time': rospy.get_time(),
                }

    def on_slam_path(self, msg):
        path = []
        for index, stamped in enumerate(msg.poses):
            pose = stamped.pose
            path.append({
                'index': index,
                'x': float(pose.position.x),
                'y': float(pose.position.y),
                'theta': yaw_from_quaternion(pose.orientation),
            })
        with self.lock:
            self.slam_path = path

    def on_marker(self, msg):
        edges = []
        for index in range(0, len(msg.points) - 1, 2):
            edges.append([
                [msg.points[index].x, msg.points[index].y],
                [msg.points[index + 1].x, msg.points[index + 1].y],
            ])
        with self.lock:
            self.closure_marker_edges = edges

    def on_rosout(self, msg):
        text = msg.msg.strip()
        timestamp = msg.header.stamp.to_sec() or rospy.get_time()
        with self.lock:
            if 'Add one Loop closure.' in text:
                self.karto_events.append({'timestamp': timestamp, 'message': text})
            if any(token in text for token in (
                'Coarse LC failed', 'Fine LC failed', 'COARSE RESPONSE', 'FINE RESPONSE'
            )):
                self.matcher_debug.append({'timestamp': timestamp, 'message': text})

    def on_gt(self, msg):
        p = msg.pose.pose
        sample = [
            msg.header.stamp.to_sec() or rospy.get_time(),
            float(p.position.x), float(p.position.y), yaw_from_quaternion(p.orientation),
        ]
        with self.lock:
            self.current_gt = sample
            if self.revisit_active:
                self.revisit_gt.append(sample)

    def on_explore_result(self, msg):
        with self.lock:
            if self.explore_result is not None:
                return
            self.explore_result = {
                'status': int(msg.status.status),
                'text': msg.status.text,
                'timestamp': msg.header.stamp.to_sec() or rospy.get_time(),
            }
        threading.Thread(target=self.run_revisit, daemon=True).start()

    def select_targets(self, before):
        path = before['trajectory_estimate']
        final_index = self.first_history_index + self.target_stride * (self.target_count - 1)
        if len(path) <= final_index:
            raise RuntimeError(
                'history has {} poses, but target index {} is required'.format(len(path), final_index)
            )
        indices = list(range(final_index, self.first_history_index - 1, -self.target_stride))
        return [dict(path[index], history_index=index) for index in indices]

    @staticmethod
    def new_edges(before, after):
        old_indices = {int(edge['index']) for edge in before['pose_graph_edges']}
        return [
            edge for edge in after['pose_graph_edges']
            if int(edge['index']) not in old_indices
        ]

    @staticmethod
    def trajectory_correction(before, after):
        count = min(len(before['trajectory_estimate']), len(after['trajectory_estimate']))
        shifts = []
        for index in range(count):
            left = before['trajectory_estimate'][index]
            right = after['trajectory_estimate'][index]
            shifts.append(math.hypot(right['x'] - left['x'], right['y'] - left['y']))
        return {
            'compared_historical_poses': count,
            'mean_translation_shift_m': sum(shifts) / len(shifts) if shifts else None,
            'max_translation_shift_m': max(shifts) if shifts else None,
        }

    @staticmethod
    def resolve_marker_edges(snapshot):
        trajectory = snapshot['trajectory_estimate']
        resolved = []
        if not trajectory:
            return resolved
        for edge in snapshot['closure_marker_edges']:
            endpoints = []
            for point in edge:
                node = min(
                    trajectory,
                    key=lambda pose: (pose['x'] - point[0]) ** 2 + (pose['y'] - point[1]) ** 2,
                )
                endpoints.append({
                    'node_index': int(node['index']),
                    'match_error_m': math.hypot(node['x'] - point[0], node['y'] - point[1]),
                })
            resolved.append({
                'source': endpoints[0]['node_index'],
                'target': endpoints[1]['node_index'],
                'scan_index_gap': abs(endpoints[0]['node_index'] - endpoints[1]['node_index']),
                'endpoint_match_error_max_m': max(
                    endpoints[0]['match_error_m'], endpoints[1]['match_error_m']
                ),
            })
        return resolved

    def run_revisit(self):
        try:
            if self.explore_result['status'] != 3:
                raise RuntimeError('exploration action did not succeed: {}'.format(self.explore_result))
            rospy.sleep(5.0)
            with self.lock:
                before = self.write_snapshot('before')
                targets = self.select_targets(before)
                start_event_count = len(self.karto_events)
                revisit_start = rospy.get_time()
                self.revisit_active = True
                self.result.update({
                    'status': 'REVISITING',
                    'explore_result': self.explore_result,
                    'revisit_start_time': revisit_start,
                    'before_node_count': len(before['trajectory_estimate']),
                    'before_edge_count': before['pose_graph_edge_count'],
                    'selected_history_indices': [target['history_index'] for target in targets],
                })

            client = actionlib.SimpleActionClient('/MoveTo', MoveToPosition2DAction)
            if not client.wait_for_server(rospy.Duration(60.0)):
                raise RuntimeError('MoveTo action server unavailable')

            action_rows = []
            for sequence, target in enumerate(targets, 1):
                goal = MoveToPosition2DGoal()
                goal.header.stamp = rospy.Time.now()
                goal.header.frame_id = 'map'
                goal.target_pose.x = target['x']
                goal.target_pose.y = target['y']
                goal.target_pose.theta = target['theta']
                goal.target_distance = 0.25
                goal.target_angle = 0.1
                start_time = rospy.get_time()
                client.send_goal(goal)
                finished = client.wait_for_result(rospy.Duration(self.target_timeout))
                state = int(client.get_state())
                result = client.get_result()
                row = {
                    'sequence': sequence,
                    'history_index': target['history_index'],
                    'target_x': target['x'], 'target_y': target['y'],
                    'target_theta': target['theta'],
                    'start_time': start_time, 'end_time': rospy.get_time(),
                    'action_finished': bool(finished), 'action_state': state,
                }
                if result is not None:
                    row.update({
                        'final_x': float(result.final_pose.x),
                        'final_y': float(result.final_pose.y),
                        'final_theta': float(result.final_pose.theta),
                        'final_distance': float(result.final_distance),
                    })
                action_rows.append(row)
                if not finished or state != 3:
                    raise RuntimeError('MoveTo target {} failed with state {}'.format(sequence, state))

            rospy.sleep(8.0)
            with self.lock:
                self.revisit_active = False
                after = self.write_snapshot('after')
                new_edges = self.new_edges(before, after)
                events = self.karto_events[start_event_count:]
                history_cutoff = len(before['trajectory_estimate']) - 1
                new_history_links = [
                    edge for edge in new_edges
                    if min(int(edge['start']), int(edge['end'])) <= history_cutoff
                    and max(int(edge['start']), int(edge['end'])) > history_cutoff
                ]
                new_nonlocal_history_links = [
                    edge for edge in new_history_links
                    if abs(int(edge['start']) - int(edge['end'])) > 70
                ]
                resolved_after_marker_edges = self.resolve_marker_edges(after)
                marker_nonlocal_history_links = [
                    edge for edge in resolved_after_marker_edges
                    if min(edge['source'], edge['target']) <= history_cutoff
                    and max(edge['source'], edge['target']) > history_cutoff
                    and edge['scan_index_gap'] > 70
                    and edge['endpoint_match_error_max_m'] < 0.05
                ]
                self.result.update({
                    'status': 'SUCCEEDED',
                    'revisit_end_time': rospy.get_time(),
                    'targets': action_rows,
                    'actual_revisit_trajectory': self.revisit_gt,
                    'after_node_count': len(after['trajectory_estimate']),
                    'after_edge_count': after['pose_graph_edge_count'],
                    'new_pose_graph_edges': new_edges,
                    'new_history_link_edges': new_history_links,
                    'new_nonlocal_history_link_edges': new_nonlocal_history_links,
                    'resolved_after_closure_marker_edges': resolved_after_marker_edges,
                    'marker_nonlocal_history_link_edges': marker_nonlocal_history_links,
                    'karto_accepted_loop_events_during_revisit': events,
                    'closure_marker_edge_delta': (
                        after['closure_marker_edge_count'] - before['closure_marker_edge_count']
                    ),
                    'trajectory_correction': self.trajectory_correction(before, after),
                    'matcher_debug_during_run': self.matcher_debug,
                    'incremental_pose_graph_topic_stale_after_exploration': (
                        len(after['trajectory_estimate']) > after['pose_graph_node_count']
                    ),
                    'positive_control_success': bool(events and marker_nonlocal_history_links),
                })
        except Exception as exc:
            with self.lock:
                self.revisit_active = False
                self.result.update({
                    'status': 'FAILED',
                    'reason': '{}: {}'.format(type(exc).__name__, exc),
                    'karto_events_seen': self.karto_events,
                    'matcher_debug_seen': self.matcher_debug,
                    'actual_revisit_trajectory': self.revisit_gt,
                })
        finally:
            with open(os.path.join(self.output_dir, 'positive_control.json'), 'w') as output:
                json.dump(self.result, output, indent=2, sort_keys=True)
                output.write('\n')
            self.done.set()
            rospy.signal_shutdown('positive-control driver finished')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--first-history-index', type=int, default=30)
    parser.add_argument('--target-count', type=int, default=7)
    parser.add_argument('--target-stride', type=int, default=5)
    parser.add_argument('--target-timeout', type=float, default=420.0)
    args = parser.parse_args(rospy.myargv()[1:])
    rospy.init_node('phase2b_positive_control_driver', anonymous=False)
    driver = PositiveControlDriver(
        args.output_dir, args.first_history_index, args.target_count, args.target_stride,
        target_timeout=args.target_timeout,
    )
    rospy.spin()
    if not driver.done.is_set():
        raise SystemExit('ROS shutdown before positive control completed')


if __name__ == '__main__':
    main()
