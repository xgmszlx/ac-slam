#!/usr/bin/python3
"""Integrity and protocol verification for a continuous revisit suite.

Checks the recording chain before any scientific number is read:

* suite bookkeeping: planned vs terminal episodes, attempts, failure reasons;
* per-episode file set and the frozen identity gate;
* scan stream continuity (monotone stamps, no index gaps, odometry present);
* phase partitions (history / return / action / tail) are non-empty, disjoint
  and cover the stream, and the action phase holds exactly the frozen budget;
* snapshot boundaries are marked satisfied and their node counts are monotone;
* executed action geometry: the arm ordering of the measured rotation, L+/L-
  symmetry, and the return-to-theta0 property;
* the return leg reproduces the historical observation pose within the frozen
  ground-truth tolerance;
* the information metric is computable and responds to a synthetic constraint
  on the target states (measurement sensitivity).

Writes ``verification.json`` next to the suite and prints a compact report.
"""

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

import analysis as an  # noqa: E402
import protocol as cr  # noqa: E402

REQUIRED_FILES = (
    'episode_spec.json', 'manifest.json', 'episode_result.json',
    'frozen_target.json', 'resolved_route.json', 'scan_stream.jsonl',
    'gt_stream.jsonl', 'keyscan_stream.jsonl', 'loop_events.jsonl',
    'graph_before_return.json', 'graph_arrival.json', 'graph_action_done.json',
    'graph_final.json', 'monitor.csv', 'driver.log', 'roslaunch.log',
)
#: The executed action rotation must exceed the previous arm's by this margin
#: (radians) and L+/L- must agree within this margin.
ARM_ORDER_MARGIN_RAD = 0.2
DIRECTION_SYMMETRY_MARGIN_RAD = 0.6


