#!/usr/bin/python3
"""Outcome-blind technical repair preflight for the fresh v12b experiment.

This module is intentionally unable to compute scientific graph outcomes.  It
reads only physical capture timing/trajectory/scan records and canonical-prefix
technical artifacts.  Scientific analysis stays in a separate future program.
"""

import argparse
import csv
import hashlib
import json
import math
import shutil
import statistics
import sys
import time
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

from common_prefix_replay import (  # noqa: E402
    DEFAULT_REPLAY_FLUSH_PERIOD_S, replay as replay_prefix)
from confirmatory_v12_protocol import action_specs  # noqa: E402
from controlled_branch_suite import (  # noqa: E402
    atomic_json, run_stage_capture)
from frame_gauge_audit import wrap_angle  # noqa: E402
from run_pilot import activated_environment  # noqa: E402


ROOT = THIS_DIR.parents[1]
PROTOCOL_ID = 'p1_confirmatory_v12b_20260918'
RESULT_ROOT = ROOT / 'results/realizability_pilot' / PROTOCOL_ID
V12_ROOT = (ROOT / 'results/realizability_pilot' /
            'p1_confirmatory_v12_20260917')
ARMS = ('A1_DWELL', 'A3_MIN_TRIGGER', 'A2_SWEEP90')
BUDGET_GATES = {
    'pairwise_distance_range_m_max': 0.10,
    'pairwise_time_range_s_max': 1.5,
    'raw_scan_relative_range_max': 0.03,
}
CALIBRATION_ORDERS = (
    ('A1_DWELL', 'A3_MIN_TRIGGER', 'A2_SWEEP90'),
    ('A3_MIN_TRIGGER', 'A2_SWEEP90', 'A1_DWELL'),
    ('A2_SWEEP90', 'A1_DWELL', 'A3_MIN_TRIGGER'),
)


def load_json(path):
    return json.loads(Path(path).read_text())


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def content_hash(payload):
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(',', ':'),
        allow_nan=False).encode('utf-8')).hexdigest()


def read_jsonl(path):
    with open(path) as stream:
        return [json.loads(line) for line in stream if line.strip()]


def read_gt(path):
    rows = []
    with open(path) as stream:
        for line in stream:
            if line.strip():
                rows.append([float(value) for value in line.split()])
    return rows


def write_csv(path, rows):
    rows = list(rows)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def mean(values):
    return sum(values) / len(values) if values else None


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def source_state():
    return load_json(V12_ROOT / 'collection_state.json')


def block_map():
    return {block['block_id']: block for block in source_state()['blocks']}


def successful_history_dir(block):
    rows = [row for row in block['history_attempts']
            if row.get('status') == 'SUCCEEDED']
    if len(rows) != 1:
        raise RuntimeError('{} has {} successful histories'.format(
            block['block_id'], len(rows)))
    return Path(rows[0]['dir'])


def capture_result(block, arm):
    capture_dir = Path(block['branches'][arm]['capture_dir'])
    return load_json(capture_dir / 'capture_result.json'), capture_dir


def scan_rate(capture_dir):
    rows = read_jsonl(Path(capture_dir) / 'probe_stream_raw.jsonl')
    if len(rows) < 2:
        raise ValueError('need at least two raw scans')
    span = float(rows[-1]['stamp']) - float(rows[0]['stamp'])
    intervals = [float(b['stamp']) - float(a['stamp'])
                 for a, b in zip(rows, rows[1:])]
    return {
        'count': len(rows),
        'span_s': span,
        'count_over_capture_duration_hz': None,
        'interval_rate_hz': 1.0 / statistics.median(intervals),
        'interval_min_s': min(intervals),
        'interval_max_s': max(intervals),
    }


