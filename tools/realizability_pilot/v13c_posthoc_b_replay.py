#!/usr/bin/python3
"""Outcome-blind forensics, cropping, and replay for the Target-B diagnostic."""

import argparse
import csv
import json
import math
import os
import time
from pathlib import Path

import numpy as np

from controlled_branch_suite import atomic_json
from stitch_probe_stream import stitch
from v13_prefix_equivalence import compare_graphs
from v13_unified_replay import unified_replay
from v13c_posthoc_b_protocol import (
    ARMS, BASE_COMMIT, BLOCKS, CROP_STAMP_EPSILON_S, FORENSIC_RULE,
    PREREGISTRATION_PATH, RATE_HZ, REPLAY_MODES, RESULT_ROOT, ROOT,
    SOURCE_ROOT, TAIL_TRANSLATION_TOLERANCE_M, TAIL_YAW_TOLERANCE_RAD,
    V12B_ROOT, git_head, load_json, prefix_reference, sha256,
    source_block_dir, source_capture_dir, verify_source_immutable,
    write_preregistration,
)


FINAL_MOVE_LABEL = {
    'A1_DWELL': 'probe_arrival',
    'A3_MIN_TRIGGER': 'min_trigger_return',
    'A2_SWEEP90': 'sweep_+30deg',
}


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def wrap_angle(value):
    return math.atan2(math.sin(value), math.cos(value))


def read_jsonl(path):
    with open(path) as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as stream:
        for row in rows:
            stream.write(json.dumps(
                row, sort_keys=True, separators=(',', ':')) + '\n')


def load_gt(path):
    rows = []
    with open(path) as stream:
        for line in stream:
            if line.strip():
                rows.append([float(value) for value in line.split()])
    return rows


def path_length(rows):
    return sum(math.hypot(right[1] - left[1], right[2] - left[2])
               for left, right in zip(rows, rows[1:]))


def yaw_excursion(rows):
    return sum(abs(wrap_angle(right[3] - left[3]))
               for left, right in zip(rows, rows[1:]))


def _move(result, label):
    matches = [row for row in result['moves'] if row['label'] == label]
    if len(matches) != 1:
        raise RuntimeError('expected one move labelled {}'.format(label))
    return matches[0]


def decompose_capture(capture_result_path, source_kind, group_id):
    capture_result_path = Path(capture_result_path)
    result = load_json(capture_result_path)
    spec = load_json(capture_result_path.with_name('capture_spec.json'))
    arm = result['action_id']
    arrival = _move(result, 'probe_arrival')
    final_move = _move(result, FINAL_MOVE_LABEL[arm])
    before = arrival['before']
    target = arrival['target']
    arrival_bearing = math.atan2(
        float(target[1]) - float(before[1]),
        float(target[0]) - float(before[0]))
    target_yaw = float(target[2])
    dwell = result.get('dwell')
    dwell_duration = float(dwell['actual_duration_s']) if dwell else 0.0
    final_static_start = (float(dwell['end_time']) if dwell else
                          float(final_move['end_time']))
    final_hold_duration = float(result['probe_end_time']) - final_static_start
    treatment_start = float(arrival['start_time'])
    action_motion_duration = float(final_move['end_time']) - treatment_start
    common_pre_duration = treatment_start - float(result['probe_start_time'])
    reconstructed = (common_pre_duration + action_motion_duration +
                     dwell_duration + final_hold_duration)
    raw = read_jsonl(capture_result_path.with_name('probe_stream_raw.jsonl'))
    row = {
        'source_kind': source_kind,
        'group_id': group_id,
        'arm': arm,
        'capture_result_path': str(capture_result_path.relative_to(ROOT)),
        'anchor_yaw_rad': float(
            spec['target_anchor_world_by_history_only_se2'][2]),
        'common_pre_treatment_approach_duration_s': common_pre_duration,
        'probe_arrival_duration_s': (
            float(arrival['end_time']) - float(arrival['start_time'])),
        'arrival_target_yaw_rad': target_yaw,
        'arrival_bearing_rad': arrival_bearing,
        'final_yaw_rotation_demand_rad': abs(wrap_angle(
            target_yaw - arrival_bearing)),
        'A3_peak_duration_s': None,
        'A3_return_duration_s': None,
        'A2_arrival_duration_s': None,
        'A2_sweep_minus30_duration_s': None,
        'A2_sweep_zero_duration_s': None,
        'A2_sweep_plus30_duration_s': None,
        'action_motion_duration_s': action_motion_duration,
        'residual_dwell_duration_s': dwell_duration,
        'frozen_dwell_s': float(spec.get('dwell_s', 0.0)),
        'final_common_hold_duration_s': final_hold_duration,
        'total_treatment_package_duration_s': (
            float(result['probe_end_time']) - treatment_start),
        'full_probe_duration_s': float(result['actual_duration_s']),
        'timing_decomposition_residual_s': (
            float(result['actual_duration_s']) - reconstructed),
        'raw_scan_count': int(result['raw_scan_count']),
        'scans_during_final_static_hold': sum(
            float(scan['stamp']) + CROP_STAMP_EPSILON_S >= final_static_start
            for scan in raw),
        'final_static_hold_start_s': final_static_start,
        'probe_end_time_s': float(result['probe_end_time']),
    }
    if arm == 'A3_MIN_TRIGGER':
        peak = _move(result, 'min_trigger_peak')
        ret = _move(result, 'min_trigger_return')
        row['A3_peak_duration_s'] = (
            float(peak['end_time']) - float(peak['start_time']))
        row['A3_return_duration_s'] = (
            float(ret['end_time']) - float(ret['start_time']))
    if arm == 'A2_SWEEP90':
        row['A2_arrival_duration_s'] = row['probe_arrival_duration_s']
        for label, field in (
                ('sweep_-30deg', 'A2_sweep_minus30_duration_s'),
                ('sweep_+0deg', 'A2_sweep_zero_duration_s'),
                ('sweep_+30deg', 'A2_sweep_plus30_duration_s')):
            move = _move(result, label)
            row[field] = float(move['end_time']) - float(move['start_time'])
    return row


