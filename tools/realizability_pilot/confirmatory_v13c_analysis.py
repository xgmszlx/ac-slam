#!/usr/bin/python3
"""Frozen one-time post-lock scientific analysis for v13-C."""

import argparse
import csv
import itertools
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

import edge_analytics
import se2_information
from common_prefix_analysis import (
    LOCAL_LABEL, NONTARGET_LABEL, TARGET_LABEL, classify_new_edges,
    edges_from_graph, nodes_from_graph, paper_graph_utilities,
)
from confirmatory_v13c_protocol import (
    ARMS, BOOTSTRAP_REPETITIONS, BOOTSTRAP_SEED, J_T_NONTRIVIAL_FLOOR,
    PROTOCOL_ID, RESULT_ROOT, TARGETS, sha256,
)


HEADING_THRESHOLD = 0.52
DISTANCE_THRESHOLD = 1.0
V12_TARGET_A_REFERENCE = {
    'D_sweep': {'positive': 4, 'total': 4, 'mean': 0.07086829572408293},
    'D_trigger': {'positive': 3, 'total': 4, 'mean': 0.05766937777245884},
    'D_total': {'positive': 4, 'total': 4, 'mean': 0.12853767349654177},
}


def load_json(path):
    return json.loads(Path(path).read_text())


def read_jsonl(path):
    try:
        with open(path) as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except IOError:
        return []


def atomic_json(path, payload):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def write_csv(path, rows):
    rows = list(rows)
    fields = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with open(path, 'w', newline='') as stream:
        if not fields:
            return
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def analysis_preflight(root):
    root = Path(root).resolve()
    lock_path = root / 'COLLECTION_LOCKED.json'
    if not lock_path.exists():
        raise RuntimeError('analysis locked until COLLECTION_LOCKED')
    lock = load_json(lock_path)
    state = load_json(root / 'collection/collection_state.json')
    prereg_path = root / 'preregistration/v13C_preregistration.json'
    prereg = load_json(prereg_path)
    protocol_hash = sha256(prereg_path)
    allowed_locks = {
        'COLLECTION_LOCKED_CONFIRMATORY_COMPLETE',
        'COLLECTION_LOCKED_TECHNICALLY_INCOMPLETE',
    }
    if lock.get('status') not in allowed_locks:
        raise RuntimeError('invalid collection lock status')
    if state.get('status') != lock.get('status'):
        raise RuntimeError('collection state and lock disagree')
    if not (protocol_hash == state.get('protocol_hash') ==
            lock.get('protocol_hash')):
        raise RuntimeError('v13-C preregistration hash mismatch')
    if prereg.get('protocol_id') != PROTOCOL_ID:
        raise RuntimeError('unexpected protocol id')
    relative = 'tools/realizability_pilot/confirmatory_v13c_analysis.py'
    expected = prereg.get('code_hashes', {}).get(relative)
    if not expected or expected != sha256(Path(__file__)):
        raise RuntimeError('analysis code hash differs from preregistration')
    return state, prereg, lock


def block_dir(root, block):
    return (Path(root) / block['target_label'] /
            block['block_id'].split('_H')[1])


def replay_dir(root, block, arm):
    return Path(block['branches'][arm]['replay_dir'])


def reconstruct_keyscans(combined_path, prefix_count, expected):
    records = read_jsonl(combined_path)
    previous = records[int(prefix_count) - 1]
    rows = []
    for raw_index, scan in enumerate(records[int(prefix_count):]):
        heading = math.atan2(
            math.sin(float(scan['yaw']) - float(previous['yaw'])),
            math.cos(float(scan['yaw']) - float(previous['yaw'])))
        distance = math.hypot(float(scan['x']) - float(previous['x']),
                              float(scan['y']) - float(previous['y']))
        heading_fired = abs(heading) >= HEADING_THRESHOLD - 1e-12
        distance_fired = distance * distance >= DISTANCE_THRESHOLD ** 2 - 1e-6
        if heading_fired or distance_fired:
            rows.append({
                'raw_index': raw_index,
                'criterion': 'HEADING' if heading_fired else 'DISTANCE',
                'heading_change_rad': heading,
                'travel_distance_m': distance,
                'replay_stamp_s': scan['stamp'],
            })
            previous = scan
    if len(rows) != expected:
        return [], 'RECONSTRUCTION_COUNT_MISMATCH_{}_{}'.format(
            len(rows), expected)
    return rows, 'EXACT_COUNT_MATCH'


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