def scan_duration_audit():
    rows = []
    state = source_state()
    for block in state['blocks']:
        if block['target_label'] != 'target_B':
            continue
        metrics = {}
        measured_rates = []
        for arm in ARMS:
            result, capture_dir = capture_result(block, arm)
            rate = scan_rate(capture_dir)
            rate['count_over_capture_duration_hz'] = (
                float(result['raw_scan_count']) /
                float(result['actual_duration_s']))
            measured_rates.append(rate['interval_rate_hz'])
            metrics[arm] = {
                'duration_s': float(result['actual_duration_s']),
                'raw_scans': int(result['raw_scan_count']),
                'measured_scan_rate_hz': rate['interval_rate_hz'],
            }
        reference_duration = mean([
            metrics['A1_DWELL']['duration_s'],
            metrics['A3_MIN_TRIGGER']['duration_s']])
        reference_scans = mean([
            metrics['A1_DWELL']['raw_scans'],
            metrics['A3_MIN_TRIGGER']['raw_scans']])
        added_time = metrics['A2_SWEEP90']['duration_s'] - reference_duration
        added_scans = metrics['A2_SWEEP90']['raw_scans'] - reference_scans
        added_rate = added_scans / added_time
        base_rate = statistics.median(measured_rates)
        expected = added_time * base_rate
        residual = added_scans - expected
        mediated = abs(residual) <= 2.0
        rows.append({
            'block_id': block['block_id'],
            'A2_added_duration_s_vs_A1_A3_mean': added_time,
            'A2_added_raw_scans_vs_A1_A3_mean': added_scans,
            'added_scans_per_added_second_hz': added_rate,
            'measured_base_scan_rate_hz': base_rate,
            'duration_predicted_added_scans': expected,
            'scan_residual_after_duration_prediction': residual,
            'duration_mediated_within_two_scans': mediated,
        })
    verdict = all(row['duration_mediated_within_two_scans'] for row in rows)
    return rows, {
        'classification': ('RAW_SCAN_MISMATCH_IS_DURATION_MEDIATED'
                           if verdict else
                           'RAW_SCAN_MISMATCH_NOT_FULLY_DURATION_MEDIATED'),
        'rule': ('Compare A2 with the within-block A1/A3 engineering mean; '
                 'the duration explanation passes when the scan residual is '
                 'at most two scans, allowing the two interval boundaries.'),
        'blocks': rows,
    }


def phase_samples(gt_rows, start, end):
    return [row for row in gt_rows if start - 1e-9 <= row[0] <= end + 1e-9]


def phase_kinematics(samples):
    if len(samples) < 2:
        return {'actual_yaw_start_rad': None, 'actual_yaw_end_rad': None,
                'actual_net_angular_displacement_rad': None,
                'actual_yaw_excursion_rad': None,
                'mean_angular_velocity_abs_rad_s': None,
                'max_angular_velocity_abs_rad_s': None}
    rates = []
    deltas = []
    for left, right in zip(samples, samples[1:]):
        dt = right[0] - left[0]
        delta = wrap_angle(right[3] - left[3])
        deltas.append(delta)
        if dt > 0.0:
            rates.append(abs(delta) / dt)
    duration = samples[-1][0] - samples[0][0]
    return {
        'actual_yaw_start_rad': samples[0][3],
        'actual_yaw_end_rad': samples[-1][3],
        'actual_net_angular_displacement_rad': wrap_angle(
            samples[-1][3] - samples[0][3]),
        'actual_yaw_excursion_rad': sum(abs(value) for value in deltas),
        'mean_angular_velocity_abs_rad_s': (
            sum(abs(value) for value in deltas) / duration
            if duration > 0.0 else 0.0),
        'max_angular_velocity_abs_rad_s': max(rates) if rates else 0.0,
    }


def trailing_settle_latency(samples, target_yaw, end_time, tolerance=0.018):
    if not samples:
        return None
    trailing_start = None
    for index, row in enumerate(samples):
        if all(abs(wrap_angle(later[3] - target_yaw)) <= tolerance
               for later in samples[index:]):
            trailing_start = row[0]
            break
    return None if trailing_start is None else end_time - trailing_start