def forensic_rows():
    groups = []
    for repeat in range(1, 4):
        directory = (V12B_ROOT / 'calibration/target_B' /
                     'repeat_{:02d}'.format(repeat))
        groups.append(('CALIBRATION', 'calibration_repeat_{}'.format(repeat),
                       directory))
    for block_id in BLOCKS:
        groups.append(('V13C', block_id, source_block_dir(block_id)))
    output = []
    for source_kind, group_id, directory in groups:
        rows = []
        for arm in ARMS:
            capture = (directory / arm / 'capture_result.json'
                       if source_kind == 'CALIBRATION' else
                       directory / arm / 'raw_attempt_01/capture_result.json')
            rows.append(decompose_capture(capture, source_kind, group_id))
        by_arm = {row['arm']: row for row in rows}
        a2_motion = by_arm['A2_SWEEP90']['action_motion_duration_s']
        durations = [row['full_probe_duration_s'] for row in rows]
        scans = [row['raw_scan_count'] for row in rows]
        for row in rows:
            if row['arm'] == 'A2_SWEEP90':
                required = 0.0
            else:
                required = a2_motion - row['action_motion_duration_s']
            row['required_dwell_s'] = required
            row['frozen_dwell_error_s'] = row['frozen_dwell_s'] - required
            row['observed_full_duration_spread_s'] = max(durations) - min(
                durations)
            row['observed_scan_relative_spread'] = (
                (max(scans) - min(scans)) /
                (sum(scans) / float(len(scans))))
        output.extend(rows)
    return output


