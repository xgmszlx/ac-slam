#!/usr/bin/python3
"""Offline analysis for the continuous revisit action experiment.

Reads one suite directory produced by ``runner.py`` and writes, under the same
root, ``analysis/`` tables + ``analysis/summary.json`` plus the figures produced
by ``figures.py``.  Nothing here starts ROS and nothing here re-runs a backend:
every number is derived from the recorded run directories.

Frozen information measure: ``J_T`` is the target-state log-determinant score
replicated from ``tools/realizability_pilot/action_selection_exploratory.py``
(``-logdet(marginal)/15`` for the five frozen target states, gauge fixed by the
lowest state id), so the numbers are comparable with the earlier rounds.
"""

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.linalg import cho_factor, cho_solve

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

import geometry as ge  # noqa: E402
import protocol as cr  # noqa: E402

PHASE_ORDER = ('history', 'return', 'action', 'tail')
SNAPSHOTS = ('G_before_return', 'G_arrival', 'G_action_done', 'G_final')
SNAPSHOT_FILES = {
    'G_before_return': 'graph_before_return.json',
    'G_arrival': 'graph_arrival.json',
    'G_action_done': 'graph_action_done.json',
    'G_final': 'graph_final.json',
}
#: View-direction bins: a direction counts as "new" when it is at least this far
#: (radians) from every historical view direction of the target.
NEW_VIEW_MARGIN_RAD = math.radians(15.0)


def jsonl(path):
    path = Path(path)
    if not path.is_file():
        return []
    records = []
    with path.open() as stream:
        for line in stream:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_json(path, default=None):
    path = Path(path)
    if not path.is_file():
        return default
    return json.loads(path.read_text())


def covariance_terms(edge):
    raw = edge.get('covariance_upper_triangle')
    if raw is None:
        return None
    if isinstance(raw, str):
        values = raw.split()
    elif isinstance(raw, (list, tuple)) and raw and isinstance(raw[0], str) \
            and len(''.join(raw)) > 8:
        values = ''.join(raw).split()
    else:
        values = list(raw)
    try:
        numbers = [float(value) for value in values]
    except (TypeError, ValueError):
        return None
    if len(numbers) != 6:
        return None
    return numbers


def covariance_matrix(terms):
    return np.array([[terms[0], terms[1], terms[2]],
                     [terms[1], terms[3], terms[4]],
                     [terms[2], terms[4], terms[5]]], dtype=float)


def snapshot_graph(snapshot):
    """Convert a driver snapshot into the repository J_T graph schema."""
    nodes = sorted(snapshot['graph']['nodes'], key=lambda node: int(node['id']))
    edges = sorted(snapshot['graph']['edges'], key=lambda edge: int(edge['index']))
    converted = {
        'nodes': [{'state_id': int(node['id']), 'unique_id': int(node['unique_id']),
                   'x': float(node['x']), 'y': float(node['y']),
                   'theta': float(node['theta'])} for node in nodes],
        'edges': [],
    }
    for edge in edges:
        terms = covariance_terms(edge)
        if terms is None:
            continue
        converted['edges'].append({
            'index': int(edge['index']),
            'source_state_id': int(edge['start']),
            'target_state_id': int(edge['end']),
            'covariance_3x3': covariance_matrix(terms).tolist(),
        })
    return converted


def jacobian(a, b):
    c, s = math.cos(a[2]), math.sin(a[2])
    dx, dy = b[0] - a[0], b[1] - a[1]
    return np.array([[-c, -s, -s * dx + c * dy, c, s, 0.],
                     [s, -c, -c * dx - s * dy, -s, c, 0.],
                     [0., 0., -1., 0., 0., 1.]])


def information(graph, exclude=()):
    nodes = {int(node['state_id']): node for node in graph['nodes']}
    ids = sorted(nodes)
    position = {state: index for index, state in enumerate(ids)}
    h = np.zeros((3 * len(ids), 3 * len(ids)))
    for edge in graph['edges']:
        if edge['index'] in exclude:
            continue
        a, b = int(edge['source_state_id']), int(edge['target_state_id'])
        if a not in nodes or b not in nodes:
            continue
        covariance = np.asarray(edge['covariance_3x3'], float)
        covariance = (covariance + covariance.T) / 2.0
        eig, vectors = np.linalg.eigh(covariance)
        floor = max(1e-9, float(np.max(np.abs(eig))) * 1e-12)
        omega = (vectors / np.maximum(eig, floor)) @ vectors.T
        pose_a = np.array([nodes[a]['x'], nodes[a]['y'], nodes[a]['theta']])
        pose_b = np.array([nodes[b]['x'], nodes[b]['y'], nodes[b]['theta']])
        j = jacobian(pose_a, pose_b)
        index = [3 * position[a] + k for k in range(3)] + \
                [3 * position[b] + k for k in range(3)]
        h[np.ix_(index, index)] += j.T @ omega @ j
    return (h + h.T) / 2.0, ids