def check_episode(run_dir, spec):
    run_dir = Path(run_dir)
    problems, notes = [], {}
    for name in REQUIRED_FILES:
        if not (run_dir / name).is_file():
            problems.append('missing {}'.format(name))
    if problems:
        return problems, notes

    result = an.load_json(run_dir / 'episode_result.json')
    frozen = an.load_json(run_dir / 'frozen_target.json')
    spec_file = an.load_json(run_dir / 'episode_spec.json')
    if result.get('status') != 'SUCCEEDED':
        problems.append('episode_result status {}'.format(result.get('status')))
    if not frozen.get('passed'):
        problems.append('frozen identity gate failed: {}'.format(
            sorted(key for key, ok in frozen['checks'].items() if not ok)))
    notes['action_id'] = spec_file['action_id']
    notes['place_id'] = spec_file['place_id']

    # ---- scan stream -----------------------------------------------------
    scans = an.jsonl(run_dir / 'scan_stream.jsonl')
    if not scans:
        problems.append('empty scan stream')
        return problems, notes
    indices = [record['index'] for record in scans]
    if indices != list(range(len(scans))):
        problems.append('scan indices are not contiguous')
    stamps = [record['stamp'] for record in scans]
    if any(second < first for first, second in zip(stamps, stamps[1:])):
        problems.append('scan stamps are not monotone')
    missing_odom = sum(1 for record in scans if record['odom_base'] is None)
    notes['scan_count'] = len(scans)
    notes['scans_missing_odom'] = missing_odom
    notes['scan_dt_median_s'] = float(np.median([
        second - first for first, second in zip(stamps, stamps[1:])]))
    if missing_odom > 0.02 * len(scans):
        problems.append('more than 2% of scans lack an odometric pose ({})'.format(
            missing_odom))

    # ---- phases ----------------------------------------------------------
    bounds = an.phase_bounds(result)
    marks = result['phase_scan_marks']
    ordered = [bounds[phase] for phase in an.PHASE_ORDER]
    if not (0 <= marks['history_end_scan'] <= marks['return_start_scan']
            <= int(result['action_start_scan_index'])):
        problems.append('phase marks are not ordered')
    for phase, window in bounds.items():
        records = an.slice_records(scans, window)
        notes['{}_frames'.format(phase)] = len(records)
        if not records:
            problems.append('phase {} has no frames'.format(phase))
    action_frames = notes.get('action_frames', 0)
    notes['action_budget'] = int(result['action_frames_target'])
    if action_frames < int(result['action_frames_target']):
        problems.append('action phase holds {} of {} frames'.format(
            action_frames, result['action_frames_target']))
    covered = set()
    for window in ordered:
        start, end = window
        indices_in = {record['index'] for record in an.slice_records(scans, window)}
        if covered & indices_in:
            problems.append('phase windows overlap')
        covered |= indices_in
    if len(covered) != len(scans):
        notes['frames_outside_phases'] = len(scans) - len(covered)

    # ---- snapshots -------------------------------------------------------
    node_counts = []
    for name, filename in an.SNAPSHOT_FILES.items():
        snapshot = an.load_json(run_dir / filename)
        boundary = snapshot.get('graph_boundary', {})
        if not boundary.get('satisfied'):
            problems.append('{} boundary not satisfied'.format(name))
        node_counts.append(len(snapshot['graph']['nodes']))
        edges = snapshot['graph']['edges']
        unparsed = sum(1 for edge in edges if an.covariance_terms(edge) is None)
        if unparsed:
            problems.append('{} has {} edges without covariances'.format(name,
                                                                         unparsed))
    notes['snapshot_node_counts'] = node_counts
    if any(second < first for first, second in zip(node_counts, node_counts[1:])):
        problems.append('graph node count is not monotone across snapshots')
    notes['missing_from_graph'] = result['phase_boundaries']['G_final'][
        'boundary'].get('keyscan_publications')

    # ---- action geometry -------------------------------------------------
    action_records = an.slice_records(scans, bounds['action'])
    poses = [record['odom_base'] for record in action_records
             if record['odom_base'] is not None]
    rotation = an.ge.cumulative_rotation(poses)
    path = an.ge.path_length(poses)
    notes['measured_rotation_rad'] = rotation
    notes['measured_path_m'] = path
    notes['planned_rotation_rad'] = float(
        spec_file['planned_cumulative_rotation_rad'])
    if poses:
        entry_yaw = poses[0][2]
        deflection = max(abs(an.ge.wrap_angle(pose[2] - entry_yaw))
                         for pose in poses)
        final_offset = abs(an.ge.wrap_angle(poses[-1][2] - entry_yaw))
        notes['max_deflection_rad'] = deflection
        notes['final_heading_offset_rad'] = final_offset
        if final_offset > float(spec_file['goal_heading_tolerance_rad']):
            problems.append('action did not return to theta0 ({:.3f} rad)'.format(
                final_offset))
    if spec['action_id'] == 'S0' and rotation > 0.1:
        problems.append('static arm rotated {:.3f} rad'.format(rotation))

    # ---- return leg ------------------------------------------------------
    return_moves = [move for move in result['moves']
                    if move['label'].startswith('return_to')]
    if not return_moves:
        problems.append('no return move recorded')
    else:
        move = return_moves[-1]
        notes['return_gt_error_m'] = move['gt_position_error_m']
        notes['return_gt_error_rad'] = move['gt_heading_error_rad']
        if not move['reached']:
            problems.append('return move did not satisfy both checks')
        if move['gt_position_error_m'] > float(spec_file['gt_position_tolerance_m']):
            problems.append('return position error {:.3f} m'.format(
                move['gt_position_error_m']))
        if move['gt_heading_error_rad'] > float(spec_file['gt_heading_tolerance_rad']):
            problems.append('return heading error {:.3f} rad'.format(
                move['gt_heading_error_rad']))

    # ---- metric ----------------------------------------------------------
    try:
        episode = an.analyse_episode(run_dir)
        notes['J_T'] = episode['J_T']
        notes['action_gain'] = episode.get('action_gain')
        notes['return_gain'] = episode.get('return_gain')
        notes['odom_gt_residual_mean_m'] = episode.get('odom_gt_residual_mean_m')
        sensitivity = an.measurement_sensitivity([episode])
        if sensitivity and 'added_edge_J_T_gain' in sensitivity[0]:
            notes['sensitivity_J_T_gain'] = sensitivity[0]['added_edge_J_T_gain']
            if sensitivity[0]['added_edge_J_T_gain'] <= 0.0:
                problems.append('measurement sensitivity is not positive')
        else:
            problems.append('measurement sensitivity could not be computed')
    except Exception as exc:
        problems.append('analysis failed: {}: {}'.format(type(exc).__name__, exc))
    return problems, notes