def target_information(final_nodes, final_edges, target_ids):
    node_ids = sorted(final_nodes)
    information, contributors, rejected = se2_information.build_information(
        node_ids, final_edges)
    positions = [node_ids.index(int(state_id)) for state_id in target_ids]
    score, marginal = se2_information.v13_target_information_score(
        information, positions, root_position=0)
    eigenvalues = np.linalg.eigvalsh(0.5 * (marginal + marginal.T))
    return {
        'J_T': score,
        'dimension': marginal.shape[0],
        'trace': float(np.trace(marginal)),
        'logdet': float(np.linalg.slogdet(marginal)[1]),
        'eigenvalues': [float(value) for value in eigenvalues],
        'covariance': marginal.tolist(),
        'information_contributors': contributors,
        'rejected_edges': rejected,
        'estimator': ('fixed-first-pose fixed-linearisation local '
                      'linear-Gaussian joint marginal covariance'),
    }


def branch_data(root, block, arm):
    directory = block_dir(root, block)
    replay = replay_dir(root, block, arm)
    before_graph = load_json(replay / 'graph_pre.json')
    final_graph = load_json(replay / 'graph_final.json')
    before_nodes = nodes_from_graph(before_graph)
    final_nodes = nodes_from_graph(final_graph)
    before_edges = edges_from_graph(before_graph, before_nodes)
    final_edges = edges_from_graph(final_graph, final_nodes)
    frozen = load_json(directory / 'frozen_target.json')
    target_ids = [int(value) for value in frozen['historical_scan_ids']]
    history_ids = set(before_nodes)
    new_edges = classify_new_edges(before_edges, final_edges, target_ids,
                                   history_ids)
    posterior = target_information(final_nodes, final_edges, target_ids)
    utilities = paper_graph_utilities(final_nodes, final_edges, new_edges)
    result = load_json(replay / 'unified_replay_result.json')
    accepted = len(final_nodes) - len(before_nodes)
    combined = replay / 'combined_stream.jsonl'
    keyscans, keyscan_status = reconstruct_keyscans(
        combined, result['prefix_record_count'], accepted)
    capture_dir = Path(block['branches'][arm]['capture_dir'])
    capture = load_json(capture_dir / 'capture_result.json')
    raw = read_jsonl(capture_dir / 'probe_stream_raw.jsonl')
    counts = {label: sum(edge['attribution'] == label for edge in new_edges)
              for label in (TARGET_LABEL, NONTARGET_LABEL, LOCAL_LABEL)}
    provenance_records = edge_analytics.provenance_constraints(
        edge_analytics.load_provenance(replay / 'edge_provenance.jsonl'))
    provenance = {int(row['creation_sequence']) - 1: row
                  for row in provenance_records}
    insertion = edge_analytics.insertion_time_metrics(
        final_edges, final_nodes,
        [(edge['start'], edge['end']) for edge in new_edges])
    constraints = []
    for edge in new_edges:
        record = provenance.get(edge['index'], {})
        covariance = np.asarray(edge['covariance_3x3'], dtype=float)
        eigen_cov = np.linalg.eigvalsh(covariance)
        eigen_info = np.linalg.eigvalsh(np.linalg.inv(covariance))
        metric = insertion[tuple(sorted((edge['start'], edge['end'])))]
        constraints.append({
            'block_id': block['block_id'],
            'target': block['target_label'],
            'arm': arm,
            'edge_index': edge['index'],
            'source': edge['start'],
            'target_state': edge['end'],
            'attribution': edge['attribution'],
            'creation_provenance': record.get('creation_provenance'),
            'creation_stage': record.get('creation_stage'),
            'matcher_type': record.get('matcher_type'),
            'match_response': record.get('match_response'),
            'measurement_dx': edge['measurement']['dx'],
            'measurement_dy': edge['measurement']['dy'],
            'measurement_dtheta': edge['measurement']['dtheta'],
            'covariance_eigenvalues': json.dumps(eigen_cov.tolist()),
            'information_eigenvalues': json.dumps(eigen_info.tolist()),
            'constraint_d_opt': se2_information.constraint_d_opt(covariance),
            'geodesic_at_insertion_m': metric['geodesic_m'],
            'hops_at_insertion': metric['hops'],
            'cycle_length_edges': (metric['hops'] + 1
                                   if metric['hops'] is not None else None),
        })
    fov = circular_fov_union(raw)
    row = {
        'block_id': block['block_id'],
        'target': block['target_label'],
        'seed': block['seed'],
        'arm': arm,
        'budget_valid': block['budget_gate']['passed'],
        'distance_m': capture['actual_distance_m'],
        'duration_s': capture['actual_duration_s'],
        'raw_scan_count': capture['raw_scan_count'],
        'yaw_excursion_rad': capture['actual_yaw_excursion_rad'],
        'fov_union_rad': fov,
        'fov_union_deg': math.degrees(fov) if fov is not None else None,
        'accepted_keyscan_count': accepted,
        'keyscan_reconstruction_status': keyscan_status,
        'heading_triggered_keyscan_count': sum(
            item['criterion'] == 'HEADING' for item in keyscans),
        'distance_triggered_keyscan_count': sum(
            item['criterion'] == 'DISTANCE' for item in keyscans),
        'new_edge_count': len(new_edges),
        'E_T_count': counts[TARGET_LABEL],
        'E_N_count': counts[NONTARGET_LABEL],
        'local_edge_count': counts[LOCAL_LABEL],
        'target_trace': posterior['trace'],
        'target_logdet': posterior['logdet'],
        'J_T': posterior['J_T'],
        'U_all': utilities['all'],
        'U_without_target': utilities['target_removed'],
        'delta_U_T': (None if utilities['target_removed_disconnects_graph']
                      else utilities['all'] - utilities['target_removed']),
        'target_removed_disconnects_graph':
            utilities['target_removed_disconnects_graph'],
        'U_without_history': utilities['history_removed'],
        'history_removed_disconnects_graph':
            utilities['history_removed_disconnects_graph'],
    }
    detail = {
        'metrics': row,
        'target_ids': target_ids,
        'target_posterior': posterior,
        'keyscans': keyscans,
        'new_edges': new_edges,
        'provenance': provenance,
        'target_edge_pairs': sorted({tuple(sorted((edge['start'], edge['end'])))
                                     for edge in new_edges
                                     if edge['attribution'] == TARGET_LABEL}),
    }
    return row, detail, constraints