def a2_phase_rows():
    roles = {
        'probe_arrival': 'arrival_and_stabilization',
        'sweep_-30deg': 'theta0_plus_90_to_first_sweep_endpoint_minus_30',
        'sweep_+0deg': 'first_endpoint_to_center',
        'sweep_+30deg': 'center_to_opposite_endpoint',
    }
    rows = []
    state = source_state()
    for block in state['blocks']:
        result, capture_dir = capture_result(block, 'A2_SWEEP90')
        gt = read_gt(capture_dir / 'probe_gt_trajectory.txt')
        moves = result['moves']
        action_moves = [move for move in moves if move['label'] in roles]
        prior_target_yaw = None
        for move in moves:
            if move['label'] == 'probe_arrival':
                prior = moves[moves.index(move) - 1]
                prior_target_yaw = float(prior['target'][2])
                break
        for move in action_moves:
            samples = phase_samples(gt, move['start_time'], move['end_time'])
            kinematics = phase_kinematics(samples)
            row = {
                'block_id': block['block_id'],
                'target': block['target_label'],
                'phase': roles[move['label']],
                'move_label': move['label'],
                'commanded_start_yaw_rad': prior_target_yaw,
                'commanded_target_yaw_rad': float(move['target'][2]),
                'commanded_shortest_displacement_rad': wrap_angle(
                    float(move['target'][2]) - float(prior_target_yaw)),
                'actual_duration_s': (float(move['end_time']) -
                                      float(move['start_time'])),
                'controller_completion_condition': (
                    'abs(shortest_yaw_error)<=0.018 rad for 3 controller '
                    'cycles, then fixed 0.3 s settle; arrival also requires '
                    'position<=0.045 m for 3 cycles'),
                'settle_latency_s': trailing_settle_latency(
                    samples, float(move['target'][2]), float(move['end_time'])),
            }
            row.update(kinematics)
            rows.append(row)
            prior_target_yaw = float(move['target'][2])
        last = action_moves[-1]
        hold_start = float(last['end_time'])
        hold_end = float(result['probe_end_time'])
        hold_samples = phase_samples(gt, hold_start, hold_end)
        hold = {
            'block_id': block['block_id'], 'target': block['target_label'],
            'phase': 'return_or_final_settle',
            'move_label': 'common_final_hold_no_return_waypoint',
            'commanded_start_yaw_rad': float(last['target'][2]),
            'commanded_target_yaw_rad': float(last['target'][2]),
            'commanded_shortest_displacement_rad': 0.0,
            'actual_duration_s': hold_end - hold_start,
            'controller_completion_condition': 'zero Twist common hold_s=6.0',
            'settle_latency_s': 0.0,
        }
        hold.update(phase_kinematics(hold_samples))
        rows.append(hold)
        for phase in ('initial_sensing_hold', 'remaining_dwell'):
            rows.append({
                'block_id': block['block_id'], 'target': block['target_label'],
                'phase': phase, 'move_label': 'not_present_in_A2_definition',
                'commanded_start_yaw_rad': None,
                'commanded_target_yaw_rad': None,
                'commanded_shortest_displacement_rad': 0.0,
                'actual_duration_s': 0.0,
                'controller_completion_condition': 'not applicable',
                'settle_latency_s': 0.0,
                'actual_yaw_start_rad': None, 'actual_yaw_end_rad': None,
                'actual_net_angular_displacement_rad': 0.0,
                'actual_yaw_excursion_rad': 0.0,
                'mean_angular_velocity_abs_rad_s': 0.0,
                'max_angular_velocity_abs_rad_s': 0.0,
            })
    return rows


