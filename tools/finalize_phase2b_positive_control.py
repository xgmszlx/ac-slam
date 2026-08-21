#!/usr/bin/python3
"""Reconcile positive-control before/after evidence from full Karto topics."""

import argparse
import json
import math
from pathlib import Path


def resolve_marker_edges(snapshot):
    trajectory = snapshot['trajectory_estimate']
    resolved = []
    for edge in snapshot['closure_marker_edges']:
        endpoints = []
        for point in edge:
            node = min(
                trajectory,
                key=lambda pose: (pose['x'] - point[0]) ** 2 + (pose['y'] - point[1]) ** 2,
            )
            endpoints.append((
                int(node['index']),
                math.hypot(node['x'] - point[0], node['y'] - point[1]),
            ))
        resolved.append({
            'source': endpoints[0][0], 'target': endpoints[1][0],
            'scan_index_gap': abs(endpoints[0][0] - endpoints[1][0]),
            'endpoint_match_error_max_m': max(endpoints[0][1], endpoints[1][1]),
        })
    return resolved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', required=True, type=Path)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    result_path = run_dir / 'positive_control.json'
    result = json.loads(result_path.read_text())
    before = json.loads((run_dir / 'pose_graph_before.json').read_text())
    after = json.loads((run_dir / 'pose_graph_after.json').read_text())
    before_resolved = resolve_marker_edges(before)
    after_resolved = resolve_marker_edges(after)
    cutoff = len(before['trajectory_estimate']) - 1
    crossing = [
        edge for edge in after_resolved
        if min(edge['source'], edge['target']) <= cutoff
        and max(edge['source'], edge['target']) > cutoff
        and edge['scan_index_gap'] > 70
        and edge['endpoint_match_error_max_m'] < 0.05
    ]
    result.update({
        'before_node_count': len(before['trajectory_estimate']),
        'after_node_count': len(after['trajectory_estimate']),
        'before_incremental_pose_graph_node_count': before['pose_graph_node_count'],
        'after_incremental_pose_graph_node_count': after['pose_graph_node_count'],
        'before_closure_marker_edge_count': before['closure_marker_edge_count'],
        'after_closure_marker_edge_count': after['closure_marker_edge_count'],
        'resolved_before_closure_marker_edges': before_resolved,
        'resolved_after_closure_marker_edges': after_resolved,
        'marker_nonlocal_history_link_edges': crossing,
        'incremental_pose_graph_topic_stale_after_exploration': (
            len(after['trajectory_estimate']) > after['pose_graph_node_count']
        ),
        'positive_control_success': bool(
            result.get('karto_accepted_loop_events_during_revisit') and crossing
        ),
        'positive_control_evidence_note': (
            'Accepted Karto callback plus a full-graph closure-marker edge resolved '
            'against /slam_path with current node index above the pre-revisit cutoff. '
            'The custom incremental /slam_pose_graph topic stopped advancing after exploration.'
        ),
    })
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    manifest_path = run_dir / 'manifest.json'
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text())
        manifest['positive_control_success'] = result['positive_control_success']
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    state_path = run_dir / 'run_state.json'
    if state_path.is_file():
        state = json.loads(state_path.read_text())
        state['positive_control_success'] = result['positive_control_success']
        state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + '\n')
    print(json.dumps({
        'positive_control_success': result['positive_control_success'],
        'accepted_events': len(result.get('karto_accepted_loop_events_during_revisit', [])),
        'new_nonlocal_marker_edges': len(crossing),
        'before_nodes': result['before_node_count'], 'after_nodes': result['after_node_count'],
    }, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
