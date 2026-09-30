#!/usr/bin/python3
"""Technical-only fixed-N controller for standardized CD-T angular doses."""

import argparse
import json
import os

import rospy

from controlled_probe_capture import path_length, wrap_angle, yaw_excursion
from context_disentangle_protocol import (
    D0_YAW_MAX_RAD, DOSES, FINAL_HEADING_TOLERANCE_RAD,
    pretreatment_scan_descriptor, YAW_TOLERANCE_RAD,
)
from fixed_scan_capture import FixedScanCapture
from v14t_fixed_scan_protocol import fixed_scan_stream_diagnostics


def angular_rates(samples):
    rates = [abs(wrap_angle(right[3] - left[3])) / (right[0] - left[0])
             for left, right in zip(samples, samples[1:])
             if right[0] > left[0]]
    return {
        'mean_abs_angular_velocity_rad_s': (
            sum(rates) / len(rates) if rates else 0.0),
        'max_abs_angular_velocity_rad_s': max(rates) if rates else 0.0,
    }


class ContextDoseCapture(FixedScanCapture):
    def __init__(self, spec, output_dir):
        self.last_scan_record = None
        super().__init__(spec, output_dir)

    def on_scan(self, scan):
        with self.lock:
            self.scan_seen = True
            if self.odom is None:
                return
            record = self._scan_record(scan, list(self.odom))
            self.last_scan_record = record
            if not self.capture_active:
                return
            self.records.append(record)
            if (self.treatment_active and self.treatment_start_time is not None
                    and float(record['stamp']) >= self.treatment_start_time):
                self.treatment_records_all.append(record)
                if len(self.scientific_records) < self.scan_budget:
                    self.scientific_records.append(record)

    def _begin_treatment(self):
        start_time = float(rospy.get_time())
        with self.lock:
            self.records = []
            self.gt_samples = []
            self.scientific_records = []
            self.treatment_records_all = []
            self.treatment_gt_samples = []
            self.treatment_start_time = start_time
            self.capture_active = True
            self.treatment_active = True
        return start_time

    def run(self):
        self.wait_ready()
        initial_pose = self.pose()
        for index, waypoint in enumerate(self.spec['setup_waypoints']):
            self.move_to(waypoint, 'setup_{:02d}'.format(index + 1))
        branch_start = self.pose()

        core = int(self.spec['core_action_start_index'])
        for index in range(core):
            self.move_to(self.spec['action_waypoints'][index],
                         self.spec['action_labels'][index])
        if self.spec['action_labels'][core] != 'probe_arrival':
            raise RuntimeError('core action must start with probe_arrival')
        self.move_to(self.spec['action_waypoints'][core], 'probe_arrival')
        common_start_pose = self.pose()
        theta0 = float(self.spec['theta0_rad'])
        if abs(wrap_angle(common_start_pose[2] - theta0)) > \
                FINAL_HEADING_TOLERANCE_RAD:
            raise RuntimeError('common treatment start heading gate failed')
        with self.lock:
            snapshot = dict(self.last_scan_record) if self.last_scan_record else None
        if snapshot is None:
            raise RuntimeError('no pre-treatment laser scan available')
        descriptor = pretreatment_scan_descriptor(snapshot)

        treatment_start = self._begin_treatment()
        self.stop()
        rospy.sleep(0.3)
        arm = self.spec['action_id']
        if arm not in DOSES:
            raise RuntimeError('unknown CD-T dose arm')
        for index in range(core + 1, len(self.spec['action_waypoints'])):
            self.move_to(self.spec['action_waypoints'][index],
                         self.spec['action_labels'][index])
        self.stop()
        completion_time = float(rospy.get_time())
        completion_pose = self.pose()
        with self.lock:
            moving_samples = [list(row) for row in self.treatment_gt_samples
                              if treatment_start <= row[0] <= completion_time]
            completion_scan_index = sum(
                treatment_start <= float(row['stamp']) <= completion_time
                for row in self.treatment_records_all)
        moving_path = ([[treatment_start] + common_start_pose] + moving_samples +
                       [[completion_time] + completion_pose])
        actual_yaw = yaw_excursion(moving_path)
        final_residual = abs(wrap_angle(completion_pose[2] - theta0))

        if completion_scan_index <= self.scan_budget:
            self.wait_for_scan_budget()
        with self.lock:
            scientific = list(self.scientific_records[:self.scan_budget])
            treatment_all = list(self.treatment_records_all)
            treatment_end = float(scientific[-1]['stamp']) if scientific else None
            self.treatment_active = False
        self.stop()
        rospy.sleep(0.3)
        with self.lock:
            self.capture_active = False
        diagnostics = fixed_scan_stream_diagnostics(
            treatment_all, treatment_start, completion_time, self.scan_budget)
        integrity = self.timestamp_integrity(scientific)
        exact_first_n = scientific == treatment_all[:self.scan_budget]
        status = diagnostics['status']
        planned = float(DOSES[arm])
        yaw_ok = (actual_yaw <= D0_YAW_MAX_RAD if arm == 'D0_ZERO' else
                  abs(actual_yaw - planned) <= YAW_TOLERANCE_RAD)
        if status == 'SUCCEEDED' and not exact_first_n:
            status = 'TECHNICAL_INVALID_SCIENTIFIC_STREAM_CONTAMINATION'
        if status == 'SUCCEEDED' and not yaw_ok:
            status = 'TECHNICAL_INVALID_ACTUAL_DOSE'
        if status == 'SUCCEEDED' and final_residual > \
                FINAL_HEADING_TOLERANCE_RAD:
            status = 'TECHNICAL_INVALID_FINAL_HEADING'
        rates = angular_rates(moving_path)
        result = {
            'status': status, 'technical_only': True,
            'backend_started': False, 'scientific_endpoint_read': False,
            'action_id': arm, 'dose_intervention': 'STANDARDIZED_ANGULAR_DOSE',
            'initial_gt_pose': initial_pose,
            'branch_start_gt_pose': branch_start,
            'common_treatment_start_gt_pose': common_start_pose,
            'branch_end_gt_pose': self.pose(),
            'treatment_start_time': treatment_start,
            'treatment_end_timestamp': treatment_end,
            'maneuver_completion_time': completion_time,
            'maneuver_duration_s': completion_time - treatment_start,
            'completion_scan_index': diagnostics['completion_scan_index'],
            'moving_scan_count': diagnostics['completion_scan_index'],
            'scientific_treatment_scan_budget': self.scan_budget,
            'scientific_treatment_scan_count': len(scientific),
            'completion_margin': self.scan_budget - diagnostics[
                'completion_scan_index'],
            'post_maneuver_static_scan_count': max(
                0, self.scan_budget - diagnostics['completion_scan_index']),
            'raw_scan_count': len(self.records),
            'treatment_raw_scan_count': len(treatment_all),
            'scientific_stream_exact_first_N': exact_first_n,
            'no_scientific_stream_contamination_after_N': exact_first_n,
            'duplicate_timestamp_count': integrity['duplicate_timestamp_count'],
            'nonmonotonic_timestamp_count': integrity[
                'nonmonotonic_timestamp_count'],
            'planned_cumulative_yaw_rad': planned,
            'actual_cumulative_yaw_rad': actual_yaw,
            'actual_dose_error_rad': actual_yaw - planned,
            'actual_dose_gate_passed': yaw_ok,
            'final_heading_rad': completion_pose[2],
            'final_heading_residual_rad': final_residual,
            'treatment_path_length_m': path_length(moving_path),
            'moving_gt_sample_count': len(moving_samples),
            'mean_abs_angular_velocity_rad_s': rates[
                'mean_abs_angular_velocity_rad_s'],
            'max_abs_angular_velocity_rad_s': rates[
                'max_abs_angular_velocity_rad_s'],
            'moves': self.all_moves,
            'action_waypoints': self.spec['action_waypoints'],
            'action_labels': self.spec['action_labels'],
            'pre_treatment_descriptor_strict': (
                descriptor['scan_stamp'] <= treatment_start),
            'controller_properties': self.spec['controller_properties'],
        }
        self.write_fixed_outputs(result, scientific)
        with open(os.path.join(
                self.output_dir, 'pre_treatment_descriptor.json'), 'w') as stream:
            json.dump(descriptor, stream, indent=2, sort_keys=True)
            stream.write('\n')
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--spec', required=True)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args(rospy.myargv()[1:])
    with open(args.spec) as stream:
        spec = json.load(stream)
    rospy.init_node('context_disentangle_technical_capture', anonymous=False)
    capture = ContextDoseCapture(spec, args.output_dir)
    try:
        result = capture.run()
        print(json.dumps({
            'status': result['status'],
            'scientific_treatment_scan_count': result[
                'scientific_treatment_scan_count'],
            'actual_cumulative_yaw_rad': result['actual_cumulative_yaw_rad'],
            'completion_margin': result['completion_margin'],
        }, sort_keys=True))
        if result['status'] != 'SUCCEEDED':
            raise SystemExit(2)
    finally:
        capture.stop()


if __name__ == '__main__':
    main()
