#!/usr/bin/python3
"""Doc-79 offline analysis: synchronous dumps only, everything re-derivable.

Reads ``runs/<episode>/attempt_NN`` and writes ``analysis/*.csv`` plus
``analysis/final_gate.json``.  Primary information values come from the
synchronous pose-graph dumps; topic caches are used only for the
topic-vs-sync comparison.  Any sub-graph / edge-removal value is labelled
``FIXED_LINEARIZATION_FACTOR_DIAGNOSTIC`` and kept out of the primary columns
(guard: ``checks.check_gain_sources_agree``).
"""

import csv
import json
import math
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
for candidate in (THIS_DIR, THIS_DIR.parent,
                  THIS_DIR.parent / 'continuous_revisit'):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import checks as ck  # noqa: E402

import analysis as an  # noqa: E402  (frozen J_T implementation)
import geometry as ge  # noqa: E402

SYNC_STEMS = ('before_return', 'arrival', 'action_done', 'final')
BOUNDARY_OF_STEM = {'before_return': 'G_before_return', 'arrival': 'G_arrival',
                    'action_done': 'G_action_done', 'final': 'G_final'}
NEW_VIEW_MARGIN_RAD = math.radians(15.0)
KEYFRAME_HEADING_GATE_RAD = 0.52
KEYFRAME_TRAVEL_GATE_M = 1.0
TARGET_GT_TOLERANCE_S = 0.1
ACCEPT_RE = re.compile(
    r'PHASE2C_KEYSCAN_ACCEPTED unique_id=(\d+) state_id=(\d+) sim_time=([0-9.]+)')


# ------------------------------------------------------------------ loading
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
    records = []
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def sha256_file(path):
    import hashlib
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def sync_graph_to_analysis(payload):
    """Mapper dump schema -> the frozen J_T graph schema (laser poses)."""
    return {
        'nodes': [{'state_id': int(node['state_id']),
                   'unique_id': int(node['unique_id']),
                   'x': float(node['x']), 'y': float(node['y']),
                   'theta': float(node['theta'])}
                  for node in payload['nodes']],
        'edges': [{'index': int(edge['index']),
                   'source_state_id': int(edge['source_state_id']),
                   'target_state_id': int(edge['target_state_id']),
                   'covariance_3x3': edge['covariance_3x3']}
                  for edge in payload['edges']
                  if edge.get('covariance_3x3') is not None],
    }


def parse_accepts(run_dir):
    path = Path(run_dir) / 'rosout.log'
    accepts = []
    if path.is_file():
        with open(path, errors='ignore') as handle:
            for line in handle:
                match = ACCEPT_RE.search(line)
                if match:
                    accepts.append({'unique_id': int(match.group(1)),
                                    'state_id': int(match.group(2)),
                                    'sim_time': float(match.group(3))})
    return sorted(accepts, key=lambda item: item['state_id'])


def discover_runs(suite_dir):
    runs = []
    runs_dir = Path(suite_dir) / 'runs'
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
                'attempt_dir': attempt_dir,
                'attempt': attempt_dir.name,
                'spec': load_json(attempt_dir / 'episode_spec.json', {}) or {},
                'manifest': load_json(attempt_dir / 'run_manifest.json', {}) or {},
                'state': load_json(attempt_dir / 'run_state.json', {}) or {},
                'result': load_json(attempt_dir / 'episode_result.json', {}) or {},
                'boundary_manifest': load_json(attempt_dir / 'boundary_manifest.json', {}) or {},
            })
    return runs


def pose_at(samples, stamp, tolerance):
    """Nearest sample (no interpolation) with a hard tolerance."""
    best = None
    for sample in samples:
        gap = abs(float(sample['stamp']) - float(stamp))
        if best is None or gap < best[0]:
            best = (gap, sample)
    if best is None or best[0] > tolerance:
        return None
    return best[1]


