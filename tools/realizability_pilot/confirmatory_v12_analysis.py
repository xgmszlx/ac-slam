#!/usr/bin/python3
"""Outcome analysis for the sealed v12 confirmatory collection."""

import argparse
import csv
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

import edge_analytics
import se2_information
from common_prefix_analysis import (
    LOCAL_LABEL, NONTARGET_LABEL, TARGET_LABEL, classify_new_edges,
    covariance_text, edges_from_graph, nodes_from_graph, paper_graph_utilities,
)
from confirmatory_v12_protocol import ARMS, PROTOCOL_ID, RESULT_ROOT, sha256


HEADING_THRESHOLD = 0.52
DISTANCE_THRESHOLD = 1.0
HEADING_RECONSTRUCTION_TOLERANCE = 1e-12


def load_json(path):
    return json.loads(Path(path).read_text())


def read_jsonl(path):
    with open(path) as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_csv(path, rows):
    rows = list(rows)
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with open(path, 'w', newline='') as stream:
        if not fields:
            return
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def atomic_json(path, payload):
    path = Path(path); temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def fixed_root_covariance(nodes, edges, root_id=None):
    node_ids = sorted(nodes)
    root_id = node_ids[0] if root_id is None else int(root_id)
    information, contributors, rejected = se2_information.build_information(
        node_ids, edges)
    root_position = node_ids.index(root_id)
    root_indices = set(range(3 * root_position, 3 * root_position + 3))
    retained = [index for index in range(information.shape[0])
                if index not in root_indices]
    reduced = information[np.ix_(retained, retained)]
    eigenvalues = np.linalg.eigvalsh(0.5 * (reduced + reduced.T))
    tolerance = max(float(np.max(np.abs(eigenvalues))) * 1e-10, 1e-12)
    if np.any(eigenvalues <= tolerance):
        raise ValueError('fixed-root graph information is singular/disconnected')
    reduced_covariance = np.linalg.inv(reduced)
    full = np.zeros_like(information)
    full[np.ix_(retained, retained)] = reduced_covariance
    return full, {'root_id': root_id, 'contributors': contributors,
                  'rejected_edges': rejected,
                  'minimum_reduced_information_eigenvalue': float(
                      np.min(eigenvalues))}


def joint_metrics(covariance, node_ids, selected_ids):
    index = {node_id: position for position, node_id in enumerate(node_ids)}
    indices = []
    for node_id in selected_ids:
        position = index[int(node_id)]
        indices.extend(range(3 * position, 3 * position + 3))
    marginal = covariance[np.ix_(indices, indices)]
    marginal = 0.5 * (marginal + marginal.T)
    sign, logdet = np.linalg.slogdet(marginal)
    eigenvalues = np.linalg.eigvalsh(marginal)
    if sign <= 0 or not np.all(np.isfinite(marginal)):
        raise ValueError('target marginal is not finite positive definite')
    return {'dimension': len(indices), 'trace': float(np.trace(marginal)),
            'logdet': float(logdet), 'J': float(-logdet / len(indices)),
            'eigenvalues': [float(value) for value in eigenvalues],
            'covariance': marginal.tolist()}


def wrap_angle(value):
    return math.atan2(math.sin(value), math.cos(value))


def reconstruct_keyscans(replay_dir):
    result = load_json(replay_dir / 'branch_replay_result.json')
    records = read_jsonl(replay_dir / 'combined_stream.jsonl')
    prefix_count = int(result['prefix_record_count'])
    expected = int(result['accepted_probe_keyscan_count'])

    def apply(heading_tolerance, policy):
        previous = records[prefix_count - 1]
        rows = []
        for raw_index, scan in enumerate(records[prefix_count:]):
            heading = wrap_angle(float(scan['yaw']) - float(previous['yaw']))
            distance = math.hypot(float(scan['x']) - float(previous['x']),
                                  float(scan['y']) - float(previous['y']))
            heading_fired = (abs(heading) >=
                             HEADING_THRESHOLD - heading_tolerance)
            distance_fired = (distance * distance >=
                              DISTANCE_THRESHOLD ** 2 - 1e-6)
            if heading_fired or distance_fired:
                rows.append({
                    'raw_index': raw_index,
                    'criterion': 'HEADING' if heading_fired else 'DISTANCE',
                    'heading_change_rad': heading,
                    'travel_distance_m': distance,
                    'replay_stamp_s': scan['stamp'],
                    'heading_boundary_policy': policy,
                    'heading_boundary_tolerance_rad': heading_tolerance,
                })
                previous = scan
        return rows

    # Use the literal frozen threshold whenever it reproduces the backend.
    # Only a count mismatch authorizes the machine-scale equality fallback;
    # this avoids shifting already exact branches at the 0.52-rad boundary.
    strict = apply(0.0, 'STRICT_RECORDED_DOUBLE')
    if len(strict) == expected:
        return strict
    tolerant = apply(HEADING_RECONSTRUCTION_TOLERANCE,
                     'MACHINE_SCALE_EQUALITY_FALLBACK')
    if len(tolerant) == expected:
        return tolerant
    raise AssertionError(
        'keyscan reconstruction mismatch: strict={} tolerant={} recorded={}'
        .format(len(strict), len(tolerant), expected))