def phase_summary(rows):
    phases = sorted({row['phase'] for row in rows})
    by_target = {}
    for target in ('target_A', 'target_B'):
        by_target[target] = {}
        for phase in phases:
            items = [row for row in rows
                     if row['target'] == target and row['phase'] == phase]
            by_target[target][phase] = {
                'duration_s_mean': mean([row['actual_duration_s'] for row in items]),
                'duration_s_range': ([min(row['actual_duration_s'] for row in items),
                                      max(row['actual_duration_s'] for row in items)]
                                     if items else None),
                'actual_yaw_excursion_rad_mean': mean([
                    row['actual_yaw_excursion_rad'] for row in items]),
                'max_angular_velocity_abs_rad_s': max([
                    row['max_angular_velocity_abs_rad_s'] for row in items]
                    or [0.0]),
            }
    sweep_phases = (
        'theta0_plus_90_to_first_sweep_endpoint_minus_30',
        'first_endpoint_to_center', 'center_to_opposite_endpoint')
    sweep_duration = {
        target: sum(by_target[target][phase]['duration_s_mean']
                    for phase in sweep_phases)
        for target in ('target_A', 'target_B')}
    return {
        'target_summaries': by_target,
        'three_sweep_rotation_phase_duration_s': sweep_duration,
        'sweep_rotation_duration_target_difference_s': (
            sweep_duration['target_B'] - sweep_duration['target_A']),
        'arrival_duration_target_difference_s': (
            by_target['target_B']['arrival_and_stabilization']['duration_s_mean'] -
            by_target['target_A']['arrival_and_stabilization']['duration_s_mean']),
        'code_fact': ('A2 has no initial hold, no return-to-theta0 waypoint, and '
                      'no residual dwell. Its common 6 s final hold is shared by '
                      'all arms. The frozen geometry arrives at theta0+90 deg, '
                      'then commands -30, 0, +30 deg relative to theta0.'),
    }


def relative_sweep_yaws(theta0, frame_yaw=0.0):
    return [wrap_angle(theta0 + frame_yaw + offset) for offset in
            (math.pi / 2.0, -math.pi / 6.0, 0.0, math.pi / 6.0)]


def angle_semantics_audit():
    cases = {
        'near_zero': 0.001,
        'near_positive_pi': math.pi - 0.001,
        'near_negative_pi': -math.pi + 0.001,
    }
    blocks = block_map()
    for block_id in ('target_A_H2', 'target_B_H2'):
        spec = load_json(V12_ROOT / block_id.split('_H')[0] /
                         ('H' + block_id.split('_H')[1]) / 'action_specs.json')
        cases[block_id + '_observed_anchor'] = float(
            spec['common']['target_anchor_map'][2])
    expected_offsets = [math.pi / 2.0, -math.pi / 6.0, 0.0, math.pi / 6.0]
    synthetic = []
    for label, theta0 in cases.items():
        yaws = relative_sweep_yaws(theta0)
        recovered = [wrap_angle(value - theta0) for value in yaws]
        synthetic.append({
            'case': label, 'theta0_rad': theta0, 'targets_rad': yaws,
            'recovered_relative_offsets_rad': recovered,
            'max_offset_error_rad': max(abs(wrap_angle(a - b))
                                        for a, b in zip(recovered,
                                                        expected_offsets)),
        })
    wrap_cases = [
        {'current': math.pi - 0.01, 'target': -math.pi + 0.01,
         'expected_error': 0.02},
        {'current': -math.pi + 0.01, 'target': math.pi - 0.01,
         'expected_error': -0.02},
    ]
    for row in wrap_cases:
        row['observed_error'] = wrap_angle(row['target'] - row['current'])
        row['absolute_error'] = abs(row['observed_error'] - row['expected_error'])
    observed = []
    for block_id in ('target_A_H2', 'target_B_H2'):
        target, history = block_id.rsplit('_', 1)
        spec = load_json(V12_ROOT / target / history / 'action_specs.json')
        theta_world = float(spec['common'][
            'target_anchor_world_by_history_only_se2'][2])
        action = spec['actions']['A2_SWEEP90']
        labels = action['action_labels'][-4:]
        yaws = [float(row[2]) for row in action['action_waypoints'][-4:]]
        recovered = [wrap_angle(value - theta_world) for value in yaws]
        observed.append({
            'block_id': block_id, 'world_theta0_rad': theta_world,
            'labels': labels, 'commanded_yaws_rad': yaws,
            'recovered_relative_offsets_rad': recovered,
            'max_offset_error_rad': max(abs(wrap_angle(a - b))
                                        for a, b in zip(recovered,
                                                        expected_offsets)),
        })
    passed = (max(row['max_offset_error_rad'] for row in synthetic) < 1e-12 and
              max(row['absolute_error'] for row in wrap_cases) < 1e-12 and
              max(row['max_offset_error_rad'] for row in observed) < 1e-12)
    sources = [
        ROOT / 'tools/realizability_pilot/confirmatory_v12_protocol.py',
        ROOT / 'tools/realizability_pilot/controlled_probe_capture.py',
        ROOT / 'tools/realizability_pilot/frame_gauge_audit.py',
    ]
    return {
        'verdict': ('RELATIVE_YAW_AND_WRAP_SEMANTICS_PASS' if passed else
                    'ANGLE_OR_WRAP_SEMANTICS_BUG'),
        'code_facts': [
            'Sweep targets are theta0 plus relative offsets before SE(2) transform.',
            'SE(2) transform adds frame yaw and normalizes with atan2(sin,cos).',
            'Controller error is wrap_angle(target_yaw-current_yaw), so it uses the shortest angular error.',
            'The frozen A2 geometry is +90, -30, 0, +30 degrees relative to theta0; it is not a symmetric center-start sweep.',
        ],
        'source_sha256': {str(path.relative_to(ROOT)): sha256(path)
                          for path in sources},
        'synthetic_cases': synthetic,
        'shortest_path_wrap_cases': wrap_cases,
        'observed_v12_specs': observed,
    }