def forensic_summary(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row['group_id'], {})[row['arm']] = row
    calibration = [grouped['calibration_repeat_{}'.format(value)]
                   for value in range(1, 4)]
    calibration_median_demand = {
        arm: float(np.median([
            group[arm]['final_yaw_rotation_demand_rad']
            for group in calibration])) for arm in ARMS}
    group_rows = {}
    for group_id, arms in grouped.items():
        errors = [abs(arms[arm]['frozen_dwell_error_s'])
                  for arm in ('A1_DWELL', 'A3_MIN_TRIGGER')]
        shifts = {arm: abs(
            arms[arm]['final_yaw_rotation_demand_rad'] -
            calibration_median_demand[arm]) for arm in ARMS}
        group_rows[group_id] = {
            'max_abs_frozen_dwell_error_s': max(errors),
            'rotation_demand_shift_from_calibration_median_rad': shifts,
            'min_rotation_demand_shift_rad': min(shifts.values()),
            'max_rotation_demand_shift_rad': max(shifts.values()),
            'max_abs_timing_decomposition_residual_s': max(
                abs(row['timing_decomposition_residual_s'])
                for row in arms.values()),
            'observed_full_duration_spread_s': next(
                iter(arms.values()))['observed_full_duration_spread_s'],
            'observed_scan_relative_spread': next(
                iter(arms.values()))['observed_scan_relative_spread'],
        }
    calibration_errors_ok = all(
        group_rows['calibration_repeat_{}'.format(value)][
            'max_abs_frozen_dwell_error_s'] <=
        FORENSIC_RULE['calibration_and_H4_max_abs_dwell_error_s']
        for value in range(1, 4))
    h4_error_ok = (group_rows['B-H4']['max_abs_frozen_dwell_error_s'] <=
                   FORENSIC_RULE[
                       'calibration_and_H4_max_abs_dwell_error_s'])
    failed_error_shift = all(
        group_rows[block]['max_abs_frozen_dwell_error_s'] >=
        FORENSIC_RULE['failed_block_min_max_abs_dwell_error_s']
        for block in ('B-H1', 'B-H2', 'B-H3'))
    failed_geometry_shift = all(
        group_rows[block]['min_rotation_demand_shift_rad'] >=
        FORENSIC_RULE['failed_block_min_rotation_demand_shift_rad']
        for block in ('B-H1', 'B-H2', 'B-H3'))
    h4_geometry_close = (
        group_rows['B-H4']['max_rotation_demand_shift_rad'] <=
        FORENSIC_RULE['H4_max_rotation_demand_shift_rad'])
    timing_exact = all(
        row['max_abs_timing_decomposition_residual_s'] <=
        FORENSIC_RULE['timing_decomposition_residual_max_s']
        for row in group_rows.values())
    evidence = {
        'calibration_dwell_errors_within_envelope': calibration_errors_ok,
        'B_H4_dwell_errors_within_calibration_envelope': h4_error_ok,
        'B_H1_H3_dwell_errors_outside_transport_threshold':
            failed_error_shift,
        'B_H1_H3_rotation_geometry_shifted': failed_geometry_shift,
        'B_H4_rotation_geometry_close_to_calibration': h4_geometry_close,
        'timing_decomposition_closes': timing_exact,
    }
    if all(evidence.values()):
        conclusion = 'GEOMETRY_DEPENDENT_CALIBRATION_SUPPORTED'
    elif (not failed_error_shift and not failed_geometry_shift and
          calibration_errors_ok):
        conclusion = 'GEOMETRY_DEPENDENT_CALIBRATION_NOT_SUPPORTED'
    else:
        conclusion = 'FORENSIC_INCONCLUSIVE'
    return {
        'status': 'ANALYZED_WITHOUT_BACKEND_ENDPOINTS',
        'decision_rule': FORENSIC_RULE,
        'calibration_median_rotation_demand_rad':
            calibration_median_demand,
        'groups': group_rows,
        'evidence': evidence,
        'conclusion': conclusion,
    }


def write_forensics(root=RESULT_ROOT):
    root = Path(root)
    rows = forensic_rows()
    summary = forensic_summary(rows)
    directory = root / 'forensics'
    directory.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with open(directory / 'budget_geometry_forensics.csv', 'w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    atomic_json(directory / 'budget_geometry_forensics.json', {
        'rows': rows, 'summary': summary})
    return summary


def final_static_hold_start(capture):
    arm = capture['action_id']
    if arm in ('A1_DWELL', 'A3_MIN_TRIGGER'):
        if not capture.get('dwell'):
            raise RuntimeError('{} is missing dwell metadata'.format(arm))
        return float(capture['dwell']['end_time'])
    return float(_move(capture, 'sweep_+30deg')['end_time'])


def crop_records(records, n_match, static_start, gt_rows):
    if n_match <= 0 or n_match > len(records):
        raise ValueError('invalid matched scan count')
    kept = records[:n_match]
    removed = records[n_match:]
    if removed and any(
            float(row['stamp']) + CROP_STAMP_EPSILON_S < static_start
            for row in removed):
        raise ValueError('EXPOSURE_MATCH_NOT_IDENTIFIABLE: action-phase deletion')
    first_removed = float(removed[0]['stamp']) if removed else None
    tail_gt = ([row for row in gt_rows if row[0] +
                CROP_STAMP_EPSILON_S >= first_removed]
               if first_removed is not None else [])
    tail_distance = path_length(tail_gt)
    tail_yaw = yaw_excursion(tail_gt)
    valid = (tail_distance <= TAIL_TRANSLATION_TOLERANCE_M and
             tail_yaw <= TAIL_YAW_TOLERANCE_RAD)
    if not valid:
        raise ValueError(
            'EXPOSURE_MATCH_NOT_IDENTIFIABLE: removed tail moved')
    return kept, {
        'original_scans': len(records),
        'matched_scans': len(kept),
        'removed_scans': len(removed),
        'crop_cutoff_timestamp_s': float(kept[-1]['stamp']),
        'first_removed_timestamp_s': first_removed,
        'final_action_completion_timestamp_s': static_start,
        'removed_tail_gt_path_length_m': tail_distance,
        'removed_tail_gt_yaw_excursion_rad': tail_yaw,
        'cropping_valid': True,
        'operation': 'TAIL_TRUNCATION_ONLY',
        'record_order_preserved': kept == records[:n_match],
    }