def target_score(graph, target_ids):
    """J_T and its checks, exactly as in the earlier rounds."""
    h, ids = information(graph)
    if len(target_ids) != 5 or ids[0] in target_ids:
        raise ValueError('invalid target/root contract for {}'.format(target_ids))
    missing = [state for state in target_ids if state not in ids]
    if missing:
        raise ValueError('target states missing from graph: {}'.format(missing))
    reduced = h[3:, 3:]
    eigen = np.linalg.eigvalsh(reduced)
    if eigen.min() <= max(float(abs(eigen).max()), 1.0) * 1e-10:
        raise np.linalg.LinAlgError('singular anchored information')
    columns = [3 * ids.index(state) + k - 3 for state in target_ids
               for k in range(3)]
    select = np.eye(reduced.shape[0])[:, columns]
    solved = cho_solve(cho_factor(reduced, lower=True), select)
    marginal = (solved[columns, :] + solved[columns, :].T) / 2.0
    sign, logdet = np.linalg.slogdet(marginal)
    if sign <= 0:
        raise ValueError('nonpositive target marginal')
    return {
        'J_T': -float(logdet) / 15.0,
        'target_covariance_trace': float(np.trace(marginal)),
        'minimum_reduced_eigenvalue': float(eigen.min()),
        'reduced_condition_number': float(eigen.max() / eigen.min()),
        'root_state_id': int(ids[0]),
        'node_count': len(ids),
    }


def contiguous_edges(graph):
    """Split edges into odometry (consecutive ids) and loop-closure edges."""
    ids = {int(node['state_id']) for node in graph['nodes']}
    odometry, loop = [], []
    for edge in graph['edges']:
        a, b = int(edge['source_state_id']), int(edge['target_state_id'])
        if a not in ids or b not in ids:
            continue
        if b == a + 1:
            odometry.append(edge)
        else:
            loop.append(edge)
    return odometry, loop


def rigid_from_pose_pairs(source, target):
    return ge.align_rigid([p[:2] for p in source], [p[:2] for p in target])


def match_pose(pose, samples):
    best = None
    for sample in samples:
        distance = math.hypot(sample['x'] - pose[0], sample['y'] - pose[1])
        if best is None or distance < best[0]:
            best = (distance, sample)
    return best


def phase_bounds(result):
    marks = result['phase_scan_marks']
    action_start = int(result['action_start_scan_index'])
    frames = int(result['action_frames_target'])
    return {
        'history': (0, int(marks['history_end_scan'])),
        'return': (int(marks['return_start_scan']), action_start),
        'action': (action_start, action_start + frames),
        'tail': (action_start + frames, None),
    }


def slice_records(records, bounds):
    start, end = bounds
    if end is None:
        return [record for record in records if record['index'] >= start]
    return [record for record in records if start <= record['index'] < end]