def exact_sign_test_one_sided(positive, total):
    return sum(math.comb(total, value)
               for value in range(positive, total + 1)) / float(2 ** total)


def exact_sign_flip_p(values):
    if not values:
        return None
    observed = float(np.mean(values))
    distribution = [
        float(np.mean([sign * value for sign, value in zip(signs, values)]))
        for signs in itertools.product((-1.0, 1.0), repeat=len(values))]
    return sum(value >= observed - 1e-15 for value in distribution) / float(
        len(distribution))


def contrast_summary(rows, left, right, name):
    grouped = defaultdict(dict)
    for row in rows:
        grouped[row['block_id']][row['arm']] = row
    paired = []
    for block_id, arms in sorted(grouped.items()):
        if left in arms and right in arms:
            paired.append({
                'block_id': block_id,
                'target': arms[left]['target'],
                'contrast': name,
                'left_arm': left,
                'right_arm': right,
                'difference': float(arms[left]['J_T'] - arms[right]['J_T']),
            })
    values = [row['difference'] for row in paired]
    by_target = {target: [row['difference'] for row in paired
                          if row['target'] == target]
                 for target in TARGETS}
    target_positive = {target: sum(value > 0.0 for value in target_values)
                       for target, target_values in by_target.items()}
    positive = sum(value > 0.0 for value in values)
    evaluable = (len(values) == 8 and
                 all(len(by_target[target]) == 4 for target in TARGETS))
    rng = random.Random(BOOTSTRAP_SEED)
    bootstrap = []
    if all(by_target.values()):
        for _ in range(BOOTSTRAP_REPETITIONS):
            sample = []
            for target in TARGETS:
                sample.extend(rng.choice(by_target[target])
                              for _ in range(len(by_target[target])))
            bootstrap.append(float(np.mean(sample)))
    interval = ([float(np.percentile(bootstrap, 2.5)),
                 float(np.percentile(bootstrap, 97.5))]
                if bootstrap else None)
    mean = float(np.mean(values)) if values else None
    target_means = {target: (float(np.mean(target_values))
                             if target_values else None)
                    for target, target_values in by_target.items()}
    supported = bool(
        evaluable and positive >= 6 and
        all(target_positive[target] >= 3 for target in TARGETS) and
        mean is not None and mean > J_T_NONTRIVIAL_FLOOR and
        interval is not None and interval[0] > 0.0)
    heterogeneous = bool(
        evaluable and (
            ((target_positive['target_A'] >= 3 and
              target_positive['target_B'] <= 2) or
             (target_positive['target_B'] >= 3 and
              target_positive['target_A'] <= 2)) or
            target_means['target_A'] * target_means['target_B'] < 0.0))
    return paired, {
        'contrast': name,
        'left_arm': left,
        'right_arm': right,
        'usable_blocks': len(values),
        'values': values,
        'positive_blocks': positive,
        'target_positive': target_positive,
        'mean': mean,
        'median': float(np.median(values)) if values else None,
        'target_means': target_means,
        'target_medians': {
            target: (float(np.median(target_values))
                     if target_values else None)
            for target, target_values in by_target.items()},
        'one_sided_exact_sign_test_p': (
            exact_sign_test_one_sided(positive, len(values))
            if values else None),
        'one_sided_exact_sign_flip_mean_p': exact_sign_flip_p(values),
        'target_stratified_block_bootstrap_mean_95pct_CI': interval,
        'confirmatory_evaluable': evaluable,
        'target_dependent_heterogeneity': heterogeneous,
        'supported_by_preregistered_rule': supported,
        'confirmatory_verdict': (
            'SUPPORTED' if supported else
            'NOT_SUPPORTED' if evaluable else
            'INCONCLUSIVE_TECHNICAL_INCOMPLETENESS'),
    }