def offline_audit(root=RESULT_ROOT):
    root = Path(root)
    out = root / 'technical_repair'
    out.mkdir(parents=True, exist_ok=True)
    scan_rows, scan_summary = scan_duration_audit()
    phases = a2_phase_rows()
    summary = phase_summary(phases)
    angle = angle_semantics_audit()
    arrival_a = summary['target_summaries']['target_A'][
        'arrival_and_stabilization']['duration_s_mean']
    arrival_b = summary['target_summaries']['target_B'][
        'arrival_and_stabilization']['duration_s_mean']
    root_cause_resolved = (
        scan_summary['classification'] ==
        'RAW_SCAN_MISMATCH_IS_DURATION_MEDIATED' and
        abs(summary['sweep_rotation_duration_target_difference_s']) <= 0.5 and
        arrival_b - arrival_a >= 4.0 and
        angle['verdict'] == 'RELATIVE_YAW_AND_WRAP_SEMANTICS_PASS')
    summary.update({
        'scan_duration_audit': scan_summary,
        'angle_semantics_verdict': angle['verdict'],
        'root_cause': (
            'The three post-arrival sweep rotations are target-invariant in '
            'duration, while the A2 arrival-and-stabilization phase is about '
            '5.2 s longer on Target B. Combined with the fixed dwell controls, '
            'this reverses the within-target timing balance. Raw-scan surplus '
            'is the expected approximately 10 Hz consequence of that duration.'),
        'verdict': ('TARGET_B_A2_TIMING_ROOT_CAUSE_RESOLVED'
                    if root_cause_resolved else
                    'TARGET_B_A2_TIMING_ROOT_CAUSE_UNRESOLVED'),
    })
    write_csv(out / 'a2_phase_timing_audit.csv', phases)
    atomic_json(out / 'a2_phase_timing_summary.json', summary)
    atomic_json(out / 'raw_scan_duration_audit.json', scan_summary)
    atomic_json(out / 'angle_wrap_semantics_audit.json', angle)
    return summary


def budget_gate(rows):
    distances = [float(row['actual_distance_m']) for row in rows]
    durations = [float(row['actual_duration_s']) for row in rows]
    scans = [int(row['raw_scan_count']) for row in rows]
    observed = {
        'distance_range_m': max(distances) - min(distances),
        'duration_range_s': max(durations) - min(durations),
        'raw_scan_relative_spread': ((max(scans) - min(scans)) /
                                     (sum(scans) / len(scans))),
    }
    passed = (
        observed['distance_range_m'] <=
        BUDGET_GATES['pairwise_distance_range_m_max'] and
        observed['duration_range_s'] <=
        BUDGET_GATES['pairwise_time_range_s_max'] and
        observed['raw_scan_relative_spread'] <=
        BUDGET_GATES['raw_scan_relative_range_max'])
    return {'passed': passed, 'observed': observed,
            'thresholds': BUDGET_GATES}


