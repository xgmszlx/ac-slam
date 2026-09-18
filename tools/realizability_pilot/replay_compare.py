#!/usr/bin/python3
"""Compare two same-input replay graphs and decide instrumentation neutrality.

The comparison is deliberately broader than "target constraint count": it
compares the whole constraint-generation output of the Karto subsystem.

Pre-registered tolerances (stated here, before any comparison is evaluated):

* ``NUMERICAL_FLOOR_*`` - the numerical resolution of the recorded values
  (poses and measurements are written with six decimals, covariances likewise),
  so exact replay equality is expected at 1e-6 and any deviation above it is a
  real difference;
* the verdict tolerance is ``max(numerical floor, 2 x measured replay
  repeatability)``, where the repeatability comes from replaying the *same* arm
  twice.  That is a measured scale, not a chosen one.

Verdicts:

``REPLAY_NEUTRALITY_CERTIFIED``
    identical input, identical graph within tolerance: the instrument does not
    change what Karto produces.
``REPLAY_INSTRUMENT_NOT_NEUTRAL``
    the instrumented replay differs beyond the measured replay repeatability.
"""

import argparse
import json
from pathlib import Path

NUMERICAL_FLOOR_POSE_M = 1e-6
NUMERICAL_FLOOR_ANGLE_RAD = 1e-6
NUMERICAL_FLOOR_MEASUREMENT = 1e-6
NUMERICAL_FLOOR_COVARIANCE = 1e-9
REPEATABILITY_MULTIPLIER = 2.0


def load_graph(path):
    with open(path) as stream:
        return json.load(stream)


def graph_summary(graph):
    nodes = graph['nodes']
    edges = graph['edges']
    return {
        'node_count': len(nodes),
        'edge_count': len(edges),
        'node_ids': [node['state_id'] for node in nodes],
        'node_unique_ids': [node['unique_id'] for node in nodes],
        'node_poses': [[node['x'], node['y'], node['theta']] for node in nodes],
        'edge_pairs': [[edge['source_state_id'], edge['target_state_id']]
                       for edge in edges],
        'edge_measurements': [[edge.get('measurement', {}).get('dx', 0.0),
                               edge.get('measurement', {}).get('dy', 0.0),
                               edge.get('measurement', {}).get('dtheta', 0.0)]
                              for edge in edges],
        'edge_covariances': [edge.get('covariance_3x3', []) for edge in edges],
    }


def max_difference(values_a, values_b):
    """Largest absolute element-wise difference of two nested float lists."""
    if len(values_a) != len(values_b):
        return None
    worst = 0.0
    for left, right in zip(values_a, values_b):
        if isinstance(left, (list, tuple)):
            nested = max_difference(left, right)
            if nested is None:
                return None
            worst = max(worst, nested)
        else:
            worst = max(worst, abs(float(left) - float(right)))
    return worst


def compare_graphs(graph_a, graph_b):
    """Structural and numerical comparison of two dumped graphs."""
    summary_a = graph_summary(graph_a)
    summary_b = graph_summary(graph_b)
    comparison = {
        'node_count': [summary_a['node_count'], summary_b['node_count']],
        'edge_count': [summary_a['edge_count'], summary_b['edge_count']],
        'node_ids_equal': summary_a['node_ids'] == summary_b['node_ids'],
        'node_unique_ids_equal': (summary_a['node_unique_ids']
                                  == summary_b['node_unique_ids']),
        'edge_pair_sequence_equal': (summary_a['edge_pairs']
                                     == summary_b['edge_pairs']),
        'edge_pair_set_equal': (sorted(map(tuple, summary_a['edge_pairs']))
                                == sorted(map(tuple, summary_b['edge_pairs']))),
    }
    comparison['node_pose_max_difference'] = max_difference(
        summary_a['node_poses'], summary_b['node_poses'])
    comparison['edge_measurement_max_difference'] = max_difference(
        summary_a['edge_measurements'], summary_b['edge_measurements'])
    comparison['edge_covariance_max_difference'] = max_difference(
        summary_a['edge_covariances'], summary_b['edge_covariances'])
    return comparison