def mechanism_summary(metrics, constraints, details):
    by_block = defaultdict(dict)
    for key, detail in details.items():
        block_id, arm = key.split(':', 1)
        by_block[block_id][arm] = {
            tuple(pair) for pair in detail['target_edge_pairs']}
    identity = {}
    for block_id, arms in sorted(by_block.items()):
        complete = all(arm in arms for arm in ARMS)
        exact = complete and all(arms[arm] == arms[ARMS[0]]
                                 for arm in ARMS[1:])
        identity[block_id] = {
            'all_arms_present': complete,
            'exact_target_edge_sets_equal': exact,
            'target_edge_counts': {arm: len(arms.get(arm, set()))
                                   for arm in ARMS},
        }
    swap_identifiable = bool(identity) and all(
        row['exact_target_edge_sets_equal'] for row in identity.values())
    history_critical = [bool(row['history_removed_disconnects_graph'])
                        for row in metrics]
    return {
        'constraint_counts_by_arm': {
            arm: {
                'all_new': sum(row['arm'] == arm for row in constraints),
                'E_T': sum(row['arm'] == arm and
                           row['attribution'] == TARGET_LABEL
                           for row in constraints),
                'E_N': sum(row['arm'] == arm and
                           row['attribution'] == NONTARGET_LABEL
                           for row in constraints),
                'local': sum(row['arm'] == arm and
                             row['attribution'] == LOCAL_LABEL
                             for row in constraints),
            } for arm in ARMS},
        'creation_provenance_by_arm': {
            arm: dict(Counter(
                row.get('creation_provenance') or 'UNKNOWN'
                for row in constraints if row['arm'] == arm))
            for arm in ARMS},
        'matcher_type_by_arm': {
            arm: dict(Counter(
                row.get('matcher_type') or 'UNKNOWN'
                for row in constraints if row['arm'] == arm))
            for arm in ARMS},
        'target_edge_identity_by_block': identity,
        'covariance_swap': {
            'identifiable': swap_identifiable,
            'verdict': ('IDENTIFIABLE' if swap_identifiable else
                        'COUNTERFACTUAL_SWAP_NOT_IDENTIFIABLE'),
        },
        'history_ablation': {
            'branches_disconnected_after_history_edge_removal':
                sum(history_critical),
            'analyzed_branches': len(history_critical),
            'verdict': ('HISTORY_CONNECTIVITY_CRITICAL'
                        if any(history_critical) else
                        'FINITE_HISTORY_ABLATION'),
        },
        'arm_means': {
            arm: {field: float(np.mean([
                row[field] for row in metrics if row['arm'] == arm]))
                  for field in ('accepted_keyscan_count', 'new_edge_count',
                                'E_T_count', 'E_N_count', 'local_edge_count')}
            for arm in ARMS if any(row['arm'] == arm for row in metrics)},
    }


