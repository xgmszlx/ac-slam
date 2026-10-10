#!/usr/bin/python3
"""Continuous-chain driver for the revisited-action experiment.

One process, one Stage/Karto run, no stitching and no suffix transformation:

    initial mapping (runner) -> history route (passes place once)
    -> G_before_return -> return leg -> G_arrival
    -> action phase (first ACTION_FRAMES valid scans)
    -> G_action_done -> static tail -> G_final

The driver only observes.  It never writes to the mapper's inputs, never
changes matcher thresholds and never feeds a graph back into navigation.

Recorded native stream: every ``/scan`` message with its wire-precision ranges
plus the odometric pose resolved from TF at that scan's stamp (and the age of
the pose actually used), so the offline analysis can re-derive the trajectory
without relying on any SLAM output.
"""

import argparse
import json
import math
import os
import sys
import threading
import time
from pathlib import Path

import actionlib
import rospy
import tf
from nav_msgs.msg import Odometry, Path as RosPath
from nav2d_msgs.msg import RobotPose
from nav2d_navigator.msg import MoveToPosition2DAction, MoveToPosition2DGoal
from sensor_msgs.msg import LaserScan
from cpp_solver.msg import LoopClosureEvent, PoseGraph
from visualization_msgs.msg import Marker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol import (  # noqa: E402  (frozen helpers shared with the pilot)
    goal_errors,
    resolve_local_waypoints,
)
from continuous_revisit import protocol as cr  # noqa: E402


def wrap_angle(value):
    return math.atan2(math.sin(float(value)), math.cos(float(value)))


def gt_xy_yaw(sample):
    """[x, y, yaw] of a ground-truth sample stored as [stamp, x, y, yaw]."""
    if sample is None:
        return sample
    if len(sample) == 4:
        return [float(sample[1]), float(sample[2]), float(sample[3])]
    return [float(value) for value in sample]


def parse_covariance(text):
    """Six upper-triangle terms of PoseGraph.covariance (a float32 string)."""
    try:
        values = [float(value) for value in str(text).split()]
    except ValueError:
        return None
    return values if len(values) == 6 else None


def yaw_from_quaternion(q):
    """Yaw of a geometry_msgs/Quaternion-like object."""
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y),
                      1.0 - 2.0 * (q.y * q.y + q.z * q.z))


def yaw_from_tf_rotation(rotation):
    """Yaw of a tf rotation, returned as [x, y, z, w] or as a message."""
    if hasattr(rotation, 'w'):
        return yaw_from_quaternion(rotation)
    return float(tf.transformations.euler_from_quaternion(list(rotation))[2])


def path_length(samples):
    total = 0.0
    for first, second in zip(samples[:-1], samples[1:]):
        total += math.hypot(second[1] - first[1], second[2] - first[2])
    return total


def cumulative_rotation(samples):
    total = 0.0
    for first, second in zip(samples[:-1], samples[1:]):
        total += abs(wrap_angle(second[3] - first[3]))
    return total


