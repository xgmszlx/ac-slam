#!/usr/bin/python3
"""Pure-python validators shared by the Doc-79 driver, runner and analysis.

Everything here is deterministic and ROS-free so the observation chain can be
tested before any physical run (the handoff's unit-test list) and re-checked
offline afterwards.  The functions never "repair" data: they return
``(ok, reasons, details)`` and the caller decides.
"""

import json
import math
from pathlib import Path


class GainSourceMixingError(RuntimeError):
    """Raised when recorded and re-attributed gains could be mixed up."""


# ------------------------------------------------------------------ SE(2) math
def se2(x, y, theta):
    return (float(x), float(y), float(theta))


def se2_compose(a, b):
    ca, sa = math.cos(a[2]), math.sin(a[2])
    return (a[0] + ca * b[0] - sa * b[1],
            a[1] + sa * b[0] + ca * b[1],
            wrap_angle(a[2] + b[2]))


def se2_inverse(a):
    ca, sa = math.cos(a[2]), math.sin(a[2])
    return (-(ca * a[0] + sa * a[1]), -(-sa * a[0] + ca * a[1]), wrap_angle(-a[2]))


def se2_between(anchor, robot):
    """T_rel = inverse(T_anchor) * T_robot."""
    return se2_compose(se2_inverse(anchor), robot)


def se2_error(relative_est, relative_gt):
    """(translation error m, rotation error rad) of the relative pose pair.

    T_error = inverse(T_rel_gt) * T_rel_est; the errors are the translation
    norm of T_error and its wrapped heading.  This is the SE(2) formulation the
    handoff requires instead of ``abs(norm(est) - norm(gt))``.
    """
    error = se2_compose(se2_inverse(relative_gt), relative_est)
    return math.hypot(error[0], error[1]), abs(wrap_angle(error[2]))


def wrap_angle(value):
    return math.atan2(math.sin(float(value)), math.cos(float(value)))


# ------------------------------------------------------- scan identity checks
def scan_identity_audit(records, key='seq'):
    """Monotonicity / duplication of a scan identity stream."""
    values = [record.get(key) for record in records if record.get(key) is not None]
    duplicates = len(values) - len(set(values))
    regressions = sum(1 for a, b in zip(values[:-1], values[1:]) if b < a)
    steps = [b - a for a, b in zip(values[:-1], values[1:]) if b >= a]
    return {
        'count': len(values),
        'duplicates': duplicates,
        'regressions': regressions,
        'max_step': max(steps) if steps else 0,
        'usable_alone': (len(values) > 0 and duplicates == 0 and regressions == 0),
    }


def watermark_satisfied(telemetry, watermark, require_received=True):
    """Does the mapper telemetry cover the driver's stage-end scan?"""
    reasons = []
    if telemetry is None:
        return False, ['no telemetry'], {}
    last_stamp = telemetry.get('last_native_scan_stamp')
    processed = telemetry.get('native_scan_processed', 0)
    if not processed or last_stamp is None:
        reasons.append('mapper has not processed any native scan')
    elif float(last_stamp) < float(watermark['stamp']) - 1e-9:
        reasons.append(
            'mapper last processed stamp {:.6f} < watermark {:.6f}'.format(
                last_stamp, watermark['stamp']))
    if require_received:
        received = telemetry.get('native_scan_received', 0)
        if received < int(watermark.get('driver_scan_count', 0)):
            reasons.append('mapper received {} < driver scan count {}'.format(
                received, watermark.get('driver_scan_count')))
    return (not reasons), reasons, {
        'last_native_scan_stamp': last_stamp,
        'native_scan_processed': processed,
    }


def accepted_consistent(telemetry, keyscan_count):
    if telemetry is None:
        return False, 'no telemetry'
    accepted = telemetry.get('native_scan_accepted')
    if accepted != keyscan_count:
        return False, 'mapper accepted {} != driver keyscan events {}'.format(
            accepted, keyscan_count)
    return True, ''


# ------------------------------------------------------ artifact validation
def validate_sync_document(path, run_id, expected_nodes=None, expected_edges=None,
                           expected_sha256=None):
    """Parse + identity + count validation of a synchronous graph dump."""
    reasons = []
    summary = {}
    path = Path(path)
    if not path.is_file():
        return False, ['sync file missing: {}'.format(path)], summary
    if expected_sha256 is not None:
        import hashlib
        digest = hashlib.sha256()
        with open(path, 'rb') as handle:
            for chunk in iter(lambda: handle.read(65536), b''):
                digest.update(chunk)
        if digest.hexdigest() != expected_sha256:
            reasons.append('sha256 mismatch')
    try:
        payload = json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        return False, reasons + ['unparseable json: {}'.format(exc)], summary
    if payload.get('run_id') != run_id:
        reasons.append('run_id mismatch: {!r} != {!r}'.format(
            payload.get('run_id'), run_id))
    nodes = payload.get('nodes')
    edges = payload.get('edges')
    if not isinstance(nodes, list) or not nodes:
        reasons.append('no nodes in dump')
        nodes = nodes or []
    if not isinstance(edges, list):
        reasons.append('no edge list in dump')
        edges = edges or []
    summary['nodes'] = len(nodes)
    summary['edges'] = len(edges)
    if expected_nodes is not None and summary['nodes'] != expected_nodes:
        reasons.append('node count {} != {}'.format(summary['nodes'], expected_nodes))
    if expected_edges is not None and summary['edges'] != expected_edges:
        reasons.append('edge count {} != {}'.format(summary['edges'], expected_edges))
    ok, bad = graph_edge_reference_ok({'nodes': nodes, 'edges': edges})
    if not ok:
        reasons.append('edges reference unknown nodes: {}'.format(bad[:5]))
    state_ids = [node.get('state_id') for node in nodes]
    if len(state_ids) != len(set(state_ids)):
        reasons.append('duplicate state ids in dump')
    return (not reasons), reasons, summary