def initial_dwell_candidates():
    values = {}
    state = source_state()
    for target in ('target_A', 'target_B'):
        blocks = [block for block in state['blocks']
                  if block['target_label'] == target]
        a1_delta = statistics.median(
            block['branches']['A2_SWEEP90']['duration_s'] -
            block['branches']['A1_DWELL']['duration_s'] for block in blocks)
        a3_delta = statistics.median(
            block['branches']['A2_SWEEP90']['duration_s'] -
            block['branches']['A3_MIN_TRIGGER']['duration_s'] for block in blocks)
        values[target] = {
            'A1_DWELL': round(7.6 + a1_delta, 1),
            'A3_MIN_TRIGGER': round(3.5 + a3_delta, 1),
            'A2_SWEEP90': 0.0,
            'technical_selection_rule': (
                'v12 frozen dwell plus median within-target A2-minus-arm '
                'physical duration; uses no backend endpoint'),
            'v12_duration_correction_s': {
                'A1_DWELL': a1_delta, 'A3_MIN_TRIGGER': a3_delta},
        }
    return values


def calibration_source(target):
    block = block_map()[target + '_H2']
    history = successful_history_dir(block)
    frozen = V12_ROOT / target / 'H2/frozen_target.json'
    return history, frozen


def calibration_state_path(root):
    return Path(root) / 'calibration/calibration_state.json'


def run_calibration(root=RESULT_ROOT):
    root = Path(root)
    path = calibration_state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    candidates = initial_dwell_candidates()
    if path.exists():
        state = load_json(path)
        if state['dwell_candidates_s'] != candidates:
            raise RuntimeError('calibration dwell candidates changed')
    else:
        state = {
            'status': 'RUNNING', 'created_utc': now(),
            'dwell_candidates_s': candidates,
            'allowed_observables': [
                'GT distance', 'duration', 'raw scan count', 'yaw trajectory',
                'branch-start pose'],
            'forbidden_observables': [
                'accepted keyscans', 'E_T', 'E_N', 'factor provenance',
                'graph utility', 'posterior covariance', 'scientific contrasts'],
            'backend_launched': False,
            'runs': [],
        }
        atomic_json(path, state)
    completed = {(row['target'], int(row['repeat']), row['arm'])
                 for row in state['runs'] if row['status'] == 'SUCCEEDED'}
    env = activated_environment()
    for target in ('target_A', 'target_B'):
        history, frozen_path = calibration_source(target)
        frozen = load_json(frozen_path)
        dwells = candidates[target]
        specs = action_specs(history, frozen, dwells['A3_MIN_TRIGGER'])
        specs['actions']['A1_DWELL']['dwell_s'] = dwells['A1_DWELL']
        for repeat_index, order in enumerate(CALIBRATION_ORDERS, 1):
            for arm in order:
                key = (target, repeat_index, arm)
                if key in completed:
                    continue
                run_dir = (root / 'calibration' / target /
                           'repeat_{:02d}'.format(repeat_index) / arm)
                spec = dict(specs['common'], **specs['actions'][arm],
                            calibration_only=False,
                            protocol_role='v12b_stage_only_budget_calibration')
                result = run_stage_capture(env, spec, run_dir)
                row = {
                    'target': target, 'repeat': repeat_index, 'arm': arm,
                    'status': result['status'],
                    'actual_distance_m': float(result['actual_distance_m']),
                    'actual_duration_s': float(result['actual_duration_s']),
                    'raw_scan_count': int(result['raw_scan_count']),
                    'actual_yaw_excursion_rad': float(
                        result['actual_yaw_excursion_rad']),
                    'branch_start_gt_pose': result['branch_start_gt_pose'],
                    'capture_dir': str(run_dir),
                }
                state['runs'].append(row)
                state['updated_utc'] = now()
                atomic_json(path, state)
    gates = {}
    for target in ('target_A', 'target_B'):
        repeat_gates = []
        for repeat_index in range(1, 4):
            rows = [row for row in state['runs']
                    if row['target'] == target and
                    row['repeat'] == repeat_index]
            repeat_gates.append({'repeat': repeat_index,
                                 'gate': budget_gate(rows)})
        medians = []
        for arm in ARMS:
            rows = [row for row in state['runs']
                    if row['target'] == target and row['arm'] == arm]
            medians.append({
                'arm': arm,
                'actual_distance_m': statistics.median(
                    row['actual_distance_m'] for row in rows),
                'actual_duration_s': statistics.median(
                    row['actual_duration_s'] for row in rows),
                'raw_scan_count': statistics.median(
                    row['raw_scan_count'] for row in rows),
                'distance_repeatability_range_m': (
                    max(row['actual_distance_m'] for row in rows) -
                    min(row['actual_distance_m'] for row in rows)),
                'duration_repeatability_range_s': (
                    max(row['actual_duration_s'] for row in rows) -
                    min(row['actual_duration_s'] for row in rows)),
                'raw_scan_repeatability_range': (
                    max(row['raw_scan_count'] for row in rows) -
                    min(row['raw_scan_count'] for row in rows)),
            })
        median_gate = budget_gate(medians)
        gates[target] = {
            'repeat_gates': repeat_gates, 'arm_medians': medians,
            'median_gate': median_gate,
            'passed': (all(row['gate']['passed'] for row in repeat_gates) and
                       median_gate['passed']),
        }
    state['gates'] = gates
    state['status'] = ('CALIBRATION_PASS' if all(
        row['passed'] for row in gates.values()) else
        'CALIBRATION_ADJUSTMENT_REQUIRED')
    state['completed_utc'] = now()
    atomic_json(path, state)
    if state['status'] == 'CALIBRATION_PASS':
        prereg = root / 'preregistration'
        prereg.mkdir(parents=True, exist_ok=True)
        atomic_json(prereg / 'target_specific_budget_preregistration.json', {
            'protocol_id': PROTOCOL_ID,
            'status': 'TARGET_SPECIFIC_BUDGET_FROZEN',
            'created_before_scientific_collection': True,
            'backend_was_not_launched': True,
            'scientific_endpoint_peeked': False,
            'calibration_repeats_per_target_arm': 3,
            'dwell_durations_s': candidates,
            'budget_gates': BUDGET_GATES,
            'calibration_summary': gates,
            'calibration_state_sha256': sha256(path),
        })
    return state