def prepare_crops(root=RESULT_ROOT):
    root = Path(root)
    reports = []
    for block_id in BLOCKS:
        sources = {}
        for arm in ARMS:
            directory = source_capture_dir(block_id, arm)
            sources[arm] = {
                'directory': directory,
                'capture': load_json(directory / 'capture_result.json'),
                'records': read_jsonl(directory / 'probe_stream_raw.jsonl'),
                'gt': load_gt(directory / 'probe_gt_trajectory.txt'),
            }
        n_match = min(len(row['records']) for row in sources.values())
        for arm in ARMS:
            source = sources[arm]
            static_start = final_static_hold_start(source['capture'])
            output, report = crop_records(
                source['records'], n_match, static_start, source['gt'])
            directory = root / 'cropping' / block_id / arm
            output_path = directory / 'probe_stream_matched.jsonl'
            write_jsonl(output_path, output)
            report.update({
                'block_id': block_id,
                'arm': arm,
                'N_match': n_match,
                'source_raw_path': str(
                    (source['directory'] / 'probe_stream_raw.jsonl').relative_to(ROOT)),
                'source_raw_sha256': sha256(
                    source['directory'] / 'probe_stream_raw.jsonl'),
                'matched_path': str(output_path.relative_to(ROOT)),
                'matched_sha256': sha256(output_path),
            })
            atomic_json(directory / 'crop_report.json', report)
            reports.append(report)
    atomic_json(root / 'cropping/crop_summary.json', {
        'status': ('EXPOSURE_MATCH_VALID' if all(
            row['cropping_valid'] for row in reports)
                   else 'EXPOSURE_MATCH_NOT_IDENTIFIABLE'),
        'reports': reports,
    })
    return reports


def replay_directory(root, mode, block_id, arm):
    return Path(root) / 'replays' / mode / block_id / arm


def _probe_path(root, mode, block_id, arm):
    if mode == 'FULL':
        return source_capture_dir(block_id, arm) / 'probe_stream_raw.jsonl'
    return (Path(root) / 'cropping' / block_id / arm /
            'probe_stream_matched.jsonl')


def _verify_completed_replay(directory):
    required = [directory / name for name in (
        'graph_pre.json', 'graph_final.json', 'unified_replay_result.json')]
    if not all(path.is_file() for path in required):
        return None
    result = load_json(directory / 'unified_replay_result.json')
    if not (result.get('prefix_gate_passed') and result.get('suffix_published')):
        return None
    return result


def replay_one(root, mode, block_id, arm):
    root = Path(root)
    reference = prefix_reference(block_id)
    directory = replay_directory(root, mode, block_id, arm)
    completed = _verify_completed_replay(directory)
    if completed:
        return completed
    if directory.exists() and any(directory.iterdir()):
        raise RuntimeError('refusing to overwrite partial replay {}'.format(
            directory))
    directory.mkdir(parents=True, exist_ok=True)
    # Keep the stitched replay input distinct from the canonical output copy
    # produced by unified_replay().  Passing its destination as its source
    # makes shutil.copy2 reject the replay before ROS starts.
    combined = directory / 'stitched_input.jsonl'
    report = stitch(
        ROOT / reference['canonical_prefix_path'],
        _probe_path(root, mode, block_id, arm), combined)
    atomic_json(directory / 'stitch_report.json', report)
    if (not report['prefix_byte_identical'] or
            report['prefix_hash'] != reference['canonical_prefix_sha256']):
        raise RuntimeError('canonical prefix changed during stitch')
    result = unified_replay(
        ROOT / reference['canonical_prefix_path'],
        ROOT / reference['mapper_params_path'], directory,
        rate_hz=RATE_HZ, combined_path=combined,
        target_ids=reference['local_five_target_state_ids'],
        prefix_reference_path=ROOT /
        reference['prefix_reference_graph_path'])
    if not (result['prefix_gate_passed'] and result['suffix_published']):
        raise RuntimeError('unified replay did not pass technical gate')
    return result


