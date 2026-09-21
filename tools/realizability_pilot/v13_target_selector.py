#!/usr/bin/python3
"""Outcome-blind block-local v13 target-state selector.

Only canonical prefix/history artifacts are accepted as inputs.  The selector
does not import branch results, constraints, posterior metrics, or action
provenance.
"""

import argparse
import json
import math
from pathlib import Path


QUANTILES = (0.1, 0.3, 0.5, 0.7, 0.9)
SEGMENT_HALF_WIDTH_STATES = 10


def _load(path):
    with open(path) as stream:
        return json.load(stream)


def _distance(a, b):
    return math.hypot(float(a[0]) - float(b[0]),
                      float(a[1]) - float(b[1]))


def select_block_local_target(attempt_dir, target_label, target_id):
    attempt_dir = Path(attempt_dir)
    snapshot = _load(attempt_dir / 'pose_graph_before.json')
    route = _load(attempt_dir / 'resolved_history_route.json')
    result = _load(attempt_dir / 'episode_result.json')
    route_start = int(route['route_start_node_count'])
    waypoint_index = {'map3_grid_anchor_01': 0,
                      'map3_grid_anchor_03': 1}[target_id]
    waypoint = route['resolved_history_waypoints'][waypoint_index]
    unique_by_state = {int(row['id']): int(row['unique_id'])
                       for row in snapshot.get('full_pose_nodes', [])}
    candidates = [row for row in snapshot['nodes']
                  if int(row['id']) >= route_start]
    candidates.sort(key=lambda row: int(row['id']))
    if len(candidates) < 5:
        raise ValueError('fewer than five legal post-route-start scans')

    anchor_index = min(range(len(candidates)), key=lambda index: (
        _distance([candidates[index]['x'], candidates[index]['y']], waypoint),
        int(candidates[index]['id'])))
    anchor = candidates[anchor_index]
    start = max(0, anchor_index - SEGMENT_HALF_WIDTH_STATES)
    stop = min(len(candidates), anchor_index + SEGMENT_HALF_WIDTH_STATES + 1)
    segment = candidates[start:stop]
    if len(segment) < 5:
        raise ValueError('fixed local segment contains fewer than five scans')

    cumulative = [0.0]
    for left, right in zip(segment, segment[1:]):
        cumulative.append(cumulative[-1] + _distance(
            [left['x'], left['y']], [right['x'], right['y']]))
    total = cumulative[-1]
    if total <= 0.0:
        raise ValueError('fixed local segment has zero spatial arc length')
    progress = [value / total for value in cumulative]
    selected_indices = []
    for quantile in QUANTILES:
        index = min(range(len(segment)),
                    key=lambda i: (abs(progress[i] - quantile), i))
        selected_indices.append(index)
    if len(set(selected_indices)) != 5:
        raise ValueError('quantile rule did not produce five distinct states')
    if selected_indices != sorted(selected_indices):
        raise ValueError('quantile states are not strictly ordered')

    selected = [segment[index] for index in selected_indices]
    selected_ids = [int(row['id']) for row in selected]
    if any(left >= right for left, right in zip(selected_ids, selected_ids[1:])):
        raise ValueError('selected state ids are not strictly increasing')
    segment_rows = []
    for row, arc, norm in zip(segment, cumulative, progress):
        segment_rows.append({
            'state_id': int(row['id']),
            'unique_id': unique_by_state.get(int(row['id'])),
            'x': float(row['x']), 'y': float(row['y']),
            'theta': float(row['theta']), 'arc_length_m': arc,
            'normalized_progress': norm,
        })
    selection_rows = []
    for quantile, index in zip(QUANTILES, selected_indices):
        row = segment_rows[index]
        selection_rows.append({
            'quantile': quantile, 'segment_index': index,
            'state_id': row['state_id'], 'unique_id': row['unique_id'],
            'normalized_progress': row['normalized_progress'],
            'quantile_abs_error': abs(row['normalized_progress'] - quantile),
        })
    return {
        'protocol': 'v13 block-local target selector v1',
        'target_label': target_label,
        'target_id': target_id,
        'allowed_inputs': [
            'pose_graph_before.json nodes/full_pose_nodes',
            'resolved_history_route.json',
            'episode_result.json canonical_history_complete'],
        'forbidden_future_inputs_accessed': False,
        'canonical_history_complete': bool(
            result.get('canonical_history_complete')),
        'fixed_target_waypoint_index': waypoint_index,
        'fixed_target_waypoint': waypoint,
        'route_start_node_count': route_start,
        'anchor_rule': ('nearest legal post-route-start scan to the fixed '
                        'target waypoint; ties use lower state id'),
        'action_anchor': dict(anchor,
                              unique_id=unique_by_state.get(int(anchor['id']))),
        'anchor_to_waypoint_distance_m': _distance(
            [anchor['x'], anchor['y']], waypoint),
        'segment_rule': ('contiguous ordered post-route-start scan slice with '
                         'at most 10 predecessors and 10 successors around '
                         'the action anchor'),
        'segment_half_width_states': SEGMENT_HALF_WIDTH_STATES,
        'candidate_segment_state_ids': [row['state_id'] for row in segment_rows],
        'candidate_segment': segment_rows,
        'segment_arc_length_m': total,
        'quantiles': list(QUANTILES),
        'quantile_selections': selection_rows,
        'historical_scan_ids': selected_ids,
        'historical_unique_ids': [unique_by_state.get(state_id)
                                  for state_id in selected_ids],
        'exact_state_count': len(selected_ids),
        'distinct_states': len(set(selected_ids)) == 5,
        'strictly_ordered_states': all(
            left < right for left, right in zip(selected_ids,
                                                selected_ids[1:])),
        'selection_valid': (
            bool(result.get('canonical_history_complete')) and
            len(selected_ids) == 5 and len(set(selected_ids)) == 5 and
            all(value is not None for value in
                [unique_by_state.get(state_id) for state_id in selected_ids])),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--attempt-dir', required=True)
    parser.add_argument('--target-label', required=True,
                        choices=('target_A', 'target_B'))
    parser.add_argument('--target-id', required=True,
                        choices=('map3_grid_anchor_01', 'map3_grid_anchor_03'))
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    payload = select_block_local_target(args.attempt_dir, args.target_label,
                                        args.target_id)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