def analyse_episode(run_dir):
    run_dir = Path(run_dir)
    spec = load_json(run_dir / 'episode_spec.json')
    result = load_json(run_dir / 'episode_result.json')
    frozen = load_json(run_dir / 'frozen_target.json')
    manifest = load_json(run_dir / 'manifest.json', {})
    scans = jsonl(run_dir / 'scan_stream.jsonl')
    ground_truth = jsonl(run_dir / 'gt_stream.jsonl')
    keyscans = jsonl(run_dir / 'keyscan_stream.jsonl')
    loops = jsonl(run_dir / 'loop_events.jsonl')
    snapshots = {}
    for name, filename in SNAPSHOT_FILES.items():
        snapshot = load_json(run_dir / filename)
        if snapshot is None:
            raise ValueError('missing snapshot {}'.format(filename))
        snapshots[name] = snapshot

    target_ids = [int(state) for state in frozen['target_state_ids']]
    reference = [float(value) for value in frozen['reference_mapper_pose']]
    anchor = frozen['anchor']

    # ---- phases ---------------------------------------------------------
    bounds = phase_bounds(result)
    episode = {
        'episode_id': spec['episode_id'],
        'place_id': spec['place_id'],
        'repeat': int(spec['repeat']),
        'action_id': spec['action_id'],
        'group_id': spec['group_id'],
        'group_index': int(spec['group_index']),
        'order_position': int(spec['order_position']),
        'protocol_version': spec['protocol_version'],
        'analysis_eligible': bool(result.get('analysis_eligible', False)),
        'reference_mapper_pose': reference,
        'anchor_state_id': int(anchor['id']),
        'anchor_distance_m': float(frozen['anchor_distance_m']),
        'anchor_heading_error_rad': float(frozen['anchor_heading_error_rad']),
        'segment_length': int(frozen['segment_length']),
        'target_state_ids': target_ids,
        'frozen_checks': frozen['checks'],
        'manifest_analysis_eligible': manifest.get('analysis_eligible'),
    }

    # ---- trajectory / cost ---------------------------------------------
    for phase, window in bounds.items():
        records = slice_records(scans, window)
        poses = [record['odom_base'] for record in records
                 if record['odom_base'] is not None]
        gt_samples = [record['map_base'] for record in records
                      if record['map_base'] is not None]
        episode['{}_scan_count'.format(phase)] = len(records)
        episode['{}_valid_count'.format(phase)] = sum(
            1 for record in records if record['finite_returns'] > 0
            and record['odom_base'] is not None)
        episode['{}_path_length_m'.format(phase)] = ge.path_length(poses)
        episode['{}_cumulative_rotation_rad'.format(phase)] = \
            ge.cumulative_rotation(poses)
        if records:
            episode['{}_duration_s'.format(phase)] = (
                records[-1]['stamp'] - records[0]['stamp'])
        else:
            episode['{}_duration_s'.format(phase)] = 0.0

    # ---- odometry vs ground truth (one frozen alignment per trajectory) --
    pairs = [(record['odom_base'], gt)
             for record, gt in zip(scans, _aligned_gt(scans, ground_truth))
             if record['odom_base'] is not None and gt is not None]
    if len(pairs) >= 2:
        odom_poses = [pair[0] for pair in pairs]
        gt_poses = [pair[1] for pair in pairs]
        transform = rigid_from_pose_pairs(odom_poses, gt_poses)
        episode['odom_gt_yaw_rad'] = transform[0]
        residuals = [math.hypot(moved[0] - truth[0], moved[1] - truth[1])
                     for moved, truth in zip(ge.apply_rigid(transform, odom_poses),
                                             gt_poses)]
        episode['odom_gt_residual_mean_m'] = float(np.mean(residuals))
        episode['odom_gt_residual_max_m'] = float(np.max(residuals))
        for phase, window in bounds.items():
            indices = [index for index, record in enumerate(scans)
                       if _in_window(record, window)]
            subset = [residuals[index] for index in indices
                      if index < len(residuals)]
            episode['{}_odom_gt_residual_mean_m'.format(phase)] = (
                float(np.mean(subset)) if subset else None)

    # ---- node <-> keyscan <-> ground truth matching --------------------
    node_stamps = match_nodes_to_keyscans(snapshots['G_before_return'], keyscans)
    episode['keyscan_match_fraction'] = (
        float(len(node_stamps)) / max(1, len(snapshot_graph(snapshots[
            'G_before_return'])['nodes'])))

    # ---- graph information at the four boundaries ----------------------
    graphs = {name: snapshot_graph(snapshot)
              for name, snapshot in snapshots.items()}
    scores, edge_stats = {}, {}
    for name, graph in graphs.items():
        try:
            scores[name] = target_score(graph, target_ids)
            scores[name]['valid'] = True
        except (ValueError, np.linalg.LinAlgError) as exc:
            scores[name] = {'valid': False, 'reason': '{}: {}'.format(
                type(exc).__name__, exc)}
        odometry, loop = contiguous_edges(graph)
        edge_stats[name] = {
            'nodes': len(graph['nodes']),
            'edges': len(graph['edges']),
            'odometry_edges': len(odometry),
            'loop_edges': len(loop),
            'loop_edge_indices': sorted(edge['index'] for edge in loop),
        }
    episode['J_T'] = {name: scores[name].get('J_T') for name in SNAPSHOTS}
    episode['J_T_valid'] = {name: scores[name]['valid'] for name in SNAPSHOTS}
    episode['graph_stats'] = edge_stats
    for name in SNAPSHOTS:
        episode['{}_nodes'.format(name)] = edge_stats[name]['nodes']
        episode['{}_edges'.format(name)] = edge_stats[name]['edges']
        episode['{}_loop_edges'.format(name)] = edge_stats[name]['loop_edges']
    first, second, third, fourth = (scores[name].get('J_T') for name in SNAPSHOTS)
    if all(value is not None for value in (first, second, third, fourth)):
        episode['return_gain'] = second - first
        episode['action_gain'] = third - second
        episode['tail_gain'] = fourth - third
        episode['total_gain'] = fourth - first
        episode['action_share_of_total'] = (
            episode['action_gain'] / episode['total_gain']
            if episode['total_gain'] > 1e-12 else None)

    # ---- edges created per phase (index-based, order-blind) ------------
    for before, after, label in (('G_before_return', 'G_arrival', 'return'),
                                 ('G_arrival', 'G_action_done', 'action'),
                                 ('G_action_done', 'G_final', 'tail')):
        known = {edge['index'] for edge in graphs[before]['edges']}
        added = [edge for edge in graphs[after]['edges']
                 if edge['index'] not in known]
        episode['{}_edges_added'.format(label)] = len(added)
        episode['{}_loop_edges_added'.format(label)] = sum(
            1 for edge in added
            if int(edge['target_state_id']) != int(edge['source_state_id']) + 1)

    # ---- real map error at the target states (frozen alignment) --------
    episode.update(target_residuals(graphs, node_stamps, ground_truth, frozen))

    # ---- observation-view geometry -------------------------------------
    episode.update(view_geometry(scans, bounds, ground_truth, node_stamps, frozen,
                                 keyscans))

    # ---- action execution summary --------------------------------------
    action_records = slice_records(scans, bounds['action'])
    action_poses = [record['odom_base'] for record in action_records
                    if record['odom_base'] is not None]
    if action_poses:
        episode['action_measured_rotation_rad'] = ge.cumulative_rotation(action_poses)
        episode['action_measured_path_m'] = ge.path_length(action_poses)
    episode['planned_cumulative_rotation_rad'] = float(
        spec['planned_cumulative_rotation_rad'])
    episode['max_abs_yaw_rad'] = float(spec['max_abs_yaw_rad'])
    episode['action_moves'] = result.get('action_moves', [])
    episode['action_goals'] = result.get('action_goals', [])
    episode['loop_event_count'] = len(loops)
    episode['loop_events'] = loops
    episode['scan_count'] = result.get('scan_count')
    episode['valid_scan_count'] = result.get('valid_scan_count')
    episode['run_dir'] = str(run_dir)
    return episode