class ContinuousRevisitDriver:
    def __init__(self, spec, output_dir):
        self.spec = spec
        self.output_dir = os.path.abspath(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)
        self.lock = threading.RLock()

        self.pose_nodes = {}
        self.pose_edges = {}
        self.full_nodes = {}
        self.full_edges = {}
        self.full_graph_count = 0
        self.full_graph_received_time = None
        self.slam_path = []
        self.slam_path_count = 0
        self.mapper_keyscan = None
        self.keyscan_events = []          # accepted keyscans observed on /others
        self.gt_pose = None
        self.gt_samples = []
        self.move_gt = []
        self.action_gt = []
        self.move_active = False
        self.action_active = False
        self.loop_events = []
        self.closure_edges = []
        self.moves = []

        self.scan_topic = rospy.get_param('~scan_topic', '/base_scan')
        self.scan_stream = None
        self.gt_stream = None
        self.keyscan_stream = None
        self.loop_stream = None
        self.scan_count = 0
        self.valid_scan_count = 0
        self.scan_records = []            # index, stamp, odom pose, dt
        self.phase_scan_marks = {}

        self.tf_listener = tf.TransformListener()
        # Frame names measured from the live TF tree of this workspace:
        #   map -> offset -> odom -> base_footprint -> base_link -> base_laser_link
        # ``map`` is SLAM-corrected (the mapper inserts ``offset``), while
        # ``odom`` is the raw, correction-free odometric chain the continuity
        # analysis needs.
        self.map_frame = rospy.get_param('~map_frame', 'map')
        self.odom_frame = rospy.get_param('~odom_frame', 'odom')
        self.base_frame = rospy.get_param('~base_frame', 'base_link')
        self.laser_frame = rospy.get_param('~laser_frame', 'base_laser_link')

        if spec.get('record_stream', True):
            self.scan_stream = open(os.path.join(self.output_dir,
                                                 'scan_stream.jsonl'), 'w')
            self.gt_stream = open(os.path.join(self.output_dir,
                                               'gt_stream.jsonl'), 'w')
            self.keyscan_stream = open(os.path.join(self.output_dir,
                                                    'keyscan_stream.jsonl'), 'w')
            self.loop_stream = open(os.path.join(self.output_dir,
                                                 'loop_events.jsonl'), 'w')

        rospy.Subscriber(self.scan_topic, LaserScan, self.on_scan,
                         queue_size=200)
        rospy.Subscriber('/slam_pose_graph', PoseGraph, self.on_pose_graph,
                         queue_size=100)
        rospy.Subscriber('/slam_pose_graph_full', PoseGraph,
                         self.on_full_pose_graph, queue_size=20)
        rospy.Subscriber('/slam_path', RosPath, self.on_slam_path,
                         queue_size=20)
        rospy.Subscriber('/base_pose_ground_truth', Odometry, self.on_gt,
                         queue_size=200)
        rospy.Subscriber('/others', RobotPose, self.on_mapper_keyscan_pose,
                         queue_size=200)
        rospy.Subscriber('/Mapper/loop_closed', LoopClosureEvent,
                         self.on_loop_closed, queue_size=20)
        rospy.Subscriber('/Mapper/closure_edges', Marker, self.on_closure_edges,
                         queue_size=20)

    # ------------------------------------------------------------------ callbacks
    def on_scan(self, msg):
        """Record one native scan and the odometric poses resolved for it.

        ``odom_laser`` is the laser pose in the correction-free odometric
        chain, so a laser return at beam ``i`` maps to the odom point
        ``odom_laser + range * (cos, sin)(bearing)`` with no extra lever arm.
        ``odom_base`` is the base pose in the same chain, and ``map_base`` is
        the SLAM-corrected pose, kept only as a cross-check.
        """
        stamp = float(msg.header.stamp.to_sec())
        odom_laser, odom_laser_age = self.resolve_tf(
            self.odom_frame, self.laser_frame, stamp)
        odom_base, odom_base_age = self.resolve_tf(
            self.odom_frame, self.base_frame, stamp)
        map_base, map_base_age = self.resolve_tf(
            self.map_frame, self.base_frame, stamp)
        finite = sum(1 for value in msg.ranges
                     if math.isfinite(float(value))
                     and float(value) >= float(msg.range_min)
                     and float(value) <= float(msg.range_max))
        record = {
            'index': self.scan_count,
            'stamp': stamp,
            'frame_id': msg.header.frame_id,
            'angle_min': float(msg.angle_min),
            'angle_max': float(msg.angle_max),
            'angle_increment': float(msg.angle_increment),
            'range_min': float(msg.range_min),
            'range_max': float(msg.range_max),
            'odom_laser': odom_laser,
            'odom_laser_age_s': odom_laser_age,
            'odom_base': odom_base,
            'odom_base_age_s': odom_base_age,
            'map_base': map_base,
            'map_base_age_s': map_base_age,
            'finite_returns': int(finite),
        }
        if self.scan_stream is not None:
            payload = dict(record)
            payload['ranges'] = [float(value) for value in msg.ranges]
            self.scan_stream.write(json.dumps(payload, separators=(',', ':')))
            self.scan_stream.write('\n')
        with self.lock:
            self.scan_records.append(record)
            self.scan_count += 1
            if finite > 0 and odom_laser is not None:
                self.valid_scan_count += 1

    def resolve_tf(self, parent, child, stamp):
        """(pose, age) of ``child`` in ``parent`` at ``stamp``, or (None, None)."""
        try:
            translation, rotation = self.tf_listener.lookupTransform(
                parent, child, rospy.Time(stamp))
            return ([float(translation[0]), float(translation[1]),
                     yaw_from_tf_rotation(rotation)], 0.0)
        except tf.Exception:
            pass
        try:
            translation, rotation = self.tf_listener.lookupTransform(
                parent, child, rospy.Time(0))
            return ([float(translation[0]), float(translation[1]),
                     yaw_from_tf_rotation(rotation)],
                    float(rospy.get_time()) - stamp)
        except tf.Exception:
            return None, None

    def on_pose_graph(self, msg):
        with self.lock:
            for index, node_id in enumerate(msg.vertices):
                self.pose_nodes[int(node_id)] = {
                    'id': int(node_id),
                    'x': float(msg.vertex_x[index]),
                    'y': float(msg.vertex_y[index]),
                    'theta': float(msg.vertex_theta[index]),
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
                'covariance_upper_triangle': parse_covariance(msg.covariance[index]),
            }
        with self.lock:
            self.full_nodes = nodes
            self.full_edges = edges
            self.full_graph_count += 1
            self.full_graph_received_time = float(rospy.get_time())

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
            self.slam_path_count += 1

    def on_mapper_keyscan_pose(self, msg):
        sample = {
            'stamp': float(msg.header.stamp.to_sec()),
            'received_ros_time': float(rospy.get_time()),
            'x': float(msg.pose.x),
            'y': float(msg.pose.y),
            'theta': float(msg.pose.theta),
        }
        with self.lock:
            self.mapper_keyscan = sample
            if len(self.keyscan_events) < 20000:
                self.keyscan_events.append(sample)
            if self.keyscan_stream is not None:
                self.keyscan_stream.write(json.dumps(sample, separators=(',', ':')))
                self.keyscan_stream.write('\n')

    def on_gt(self, msg):
        pose = msg.pose.pose
        sample = [
            float(msg.header.stamp.to_sec() or rospy.get_time()),
            float(pose.position.x), float(pose.position.y),
            yaw_from_quaternion(pose.orientation),
        ]
        with self.lock:
            self.gt_pose = sample
            self.gt_samples.append(sample)
            if self.gt_stream is not None:
                self.gt_stream.write(json.dumps(
                    {'stamp': sample[0], 'x': sample[1], 'y': sample[2],
                     'theta': sample[3]}, separators=(',', ':')))
                self.gt_stream.write('\n')
            if self.move_active:
                self.move_gt.append(sample)
            if self.action_active:
                self.action_gt.append(sample)

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
            'received_ros_time': float(rospy.get_time()),
        }
        with self.lock:
            self.loop_events.append(event)
            if self.loop_stream is not None:
                self.loop_stream.write(json.dumps(event, separators=(',', ':')))
                self.loop_stream.write('\n')

    def on_closure_edges(self, msg):
        edges = []
        for index in range(0, len(msg.points) - 1, 2):
            edges.append([[float(msg.points[index].x), float(msg.points[index].y)],
                          [float(msg.points[index + 1].x),
                           float(msg.points[index + 1].y)]])
        with self.lock:
            self.closure_edges = edges

    # ------------------------------------------------------------------ helpers
    def write_json(self, name, payload):
        path = os.path.join(self.output_dir, name)
        tmp = path + '.tmp'
        with open(tmp, 'w') as stream:
            json.dump(payload, stream, indent=1, sort_keys=True, default=str)
        os.replace(tmp, path)

    def wait_ready(self):
        rospy.loginfo('continuous-revisit driver ready; waiting for start gate')
        rate = rospy.Rate(5.0)
        while not rospy.is_shutdown():
            if rospy.get_param(self.gate_param, False):
                break
            rate.sleep()
        rospy.loginfo('start gate open')

    def current_tf_pose(self):
        """SLAM-corrected mapper pose of the base frame (map -> base_link)."""
        pose, _ = self.resolve_tf(self.map_frame, self.base_frame,
                                  rospy.get_time())
        return pose

    def current_odom_pose(self):
        pose, _ = self.resolve_tf(self.odom_frame, self.base_frame,
                                  rospy.get_time())
        return pose

    def current_gt_pose(self):
        with self.lock:
            return list(self.gt_pose) if self.gt_pose else None

    def snapshot(self, phase):
        """Record the synchronised graph state at a phase boundary."""
        with self.lock:
            keyscans = list(self.keyscan_events)
            full_nodes = dict(self.full_nodes)
            full_edges = dict(self.full_edges)
            pose_nodes = dict(self.pose_nodes)
            pose_edges = dict(self.pose_edges)
            slam_path = list(self.slam_path)
            gt = list(self.gt_pose) if self.gt_pose else None
            scans = list(self.scan_records)
            full_graph_count = self.full_graph_count
            slam_path_count = self.slam_path_count
        keyscan_ids = {int(node['id']) for node in full_nodes.values()}
        last_keyscan_state = None
        missing = []
        for event in keyscans:
            state = event.get('state_id')
            if state is None:
                continue
            last_keyscan_state = int(state)
            if int(state) not in keyscan_ids:
                missing.append(int(state))
        payload = {
            'phase': phase,
            'wall_time': time.time(),
            'ros_time': float(rospy.get_time()),
            'graph': {
                'nodes': sorted(full_nodes.values(), key=lambda n: n['id']),
                'edges': sorted(full_edges.values(), key=lambda e: e['index']),
            },
            'slam_path': slam_path,
            'pose_nodes': sorted(pose_nodes.values(), key=lambda n: n['id']),
            'pose_edges': sorted(pose_edges.values(), key=lambda e: e['index']),
            'gt_pose': gt,
            'scan_index_last': (scans[-1]['index'] if scans else None),
            'scan_count': len(scans),
            'valid_scan_count': self.valid_scan_count,
            'full_graph_message_count': full_graph_count,
            'slam_path_message_count': slam_path_count,
            'keyscan_events_seen': len(keyscans),
            'last_keyscan_state_id': last_keyscan_state,
            'keyscan_states_missing_from_graph': missing,
            'loop_events': list(self.loop_events),
        }
        return payload

    def wait_for_graph_boundary(self, timeout_s, quiescence_s=0.5):
        """Wait for a fresh, quiescent full-pose-graph state.

        Guarantee recorded here (and in the README): the returned snapshot is
        the newest full pose graph published after the phase's last scan and
        after at least ``quiescence_s`` of no new full-graph message, no new
        mapper keyscan publication and no new accepted-scan publication.  It is
        *not* an in-mapper barrier: the mapper has no per-scan processing ack,
        so the analysis additionally verifies node/edge counts and the scan
        index recorded with each snapshot.
        """
        deadline = time.time() + float(timeout_s)
        last_graph_count = None
        last_keyscan_count = None
        stable_start = None
        while time.time() < deadline:
            with self.lock:
                graph_count = self.full_graph_count
                keyscan_count = len(self.keyscan_events)
                graph_time = self.full_graph_received_time
                node_count = len(self.full_nodes)
                edge_count = len(self.full_edges)
            changed = (graph_count != last_graph_count
                       or keyscan_count != last_keyscan_count)
            if changed:
                stable_start = time.time()
                last_graph_count = graph_count
                last_keyscan_count = keyscan_count
            elif stable_start is not None and (time.time() - stable_start) >= quiescence_s:
                return {'satisfied': True,
                        'full_graph_messages': graph_count,
                        'keyscan_publications': keyscan_count,
                        'graph_nodes': node_count,
                        'graph_edges': edge_count,
                        'graph_received_ros_time': graph_time,
                        'quiescence_s': quiescence_s}
            time.sleep(0.1)
        return {'satisfied': False,
                'full_graph_messages': last_graph_count,
                'keyscan_publications': last_keyscan_count,
                'quiescence_s': quiescence_s}

    # ------------------------------------------------------------------ motion
    def move_to(self, client, x, y, theta, label, expected_gt_pose,
                timeout_s=None, settle_s=None):
        timeout_s = float(timeout_s or self.spec['move_timeout_s'])
        settle_s = float(self.spec.get('goal_settle_s', 1.0)
                         if settle_s is None else settle_s)
        goal = MoveToPosition2DGoal()
        goal.header.stamp = rospy.Time.now()
        goal.header.frame_id = 'map'
        goal.target_pose.x = float(x)
        goal.target_pose.y = float(y)
        goal.target_pose.theta = wrap_angle(float(theta))
        goal.target_distance = 0.25
        goal.target_angle = 0.1
        with self.lock:
            self.move_gt = []
            self.move_active = True
        start_time = float(rospy.get_time())
        start_tf = self.current_tf_pose()
        start_gt = self.current_gt_pose()
        client.send_goal(goal)
        finished = client.wait_for_result(rospy.Duration(timeout_s))
        if not finished:
            client.cancel_goal()
        state = int(client.get_state())
        deadline = time.time() + settle_s
        while time.time() < deadline:
            time.sleep(0.05)
        with self.lock:
            self.move_active = False
            samples = list(self.move_gt)
        observed_tf = self.current_tf_pose()
        observed_gt = self.current_gt_pose()
        if observed_tf is None or observed_gt is None:
            raise RuntimeError('no live TF/GT pose after MoveTo {}'.format(label))
        tf_position_error, tf_heading_error = goal_errors(observed_tf,
                                                         [x, y, theta])
        gt_position_error, gt_heading_error = goal_errors(gt_xy_yaw(observed_gt),
                                                         gt_xy_yaw(expected_gt_pose))
        row = {
            'label': label,
            'target_x': float(x), 'target_y': float(y),
            'target_theta': wrap_angle(float(theta)),
            'expected_gt_pose': list(expected_gt_pose),
            'start_time': start_time, 'end_time': float(rospy.get_time()),
            'action_finished': bool(finished), 'action_state': int(state),
            'tf_pose_before': start_tf, 'tf_pose_after': observed_tf,
            'gt_pose_before': gt_xy_yaw(start_gt),
            'gt_pose_after': gt_xy_yaw(observed_gt),
            'tf_position_error_m': tf_position_error,
            'tf_heading_error_rad': tf_heading_error,
            'gt_position_error_m': gt_position_error,
            'gt_heading_error_rad': gt_heading_error,
            'path_length_m': path_length(samples),
            'cumulative_rotation_rad': cumulative_rotation(samples),
            'gt_sample_count': len(samples),
        }
        self.moves.append(row)
        tf_reached = (tf_position_error <= self.spec['goal_position_tolerance_m']
                      and tf_heading_error <= self.spec['goal_heading_tolerance_rad'])
        gt_reached = (gt_position_error <= self.spec['gt_position_tolerance_m']
                      and gt_heading_error <= self.spec['gt_heading_tolerance_rad'])
        row['tf_reached'] = bool(tf_reached)
        row['gt_reached'] = bool(gt_reached)
        row['reached'] = bool(finished and state == 3 and tf_reached and gt_reached)
        rospy.logwarn(
            'CR_MOVE %s state=%s finished=%s tf=%.3f/%.3f gt=%.3f/%.3f '
            'rot=%.3f path=%.2f reached=%s',
            label, state, finished, tf_position_error, tf_heading_error,
            gt_position_error, gt_heading_error,
            row['cumulative_rotation_rad'], row['path_length_m'], row['reached'])
        if not finished or state != 3:
            raise RuntimeError('MoveTo {} failed with state {}'.format(label, state))
        if not row['reached']:
            raise RuntimeError(
                'MoveTo {} reported success but independent pose error is '
                'TF {:.3f} m/{:.3f} rad and GT {:.3f} m/{:.3f} rad'.format(
                    label, tf_position_error, tf_heading_error,
                    gt_position_error, gt_heading_error))
        return row

    # ------------------------------------------------------------------ target
    @staticmethod
    def contiguous_segment(nodes, reference, radius, heading_weight=None):
        """Anchor node for the historical observation pose, and its segment.

        ``reference`` is the executed arrival pose ``[x, y, theta]`` of the
        history leg recorded by the driver itself, so the anchor is the graph
        state that best represents *that* pose: position distance plus a fixed
        ``heading_weight`` (metres per radian) times the wrapped heading
        difference.  The segment is the maximal run of consecutively created
        states whose position stays within ``radius`` of the anchor.  The rule
        reads no action outcome and no post-action state.
        """
        if heading_weight is None:
            heading_weight = float(cr.TARGET_ANCHOR_HEADING_WEIGHT)

        def pose_distance(node):
            return (math.hypot(float(node['x']) - float(reference[0]),
                               float(node['y']) - float(reference[1]))
                    + heading_weight * abs(wrap_angle(
                        float(node['theta']) - float(reference[2]))))

        anchor = min(nodes, key=pose_distance)
        ordered = sorted(nodes, key=lambda node: node['id'])
        anchor_index = next(index for index, node in enumerate(ordered)
                            if node['id'] == anchor['id'])

        def inside(node):
            return math.hypot(float(node['x']) - anchor['x'],
                              float(node['y']) - anchor['y']) <= radius

        left = anchor_index
        while (left > 0 and ordered[left - 1]['id'] + 1 == ordered[left]['id']
               and inside(ordered[left - 1])):
            left -= 1
        right = anchor_index
        while (right + 1 < len(ordered)
               and ordered[right]['id'] + 1 == ordered[right + 1]['id']
               and inside(ordered[right + 1])):
            right += 1
        return anchor, ordered[left:right + 1]

    def freeze_target(self, before, arrival_pose):
        """Freeze the target identity from the executed history arrival pose.

        ``arrival_pose`` is the map-frame pose the probe actually held when the
        history leg stopped at the place (TF ``map -> base_link``, recorded by
        ``move_to``).  Everything below is derived from that pose and the graph
        snapshot taken before the return leg.
        """
        nodes = before['graph']['nodes']
        reference = [float(value) for value in arrival_pose]
        anchor, segment = self.contiguous_segment(
            nodes, reference, float(self.spec['target_segment_radius_m']),
            float(self.spec.get('target_anchor_heading_weight',
                                cr.TARGET_ANCHOR_HEADING_WEIGHT)))
        selected = cr.select_target_states(
            segment, count=int(self.spec['target_state_count']))
        anchor_distance = math.hypot(float(anchor['x']) - reference[0],
                                     float(anchor['y']) - reference[1])
        anchor_heading_error = abs(wrap_angle(float(anchor['theta'])
                                              - reference[2]))
        checks = {
            'minimum_history_node_count': (
                len(nodes) >= int(self.spec['minimum_history_node_count'])),
            'anchor_within_reference_radius': (
                anchor_distance <= float(self.spec['target_anchor_max_distance_m'])),
            'anchor_heading_within_tolerance': (
                anchor_heading_error <= float(self.spec[
                    'target_anchor_heading_tolerance_rad'])),
            'segment_has_target_states': (
                len(segment) >= int(self.spec['target_state_count'])),
            'anchor_is_not_root': int(anchor['id']) != int(nodes[0]['id']),
        }
        frozen = {
            'place_id': self.spec['place_id'],
            'action_id': self.spec['action_id'],
            'group_id': self.spec['group_id'],
            'reference_world_position': list(self.spec['place_world_position']),
            'reference_commanded_waypoint': list(self.resolved_reference),
            'reference_mapper_pose': reference,
            'reference_source': 'history_arrival_tf_pose',
            'anchor': anchor,
            'segment_state_ids': [int(node['id']) for node in segment],
            'segment_unique_ids': [int(node['unique_id']) for node in segment],
            'target_state_ids': [int(node['id']) for node in selected],
            'target_unique_ids': [int(node['unique_id']) for node in selected],
            'target_states': selected,
            'anchor_distance_m': anchor_distance,
            'anchor_heading_error_rad': anchor_heading_error,
            'anchor_heading_weight': float(
                self.spec.get('target_anchor_heading_weight',
                              cr.TARGET_ANCHOR_HEADING_WEIGHT)),
            'segment_length': len(segment),
            'checks': checks,
            'passed': all(checks.values()),
            'frozen_phase': 'G_before_return',
            'frozen_scan_index': before['scan_index_last'],
            'frozen_graph_node_count': len(nodes),
        }
        self.write_json('frozen_target.json', frozen)
        return frozen

    # ------------------------------------------------------------------ run
    def run(self):
        self.wait_ready()

        client = actionlib.SimpleActionClient('/MoveTo', MoveToPosition2DAction)
        if not client.wait_for_server(rospy.Duration(60.0)):
            raise RuntimeError('/MoveTo action server unavailable')

        live_tf = self.current_tf_pose()
        live_gt = self.current_gt_pose()
        with self.lock:
            first_karto = dict(self.slam_path[0]) if self.slam_path else None
        if live_tf is None or live_gt is None or first_karto is None:
            raise RuntimeError('no live TF/GT/Karto pose for the route origin')
        axis = float(self.spec['route_axis_heading_rad'])
        episode_origin = [first_karto['x'], first_karto['y'], axis]
        episode_gt_origin = [float(self.spec['start_pose'][0]),
                             float(self.spec['start_pose'][1]), axis]
        history_waypoints = resolve_local_waypoints(
            episode_origin, self.spec['history_offsets'])
        history_gt_waypoints = resolve_local_waypoints(
            episode_gt_origin, self.spec['history_offsets'])
        target_index = int(self.spec['target_history_waypoint_index'])
        self.resolved_reference = history_waypoints[target_index]
        with self.lock:
            route_start_nodes = len(self.slam_path)
        self.write_json('resolved_route.json', {
            'episode_mapper_origin': episode_origin,
            'episode_gt_origin': episode_gt_origin,
            'live_tf_pose_at_route_start': live_tf,
            'history_waypoints': history_waypoints,
            'history_gt_waypoints': history_gt_waypoints,
            'target_waypoint_index': target_index,
            'target_reference': self.resolved_reference,
            'route_start_node_count': route_start_nodes,
        })

        history_moves = []
        for index, (waypoint, gt_waypoint) in enumerate(
                zip(history_waypoints, history_gt_waypoints), 1):
            history_moves.append(self.move_to(
                client, waypoint[0], waypoint[1], waypoint[2],
                'history_{:02d}'.format(index), gt_waypoint))
        rospy.sleep(float(self.spec['history_hold_s']))
        with self.lock:
            self.phase_scan_marks['history_end_scan'] = self.scan_count

        boundary = self.wait_for_graph_boundary(30.0)
        before_return = self.snapshot('G_before_return')
        before_return['graph_boundary'] = boundary
        self.write_json('graph_before_return.json', before_return)
        if self.spec.get('stop_after_history'):
            self.write_json('episode_result.json', {
                'status': 'SUCCEEDED', 'episode_id': self.spec['episode_id'],
                'analysis_eligible': False,
                'exclusion_reason': 'history-only smoke capture',
                'moves': self.moves})
            self.close_stream()
            return

        arrival_pose = history_moves[target_index]['tf_pose_after']
        frozen = self.freeze_target(before_return, arrival_pose)
        frozen['return_goal_pose'] = [float(value) for value in arrival_pose]
        self.write_json('frozen_target.json', frozen)
        if not frozen['passed']:
            failed = sorted(name for name, ok in frozen['checks'].items() if not ok)
            raise RuntimeError('target identity gate failed: {}'.format(
                ', '.join(failed)))

        # ---- return leg -----------------------------------------------------
        with self.lock:
            self.phase_scan_marks['return_start_scan'] = self.scan_count
        historical_gt = history_moves[target_index]['gt_pose_after']
        arrival_label = 'return_to_{}'.format(self.spec['place_id'])
        # The observation pose to reproduce is the pose the history leg actually
        # stopped in (recorded by move_to), not the closest graph state: the
        # mapper only inserts a state after 0.52 rad of turning, so the closest
        # state can lag the stop heading by that much.
        self.move_to(client, arrival_pose[0], arrival_pose[1], arrival_pose[2],
                     arrival_label, historical_gt)
        rospy.sleep(float(self.spec['arrival_hold_s']))
        boundary = self.wait_for_graph_boundary(30.0)
        arrival = self.snapshot('G_arrival')
        arrival['graph_boundary'] = boundary
        self.write_json('graph_arrival.json', arrival)

        # ---- action phase ---------------------------------------------------
        with self.lock:
            action_start_scan = self.scan_count
            action_start_valid = self.valid_scan_count
            self.action_gt = []
            self.action_active = True
        action_goals = cr.action_goals(self.spec,
                                      [arrival_pose[0], arrival_pose[1],
                                       arrival_pose[2]], historical_gt)
        action_moves = []
        for x, y, theta, label, expected_gt in action_goals:
            action_moves.append(self.move_to(client, x, y, theta, label,
                                             expected_gt))
        action_done_valid = self.valid_scan_count - action_start_valid
        # The handoff requires an explicitly recorded end of the initial hold
        # for the static arm, so every arm waits the same settle time here.
        rospy.sleep(float(self.spec['action_finish_hold_s']))
        boundary = self.wait_for_graph_boundary(30.0)
        action_done = self.snapshot('G_action_done')
        action_done['graph_boundary'] = boundary
        self.write_json('graph_action_done.json', action_done)

        # ---- collect the remaining action-phase frames ----------------------
        deadline = time.time() + float(self.spec['action_phase_timeout_s'])
        target_frames = int(self.spec['action_frames'])
        while (self.valid_scan_count - action_start_valid) < target_frames:
            if time.time() > deadline:
                raise RuntimeError(
                    'action phase did not collect {} valid scans in time '
                    '({} collected)'.format(
                        target_frames, self.valid_scan_count - action_start_valid))
            time.sleep(0.05)
        final_valid = self.valid_scan_count - action_start_valid
        with self.lock:
            self.action_active = False
        boundary = self.wait_for_graph_boundary(30.0)
        final = self.snapshot('G_final')
        final['graph_boundary'] = boundary
        self.write_json('graph_final.json', final)

        with self.lock:
            action_scans = [record for record in self.scan_records
                            if record['index'] >= action_start_scan]
            action_gt = list(self.action_gt)
        result = {
            'status': 'SUCCEEDED',
            'episode_id': self.spec['episode_id'],
            'analysis_eligible': True,
            'frozen_target': frozen,
            'history_moves': [move['label'] for move in history_moves],
            'arrival_move': self.moves[-1 - len(action_moves)]['label']
            if action_moves else self.moves[-1]['label'],
            'action_goals': [goal[3] for goal in action_goals],
            'phase_scan_marks': dict(self.phase_scan_marks),
            'action_start_scan_index': action_start_scan,
            'action_start_valid_index': action_start_valid,
            'action_done_valid_frames': action_done_valid,
            'action_final_valid_frames': final_valid,
            'action_frames_target': target_frames,
            'action_moves': action_moves,
            'action_scan_count': len(action_scans),
            'action_gt_samples': len(action_gt),
            'action_path_length_m': path_length(action_gt),
            'action_cumulative_rotation_rad': cumulative_rotation(action_gt),
            'action_max_abs_yaw_from_start_rad': max(
                (abs(wrap_angle(sample[3] - action_gt[0][3]))
                 for sample in action_gt), default=0.0),
            'action_gt_track': [[float(sample[1]), float(sample[2]),
                                 float(sample[3])] for sample in action_gt],
            'total_path_length_m': path_length(self.gt_samples),
            'total_cumulative_rotation_rad': cumulative_rotation(self.gt_samples),
            'moves': self.moves,
            'loop_events': self.loop_events,
            'scan_count': self.scan_count,
            'valid_scan_count': self.valid_scan_count,
            'phase_boundaries': {
                'G_before_return': {
                    'scan_index': before_return['scan_index_last'],
                    'graph_nodes': len(before_return['graph']['nodes']),
                    'boundary': before_return['graph_boundary']},
                'G_arrival': {
                    'scan_index': arrival['scan_index_last'],
                    'graph_nodes': len(arrival['graph']['nodes']),
                    'boundary': arrival['graph_boundary']},
                'G_action_done': {
                    'scan_index': action_done['scan_index_last'],
                    'graph_nodes': len(action_done['graph']['nodes']),
                    'boundary': action_done['graph_boundary']},
                'G_final': {
                    'scan_index': final['scan_index_last'],
                    'graph_nodes': len(final['graph']['nodes']),
                    'boundary': final['graph_boundary']},
            },
        }
        self.close_stream()
        self.write_json('episode_result.json', result)
        return result

    def close_stream(self):
        for name in ('scan_stream', 'gt_stream', 'keyscan_stream', 'loop_stream'):
            stream = getattr(self, name)
            if stream is not None:
                stream.flush()
                stream.close()
                setattr(self, name, None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--spec', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--start-gate-param', required=True)
    args = parser.parse_args(rospy.myargv()[1:])
    with open(args.spec) as stream:
        spec = json.load(stream)
    rospy.init_node('continuous_revisit_driver', anonymous=False)
    driver = ContinuousRevisitDriver(spec, args.output_dir)
    driver.gate_param = args.start_gate_param
    rospy.set_param(args.start_gate_param + '_subscriber_ready', True)
    try:
        result = driver.run()
        print(json.dumps({
            'status': result['status'],
            'episode_id': result['episode_id'],
            'analysis_eligible': result.get('analysis_eligible'),
        }, sort_keys=True))
    except Exception as exc:
        driver.close_stream()
        driver.write_json('episode_result.json', {
            'status': 'FAILED', 'episode_id': spec.get('episode_id'),
            'reason': '{}: {}'.format(type(exc).__name__, exc),
            'moves': driver.moves})
        raise
    finally:
        driver.close_stream()
        rospy.signal_shutdown('continuous revisit episode finished')


if __name__ == '__main__':
    main()
