#!/usr/bin/python3
"""Doc-80 offline review: shared loading, geometry and stage utilities.

Read-only with respect to every Doc-77/78/79 artifact.  All functions here are
pure (files -> data); no module in this package writes outside the Doc-80
results root.
"""

import json
import math
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

DOC79 = REPO / 'results/realizability_pilot/p1_doc79_synchronous_revisit_validation_20261012'
DOC80 = REPO / 'results/realizability_pilot/p1_doc80_offline_research_convergence_20261013'

STAGES = ('before_return', 'arrival', 'action_done', 'final')
BOUNDARY_OF = {'before_return': 'G_before_return', 'arrival': 'G_arrival',
               'action_done': 'G_action_done', 'final': 'G_final'}

#: Base-in-laser static transform recovered from the Stage world
#: (`hokuyolaser(pose [0.2 0 -0.2 0])`) and cross-checked against the runtime
#: TF records.  Position of the base origin expressed in the laser frame.
T_LASER_BASE = (-0.2, 0.0, 0.0)
TARGET_GT_TOLERANCE_S = 0.1


# ---------------------------------------------------------------- basics
def load_json(path, default=None):
    path = Path(path)
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return default


def jsonl(path):
    path = Path(path)
    if not path.is_file():
        return []
    rows = []
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def wrap(value):
    return math.atan2(math.sin(float(value)), math.cos(float(value)))


# ---------------------------------------------------------------- SE(2)
def compose(first, second):
    """T1 o T2 for poses (x, y, yaw)."""
    c, s = math.cos(first[2]), math.sin(first[2])
    return (first[0] + c * second[0] - s * second[1],
            first[1] + s * second[0] + c * second[1],
            wrap(first[2] + second[2]))


def inverse(pose):
    c, s = math.cos(pose[2]), math.sin(pose[2])
    return (-(c * pose[0] + s * pose[1]),
            -(-s * pose[0] + c * pose[1]),
            wrap(-pose[2]))


def between(reference, pose):
    """Pose of ``pose`` expressed in the ``reference`` frame."""
    return compose(inverse(reference), pose)


def translation_error(first, second):
    return math.hypot(first[0] - second[0], first[1] - second[1])


def rotation_error(first, second):
    return abs(wrap(first[2] - second[2]))


def apply_transform(transform, point, yaw=0.0):
    c, s = math.cos(transform[0]), math.sin(transform[0])
    return (transform[1] + c * point[0] - s * point[1],
            transform[2] + s * point[0] + c * point[1],
            wrap(transform[0] + yaw))


# ---------------------------------------------------------------- stage windows
def windows(result):
    marks = result.get('phase_scan_marks') or {}
    action_start = result.get('action_start_scan_index')
    frames = result.get('action_frames_target')
    if action_start is None or frames is None:
        return None
    return {
        'history': (0, int(marks.get('history_end_scan', 0))),
        'return': (int(marks.get('return_start_scan', 0)), int(action_start)),
        'action': (int(action_start), int(action_start) + int(frames)),
        'tail': (int(action_start) + int(frames), None),
    }


def in_window(index, window):
    start, end = window
    return index >= start and (end is None or index < end)


def stage_of_index(index, stage_windows):
    for name in ('history', 'return', 'action', 'tail'):
        if in_window(index, stage_windows[name]):
            return name
    return None


def stage_of_stamp(stamp, scans, stage_windows):
    """Stage of the scan whose stamp is nearest ``stamp``."""
    if not scans:
        return None
    best = min(scans, key=lambda record: abs(record['stamp'] - float(stamp)))
    if abs(best['stamp'] - float(stamp)) > 0.5:
        return None
    return stage_of_index(best['index'], stage_windows)


# ---------------------------------------------------------------- run loading
def discover_attempts(doc79_root=DOC79):
    runs = []
    runs_dir = Path(doc79_root) / 'runs'
    if not runs_dir.is_dir():
        return runs
    for episode_dir in sorted(runs_dir.iterdir()):
        if not episode_dir.is_dir():
            continue
        for attempt_dir in sorted(episode_dir.iterdir()):
            if not attempt_dir.is_dir():
                continue
            runs.append({
                'episode_id': episode_dir.name,
                'attempt': attempt_dir.name,
                'attempt_dir': attempt_dir,
                'spec': load_json(attempt_dir / 'episode_spec.json', {}) or {},
                'manifest': load_json(attempt_dir / 'run_manifest.json', {}) or {},
                'state': load_json(attempt_dir / 'run_state.json', {}) or {},
                'result': load_json(attempt_dir / 'episode_result.json', {}) or {},
                'frozen': load_json(attempt_dir / 'frozen_target.json', {}) or {},
                'boundary_manifest': load_json(
                    attempt_dir / 'boundary_manifest.json', {}) or {},
            })
    return runs


def valid_runs(doc79_root=DOC79):
    return [run for run in discover_attempts(doc79_root)
            if run['manifest'].get('technical_validity') == 'MEASUREMENT_VALIDATED']


