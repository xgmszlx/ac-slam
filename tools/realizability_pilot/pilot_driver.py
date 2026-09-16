#!/usr/bin/python3
"""Build one fixed history and execute one controlled revisit action."""

import argparse
import json
import math
import os
import threading
import time

import actionlib
import rospy
import tf
from nav_msgs.msg import Odometry, Path
from nav_msgs.srv import GetMap
from nav2d_msgs.msg import RobotPose
from nav2d_navigator.msg import MoveToPosition2DAction, MoveToPosition2DGoal
from visualization_msgs.msg import Marker

from cpp_solver.msg import LoopClosureEvent, PoseGraph

from protocol import (goal_errors, resolve_local_waypoints, resolve_marker_edges,
                      target_freeze_checks)


def wrap_angle(value):
    return math.atan2(math.sin(value), math.cos(value))


def yaw_from_quaternion(q):
    return math.atan2(
        2.0 * (q.w * q.z + q.x * q.y),
        1.0 - 2.0 * (q.y * q.y + q.z * q.z),
    )


def path_length(samples):
    return sum(
        math.hypot(right[1] - left[1], right[2] - left[2])
        for left, right in zip(samples, samples[1:])
    )


class PilotDriver:
    def __init__(self, spec, output_dir):
        self.spec = spec
        self.output_dir = os.path.abspath(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)
        self.lock = threading.RLock()
        self.pose_nodes = {}
        self.pose_edges = {}
        self.full_pose_nodes = {}
        self.full_pose_edges = {}
        self.full_pose_graph_received_time = None
        self.full_pose_graph_message_count = 0
        self.slam_path = []
        self.slam_path_received_time = None
        self.slam_path_message_count = 0
        self.mapper_keyscan_pose = None
        self.gt_pose = None
        self.probe_gt = []
        self.probe_active = False
        self.loop_events = []
        self.closure_marker_edges = []
        self.moves = []
        self.tf_listener = tf.TransformListener()

        rospy.Subscriber('/slam_pose_graph', PoseGraph, self.on_pose_graph, queue_size=100)
        rospy.Subscriber('/slam_pose_graph_full', PoseGraph,
                         self.on_full_pose_graph, queue_size=20)
        rospy.Subscriber('/slam_path', Path, self.on_slam_path, queue_size=20)
        rospy.Subscriber('/base_pose_ground_truth', Odometry, self.on_gt, queue_size=200)
        rospy.Subscriber('/others', RobotPose, self.on_mapper_keyscan_pose, queue_size=100)
        rospy.Subscriber('/Mapper/loop_closed', LoopClosureEvent,
                         self.on_loop_closed, queue_size=20)
        rospy.Subscriber('/Mapper/closure_edges', Marker,
                         self.on_closure_edges, queue_size=20)

    def on_pose_graph(self, msg):
        with self.lock:
            for index, node_id in enumerate(msg.vertices):
                self.pose_nodes[int(node_id)] = {
                    'id': int(node_id),
                    'x': float(msg.vertex_x[index]),
                    'y': float(msg.vertex_y[index]),
                    'theta': float(msg.vertex_theta[index]),
                    'observed_time': float(rospy.get_time()),
                }
            for index, start in enumerate(msg.edges_start):
                edge_index = int(msg.edge_start_idx + index)
                self.pose_edges[edge_index] = {
                    'index': edge_index,
                    'start': int(start),
                    'end': int(msg.edges_end[index]),
                }

    def on_full_pose_graph(self, msg):
        nodes = {}
        edges = {}
        for index, node_id in enumerate(msg.vertices):
            nodes[int(node_id)] = {
                'id': int(node_id),
                'unique_id': int(msg.vertex_unique_ids[index]),
                'x': float(msg.vertex_x[index]),
                'y': float(msg.vertex_y[index]),
                'theta': float(msg.vertex_theta[index]),
            }
        for index, start in enumerate(msg.edges_start):
            edge_index = int(msg.edge_start_idx + index)
            edges[edge_index] = {
                'index': edge_index,
                'start': int(start),
                'end': int(msg.edges_end[index]),
                'covariance_upper_triangle': msg.covariance[index],
            }
        with self.lock:
            self.full_pose_nodes = nodes
            self.full_pose_edges = edges
            self.full_pose_graph_received_time = float(rospy.get_time())
            self.full_pose_graph_message_count += 1

    def on_slam_path(self, msg):
        path = []
        for index, stamped in enumerate(msg.poses):
            pose = stamped.pose
            path.append({
                'id': index,
                'x': float(pose.position.x),
                'y': float(pose.position.y),
                'theta': yaw_from_quaternion(pose.orientation),
            })
        with self.lock:
            self.slam_path = path
            self.slam_path_received_time = float(rospy.get_time())
            self.slam_path_message_count += 1

    def on_mapper_keyscan_pose(self, msg):
        sample = {
            'stamp': float(msg.header.stamp.to_sec()),
            'received_ros_time': float(rospy.get_time()),
            'robot_id': int(msg.robot_id),
            'x': float(msg.pose.x),
            'y': float(msg.pose.y),
            'theta': float(msg.pose.theta),
        }
        with self.lock:
            self.mapper_keyscan_pose = sample

    def on_gt(self, msg):
        pose = msg.pose.pose
        sample = [
            float(msg.header.stamp.to_sec() or rospy.get_time()),
            float(pose.position.x), float(pose.position.y),
            yaw_from_quaternion(pose.orientation),
        ]
        with self.lock:
            self.gt_pose = sample
            if self.probe_active:
                self.probe_gt.append(sample)

    def on_loop_closed(self, msg):
        event = {
            'seq': int(msg.seq),
            'loop_count': int(msg.loop_count),
            'current_scan': int(msg.current_scan),
            'chain_start': int(msg.chain_start),
            'chain_end': int(msg.chain_end),
            'historical_scan': int(msg.historical_scan),
            'measurement_dx': float(msg.measurement_dx),
            'measurement_dy': float(msg.measurement_dy),
            'measurement_dyaw': float(msg.measurement_dyaw),
            'covariance_xx': float(msg.covariance_xx),
            'covariance_xy': float(msg.covariance_xy),
            'covariance_xt': float(msg.covariance_xt),
            'covariance_yy': float(msg.covariance_yy),
            'covariance_yt': float(msg.covariance_yt),
            'covariance_tt': float(msg.covariance_tt),
            'stamp': float(msg.stamp.to_sec()),
        }
        with self.lock:
            self.loop_events.append(event)

    def on_closure_edges(self, msg):
        edges = []
        for index in range(0, len(msg.points) - 1, 2):
            edges.append([
                [float(msg.points[index].x), float(msg.points[index].y)],
                [float(msg.points[index + 1].x), float(msg.points[index + 1].y)],
            ])
        with self.lock:
            self.closure_marker_edges = edges

    def snapshot(self, phase):
        with self.lock:
            received_time = self.slam_path_received_time
            full_path_nodes = []
            for original in self.slam_path:
                node = dict(original)
                node['observed_time'] = received_time
                full_path_nodes.append(node)
            return {
                'phase': phase,
                'sim_time': float(rospy.get_time()),
                # /slam_path is rebuilt from the full, ordered Karto vertex
                # list on every map publication. Its list index is the graph
                # state ID (see MultiMapper::sendMap). /slam_pose_graph is an
                # incremental stream controlled by a shared publication cursor
                # and is therefore retained as telemetry, not used as the
                # canonical historical node set.
                'nodes': full_path_nodes,
                'node_source': '/slam_path full corrected Karto vertex sequence',
                'slam_path_received_time': received_time,
                'slam_path_age_s': (
                    None if received_time is None
                    else float(rospy.get_time()) - received_time),
                'incremental_pose_nodes': [
                    self.pose_nodes[key] for key in sorted(self.pose_nodes)],
                'edges': [self.pose_edges[key] for key in sorted(self.pose_edges)],
                'full_pose_nodes': [
                    self.full_pose_nodes[key] for key in sorted(self.full_pose_nodes)],
                'full_pose_edges': [
                    self.full_pose_edges[key] for key in sorted(self.full_pose_edges)],
                'full_pose_graph_received_time': self.full_pose_graph_received_time,
                'full_pose_graph_message_count': self.full_pose_graph_message_count,
                'full_pose_graph_age_s': (
                    None if self.full_pose_graph_received_time is None
                    else float(rospy.get_time()) - self.full_pose_graph_received_time),
                'closure_marker_edges': list(self.closure_marker_edges),
                'slam_path': full_path_nodes,
                'loop_events': list(self.loop_events),
            }

    def refresh_graph_observers(self):
        """Request one atomic mapper publication and wait for both observers."""
        service_name = '/get_map'
        rospy.wait_for_service(service_name, timeout=30.0)
        with self.lock:
            previous_path_count = self.slam_path_message_count
            previous_graph_count = self.full_pose_graph_message_count
        service = rospy.ServiceProxy(service_name, GetMap)
        service()
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and not rospy.is_shutdown():
            with self.lock:
                path_updated = self.slam_path_message_count > previous_path_count
                graph_updated = self.full_pose_graph_message_count > previous_graph_count
            if path_updated and graph_updated:
                return
            rospy.sleep(0.05)
        raise RuntimeError('forced mapper observer refresh did not arrive within 15 s')

    def write_json(self, name, payload):
        path = os.path.join(self.output_dir, name)
        with open(path, 'w') as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write('\n')

    def wait_ready(self):
        deadline = time.monotonic() + 90.0
        while time.monotonic() < deadline and not rospy.is_shutdown():
            with self.lock:
                topics_ready = (self.gt_pose is not None and self.slam_path
                                and self.mapper_keyscan_pose is not None
                                and self.full_pose_nodes)
            if topics_ready and self.current_tf_pose() is not None:
                return
            rospy.sleep(0.25)
        raise RuntimeError(
            'no GT, Karto keyscan, slam_path, full pose graph, and '
            'map->base_link TF within 90 s')

    @staticmethod
    def wait_for_start_gate(parameter_name):
        if not parameter_name:
            return
        while not rospy.is_shutdown():
            if bool(rospy.get_param(parameter_name, False)):
                return
            rospy.sleep(0.1)
        raise RuntimeError('ROS shutdown before pilot start gate opened')

    def current_slam_pose(self):
        with self.lock:
            if not self.slam_path:
                return None
            pose = self.slam_path[-1]
            return [float(pose['x']), float(pose['y']), float(pose['theta'])]

    def current_tf_pose(self):
        try:
            translation, rotation = self.tf_listener.lookupTransform(
                'map', 'base_link', rospy.Time(0))
        except (tf.LookupException, tf.ConnectivityException, tf.ExtrapolationException):
            return None
        return [float(translation[0]), float(translation[1]),
                float(tf.transformations.euler_from_quaternion(rotation)[2])]

    def current_gt_pose(self):
        with self.lock:
            if self.gt_pose is None:
                return None
            return [float(self.gt_pose[1]), float(self.gt_pose[2]),
                    float(self.gt_pose[3])]

    def current_keyscan_pose(self):
        with self.lock:
            if self.mapper_keyscan_pose is None:
                return None
            return dict(self.mapper_keyscan_pose)

    def move_to(self, client, x, y, theta, label, expected_gt_pose):
        goal = MoveToPosition2DGoal()
        goal.header.stamp = rospy.Time.now()
        goal.header.frame_id = 'map'
        goal.target_pose.x = float(x)
        goal.target_pose.y = float(y)
        goal.target_pose.theta = wrap_angle(float(theta))
        goal.target_distance = 0.25
        goal.target_angle = 0.1
        start = float(rospy.get_time())
        start_tf_pose = self.current_tf_pose()
        start_gt_pose = self.current_gt_pose()
        start_path_pose = self.current_slam_pose()
        client.send_goal(goal)
        finished = client.wait_for_result(rospy.Duration(float(self.spec['move_timeout_s'])))
        state = int(client.get_state())
        result = client.get_result()
        if not finished:
            client.cancel_goal()
        rospy.sleep(float(self.spec['goal_settle_s']))
        observed_tf_pose = self.current_tf_pose()
        observed_gt_pose = self.current_gt_pose()
        observed_path_pose = self.current_slam_pose()
        observed_keyscan_pose = self.current_keyscan_pose()
        if observed_tf_pose is None or observed_gt_pose is None:
            raise RuntimeError('no live TF/GT pose after MoveTo {}'.format(label))
        tf_position_error, tf_heading_error = goal_errors(
            observed_tf_pose, [x, y, theta])
        gt_position_error, gt_heading_error = goal_errors(
            observed_gt_pose, expected_gt_pose)
        if observed_path_pose is not None:
            path_position_error, path_heading_error = goal_errors(
                observed_path_pose, [x, y, theta])
        else:
            path_position_error = path_heading_error = None
        if observed_keyscan_pose is not None:
            keyscan_position_error, keyscan_heading_error = goal_errors(
                [observed_keyscan_pose['x'], observed_keyscan_pose['y'],
                 observed_keyscan_pose['theta']], [x, y, theta])
            keyscan_age = float(rospy.get_time()) - observed_keyscan_pose['received_ros_time']
        else:
            keyscan_position_error = keyscan_heading_error = keyscan_age = None
        row = {
            'label': label,
            'target_x': float(x), 'target_y': float(y),
            'target_theta': wrap_angle(float(theta)),
            'start_time': start, 'end_time': float(rospy.get_time()),
            'action_finished': bool(finished), 'action_state': state,
            'expected_gt_pose': list(expected_gt_pose),
            'tf_pose_before': start_tf_pose,
            'tf_pose_after': observed_tf_pose,
            'gt_pose_before': start_gt_pose,
            'gt_pose_after': observed_gt_pose,
            'slam_path_pose_before': start_path_pose,
            'slam_path_pose_after': observed_path_pose,
            'mapper_keyscan_pose_after': observed_keyscan_pose,
            'slam_path_node_count_after': len(self.slam_path),
            'tf_position_error_m': tf_position_error,
            'tf_heading_error_rad': tf_heading_error,
            'gt_position_error_m': gt_position_error,
            'gt_heading_error_rad': gt_heading_error,
            'slam_path_position_error_m': path_position_error,
            'slam_path_heading_error_rad': path_heading_error,
            'keyscan_position_error_m': keyscan_position_error,
            'keyscan_heading_error_rad': keyscan_heading_error,
            'keyscan_age_s': keyscan_age,
            'position_tolerance_m': float(self.spec['goal_position_tolerance_m']),
            'heading_tolerance_rad': float(self.spec['goal_heading_tolerance_rad']),
            'gt_position_tolerance_m': float(self.spec['gt_position_tolerance_m']),
            'gt_heading_tolerance_rad': float(self.spec['gt_heading_tolerance_rad']),
        }
        if result is not None:
            row.update({
                'final_x': float(result.final_pose.x),
                'final_y': float(result.final_pose.y),
                'final_theta': float(result.final_pose.theta),
                'final_distance': float(result.final_distance),
            })
        self.moves.append(row)
        tf_reached = (
            tf_position_error <= float(self.spec['goal_position_tolerance_m'])
            and tf_heading_error <= float(self.spec['goal_heading_tolerance_rad']))
        gt_reached = (
            gt_position_error <= float(self.spec['gt_position_tolerance_m'])
            and gt_heading_error <= float(self.spec['gt_heading_tolerance_rad']))
        reached = bool(finished) and state == 3 and tf_reached and gt_reached
        row['tf_reached'] = tf_reached
        row['gt_reached'] = gt_reached
        row['independently_reached'] = reached
        rospy.logwarn(
            'PILOT_MOVE %s state=%d finished=%s tf_error=%.3f/%.3f '
            'gt_error=%.3f/%.3f path_error=%s reached=%s',
            label, state, finished, tf_position_error, tf_heading_error,
            gt_position_error, gt_heading_error,
            'none' if path_position_error is None else '{:.3f}'.format(path_position_error),
            reached)
        if not finished or state != 3:
            raise RuntimeError('MoveTo {} failed with state {}'.format(label, state))
        if not reached:
            raise RuntimeError(
                'MoveTo {} reported success but independent pose error is '
                'TF {:.3f} m/{:.3f} rad and GT {:.3f} m/{:.3f} rad'.format(
                    label, tf_position_error, tf_heading_error,
                    gt_position_error, gt_heading_error))
        return row

    @staticmethod
    def target_segment(nodes, reference, radius):
        if not nodes:
            raise RuntimeError('pose graph is empty at target freeze')
        anchor = min(nodes, key=lambda node: math.hypot(
            node['x'] - reference[0], node['y'] - reference[1]))
        ordered = sorted(nodes, key=lambda node: node['id'])
        anchor_pos = next(i for i, node in enumerate(ordered) if node['id'] == anchor['id'])

        def inside(node):
            return math.hypot(node['x'] - anchor['x'], node['y'] - anchor['y']) <= radius

        left = anchor_pos
        while left > 0 and ordered[left - 1]['id'] + 1 == ordered[left]['id'] \
                and inside(ordered[left - 1]):
            left -= 1
        right = anchor_pos
        while right + 1 < len(ordered) and ordered[right]['id'] + 1 == ordered[right + 1]['id'] \
                and inside(ordered[right + 1]):
            right += 1
        segment = ordered[left:right + 1]
        return anchor, segment

    def probe_goals(self, anchor, historical_gt_pose):
        heading = float(anchor['theta'])
        offset = float(self.spec['lateral_offset_m'])
        x = float(anchor['x']) - math.sin(heading) * offset
        y = float(anchor['y']) + math.cos(heading) * offset
        arrival = wrap_angle(heading + math.radians(float(self.spec['delta_yaw_deg'])))
        gt_heading = float(historical_gt_pose[2])
        gt_x = float(historical_gt_pose[0]) - math.sin(gt_heading) * offset
        gt_y = float(historical_gt_pose[1]) + math.cos(gt_heading) * offset
        gt_arrival = wrap_angle(
            gt_heading + math.radians(float(self.spec['delta_yaw_deg'])))
        goals = [(x, y, arrival, 'probe_arrival', [gt_x, gt_y, gt_arrival])]
        maneuver = self.spec['maneuver_type']
        if maneuver == 'align':
            goals.append((x, y, heading, 'historical_heading_alignment',
                          [gt_x, gt_y, gt_heading]))
        elif maneuver == 'sweep':
            for degrees in (-30.0, 0.0, 30.0):
                goals.append((x, y, wrap_angle(heading + math.radians(degrees)),
                              'sweep_{:+.0f}deg'.format(degrees),
                              [gt_x, gt_y, wrap_angle(
                                  gt_heading + math.radians(degrees))]))
        elif maneuver != 'pass':
            raise RuntimeError('unknown maneuver {}'.format(maneuver))
        return goals

    def run(self):
        self.wait_ready()
        client = actionlib.SimpleActionClient('/MoveTo', MoveToPosition2DAction)
        if not client.wait_for_server(rospy.Duration(60.0)):
            raise RuntimeError('/MoveTo action server unavailable')

        live_tf_origin = self.current_tf_pose()
        live_gt_origin = self.current_gt_pose()
        with self.lock:
            first_karto_pose = dict(self.slam_path[0]) if self.slam_path else None
        if live_tf_origin is None or live_gt_origin is None or first_karto_pose is None:
            raise RuntimeError('no live TF/GT/first-Karto pose for route origin')
        axis_heading = float(self.spec['route_axis_heading_rad'])
        episode_origin = [first_karto_pose['x'], first_karto_pose['y'], axis_heading]
        episode_gt_origin = [float(self.spec['start_pose'][0]),
                             float(self.spec['start_pose'][1]), axis_heading]
        history_waypoints = resolve_local_waypoints(
            episode_origin, self.spec['history_offsets'])
        history_gt_waypoints = resolve_local_waypoints(
            episode_gt_origin, self.spec['history_offsets'])
        target_reference = history_waypoints[
            int(self.spec['target_history_waypoint_index'])]
        with self.lock:
            route_start_node_count = len(self.slam_path)
        self.write_json('resolved_history_route.json', {
            'history_frame': self.spec['history_frame'],
            'history_origin_source': self.spec['history_origin_source'],
            'route_axis_heading_rad': axis_heading,
            'episode_mapper_origin': episode_origin,
            'episode_gt_origin': episode_gt_origin,
            'live_tf_pose_at_route_start': live_tf_origin,
            'live_gt_pose_at_route_start': live_gt_origin,
            'history_offsets': self.spec['history_offsets'],
            'resolved_history_waypoints': history_waypoints,
            'resolved_history_gt_waypoints': history_gt_waypoints,
            'target_reference': target_reference,
            'route_start_node_count': route_start_node_count,
        })

        history_moves = []
        for index, (waypoint, gt_waypoint) in enumerate(
                zip(history_waypoints, history_gt_waypoints), 1):
            history_moves.append(self.move_to(
                client, waypoint[0], waypoint[1], waypoint[2],
                'history_{:02d}'.format(index), gt_waypoint))
        rospy.sleep(float(self.spec['history_hold_s']))

        self.refresh_graph_observers()
        before = self.snapshot('before_probe')
        self.write_json('pose_graph_before.json', before)
        if len(before['full_pose_nodes']) != len(before['nodes']):
            raise RuntimeError(
                'full pose graph/path node-count mismatch before probe: {} vs {}'.format(
                    len(before['full_pose_nodes']), len(before['nodes'])))
        history_event_count = len(before['loop_events'])
        anchor, segment = self.target_segment(
            before['nodes'], target_reference,
            float(self.spec['target_segment_radius_m']))
        anchor_distance = math.hypot(
            float(anchor['x']) - float(target_reference[0]),
            float(anchor['y']) - float(target_reference[1]))
        freeze_checks = target_freeze_checks(
            len(before['nodes']), anchor['id'], anchor_distance,
            len(segment), route_start_node_count, self.spec)
        full_unique_by_state = {
            node['id']: node['unique_id'] for node in before['full_pose_nodes']
        }
        frozen_target = {
            'target_id': self.spec['target_id'],
            'frozen_before_probe': True,
            'target_reference': target_reference,
            'anchor_scan': anchor,
            'historical_scan_ids': [node['id'] for node in segment],
            'historical_unique_ids': [
                full_unique_by_state[node['id']] for node in segment],
            'segment_nodes': [dict(
                node,
                unique_id=full_unique_by_state[node['id']])
                for node in segment],
            'target_segment_radius_m': float(self.spec['target_segment_radius_m']),
            'anchor_to_reference_distance_m': anchor_distance,
            'route_start_node_count': route_start_node_count,
            'target_identity_gate': freeze_checks,
        }
        self.write_json('frozen_target.json', frozen_target)
        if not freeze_checks['passed']:
            failed = sorted(name for name, passed in freeze_checks['checks'].items()
                            if not passed)
            raise RuntimeError(
                'target identity gate failed before probe: {}'.format(', '.join(failed)))

        with self.lock:
            self.probe_gt = []
            self.probe_active = True
        rospy.set_param('/constraint_realizability_pilot/probe_phase', 'DURING_PROBE')
        probe_start = float(rospy.get_time())
        probe_event_index = len(self.loop_events)
        action_completed = False
        historical_gt_pose = history_moves[
            int(self.spec['target_history_waypoint_index'])]['gt_pose_after']
        try:
            for x, y, theta, label, expected_gt in self.probe_goals(
                    anchor, historical_gt_pose):
                self.move_to(client, x, y, theta, label, expected_gt)
            action_completed = True
            rospy.sleep(float(self.spec['probe_hold_s']))
        finally:
            with self.lock:
                self.probe_active = False
            rospy.set_param('/constraint_realizability_pilot/probe_phase', 'AFTER_PROBE')
        probe_end = float(rospy.get_time())

        self.refresh_graph_observers()
        after = self.snapshot('after_probe')
        self.write_json('pose_graph_after.json', after)
        if len(after['full_pose_nodes']) != len(after['nodes']):
            raise RuntimeError(
                'full pose graph/path node-count mismatch after probe: {} vs {}'.format(
                    len(after['full_pose_nodes']), len(after['nodes'])))
        target_ids = set(frozen_target['historical_scan_ids'])
        events = self.loop_events[probe_event_index:]
        before_edge_ids = {edge['index'] for edge in before['edges']}
        new_edges = [edge for edge in after['edges'] if edge['index'] not in before_edge_ids]
        attributed_events = []
        for original_event in events:
            event = dict(original_event)
            matching_edges = [edge for edge in new_edges
                              if edge['start'] == event['historical_scan']
                              and edge['end'] == event['current_scan']]
            event['new_pose_graph_edge_confirmed'] = bool(matching_edges)
            event['pose_graph_edge_index'] = (
                matching_edges[0]['index'] if matching_edges else None)
            attributed_events.append(event)
        target_match_events = [event for event in attributed_events
                               if event['historical_scan'] in target_ids]
        wrong_match_events = [event for event in attributed_events
                              if event['historical_scan'] not in target_ids]
        target_events = [event for event in target_match_events
                         if event['new_pose_graph_edge_confirmed']]
        wrong_events = [event for event in wrong_match_events
                        if event['new_pose_graph_edge_confirmed']]
        before_max = max((node['id'] for node in before['nodes']), default=-1)
        new_nodes = [node for node in after['nodes'] if node['id'] > before_max]
        near_nodes = [node for node in new_nodes if math.hypot(
            node['x'] - anchor['x'], node['y'] - anchor['y'])
            <= float(self.spec['target_reached_radius_m'])]
        marker_error_limit = float(self.spec['marker_endpoint_max_error_m'])
        before_marker_edges = resolve_marker_edges(
            before.get('closure_marker_edges', []), before['nodes'])
        after_marker_edges = resolve_marker_edges(
            after.get('closure_marker_edges', []), after['nodes'])
        before_marker_pairs = {
            tuple(sorted((edge['source'], edge['target'])))
            for edge in before_marker_edges
            if edge['endpoint_match_error_max_m'] <= marker_error_limit
        }
        new_marker_edges = [
            edge for edge in after_marker_edges
            if edge['endpoint_match_error_max_m'] <= marker_error_limit
            and tuple(sorted((edge['source'], edge['target'])))
            not in before_marker_pairs
        ]
        target_marker_edges = [
            edge for edge in new_marker_edges
            if ((edge['source'] in target_ids and edge['target'] > before_max)
                or (edge['target'] in target_ids and edge['source'] > before_max))
        ]
        before_full_pairs = {
            tuple(sorted((edge['start'], edge['end'])))
            for edge in before['full_pose_edges']
        }
        new_full_edges = [
            edge for edge in after['full_pose_edges']
            if tuple(sorted((edge['start'], edge['end']))) not in before_full_pairs
        ]
        target_full_edges = [
            edge for edge in new_full_edges
            if ((edge['start'] in target_ids and edge['end'] > before_max)
                or (edge['end'] in target_ids and edge['start'] > before_max))
        ]
        target_event_pairs = {
            tuple(sorted((event['historical_scan'], event['current_scan'])))
            for event in target_match_events
        }
        explicit_target_full_edges = [
            edge for edge in target_full_edges
            if tuple(sorted((edge['start'], edge['end']))) in target_event_pairs
        ]
        nonexplicit_target_full_edges = [
            edge for edge in target_full_edges
            if tuple(sorted((edge['start'], edge['end']))) not in target_event_pairs
        ]
        result = {
            'status': 'SUCCEEDED',
            'episode_id': self.spec['episode_id'],
            'spec': self.spec,
            'history_contaminated_by_closure': history_event_count > 0,
            'history_loop_events': self.loop_events[:probe_event_index],
            'frozen_target': frozen_target,
            'before_max_scan_id': before_max,
            'after_max_scan_id': max((node['id'] for node in after['nodes']), default=-1),
            'probe_start_time': probe_start,
            'probe_end_time': probe_end,
            'action_completed': action_completed,
            'new_keyscan_ids': [node['id'] for node in new_nodes],
            'near_target_keyscan_ids': [node['id'] for node in near_nodes],
            'near_target_keyscan_generated': bool(near_nodes),
            'loop_events_during_probe': attributed_events,
            'matcher_accepted_target': bool(target_match_events),
            'matcher_accepted_wrong_target': bool(wrong_match_events),
            'backend_event_without_new_edge': any(
                not event['new_pose_graph_edge_confirmed']
                for event in attributed_events),
            'target_constraint': bool(target_events),
            # Keep explicit loop acceptance separate from other Karto graph
            # measurements. The marker also contains ordinary near-chain links.
            'target_backend_measurement': bool(target_full_edges),
            'target_explicit_loop_constraint_full_graph': bool(
                explicit_target_full_edges),
            'target_nonexplicit_full_graph_constraint': bool(
                nonexplicit_target_full_edges),
            'new_full_pose_graph_edges': new_full_edges,
            'target_full_pose_graph_constraints': target_full_edges,
            'target_explicit_full_graph_constraints': explicit_target_full_edges,
            'target_nonexplicit_full_graph_constraints': nonexplicit_target_full_edges,
            'target_nonexplicit_marker_constraint': bool(target_marker_edges),
            'marker_endpoint_max_error_m': marker_error_limit,
            'resolved_marker_edges_before': before_marker_edges,
            'resolved_marker_edges_after': after_marker_edges,
            'new_resolved_marker_edges': new_marker_edges,
            'target_marker_constraints': target_marker_edges,
            'wrong_target_constraint': bool(wrong_events),
            'target_match_events': target_match_events,
            'wrong_target_match_events': wrong_match_events,
            'target_constraint_events': target_events,
            'wrong_target_constraint_events': wrong_events,
            'false_constraint': None,
            'false_constraint_status': 'UNKNOWN_NOT_AUTOMATICALLY_LABELLED',
            'actual_probe_trajectory_gt': self.probe_gt,
            'actual_probe_distance_m': path_length(self.probe_gt),
            'moves': self.moves,
        }
        if history_event_count > 0:
            result['analysis_eligible'] = False
            result['exclusion_reason'] = 'closure occurred before frozen probe action'
        else:
            result['analysis_eligible'] = True
            result['exclusion_reason'] = None
        self.write_json('episode_result.json', result)
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--spec', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--start-gate-param')
    args = parser.parse_args(rospy.myargv()[1:])
    spec = json.loads(open(args.spec).read())
    rospy.init_node('constraint_realizability_pilot_driver', anonymous=False)
    rospy.set_param('/constraint_realizability_pilot/probe_phase', 'BEFORE_PROBE')
    driver = PilotDriver(spec, args.output_dir)
    if args.start_gate_param:
        rospy.set_param(args.start_gate_param + '_subscriber_ready', True)
    driver.wait_for_start_gate(args.start_gate_param)
    try:
        result = driver.run()
        print(json.dumps({
            'status': result['status'],
            'analysis_eligible': result['analysis_eligible'],
            'target_constraint': result['target_constraint'],
            'wrong_target_constraint': result['wrong_target_constraint'],
        }, sort_keys=True))
    except Exception as exc:
        payload = {
            'status': 'FAILED',
            'episode_id': spec.get('episode_id'),
            'reason': '{}: {}'.format(type(exc).__name__, exc),
            'moves': driver.moves,
        }
        driver.write_json('episode_result.json', payload)
        raise
    finally:
        rospy.signal_shutdown('controlled pilot episode finished')


if __name__ == '__main__':
    main()