def stage_windows(result):
    marks = result.get('phase_scan_marks', {})
    action_start = result.get('action_start_scan_index')
    frames = result.get('action_frames_target')
    if action_start is None or frames is None:
        return None
    windows = {
        'history': (0, int(marks.get('history_end_scan', 0))),
        'return': (int(marks.get('return_start_scan', 0)), int(action_start)),
        'action': (int(action_start), int(action_start) + int(frames)),
        'tail': (int(action_start) + int(frames), None),
    }
    return windows


def in_window(index, window):
    start, end = window
    return index >= start and (end is None or index < end)


# ------------------------------------------------------------------ metrics
def episode_metrics(run):
    attempt_dir = run['attempt_dir']
    spec = run['spec']
    result = run['result']
    frozen = load_json(attempt_dir / 'frozen_target.json', {}) or {}
    scans = jsonl(attempt_dir / 'scan_stream.jsonl')
    keyscans = jsonl(attempt_dir / 'keyscan_stream.jsonl')
    accepts = parse_accepts(attempt_dir)
    sync_payloads = {stem: load_json(attempt_dir /
                                     'graph_{}_sync.json'.format(stem))
                     for stem in SYNC_STEMS}
    graphs = {stem: (sync_graph_to_analysis(payload) if payload else None)
              for stem, payload in sync_payloads.items()}
    targets = [int(state) for state in frozen.get('target_state_ids', [])]

    row = {
        'episode_id': run['episode_id'],
        'attempt': run['attempt'],
        'run_id': spec.get('provenance_run_id'),
        'place': spec.get('place_id'),
        'action': spec.get('action_id'),
        'seed': spec.get('tsp_seed'),
        'doc79_order': spec.get('doc79_order'),
        'run_index': spec.get('doc79_run_index'),
        'technical_validity': run['manifest'].get('technical_validity'),
        'actual_rotation_rad': result.get('action_cumulative_rotation_rad'),
        'planned_rotation_rad': spec.get('planned_cumulative_rotation_rad'),
        'action_path_m': result.get('action_path_length_m'),
        'native_scans_driver': len(scans),
        'keyscans_accepted_driver': len(keyscans),
        'accept_log_states': len(accepts),
    }

    scores = {}
    for stem in SYNC_STEMS:
        graph = graphs.get(stem)
        if graph is None or not targets:
            scores[stem] = None
            continue
        try:
            scores[stem] = an.target_score(graph, targets)['J_T']
        except Exception:  # noqa: BLE001
            scores[stem] = None
        row['nodes_{}_sync'.format(stem)] = len(graph['nodes'])
        row['edges_{}_sync'.format(stem)] = len(graph['edges'])
        row['J_{}_sync'.format(stem)] = scores[stem]
    if all(scores.get(stem) is not None for stem in SYNC_STEMS):
        row['delta_J_return_sync'] = scores['arrival'] - scores['before_return']
        row['delta_J_action_sync'] = scores['action_done'] - scores['arrival']
        row['delta_J_tail_sync'] = scores['final'] - scores['action_done']
        row['delta_J_total_sync'] = scores['final'] - scores['before_return']
        row['gain_source'] = 'SYNCHRONOUS_DUMP'
    else:
        for key in ('delta_J_return_sync', 'delta_J_action_sync',
                    'delta_J_tail_sync', 'delta_J_total_sync'):
            row[key] = None
        row['gain_source'] = 'SYNCHRONOUS_DUMP_INCOMPLETE'

    # ---- identity audits -------------------------------------------------
    seq_audit = ck.scan_identity_audit(scans, key='seq')
    stamp_audit = ck.scan_identity_audit(scans, key='stamp')
    row['scan_seq_duplicates'] = seq_audit['duplicates']
    row['scan_seq_regressions'] = seq_audit['regressions']
    row['scan_stamp_duplicates'] = stamp_audit['duplicates']
    row['scan_stamp_regressions'] = stamp_audit['regressions']

    # ---- observation duration -------------------------------------------
    windows = stage_windows(result)
    if windows and scans:
        stamps_by_index = {record['index']: record['stamp'] for record in scans}
        start, end = windows['action']
        end_index = end - 1
        if start in stamps_by_index and end_index in stamps_by_index:
            row['observation_duration_s'] = stamps_by_index[end_index] - stamps_by_index[start]
    return row, {'graphs': graphs, 'scores': scores, 'frozen': frozen,
                 'scans': scans, 'keyscans': keyscans, 'accepts': accepts,
                 'sync_payloads': sync_payloads, 'result': result,
                 'spec': spec, 'attempt_dir': attempt_dir, 'windows': windows,
                 'targets': targets}


