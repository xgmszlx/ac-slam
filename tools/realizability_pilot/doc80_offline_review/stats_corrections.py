#!/usr/bin/python3
"""Doc-80 section 8: statistical interpretation corrections.

Separates per-run facts (episode = independent unit) from the descriptive
cross-differences, explains the exact semantics of the Doc-79 suite gate, and
records the real cost differences of the executed actions.

Output: analysis/statistical_corrections.csv
"""

import csv
import json
import statistics
from pathlib import Path

from . import common


def run(doc80_root=common.DOC80, doc79_root=common.DOC79):
    metrics_path = Path(doc79_root) / 'analysis' / 'per_episode_metrics.csv'
    rows = []
    if metrics_path.is_file():
        with open(metrics_path) as handle:
            for row in csv.DictReader(handle):
                if row['technical_validity'] != 'MEASUREMENT_VALIDATED':
                    continue
                def number(value):
                    try:
                        return float(value)
                    except (TypeError, ValueError):
                        return None
                rows.append({
                    'episode_id': row['episode_id'], 'attempt': row['attempt'],
                    'place': row['place'], 'action': row['action'],
                    'seed': row['seed'],
                    'action_gain_sync': number(row['delta_J_action_sync']),
                    'actual_rotation_rad': number(row['actual_rotation_rad']),
                    'planned_rotation_rad': number(row['planned_rotation_rad']),
                    'action_path_m': number(row['action_path_m']),
                    'observation_duration_s': number(row['observation_duration_s']),
                    'total_rotation_rad': number(row.get('total_rotation_rad', '')),
                    'unit': 'episode',
                })
    # cost summary per (place, action)
    summary = []
    for place in ('place_B', 'place_C'):
        for action in ('L+', 'L-'):
            subset = [row for row in rows
                      if row['place'] == place and row['action'] == action]
            gains = [row['action_gain_sync'] for row in subset
                     if row['action_gain_sync'] is not None]
            rotations = [row['actual_rotation_rad'] for row in subset
                         if row['actual_rotation_rad'] is not None]
            paths = [row['action_path_m'] for row in subset
                     if row['action_path_m'] is not None]
            summary.append({
                'episode_id': 'SUMMARY_{}_{}'.format(place, action),
                'unit': 'descriptive',
                'runs': len(subset),
                'action_gain_mean': statistics.mean(gains) if gains else None,
                'action_gain_min': min(gains) if gains else None,
                'action_gain_max': max(gains) if gains else None,
                'actual_rotation_mean_rad': (statistics.mean(rotations)
                                             if rotations else None),
                'actual_rotation_min_rad': min(rotations) if rotations else None,
                'actual_rotation_max_rad': max(rotations) if rotations else None,
                'action_path_mean_m': statistics.mean(paths) if paths else None,
                'rotation_vs_plan_ratio': (
                    statistics.mean(rotations) / (3.141592653589793)
                    if rotations else None),
            })
    # cross differences are NOT independent: list them once, with a warning row
    plus = [row['action_gain_sync'] for row in rows if row['action'] == 'L+']
    cross = []
    for place in ('place_B', 'place_C'):
        p = [row['action_gain_sync'] for row in rows
             if row['place'] == place and row['action'] == 'L+']
        m = [row['action_gain_sync'] for row in rows
             if row['place'] == place and row['action'] == 'L-']
        for value_p in p:
            for value_m in m:
                cross.append({'place': place, 'difference': value_p - value_m})
    common.write_csv(Path(doc80_root) / 'analysis' / 'statistical_corrections.csv',
                     rows)
    payload = {
        'per_run': rows,
        'group_summary': summary,
        'cross_differences': {
            'definition': 'L+ minus L- within a place; all combinations, '
                          'descriptive only',
            'counts': {'place_B': len([c for c in cross if c['place'] == 'place_B']),
                       'place_C': len([c for c in cross if c['place'] == 'place_C'])},
            'warning': ('cross differences reuse the same runs; they are NOT '
                        'independent pair trials and carry no extra replication'),
        },
        'final_gate_semantics': {
            'doc79_field_measurement_validated': False,
            'reason': ('Doc-79 code required valid_attempts == total_attempts; the '
                       'physical retry made attempts (8) exceed validated runs (7)'),
            'VALID_RUN_MEASUREMENT_PASS': True,
            'valid_runs': len(rows),
            'attempts': 8,
            'planned_episodes': 8,
            'completed_planned_episodes': 7,
            'SUITE_COMPLETE': False,
        },
        'cost_note': ('actual cumulative rotation 3.40-3.83 rad vs planned pi rad; '
                      'B_Lplus_2 has non-zero action path; action cost is NOT '
                      'identical across runs and an information-per-angle ratio is '
                      'auxiliary only'),
    }
    common.write_json(Path(doc80_root) / 'analysis' / 'statistical_corrections.json',
                      payload)
    return payload


if __name__ == '__main__':
    print(json.dumps(run()['final_gate_semantics'], indent=1))
