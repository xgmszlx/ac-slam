#!/usr/bin/python3
"""Freeze v10 timestamp and target-region evidence from canonical v9 data."""

import argparse
import hashlib
import json
import math
from pathlib import Path


def load_json(path):
    with open(path) as stream:
        return json.load(stream)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def yaw_from_tum(row):
    qx, qy, qz, qw = row[4:8]
    return math.atan2(2.0 * (qw * qz + qx * qy),
                      1.0 - 2.0 * (qy * qy + qz * qz))


def load_tum(path):
    rows = []
    with open(path) as stream:
        for line in stream:
            if line.strip():
                values = [float(value) for value in line.split()]
                rows.append({'stamp': values[0], 'x': values[1],
                             'y': values[2], 'yaw': yaw_from_tum(values)})
    return rows


def exact_gt(rows, stamp, tolerance=1e-9):
    matches = [row for row in rows if abs(row['stamp'] - stamp) <= tolerance]
    if len(matches) != 1:
        raise ValueError('expected one GT row at {:.9f}; got {}'.format(
            stamp, len(matches)))
    return matches[0]


def target_region(canonical_dir):
    canonical_dir = Path(canonical_dir).resolve()
    frozen_path = canonical_dir / 'frozen_target.json'
    slam_path = canonical_dir / 'trajectory_slam.txt'
    gt_path = canonical_dir / 'trajectory_gt.txt'
    frozen = load_json(frozen_path)
    slam = load_tum(slam_path)
    gt = load_tum(gt_path)
    nodes = {int(node['id']): node for node in frozen['segment_nodes']}
    mappings = []
    for state_id in frozen['historical_scan_ids']:
        if state_id >= len(slam):
            raise ValueError('state id {} absent from SLAM trajectory'.format(
                state_id))
        slam_row = slam[state_id]
        node = nodes[state_id]
        karto_error = math.hypot(slam_row['x'] - float(node['x']),
                                 slam_row['y'] - float(node['y']))
        if karto_error > 1e-5:
            raise ValueError('state-id/SLAM-row identity failed for {}'.format(
                state_id))
        gt_row = exact_gt(gt, slam_row['stamp'])
        mappings.append({
            'state_id': state_id,
            'unique_id': int(node['unique_id']),
            'capture_stamp_s': slam_row['stamp'],
            'karto_map_pose': [float(node['x']), float(node['y']),
                               float(node['theta'])],
            'stage_gt_base_pose': [gt_row['x'], gt_row['y'], gt_row['yaw']],
            'karto_vs_trajectory_slam_position_error_m': karto_error,
        })
    return {
        'schema_version': 'v10_target_physical_region_v1',
        'derivation': ('state_id indexes canonical trajectory_slam rows; its '
                       'original capture timestamp is joined exactly to the '
                       'canonical Stage trajectory_gt timestamp'),
        'not_derived_from_nominal_waypoint': True,
        'target_id': frozen['target_id'],
        'target_scan_ids': list(frozen['historical_scan_ids']),
        'mappings': mappings,
        'sources': {
            'frozen_target': str(frozen_path),
            'trajectory_slam': str(slam_path),
            'trajectory_gt': str(gt_path),
            'frozen_target_sha256': sha256(frozen_path),
            'trajectory_slam_sha256': sha256(slam_path),
            'trajectory_gt_sha256': sha256(gt_path),
        },
        'identity_checks_passed': True,
    }


def timestamp_audit(root):
    root = Path(root).resolve()
    wrapper = root / 'dependencies/navigation_2d/nav2d_karto/src/MultiMapper.cpp'
    mapper = root / ('dependencies/navigation_2d/nav2d_karto/OpenKarto/source/'
                     'OpenMapper.cpp')
    sensor = root / ('dependencies/navigation_2d/nav2d_karto/OpenKarto/source/'
                     'OpenKarto/SensorData.h')
    wrapper_text = wrapper.read_text()
    mapper_text = mapper.read_text()
    checks = {
        'wrapper_constructs_scan_without_SetTime': (
            'return new karto::LocalizedRangeScan(robot, readings);' in
            wrapper_text and 'laserScan->SetTime' not in wrapper_text),
        'openmapper_never_reads_GetTime': 'GetTime(' not in mapper_text,
        'keyscan_gate_uses_pose_not_delta_t': (
            'HasMovedEnough(pScan, pLastScan)' in mapper_text and
            'squaredTravelDistance' in mapper_text and
            'deltaHeading' in mapper_text),
        'running_buffer_uses_size_and_pose_distance': (
            'm_RunningScans.Size() > m_RunningBufferMaximumSize' in mapper_text
            and 'm_RunningBufferMaximumDistance' in mapper_text),
        'loop_candidate_uses_scan_order_and_pose_distance': (
            'for (; rStartScanIndex < nScans; rStartScanIndex++)' in mapper_text
            and 'm_pLoopSearchMaximumDistance' in mapper_text),
        'time_field_exists_but_is_not_consumed': (
            'inline kt_int64s GetTime() const' in sensor.read_text()),
    }
    verdict = ('DETERMINISTIC_RETIMING_ACCEPTABLE'
               if all(checks.values()) else 'TIMESTAMP_DEPENDENCE_UNRESOLVED')
    return {
        'schema_version': 'v10_timestamp_source_audit_v1',
        'verdict': verdict,
        'scope': 'offline canonical-prefix replay and branch stitching',
        'checks': checks,
        'pipeline': [
            {'stage': 'ROS wrapper ingestion', 'numeric_timestamp_use': True,
             'role': 'TF lookup plus diagnostic/republished message stamps',
             'affects_offline_measurement_content': False},
            {'stage': 'SensorData construction', 'numeric_timestamp_use': False,
             'role': 'LocalizedRangeScan is constructed without SetTime'},
            {'stage': 'keyscan decision', 'numeric_timestamp_use': False,
             'role': 'translation and heading thresholds only'},
            {'stage': 'running scans', 'numeric_timestamp_use': False,
             'role': 'insertion order, maximum count, pose distance'},
            {'stage': 'sequential scan matcher',
             'numeric_timestamp_use': False,
             'role': 'scan geometry, search poses and correlation scores'},
            {'stage': 'near-chain and TryCloseLoop',
             'numeric_timestamp_use': False,
             'role': 'state-id order, graph adjacency, pose distance and scores'},
            {'stage': 'graph optimization', 'numeric_timestamp_use': False,
             'role': 'constraint measurements and covariance'},
        ],
        'interpretation': (
            'Retiming changes transport/TF query stamps but preserves ordered '
            'recorded poses and scans. No Karto decision path computes delta-t '
            'or reads SensorData::m_Time in this checkout.'),
        'sources': {
            str(wrapper.relative_to(root)): sha256(wrapper),
            str(mapper.relative_to(root)): sha256(mapper),
            str(sensor.relative_to(root)): sha256(sensor),
        },
    }


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--canonical-dir', required=True)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    output = Path(args.output_dir)
    audit = timestamp_audit(args.root)
    region = target_region(args.canonical_dir)
    write_json(output / 'timestamp_audit/timestamp_source_audit.json', audit)
    write_json(output / 'target_physical_region.json', region)
    print(json.dumps({'timestamp_verdict': audit['verdict'],
                      'target_mapping_count': len(region['mappings'])},
                     indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
