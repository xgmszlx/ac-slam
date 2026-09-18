#!/usr/bin/python3
"""World-frame Stage controller and raw probe-stream recorder for v9."""

import argparse
import json
import math
import os
import threading
import time

import rospy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan


LASER_OFFSET_M = 0.2


def wrap_angle(value):
    return math.atan2(math.sin(value), math.cos(value))


def yaw_from_quaternion(q):
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y),
                      1.0 - 2.0 * (q.y * q.y + q.z * q.z))


def clamp(value, limit):
    return max(-limit, min(limit, value))


def path_length(samples):
    return sum(math.hypot(right[1] - left[1], right[2] - left[2])
               for left, right in zip(samples, samples[1:]))


def yaw_excursion(samples):
    return sum(abs(wrap_angle(right[3] - left[3]))
               for left, right in zip(samples, samples[1:]))


class ControlledCapture:
    def __init__(self, spec, output_dir):
        self.spec = spec
        self.output_dir = os.path.abspath(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)
        self.lock = threading.RLock()
        self.gt = None
        self.odom = None
        self.scan_seen = False
        self.capture_active = False
        self.records = []
        self.gt_samples = []
        self.all_moves = []
        self.publisher = rospy.Publisher('/cmd_vel', Twist, queue_size=1)
        rospy.Subscriber('/base_pose_ground_truth', Odometry, self.on_gt,
                         queue_size=100)
        rospy.Subscriber('/odom', Odometry, self.on_odom, queue_size=100)
        rospy.Subscriber('/base_scan', LaserScan, self.on_scan, queue_size=100)

    def on_gt(self, message):
        pose = message.pose.pose
        sample = [float(message.header.stamp.to_sec()), float(pose.position.x),
                  float(pose.position.y), yaw_from_quaternion(pose.orientation)]
        with self.lock:
            self.gt = sample
            if self.capture_active:
                self.gt_samples.append(sample)

    def on_odom(self, message):
        pose = message.pose.pose
        with self.lock:
            self.odom = [float(message.header.stamp.to_sec()),
                         float(pose.position.x), float(pose.position.y),
                         yaw_from_quaternion(pose.orientation)]

    def on_scan(self, scan):
        with self.lock:
            self.scan_seen = True
            if not self.capture_active or self.odom is None:
                return
            odom = list(self.odom)
        laser_x = odom[1] + LASER_OFFSET_M * math.cos(odom[3])
        laser_y = odom[2] + LASER_OFFSET_M * math.sin(odom[3])
        self.records.append({
            'stamp': float(scan.header.stamp.to_sec()),
            'frame_id': scan.header.frame_id,
            'robot_id': 1,
            'laser_type': 0,
            'x': laser_x, 'y': laser_y, 'yaw': odom[3],
            'angle_min': float(scan.angle_min),
            'angle_max': float(scan.angle_max),
            'angle_increment': float(scan.angle_increment),
            'range_min': float(scan.range_min),
            'range_max': float(scan.range_max),
            'ranges': [float(value) for value in scan.ranges],
        })

    def pose(self):
        with self.lock:
            return None if self.gt is None else list(self.gt[1:])

    def stop(self):
        self.publisher.publish(Twist())

    def hold_static(self, duration_s):
        """Hold zero velocity while retaining raw scan exposure.

        The dwell is deliberately implemented outside the waypoint controller:
        it has no target-yaw update and therefore cannot contain an implicit
        sweep.  The returned motion diagnostics are used as an execution gate,
        not as a backend outcome.
        """
        duration_s = float(duration_s)
        start_time = float(rospy.get_time())
        start_pose = self.pose()
        with self.lock:
            gt_start_index = len(self.gt_samples)
            raw_start_index = len(self.records)
        rate = rospy.Rate(20)
        while (float(rospy.get_time()) - start_time < duration_s and
               not rospy.is_shutdown()):
            self.stop()
            rate.sleep()
        self.stop()
        end_time = float(rospy.get_time())
        end_pose = self.pose()
        with self.lock:
            dwell_gt = list(self.gt_samples[gt_start_index:])
            raw_count = len(self.records) - raw_start_index
        return {
            'requested_duration_s': duration_s,
            'actual_duration_s': end_time - start_time,
            'start_time': start_time,
            'end_time': end_time,
            'start_gt_pose': start_pose,
            'end_gt_pose': end_pose,
            'distance_m': path_length(dwell_gt),
            'yaw_excursion_rad': yaw_excursion(dwell_gt),
            'raw_scan_count': raw_count,
            'command': 'zero_twist_only',
            'deliberate_yaw_command': False,
        }

    def wait_ready(self):
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline and not rospy.is_shutdown():
            with self.lock:
                ready = self.gt is not None and self.odom is not None and self.scan_seen
            if ready and self.publisher.get_num_connections() > 0:
                return
            rospy.sleep(0.05)
        raise RuntimeError('Stage GT/odom/scan/cmd_vel not ready within 60 s')

    def rotate_to(self, target_yaw, timeout_s=40.0):
        deadline = float(rospy.get_time()) + timeout_s
        stable = 0
        while not rospy.is_shutdown():
            current = self.pose()
            error = wrap_angle(float(target_yaw) - current[2])
            if abs(error) <= 0.018:
                stable += 1
                self.stop()
                if stable >= 3:
                    return
            else:
                stable = 0
                command = Twist()
                command.angular.z = clamp(1.8 * error, 0.65)
                self.publisher.publish(command)
            if float(rospy.get_time()) > deadline:
                self.stop()
                raise RuntimeError('rotation timeout; remaining {:.3f} rad'.format(error))
            rospy.sleep(0.05)

    def drive_to(self, target_x, target_y, timeout_s=90.0):
        deadline = float(rospy.get_time()) + timeout_s
        stable = 0
        while not rospy.is_shutdown():
            current = self.pose()
            dx = float(target_x) - current[0]
            dy = float(target_y) - current[1]
            distance = math.hypot(dx, dy)
            if distance <= 0.045:
                stable += 1
                self.stop()
                if stable >= 3:
                    return
            else:
                stable = 0
                desired = math.atan2(dy, dx)
                heading_error = wrap_angle(desired - current[2])
                command = Twist()
                command.linear.x = min(0.55, max(0.08, 0.8 * distance)) \
                    if abs(heading_error) < 0.65 else 0.0
                command.angular.z = clamp(2.0 * heading_error, 0.65)
                self.publisher.publish(command)
            if float(rospy.get_time()) > deadline:
                self.stop()
                raise RuntimeError('translation timeout; remaining {:.3f} m'.format(distance))
            rospy.sleep(0.05)

    def move_to(self, waypoint, label):
        start_time = float(rospy.get_time())
        before = self.pose()
        target_x, target_y, target_yaw = [float(value) for value in waypoint]
        current = self.pose()
        bearing = math.atan2(target_y - current[1], target_x - current[0])
        if math.hypot(target_x - current[0], target_y - current[1]) > 0.05:
            self.rotate_to(bearing)
            self.drive_to(target_x, target_y)
        self.rotate_to(target_yaw)
        rospy.sleep(0.3)
        after = self.pose()
        error = [math.hypot(after[0] - target_x, after[1] - target_y),
                 abs(wrap_angle(after[2] - target_yaw))]
        row = {'label': label, 'target': [target_x, target_y, target_yaw],
               'before': before, 'after': after, 'position_error_m': error[0],
               'heading_error_rad': error[1], 'start_time': start_time,
               'end_time': float(rospy.get_time())}
        self.all_moves.append(row)
        if error[0] > 0.08 or error[1] > 0.04:
            raise RuntimeError('{} controller gate failed: {:.3f} m/{:.3f} rad'.format(
                label, error[0], error[1]))
        return row

    def run(self):
        self.wait_ready()
        initial_pose = self.pose()
        for index, waypoint in enumerate(self.spec['setup_waypoints']):
            self.move_to(waypoint, 'setup_{:02d}'.format(index + 1))
        branch_start = self.pose()
        if self.spec.get('calibration_only', False):
            result = {'status': 'SUCCEEDED', 'calibration_only': True,
                      'initial_gt_pose': initial_pose,
                      'branch_start_gt_pose': branch_start,
                      'moves': self.all_moves}
            self.write_outputs(result)
            return result

        with self.lock:
            self.records = []
            self.gt_samples = []
            self.capture_active = True
        # Ensure the stitched branch has a sample exactly at the physical start.
        rospy.sleep(0.2)
        probe_start_time = float(rospy.get_time())
        for index, waypoint in enumerate(self.spec['action_waypoints']):
            label = self.spec['action_labels'][index]
            self.move_to(waypoint, label)
        dwell = None
        if float(self.spec.get('dwell_s', 0.0)) > 0.0:
            dwell = self.hold_static(self.spec['dwell_s'])
        rospy.sleep(float(self.spec.get('hold_s', 6.0)))
        with self.lock:
            self.capture_active = False
        self.stop()
        result = {
            'status': 'SUCCEEDED', 'calibration_only': False,
            'action_id': self.spec['action_id'],
            'initial_gt_pose': initial_pose,
            'branch_start_gt_pose': branch_start,
            'branch_end_gt_pose': self.pose(),
            'probe_start_time': probe_start_time,
            'probe_end_time': float(rospy.get_time()),
            'actual_duration_s': float(rospy.get_time()) - probe_start_time,
            'actual_distance_m': path_length(self.gt_samples),
            'actual_yaw_excursion_rad': yaw_excursion(self.gt_samples),
            'raw_scan_count': len(self.records),
            'gt_sample_count': len(self.gt_samples),
            'moves': self.all_moves,
            'action_waypoints': self.spec['action_waypoints'],
            'action_labels': self.spec['action_labels'],
            'dwell': dwell,
        }
        self.write_outputs(result)
        return result

    def write_outputs(self, result):
        with open(os.path.join(self.output_dir, 'capture_result.json'), 'w') as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write('\n')
        if not self.spec.get('calibration_only', False):
            with open(os.path.join(self.output_dir, 'probe_stream_raw.jsonl'), 'w') as stream:
                for row in self.records:
                    stream.write(json.dumps(row, separators=(',', ':')) + '\n')
            with open(os.path.join(self.output_dir, 'probe_gt_trajectory.txt'), 'w') as stream:
                for row in self.gt_samples:
                    stream.write('{:.9f} {:.9f} {:.9f} {:.9f}\n'.format(*row))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--spec', required=True)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args(rospy.myargv()[1:])
    with open(args.spec) as stream:
        spec = json.load(stream)
    rospy.init_node('v9_controlled_probe_capture', anonymous=False)
    capture = ControlledCapture(spec, args.output_dir)
    try:
        result = capture.run()
        print(json.dumps({'status': result['status'],
                          'branch_start_gt_pose': result['branch_start_gt_pose'],
                          'raw_scan_count': result.get('raw_scan_count', 0)},
                         sort_keys=True))
    finally:
        capture.stop()


if __name__ == '__main__':
    main()