def b_h4_reproducibility(root):
    root = Path(root)
    target_ids = prefix_reference('B-H4')['local_five_target_state_ids']
    comparisons = {}
    for arm in ARMS:
        observed_path = replay_directory(
            root, 'FULL', 'B-H4', arm) / 'graph_final.json'
        original_path = (source_block_dir('B-H4') / arm /
                         'replay_attempt_01/graph_final.json')
        comparison = compare_graphs(
            load_json(original_path), load_json(observed_path),
            target_ids=target_ids)
        comparisons[arm] = {
            'original_graph_path': str(original_path.relative_to(ROOT)),
            'diagnostic_graph_path': str(observed_path.relative_to(ROOT)),
            'comparison': comparison,
            'exact': bool(comparison['structural']['exact'] and
                          comparison['numerical']['exact']),
        }
    passed = all(row['exact'] for row in comparisons.values())
    payload = {
        'status': ('B_H4_REPRODUCIBILITY_EXACT' if passed else
                   'REPLAY_REPRODUCIBILITY_FAILURE'),
        'passed': passed,
        'arms': comparisons,
    }
    atomic_json(root / 'technical/B_H4_reproducibility_gate.json', payload)
    return payload


def run_replays(root=RESULT_ROOT):
    root = Path(root)
    prereg = load_json(PREREGISTRATION_PATH)
    source_check = verify_source_immutable(prereg['source_capture_hashes'])
    if not source_check['passed']:
        raise RuntimeError('original v13-C artifacts changed')
    crop_summary = load_json(root / 'cropping/crop_summary.json')
    if crop_summary['status'] != 'EXPOSURE_MATCH_VALID':
        raise RuntimeError('exposure matching is not identifiable')
    state = {
        'status': 'RUNNING',
        'protocol_sha256': sha256(PREREGISTRATION_PATH),
        'started_utc': now(),
        'branches': [],
    }
    atomic_json(root / 'collection/replay_state.json', state)

    # All three B-H4 arms are mandatory reproducibility sentinels and run first.
    for arm in ARMS:
        result = replay_one(root, 'FULL', 'B-H4', arm)
        state['branches'].append({
            'mode': 'FULL', 'block_id': 'B-H4', 'arm': arm,
            'status': result['status']})
        atomic_json(root / 'collection/replay_state.json', state)
    reproducibility = b_h4_reproducibility(root)
    if not reproducibility['passed']:
        state['status'] = 'REPLAY_REPRODUCIBILITY_FAILURE'
        atomic_json(root / 'collection/replay_state.json', state)
        raise RuntimeError('B-H4 exact reproducibility gate failed')

    for mode in REPLAY_MODES:
        for block_id in BLOCKS:
            for arm in ARMS:
                if mode == 'FULL' and block_id == 'B-H4':
                    continue
                result = replay_one(root, mode, block_id, arm)
                state['branches'].append({
                    'mode': mode, 'block_id': block_id, 'arm': arm,
                    'status': result['status']})
                atomic_json(root / 'collection/replay_state.json', state)
    state.update(status='REPLAY_COLLECTION_LOCKED', completed_utc=now())
    state['source_immutability_after'] = verify_source_immutable(
        prereg['source_capture_hashes'])
    if not state['source_immutability_after']['passed']:
        raise RuntimeError('original v13-C artifacts changed during replay')
    atomic_json(root / 'collection/replay_state.json', state)
    atomic_json(root / 'REPLAY_COLLECTION_LOCKED.json', {
        'status': state['status'],
        'protocol_sha256': state['protocol_sha256'],
        'completed_branches': len(state['branches']),
        'expected_branches': 24,
        'B_H4_reproducibility': reproducibility['status'],
        'analysis_not_yet_run': True,
        'locked_utc': now(),
    })
    return state


def prepare(root=RESULT_ROOT):
    if git_head() != BASE_COMMIT:
        raise RuntimeError('unexpected git base before diagnostic freeze')
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    summary = write_forensics(root)
    crops = prepare_crops(root)
    prereg = write_preregistration(
        root / 'preregistration/posthoc_diagnostic_preregistration.json')
    return {
        'status': 'POSTHOC_DIAGNOSTIC_PREREGISTERED',
        'forensic_conclusion': summary['conclusion'],
        'exposure_match_valid': all(row['cropping_valid'] for row in crops),
        'preregistration_sha256': sha256(
            root / 'preregistration/posthoc_diagnostic_preregistration.json'),
        'code_bundle_sha256': prereg['code_bundle_sha256'],
        'analysis_sha256': prereg['analysis_sha256'],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('prepare', 'run', 'status'))
    parser.add_argument('--root', type=Path, default=RESULT_ROOT)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.root)
    elif args.command == 'run':
        result = run_replays(args.root)
    else:
        state = args.root / 'collection/replay_state.json'
        result = load_json(state) if state.exists() else {'status': 'NOT_STARTED'}
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
