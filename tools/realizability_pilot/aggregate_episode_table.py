#!/usr/bin/python3
"""Aggregate one-row-per-episode pilot outcomes and target-related stages."""

import argparse
import csv
import json
from pathlib import Path


FIELDS = [
    'map_id', 'target_id', 'episode_id', 'condition_id', 'repeat',
    'delta_yaw_deg', 'lateral_offset_m', 'maneuver_type',
    'diagnostics_enabled', 'analysis_eligible', 'history_contaminated_by_closure',
    'action_completed', 'near_target_keyscan_generated',
    'target_related_opportunity', 'target_related_coarse_pass',
    'target_related_fine_pass', 'matcher_accepted_target',
    'matcher_accepted_wrong_target', 'backend_event_without_new_edge',
    'target_constraint', 'target_backend_measurement',
    'target_explicit_loop_constraint_full_graph',
    'target_nonexplicit_full_graph_constraint',
    'target_nonexplicit_marker_constraint', 'wrong_target_constraint',
    'false_constraint', 'actual_probe_distance_m', 'probe_duration_s',
    'current_scan_id', 'historical_scan_id', 'measurement_dx', 'measurement_dy',
    'measurement_dyaw', 'covariance_xx', 'covariance_xy', 'covariance_xt',
    'covariance_yy', 'covariance_yt', 'covariance_tt', 'run_dir',
]


def diagnostic_stages(path, target_ids, before_max, after_max):
    result = {'opportunity': None, 'coarse': None, 'fine': None}
    if not path.is_file():
        return result
    result = {'opportunity': False, 'coarse': False, 'fine': False}
    for line in path.read_text(errors='replace').splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        scan_id = int(record.get('scan_id', -1))
        if scan_id <= before_max or (after_max >= 0 and scan_id > after_max):
            continue
        chain_ids = {int(value) for value in (record.get('scan_ids') or [])}
        if not chain_ids.intersection(target_ids):
            continue
        result['opportunity'] = True
        if record.get('coarse_pass'):
            result['coarse'] = True
        if record.get('fine_pass'):
            result['fine'] = True
    return result


def rows(suite_dir):
    state = json.loads((suite_dir / 'suite_state.json').read_text())
    for episode in state['episodes']:
        succeeded = [attempt for attempt in episode['attempts'] if attempt['status'] == 'SUCCEEDED']
        if not succeeded:
            continue
        run_dir = suite_dir / succeeded[-1]['run_dir']
        result = json.loads((run_dir / 'episode_result.json').read_text())
        spec = result['spec']
        target_ids = set(result['frozen_target']['historical_scan_ids'])
        stages = diagnostic_stages(
            run_dir / 'karto_loop_diagnostics.jsonl', target_ids,
            int(result['before_max_scan_id']), int(result['after_max_scan_id']))
        event = result['target_constraint_events'][0] if result['target_constraint_events'] else {}
        yield {
            'map_id': spec['map_id'], 'target_id': spec['target_id'],
            'episode_id': spec['episode_id'], 'condition_id': spec['condition_id'],
            'repeat': spec['repeat'], 'delta_yaw_deg': spec['delta_yaw_deg'],
            'lateral_offset_m': spec['lateral_offset_m'],
            'maneuver_type': spec['maneuver_type'],
            'diagnostics_enabled': spec['diagnostics_enabled'],
            'analysis_eligible': result['analysis_eligible'],
            'history_contaminated_by_closure': result['history_contaminated_by_closure'],
            'action_completed': result['action_completed'],
            'near_target_keyscan_generated': result['near_target_keyscan_generated'],
            'target_related_opportunity': stages['opportunity'],
            'target_related_coarse_pass': stages['coarse'],
            'target_related_fine_pass': stages['fine'],
            'matcher_accepted_target': result['matcher_accepted_target'],
            'matcher_accepted_wrong_target': result['matcher_accepted_wrong_target'],
            'backend_event_without_new_edge': result['backend_event_without_new_edge'],
            'target_constraint': result['target_constraint'],
            'target_backend_measurement': result.get('target_backend_measurement'),
            'target_explicit_loop_constraint_full_graph': result.get(
                'target_explicit_loop_constraint_full_graph'),
            'target_nonexplicit_full_graph_constraint': result.get(
                'target_nonexplicit_full_graph_constraint'),
            'target_nonexplicit_marker_constraint': result.get(
                'target_nonexplicit_marker_constraint'),
            'wrong_target_constraint': result['wrong_target_constraint'],
            'false_constraint': result['false_constraint'],
            'actual_probe_distance_m': result['actual_probe_distance_m'],
            'probe_duration_s': result['probe_end_time'] - result['probe_start_time'],
            'current_scan_id': event.get('current_scan'),
            'historical_scan_id': event.get('historical_scan'),
            'measurement_dx': event.get('measurement_dx'),
            'measurement_dy': event.get('measurement_dy'),
            'measurement_dyaw': event.get('measurement_dyaw'),
            'covariance_xx': event.get('covariance_xx'),
            'covariance_xy': event.get('covariance_xy'),
            'covariance_xt': event.get('covariance_xt'),
            'covariance_yy': event.get('covariance_yy'),
            'covariance_yt': event.get('covariance_yt'),
            'covariance_tt': event.get('covariance_tt'),
            'run_dir': str(run_dir),
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--suite-dir', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    suite_dir = args.suite_dir.resolve()
    output = args.output or (suite_dir / 'pilot_episodes.csv')
    records = list(rows(suite_dir))
    with output.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(records)
    print('wrote {} episode rows to {}'.format(len(records), output))


if __name__ == '__main__':
    main()