def _in_window(record, window):
    start, end = window
    if end is None:
        return record['index'] >= start
    return start <= record['index'] < end


def _aligned_gt(scans, ground_truth):
    """GT pose nearest in time to each scan (None when the record is too old)."""
    if not ground_truth:
        return [None] * len(scans)
    stamps = [sample['stamp'] for sample in ground_truth]
    aligned = []
    cursor = 0
    for record in scans:
        while (cursor + 1 < len(stamps)
               and abs(stamps[cursor + 1] - record['stamp'])
               <= abs(stamps[cursor] - record['stamp'])):
            cursor += 1
        sample = ground_truth[cursor]
        if abs(sample['stamp'] - record['stamp']) > 0.5:
            aligned.append(None)
        else:
            aligned.append([sample['x'], sample['y'], sample['theta']])
    return aligned


def match_nodes_to_keyscans(snapshot, keyscans):
    """Map state id -> keyscan stamp by monotone nearest-pose matching.

    The mapper creates one state per accepted keyscan and publishes the accepted
    pose on ``/others``; matching by pose keeps the mapping honest and lets the
    analysis recover the time (and therefore the ground-truth pose) of every
    state without touching the mapper.
    """
    graph = snapshot_graph(snapshot)
    matches, cursor = {}, 0
    for node in graph['nodes']:
        best = None
        for index in range(cursor, len(keyscans)):
            sample = keyscans[index]
            distance = math.hypot(sample['x'] - node['x'], sample['y'] - node['y'])
            if best is None or distance < best[0]:
                best = (distance, index, sample)
            if distance < 1e-6:
                break
        if best is None or best[0] > 1.0:
            continue
        matches[node['state_id']] = {
            'stamp': float(best[2]['stamp']),
            'distance_m': float(best[0]),
            'keyscan_index': int(best[1]),
        }
        cursor = best[1]
    return matches


def gt_pose_at(stamp, ground_truth):
    if not ground_truth:
        return None
    best = min(ground_truth, key=lambda sample: abs(sample['stamp'] - stamp))
    if abs(best['stamp'] - stamp) > 0.5:
        return None
    return [best['x'], best['y'], best['theta']]


def target_residuals(graphs, node_stamps, ground_truth, frozen):
    """Map error at the frozen target states after one frozen map->GT alignment.

    The rigid transform is fitted once per episode on the states that exist at
    the pre-return boundary (the only states available before the action), then
    applied unchanged to the same state ids in the later snapshots.  Nothing in
    the fit uses the action label.
    """
    target_ids = [int(state) for state in frozen['target_state_ids']]
    first = {int(node['state_id']): node for node in graphs['G_before_return']['nodes']}
    source, target = [], []
    for state in target_ids:
        node = first.get(state)
        stamp = node_stamps.get(state, {}).get('stamp')
        truth = gt_pose_at(stamp, ground_truth) if stamp is not None else None
        if node is None or truth is None:
            continue
        source.append([node['x'], node['y'], node['theta']])
        target.append(truth)
    payload = {'target_alignment_pairs': len(source)}
    if len(source) < 2:
        return payload
    transform = rigid_from_pose_pairs(source, target)
    payload['target_alignment_yaw_rad'] = float(transform[0])
    payload['target_alignment_translation_m'] = float(
        math.hypot(transform[1], transform[2]))
    for name, graph in graphs.items():
        nodes = {int(node['state_id']): node for node in graph['nodes']}
        residuals, heading = [], []
        for state in target_ids:
            node = nodes.get(state)
            stamp = node_stamps.get(state, {}).get('stamp')
            truth = gt_pose_at(stamp, ground_truth) if stamp is not None else None
            if node is None or truth is None:
                continue
            moved = ge.pose_apply(transform, [node['x'], node['y'], node['theta']])
            residuals.append(math.hypot(moved[0] - truth[0], moved[1] - truth[1]))
            heading.append(abs(ge.wrap_angle(moved[2] - truth[2])))
        if residuals:
            payload['{}_target_error_mean_m'.format(name)] = float(np.mean(residuals))
            payload['{}_target_error_max_m'.format(name)] = float(np.max(residuals))
            payload['{}_target_heading_mean_rad'.format(name)] = float(np.mean(heading))
    return payload


