#!/usr/bin/python3
"""Doc-80 section 7.2-7.5: strictly pre-action feature construction.

Input firewall
--------------
``slice_pre_action`` copies the *only* allowed inputs into a bundle directory:

- ``episode_spec.json``             (frozen protocol definition)
- ``frozen_target.json``            (target identity, outcome-blind)
- ``resolved_route.json``           (planned route)
- protocol markers from ``episode_result.json`` (phase scan windows only)
- ``graph_before_return_sync.json`` (pre-return synchronous graph)
- ``graph_arrival_sync.json``       (pre-action synchronous graph)
- ``scans_pre_action.jsonl``        (scan records with index < action start)

``build_features`` reads **nothing else**: it accepts only those bundle paths
and refuses any path whose name looks like a post-action artifact.  The
outcome side lives in ``outcome_evaluation.py`` and is never imported here.
"""

import json
import math
from pathlib import Path

from . import common

FORBIDDEN_TOKENS = ('action_done', 'final', 'gt_stream', 'karto_edge_provenance',
                    'native_processing_ledger', 'rosout', 'scan_stream.jsonl')


def _guard(path):
    name = Path(path).name
    if any(token in name for token in FORBIDDEN_TOKENS):
        raise AssertionError('post-action input refused by the feature firewall: '
                             '{}'.format(path))


