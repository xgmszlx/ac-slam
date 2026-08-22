#!/usr/bin/python3
"""Verify Phase 2C Karto loop-diagnostics JSONL against known outcomes.

For a positive-control trial, checks that:
  - the diagnostics file parses,
  - every record has the required fields,
  - the number of structured ACCEPTED records equals the number of accepted
    "Add one Loop closure" callbacks observed during the explicit revisit
    (from positive_control.json), and
  - the no-chain reject reasons are consistent with the recorded counters.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


REQUIRED_FIELDS = [
    'event', 'wall_time_ms', 'run_id', 'scan_id', 'scan_unique_id',
    'scan_pose_x', 'scan_pose_y', 'scan_yaw', 'loop_search_triggered',
    'historical_scans_considered', 'historical_scans_in_distance',
    'historical_scans_filtered_near_linked', 'candidate_chain_count',
    'chain_attempt_index', 'chain_id', 'chain_size', 'scan_ids',
    'min_scan_index_gap', 'max_scan_index_gap',
    'coarse_attempted', 'coarse_response', 'coarse_variance_x',
    'coarse_variance_y', 'coarse_pass', 'coarse_reject_reason',
    'fine_attempted', 'fine_response', 'fine_pass',
    'accepted', 'reject_stage', 'reject_reason',
]


def load_jsonl(path):
    records = []
    with open(path) as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise RuntimeError('invalid JSON at line {}: {}'.format(lineno, exc))
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--diagnostics', required=True, type=Path)
    parser.add_argument('--positive-control-json', type=Path, default=None)
    args = parser.parse_args()

    if not args.diagnostics.is_file():
        print('FAIL: diagnostics file not found: {}'.format(args.diagnostics))
        sys.exit(1)

    records = load_jsonl(args.diagnostics)
    if not records:
        print('FAIL: diagnostics file is empty')
        sys.exit(1)

    missing_fields = Counter()
    events = Counter()
    accepted_records = []
    no_chain_reasons = Counter()
    for record in records:
        events[record.get('event')] += 1
        for field in REQUIRED_FIELDS:
            if field not in record:
                missing_fields[field] += 1
        if record.get('event') == 'loop_search_chain':
            if record.get('accepted') is True:
                accepted_records.append(record)
        if record.get('event') == 'loop_search_no_chain':
            no_chain_reasons[record.get('reject_reason')] += 1

    print('=== Phase 2C diagnostics validation ===')
    print('file: {}'.format(args.diagnostics))
    print('total records: {}'.format(len(records)))
    print('event counts: {}'.format(dict(events)))
    print('missing field occurrences: {}'.format(dict(missing_fields) or 'none'))
    print('no-chain reject reasons: {}'.format(dict(no_chain_reasons) or 'none'))
    print('structured ACCEPTED records: {}'.format(len(accepted_records)))
    for rec in accepted_records:
        print('  ACCEPTED scan_id={} chain_size={} coarse_response={:.4f} '
              'fine_response={:.4f}'.format(
                  rec['scan_id'], rec['chain_size'],
                  rec['coarse_response'], rec['fine_response']))

    if missing_fields:
        print('FAIL: records missing required fields')
        sys.exit(1)

    if args.positive_control_json is not None:
        pc = json.loads(args.positive_control_json.read_text())
        callback_count = len(pc.get('karto_accepted_loop_events_during_revisit', []))
        pc_status = pc.get('positive_control_success')
        print('positive control accepted callbacks (revisit): {}'.format(callback_count))
        print('positive control success: {}'.format(pc_status))
        if len(accepted_records) != callback_count:
            print('FAIL: structured ACCEPTED ({}) != accepted callback count ({})'.format(
                len(accepted_records), callback_count))
            sys.exit(1)
        print('PASS: structured ACCEPTED matches accepted callback count')
    else:
        print('(no positive-control reference provided; structural checks only)')

    # Internal consistency of no-chain records: reason must match counters.
    for rec in records:
        if rec.get('event') != 'loop_search_no_chain':
            continue
        in_dist = rec['historical_scans_in_distance']
        near = rec['historical_scans_filtered_near_linked']
        reason = rec['reject_reason']
        if in_dist == 0:
            expected = 'NO_SPATIAL_CANDIDATE'
        elif in_dist - near == 0:
            expected = 'ALL_CANDIDATES_NEAR_LINKED'
        else:
            expected = 'CHAIN_TOO_SHORT'
        if reason != expected:
            print('FAIL: no-chain reason mismatch scan_id={}: {} != {}'.format(
                rec['scan_id'], reason, expected))
            sys.exit(1)
    print('PASS: no-chain reject reasons are internally consistent')
    print('=== validation PASS ===')


if __name__ == '__main__':
    main()