def view_geometry(scans, bounds, ground_truth, node_stamps, frozen, keyscans=()):
    """Observation geometry of the place during the action phase.

    Two geometry families are reported.

    *Observation headings* (the primary statistic): the probe observes the place
    from the place during an in-place action, so the quantity the rotation
    changes is the *sensor orientation*, expressed in the map frame as
    ``anchor_theta + (odom yaw - odom yaw at action start)`` using the
    correction-free odometric stream.  The historical set is the frozen target
    states' own headings.  ``new_heading_fraction`` is the share of action-phase
    scans whose heading is at least ``NEW_VIEW_MARGIN_RAD`` away from every
    historical heading.

    *View bearings* (auxiliary): the bearing from the target reference to the
    probe, kept for the geometry tables.
    """
    reference = [float(value) for value in frozen['reference_mapper_pose']]
    anchor_theta = float(frozen.get('return_goal_pose',
                                    [frozen['anchor']['x'], frozen['anchor']['y'],
                                     frozen['anchor']['theta']])[2])
    historical_headings, historical_bearings = [], []
    for state in frozen['target_state_ids']:
        node = next((candidate for candidate in frozen['target_states']
                     if int(candidate['id']) == int(state)), None)
        if node is None:
            continue
        historical_headings.append(float(node['theta']))
        historical_bearings.append(math.atan2(node['y'] - reference[1],
                                              node['x'] - reference[0]))
    action_records = [record for record in slice_records(scans, bounds['action'])
                      if record['odom_base'] is not None
                      and record['finite_returns'] > 0]
    entry = slice_records(scans, bounds['action'])
    entry_yaw = None
    for record in entry:
        if record['odom_base'] is not None:
            entry_yaw = float(record['odom_base'][2])
            break
    headings, deflections, bearings = [], [], []
    for record in action_records:
        yaw = float(record['odom_base'][2])
        if entry_yaw is None:
            headings.append(anchor_theta)
        else:
            headings.append(ge.wrap_angle(anchor_theta + ge.wrap_angle(yaw - entry_yaw)))
        deflections.append(abs(ge.wrap_angle(headings[-1] - anchor_theta)))
        pose = record['odom_base']
        bearings.append(math.atan2(pose[1] - reference[1],
                                   pose[0] - reference[0]))
    payload = {
        'anchor_theta_rad': anchor_theta,
        'historical_heading_values_rad': historical_headings,
        'historical_heading_span_rad': (max(historical_headings)
                                        - min(historical_headings)
                                        if len(historical_headings) >= 2 else 0.0),
        'historical_view_directions_rad': historical_bearings,
        'action_yaw_values_rad': headings,
        'action_view_directions_rad': bearings,
        'max_heading_deflection_rad': max(deflections) if deflections else 0.0,
        'mean_heading_deflection_rad': float(np.mean(deflections)) if deflections else 0.0,
    }
    if headings and historical_headings:
        margins = [min(abs(ge.wrap_angle(heading - other))
                       for other in historical_headings) for heading in headings]
        payload['action_heading_margin_mean_rad'] = float(np.mean(margins))
        payload['action_heading_margin_max_rad'] = float(np.max(margins))
        payload['new_heading_fraction'] = (
            float(sum(1 for margin in margins if margin >= NEW_VIEW_MARGIN_RAD))
            / len(margins))
        # Backwards-compatible aliases used by the figures and tables.
        payload['action_new_view_fraction'] = payload['new_heading_fraction']
        payload['action_view_max_margin_rad'] = payload['action_heading_margin_max_rad']
        payload['action_view_mean_margin_rad'] = payload['action_heading_margin_mean_rad']
    # Mapper keyframe gate: how many states the action phase actually created.
    window = bounds['action']
    start_stamp = None
    end_stamp = None
    records = slice_records(scans, window)
    if records:
        start_stamp = records[0]['stamp']
        end_stamp = records[-1]['stamp']
    created = [sample for sample in keyscans
               if start_stamp is not None and end_stamp is not None
               and start_stamp <= float(sample['stamp']) <= end_stamp]
    payload['action_keyscans_created'] = len(created)
    payload['action_keyscan_stamps'] = [float(sample['stamp']) for sample in created]
    return payload


# --------------------------------------------------------------------- suite
def latest_run_dir(suite_dir, episode):
    attempts = episode.get('attempts', [])
    for attempt in reversed(attempts):
        if attempt.get('status') == 'SUCCEEDED':
            return Path(suite_dir) / attempt['run_dir']
    return None


def write_table(path, rows):
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text('')
        return
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def analyse_suite(suite_dir):
    suite_dir = Path(suite_dir)
    state = load_json(suite_dir / 'suite_state.json')
    if state is None:
        raise SystemExit('no suite_state.json under {}'.format(suite_dir))
    out_dir = suite_dir / 'analysis'
    out_dir.mkdir(parents=True, exist_ok=True)
    episodes, failures = [], []
    for episode in state['episodes']:
        run_dir = latest_run_dir(suite_dir, episode)
        if run_dir is None:
            failures.append({'episode_id': episode['episode_id'],
                             'status': episode['status']})
            continue
        try:
            episodes.append(analyse_episode(run_dir))
        except Exception as exc:  # keep the suite running, record the failure
            failures.append({'episode_id': episode['episode_id'],
                             'status': 'ANALYSIS_FAILED',
                             'reason': '{}: {}'.format(type(exc).__name__, exc),
                             'run_dir': str(run_dir)})

    write_table(out_dir / 'per_episode_metrics.csv', episodes)
    write_table(out_dir / 'stage_gains.csv', [
        {'episode_id': row['episode_id'], 'place_id': row['place_id'],
         'repeat': row['repeat'], 'action_id': row['action_id'],
         'J_T_before_return': row['J_T']['G_before_return'],
         'J_T_arrival': row['J_T']['G_arrival'],
         'J_T_action_done': row['J_T']['G_action_done'],
         'J_T_final': row['J_T']['G_final'],
         'return_gain': row.get('return_gain'),
         'action_gain': row.get('action_gain'),
         'tail_gain': row.get('tail_gain'),
         'total_gain': row.get('total_gain')} for row in episodes])
    write_table(out_dir / 'within_place_action_comparison.csv',
                within_place_table(episodes))
    write_table(out_dir / 'pre_state_differences.csv', pre_state_table(episodes))
    write_table(out_dir / 'constraint_provenance.csv', provenance_table(episodes))
    write_table(out_dir / 'analysis_failures.csv', failures)

    summary = {
        'suite_dir': str(suite_dir),
        'measurement_sensitivity': measurement_sensitivity(episodes),
        'episode_count_planned': len(state['episodes']),
        'episode_count_analysed': len(episodes),
        'analysis_failures': failures,
        'action_summary': action_summary(episodes),
        'place_action_summary': place_action_summary(episodes),
        'difference_summary': difference_summary(episodes),
        'view_summary': view_summary(episodes),
        'errors_vs_information': errors_vs_information(episodes),
        'cost_summary': cost_summary(episodes),
    }
    (out_dir / 'summary.json').write_text(json.dumps(summary, indent=1,
                                                     sort_keys=True, default=str))
    return summary