def sync_graph(run, stem, keys='state_id'):
    """Sync dump nodes normalised to the driver schema (id/x/y/theta).

    ``keys='state_id'`` keeps state identity; the driver's ``freeze_target``
    reads ``id``, which for the topic payload equals the vertex index.  Dump
    ``index`` and ``state_id`` are verified equal in the Doc-80 frame audit.
    """
    payload = load_json(run['attempt_dir'] / 'graph_{}_sync.json'.format(stem))
    if payload is None:
        return None
    nodes = []
    for node in payload['nodes']:
        nodes.append({
            'id': int(node['state_id']) if keys == 'state_id' else int(node['index']),
            'state_id': int(node['state_id']),
            'unique_id': int(node['unique_id']),
            'x': float(node['x']), 'y': float(node['y']),
            'theta': float(node['theta']),
        })
    edges = []
    for edge in payload['edges']:
        edges.append({
            'index': int(edge['index']),
            'source_state_id': int(edge['source_state_id']),
            'target_state_id': int(edge['target_state_id']),
            'source_unique_id': int(edge['source_unique_id']),
            'target_unique_id': int(edge['target_unique_id']),
            'covariance_3x3': edge.get('covariance_3x3'),
        })
    return {'run_id': payload.get('run_id'), 'nodes': nodes, 'edges': edges}


def graph_as_analysis(graph):
    """Sync graph -> frozen ``target_score`` schema (state ids)."""
    return {
        'nodes': [{'state_id': node['state_id'], 'unique_id': node['unique_id'],
                   'x': node['x'], 'y': node['y'], 'theta': node['theta']}
                  for node in graph['nodes']],
        'edges': [{'index': edge['index'],
                   'source_state_id': edge['source_state_id'],
                   'target_state_id': edge['target_state_id'],
                   'covariance_3x3': edge['covariance_3x3']}
                  for edge in graph['edges']
                  if edge.get('covariance_3x3') is not None],
    }


def topic_payload(run, stem):
    return load_json(run['attempt_dir'] / 'graph_{}_topic.json'.format(stem))


def accepts(run):
    """PHASE2C_KEYSCAN_ACCEPTED records from the per-attempt rosout copy."""
    import re
    pattern = re.compile(
        r'PHASE2C_KEYSCAN_ACCEPTED unique_id=(\d+) state_id=(\d+) sim_time=([0-9.]+)')
    records = []
    path = run['attempt_dir'] / 'rosout.log'
    if path.is_file():
        with open(path, errors='ignore') as handle:
            for line in handle:
                match = pattern.search(line)
                if match:
                    records.append({'unique_id': int(match.group(1)),
                                    'state_id': int(match.group(2)),
                                    'sim_time': float(match.group(3))})
    return sorted(records, key=lambda item: item['state_id'])


def gt_pose_at(gt_stream, stamp, tolerance=TARGET_GT_TOLERANCE_S):
    """Bracketed linear x/y and shortest-arc yaw interpolation over GT.

    Primary path: when ``stamp`` is bracketed by two samples at most
    ``2 * tolerance`` apart, interpolate (x/y linear, yaw shortest arc) and
    record the bracket span.  Fallback: the nearest sample when within
    ``tolerance``.  Otherwise None (NOT_EVALUABLE).
    """
    if not gt_stream:
        return None
    lower = None
    upper = None
    for index in range(len(gt_stream) - 1, -1, -1):
        if gt_stream[index]['stamp'] <= stamp:
            lower = gt_stream[index]
            break
    for index in range(len(gt_stream)):
        if gt_stream[index]['stamp'] >= stamp:
            upper = gt_stream[index]
            break
    if lower is not None and upper is not None and lower is not upper:
        span = upper['stamp'] - lower['stamp']
        if 0.0 < span <= 2.0 * tolerance:
            ratio = (stamp - lower['stamp']) / span
            return {'stamp': float(stamp),
                    'x': lower['x'] + ratio * (upper['x'] - lower['x']),
                    'y': lower['y'] + ratio * (upper['y'] - lower['y']),
                    'theta': wrap(lower['theta'] +
                                  ratio * wrap(upper['theta'] - lower['theta'])),
                    'gap_s': 0.0, 'span_s': span, 'interpolated': True}
    best = min(range(len(gt_stream)),
               key=lambda i: abs(gt_stream[i]['stamp'] - float(stamp)))
    sample = gt_stream[best]
    if abs(sample['stamp'] - float(stamp)) <= tolerance:
        return {'stamp': sample['stamp'], 'x': sample['x'], 'y': sample['y'],
                'theta': sample['theta'],
                'gap_s': abs(sample['stamp'] - float(stamp)),
                'span_s': None, 'interpolated': False}
    return None


def scan_at(scans, stamp, tolerance=0.05):
    if not scans:
        return None
    best = min(scans, key=lambda record: abs(record['stamp'] - float(stamp)))
    if abs(best['stamp'] - float(stamp)) <= tolerance:
        return best
    return None


def write_csv(path, rows):
    import csv
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text('')
        return
    keys = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with open(path, 'w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=True, default=str))