def graph_edge_reference_ok(graph):
    ids = {int(node['state_id']) for node in graph['nodes']}
    bad = []
    for edge in graph['edges']:
        if int(edge['source_state_id']) not in ids or \
                int(edge['target_state_id']) not in ids:
            bad.append((edge.get('index'), edge.get('source_state_id'),
                        edge.get('target_state_id')))
    return (not bad), bad


def compare_topic_sync(topic_graph, sync_graph):
    """Structural difference between the old-topic cache and the sync dump."""
    topic_nodes = {int(node['id'] if 'id' in node else node['state_id'])
                   for node in topic_graph.get('nodes', [])}
    sync_nodes = {int(node['state_id']) for node in sync_graph.get('nodes', [])}
    topic_edges = set()
    for edge in topic_graph.get('edges', []):
        start = edge.get('start', edge.get('source_state_id'))
        end = edge.get('end', edge.get('target_state_id'))
        topic_edges.add((int(start), int(end)))
    sync_edges = {(int(edge['source_state_id']), int(edge['target_state_id']))
                  for edge in sync_graph.get('edges', [])}
    return {
        'topic_nodes': len(topic_nodes),
        'sync_nodes': len(sync_nodes),
        'nodes_only_in_sync': sorted(sync_nodes - topic_nodes),
        'nodes_only_in_topic': sorted(topic_nodes - sync_nodes),
        'topic_edges': len(topic_edges),
        'sync_edges': len(sync_edges),
        'edges_only_in_sync': sorted(sync_edges - topic_edges),
        'edges_only_in_topic': sorted(topic_edges - sync_edges),
    }


def boundary_paths_unique(manifests):
    paths = {}
    offenders = []
    for name, entry in (manifests or {}).items():
        path = ((entry or {}).get('sync_file') or {}).get('path')
        if path is None:
            continue
        if path in paths:
            offenders.append((paths[path], name, path))
        paths[path] = name
    return (not offenders), offenders


def provenance_summary(path, run_id):
    """Integrity summary of the edge-provenance JSONL."""
    reasons = []
    info = {'records': 0, 'record_types': {}, 'creation_sequence_max': None,
            'duplicate_sequences': 0, 'creation_sequences_monotonic': True}
    path = Path(path)
    if not path.is_file():
        return False, ['provenance file missing'], info
    sequences = []
    seen = set()
    duplicates = 0
    last = None
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except Exception as exc:  # noqa: BLE001
                reasons.append('unparseable provenance record: {}'.format(exc))
                continue
            info['records'] += 1
            kind = record.get('record_type')
            info['record_types'][kind] = info['record_types'].get(kind, 0) + 1
            if record.get('run_id') != run_id:
                reasons.append('run_id mismatch in provenance record')
            if kind == 'constraint_created':
                sequence = record.get('creation_sequence')
                if sequence in seen:
                    duplicates += 1
                seen.add(sequence)
                sequences.append(sequence)
                if last is not None and sequence is not None and sequence < last:
                    info['creation_sequences_monotonic'] = False
                last = sequence
    info['duplicate_sequences'] = duplicates
    if duplicates:
        reasons.append('duplicate creation_sequence values: {}'.format(duplicates))
    if sequences:
        info['creation_sequence_max'] = max(sequences)
    if not info['records']:
        reasons.append('provenance file is empty')
    return (not reasons), reasons, info


def provenance_graph_consistency(provenance_records, sync_graph):
    """Every graph edge must have a creation record with matching endpoints.

    The export flushes before dumping, so the synchronous dump cannot contain
    an edge whose creation record is still buffered (single queued callback).
    """
    created = set()
    for record in provenance_records:
        if record.get('record_type') != 'constraint_created':
            continue
        created.add((int(record['source_state_id']),
                     int(record['target_state_id'])))
    graph_edges = {(int(edge['source_state_id']), int(edge['target_state_id']))
                   for edge in sync_graph.get('edges', [])}
    missing = sorted(graph_edges - created)
    return (not missing), {'graph_edges': len(graph_edges),
                           'provenance_edges': len(created),
                           'edges_without_record': missing[:10]}


def gain_source_tag(source):
    if source not in ('RECORDED_SNAPSHOT_DIFFERENCE', 'SYNCHRONOUS_DUMP',
                      'FIXED_LINEARIZATION_FACTOR_DIAGNOSTIC'):
        raise ValueError('unknown gain source: {!r}'.format(source))
    return source


def check_gain_sources_agree(first, second):
    if first != second:
        raise GainSourceMixingError(
            'gain sources differ: {!r} vs {!r}'.format(first, second))
    return True


def budget_state(attempts_used, budget, planned):
    remaining = max(0, int(budget) - int(attempts_used))
    return {'attempts_used': int(attempts_used), 'budget': int(budget),
            'remaining': remaining,
            'can_start_planned': remaining >= max(0, planned - 0),
            'budget_exhausted': remaining == 0}