def replication_reference(summaries):
    records = {}
    for name, reference in V12_TARGET_A_REFERENCE.items():
        target_a = summaries[name]['values'][:4]
        fresh_mean = float(np.mean(target_a)) if target_a else None
        records[name] = {
            'v12_reference': reference,
            'v13C_target_A_values': target_a,
            'v13C_target_A_mean': fresh_mean,
            'direction_qualitatively_consistent': (
                fresh_mean is not None and
                (fresh_mean > 0.0) == (reference['mean'] > 0.0)),
        }
    return {
        'role': 'EXTERNAL_DESCRIPTIVE_REPLICATION_NOT_POOLED',
        'estimand_changed_to_local_region': True,
        'magnitude_formally_pooled': False,
        'contrasts': records,
    }


def analyze(root=RESULT_ROOT):
    root = Path(root).resolve()
    state, prereg, lock = analysis_preflight(root)
    out = root / 'analysis'
    out.mkdir(parents=True, exist_ok=True)
    ledger, metrics, constraints, details = [], [], [], {}
    for block in state['blocks']:
        budget = block.get('budget_gate', {})
        observed = budget.get('observed', {})
        branches = block.get('branches', {})
        ledger.append({
            'block_id': block['block_id'],
            'target': block['target_label'],
            'seed': block['seed'],
            'status': block['status'],
            'budget_valid': budget.get('passed'),
            'budget_distance_range_m': observed.get('distance_range_m'),
            'budget_time_range_s': observed.get('time_range_s'),
            'budget_raw_scan_relative_range': observed.get(
                'raw_scan_relative_range'),
            **{arm + '_status': branches.get(arm, {}).get('status')
               for arm in ARMS},
            'primary_analysis_eligible': block['status'] == 'COLLECTED',
        })
        if block['status'] != 'COLLECTED':
            continue
        for arm in ARMS:
            row, detail, constraint_rows = branch_data(root, block, arm)
            metrics.append(row)
            constraints.extend(constraint_rows)
            details['{}:{}'.format(block['block_id'], arm)] = detail
    write_csv(out / 'block_ledger.csv', ledger)
    write_csv(out / 'branch_metrics.csv', metrics)
    write_csv(out / 'constraint_mechanism.csv', constraints)
    atomic_json(out / 'branch_details.json', details)

    definitions = (
        ('D_sweep', 'A2_SWEEP90', 'A3_MIN_TRIGGER'),
        ('D_trigger', 'A3_MIN_TRIGGER', 'A1_DWELL'),
        ('D_total', 'A2_SWEEP90', 'A1_DWELL'),
    )
    paired_rows, summaries = [], {}
    for name, left, right in definitions:
        paired, summary = contrast_summary(metrics, left, right, name)
        paired_rows.extend(paired)
        summaries[name] = summary
    write_csv(out / 'paired_contrasts.csv', paired_rows)
    atomic_json(out / 'contrast_summary.json', summaries)
    mechanism = mechanism_summary(metrics, constraints, details)
    atomic_json(out / 'mechanism_summary.json', mechanism)
    replication = replication_reference(summaries)
    atomic_json(out / 'v12_target_A_replication.json', replication)

    usable = {row['block_id'] for row in metrics}
    usable_by_target = {target: len({row['block_id'] for row in metrics
                                     if row['target'] == target})
                        for target in TARGETS}
    complete = (lock['status'] == 'COLLECTION_LOCKED_CONFIRMATORY_COMPLETE'
                and len(usable) == 8 and len(metrics) == 24 and
                all(usable_by_target[target] == 4 for target in TARGETS))
    sweep = summaries['D_sweep']['supported_by_preregistered_rule']
    trigger = summaries['D_trigger']['supported_by_preregistered_rule']
    heterogeneity = summaries['D_sweep']['target_dependent_heterogeneity']
    if not complete:
        final_gate = 'CONFIRMATORY_EXPERIMENT_TECHNICALLY_INCOMPLETE'
    elif heterogeneity:
        final_gate = 'PAUSE_FOR_CONTEXT_CONDITIONED_REFRAMING'
    elif sweep and trigger:
        final_gate = 'PROCEED_TO_MODELING_MIXED_ACTION_CONSTRAINT_GENERATION'
    elif not sweep and trigger:
        final_gate = 'PROCEED_WITH_BACKEND_GENERALITY_CHECK'
    elif sweep and not trigger:
        final_gate = 'PROCEED_WITH_BROAD_SWEEP_NOVELTY_REAUDIT'
    else:
        final_gate = 'STOP_SWEEP_INTERVENTION_LINE'
    final = {
        'status': 'ANALYZED',
        'protocol_id': PROTOCOL_ID,
        'protocol_hash': lock['protocol_hash'],
        'collection_lock_status': lock['status'],
        'confirmatory_evaluable': complete,
        'planned_blocks': 8,
        'usable_blocks': len(usable),
        'usable_blocks_by_target': usable_by_target,
        'planned_branches': 24,
        'analyzed_branches': len(metrics),
        'contrasts': summaries,
        'D_sweep_target_dependent_heterogeneity': heterogeneity,
        'mechanism': mechanism,
        'v12_target_A_replication': replication,
        'technical_exclusion_counts': dict(Counter(
            block['status'] for block in state['blocks'])),
        'statistical_unit': 'canonical-history block',
        'branch_level_pseudoreplication_used': False,
        'v12_v12b_pooled': False,
        'posterior_language': ('local fixed-linearisation linear-Gaussian '
                               'interpretation; not exact nonlinear causality'),
        'final_scientific_gate': final_gate,
    }
    atomic_json(out / 'confirmatory_summary.json', final)
    decision = root / 'decision'
    decision.mkdir(exist_ok=True)
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
