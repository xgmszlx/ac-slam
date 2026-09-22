#!/usr/bin/python3
"""Stage controller with an exact first-N scientific treatment stream."""

import argparse
import json
import math
import os
import threading

import rospy
from geometry_msgs.msg import Twist
from sensor_msgs.msg import LaserScan

from controlled_probe_capture import (
    LASER_OFFSET_M, ControlledCapture, path_length, wrap_angle, yaw_excursion,
)
from v14t_fixed_scan_protocol import (MANEUVER_COMPLETION_LABEL,
                                      fixed_scan_stream_diagnostics)


class FixedScanCapture(ControlledCapture):
    def __init__(self, spec, output_dir):
        self.scan_budget = int(spec['scientific_treatment_scan_budget'])
        if self.scan_budget <= 0:
            raise ValueError('scientific treatment scan budget must be positive')
        self.scientific_records = []
        self.treatment_records_all = []
        self.treatment_gt_samples = []
        self.treatment_active = False
        self.treatment_start_time = None
        super().__init__(spec, output_dir)

    @staticmethod
    def _scan_record(scan, odom):
        laser_x = odom[1] + LASER_OFFSET_M * math.cos(odom[3])
        laser_y = odom[2] + LASER_OFFSET_M * math.sin(odom[3])
        return {
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
        }

    def on_gt(self, message):
        super().on_gt(message)
        with self.lock:
            if self.treatment_active and self.gt is not None:
                self.treatment_gt_samples.append(list(self.gt))

    def on_scan(self, scan):
        with self.lock:
            self.scan_seen = True
            if not self.capture_active or self.odom is None:
                return
            record = self._scan_record(scan, list(self.odom))
            self.records.append(record)
            if (self.treatment_active and self.treatment_start_time is not None
                    and float(record['stamp']) >= self.treatment_start_time):
                self.treatment_records_all.append(record)
                if len(self.scientific_records) < self.scan_budget:
                    self.scientific_records.append(record)

    def move_to_treatment_start(self, waypoint, label):
        """Reset the counter at the exact start time recorded for arrival."""
        start_time = float(rospy.get_time())
        with self.lock:
            self.scientific_records = []
            self.treatment_records_all = []
            self.treatment_gt_samples = []
            self.treatment_start_time = start_time
            self.treatment_active = True
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
               'before': before, 'after': after,
               'position_error_m': error[0],
               'heading_error_rad': error[1], 'start_time': start_time,
               'end_time': float(rospy.get_time())}
        self.all_moves.append(row)
        if error[0] > 0.08 or error[1] > 0.04:
            raise RuntimeError(
                '{} controller gate failed: {:.3f} m/{:.3f} rad'.format(
                    label, error[0], error[1]))
        return row

    def wait_for_scan_budget(self, timeout_s=90.0):
        deadline = float(rospy.get_time()) + float(timeout_s)
        rate = rospy.Rate(20)
        while not rospy.is_shutdown():
            with self.lock:
                count = len(self.scientific_records)
            if count >= self.scan_budget:
                return
            self.stop()
            if float(rospy.get_time()) > deadline:
                raise RuntimeError(
                    'treatment scan budget timeout: {}/{}'.format(
                        count, self.scan_budget))
            rate.sleep()
        raise RuntimeError('ROS shutdown before treatment scan budget')

    @staticmethod
    def timestamp_integrity(records):
        stamps = [float(row['stamp']) for row in records]
        return {
            'duplicate_timestamp_count': len(stamps) - len(set(stamps)),
            'nonmonotonic_timestamp_count': sum(
                right <= left for left, right in zip(stamps, stamps[1:])),
        }

    def run(self):
        self.wait_ready()
        initial_pose = self.pose()
        for index, waypoint in enumerate(self.spec['setup_waypoints']):
            self.move_to(waypoint, 'setup_{:02d}'.format(index + 1))
        branch_start = self.pose()

        with self.lock:
            self.records = []
            self.gt_samples = []
            self.capture_active = True
        rospy.sleep(0.2)
        raw_capture_start = float(rospy.get_time())
        core = int(self.spec['core_action_start_index'])
        for index in range(core):
            self.move_to(self.spec['action_waypoints'][index],
                         self.spec['action_labels'][index])
        if self.spec['action_labels'][core] != 'probe_arrival':
            raise RuntimeError('core action must start with probe_arrival')
        self.move_to_treatment_start(
            self.spec['action_waypoints'][core], 'probe_arrival')
        for index in range(core + 1, len(self.spec['action_waypoints'])):
            self.move_to(self.spec['action_waypoints'][index],
                         self.spec['action_labels'][index])
        completion_label = MANEUVER_COMPLETION_LABEL[self.spec['action_id']]
        completion_move = next(
            row for row in self.all_moves if row['label'] == completion_label)
        completion_time = float(completion_move['end_time'])
        self.stop()

        with self.lock:
            count_at_completion = sum(
                self.treatment_start_time <= float(row['stamp']) <= completion_time
                for row in self.treatment_records_all)
        if count_at_completion <= self.scan_budget:
            self.wait_for_scan_budget()
        with self.lock:
            scientific = list(self.scientific_records[:self.scan_budget])
            treatment_all = list(self.treatment_records_all)
            treatment_end = (float(scientific[-1]['stamp'])
                             if scientific else None)
            self.treatment_active = False
        # Preserve a small raw-only shutdown tail to prove first-N isolation.
        self.stop()
        rospy.sleep(0.3)
        with self.lock:
            self.capture_active = False
        self.stop()

        diagnostics = fixed_scan_stream_diagnostics(
            treatment_all, self.treatment_start_time, completion_time,
            self.scan_budget)
        integrity = self.timestamp_integrity(scientific)
        final_completion_index = diagnostics['completion_scan_index']
        exact_first_n = scientific == treatment_all[:self.scan_budget]
        status = diagnostics['status']
        if status == 'SUCCEEDED' and not exact_first_n:
            status = 'TECHNICAL_INVALID_SCIENTIFIC_STREAM_CONTAMINATION'

        result = {
            'status': status,
            'technical_only': True,
            'backend_started': False,
            'scientific_endpoint_read': False,
            'action_id': self.spec['action_id'],
            'initial_gt_pose': initial_pose,
            'branch_start_gt_pose': branch_start,
            'branch_end_gt_pose': self.pose(),
            'raw_capture_start_time': raw_capture_start,
            'treatment_start_time': self.treatment_start_time,
            'treatment_end_timestamp': treatment_end,
            'maneuver_completion_time': completion_time,
            'completion_scan_index': final_completion_index,
            'scientific_treatment_scan_budget': self.scan_budget,
            'scientific_treatment_scan_count': len(scientific),
            'completion_margin': self.scan_budget - final_completion_index,
            'static_tail_scan_count': max(
                0, self.scan_budget - final_completion_index),
            'raw_scan_count': len(self.records),
            'treatment_raw_scan_count': len(treatment_all),
            'raw_exceeds_scientific_by': len(self.records) - len(scientific),
            'scientific_stream_exact_first_N': exact_first_n,
            'no_scientific_stream_contamination_after_N': exact_first_n,
            'duplicate_timestamp_count': integrity['duplicate_timestamp_count'],
            'nonmonotonic_timestamp_count': integrity[
                'nonmonotonic_timestamp_count'],
            'wall_clock_duration_s': (
                treatment_end - self.treatment_start_time
                if treatment_end is not None else None),
            'treatment_path_length_m': path_length(self.treatment_gt_samples),
            'treatment_yaw_excursion_rad': yaw_excursion(
                self.treatment_gt_samples),
            'moves': self.all_moves,
            'action_waypoints': self.spec['action_waypoints'],
            'action_labels': self.spec['action_labels'],
            'timestamp_inclusion': (
                'treatment_start <= scan.stamp <= maneuver_completion'),
        }
        self.write_fixed_outputs(result, scientific)
        return result

    def write_fixed_outputs(self, result, scientific):
        with open(os.path.join(self.output_dir, 'capture_result.json'), 'w') as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write('\n')
        with open(os.path.join(self.output_dir, 'probe_stream_raw.jsonl'), 'w') as stream:
            for row in self.records:
                stream.write(json.dumps(row, separators=(',', ':')) + '\n')
        with open(os.path.join(
                self.output_dir, 'scientific_treatment_stream.jsonl'), 'w') as stream:
            for row in scientific:
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
    rospy.init_node('v14t_fixed_scan_capture', anonymous=False)
    capture = FixedScanCapture(spec, args.output_dir)
    try:
        result = capture.run()
        print(json.dumps({
            'status': result['status'],
            'scientific_treatment_scan_count': result[
                'scientific_treatment_scan_count'],
            'completion_scan_index': result['completion_scan_index'],
            'completion_margin': result['completion_margin'],
        }, sort_keys=True))
        if result['status'] != 'SUCCEEDED':
            raise SystemExit(2)
    finally:
        capture.stop()


if __name__ == '__main__':
    main()