def verify_suite(suite_dir):
    suite_dir = Path(suite_dir)
    state = an.load_json(suite_dir / 'suite_state.json')
    verification = {
        'suite_dir': str(suite_dir),
        'planned': len(state['episodes']),
        'status': state['status'],
        'episodes': [],
    }
    counts = {}
    arms = {}
    for episode in state['episodes']:
        counts[episode['status']] = counts.get(episode['status'], 0) + 1
        run_dir = an.latest_run_dir(suite_dir, episode)
        record = {'episode_id': episode['episode_id'],
                  'suite_status': episode['status'],
                  'attempts': len(episode['attempts'])}
        if run_dir is None:
            record['problems'] = ['no successful attempt']
        else:
            problems, notes = check_episode(run_dir, episode['spec'])
            record['problems'] = problems
            record.update(notes)
            record['run_dir'] = str(run_dir)
            if not problems:
                arms.setdefault((episode['spec']['place_id'],
                                 episode['spec']['action_id']), []).append(notes)
        verification['episodes'].append(record)
    verification['status_counts'] = counts
    verification['failed_episodes'] = [
        {'episode_id': episode['episode_id'],
         'reasons': [attempt.get('reason') for attempt in episode['attempts']]}
        for episode in state['episodes'] if episode['status'] == 'FAILED']
    # ---- cross-episode protocol checks ----------------------------------
    ordering = []
    for key in sorted({key[0] for key in arms}):
        arm_rotations = {action: arms.get((key, action)) for action in cr.ACTION_IDS}
        means = {action: (float(np.mean([entry['measured_rotation_rad']
                                         for entry in values]))
                          if values else None)
                 for action, values in arm_rotations.items()}
        ordering.append({'place_id': key, 'rotation_mean_rad': means})
        if all(means.get(action) is not None for action in cr.ACTION_IDS):
            if means['S0'] + ARM_ORDER_MARGIN_RAD > means['S1']:
                verification.setdefault('protocol_problems', []).append(
                    '{}: S0 rotation not below S1'.format(key))
            if means['S1'] + ARM_ORDER_MARGIN_RAD > means['L+']:
                verification.setdefault('protocol_problems', []).append(
                    '{}: S1 rotation not below L+'.format(key))
            for action in ('L+', 'L-'):
                if means[action] < math.pi / 2:
                    verification.setdefault('protocol_problems', []).append(
                        '{}: {} rotation below pi/2'.format(key, action))
            if abs(means['L+'] - means['L-']) > DIRECTION_SYMMETRY_MARGIN_RAD:
                verification.setdefault('protocol_problems', []).append(
                    '{}: L+ and L- rotations differ by more than {:.1f} rad'.format(
                        key, DIRECTION_SYMMETRY_MARGIN_RAD))
    verification['rotation_ordering'] = ordering
    return verification


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('suite_dir')
    parser.add_argument('--output', default='verification.json')
    args = parser.parse_args()
    suite_dir = Path(args.suite_dir)
    verification = verify_suite(suite_dir)
    path = suite_dir / args.output
    path.write_text(json.dumps(verification, indent=1, sort_keys=True,
                               default=str))
    clean = [record for record in verification['episodes'] if not record['problems']]
    broken = [record for record in verification['episodes'] if record['problems']]
    print(json.dumps({
        'status_counts': verification['status_counts'],
        'episodes_clean': len(clean),
        'episodes_with_problems': len(broken),
        'problems': {record['episode_id']: record['problems'] for record in broken},
        'protocol_problems': verification.get('protocol_problems', []),
        'written': str(path),
    }, indent=1, default=str))


if __name__ == '__main__':
    main()