def verdict(comparisons, repeatability):
    """Turn one or more graph comparisons into a neutrality verdict.

    ``comparisons`` is a list of (label, comparison) pairs.  ``repeatability``
    is the measured same-arm replay variation (a dict with the same keys as a
    comparison).
    """
    tolerances = {
        'node_pose_max_difference': max(
            NUMERICAL_FLOOR_POSE_M,
            REPEATABILITY_MULTIPLIER * (repeatability.get(
                'node_pose_max_difference') or 0.0)),
        'edge_measurement_max_difference': max(
            NUMERICAL_FLOOR_MEASUREMENT,
            REPEATABILITY_MULTIPLIER * (repeatability.get(
                'edge_measurement_max_difference') or 0.0)),
        'edge_covariance_max_difference': max(
            NUMERICAL_FLOOR_COVARIANCE,
            REPEATABILITY_MULTIPLIER * (repeatability.get(
                'edge_covariance_max_difference') or 0.0)),
    }
    failures = []
    for label, comparison in comparisons:
        for field in ('node_ids_equal', 'node_unique_ids_equal',
                      'edge_pair_sequence_equal'):
            if not comparison.get(field):
                failures.append({'comparison': label, 'field': field})
        if comparison['node_count'][0] != comparison['node_count'][1]:
            failures.append({'comparison': label, 'field': 'node_count',
                             'values': comparison['node_count']})
        if comparison['edge_count'][0] != comparison['edge_count'][1]:
            failures.append({'comparison': label, 'field': 'edge_count',
                             'values': comparison['edge_count']})
        for field, tolerance in tolerances.items():
            value = comparison.get(field)
            if value is None:
                failures.append({'comparison': label, 'field': field,
                                 'reason': 'shape mismatch'})
            elif value > tolerance:
                failures.append({'comparison': label, 'field': field,
                                 'value': value, 'tolerance': tolerance})
    return {
        'tolerance': tolerances,
        'failures': failures,
        'verdict': ('REPLAY_NEUTRALITY_CERTIFIED' if not failures
                    else 'REPLAY_INSTRUMENT_NOT_NEUTRAL'),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runs-dir', required=True,
                        help='directory containing the per-arm graph dumps')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    runs_dir = Path(args.runs_dir)

    graphs = {arm: [] for arm in ('off', 'on')}
    for arm in graphs:
        for path in sorted(runs_dir.glob('graph_{}_*.json'.format(arm))):
            graphs[arm].append(load_graph(path))
        legacy = runs_dir / 'graph_{}.json'.format(arm)
        if not graphs[arm] and legacy.is_file():
            graphs[arm].append(load_graph(legacy))

    if not graphs['off'] or not graphs['on']:
        raise SystemExit('need at least one dump per arm in {}'.format(runs_dir))

    # Same-arm comparison is the measured replay repeatability.
    repeatability = None
    same_arm_comparisons = []
    for arm, items in graphs.items():
        for index in range(1, len(items)):
            comparison = compare_graphs(items[0], items[index])
            same_arm_comparisons.append((arm, comparison))
            if repeatability is None:
                repeatability = comparison

    cross_arm_comparisons = []
    for index, off_graph in enumerate(graphs['off']):
        for on_graph in graphs['on']:
            cross_arm_comparisons.append(
                ('off{}_vs_on'.format(index), compare_graphs(off_graph, on_graph)))

    payload = {
        'same_arm_repeatability_comparisons': same_arm_comparisons,
        'cross_arm_comparisons': cross_arm_comparisons,
        'measured_replay_repeatability': repeatability,
        'verdict': verdict(cross_arm_comparisons, repeatability or {}),
        'numerical_floors': {
            'pose_m': NUMERICAL_FLOOR_POSE_M,
            'angle_rad': NUMERICAL_FLOOR_ANGLE_RAD,
            'measurement': NUMERICAL_FLOOR_MEASUREMENT,
            'covariance': NUMERICAL_FLOOR_COVARIANCE,
        },
        'repeatability_multiplier': REPEATABILITY_MULTIPLIER,
    }
    with open(args.out, 'w') as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, default=str)
        stream.write('\n')
    print(json.dumps({'verdict': payload['verdict']['verdict'],
                      'failures': payload['verdict']['failures']}, indent=2))


if __name__ == '__main__':
    main()