def circular_fov_union(raw_records):
    if not raw_records:
        return None
    intervals = []
    twopi = 2.0 * math.pi
    for row in raw_records:
        low = (float(row['yaw']) + float(row['angle_min'])) % twopi
        high = (float(row['yaw']) + float(row['angle_max'])) % twopi
        width = float(row['angle_max']) - float(row['angle_min'])
        if width >= twopi:
            return twopi
        if low <= high:
            intervals.append((low, high))
        else:
            intervals.extend(((low, twopi), (0.0, high)))
    merged = []
    for low, high in sorted(intervals):
        if not merged or low > merged[-1][1]:
            merged.append([low, high])
        else:
            merged[-1][1] = max(merged[-1][1], high)
    return sum(high - low for low, high in merged)


def branch_data(root, state_block, arm):
    block_dir = root / state_block['target_label'] / state_block['block_id'].split('_')[-1]
    replay_dir = block_dir / arm / 'replay'
    capture_dir = Path(state_block['branches'][arm]['capture_dir'])
    frozen = load_json(block_dir / 'frozen_target.json')
    before_graph = load_json(replay_dir / 'graph_preprobe.json')
    final_graph = load_json(replay_dir / 'graph_final.json')
    before_nodes = nodes_from_graph(before_graph)
    final_nodes = nodes_from_graph(final_graph)
    before_edges = edges_from_graph(before_graph, before_nodes)
    final_edges = edges_from_graph(final_graph, final_nodes)
    history_ids = set(before_nodes)
    target_ids = [int(value) for value in frozen['historical_scan_ids']]
    new_edges = classify_new_edges(before_edges, final_edges, target_ids,
                                   history_ids)
    covariance, root_diagnostic = fixed_root_covariance(final_nodes, final_edges)
    target = joint_metrics(covariance, sorted(final_nodes), target_ids)
    terminal = joint_metrics(covariance, sorted(final_nodes), [max(history_ids)])
    utilities = paper_graph_utilities(final_nodes, final_edges, new_edges)
    provenance_records = [row for row in read_jsonl(
        replay_dir / 'edge_provenance.jsonl')
                          if row.get('record_type') == 'constraint_created']
    provenance = {int(row['creation_sequence']) - 1: row
                  for row in provenance_records}
    keyscans = reconstruct_keyscans(replay_dir)
    capture = load_json(capture_dir / 'capture_result.json')
    raw = read_jsonl(capture_dir / 'probe_stream_raw.jsonl')
    counts = {label: sum(edge['attribution'] == label for edge in new_edges)
              for label in (TARGET_LABEL, NONTARGET_LABEL, LOCAL_LABEL)}
    row = {
        'block_id': state_block['block_id'],
        'target': state_block['target_label'], 'seed': state_block['active_seed'],
        'arm': arm, 'budget_valid': state_block['budget_gate']['passed'],
        'prefix_hash': state_block['branches'][arm]['prefix_hash'],
        'distance_m': capture['actual_distance_m'],
        'duration_s': capture['actual_duration_s'],
        'raw_scan_count': capture['raw_scan_count'],
        'yaw_excursion_rad': capture['actual_yaw_excursion_rad'],
        'fov_union_rad': circular_fov_union(raw),
        'fov_union_deg': math.degrees(circular_fov_union(raw)),
        'accepted_keyscan_count': len(keyscans),
        'heading_triggered_keyscan_count': sum(
            item['criterion'] == 'HEADING' for item in keyscans),
        'distance_triggered_keyscan_count': sum(
            item['criterion'] == 'DISTANCE' for item in keyscans),
        'new_edge_count': len(new_edges),
        'E_T_count': counts[TARGET_LABEL],
        'E_N_count': counts[NONTARGET_LABEL],
        'local_edge_count': counts[LOCAL_LABEL],
        'target_trace': target['trace'], 'target_logdet': target['logdet'],
        'J_T': target['J'], 'terminal_trace': terminal['trace'],
        'terminal_logdet': terminal['logdet'],
        'U_all': utilities['all'], 'U_without_target': utilities['target_removed'],
        'delta_U_T': utilities['all'] - utilities['target_removed'],
        'U_without_history': utilities['history_removed'],
        'history_removed_disconnects_graph':
            utilities['history_removed_disconnects_graph'],
    }
    details = {'metrics': row, 'target_ids': target_ids,
               'target_posterior': target, 'terminal_posterior': terminal,
               'fixed_root': root_diagnostic, 'keyscans': keyscans,
               'new_edges': new_edges, 'provenance': provenance}
    constraint_rows = []
    insertion = edge_analytics.insertion_time_metrics(
        final_edges, final_nodes,
        [(edge['start'], edge['end']) for edge in new_edges])
    for edge in new_edges:
        record = provenance.get(edge['index'], {})
        covariance_edge = np.asarray(edge['covariance_3x3'], dtype=float)
        eigen_cov = np.linalg.eigvalsh(covariance_edge)
        eigen_info = np.linalg.eigvalsh(np.linalg.inv(covariance_edge))
        metric = insertion[tuple(sorted((edge['start'], edge['end'])))]
        constraint_rows.append({
            'block_id': row['block_id'], 'target': row['target'], 'arm': arm,
            'edge_index': edge['index'], 'source': edge['start'],
            'target_state': edge['end'], 'attribution': edge['attribution'],
            'creation_provenance': record.get('creation_provenance'),
            'creation_stage': record.get('creation_stage'),
            'matcher_type': record.get('matcher_type'),
            'match_response': record.get('match_response'),
            'geodesic_at_insertion_m': metric['geodesic_m'],
            'hops_at_insertion': metric['hops'],
            'covariance_eigenvalues': json.dumps(eigen_cov.tolist()),
            'information_eigenvalues': json.dumps(eigen_info.tolist()),
            'constraint_d_opt': se2_information.constraint_d_opt(covariance_edge),
        })
    return row, details, constraint_rows