def target_base_poses(context):
    """Target/anchor states expressed in the base frame via recorded scan poses.

    Mapper node poses are laser poses; the driver records the TF-resolved
    ``map -> base_link`` pose for every scan stamp, so each accepted state can
    be compared to GT in one common reference point without assuming an
    unrecorded lever arm.
    """
    accepts = {item['state_id']: item for item in context['accepts']}
    scans = context['scans']
    stamps = [record['stamp'] for record in scans]
    base_pose = {}
    for state in list(context['targets']) + [int(context['frozen'].get('anchor', {}).get('id', -1))]:
        item = accepts.get(state)
        if item is None:
            base_pose[state] = None
            continue
        import bisect
        position = bisect.bisect_left(stamps, item['sim_time'])
        best = None
        for candidate in (position - 1, position, position + 1):
            if 0 <= candidate < len(scans):
                gap = abs(scans[candidate]['stamp'] - item['sim_time'])
                if best is None or gap < best[0]:
                    best = (gap, scans[candidate])
        if best is None or best[0] > 0.05 or best[1].get('map_base') is None:
            base_pose[state] = None
        else:
            base_pose[state] = list(best[1]['map_base'])
    return base_pose


def corrected_gt_rows(run, context, gt_stream):
    row_inputs = {}
    windows = context['windows']
    scans = context['scans']
    if windows is None:
        return [], row_inputs
    # pre-action alignment fitted on history + return scans only
    pairs = []
    for record in scans:
        if record.get('map_base') is None:
            continue
        stage = None
        for name in ('history', 'return', 'action', 'tail'):
            if in_window(record['index'], windows[name]):
                stage = name
                break
        if stage not in ('history', 'return'):
            continue
        truth = pose_at(gt_stream, record['stamp'], TARGET_GT_TOLERANCE_S)
        if truth is None:
            continue
        pairs.append((record['map_base'], [truth['x'], truth['y'], truth['theta']]))
    if len(pairs) < 2:
        return [], {'GT_EFFECT_NOT_ESTIMABLE': True}
    transform = ge.align_rigid([pair[0][:2] for pair in pairs],
                               [pair[1][:2] for pair in pairs])
    row_inputs['alignment_yaw_rad'] = transform[0]
    row_inputs['alignment_translation_m'] = math.hypot(transform[1], transform[2])

    rows = []
    def emit(family, stage, metric, value, n, notes=''):
        rows.append({'episode_id': run['episode_id'], 'attempt': run['attempt'],
                     'family': family, 'stage': stage, 'metric': metric,
                     'value': value, 'n': n, 'notes': notes})

    # A. robot localisation error (map pose vs GT) per stage
    per_stage = {}
    for record in scans:
        if record.get('map_base') is None:
            continue
        truth = pose_at(gt_stream, record['stamp'], TARGET_GT_TOLERANCE_S)
        if truth is None:
            continue
        moved = ge.pose_apply(transform, record['map_base'])
        error = math.hypot(moved[0] - truth['x'], moved[1] - truth['y'])
        for name in ('history', 'return', 'action', 'tail'):
            if in_window(record['index'], windows[name]):
                per_stage.setdefault(name, []).append(error)
                break
    for name in ('history', 'return', 'action', 'tail'):
        values = per_stage.get(name) or []
        if values:
            emit('ROBOT_LOCALIZATION_ERROR', name, 'mean_m',
                 statistics.mean(values), len(values),
                 'SLAM map pose vs GT, pre-action alignment')
            emit('ROBOT_LOCALIZATION_ERROR', name, 'max_m', max(values),
                 len(values), 'SLAM map pose vs GT, pre-action alignment')

    # B. frozen-target map error per synchronous boundary
    base_poses = target_base_poses(context)
    stamp_of_state = {item['state_id']: item['sim_time'] for item in context['accepts']}
    for stem in SYNC_STEMS:
        graph = context['graphs'].get(stem)
        if graph is None:
            continue
        residuals = []
        for state in context['targets']:
            pose = base_poses.get(state)
            stamp = stamp_of_state.get(state)
            if pose is None or stamp is None:
                continue
            truth = pose_at(gt_stream, stamp, TARGET_GT_TOLERANCE_S)
            if truth is None:
                continue
            moved = ge.pose_apply(transform, pose)
            residuals.append(math.hypot(moved[0] - truth['x'], moved[1] - truth['y']))
        if residuals:
            emit('TARGET_MAP_ERROR', stem, 'mean_m', statistics.mean(residuals),
                 len(residuals), 'base-frame target state vs GT')
            emit('TARGET_MAP_ERROR', stem, 'max_m', max(residuals),
                 len(residuals), 'base-frame target state vs GT')

    # C. SE(2) relative pose error (robot vs anchor) in the action window
    anchor_state = int(context['frozen'].get('anchor', {}).get('id', -1))
    anchor_pose = base_poses.get(anchor_state)
    anchor_stamp = stamp_of_state.get(anchor_state)
    anchor_truth = pose_at(gt_stream, anchor_stamp, TARGET_GT_TOLERANCE_S) if anchor_stamp else None
    if anchor_pose is not None and anchor_truth is not None:
        translations, rotations = [], []
        for record in scans:
            if record.get('map_base') is None or not in_window(record['index'], windows['action']):
                continue
            truth = pose_at(gt_stream, record['stamp'], TARGET_GT_TOLERANCE_S)
            if truth is None:
                continue
            robot_pose = record['map_base']
            robot_truth = [truth['x'], truth['y'], truth['theta']]
            rel_est = ck.se2_between(tuple(anchor_pose), tuple(robot_pose))
            rel_gt = ck.se2_between(
                (anchor_truth['x'], anchor_truth['y'], anchor_truth['theta']),
                tuple(robot_truth))
            translation, rotation = ck.se2_error(rel_est, rel_gt)
            translations.append(translation)
            rotations.append(rotation)
        if translations:
            emit('RELATIVE_POSE_ERROR', 'action', 'translation_mean_m',
                 statistics.mean(translations), len(translations),
                 'SE(2) T_error, base-frame anchor vs robot')
            emit('RELATIVE_POSE_ERROR', 'action', 'rotation_mean_rad',
                 statistics.mean(rotations), len(rotations),
                 'SE(2) T_error, base-frame anchor vs robot')
    return rows, row_inputs


