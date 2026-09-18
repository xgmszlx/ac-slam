#!/usr/bin/python3
"""Offline v9 analysis for common-prefix branched Karto replays."""

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

import edge_analytics  # noqa: E402
import se2_information  # noqa: E402


BRANCHES = ('A0_baseline', 'A1_neutral', 'A2_sweep90')
TARGET_LABEL = 'E_T_target'
NONTARGET_LABEL = 'E_N_nontarget_history'
LOCAL_LABEL = 'local_new_scan'
EIG_TH = 1e-6  # baseline/scripts/utils.py


def load_json(path):
    with open(path) as stream:
        return json.load(stream)


def write_csv(path, rows):
    rows = list(rows)
    if not rows:
        Path(path).write_text('')
        return
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with open(path, 'w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def nodes_from_graph(graph):
    return {int(node['state_id']): {
        'id': int(node['state_id']),
        'unique_id': int(node['unique_id']),
        'x': float(node['x']), 'y': float(node['y']),
        'theta': float(node['theta']),
    } for node in graph['nodes']}


def covariance_text(matrix):
    return ' '.join(str(float(value)) for value in (
        matrix[0][0], matrix[0][1], matrix[0][2],
        matrix[1][1], matrix[1][2], matrix[2][2]))


def edges_from_graph(graph, nodes):
    edges = []
    for edge in graph['edges']:
        start = int(edge['source_state_id'])
        end = int(edge['target_state_id'])
        edges.append({
            'index': int(edge['index']), 'start': start, 'end': end,
            'source_pose': [nodes[start]['x'], nodes[start]['y'],
                            nodes[start]['theta']],
            'target_pose': [nodes[end]['x'], nodes[end]['y'],
                            nodes[end]['theta']],
            'covariance_upper_triangle': covariance_text(
                edge['covariance_3x3']),
            'measurement': edge['measurement'],
            'covariance_3x3': edge['covariance_3x3'],
        })
    return sorted(edges, key=lambda row: row['index'])


def classify_new_edges(before_edges, final_edges, target_ids, history_ids):
    before_indices = {edge['index'] for edge in before_edges}
    target_ids = set(target_ids)
    history_ids = set(history_ids)
    rows = []
    for edge in final_edges:
        if edge['index'] in before_indices:
            continue
        pair = {edge['start'], edge['end']}
        touches_new = bool(pair - history_ids)
        if touches_new and pair & target_ids:
            attribution = TARGET_LABEL
        elif touches_new and pair & history_ids:
            attribution = NONTARGET_LABEL
        else:
            attribution = LOCAL_LABEL
        row = dict(edge)
        row['attribution'] = attribution
        rows.append(row)
    return rows


def path_length(samples):
    return sum(math.hypot(right[1] - left[1], right[2] - left[2])
               for left, right in zip(samples, samples[1:]))


def load_gt(path):
    rows = []
    with open(path) as stream:
        for line in stream:
            if line.strip():
                rows.append([float(value) for value in line.split()])
    return rows


def core_budget(capture, gt_samples, raw_records):
    moves = capture['moves']
    probe_moves = [move for move in moves
                   if str(move['label']).startswith('probe_') or
                   str(move['label']).startswith('neutral_') or
                   str(move['label']).startswith('sweep_')]
    start = float(probe_moves[2]['start_time']) if len(probe_moves) >= 3 \
        else float(capture['probe_start_time'])
    gt_core = [row for row in gt_samples if row[0] >= start]
    raw_core = [row for row in raw_records if float(row['stamp']) >= start]
    return {
        'action_core_start_time': start,
        'action_core_distance_m': path_length(gt_core),
        'action_core_duration_s': float(capture['probe_end_time']) - start,
        'action_core_raw_scan_count': len(raw_core),
    }


def provenance_by_sequence(path):
    records = edge_analytics.provenance_constraints(
        edge_analytics.load_provenance(path))
    return {int(record['creation_sequence']) - 1: record for record in records}


def group_positions(node_ids, target_ids, history_ids):
    index = {node_id: position for position, node_id in enumerate(node_ids)}
    target_ids = set(target_ids)
    history_ids = set(history_ids)
    groups = {
        'target_segment': sorted(target_ids),
        'historical_region': sorted(history_ids - target_ids),
        'history_all': sorted(history_ids),
        'new_scan_region': sorted(set(node_ids) - history_ids),
        'current_pose': [max(node_ids)],
    }
    return {name: [index[node_id] for node_id in values if node_id in index]
            for name, values in groups.items() if values}


def information_variants(nodes, edges, new_edges):
    node_ids = sorted(nodes)
    target_pairs = [(edge['start'], edge['end']) for edge in new_edges
                    if edge['attribution'] == TARGET_LABEL]
    history_pairs = [(edge['start'], edge['end']) for edge in new_edges
                     if edge['attribution'] in (TARGET_LABEL, NONTARGET_LABEL)]
    builds = {}
    for name, excluded in (
            ('all_constraints', ()),
            ('target_removed', target_pairs),
            ('history_removed', history_pairs)):
        information, contributors, rejected = se2_information.build_information(
            node_ids, edges, excluded_pairs=excluded)
        marginal, nullity, _eigenvalues = \
            se2_information.pseudoinverse_information(information)
        builds[name] = {
            'information': information, 'marginal': marginal,
            'contributors': contributors, 'rejected': rejected,
            'nullity': nullity, 'excluded_edge_count': len(excluded),
        }
    return node_ids, builds


def paper_graph_utilities(nodes, edges, new_edges):
    """Author-code covariance-weighted spanning-tree utility and ablations."""
    node_ids = sorted(nodes)
    graph_edges = {}
    for edge in edges:
        covariance = np.asarray(edge['covariance_3x3'], dtype=float)
        information = np.linalg.inv(covariance)
        eigenvalues = np.linalg.eigvalsh(information)
        selected = eigenvalues[eigenvalues > EIG_TH]
        weight = (float(np.exp(np.sum(np.log(selected)) /
                               information.shape[1]))
                  if selected.size else 0.0)
        # Karto and the author's nx.Graph retain one undirected edge per pair.
        graph_edges[tuple(sorted((edge['start'], edge['end'])))] = weight

    target_pairs = {tuple(sorted((edge['start'], edge['end'])))
                    for edge in new_edges
                    if edge['attribution'] == TARGET_LABEL}
    history_pairs = {tuple(sorted((edge['start'], edge['end'])))
                     for edge in new_edges
                     if edge['attribution'] in (TARGET_LABEL, NONTARGET_LABEL)}

    def utility(excluded):
        retained = {pair: weight for pair, weight in graph_edges.items()
                    if pair not in excluded}
        index = {node_id: position for position, node_id in enumerate(node_ids)}
        laplacian = np.zeros((len(node_ids), len(node_ids)))
        adjacency = {node_id: set() for node_id in node_ids}
        for (start, end), weight in retained.items():
            left, right = index[start], index[end]
            laplacian[left, left] += weight
            laplacian[right, right] += weight
            laplacian[left, right] -= weight
            laplacian[right, left] -= weight
            adjacency[start].add(end)
            adjacency[end].add(start)
        reduced = laplacian[1:, 1:]
        eigenvalues = np.linalg.eigvalsh(reduced)
        selected = eigenvalues[eigenvalues > EIG_TH]
        value = (float(np.exp(np.sum(np.log(selected)) / reduced.shape[1]))
                 if selected.size else 0.0)
        seen = set()
        stack = [node_ids[0]] if node_ids else []
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(adjacency[current] - seen)
        return value, len(seen) != len(node_ids)

    all_utility, all_disconnected = utility(set())
    target_utility, target_disconnected = utility(target_pairs)
    history_utility, history_disconnected = utility(history_pairs)

    return {
        'definition': ('author-code covariance-weighted reduced-Laplacian '
                       'normalized spanning-tree D-opt'),
        'all': all_utility,
        'target_removed': target_utility,
        'history_removed': history_utility,
        'all_disconnected': all_disconnected,
        'target_removed_disconnects_graph': target_disconnected,
        'history_removed_disconnects_graph': history_disconnected,
    }


def analyze_branch(root, branch, frozen, raw_dir_override=None):
    branch_dir = root / 'branches' / branch
    replay_dir = branch_dir / 'replay'
    result = load_json(replay_dir / 'branch_replay_result.json')
    before_graph = load_json(replay_dir / 'graph_preprobe.json')
    final_graph = load_json(replay_dir / 'graph_final.json')
    before_nodes = nodes_from_graph(before_graph)
    final_nodes = nodes_from_graph(final_graph)
    before_edges = edges_from_graph(before_graph, before_nodes)
    final_edges = edges_from_graph(final_graph, final_nodes)
    history_ids = set(before_nodes)
    target_ids = set(int(value) for value in frozen['historical_scan_ids'])
    new_edges = classify_new_edges(
        before_edges, final_edges, target_ids, history_ids)
    insertion = edge_analytics.insertion_time_metrics(
        final_edges, final_nodes,
        [(edge['start'], edge['end']) for edge in new_edges])
    provenance = provenance_by_sequence(replay_dir / 'edge_provenance.jsonl')
    constraint_rows = []
    for edge in new_edges:
        pair = tuple(sorted((edge['start'], edge['end'])))
        metric = insertion[pair]
        record = provenance.get(edge['index'], {})
        covariance = edge['covariance_3x3']
        euclidean = math.hypot(
            final_nodes[edge['end']]['x'] - final_nodes[edge['start']]['x'],
            final_nodes[edge['end']]['y'] - final_nodes[edge['start']]['y'])
        constraint_rows.append({
            'branch': branch, 'edge_index': edge['index'],
            'source': edge['start'], 'target': edge['end'],
            'attribution': edge['attribution'],
            'creation_provenance': record.get('creation_provenance'),
            'creation_stage': record.get('creation_stage'),
            'matcher_type': record.get('matcher_type'),
            'match_response': record.get('match_response'),
            'match_threshold': record.get('match_threshold'),
            'measurement_dx': edge['measurement']['dx'],
            'measurement_dy': edge['measurement']['dy'],
            'measurement_dtheta': edge['measurement']['dtheta'],
            'cov_xx': covariance[0][0], 'cov_xy': covariance[0][1],
            'cov_xt': covariance[0][2], 'cov_yy': covariance[1][1],
            'cov_yt': covariance[1][2], 'cov_tt': covariance[2][2],
            'geodesic_at_insertion_m': metric['geodesic_m'],
            'hops_at_insertion': metric['hops'],
            'cycle_length_edges': (metric['hops'] + 1
                                   if metric['hops'] is not None else None),
            'cycle_length_m': (metric['geodesic_m'] + euclidean
                               if metric['geodesic_m'] is not None else None),
            'euclidean_endpoint_distance_m': euclidean,
            'constraint_d_opt': se2_information.constraint_d_opt(
                np.asarray(covariance, dtype=float)),
        })

    node_ids, builds = information_variants(final_nodes, final_edges, new_edges)
    utilities = paper_graph_utilities(final_nodes, final_edges, new_edges)
    positions = group_positions(node_ids, target_ids, history_ids)
    posterior_rows = []
    for variant, build in builds.items():
        for group, group_positions_ in positions.items():
            disconnected = build['nullity'] != 3
            metrics = (None if disconnected else
                       se2_information.group_block_metrics(
                           build['marginal'], group_positions_))
            posterior_rows.append({
                'branch': branch, 'variant': variant, 'group': group,
                'posterior_status': ('DISCONNECTED_UNBOUNDED' if disconnected
                                     else 'FINITE_CONNECTED'),
                'node_count': len(group_positions_),
                'trace_mean': None if metrics is None else metrics['trace_mean'],
                'trace_median': None if metrics is None else metrics['trace_median'],
                'trace_max': None if metrics is None else metrics['trace_max'],
                'logdet_mean': None if metrics is None else metrics['logdet_mean'],
                'logdet_sum': None if metrics is None else metrics['logdet_sum'],
                'all_finite': None if metrics is None else metrics['all_finite'],
                'all_psd': None if metrics is None else metrics['all_psd'],
                'information_contributors': build['contributors'],
                'information_nullity': build['nullity'],
                'excluded_edge_count': build['excluded_edge_count'],
                'rejected_edge_count': len(build['rejected']),
            })

    raw_name = 'raw_attempt_02' if branch == 'A0_baseline' else 'raw'
    raw_dir = (Path(raw_dir_override) if raw_dir_override is not None else
               branch_dir / raw_name)
    capture = load_json(raw_dir / 'capture_result.json')
    gt = load_gt(raw_dir / 'probe_gt_trajectory.txt')
    raw_records = edge_analytics.load_provenance(
        raw_dir / 'probe_stream_raw.jsonl')
    counts = {label: sum(row['attribution'] == label
                         for row in constraint_rows)
              for label in (TARGET_LABEL, NONTARGET_LABEL, LOCAL_LABEL)}
    metrics = {
        'branch': branch,
        'preprobe_graph_hash': result['preprobe_signature']['preprobe_graph_hash'],
        'prefix_stream_identical': result['prefix_stream_identical'],
        'capture_status': capture['status'],
        'action_execution_passed': capture['status'] == 'SUCCEEDED',
        'branch_start_gate_passed': capture['branch_start_gate_passed'],
        'branch_start_deviation_position_m':
            capture['branch_start_deviation_position_m'],
        'branch_start_deviation_heading_rad':
            capture['branch_start_deviation_heading_rad'],
        'distance_m': capture['actual_distance_m'],
        'duration_s': capture['actual_duration_s'],
        'yaw_excursion_rad': capture['actual_yaw_excursion_rad'],
        'raw_scan_count': capture['raw_scan_count'],
        'accepted_keyscan_count': result['accepted_probe_keyscan_count'],
        'new_edge_count': result['new_edge_count'],
        'E_T_count': counts[TARGET_LABEL],
        'E_N_count': counts[NONTARGET_LABEL],
        'local_edge_count': counts[LOCAL_LABEL],
        **core_budget(capture, gt, raw_records),
        'graph_utility_definition': utilities['definition'],
        'graph_d_opt_all': utilities['all'],
        'graph_d_opt_without_target': utilities['target_removed'],
        'graph_d_opt_without_history': utilities['history_removed'],
        'history_ablation_disconnects_graph':
            utilities['history_removed_disconnects_graph'],
    }
    metrics['delta_U_T'] = (metrics['graph_d_opt_all'] -
                            metrics['graph_d_opt_without_target'])
    metrics['delta_U_H'] = (metrics['graph_d_opt_all'] -
                            metrics['graph_d_opt_without_history'])
    for name in ('delta_U_T', 'delta_U_H'):
        metrics[name + '_per_m'] = metrics[name] / metrics['distance_m']
        metrics[name + '_per_s'] = metrics[name] / metrics['duration_s']

    by_variant_group = {(row['variant'], row['group']): row
                        for row in posterior_rows}
    for group in positions:
        all_row = by_variant_group[('all_constraints', group)]
        for removed in ('target_removed', 'history_removed'):
            removed_row = by_variant_group[(removed, group)]
            posterior_rows.append({
                'branch': branch,
                'variant': removed + '_impact', 'group': group,
                'posterior_status': (
                    'UNBOUNDED_IMPACT_DISCONNECTED_COUNTERFACTUAL'
                    if removed_row['posterior_status'] == 'DISCONNECTED_UNBOUNDED'
                    else 'FINITE_CONNECTED_IMPACT'),
                'node_count': all_row['node_count'],
                'trace_mean': (None if removed_row['trace_mean'] is None else
                               removed_row['trace_mean'] - all_row['trace_mean']),
                'trace_median': None, 'trace_max': None,
                'logdet_mean': (removed_row['logdet_mean'] - all_row['logdet_mean']
                                if removed_row['logdet_mean'] is not None and
                                all_row['logdet_mean'] is not None else None),
                'logdet_sum': None, 'all_finite': all_row['all_finite'],
                'all_psd': all_row['all_psd'],
                'information_contributors': None,
                'information_nullity': removed_row['information_nullity'],
                'excluded_edge_count': removed_row['excluded_edge_count'],
                'rejected_edge_count': removed_row['rejected_edge_count'],
            })
    connected_rows = [row for row in posterior_rows
                      if row['posterior_status'] in (
                          'FINITE_CONNECTED', 'FINITE_CONNECTED_IMPACT')]
    disconnected_rows = [row for row in posterior_rows
                         if 'DISCONNECTED' in row['posterior_status']]
    pipeline_pass = (all(row.get('all_finite', True) and
                         row.get('all_psd', True) and
                         row.get('information_nullity') in (None, 3)
                         for row in connected_rows) and
                     all(row.get('information_nullity', 3) > 3
                         for row in disconnected_rows))
    return metrics, constraint_rows, posterior_rows, pipeline_pass


def relative_difference(left, right):
    denominator = (abs(float(left)) + abs(float(right))) / 2.0
    return abs(float(left) - float(right)) / denominator if denominator else 0.0


def analyze(root, out_dir):
    root = Path(root).resolve()
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    attempt = (root / 'canonical_history' / 'episodes' /
               '0001_v9_canonical_history_anchor_01' / 'attempt_01')
    frozen = load_json(attempt / 'frozen_target.json')
    metrics_rows, constraint_rows, posterior_rows = [], [], []
    pipeline = {}
    for branch in BRANCHES:
        metrics, constraints, posterior, passed = analyze_branch(
            root, branch, frozen)
        metrics_rows.append(metrics)
        constraint_rows.extend(constraints)
        posterior_rows.extend(posterior)
        pipeline[branch] = passed

    by_branch = {row['branch']: row for row in metrics_rows}
    neutral = by_branch['A1_neutral']
    sweep = by_branch['A2_sweep90']
    budget = {
        'comparison': 'A1_neutral vs A2_sweep90',
        'preregistered_distance_tolerance_m': 0.5,
        'source': ('docs/research_log/56_constraint_realizability_direction_audit.md '
                   'fixed-budget N1 specification'),
        'distance_difference_m': abs(neutral['distance_m'] - sweep['distance_m']),
        'duration_difference_s': abs(neutral['duration_s'] - sweep['duration_s']),
        'accepted_keyscan_difference': abs(
            neutral['accepted_keyscan_count'] - sweep['accepted_keyscan_count']),
        'distance_relative_difference': relative_difference(
            neutral['distance_m'], sweep['distance_m']),
        'duration_relative_difference': relative_difference(
            neutral['duration_s'], sweep['duration_s']),
        'accepted_keyscan_relative_difference': relative_difference(
            neutral['accepted_keyscan_count'], sweep['accepted_keyscan_count']),
    }
    budget['verdict'] = ('MATCH_ACCEPTABLE'
                         if budget['distance_difference_m'] <= 0.5
                         else 'MATCH_NOT_ACCEPTABLE')
    hashes = {row['preprobe_graph_hash'] for row in metrics_rows}
    replay_check = load_json(
        root / 'canonical_history' / 'normalized_prefix' / 'replay_2x' /
        'common_prefix_replay_result.json')
    stitch_checks = [load_json(root / 'branches' / branch / 'stitched' /
                               'stitch_report.json') for branch in BRANCHES]
    frame_dir = root / 'frame_gauge_audit'
    summary = {
        'protocol': 'v9 common-prefix proof-of-design',
        'scope': 'EXPLORATORY PROOF-OF-DESIGN ONLY; n=1 branch per action',
        'frame_audit_complete': all((frame_dir / name).is_file() for name in (
            'frame_alignment_per_attempt.csv', 'frame_alignment_summary.json',
            'arrival_error_raw_vs_aligned.csv',
            'old_n1_frame_confusion_audit.json')),
        'common_prefix_replay_pass':
            replay_check['verdict'] == 'COMMON_PREFIX_REPLAY_PASS',
        'stream_stitching_pass': all(
            report['prefix_byte_identical'] and
            report['timestamps_strictly_increasing']
            for report in stitch_checks),
        'preprobe_hash_identical': len(hashes) == 1,
        'preprobe_graph_hashes': sorted(hashes),
        'branch_start_pass': all(row['branch_start_gate_passed']
                                 for row in metrics_rows),
        'action_execution_pass': all(row['action_execution_passed'] and
                                     row['accepted_keyscan_count'] > 0
                                     for row in metrics_rows),
        'constraint_analytics_pass': all(pipeline.values()),
        'graph_utility_pass': all(math.isfinite(row['delta_U_H'])
                                  for row in metrics_rows),
        'posterior_uncertainty_pass': all(pipeline.values()),
        'budget_match': budget,
        'branches': metrics_rows,
    }
    if not summary['frame_audit_complete']:
        summary['proof_of_design_decision'] = 'FRAME_SEMANTICS_UNRESOLVED'
    elif not (summary['common_prefix_replay_pass'] and
              summary['preprobe_hash_identical']):
        summary['proof_of_design_decision'] = 'COMMON_PREFIX_NOT_DETERMINISTIC'
    elif not summary['stream_stitching_pass']:
        summary['proof_of_design_decision'] = 'STREAM_STITCHING_INVALID'
    elif not summary['branch_start_pass']:
        summary['proof_of_design_decision'] = 'BRANCH_START_NOT_REPEATABLE'
    elif budget['verdict'] != 'MATCH_ACCEPTABLE':
        summary['proof_of_design_decision'] = 'BUDGET_MATCH_INVALID'
    elif not (summary['constraint_analytics_pass'] and
              summary['graph_utility_pass'] and
              summary['posterior_uncertainty_pass']):
        summary['proof_of_design_decision'] = 'ANALYSIS_PIPELINE_INVALID'
    else:
        summary['proof_of_design_decision'] = \
            'READY_FOR_COMMON_PREFIX_CONFIRMATORY_N1'

    write_csv(out_dir / 'branch_metrics.csv', metrics_rows)
    write_csv(out_dir / 'realized_constraints.csv', constraint_rows)
    write_csv(out_dir / 'posterior_uncertainty.csv', posterior_rows)
    with open(out_dir / 'budget_match.json', 'w') as stream:
        json.dump(budget, stream, indent=2, sort_keys=True)
        stream.write('\n')
    with open(out_dir / 'common_prefix_analysis_summary.json', 'w') as stream:
        json.dump(summary, stream, indent=2, sort_keys=True)
        stream.write('\n')
    decision_dir = root / 'decision'
    decision_dir.mkdir(parents=True, exist_ok=True)
    decision = {
        'protocol': summary['protocol'],
        'scope': summary['scope'],
        'gates': {key: summary[key] for key in (
            'frame_audit_complete', 'common_prefix_replay_pass',
            'stream_stitching_pass', 'preprobe_hash_identical',
            'branch_start_pass', 'action_execution_pass',
            'constraint_analytics_pass', 'graph_utility_pass',
            'posterior_uncertainty_pass')},
        'budget_match_verdict': budget['verdict'],
        'decision': summary['proof_of_design_decision'],
        'intervention_hypothesis': 'UNTESTED',
        'no_retrospective_relabel': True,
        'no_confirmatory_expansion_started': True,
    }
    with open(decision_dir / 'proof_of_design_decision.json', 'w') as stream:
        json.dump(decision, stream, indent=2, sort_keys=True)
        stream.write('\n')
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--out-dir', required=True)
    args = parser.parse_args()
    summary = analyze(args.root, args.out_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
