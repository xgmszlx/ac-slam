#!/usr/bin/python3
"""Resumable v10 budget-only calibration and fresh A0/A1'/A2 capture."""

import argparse
import copy
import csv
import hashlib
import json
import math
from pathlib import Path

from controlled_branch_suite import (atomic_json, load_json, pose_error,
                                     run_stage_capture)
from run_pilot import activated_environment


BRANCHES = ('A0_baseline', 'A1_dwell', 'A2_sweep90')
CALIBRATION_REPEATS = 3
DISTANCE_TOLERANCE_M = 0.15
TIME_TOLERANCE_S = 2.0
RAW_RELATIVE_TOLERANCE = 0.05


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def median(values):
    ordered = sorted(float(value) for value in values)
    return ordered[len(ordered) // 2]


def relative_difference(left, right):
    denominator = (abs(float(left)) + abs(float(right))) / 2.0
    return abs(float(left) - float(right)) / denominator if denominator else 0.0


def capture_metrics(result):
    return {'distance_m': float(result['actual_distance_m']),
            'duration_s': float(result['actual_duration_s']),
            'raw_scan_count': int(result['raw_scan_count'])}


def resolve_run_dir(base):
    """Return an existing success or a new explicitly numbered attempt."""
    base = Path(base)
    candidates = [base] + sorted(base.parent.glob(base.name + '_attempt_*'))
    for candidate in candidates:
        result = candidate / 'capture_result.json'
        if result.is_file() and load_json(result).get('status') == 'SUCCEEDED':
            return candidate, True
    if not base.exists():
        return base, False
    index = 2
    while (base.parent / '{}_attempt_{:02d}'.format(base.name, index)).exists():
        index += 1
    return base.parent / '{}_attempt_{:02d}'.format(base.name, index), False


def load_frozen_specs(v9_specs_path):
    v9_specs_path = Path(v9_specs_path).resolve()
    source = load_json(v9_specs_path)
    actions = source['actions']
    a0 = copy.deepcopy(actions['A0_baseline'])
    a2 = copy.deepcopy(actions['A2_sweep90'])
    dwell = copy.deepcopy(a0)
    dwell['action_id'] = 'n1_a1_time_matched_dwell'
    dwell['semantic_note'] = (
        'A0 waypoint geometry followed by zero-Twist static dwell at the '
        'baseline arrival pose and heading; no deliberate yaw command')
    payload = {
        'source_v9_specs': str(v9_specs_path),
        'source_v9_specs_sha256': file_sha256(v9_specs_path),
        'common': copy.deepcopy(source['common']),
        'actions': {'A0_baseline': a0, 'A1_dwell': dwell,
                    'A2_sweep90': a2},
    }
    validate_dwell_action(payload['actions']['A0_baseline'],
                          payload['actions']['A1_dwell'])
    return payload


def validate_dwell_action(baseline, dwell):
    if dwell['action_waypoints'] != baseline['action_waypoints']:
        raise ValueError('dwell must preserve baseline waypoint geometry')
    if dwell['action_labels'] != baseline['action_labels']:
        raise ValueError('dwell must preserve baseline waypoint labels')
    if any('sweep' in str(label).lower() for label in dwell['action_labels']):
        raise ValueError('dwell action contains a yaw-sweep label')
    return True


def calibration_plan(frozen, v9_root, output_dir):
    v9_root = Path(v9_root).resolve()
    a0_path = v9_root / 'branches/A0_baseline/raw_attempt_02/capture_result.json'
    a2_path = v9_root / 'branches/A2_sweep90/raw/capture_result.json'
    a0 = load_json(a0_path)
    a2 = load_json(a2_path)
    initial = float(a2['actual_duration_s']) - float(a0['actual_duration_s'])
    if initial <= 0.0:
        raise ValueError('non-positive initial dwell estimate')
    return {
        'protocol': 'v10_dwell_budget_calibration_v1',
        'outcome_blind': True,
        'backend_launched': False,
        'science_fields_forbidden': [
            'constraints', 'utility', 'posterior', 'accepted_keyscan_count'],
        'calibration_observables': [
            'GT distance', 'elapsed sensing time', 'raw LaserScan count',
            'start-pose repeatability', 'static-dwell execution'],
        'initial_dwell_duration_s': initial,
        'selection_rule': (
            'run three fixed-duration dwell captures; freeze the initial '
            'duration only if median A1 dwell versus frozen v9 A2 meets all '
            'preregistered budget gates and repeatability ranges do not exceed '
            'the same absolute/relative tolerances'),
        'repeat_count': CALIBRATION_REPEATS,
        'budget_definition': {
            'includes': ['GT distance', 'elapsed sensing time',
                         'raw LaserScan exposure'],
            'excludes': ['accepted Karto keyscans'],
        },
        'gates': {'distance_difference_m_max': DISTANCE_TOLERANCE_M,
                  'time_difference_s_max': TIME_TOLERANCE_S,
                  'raw_scan_relative_difference_max': RAW_RELATIVE_TOLERANCE},
        'reference': {'arm': 'v9 A2_sweep90 engineering estimate only',
                      'metrics': capture_metrics(a2),
                      'path': str(a2_path), 'sha256': file_sha256(a2_path)},
        'baseline': {'arm': 'v9 A0_baseline engineering estimate only',
                     'metrics': capture_metrics(a0),
                     'path': str(a0_path), 'sha256': file_sha256(a0_path)},
        'frozen_geometry_source_sha256': frozen['source_v9_specs_sha256'],
        'created_before_calibration_capture': True,
        'output_dir': str(Path(output_dir).resolve()),
    }


def write_calibration_csv(path, rows):
    fields = ['run', 'capture_dir', 'dwell_duration_commanded_s', 'distance_m',
              'duration_s', 'raw_scan_count', 'dwell_distance_m',
              'dwell_yaw_excursion_rad', 'dwell_raw_scan_count',
              'distance_difference_vs_reference_m',
              'time_difference_vs_reference_s',
              'raw_relative_difference_vs_reference']
    with open(path, 'w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run_calibration(frozen, v9_root, output_dir):
    output_dir = Path(output_dir).resolve()
    prereg_dir = output_dir / 'preregistration'
    prereg_dir.mkdir(parents=True, exist_ok=True)
    plan_path = prereg_dir / 'dwell_calibration_plan.json'
    if plan_path.exists():
        plan = load_json(plan_path)
    else:
        plan = calibration_plan(frozen, v9_root, output_dir)
        atomic_json(plan_path, plan)
    duration = float(plan['initial_dwell_duration_s'])
    reference = plan['reference']['metrics']
    tolerance_path = Path(v9_root) / 'preregistration/branch_start_tolerance.json'
    start_tolerance = load_json(tolerance_path)['branch_start_tolerance']
    terminal = frozen['common']['canonical_terminal_gt_pose']
    env = activated_environment()
    rows = []
    for index in range(1, CALIBRATION_REPEATS + 1):
        run_dir, complete = resolve_run_dir(
            output_dir / 'calibration' / 'run_{:02d}'.format(index))
        spec = dict(frozen['common'], **frozen['actions']['A1_dwell'],
                    calibration_only=False, dwell_s=duration,
                    protocol_role='budget_only_dwell_calibration')
        result = (load_json(run_dir / 'capture_result.json') if complete else
                  run_stage_capture(env, spec, run_dir))
        start_error = pose_error(result['branch_start_gt_pose'], terminal)
        if (start_error[0] > start_tolerance['position_m'] or
                start_error[1] > start_tolerance['heading_rad']):
            raise RuntimeError('calibration branch-start gate failed in {}'.format(
                run_dir))
        metrics = capture_metrics(result)
        dwell = result.get('dwell') or {}
        rows.append({
            'run': index, 'capture_dir': str(run_dir),
            'dwell_duration_commanded_s': duration, **metrics,
            'dwell_distance_m': dwell.get('distance_m'),
            'dwell_yaw_excursion_rad': dwell.get('yaw_excursion_rad'),
            'dwell_raw_scan_count': dwell.get('raw_scan_count'),
            'distance_difference_vs_reference_m': abs(
                metrics['distance_m'] - reference['distance_m']),
            'time_difference_vs_reference_s': abs(
                metrics['duration_s'] - reference['duration_s']),
            'raw_relative_difference_vs_reference': relative_difference(
                metrics['raw_scan_count'], reference['raw_scan_count']),
        })
        write_calibration_csv(output_dir / 'dwell_budget_calibration.csv', rows)
    medians = {key: median(row[key] for row in rows)
               for key in ('distance_m', 'duration_s', 'raw_scan_count')}
    repeatability = {
        'distance_range_m': (max(row['distance_m'] for row in rows) -
                             min(row['distance_m'] for row in rows)),
        'duration_range_s': (max(row['duration_s'] for row in rows) -
                             min(row['duration_s'] for row in rows)),
        'raw_scan_relative_range': ((max(row['raw_scan_count'] for row in rows) -
                                     min(row['raw_scan_count'] for row in rows)) /
                                    median(row['raw_scan_count'] for row in rows)),
    }
    differences = {
        'distance_difference_m': abs(
            medians['distance_m'] - reference['distance_m']),
        'time_difference_s': abs(
            medians['duration_s'] - reference['duration_s']),
        'raw_scan_relative_difference': relative_difference(
            medians['raw_scan_count'], reference['raw_scan_count']),
    }
    static_gate = all((row['dwell_distance_m'] is not None and
                       row['dwell_distance_m'] <= 0.02 and
                       row['dwell_yaw_excursion_rad'] <= 0.02)
                      for row in rows)
    budget_gate = (
        differences['distance_difference_m'] <= DISTANCE_TOLERANCE_M and
        differences['time_difference_s'] <= TIME_TOLERANCE_S and
        differences['raw_scan_relative_difference'] <= RAW_RELATIVE_TOLERANCE)
    repeatability_gate = (
        repeatability['distance_range_m'] <= DISTANCE_TOLERANCE_M and
        repeatability['duration_range_s'] <= TIME_TOLERANCE_S and
        repeatability['raw_scan_relative_range'] <= RAW_RELATIVE_TOLERANCE)
    passed = static_gate and budget_gate and repeatability_gate
    decision = {
        'protocol': plan['protocol'], 'status': 'CALIBRATION_PASS' if passed
        else 'CALIBRATION_FAIL', 'selected_dwell_duration_s': duration,
        'reference_metrics': reference, 'calibration_medians': medians,
        'differences': differences, 'repeatability': repeatability,
        'static_dwell_execution_pass': static_gate,
        'budget_gate_pass': budget_gate,
        'repeatability_gate_pass': repeatability_gate,
        'accepted_keyscan_excluded_from_gate': True,
        'science_outcomes_inspected': False,
        'runs': rows,
    }
    atomic_json(output_dir / 'dwell_budget_calibration_decision.json', decision)
    if passed:
        prereg = {
            'protocol': 'v10_time_matched_dwell_control_v1',
            'frozen_after_budget_only_calibration': True,
            'selected_dwell_duration_s': duration,
            'budget_definition': plan['budget_definition'],
            'gates': plan['gates'],
            'branch_start_tolerance': start_tolerance,
            'common': frozen['common'], 'actions': frozen['actions'],
            'canonical_graph_hash':
                'd697659a6ca52d529a14171c3b383fb2b83696d108874edfbf579f570b29fe88',
            'target_scan_ids': [13, 14, 15, 16, 17],
            'science_outcome_gate': 'unavailable until fresh-batch budget pass',
        }
        atomic_json(output_dir / 'v10_dwell_preregistration.json', prereg)
    return decision


def run_branches(frozen, v9_root, output_dir):
    output_dir = Path(output_dir).resolve()
    prereg_path = output_dir / 'v10_dwell_preregistration.json'
    if not prereg_path.is_file():
        raise RuntimeError('v10 preregistration absent; calibration did not pass')
    prereg = load_json(prereg_path)
    tolerance = prereg['branch_start_tolerance']
    terminal = frozen['common']['canonical_terminal_gt_pose']
    env = activated_environment()
    results = []
    for branch in BRANCHES:
        run_dir, complete = resolve_run_dir(output_dir / 'branches' / branch / 'raw')
        dwell_s = (float(prereg['selected_dwell_duration_s'])
                   if branch == 'A1_dwell' else 0.0)
        spec = dict(frozen['common'], **frozen['actions'][branch],
                    calibration_only=False, dwell_s=dwell_s,
                    protocol_role='fresh_v10_science_batch')
        result = (load_json(run_dir / 'capture_result.json') if complete else
                  run_stage_capture(env, spec, run_dir))
        deviation = pose_error(result['branch_start_gt_pose'], terminal)
        passed = (deviation[0] <= tolerance['position_m'] and
                  deviation[1] <= tolerance['heading_rad'])
        result.update({'branch_name': branch,
                       'branch_start_deviation_position_m': deviation[0],
                       'branch_start_deviation_heading_rad': deviation[1],
                       'branch_start_gate_passed': passed})
        atomic_json(run_dir / 'capture_result.json', result)
        results.append({'branch': branch, 'raw_dir': str(run_dir),
                        'capture': result})
        if not passed:
            raise RuntimeError('{} branch-start identity gate failed'.format(
                branch))
    summary = {'status': 'CAPTURE_SUCCEEDED', 'branches': results,
               'all_branch_starts_passed': all(
                   row['capture']['branch_start_gate_passed'] for row in results)}
    (output_dir / 'analysis').mkdir(parents=True, exist_ok=True)
    atomic_json(output_dir / 'analysis/fresh_capture_summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--v9-specs', required=True)
    parser.add_argument('--v9-root', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--phase', choices=('calibration', 'branches', 'all'),
                        default='all')
    args = parser.parse_args()
    frozen = load_frozen_specs(args.v9_specs)
    outputs = {}
    if args.phase in ('calibration', 'all'):
        outputs['calibration'] = run_calibration(
            frozen, args.v9_root, args.output_dir)
        if outputs['calibration']['status'] != 'CALIBRATION_PASS':
            print(json.dumps(outputs, indent=2, sort_keys=True))
            return
    if args.phase in ('branches', 'all'):
        outputs['branches'] = run_branches(
            frozen, args.v9_root, args.output_dir)
    print(json.dumps(outputs, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
