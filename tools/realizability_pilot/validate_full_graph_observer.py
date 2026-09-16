#!/usr/bin/python3
"""Fail-closed consistency audit for one completed v7 pilot attempt."""

import argparse
import json
from pathlib import Path


def load(path):
    return json.loads(path.read_text())


def canonical_pair(left, right):
    return [min(int(left), int(right)), max(int(left), int(right))]


def covariance_checks(serialized):
    values = [float(value) for value in serialized.split()]
    if len(values) != 6:
        return {'value_count': len(values), 'positive_definite': False}
    xx, xy, xt, yy, yt, tt = values
    minor_1 = xx
    minor_2 = xx * yy - xy * xy
    determinant = (
        xx * (yy * tt - yt * yt)
        - xy * (xy * tt - yt * xt)
        + xt * (xy * yt - yy * xt)
    )
    return {
        'value_count': len(values),
        'leading_principal_minors': [minor_1, minor_2, determinant],
        'positive_definite': minor_1 > 0 and minor_2 > 0 and determinant > 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()

    before = load(args.run_dir / 'pose_graph_before.json')
    after = load(args.run_dir / 'pose_graph_after.json')
    result = load(args.run_dir / 'episode_result.json')

    exact_edges = result.get('target_full_pose_graph_constraints', [])
    marker_edges = result.get('target_marker_constraints', [])
    exact_pairs = sorted(canonical_pair(edge['start'], edge['end'])
                         for edge in exact_edges)
    marker_pairs = sorted(canonical_pair(edge['source'], edge['target'])
                          for edge in marker_edges)
    covariance = [
        {
            'pair': canonical_pair(edge['start'], edge['end']),
            **covariance_checks(edge['covariance_upper_triangle']),
        }
        for edge in exact_edges
    ]

    checks = {
        'before_node_count_matches': (
            len(before['nodes']) == len(before['full_pose_nodes'])),
        'after_node_count_matches': (
            len(after['nodes']) == len(after['full_pose_nodes'])),
        'before_node_ids_match': (
            [node['id'] for node in before['nodes']]
            == [node['id'] for node in before['full_pose_nodes']]),
        'after_node_ids_match': (
            [node['id'] for node in after['nodes']]
            == [node['id'] for node in after['full_pose_nodes']]),
        'all_full_edge_endpoints_resolved': all(
            edge['start'] >= 0 and edge['end'] >= 0
            for edge in after['full_pose_edges']),
        'exact_marker_target_pairs_match': exact_pairs == marker_pairs,
        'target_measurement_present': bool(exact_edges),
        'all_target_covariances_positive_definite': (
            bool(covariance) and all(item['positive_definite'] for item in covariance)),
        'backend_measurement_flag_matches_edges': (
            bool(result.get('target_backend_measurement')) == bool(exact_edges)),
    }
    payload = {
        'status': 'PASS' if all(checks.values()) else 'FAIL',
        'run_dir': str(args.run_dir.resolve()),
        'checks': checks,
        'before_counts': {
            'slam_path_nodes': len(before['nodes']),
            'full_graph_nodes': len(before['full_pose_nodes']),
            'full_graph_edges': len(before['full_pose_edges']),
        },
        'after_counts': {
            'slam_path_nodes': len(after['nodes']),
            'full_graph_nodes': len(after['full_pose_nodes']),
            'full_graph_edges': len(after['full_pose_edges']),
        },
        'exact_target_pairs': exact_pairs,
        'marker_target_pairs': marker_pairs,
        'target_covariance_checks': covariance,
        'explicit_target_constraint': bool(result.get('target_constraint')),
        'target_backend_measurement': bool(result.get('target_backend_measurement')),
    }
    destination = args.output or (args.run_dir / 'full_graph_observer_validation.json')
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
    print(json.dumps(payload, indent=2, sort_keys=True))
    raise SystemExit(0 if payload['status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
