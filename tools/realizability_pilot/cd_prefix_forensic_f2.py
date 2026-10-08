#!/usr/bin/python3
"""Outcome-blind, prefix-only forensic analysis for the frozen CD run.

This module only reads pre-treatment graphs, canonical prefix streams and
technical replay metadata. It never imports a scientific endpoint calculator.
"""

import argparse
import csv
import hashlib
import itertools
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
F2 = ROOT / 'results/realizability_pilot/p1_cd_prefix_forensic_f2_20261008'
ORIGINAL = ROOT / 'results/realizability_pilot/p1_context_disentangle_confirmatory_20260930'
AMENDMENT = ROOT / 'results/realizability_pilot/p1_context_disentangle_confirmatory_amendment1_20260930'

from v13_prefix_equivalence import compare_graphs, numerical_payload, stream_sha  # noqa: E402


def read_json(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')


def write_csv(path, rows, fields):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def candidate(target, seed):
    return ORIGINAL / 'qualification/candidates' / target / ('seed_%s' % seed)


def branch(target, block, arm, attempt=1):
    return (AMENDMENT / 'collection/replays' / target / block / arm /
            ('attempt_%02d' % attempt))


def frozen_block(target, block):
    frozen = read_json(AMENDMENT / 'qualification/frozen_history_manifest.json')
    return next(row for row in frozen['selected_blocks'][target]
                if row['block_id'] == block)


def history_inputs(target, block):
    record = frozen_block(target, block)
    base = candidate(target, record['seed'])
    return record, base, base / 'canonical_prefix.jsonl', base / 'attempt_01/mapper_params.yaml'


def graph_path(target, block, label):
    record, base, _, _ = history_inputs(target, block)
    _ = record
    if label.startswith('Q'):
        return base / 'prefix_replays' / ('repeat_%02d' % int(label[1:])) / 'graph_pre.json'
    arm, attempt = label.split('_')
    return branch(target, block, arm, int(attempt)) / 'graph_pre.json'


H1_LABELS = ['Q1', 'Q2', 'Q3', 'D0_1', 'D0_2', 'D1_1', 'D1_2', 'D2_1', 'D2_2']
ARM_DIRS = {'D0': 'D0_ZERO', 'D1': 'D1_THRESHOLD', 'D2': 'D2_HIGH'}


def frozen_graphs(target, block, labels):
    out = {}
    for label in labels:
        if label.startswith('Q'):
            path = graph_path(target, block, label)
        else:
            arm, attempt = label.split('_')
            path = branch(target, block, ARM_DIRS[arm], int(attempt)) / 'graph_pre.json'
        if not path.is_file():
            raise FileNotFoundError(path)
        out[label] = (path, read_json(path))
    return out


def graph_numeric_key(graph):
    return json.dumps(numerical_payload(graph), sort_keys=True, separators=(',', ':'))


def cluster_graphs(graphs):
    clusters = []
    for label, (_, graph) in graphs.items():
        for cluster in clusters:
            if compare_graphs(cluster['graph'], graph)['structural']['exact'] and \
                    graph_numeric_key(cluster['graph']) == graph_numeric_key(graph):
                cluster['labels'].append(label)
                break
        else:
            clusters.append({'graph': graph, 'labels': [label]})
    return [item['labels'] for item in clusters]


def node_rows(reference, observed, label):
    rows = []
    for left, right in zip(reference['nodes'], observed['nodes']):
        rows.append({'label': label, 'state_id': left['state_id'],
                     'unique_id': left['unique_id'],
                     'dx_m': right['x'] - left['x'],
                     'dy_m': right['y'] - left['y'],
                     'dtheta_rad': right['theta'] - left['theta'],
                     'translation_m': math.hypot(right['x'] - left['x'], right['y'] - left['y'])})
    return rows


def edge_rows(reference, observed, label):
    rows = []
    for left, right in zip(reference['edges'], observed['edges']):
        lm, rm = left.get('measurement', {}), right.get('measurement', {})
        dl = {axis: rm.get(axis, 0) - lm.get(axis, 0)
              for axis in ('dx', 'dy', 'dtheta')}
        lc, rc = left.get('covariance_3x3', []), right.get('covariance_3x3', [])
        cov = max((abs(a - b) for ra, rb in zip(lc, rc)
                   for a, b in zip(ra, rb)), default=0)
        rows.append({'label': label, 'edge_index': left['index'],
                     'source_state_id': left['source_state_id'],
                     'target_state_id': left['target_state_id'],
                     'ddx_m': dl['dx'], 'ddy_m': dl['dy'],
                     'ddtheta_rad': dl['dtheta'],
                     'measurement_translation_m': math.hypot(dl['dx'], dl['dy']),
                     'covariance_max_abs': cov})
    return rows


def first_nonzero(rows, columns):
    return next((row for row in rows if any(row[key] != 0 for key in columns)), None)


def find_accepted_scan_mapping(base, graph):
    """Use frozen provenance to map accepted state IDs to message positions.

    State ID is assigned to accepted keyscans, not all published scan messages.
    The provenance itself does not log the raw input index, so match the
    state pose to message odometry only as a candidate, never exact identity.
    """
    stream = [json.loads(line) for line in (base / 'canonical_prefix.jsonl').open() if line.strip()]
    # All 35 published scans are accepted in this H1 prefix iff graph count is 35.
    identity = len(stream) == len(graph['nodes']) and all(
        node['state_id'] == index and node['unique_id'] == index
        for index, node in enumerate(graph['nodes']))
    return {'published_scan_count': len(stream), 'accepted_node_count': len(graph['nodes']),
            'state_id_equals_zero_based_message_index_proven': False,
            'identity_is_consistent_with_counts_and_order': identity,
            'state_15_candidate_message_index_zero_based': 15 if identity else None,
            'state_15_candidate_stamp_s': stream[15]['stamp'] if identity else None,
            'limitation': 'No receiver-side raw-message-index to accepted-state-ID ledger exists; '
                          'one-to-one order is inferred from counts and sequential IDs only.'}


def normalized_launch(path):
    tree = ET.parse(path)
    nodes = tree.findall('.//node')
    if len(nodes) != 1:
        raise ValueError('expected one mapper node')
    node = nodes[0]
    params = {param.attrib['name']: param.attrib.get('value')
              for param in node.findall('param')}
    volatile = {'pose_graph_dump_path', 'edge_provenance_path'}
    semantic = {key: value for key, value in params.items() if key not in volatile}
    return {'node': {key: node.attrib.get(key) for key in ('name', 'pkg', 'type', 'output')},
            'semantic_params': semantic, 'output_only_params': {key: params.get(key) for key in volatile},
            'sha256': sha(path)}


def scan_stamps(path):
    stamps = []
    with Path(path).open() as stream:
        for line in stream:
            if line.strip():
                stamps.append(json.loads(line)['stamp'])
    return stamps


def compare_lifecycle(base, attempt_dir, name):
    q = base / 'prefix_replays/repeat_01'
    q_result = read_json(q / 'unified_replay_result.json')
    b_result = read_json(attempt_dir / 'unified_replay_result.json')
    q_launch, b_launch = normalized_launch(q / 'mapper.launch'), normalized_launch(attempt_dir / 'mapper.launch')
    prefix = base / 'canonical_prefix.jsonl'
    q_copy = q / 'canonical_prefix.jsonl'
    b_copy = attempt_dir / 'canonical_prefix.jsonl'
    checks = {
        'input_byte_identical_q_and_b': sha(q_copy) == sha(b_copy),
        'canonical_stream_semantic_sha_equal': stream_sha(q_copy) == stream_sha(b_copy),
        'input_stamps_identical': scan_stamps(q_copy) == scan_stamps(b_copy),
        'canonical_copy_byte_identical': sha(prefix) == sha(q_copy) == sha(b_copy),
        'mapper_binary_hash_equal': q_result['code_provenance']['mapper_binary_sha256'] == b_result['code_provenance']['mapper_binary_sha256'],
        'normalized_mapper_config_hash_equal': q_result['mapper_params_sha256'] == b_result['mapper_params_sha256'],
        'normalized_launch_semantics_equal': q_launch['node'] == b_launch['node'] and q_launch['semantic_params'] == b_launch['semantic_params'],
        'publisher_count_equal': q_result['prefix_publisher']['published'] == b_result['prefix_publisher']['published'],
        'processed_count_equal': q_result['processed_prefix_count'] == b_result['processed_prefix_count'],
        'both_subscriber_connected': q_result['prefix_publisher']['connection_confirmed'] and b_result['prefix_publisher']['connection_confirmed'],
        'both_synchronous_dump': not q_result['background_graph_dump_used'] and not b_result['background_graph_dump_used'],
        'both_no_fixed_drain_sleep': not q_result['fixed_sleep_used_as_drain_barrier'] and not b_result['fixed_sleep_used_as_drain_barrier'],
    }
    return {'name': name, 'qualification_dir': str(q), 'branch_dir': str(attempt_dir),
            'checks': checks, 'q_launch': q_launch, 'b_launch': b_launch,
            'qualification_mode': q_result['mode'], 'branch_mode': b_result['mode'],
            'qualification_timeline': q_result['timeline'], 'branch_timeline': b_result['timeline'],
            'suffix_published_in_failed_branch': b_result['suffix_published'],
            'callback_payload_identical_verified': False,
            'environment_fingerprint_comparable': False,
            'shared_library_snapshot_available': False,
            'cpu_affinity_snapshot_available': False,
            'tbb_runtime_snapshot_available': False}


def offline():
    analysis = F2 / 'analysis'
    analysis.mkdir(parents=True, exist_ok=True)
    graphs = frozen_graphs('target_A', 'target_A_H1', H1_LABELS)
    ref = graphs['Q1'][1]
    clusters = cluster_graphs(graphs)
    matrix = []
    for left, right in itertools.product(H1_LABELS, H1_LABELS):
        result = compare_graphs(graphs[left][1], graphs[right][1])
        matrix.append({'left': left, 'right': right,
                       'structural_exact': result['structural']['exact'],
                       'numerical_exact_6dp': result['numerical']['exact'],
                       **{key: value for key, value in result['numerical'].items()
                          if key != 'exact'}})
    write_csv(analysis / 'nine_graph_cluster_matrix.csv', matrix, list(matrix[0]))
    write_json(analysis / 'nine_graph_cluster_summary.json', {
        'clusters': [{'id': index + 1, 'labels': labels} for index, labels in enumerate(clusters)],
        'graphs': {label: {'path': str(path), 'sha256': sha(path),
                           'node_count': len(graph['nodes']), 'edge_count': len(graph['edges'])}
                   for label, (path, graph) in graphs.items()},
        'cluster_semantics': 'Graph structure and 6-decimal serialized numerical payload identity',
        'prior_four_cluster_claim_verified': sorted(map(sorted, clusters)) == sorted(map(sorted, [
            ['Q1', 'Q2', 'Q3'], ['D0_1'], ['D0_2', 'D1_1', 'D1_2', 'D2_2'], ['D2_1']]))})
    all_nodes, all_edges, first = [], [], {}
    for label in H1_LABELS[3:]:
        nr = node_rows(ref, graphs[label][1], label)
        er = edge_rows(ref, graphs[label][1], label)
        all_nodes += nr
        all_edges += er
        first[label] = {
            'first_changed_node': first_nonzero(nr, ('dx_m', 'dy_m', 'dtheta_rad')),
            'first_changed_edge_measurement': first_nonzero(er, ('ddx_m', 'ddy_m', 'ddtheta_rad')),
            'first_changed_edge_covariance': first_nonzero(er, ('covariance_max_abs',)),
            'changed_node_count': sum(bool(row['translation_m'] or row['dtheta_rad']) for row in nr),
            'changed_edge_count': sum(bool(row['measurement_translation_m'] or row['ddtheta_rad'] or row['covariance_max_abs']) for row in er),
        }
    write_csv(analysis / 'node_difference.csv', all_nodes, list(all_nodes[0]))
    write_csv(analysis / 'edge_difference.csv', all_edges, list(all_edges[0]))
    write_json(analysis / 'first_divergence.json', {
        'reference': 'Q1', 'serialized_zero_threshold_m': 0,
        'serialization_quantization_half_unit': 0.0000005,
        'note': '1e-6 difference can be rounding boundary; material 1e-2 differences cannot.',
        'by_graph': first})
    record, base, _, _ = history_inputs('target_A', 'target_A_H1')
    write_json(analysis / 'affected_state_mapping.json', {
        'target_A_H1': find_accepted_scan_mapping(base, ref),
        'source_code': 'OpenMapper.cpp assigns state_id=m_Objects.Size() on accepted keyscan',
        'input_prefix_sha256': record['canonical_prefix_sha256']})
    # Existing observation-only provenance records a sequential scan-match
    # response and relative measurement, but not runner-up candidate scores.
    provenance_rows = []
    for label, (path, _) in graphs.items():
        p = path.parent / 'edge_provenance.jsonl'
        for line in p.open():
            if not line.strip():
                continue
            event = json.loads(line)
            if (event.get('record_type') == 'constraint_created' and
                    event.get('target_state_id') in (14, 15) and
                    event.get('creation_provenance') == 'PREVIOUS_SCAN'):
                provenance_rows.append({
                    'label': label,
                    'creation_sequence': event.get('creation_sequence'),
                    'source_state_id': event.get('source_state_id'),
                    'target_state_id': event.get('target_state_id'),
                    'creation_provenance': event.get('creation_provenance'),
                    'match_response': event.get('match_response'),
                    'relative_mean': event.get('relative_mean'),
                    'covariance_3x3': event.get('covariance_3x3'),
                    'provenance_path': str(p),
                })
    write_json(analysis / 'existing_matcher_provenance_trace.json', provenance_rows)
    lifecycles = [compare_lifecycle(base, branch('target_A', 'target_A_H1', ARM_DIRS[arm], attempt),
                                    '%s_%s' % (arm, attempt))
                  for arm in ('D0', 'D1', 'D2') for attempt in (1, 2)]
    checks = sorted(lifecycles[0]['checks'])
    write_csv(analysis / 'lifecycle_equivalence_matrix.csv',
              [{'run': row['name'], 'check': key, 'equal': row['checks'][key]}
               for row in lifecycles for key in checks], ['run', 'check', 'equal'])
    write_json(analysis / 'lifecycle_equivalence_report.json', lifecycles)
    controls = []
    for target, block in (('target_A', 'target_A_H2'), ('target_B', 'target_B_H1')):
        record, base, _, _ = history_inputs(target, block)
        reference = read_json(base / 'prefix_replays/repeat_01/graph_pre.json')
        for arm in ('D0', 'D1', 'D2'):
            directory = branch(target, block, ARM_DIRS[arm], 1)
            observed = read_json(directory / 'graph_pre.json')
            result = compare_graphs(reference, observed)
            controls.append({'target': target, 'block': block, 'seed': record['seed'],
                             'arm': arm, 'qual_reference_sha': sha(base / 'prefix_replays/repeat_01/graph_pre.json'),
                             'branch_graph_sha': sha(directory / 'graph_pre.json'),
                             'structural_exact': result['structural']['exact'],
                             'numerical_exact_6dp': result['numerical']['exact'],
                             **{key: value for key, value in result['numerical'].items()
                                if key != 'exact'}})
    write_csv(analysis / 'matched_control_comparison.csv', controls, list(controls[0]))
    write_json(analysis / 'history_specificity_report.json', {
        'control_role_predeclared': {'target_A_H2': 'same Target', 'target_B_H1': 'cross Target'},
        'rows': controls,
        'caveat': 'Two controls do not establish uniqueness to H1 in all histories.'})
    source = ROOT / 'dependencies/navigation_2d/nav2d_karto/OpenKarto/source/OpenMapper.cpp'
    source_text = source.read_text()
    format_found = bool(re.search(r'snprintf\(buffer,\s*sizeof\(buffer\),\s*"%\.6f"', source_text))
    write_json(analysis / 'serialization_precision_audit.json', {
        'source_path': str(source), 'source_sha256': sha(source),
        'loop_diag_double_format_verified': format_found,
        'printed_decimal_places': 6 if format_found else None,
        'per_value_rounding_bound': 0.5e-6 if format_found else None,
        'pair_difference_rounding_bound': 1e-6 if format_found else None,
        'comparator': 'v13_prefix_equivalence.compare_graphs; json.load to binary64 then equality to 0.0',
        'what_exact_means': 'identical decoded values after %.6f serialization, not original C++ double bits'})
    (analysis / 'numerical_observability_limitations.md').write_text(
        '# Numerical observability limitations\n\n'
        'OpenKarto `LoopDiagDouble` formats `kt_double` via `snprintf("%.6f")`. '
        '`WritePoseGraphJson` applies it to node corrected poses, edge relative measurements, '
        'and 3x3 covariance. JSON decode reads six-decimal values into Python float. '
        'The frozen exact comparator therefore tests equality of serialized graph values, '
        'not bitwise equality of internal C++ doubles. A difference of 1e-6 can arise at '
        'a rounding boundary; differences near 1e-2 m are far above this limit. '
        'The dump is a final prefix snapshot, not a full sequence of intermediate '
        'matcher/optimizer states. A preexisting sub-micrometre internal divergence '
        'could be hidden until it crosses a matching or rounding boundary.\n')
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        figures = F2 / 'figures'
        figures.mkdir(parents=True, exist_ok=True)
        for rows, xkey, ykey, title, filename in (
            (all_nodes, 'state_id', 'translation_m', 'Node translation difference', 'prefix_node_error.png'),
            (all_edges, 'edge_index', 'measurement_translation_m', 'Edge measurement difference', 'prefix_edge_error.png')):
            for label in H1_LABELS[3:]:
                subset = [row for row in rows if row['label'] == label]
                plt.plot([r[xkey] for r in subset], [r[ykey] for r in subset], label=label)
            plt.xlabel(xkey)
            plt.ylabel(ykey)
            plt.title(title)
            plt.legend(fontsize=7)
            plt.tight_layout()
            plt.savefig(figures / filename, dpi=150)
            plt.close()
        data = [[int(next(row['numerical_exact_6dp'] for row in matrix
                          if row['left'] == l and row['right'] == r)) for r in H1_LABELS]
                for l in H1_LABELS]
        plt.imshow(data, cmap='gray_r', vmin=0, vmax=1)
        plt.xticks(range(9), H1_LABELS, rotation=45)
        plt.yticks(range(9), H1_LABELS)
        plt.title('6-decimal numerical identity')
        plt.tight_layout()
        plt.savefig(figures / 'numerical_cluster_heatmap.png', dpi=150)
        plt.close()
    except ImportError:
        pass
    return {'clusters': clusters, 'controls_exact': sum(row['numerical_exact_6dp'] for row in controls),
            'controls_total': len(controls), 'lifecycle_checks_all_equal': all(
                all(row['checks'].values()) for row in lifecycles)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('offline',))
    args = parser.parse_args()
    if args.command == 'offline':
        print(json.dumps(offline(), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
