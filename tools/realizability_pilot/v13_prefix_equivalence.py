#!/usr/bin/python3
"""v13-T structural/numerical prefix equivalence certification.

The v13 gate intentionally does not compare opaque JSON file hashes.  It first
certifies graph structure and then reports numerical differences.  Numerical
tolerances are zero when all repeated, same-input, same-config, same-lifecycle
prefix replays are exactly equal.  A measured envelope is only available after
structural identity has passed for every repeated pair.
"""

import argparse
import hashlib
import itertools
import json
from pathlib import Path


NUMERICAL_FLOORS = {
    'node_translation_max_m': 1e-6,
    'node_heading_max_rad': 1e-6,
    'edge_translation_measurement_max_m': 1e-6,
    'edge_heading_measurement_max_rad': 1e-6,
    'edge_covariance_max_abs': 1e-9,
}
ENVELOPE_MULTIPLIER = 2.0


def load_json(path):
    with open(path) as stream:
        return json.load(stream)


def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def canonical_json_sha(payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
    return sha256_bytes(encoded)


def stream_sha(path, prefix_count=None):
    rows = []
    with open(path) as stream:
        for line in stream:
            if line.strip():
                rows.append(json.loads(line))
    if prefix_count is not None:
        rows = rows[:int(prefix_count)]
    payload = ''.join(json.dumps(row, sort_keys=True, separators=(',', ':')) + '\n'
                      for row in rows).encode()
    return sha256_bytes(payload), len(rows)


def structural_signature(graph, target_ids=None, input_sha=None,
                         input_count=None, mapper_config_sha=None,
                         code_provenance=None):
    nodes = graph['nodes']
    edges = graph['edges']
    signature = {
        'signature_version': 'v13-prefix-structure-v1',
        'node_count': len(nodes),
        'node_state_ids_in_insertion_order': [n['state_id'] for n in nodes],
        'node_unique_ids_in_insertion_order': [n['unique_id'] for n in nodes],
        'edge_count': len(edges),
        'edge_state_endpoints_in_insertion_order': [
            [e['source_state_id'], e['target_state_id']] for e in edges],
        'edge_unique_endpoints_in_insertion_order': [
            [e.get('source_unique_id'), e.get('target_unique_id')] for e in edges],
        'target_historical_state_ids': list(target_ids or []),
        'canonical_input_sha256': input_sha,
        'canonical_input_record_count': input_count,
        'mapper_config_sha256': mapper_config_sha,
        'code_provenance': code_provenance or {},
    }
    signature['structural_signature_sha256'] = canonical_json_sha(signature)
    return signature


def numerical_payload(graph):
    return {
        'node_pose': [[n['x'], n['y'], n['theta']] for n in graph['nodes']],
        'edge_measurement': [[e.get('measurement', {}).get('dx', 0.0),
                              e.get('measurement', {}).get('dy', 0.0),
                              e.get('measurement', {}).get('dtheta', 0.0)]
                             for e in graph['edges']],
        'edge_covariance': [e.get('covariance_3x3', []) for e in graph['edges']],
    }


def _max_abs_flat(left, right):
    if isinstance(left, (list, tuple)):
        if not isinstance(right, (list, tuple)) or len(left) != len(right):
            return None
        result = 0.0
        for a, b in zip(left, right):
            value = _max_abs_flat(a, b)
            if value is None:
                return None
            result = max(result, value)
        return result
    return abs(float(left) - float(right))


def _max_xy(rows_a, rows_b):
    if len(rows_a) != len(rows_b):
        return None
    return max((max(abs(float(a[0]) - float(b[0])),
                    abs(float(a[1]) - float(b[1])))
                for a, b in zip(rows_a, rows_b)), default=0.0)


def _max_theta(rows_a, rows_b):
    if len(rows_a) != len(rows_b):
        return None
    return max((abs(float(a[2]) - float(b[2]))
                for a, b in zip(rows_a, rows_b)), default=0.0)


def compare_graphs(graph_a, graph_b, target_ids=None):
    sa = structural_signature(graph_a, target_ids)
    sb = structural_signature(graph_b, target_ids)
    structural_fields = [
        'node_count', 'node_state_ids_in_insertion_order',
        'node_unique_ids_in_insertion_order', 'edge_count',
        'edge_state_endpoints_in_insertion_order',
        'edge_unique_endpoints_in_insertion_order',
        'target_historical_state_ids',
    ]
    structural = {field + '_equal': sa[field] == sb[field]
                  for field in structural_fields}
    structural['exact'] = all(structural.values())
    na, nb = numerical_payload(graph_a), numerical_payload(graph_b)
    numerical = {
        'node_translation_max_m': _max_xy(na['node_pose'], nb['node_pose']),
        'node_heading_max_rad': _max_theta(na['node_pose'], nb['node_pose']),
        'edge_translation_measurement_max_m': _max_xy(
            na['edge_measurement'], nb['edge_measurement']),
        'edge_heading_measurement_max_rad': _max_theta(
            na['edge_measurement'], nb['edge_measurement']),
        'edge_covariance_max_abs': _max_abs_flat(
            na['edge_covariance'], nb['edge_covariance']),
    }
    numerical['exact'] = all(value == 0.0 for key, value in numerical.items()
                             if key != 'exact')
    return {'structural': structural, 'numerical': numerical}


def certify_repeatability(graphs, labels=None):
    labels = labels or ['run_{}'.format(i) for i in range(len(graphs))]
    pairs = []
    for i, j in itertools.combinations(range(len(graphs)), 2):
        pairs.append({'left': labels[i], 'right': labels[j],
                      'comparison': compare_graphs(graphs[i], graphs[j])})
    structural_exact = bool(pairs) and all(
        row['comparison']['structural']['exact'] for row in pairs)
    numerical_exact = structural_exact and all(
        row['comparison']['numerical']['exact'] for row in pairs)
    if numerical_exact:
        tolerance = {key: 0.0 for key in NUMERICAL_FLOORS}
        tolerance_source = 'exact equality across every repeated pair'
    elif structural_exact:
        maxima = {key: max(row['comparison']['numerical'][key]
                           for row in pairs) for key in NUMERICAL_FLOORS}
        tolerance = {key: max(NUMERICAL_FLOORS[key],
                              ENVELOPE_MULTIPLIER * maxima[key])
                     for key in NUMERICAL_FLOORS}
        tolerance_source = ('all-pairs same-input same-config same-lifecycle '
                            'repeatability envelope')
    else:
        tolerance = None
        tolerance_source = ('unavailable because structural repeatability '
                            'failed')
    return {
        'pair_count': len(pairs),
        'pairs': pairs,
        'structural_exact_all_pairs': structural_exact,
        'numerical_exact_all_pairs': numerical_exact,
        'frozen_numerical_tolerance': tolerance,
        'tolerance_source': tolerance_source,
        'numerical_floors_if_needed': NUMERICAL_FLOORS,
        'envelope_multiplier_if_needed': ENVELOPE_MULTIPLIER,
    }


def check_final_prefix_preservation(prefix_graph, final_graph):
    prefix_nodes = [(n['state_id'], n['unique_id']) for n in prefix_graph['nodes']]
    final_nodes = {(n['state_id'], n['unique_id']) for n in final_graph['nodes']}
    prefix_edges = [(e['source_state_id'], e['target_state_id'],
                     e.get('source_unique_id'), e.get('target_unique_id'))
                    for e in prefix_graph['edges']]
    final_edges = [(e['source_state_id'], e['target_state_id'],
                    e.get('source_unique_id'), e.get('target_unique_id'))
                   for e in final_graph['edges']]
    return {
        'all_prefix_node_id_pairs_present': all(n in final_nodes
                                                for n in prefix_nodes),
        'prefix_edge_endpoint_insertion_sequence_preserved':
            final_edges[:len(prefix_edges)] == prefix_edges,
        'prefix_node_count': len(prefix_nodes),
        'prefix_edge_count': len(prefix_edges),
        'final_node_count': len(final_nodes),
        'final_edge_count': len(final_edges),
        'corrected_pose_equality_intentionally_not_tested': True,
    }


def old_v12b_bh2_forensic(repo_root):
    root = Path(repo_root)
    block = root / ('results/realizability_pilot/'
                    'p1_confirmatory_v12b_20260918/target_B/H2')
    canonical = block / 'canonical_replay/runs/graph_on_0.json'
    attempt1 = block / ('A2_SWEEP90/replay_attempt_01_prefix_mismatch/'
                        'graph_preprobe.json')
    attempt2 = block / ('A2_SWEEP90/replay_attempt_02_prefix_mismatch/'
                        'graph_preprobe.json')
    stitch_path = block / 'A2_SWEEP90/stitch_report.json'
    frozen = load_json(block / 'frozen_target.json')
    graphs = [load_json(path) for path in (canonical, attempt1, attempt2)]
    stitch = load_json(stitch_path)
    return {
        'protocol': 'v13-T forensic-only regression of frozen v12b B/H2',
        'evidence_labels': {
            'code_fact': [
                'canonical dump came from standalone replay teardown',
                'branch preprobe dumps came from a live mapper before suffix'],
            'measured_observation': {
                'canonical_vs_attempt_01': compare_graphs(
                    graphs[0], graphs[1], frozen['historical_scan_ids']),
                'canonical_vs_attempt_02': compare_graphs(
                    graphs[0], graphs[2], frozen['historical_scan_ids']),
                'attempt_01_vs_attempt_02': compare_graphs(
                    graphs[1], graphs[2], frozen['historical_scan_ids']),
                'canonical_file_sha256': sha256_file(canonical),
                'attempt_01_file_sha256': sha256_file(attempt1),
                'attempt_02_file_sha256': sha256_file(attempt2),
                'recorded_signature_hashes': {
                    'canonical': 'f6161cffe49777779799183557ff4bae0d0cb25e5168923e20bd4a05fc69c63a',
                    'attempt_01': '3726f7237c6616ec80cfcf18608942706db7f23760023071c70e3c8a34242f3b',
                    'attempt_02': '3726f7237c6616ec80cfcf18608942706db7f23760023071c70e3c8a34242f3b'},
                'stitch_prefix_byte_identical': stitch['prefix_byte_identical'],
                'stitch_prefix_hash': stitch['prefix_hash'],
                'stitch_combined_prefix_hash': stitch['combined_prefix_hash'],
            },
            'inference': [
                ('The repeated live-cut graphs agree exactly with each other; '
                 'the old mismatch is consistent with a lifecycle-dependent '
                 'numerical dump difference, not an input-prefix mismatch.')],
            'unknown': [
                ('Frozen v12b evidence alone cannot identify the exact internal '
                 'operation during teardown that caused the numerical delta.')],
        },
        'old_gate_unchanged': 'TECHNICAL_INVALID_BLOCK',
        'old_differences_forensic_only_not_tolerance_input': True,
    }


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    compare = sub.add_parser('compare')
    compare.add_argument('left')
    compare.add_argument('right')
    compare.add_argument('--out')
    repeated = sub.add_parser('repeatability')
    repeated.add_argument('graphs', nargs='+')
    repeated.add_argument('--out', required=True)
    forensic = sub.add_parser('forensic-v12b-bh2')
    forensic.add_argument('--repo-root', required=True)
    forensic.add_argument('--out', required=True)
    args = parser.parse_args()

    if args.command == 'compare':
        payload = compare_graphs(load_json(args.left), load_json(args.right))
    elif args.command == 'repeatability':
        payload = certify_repeatability([load_json(p) for p in args.graphs],
                                        [str(p) for p in args.graphs])
    else:
        payload = old_v12b_bh2_forensic(args.repo_root)
    if getattr(args, 'out', None):
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, 'w') as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write('\n')
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