def sign_test_one_sided(positive, total):
    return sum(math.comb(total, value) for value in range(positive, total + 1)) \
        / float(2 ** total)


def contrast_summary(rows, left, right, name):
    by_block = defaultdict(dict)
    for row in rows:
        by_block[row['block_id']][row['arm']] = row
    paired = []
    for block_id, arms in sorted(by_block.items()):
        if left not in arms or right not in arms:
            continue
        paired.append({'block_id': block_id, 'target': arms[left]['target'],
                       'contrast': name, 'left_arm': left, 'right_arm': right,
                       'difference': arms[left]['J_T'] - arms[right]['J_T']})
    values = [row['difference'] for row in paired]
    positive = sum(value > 0.0 for value in values)
    target_positive = {target: sum(row['difference'] > 0.0 for row in paired
                                   if row['target'] == target)
                       for target in ('target_A', 'target_B')}
    by_target = {target: [row['difference'] for row in paired
                          if row['target'] == target]
                 for target in ('target_A', 'target_B')}
    confirmatory_evaluable = (len(values) == 8 and
                              len(by_target['target_A']) == 4 and
                              len(by_target['target_B']) == 4)
    supported = (confirmatory_evaluable and positive >= 7 and
                 target_positive['target_A'] >= 3 and
                 target_positive['target_B'] >= 3)
    rng = random.Random(120917)
    bootstrap = []
    if all(by_target.values()):
        for _ in range(10000):
            sample = []
            for target in ('target_A', 'target_B'):
                values_target = by_target[target]
                sample.extend(rng.choice(values_target)
                              for _ in range(len(values_target)))
            bootstrap.append(float(np.mean(sample)))
    target_bootstrap = {}
    for target, target_values in by_target.items():
        if not target_values:
            target_bootstrap[target] = None
            continue
        samples = [float(np.mean([
            rng.choice(target_values) for _ in range(len(target_values))]))
                   for _ in range(10000)]
        target_bootstrap[target] = [float(np.percentile(samples, 2.5)),
                                    float(np.percentile(samples, 97.5))]
    return paired, {
        'contrast': name, 'left_arm': left, 'right_arm': right,
        'usable_blocks': len(values), 'positive_blocks': positive,
        'target_positive': target_positive,
        'values': values, 'mean': float(np.mean(values)) if values else None,
        'median': float(np.median(values)) if values else None,
        'target_means': {target: float(np.mean(items)) if items else None
                         for target, items in by_target.items()},
        'target_medians': {target: float(np.median(items)) if items else None
                           for target, items in by_target.items()},
        'one_sided_exact_sign_test_p': sign_test_one_sided(positive, len(values))
            if values else None,
        'stratified_block_bootstrap_mean_95pct_CI': (
            [float(np.percentile(bootstrap, 2.5)),
             float(np.percentile(bootstrap, 97.5))] if bootstrap else None),
        'target_descriptive_bootstrap_mean_95pct_CI': target_bootstrap,
        'confirmatory_evaluable': confirmatory_evaluable,
        'confirmatory_verdict': ('SUPPORTED' if supported else
                                 'NOT_SUPPORTED' if confirmatory_evaluable else
                                 'NOT_EVALUABLE_TECHNICAL_INCOMPLETENESS'),
        'supported_by_preregistered_rule': supported,
    }