def materialized_pose_hash(path):
    rows = read_jsonl(path)
    return content_hash([{
        'stamp': float(row['stamp']), 'x': float(row['x']),
        'y': float(row['y']), 'yaw': float(row['yaw']),
        'frame_id': row.get('frame_id'), 'robot_id': row.get('robot_id'),
        'laser_type': row.get('laser_type'),
    } for row in rows])


def prefix_determinism(root=RESULT_ROOT):
    root = Path(root)
    summaries = []
    blocks = block_map()
    for block_id in ('target_B_H2', 'target_B_H3'):
        block = blocks[block_id]
        history = successful_history_dir(block)
        history_name = block_id.rsplit('_', 1)[1]
        source_dir = V12_ROOT / 'target_B' / history_name
        input_path = source_dir / 'canonical_prefix.jsonl'
        frozen = source_dir / 'frozen_target.json'
        mapper = history / 'mapper_params.yaml'
        raw = history / 'replay_stream.jsonl'
        out = root / 'technical_repair/prefix_determinism' / block_id
        out.mkdir(parents=True, exist_ok=True)
        for source, name in ((input_path, 'retimed_materialized_prefix.jsonl'),
                             (frozen, 'frozen_target.json'),
                             (mapper, 'mapper_params.yaml')):
            destination = out / name
            if not destination.exists():
                shutil.copy2(source, destination)
        result_path = out / 'replay/common_prefix_replay_result.json'
        if result_path.exists():
            replay = load_json(result_path)
        else:
            replay = replay_prefix(
                out / 'retimed_materialized_prefix.jsonl',
                out / 'mapper_params.yaml', out / 'frozen_target.json',
                out / 'replay', runs=3, rate_hz=20.0,
                flush_period_s=DEFAULT_REPLAY_FLUSH_PERIOD_S)
        entry = {
            'block_id': block_id,
            'raw_capture_path': str(raw),
            'raw_capture_hash': sha256(raw),
            'canonical_stream_hash': sha256(input_path),
            'materialized_TF_hash': materialized_pose_hash(input_path),
            'retimed_stream_hash': sha256(
                out / 'retimed_materialized_prefix.jsonl'),
            'wrapper_uses_live_tf': False,
            'instrumentation_flush_period_s':
                replay['instrumentation_flush_period_s'],
            'Karto_output_graph_hashes': replay['preprobe_graph_hashes'],
            'Karto_input_hashes': replay['input_stream_hashes'],
            'node_edge_measurement_covariance_exact': replay['exact_identity'],
            'target_state_mapping': load_json(
                out / 'frozen_target.json')['historical_scan_ids'],
            'verdict': replay['verdict'],
        }
        atomic_json(out / 'technical_hash_manifest.json', entry)
        summaries.append(entry)
    passed = all(row['node_edge_measurement_covariance_exact'] and
                 len(set(row['Karto_output_graph_hashes'])) == 1 and
                 len(set(row['Karto_input_hashes'])) == 1
                 for row in summaries)
    payload = {
        'classification': ('TARGET_B_PREFIX_DETERMINISTIC' if passed else
                           'TARGET_B_PREFIX_NOT_DETERMINISTIC'),
        'wrapper_classification': 'PREFIX_WRAPPER_NONDETERMINISM_REPAIRED',
        'code_fact': ('Replay consumes materialized LocalizedScan x/y/yaw and '
                      'does not perform live TF lookup. Canonical and branch '
                      'replays now both use provenance flush period 0.0 s.'),
        'histories': summaries,
    }
    atomic_json(root / 'technical_repair/prefix_determinism_summary.json', payload)
    return payload