def pre_action_features(run, context, gt_stream):
    """The two frozen pre-action candidates, plus outcome columns."""
    windows = context['windows']
    scans = context['scans']
    frozen = context['frozen']
    targets = context['targets']
    before_graph = context['graphs'].get('before_return')
    if windows is None or before_graph is None:
        return None
    node_by_state = {node['state_id']: node for node in before_graph['nodes']}
    target_headings = [node_by_state[state]['theta'] for state in targets
                       if state in node_by_state]
    history_odom = [record for record in scans
                    if record.get('odom_base') is not None
                    and in_window(record['index'], windows['history'])]
    residual_min = None
    overlap = 0
    for record in history_odom:
        yaw = record['odom_base'][2]
        best = min((abs(ge.wrap_angle(yaw - heading)) for heading in target_headings),
                   default=None)
        if best is not None:
            if best <= NEW_VIEW_MARGIN_RAD:
                overlap += 1
            residual_min = best if residual_min is None else min(residual_min, best)
    overlap_fraction = (overlap / len(history_odom)) if history_odom else None

    # keyframe-gate residual at action start
    action_start_stamp = None
    for record in scans:
        if in_window(record['index'], windows['action']) and record.get('odom_base'):
            action_start_stamp = record
            break
    last_accept = None
    for item in context['accepts']:
        if action_start_stamp is not None and item['sim_time'] <= action_start_stamp['stamp']:
            last_accept = item
    gate_residual = None
    if last_accept is not None and action_start_stamp is not None:
        accept_stamp = last_accept['sim_time']
        accept_scan = pose_at(scans, accept_stamp, 0.2)
        if accept_scan is not None and accept_scan.get('odom_base'):
            gate_residual = abs(ge.wrap_angle(
                action_start_stamp['odom_base'][2] - accept_scan['odom_base'][2]))
    planned = run['spec'].get('planned_cumulative_rotation_rad')
    predicted_states = None
    if gate_residual is not None and planned:
        predicted_states = int((gate_residual + abs(planned) + 1e-9)
                               // KEYFRAME_HEADING_GATE_RAD)
    return {
        'episode_id': run['episode_id'], 'attempt': run['attempt'],
        'direction_overlap_fraction': overlap_fraction,
        'direction_residual_min_deg': (None if residual_min is None
                                       else math.degrees(residual_min)),
        'gate_residual_rad': gate_residual,
        'gate_predicted_keframes': predicted_states,
    }


def mechanism_rows_for(run, context):
    rows = []
    records = jsonl(context['attempt_dir'] / 'karto_edge_provenance.jsonl')
    record_lookup = {}
    for record in records:
        if record.get('record_type') == 'constraint_created':
            record_lookup[(int(record['source_state_id']),
                           int(record['target_state_id']))] = record
    targets = context['targets']
    for before, after, stage in (('before_return', 'arrival', 'return'),
                                 ('arrival', 'action_done', 'action'),
                                 ('action_done', 'final', 'tail')):
        graph_before = context['graphs'].get(before)
        graph_after = context['graphs'].get(after)
        if not graph_before or not graph_after or not targets:
            continue
        before_edges = {(edge['source_state_id'], edge['target_state_id'])
                        for edge in graph_before['edges']}
        before_nodes = {node['state_id'] for node in graph_before['nodes']}
        new_edges = [edge for edge in graph_after['edges']
                     if (edge['source_state_id'], edge['target_state_id'])
                     not in before_edges]
        entries = []
        for edge in new_edges:
            key = (edge['source_state_id'], edge['target_state_id'])
            record = record_lookup.get(key, {})
            entries.append({
                'edge': list(key),
                'chain': edge['target_state_id'] == edge['source_state_id'] + 1,
                'provenance': record.get('creation_provenance'),
                'source_in_before': edge['source_state_id'] in before_nodes,
                'match_response': record.get('match_response'),
            })
        closures = [entry for entry in entries if not entry['chain']]
        historic = [entry for entry in closures if entry['source_in_before']]
        contribution = None
        historic_contribution = None
        try:
            full = an.target_score(graph_after, targets)['J_T']
            closed_keys = {tuple(entry['edge']) for entry in closures}
            reduced = {'nodes': graph_after['nodes'],
                       'edges': [edge for edge in graph_after['edges']
                                 if (edge['source_state_id'],
                                     edge['target_state_id']) not in closed_keys]}
            contribution = full - an.target_score(reduced, targets)['J_T']
            historic_keys = {tuple(entry['edge']) for entry in historic}
            reduced_hist = {'nodes': graph_after['nodes'],
                            'edges': [edge for edge in graph_after['edges']
                                      if (edge['source_state_id'],
                                          edge['target_state_id']) not in historic_keys]}
            historic_contribution = full - an.target_score(reduced_hist, targets)['J_T']
        except Exception:  # noqa: BLE001
            contribution = None
        rows.append({
            'episode_id': run['episode_id'], 'attempt': run['attempt'],
            'stage': stage,
            'new_edges': len(entries),
            'new_closures': len(closures),
            'historic_links': len(historic),
            'local_only_closures': len(closures) - len(historic),
            'provenance_counts': json.dumps(Counter(
                entry['provenance'] for entry in entries)),
            'historic_endpoints': json.dumps([entry['edge'] for entry in historic][:20]),
            'closure_contribution': contribution,
            'historic_contribution': historic_contribution,
            'diagnostic_label': 'FIXED_LINEARIZATION_FACTOR_DIAGNOSTIC',
            'detail': json.dumps(entries[:40]),
        })
    return rows


# ------------------------------------------------------------------ suite
def write_csv(path, rows):
    path = Path(path)
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


def analyze_suite(suite_dir):
    suite_dir = Path(suite_dir)
    out_dir = suite_dir / 'analysis'
    out_dir.mkdir(parents=True, exist_ok=True)
    runs = discover_runs(suite_dir)
    metrics, ledger, boundary_rows, identity_rows = [], [], [], []
    topic_rows, provenance_rows, gt_rows, feature_rows = [], [], [], []
    mechanism = []
    contexts = {}

    for run in runs:
        attempt_dir = run['attempt_dir']
        row, context = episode_metrics(run)
        metrics.append(row)
        contexts[run['episode_id']] = context
        ledger.append({
            'episode_id': run['episode_id'], 'attempt': run['attempt'],
            'run_id': run['spec'].get('provenance_run_id'),
            'status': run['state'].get('status'),
            'technical_validity': run['manifest'].get('technical_validity'),
            'technical_reasons': ';'.join(run['manifest'].get('technical_reasons', [])),
            'started_utc': run['state'].get('started_utc'),
            'finished_utc': run['state'].get('finished_utc'),
            'attempts_so_far': run['spec'].get('doc79_run_index'),
        })
        for boundary, entry in (run['boundary_manifest'] or {}).items():
            if boundary == 'mode' or not isinstance(entry, dict):
                continue
            checks = entry.get('checks', {})
            boundary_rows.append({
                'episode_id': run['episode_id'], 'attempt': run['attempt'],
                'boundary': boundary,
                'watermark_stamp': (entry.get('watermark') or {}).get('stamp'),
                'watermark_seq': (entry.get('watermark') or {}).get('seq'),
                'last_mapper_stamp': (entry.get('telemetry_before_export') or {}).get('last_native_scan_stamp'),
                'mapper_processed': (entry.get('telemetry_before_export') or {}).get('native_scan_processed'),
                'mapper_received': (entry.get('telemetry_before_export') or {}).get('native_scan_received'),
                'mapper_accepted': (entry.get('telemetry_before_export') or {}).get('native_scan_accepted'),
                'sync_nodes': (entry.get('sync_file') or {}).get('node_count'),
                'sync_edges': (entry.get('sync_file') or {}).get('edge_count'),
                'topic_nodes': (entry.get('topic_cache') or {}).get('node_count'),
                'topic_edges': (entry.get('topic_cache') or {}).get('edge_count'),
                'topic_message_count': (entry.get('topic_cache') or {}).get('message_count'),
                'provenance_records_after_flush': entry.get('provenance_record_count_after_flush'),
                'all_checks_passed': entry.get('all_checks_passed'),
                'failed_checks': ';'.join(sorted(k for k, v in checks.items() if not v)),
            })
        seq_audit = ck.scan_identity_audit(context['scans'], key='seq')
        stamp_audit = ck.scan_identity_audit(context['scans'], key='stamp')
        identity_rows.append({
            'episode_id': run['episode_id'], 'attempt': run['attempt'],
            'driver_scans': len(context['scans']),
            'seq_duplicates': seq_audit['duplicates'],
            'seq_regressions': seq_audit['regressions'],
            'stamp_duplicates': stamp_audit['duplicates'],
            'stamp_regressions': stamp_audit['regressions'],
            'driver_keyscans': len(context['keyscans']),
            'accept_log_states': len(context['accepts']),
        })
        provenance_path = attempt_dir / 'karto_edge_provenance.jsonl'
        prok, proreasons, proinfo = ck.provenance_summary(
            provenance_path, run['spec'].get('provenance_run_id'))
        provenance_rows.append({
            'episode_id': run['episode_id'], 'attempt': run['attempt'],
            'records': proinfo['records'],
            'record_types': json.dumps(proinfo['record_types']),
            'duplicate_sequences': proinfo['duplicate_sequences'],
            'monotonic': proinfo['creation_sequences_monotonic'],
            'ok': prok, 'reasons': ';'.join(proreasons),
            'rejection_cause': 'REJECTION_CAUSE_NOT_OBSERVABLE',
        })
        for stem in SYNC_STEMS:
            topic = load_json(attempt_dir / 'graph_{}_topic.json'.format(stem))
            payload = context['sync_payloads'].get(stem)
            if topic is None or payload is None:
                continue
            comparison = ck.compare_topic_sync(topic.get('graph', {}), {
                'nodes': payload['nodes'],
                'edges': [{'source_state_id': e['source_state_id'],
                           'target_state_id': e['target_state_id']}
                          for e in payload['edges']]})
            topic_rows.append({
                'episode_id': run['episode_id'], 'attempt': run['attempt'],
                'boundary': BOUNDARY_OF_STEM[stem],
                'topic_nodes': comparison['topic_nodes'],
                'sync_nodes': comparison['sync_nodes'],
                'node_deficit': len(comparison['nodes_only_in_sync']),
                'nodes_only_in_sync': json.dumps(comparison['nodes_only_in_sync'][:20]),
                'topic_edges': comparison['topic_edges'],
                'sync_edges': comparison['sync_edges'],
                'edge_deficit': len(comparison['edges_only_in_sync']),
                'edges_only_in_sync': json.dumps(comparison['edges_only_in_sync'][:20]),
            })
        gt_stream = jsonl(attempt_dir / 'gt_stream.jsonl')
        gt_part, align_info = corrected_gt_rows(run, context, gt_stream)
        gt_rows.extend(gt_part)
        if align_info:
            row.update({key: value for key, value in align_info.items()
                        if not key.startswith('GT_')})
        feature = pre_action_features(run, context, gt_stream)
        if feature:
            feature_rows.append(feature)
        mechanism.extend(mechanism_rows_for(run, context))

    # ---- pre/post joins for the two pre-action candidates ---------------
    outcome = {row['episode_id']: row for row in metrics}
    for feature in feature_rows:
        row = outcome.get(feature['episode_id'], {})
        feature['action_gain_sync'] = row.get('delta_J_action_sync')
        feature['rotation_rad'] = row.get('actual_rotation_rad')
        feature['historic_links_action'] = next(
            (int(item['historic_links']) for item in mechanism
             if item['episode_id'] == feature['episode_id'] and item['stage'] == 'action'),
            None)

    # ---- place x direction comparison -----------------------------------
    comparison_rows = []
    usable = [row for row in metrics
              if row.get('technical_validity') == 'MEASUREMENT_VALIDATED']
    for place in ('place_B', 'place_C'):
        for action in ('L+', 'L-'):
            arm = [row for row in usable
                   if row['place'] == place and row['action'] == action]
            values = [row['delta_J_action_sync'] for row in arm
                      if row['delta_J_action_sync'] is not None]
            comparison_rows.append({
                'place': place, 'action': action, 'runs': len(values),
                'action_gain_values': ';'.join('{:.6f}'.format(v) for v in values),
                'action_gain_mean': statistics.mean(values) if values else None,
                'action_gain_spread': (max(values) - min(values)) if len(values) > 1 else None,
                'rotation_values': ';'.join(
                    '{:.4f}'.format(row['actual_rotation_rad'])
                    for row in arm if row['actual_rotation_rad'] is not None),
            })
    for place in ('place_B', 'place_C'):
        plus = [row['delta_J_action_sync'] for row in usable
                if row['place'] == place and row['action'] == 'L+'
                and row['delta_J_action_sync'] is not None]
        minus = [row['delta_J_action_sync'] for row in usable
                 if row['place'] == place and row['action'] == 'L-'
                 and row['delta_J_action_sync'] is not None]
        paired = []
        for p in plus:
            for m in minus:
                paired.append(p - m)
        comparison_rows.append({
            'place': place, 'action': 'L+_minus_L-', 'runs': len(paired),
            'action_gain_values': ';'.join('{:.6f}'.format(v) for v in paired),
            'action_gain_mean': statistics.mean(paired) if paired else None,
            'action_gain_spread': (max(paired) - min(paired)) if len(paired) > 1 else None,
            'rotation_values': '',
        })

    # ---- cost / quality --------------------------------------------------
    cost_rows = []
    for row in metrics:
        gt_change = None
        diffs = [item for item in gt_rows
                 if item['episode_id'] == row['episode_id']
                 and item['family'] == 'ROBOT_LOCALIZATION_ERROR']
        arrival = next((item['value'] for item in diffs
                        if item['stage'] == 'return' and item['metric'] == 'mean_m'), None)
        final = next((item['value'] for item in diffs
                      if item['stage'] == 'tail' and item['metric'] == 'mean_m'), None)
        if arrival is not None and final is not None:
            gt_change = final - arrival
        cost_rows.append({
            'episode_id': row['episode_id'], 'place': row['place'],
            'action': row['action'],
            'rotation_rad': row.get('actual_rotation_rad'),
            'observation_duration_s': row.get('observation_duration_s'),
            'action_gain_sync': row.get('delta_J_action_sync'),
            'historic_links_action': next(
                (int(item['historic_links']) for item in mechanism
                 if item['episode_id'] == row['episode_id'] and item['stage'] == 'action'),
                None),
            'robot_gt_error_change_m': gt_change,
        })

    # ---- gate ------------------------------------------------------------
    total_attempts = len(metrics)
    valid = [row for row in metrics
             if row.get('technical_validity') == 'MEASUREMENT_VALIDATED']
    gate = {
        'suite': str(suite_dir),
        'attempts': total_attempts,
        'episodes_planned': 8,
        'technically_validated_attempts': len(valid),
        'measurement_validated': total_attempts > 0 and len(valid) == total_attempts,
        'per_place_direction': comparison_rows,
        'mechanism_summary': {
            'historic_links_total': sum(int(item['historic_links'])
                                        for item in mechanism),
            'local_only_closures_total': sum(int(item['local_only_closures'])
                                             for item in mechanism),
        },
        'gt_summary': {
            'relative_translation_mean_m': statistics.mean(
                [item['value'] for item in gt_rows
                 if item['family'] == 'RELATIVE_POSE_ERROR'
                 and item['metric'] == 'translation_mean_m']) if any(
                    item['family'] == 'RELATIVE_POSE_ERROR' for item in gt_rows) else None,
        },
    }
    write_csv(out_dir / 'run_ledger.csv', ledger)
    write_csv(out_dir / 'technical_eligibility.csv', boundary_rows)
    write_csv(out_dir / 'scan_identity_audit.csv', identity_rows)
    write_csv(out_dir / 'boundary_integrity.csv', boundary_rows)
    write_csv(out_dir / 'topic_vs_sync_graph.csv', topic_rows)
    write_csv(out_dir / 'constraint_provenance_audit.csv', provenance_rows)
    write_csv(out_dir / 'action_mechanism.csv', mechanism)
    write_csv(out_dir / 'per_episode_metrics.csv', metrics)
    write_csv(out_dir / 'place_direction_comparison.csv', comparison_rows)
    write_csv(out_dir / 'corrected_gt_metrics.csv', gt_rows)
    write_csv(out_dir / 'pre_action_feature_audit.csv', feature_rows)
    write_csv(out_dir / 'cost_quality_comparison.csv', cost_rows)
    (out_dir / 'final_gate.json').write_text(json.dumps(gate, indent=1, default=str))
    return gate


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--suite-dir', required=True)
    args = parser.parse_args()
    print(json.dumps(analyze_suite(args.suite_dir), indent=1, default=str))