def analyze(root):
    root = Path(root).resolve()
    marker = root / 'COLLECTION_COMPLETE.json'
    if not marker.exists():
        raise RuntimeError('analysis locked until COLLECTION_COMPLETE')
    state = load_json(root / 'collection_state.json')
    prereg_path = root / 'preregistration/v12_preregistration.json'
    prereg = load_json(prereg_path)
    if sha256(prereg_path) != state['protocol_hash']:
        raise RuntimeError('protocol hash mismatch')
    expected_hash = prereg['code_hashes'].get(
        'tools/realizability_pilot/confirmatory_v12_analysis.py')
    actual_hash = sha256(Path(__file__))
    if expected_hash and expected_hash != actual_hash:
        amendment_path = (root / 'preregistration/'
                          'technical_amendment_03_incomplete_analysis_gate.json')
        numeric_path = (root / 'preregistration/'
                        'technical_amendment_04_keyscan_boundary.json')
        if not amendment_path.exists() or not numeric_path.exists():
            raise RuntimeError('analysis code hash differs from preregistration')
        amendment = load_json(amendment_path)
        numeric = load_json(numeric_path)
        if (amendment.get('old_analysis_code_sha256') != expected_hash or
                numeric.get('old_analysis_code_sha256') !=
                amendment.get('amended_analysis_code_sha256') or
                numeric.get('amended_analysis_code_sha256') != actual_hash or
                amendment.get('changes_primary_endpoint') is not False or
                amendment.get('outcome_blind') is not True or
                numeric.get('changes_primary_endpoint') is not False):
            raise RuntimeError('analysis amendment hash/scope validation failed')
    out = root / 'analysis'; out.mkdir(parents=True, exist_ok=True)
    metrics, constraints, details = [], [], {}
    ledger = []
    for block in state['blocks']:
        branch_statuses = block.get('branches', {})
        budget = block.get('budget_gate', {})
        budget_observed = budget.get('observed', {})
        ledger.append({
            'block_id': block['block_id'], 'target': block['target_label'],
            'planned_seed': block['planned_seed'], 'active_seed': block['active_seed'],
            'status': block['status'], 'budget_valid':
                budget.get('passed'),
            'budget_distance_range_m': budget_observed.get('distance_range_m'),
            'budget_time_range_s': budget_observed.get('time_range_s'),
            'budget_raw_scan_relative_range': budget_observed.get(
                'raw_scan_relative_range'),
            'history_attempt_count': len(block['history_attempts']),
            'reserve_used': block['active_seed'] != block['planned_seed'],
            'prefix_hash': block.get('canonical_prefix_hash'),
            'A1_status': branch_statuses.get('A1_DWELL', {}).get('status'),
            'A3_status': branch_statuses.get('A3_MIN_TRIGGER', {}).get('status'),
            'A2_status': branch_statuses.get('A2_SWEEP90', {}).get('status'),
            'primary_analysis_eligible': block['status'] == 'COLLECTED',
        })
        if block['status'] != 'COLLECTED':
            continue
        for arm in ARMS:
            row, detail, constraint_rows = branch_data(root, block, arm)
            metrics.append(row); constraints.extend(constraint_rows)
            details['{}:{}'.format(block['block_id'], arm)] = detail
    write_csv(out / 'block_ledger.csv', ledger)
    write_csv(out / 'branch_metrics.csv', metrics)
    write_csv(out / 'constraint_mechanism.csv', constraints)
    atomic_json(out / 'branch_details.json', details)

    all_pairs, summaries = [], {}
    definitions = (
        ('D_view', 'A2_SWEEP90', 'A3_MIN_TRIGGER'),
        ('D_trigger', 'A3_MIN_TRIGGER', 'A1_DWELL'),
        ('D_total', 'A2_SWEEP90', 'A1_DWELL'))
    for name, left, right in definitions:
        paired, summary = contrast_summary(metrics, left, right, name)
        all_pairs.extend(paired); summaries[name] = summary
    write_csv(out / 'paired_contrasts.csv', all_pairs)
    atomic_json(out / 'contrast_summary.json', summaries)

    view = summaries['D_view']['supported_by_preregistered_rule']
    trigger = summaries['D_trigger']['supported_by_preregistered_rule']
    usable_block_ids = {row['block_id'] for row in metrics}
    usable_by_target = {
        target: len({row['block_id'] for row in metrics
                     if row['target'] == target})
        for target in ('target_A', 'target_B')}
    confirmatory_complete = (len(usable_block_ids) == 8 and
                             usable_by_target == {'target_A': 4, 'target_B': 4})
    target_direction = {}
    for target in ('target_A', 'target_B'):
        target_direction[target] = {
            name: math.copysign(1, summary['target_means'][target])
            if summary['target_means'][target] else 0
            for name, summary in summaries.items()}
    heterogeneous = any(
        target_direction['target_A'][name] * target_direction['target_B'][name] < 0
        for name in ('D_view', 'D_trigger'))
    if not confirmatory_complete:
        classification = 'CONFIRMATORY_EXPERIMENT_TECHNICALLY_INCOMPLETE'
        gate = 'CONFIRMATORY_EXPERIMENT_TECHNICALLY_INCOMPLETE'
    elif heterogeneous:
        classification = 'TARGET_DEPENDENT_HETEROGENEITY'
        gate = 'PAUSE_FOR_REFRAMING'
    elif view and trigger:
        classification = 'MIXED_ACTION_CONSTRAINT_GENERATION_SUPPORTED'
        gate = 'PROCEED_TO_MODELING'
    elif trigger:
        classification = 'KEYSCAN_FACTOR_GENERATION_DOMINANT'
        gate = 'PROCEED_WITH_BACKEND_GENERALITY_CHECK'
    elif view:
        classification = 'BROAD_SWEEP_INCREMENT_DOMINANT'
        gate = 'PROCEED_WITH_NOVELTY_REAUDIT'
    else:
        classification = 'NO_STABLE_ACTION_EFFECT'
        gate = 'STOP_DIRECTION'
    manipulation = {
        arm: {
            'accepted_keyscans': [row['accepted_keyscan_count'] for row in metrics
                                  if row['arm'] == arm],
            'heading_triggered_keyscans': [
                row['heading_triggered_keyscan_count'] for row in metrics
                if row['arm'] == arm],
            'yaw_excursion_rad': [row['yaw_excursion_rad'] for row in metrics
                                  if row['arm'] == arm],
            'fov_union_deg': [row['fov_union_deg'] for row in metrics
                              if row['arm'] == arm],
        } for arm in ARMS}
    a3_weak = (np.median(manipulation['A3_MIN_TRIGGER']['accepted_keyscans']) <=
               np.median(manipulation['A1_DWELL']['accepted_keyscans'])) \
        if metrics else None
    final = {
        'status': 'ANALYZED', 'protocol_id': PROTOCOL_ID,
        'analysis_scope': ('DESCRIPTIVE_ONLY_VALID_TARGET_A_BLOCKS'
                           if not confirmatory_complete else
                           'PREREGISTERED_CONFIRMATORY'),
        'confirmatory_complete': confirmatory_complete,
        'planned_blocks': 8, 'usable_blocks': len(usable_block_ids),
        'usable_blocks_by_target': usable_by_target,
        'planned_branches': 24, 'analyzed_branches': len(metrics),
        'contrasts': summaries, 'manipulation_checks': manipulation,
        'A3_keyscan_control_manipulation_weak': bool(a3_weak),
        'classification': classification, 'final_gate': gate,
        'technical_exclusion_counts': {
            status: sum(block['status'] == status for block in state['blocks'])
            for status in sorted({block['status'] for block in state['blocks']})},
        'statistical_unit': 'canonical-history block',
        'pseudo_replication_used': False,
        'language_boundary': ('executed action -> actual factor generation -> '
                              'realized factor set -> local Gaussian posterior'),
    }
    atomic_json(out / 'confirmatory_summary.json', final)
    decision = root / 'decision'; decision.mkdir(exist_ok=True)
    atomic_json(decision / 'final_gate.json', final)
    print(json.dumps(final, indent=2, sort_keys=True))
    return final


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=RESULT_ROOT)
    args = parser.parse_args()
    analyze(args.root)


if __name__ == '__main__':
    main()
