#!/usr/bin/python3
"""Create a deterministic monotonic-time view of a recorded replay stream.

Some legacy ``/karto_out`` messages carry a zero LaserScan header stamp.  The
record order is still well defined.  For stream stitching, assign a fixed
period in that existing order without changing poses, ranges, or metadata.
"""

import argparse
import json
from pathlib import Path

from common_prefix_signature import stream_hash


def normalize(input_path, output_path, period_s=0.1, start_s=0.0):
    with open(input_path) as stream:
        records = [json.loads(line) for line in stream if line.strip()]
    if not records:
        raise ValueError('input stream is empty')
    old_stamps = [float(row['stamp']) for row in records]
    violations = sum(right <= left
                     for left, right in zip(old_stamps, old_stamps[1:]))
    normalized = []
    for index, original in enumerate(records):
        row = dict(original)
        row['stamp'] = float(start_s) + index * float(period_s)
        normalized.append(row)
    new_stamps = [row['stamp'] for row in normalized]
    if any(right <= left for left, right in zip(new_stamps, new_stamps[1:])):
        raise ValueError('normalization failed to make timestamps increasing')
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as stream:
        for row in normalized:
            stream.write(json.dumps(row, sort_keys=True,
                                    separators=(',', ':')) + '\n')
    source_hash, source_count = stream_hash(input_path)
    output_hash, output_count = stream_hash(output_path)
    return {
        'policy': 'fixed period in original record order',
        'outcome_blind': True,
        'fields_changed': ['stamp'],
        'source_path': str(Path(input_path).resolve()),
        'output_path': str(output_path.resolve()),
        'source_hash': source_hash,
        'output_hash': output_hash,
        'source_record_count': source_count,
        'output_record_count': output_count,
        'source_nonincreasing_adjacent_count': violations,
        'start_s': float(start_s),
        'period_s': float(period_s),
        'timestamps_strictly_increasing': True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--period-s', type=float, default=0.1)
    parser.add_argument('--start-s', type=float, default=0.0)
    args = parser.parse_args()
    report = normalize(args.input, args.out, args.period_s, args.start_s)
    with open(args.report, 'w') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