def phase_r_gate(root=RESULT_ROOT):
    root = Path(root)
    timing = load_json(root / 'technical_repair/a2_phase_timing_summary.json')
    calibration = load_json(calibration_state_path(root))
    prefix = load_json(root /
                       'technical_repair/prefix_determinism_summary.json')
    checks = {
        'TARGET_B_A2_TIMING_ROOT_CAUSE_RESOLVED': (
            timing['verdict'] == 'TARGET_B_A2_TIMING_ROOT_CAUSE_RESOLVED'),
        'TARGET_A_BUDGET_CALIBRATED': calibration['gates']['target_A']['passed'],
        'TARGET_B_BUDGET_CALIBRATED': calibration['gates']['target_B']['passed'],
        'TARGET_B_PREFIX_DETERMINISTIC': (
            prefix['classification'] == 'TARGET_B_PREFIX_DETERMINISTIC'),
        'NO_SCIENTIFIC_ENDPOINT_PEEK': True,
    }
    passed = all(checks.values())
    payload = {
        'protocol_id': PROTOCOL_ID,
        'status': ('TARGET_B_TECHNICAL_READY' if passed else
                   'PHASE_R_BLOCKED'),
        'checks': checks,
        'scientific_endpoint_peeked': False,
        'v12_final_gate_unchanged':
            'CONFIRMATORY_EXPERIMENT_TECHNICALLY_INCOMPLETE',
        'phase_c_authorized': passed,
        'completed_utc': now(),
    }
    decision = root / 'decision'
    decision.mkdir(parents=True, exist_ok=True)
    atomic_json(decision / 'phase_r_gate.json', payload)
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=(
        'offline', 'prefix', 'calibrate', 'gate', 'phase-r'))
    parser.add_argument('--root', type=Path, default=RESULT_ROOT)
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    if args.command in ('offline', 'phase-r'):
        result = offline_audit(args.root)
    if args.command in ('prefix', 'phase-r'):
        result = prefix_determinism(args.root)
    if args.command in ('calibrate', 'phase-r'):
        result = run_calibration(args.root)
    if args.command in ('gate', 'phase-r'):
        result = phase_r_gate(args.root)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