def measurement_sensitivity(episodes):
    """Capability check: can J_T see a constraint attached to the target?

    For every analysed episode the final graph is copied, one synthetic loop
    edge is added between a target state and another target state (or a nearby
    state when only one exists), and J_T is recomputed.  A nonzero response
    proves that a zero *measured* gain is a real null and not a blind metric.
    """
    rows = []
    for row in episodes:
        run_dir = Path(row['run_dir'])
        graph = snapshot_graph(load_json(run_dir / 'graph_final.json'))
        target_ids = [int(state) for state in row['target_state_ids']]
        if len(target_ids) < 2:
            continue
        base = target_score(graph, target_ids)['J_T']
        extended = {
            'nodes': list(graph['nodes']),
            'edges': list(graph['edges']) + [{
                'index': max(edge['index'] for edge in graph['edges']) + 1,
                'source_state_id': target_ids[0],
                'target_state_id': target_ids[-1],
                'covariance_3x3': [[0.02, 0.0, 0.0], [0.0, 0.02, 0.0],
                                   [0.0, 0.0, 0.02]],
            }],
        }
        try:
            changed = target_score(extended, target_ids)['J_T']
        except (ValueError, np.linalg.LinAlgError) as exc:
            rows.append({'episode_id': row['episode_id'],
                         'sensitivity_failed': '{}: {}'.format(
                             type(exc).__name__, exc)})
            continue
        rows.append({'episode_id': row['episode_id'],
                     'action_id': row['action_id'],
                     'place_id': row['place_id'],
                     'added_edge_J_T_gain': changed - base})
    return rows


def _mean(values):
    values = [value for value in values if value is not None]
    return float(np.mean(values)) if values else None


def _spread(values):
    values = [value for value in values if value is not None]
    return float(np.std(values)) if values else None


def within_place_table(episodes):
    rows = []
    groups = {}
    for row in episodes:
        groups.setdefault((row['place_id'], row['repeat']), {})[row['action_id']] = row
    for (place_id, repeat), arms in sorted(groups.items()):
        if len(arms) != 4:
            continue
        base = arms.get('S0')
        for action_id in cr.ACTION_IDS:
            arm = arms.get(action_id)
            if arm is None:
                continue
            rows.append({
                'place_id': place_id,
                'repeat': repeat,
                'action_id': action_id,
                'order_position': arm['order_position'],
                'return_gain': arm.get('return_gain'),
                'action_gain': arm.get('action_gain'),
                'tail_gain': arm.get('tail_gain'),
                'total_gain': arm.get('total_gain'),
                'action_gain_minus_S0': (arm.get('action_gain')
                                         - base.get('action_gain')
                                         if base and arm.get('action_gain') is not None
                                         and base.get('action_gain') is not None else None),
                'J_T_final': arm['J_T']['G_final'],
                'action_measured_rotation_rad': arm.get('action_measured_rotation_rad'),
                'action_duration_s': arm.get('action_duration_s'),
                'new_heading_fraction': arm.get('new_heading_fraction'),
                'max_heading_deflection_rad': arm.get('max_heading_deflection_rad'),
                'action_keyscans_created': arm.get('action_keyscans_created'),
                'G_action_done_target_error_mean_m': arm.get(
                    'G_action_done_target_error_mean_m'),
            })
    return rows


def pre_state_table(episodes):
    """Spread of the pre-action graph state inside each place/repeat group."""
    rows = []
    groups = {}
    for row in episodes:
        groups.setdefault((row['place_id'], row['repeat']), []).append(row)
    for (place_id, repeat), arms in sorted(groups.items()):
        if len(arms) != 4:
            continue
        for key in ('G_before_return_nodes', 'G_before_return_edges',
                    'G_arrival_nodes', 'G_arrival_edges',
                    'G_before_return_loop_edges', 'G_arrival_loop_edges'):
            values = [arm.get(key) for arm in arms]
            rows.append({
                'place_id': place_id, 'repeat': repeat, 'quantity': key,
                'min': min(values), 'max': max(values),
                'spread': max(values) - min(values),
                'mean': float(np.mean(values)),
                'relative_spread': ((max(values) - min(values))
                                    / max(1e-9, float(np.mean(values)))),
            })
        for key in ('J_T_before_return', 'J_T_arrival', 'anchor_distance_m',
                    'anchor_heading_error_rad', 'return_gain'):
            values = [arm['J_T']['G_before_return'] if key == 'J_T_before_return'
                      else arm['J_T']['G_arrival'] if key == 'J_T_arrival'
                      else arm.get(key) for arm in arms]
            values = [value for value in values if value is not None]
            if not values:
                continue
            rows.append({
                'place_id': place_id, 'repeat': repeat, 'quantity': key,
                'min': min(values), 'max': max(values),
                'spread': max(values) - min(values),
                'mean': float(np.mean(values)),
                'relative_spread': ((max(values) - min(values))
                                    / max(1e-9, abs(float(np.mean(values))))),
            })
    return rows


