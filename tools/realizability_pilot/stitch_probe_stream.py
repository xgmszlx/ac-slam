#!/usr/bin/python3
"""Outcome-blind SE(2) and timestamp stitching for H + one probe stream."""

import argparse
import json
import math
from pathlib import Path

from common_prefix_signature import stream_hash


def wrap_angle(value):
    return math.atan2(math.sin(value), math.cos(value))


def align_pose(pose, source_initial, target_terminal):
    yaw = wrap_angle(float(target_terminal[2]) - float(source_initial[2]))
    cosine, sine = math.cos(yaw), math.sin(yaw)
    dx = float(pose[0]) - float(source_initial[0])
    dy = float(pose[1]) - float(source_initial[1])
    return [float(target_terminal[0]) + cosine * dx - sine * dy,
            float(target_terminal[1]) + sine * dx + cosine * dy,
            wrap_angle(float(pose[2]) + yaw)]


def median_period(records):
    gaps = sorted(float(right['stamp']) - float(left['stamp'])
                  for left, right in zip(records, records[1:])
                  if float(right['stamp']) > float(left['stamp']))
    return gaps[len(gaps) // 2] if gaps else 0.1


def load_records(path):
    with open(path) as stream:
        return [json.loads(line) for line in stream if line.strip()]


def stitch(prefix_path, probe_path, output_path):
    prefix = load_records(prefix_path)
    probe = load_records(probe_path)
    if not prefix or not probe:
        raise ValueError('prefix and probe streams must both be non-empty')
    prefix_terminal = [prefix[-1]['x'], prefix[-1]['y'], prefix[-1]['yaw']]
    probe_initial = [probe[0]['x'], probe[0]['y'], probe[0]['yaw']]
    period = median_period(prefix)
    first_new_stamp = float(prefix[-1]['stamp']) + period
    stamp_offset = first_new_stamp - float(probe[0]['stamp'])
    stitched_probe = []
    for original in probe:
        row = dict(original)
        row['x'], row['y'], row['yaw'] = align_pose(
            [original['x'], original['y'], original['yaw']],
            probe_initial, prefix_terminal)
        row['stamp'] = float(original['stamp']) + stamp_offset
        stitched_probe.append(row)
    combined = prefix + stitched_probe
    stamps = [float(row['stamp']) for row in combined]
    if any(right <= left for left, right in zip(stamps, stamps[1:])):
        raise ValueError('stitch produced a non-increasing timestamp sequence')
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Preserve H byte-for-byte. Re-serializing parsed JSON would be semantically
    # equal but would weaken the common-prefix identity evidence.
    with open(output_path, 'wb') as output_stream:
        with open(prefix_path, 'rb') as prefix_stream:
            prefix_bytes = prefix_stream.read()
        output_stream.write(prefix_bytes)
        if prefix_bytes and not prefix_bytes.endswith(b'\n'):
            output_stream.write(b'\n')
        for row in stitched_probe:
            output_stream.write((json.dumps(
                row, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8'))
    prefix_digest, prefix_count = stream_hash(prefix_path)
    combined_prefix_digest, checked_count = stream_hash(output_path, len(prefix))
    report = {
        'prefix_path': str(Path(prefix_path).resolve()),
        'probe_path': str(Path(probe_path).resolve()),
        'output_path': str(output_path.resolve()),
        'prefix_record_count': len(prefix),
        'probe_record_count': len(probe),
        'combined_record_count': len(combined),
        'prefix_hash': prefix_digest,
        'combined_prefix_hash': combined_prefix_digest,
        'combined_prefix_checked_records': checked_count,
        'prefix_byte_identical': prefix_digest == combined_prefix_digest,
        'prefix_terminal_odom_laser': prefix_terminal,
        'probe_initial_odom_laser': probe_initial,
        'se2_alignment_yaw_rad': wrap_angle(prefix_terminal[2] - probe_initial[2]),
        'timestamp_offset_s': stamp_offset,
        'prefix_median_period_s': period,
        'boundary_gap_s': stitched_probe[0]['stamp'] - prefix[-1]['stamp'],
        'timestamps_strictly_increasing': True,
        'alignment_inputs': 'prefix terminal odom and probe initial odom only',
    }
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--probe', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    report = stitch(args.prefix, args.probe, args.out)
    with open(args.report, 'w') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