def slice_pre_action(run, bundle_dir):
    """Materialise the allowed-input bundle for one attempt (no outcome data)."""
    bundle_dir = Path(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    result = run['result']
    stage_windows = common.windows(result)
    if stage_windows is None:
        return None
    action_start = stage_windows['action'][0]
    # protocol markers only (no action outcome fields)
    markers = {
        'episode_id': run['episode_id'],
        'attempt': run['attempt'],
        'place': run['spec'].get('place_id'),
        'action': run['spec'].get('action_id'),
        'seed': run['spec'].get('tsp_seed'),
        'stage_windows': {key: list(value) for key, value in stage_windows.items()},
        'action_start_scan_index': int(action_start),
        'action_frames_target': int(result.get('action_frames_target')),
        'history_end_scan': int((result.get('phase_scan_marks') or {}).get(
            'history_end_scan', 0)),
        'return_start_scan': int((result.get('phase_scan_marks') or {}).get(
            'return_start_scan', 0)),
        'planner_action_definition': {
            'L+': 'theta0 -> theta0 + pi/2 -> theta0',
            'L-': 'theta0 -> theta0 - pi/2 -> theta0',
            'planned_rotation_rad': run['spec'].get('planned_cumulative_rotation_rad'),
        },
    }
    common.write_json(bundle_dir / 'pre_action_bundle.json', markers)
    common.write_json(bundle_dir / 'episode_spec.json',
                      {'frozen': run['spec']})
    common.write_json(bundle_dir / 'frozen_target.json', run['frozen'])
    route = common.load_json(run['attempt_dir'] / 'resolved_route.json')
    common.write_json(bundle_dir / 'resolved_route.json', route or {})

    scans = common.jsonl(run['attempt_dir'] / 'scan_stream.jsonl')
    with open(bundle_dir / 'scans_pre_action.jsonl', 'w') as handle:
        for record in scans:
            if record['index'] >= action_start:
                break
            handle.write(json.dumps(record, separators=(',', ':')) + '\n')

    for stem in ('before_return', 'arrival'):
        payload = common.load_json(run['attempt_dir'] /
                                   'graph_{}_sync.json'.format(stem))
        common.write_json(bundle_dir / 'graph_{}_sync.json'.format(stem),
                          payload or {})
    # a copy of the boundary file stem mapping for reference (pre-action only)
    manifest = common.load_json(run['attempt_dir'] / 'boundary_manifest.json', {})
    keep = {}
    for stem in ('before_return', 'arrival'):
        entry = (manifest or {}).get(common.BOUNDARY_OF[stem], {})
        keep[common.BOUNDARY_OF[stem]] = {
            'watermark': entry.get('watermark'),
            'sync_file_stem': stem,
        }
    common.write_json(bundle_dir / 'pre_action_boundary_marks.json', keep)
    return bundle_dir


# ---------------------------------------------------------------- FOV algebra
def _wrap_interval(start, end):
    """Represent a possibly >2pi interval as (start, length) in radians."""
    return (start, end - start)


def _contains(angle, start, length):
    delta = (angle - start) % (2.0 * math.pi)
    return delta <= length + 1e-12


def swept_fov(theta0, angle_min, angle_max, direction):
    """Swept world-frame angular sector for the two rotation directions.

    The laser is fixed to the base; the action rotates the base by +pi/2 (L+)
    or -pi/2 (L-) and returns, so the swept sector is the union of the sensor
    footprint over the rotation.  Returns ``(start, length)`` with length in
    radians (<= 2*pi) using an unwrapped start.
    """
    if direction == 'L+':
        start = theta0 + angle_min
        length = (math.pi / 2.0) + (angle_max - angle_min)
    elif direction == 'L-':
        start = theta0 - math.pi / 2.0 + angle_min
        length = (math.pi / 2.0) + (angle_max - angle_min)
    else:
        raise ValueError('unknown direction {}'.format(direction))
    return start, length


def _overlap(start_a, len_a, start_b, len_b):
    """Overlap length of two circular intervals, robust to wraparound."""
    best = 0.0
    for shift in (-2.0 * math.pi, 0.0, 2.0 * math.pi):
        low = max(start_a, start_b + shift)
        high = min(start_a + len_a, start_b + shift + len_b)
        best = max(best, high - low)
    return max(0.0, min(best, len_a, len_b))


def common_exclusive(theta0, angle_min, angle_max):
    plus = swept_fov(theta0, angle_min, angle_max, 'L+')
    minus = swept_fov(theta0, angle_min, angle_max, 'L-')
    common_length = _overlap(plus[0], plus[1], minus[0], minus[1])
    return {'Lplus': plus, 'Lminus': minus,
            'common_length': common_length,
            'exclusive_Lplus': plus[1] - common_length,
            'exclusive_Lminus': minus[1] - common_length}


# ---------------------------------------------------------------- features
def build_features(bundle_dir):
    """Compute the frozen pre-action features from the bundle alone."""
    bundle_dir = Path(bundle_dir)
    _guard(bundle_dir / 'scans_pre_action.jsonl')
    markers = common.load_json(bundle_dir / 'pre_action_bundle.json')
    frozen = common.load_json(bundle_dir / 'frozen_target.json')
    scans = common.jsonl(bundle_dir / 'scans_pre_action.jsonl')
    arrival_payload = common.load_json(bundle_dir / 'graph_arrival_sync.json')
    before_payload = common.load_json(bundle_dir / 'graph_before_return_sync.json')
    if not markers or not scans or not arrival_payload:
        return None
    angle_min = float(scans[0]['angle_min'])
    angle_max = float(scans[0]['angle_max'])
    range_max = float(scans[0]['range_max'])
    fov = angle_max - angle_min

    # robot pose at the action start (last pre-action scan; base + laser)
    start_scan = scans[-1]
    robot_base = start_scan.get('map_base')
    if robot_base is None:
        return None
    robot_laser = common.compose(tuple(robot_base), (0.2, 0.0, 0.0))
    theta0 = robot_laser[2]

    # accepted history / return states (identity only, from the frozen target
    # bundle's segment information is NOT enough; derive from the pre-action
    # graphs by their state ids and the acceptance time order embedded in the
    # graph itself is unavailable, so use node order in the pre-return graph
    # for the first-visit stage and the arrival-minus-before node set for the
    # return stage -- both outcome-blind graph facts)
    before_ids = {int(node['state_id']) for node in before_payload.get('nodes', [])}
    arrival_nodes = arrival_payload.get('nodes', [])
    node_by_state = {int(node['state_id']): node for node in arrival_nodes}
    history_states = sorted(before_ids & set(node_by_state))
    return_states = sorted(set(node_by_state) - before_ids)

    intervals = common_exclusive(theta0, angle_min, angle_max)

    def visible_fraction(states):
        if not states:
            return 0.0, 0, 0
        visible_plus = 0
        visible_minus = 0
        for state in states:
            node = node_by_state[state]
            dx = node['x'] - robot_laser[0]
            dy = node['y'] - robot_laser[1]
            distance = math.hypot(dx, dy)
            if distance > range_max + 1e-9:
                continue
            bearing = math.atan2(dy, dx)
            if _contains(bearing, *intervals['Lplus']):
                visible_plus += 1
            if _contains(bearing, *intervals['Lminus']):
                visible_minus += 1
        return (max(visible_plus, visible_minus) / len(states), visible_plus,
                visible_minus)

    history_frac, history_plus, history_minus = visible_fraction(history_states)
    return_frac, return_plus, return_minus = visible_fraction(return_states)

    # non-redundant association proxy: inverse non-chain degree of visible nodes
    def nonchain_degree(states):
        edges = arrival_payload.get('edges', [])
        adjacency = {state: 0 for state in states}
        for edge in edges:
            source = int(edge['source_state_id'])
            target = int(edge['target_state_id'])
            chain = abs(target - source) == 1
            if chain:
                continue
            if source in adjacency:
                adjacency[source] += 1
            if target in adjacency:
                adjacency[target] += 1
        return adjacency

    def novelty(plus_visible, minus_visible, states):
        degree = nonchain_degree(states)
        score_plus = sum(1.0 / (1.0 + degree[state]) for state in plus_visible)
        score_minus = sum(1.0 / (1.0 + degree[state]) for state in minus_visible)
        shared = 0.0
        return score_plus, score_minus, shared

    def visible_lists(states):
        plus, minus = [], []
        for state in states:
            node = node_by_state[state]
            dx = node['x'] - robot_laser[0]
            dy = node['y'] - robot_laser[1]
            if math.hypot(dx, dy) > range_max + 1e-9:
                continue
            bearing = math.atan2(dy, dx)
            if _contains(bearing, *intervals['Lplus']):
                plus.append(state)
            if _contains(bearing, *intervals['Lminus']):
                minus.append(state)
        return plus, minus

    history_plus_list, history_minus_list = visible_lists(history_states)
    return_plus_list, return_minus_list = visible_lists(return_states)
    novelty_plus, novelty_minus, _ = novelty(history_plus_list,
                                             history_minus_list, history_states)

    targets = [int(value) for value in frozen.get('target_state_ids', [])]
    target_positions = [(node_by_state[state]['x'], node_by_state[state]['y'])
                        for state in targets if state in node_by_state]
    spread = None
    if len(target_positions) >= 2:
        cx = sum(p[0] for p in target_positions) / len(target_positions)
        cy = sum(p[1] for p in target_positions) / len(target_positions)
        spread = max(math.hypot(px - cx, py - cy) for px, py in target_positions)
    return {
        'episode_id': markers['episode_id'], 'attempt': markers['attempt'],
        'place': markers['place'], 'action': markers['action'],
        'seed': markers.get('seed'),
        'fov_deg': math.degrees(fov),
        'angle_min_rad': angle_min, 'angle_max_rad': angle_max,
        'theta0_laser_rad': theta0,
        'robot_laser_pose': json.dumps(list(robot_laser)),
        'fov_Lplus_start_rad': intervals['Lplus'][0],
        'fov_Lplus_length_rad': intervals['Lplus'][1],
        'fov_Lminus_start_rad': intervals['Lminus'][0],
        'fov_Lminus_length_rad': intervals['Lminus'][1],
        'common_sector_rad': intervals['common_length'],
        'exclusive_Lplus_rad': intervals['exclusive_Lplus'],
        'exclusive_Lminus_rad': intervals['exclusive_Lminus'],
        'history_nodes': len(history_states),
        'return_nodes': len(return_states),
        'history_visible_Lplus': len(history_plus_list),
        'history_visible_Lminus': len(history_minus_list),
        'history_visible_frac_Lplus': (len(history_plus_list) / len(history_states)
                                       if history_states else None),
        'history_visible_frac_Lminus': (len(history_minus_list) / len(history_states)
                                        if history_states else None),
        'history_exclusive_Lplus': len(set(history_plus_list)
                                        - set(history_minus_list)),
        'history_exclusive_Lminus': len(set(history_minus_list)
                                         - set(history_plus_list)),
        'return_visible_Lplus': len(return_plus_list),
        'return_visible_Lminus': len(return_minus_list),
        'novelty_proxy_Lplus': novelty_plus,
        'novelty_proxy_Lminus': novelty_minus,
        'novelty_proxy_delta': novelty_plus - novelty_minus,
        'directional_visibility_delta_frac': (
            (len(history_plus_list) - len(history_minus_list)) / len(history_states)
            if history_states else None),
        'arrival_nodes': len(arrival_nodes),
        'arrival_edges': len(arrival_payload.get('edges', [])),
        'target_spread_max_m': spread,
        'feature_source': 'PRE_ACTION_ONLY (firewalled bundle)',
        'proxy_note': 'GRAPH_NOVELTY_PROXY: geometric proxy, not a match probability',
    }


def run(doc80_root=common.DOC80):
    rows = []
    bundle_root = Path(doc80_root) / 'audit' / 'pre_action_bundles'
    for run_ in common.valid_runs():
        bundle = slice_pre_action(run_, bundle_root / run_['episode_id']
                                  / run_['attempt'])
        if bundle is None:
            continue
        features = build_features(bundle)
        if features:
            rows.append(features)
    common.write_csv(Path(doc80_root) / 'analysis' /
                     'directional_visibility_features.csv', rows)
    return rows


if __name__ == '__main__':
    for row in run():
        print(row['episode_id'], row['action'],
              'hist vis L+/L-:', row['history_visible_Lplus'],
              row['history_visible_Lminus'],
              'novelty delta:', row['novelty_proxy_delta'])