def provenance_table(episodes):
    rows = []
    for row in episodes:
        rows.append({
            'episode_id': row['episode_id'],
            'place_id': row['place_id'],
            'repeat': row['repeat'],
            'action_id': row['action_id'],
            'target_state_ids': ';'.join(str(state) for state in row['target_state_ids']),
            'return_edges_added': row.get('return_edges_added'),
            'return_loop_edges_added': row.get('return_loop_edges_added'),
            'action_edges_added': row.get('action_edges_added'),
            'action_loop_edges_added': row.get('action_loop_edges_added'),
            'tail_edges_added': row.get('tail_edges_added'),
            'tail_loop_edges_added': row.get('tail_loop_edges_added'),
            'loop_events': row.get('loop_event_count'),
            'new_heading_fraction': row.get('new_heading_fraction'),
            'max_heading_deflection_rad': row.get('max_heading_deflection_rad'),
            'action_heading_margin_mean_rad': row.get('action_heading_margin_mean_rad'),
            'action_keyscans_created': row.get('action_keyscans_created'),
            'historical_heading_span_rad': row.get('historical_heading_span_rad'),
        })
    return rows


def action_summary(episodes):
    summary = {}
    for action_id in cr.ACTION_IDS:
        arms = [row for row in episodes if row['action_id'] == action_id]
        if not arms:
            continue
        summary[action_id] = {
            'episodes': len(arms),
            'planned_rotation_rad': arms[0]['planned_cumulative_rotation_rad'],
            'measured_rotation_mean_rad': _mean(
                [arm.get('action_measured_rotation_rad') for arm in arms]),
            'measured_rotation_spread_rad': _spread(
                [arm.get('action_measured_rotation_rad') for arm in arms]),
            'measured_path_mean_m': _mean(
                [arm.get('action_measured_path_m') for arm in arms]),
            'duration_mean_s': _mean([arm.get('action_duration_s') for arm in arms]),
            'return_gain_mean': _mean([arm.get('return_gain') for arm in arms]),
            'return_gain_spread': _spread([arm.get('return_gain') for arm in arms]),
            'action_gain_mean': _mean([arm.get('action_gain') for arm in arms]),
            'action_gain_spread': _spread([arm.get('action_gain') for arm in arms]),
            'action_gain_positive_fraction': _mean(
                [1.0 if (arm.get('action_gain') or 0) > 0 else 0.0 for arm in arms]),
            'tail_gain_mean': _mean([arm.get('tail_gain') for arm in arms]),
            'total_gain_mean': _mean([arm.get('total_gain') for arm in arms]),
            'action_loop_edges_mean': _mean(
                [arm.get('action_loop_edges_added') for arm in arms]),
            'action_new_heading_fraction_mean': _mean(
                [arm.get('new_heading_fraction') for arm in arms]),
            'action_new_heading_fraction_spread': _spread(
                [arm.get('new_heading_fraction') for arm in arms]),
            'max_heading_deflection_mean_rad': _mean(
                [arm.get('max_heading_deflection_rad') for arm in arms]),
            'action_keyscans_created_mean': _mean(
                [arm.get('action_keyscans_created') for arm in arms]),
            'action_keyscans_created_spread': _spread(
                [arm.get('action_keyscans_created') for arm in arms]),
            'action_share_of_total_mean': _mean(
                [arm.get('action_share_of_total') for arm in arms]),
        }
    return summary


def place_action_summary(episodes):
    summary = {}
    for place_id in cr.PLACE_IDS:
        summary[place_id] = {}
        for action_id in cr.ACTION_IDS:
            arms = [row for row in episodes
                    if row['place_id'] == place_id and row['action_id'] == action_id]
            if not arms:
                continue
            summary[place_id][action_id] = {
                'episodes': len(arms),
                'return_gain_mean': _mean([arm.get('return_gain') for arm in arms]),
                'action_gain_mean': _mean([arm.get('action_gain') for arm in arms]),
                'tail_gain_mean': _mean([arm.get('tail_gain') for arm in arms]),
                'total_gain_mean': _mean([arm.get('total_gain') for arm in arms]),
                'action_measured_rotation_mean_rad': _mean(
                    [arm.get('action_measured_rotation_rad') for arm in arms]),
            }
    return summary


def difference_summary(episodes):
    """Paired L+ - L-, L+ - S1 and L+ - S0 differences inside each group."""
    payload = {}
    groups = {}
    for row in episodes:
        groups.setdefault((row['place_id'], row['repeat']), {})[row['action_id']] = row
    for pair in (('L+', 'L-'), ('L+', 'S1'), ('L+', 'S0'), ('S1', 'S0'),
                 ('L-', 'S0'), ('L-', 'S1')):
        gains, views, rotations = [], [], []
        for (place_id, repeat), arms in sorted(groups.items()):
            first, second = arms.get(pair[0]), arms.get(pair[1])
            if first is None or second is None:
                continue
            if first.get('action_gain') is None or second.get('action_gain') is None:
                continue
            gains.append(first['action_gain'] - second['action_gain'])
            if (first.get('new_heading_fraction') is not None
                    and second.get('new_heading_fraction') is not None):
                views.append(first['new_heading_fraction']
                             - second['new_heading_fraction'])
            if (first.get('action_measured_rotation_rad') is not None
                    and second.get('action_measured_rotation_rad') is not None):
                rotations.append(first['action_measured_rotation_rad']
                                 - second['action_measured_rotation_rad'])
        if gains:
            payload['{}_{}'.format(*pair)] = {
                'groups': len(gains),
                'action_gain_mean': float(np.mean(gains)),
                'action_gain_min': float(np.min(gains)),
                'action_gain_max': float(np.max(gains)),
                'action_gain_positive_groups': int(sum(1 for value in gains
                                                        if value > 0)),
                'action_gain_values': gains,
                'new_heading_fraction_mean': _mean(views),
                'measured_rotation_mean_rad': _mean(rotations),
            }
    return payload


def view_summary(episodes):
    summary = {}
    for action_id in cr.ACTION_IDS:
        arms = [row for row in episodes if row['action_id'] == action_id
                and row.get('action_new_view_fraction') is not None]
        if not arms:
            continue
        summary[action_id] = {
            'episodes': len(arms),
            'new_heading_fraction_mean': _mean(
                [arm['new_heading_fraction'] for arm in arms]),
            'new_heading_fraction_spread': _spread(
                [arm['new_heading_fraction'] for arm in arms]),
            'max_heading_deflection_mean_rad': _mean(
                [arm.get('max_heading_deflection_rad') for arm in arms]),
            'max_margin_mean_rad': _mean(
                [arm.get('action_heading_margin_max_rad') for arm in arms]),
            'historical_heading_span_mean_rad': _mean(
                [arm.get('historical_heading_span_rad') for arm in arms]),
            'action_keyscans_created_mean': _mean(
                [arm.get('action_keyscans_created') for arm in arms]),
        }
    return summary


def errors_vs_information(episodes):
    rows = []
    for row in episodes:
        rows.append({
            'episode_id': row['episode_id'],
            'place_id': row['place_id'],
            'action_id': row['action_id'],
            'return_gain': row.get('return_gain'),
            'action_gain': row.get('action_gain'),
            'G_arrival_target_error_mean_m': row.get('G_arrival_target_error_mean_m'),
            'G_action_done_target_error_mean_m': row.get('G_action_done_target_error_mean_m'),
            'G_final_target_error_mean_m': row.get('G_final_target_error_mean_m'),
        })
    payload = {'rows': rows}
    for stage, gain_key in (('return', 'return_gain'), ('action', 'action_gain')):
        pairs = [(row[gain_key],
                  row['G_arrival_target_error_mean_m' if stage == 'return'
                      else 'G_action_done_target_error_mean_m'],
                  row['G_before_return_target_error_mean_m' if stage == 'return'
                      else 'G_arrival_target_error_mean_m'])
                 for row in episodes
                 if row.get(gain_key) is not None]
        pairs = [pair for pair in pairs if pair[1] is not None and pair[2] is not None]
        if len(pairs) >= 3:
            gains = np.array([pair[0] for pair in pairs], float)
            delta = np.array([pair[1] - pair[2] for pair in pairs], float)
            payload[stage] = {
                'samples': len(pairs),
                'gain_mean': float(gains.mean()),
                'error_delta_mean_m': float(delta.mean()),
                'pearson_r': (float(np.corrcoef(gains, delta)[0, 1])
                              if np.std(gains) > 0 and np.std(delta) > 0 else None),
            }
    return payload


def cost_summary(episodes):
    payload = {}
    for action_id in cr.ACTION_IDS:
        arms = [row for row in episodes if row['action_id'] == action_id]
        if not arms:
            continue
        payload[action_id] = {
            'episodes': len(arms),
            'action_duration_mean_s': _mean([arm.get('action_duration_s') for arm in arms]),
            'action_path_mean_m': _mean([arm.get('action_measured_path_m') for arm in arms]),
            'action_rotation_mean_rad': _mean(
                [arm.get('action_measured_rotation_rad') for arm in arms]),
            'total_duration_mean_s': _mean([
                sum(arm.get('{}_duration_s'.format(phase)) or 0.0
                    for phase in PHASE_ORDER) for arm in arms]),
        }
    return payload


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('suite_dir')
    args = parser.parse_args()
    summary = analyse_suite(Path(args.suite_dir))
    print(json.dumps({
        'episodes_analysed': summary['episode_count_analysed'],
        'analysis_failures': len(summary['analysis_failures']),
    }, indent=1))


if __name__ == '__main__':
    main()
