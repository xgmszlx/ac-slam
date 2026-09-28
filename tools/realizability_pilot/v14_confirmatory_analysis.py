#!/usr/bin/python3
"""Frozen post-lock analysis for the v14 prospective validation."""

import argparse
import csv
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
    edges_from_graph, nodes_from_graph,
)
from controlled_branch_suite import atomic_json
from mechanism_classifier import constraint_family, is_explicit_try_close_loop
from v14_confirmatory_protocol import (
    ARMS, BOOTSTRAP_REPETITIONS, BOOTSTRAP_SEED, J_T_NONTRIVIAL_FLOOR,
    PREREGISTRATION_PATH, PROTOCOL_ID, RESULT_ROOT, ROOT, TARGETS,
    frozen_blocks, load_json, sha256, source_attempt,
)
from v14_estimator_sanity import estimator_effect_sanity, freeze_world_gauge


PHYSICAL_LOCK = RESULT_ROOT / 'collection/PHYSICAL_COLLECTION_LOCK.json'
BACKEND_LOCK = RESULT_ROOT / 'collection/BACKEND_REPLAY_LOCK.json'


def read_jsonl(path):
    try:
        with open(path) as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except OSError:
        return []


def write_csv(path, rows):
    rows = list(rows)
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='') as stream:
        if fields:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)


def analysis_preflight(root=RESULT_ROOT):
    root = Path(root).resolve()
    if root != RESULT_ROOT.resolve():
        raise RuntimeError('v14 analysis only accepts the frozen result root')
    for path in (PREREGISTRATION_PATH, PHYSICAL_LOCK, BACKEND_LOCK):
        if not path.is_file():
            raise RuntimeError('analysis requires frozen {}'.format(path.name))
    prereg = load_json(PREREGISTRATION_PATH)
    physical = load_json(PHYSICAL_LOCK)
    backend = load_json(BACKEND_LOCK)
    relative = 'tools/realizability_pilot/v14_confirmatory_analysis.py'
    if prereg['code_hashes'].get(relative) != sha256(Path(__file__)):
        raise RuntimeError('analysis code differs from preregistration')
    if backend['preregistration_sha256'] != sha256(PREREGISTRATION_PATH):
        raise RuntimeError('backend lock preregistration hash mismatch')
    if backend['physical_collection_lock_sha256'] != sha256(PHYSICAL_LOCK):
        raise RuntimeError('backend lock physical hash mismatch')
    return prereg, physical, backend


def target_information(nodes, edges, target_ids):
    node_ids = sorted(nodes)
    information, contributors, rejected = se2_information.build_information(
        node_ids, edges)
    positions = [node_ids.index(int(state_id)) for state_id in target_ids]
    score, marginal = se2_information.v13_target_information_score(
        information, positions, root_position=0)
    eigenvalues = np.linalg.eigvalsh(0.5 * (marginal + marginal.T))
    return {
        'J_T': float(score), 'dimension': int(marginal.shape[0]),
        'trace': float(np.trace(marginal)),
        'logdet': float(np.linalg.slogdet(marginal)[1]),
        'eigenvalues': [float(value) for value in eigenvalues],
        'covariance': marginal.tolist(),
        'information_contributors': contributors, 'rejected_edges': rejected,
        'definition': '-logdet(Sigma_T)/15',
    }


def graph_connectivity(graph):
    node_ids = [int(row['state_id']) for row in graph['nodes']]
    parent = {node: node for node in node_ids}

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for edge in graph['edges']:
        left = find(int(edge['source_state_id']))
        right = find(int(edge['target_state_id']))
        if left != right:
            parent[right] = left
    components = len({find(node) for node in node_ids}) if node_ids else 0
    return {
        'nodes': len(node_ids), 'edges': len(graph['edges']),
        'connected_components': components,
        'cycle_rank': len(graph['edges']) - len(node_ids) + components,
    }


def _provenance_map(path):
    rows = edge_analytics.provenance_constraints(
        edge_analytics.load_provenance(path))
    return {int(row['creation_sequence']) - 1: row for row in rows}


def branch_metrics(block, arm, replay_row):
    replay = ROOT / replay_row['selected_replay']
    before = load_json(replay / 'graph_pre.json')
    final = load_json(replay / 'graph_final.json')
    before_nodes = nodes_from_graph(before)
    final_nodes = nodes_from_graph(final)
    before_edges = edges_from_graph(before, before_nodes)
    final_edges = edges_from_graph(final, final_nodes)
    target_ids = [int(value) for value in block['target_state_ids']]
    new_edges = classify_new_edges(
        before_edges, final_edges, target_ids, set(before_nodes))
    posterior = target_information(final_nodes, final_edges, target_ids)
    provenance = _provenance_map(replay / 'edge_provenance.jsonl')
    insertion = edge_analytics.insertion_time_metrics(
        final_edges, final_nodes,
        [(edge['start'], edge['end']) for edge in new_edges])
    constraints = []
    for edge in new_edges:
        record = provenance.get(edge['index'], {})
        covariance = np.asarray(edge['covariance_3x3'], dtype=float)
        try:
            information_eigenvalues = np.linalg.eigvalsh(
                np.linalg.inv(covariance)).tolist()
        except np.linalg.LinAlgError:
            information_eigenvalues = None
        pair = tuple(sorted((edge['start'], edge['end'])))
        metric = insertion[pair]
        constraints.append({
            'block_id': block['block_id'], 'target': block['target_label'],
            'arm': arm, 'edge_index': edge['index'],
            'source_state_id': edge['start'], 'target_state_id': edge['end'],
            'attribution': edge['attribution'],
            'constraint_family': constraint_family(record),
            'explicit_try_close_loop': is_explicit_try_close_loop(record),
            'creation_provenance': record.get('creation_provenance'),
            'creation_stage': record.get('creation_stage'),
            'matcher_type': record.get('matcher_type'),
            'match_response': record.get('match_response'),
            'match_threshold': record.get('match_threshold'),
            'measurement_dx': edge['measurement']['dx'],
            'measurement_dy': edge['measurement']['dy'],
            'measurement_dtheta': edge['measurement']['dtheta'],
            'covariance_eigenvalues': json.dumps(
                np.linalg.eigvalsh(covariance).tolist()),
            'information_eigenvalues': json.dumps(information_eigenvalues),
            'constraint_d_opt': se2_information.constraint_d_opt(covariance),
            'geodesic_at_insertion_m': metric['geodesic_m'],
            'hops_at_insertion': metric['hops'],
            'cycle_size_edges': (metric['hops'] + 1
                                 if metric['hops'] is not None else None),
        })
    counts = Counter(row['attribution'] for row in constraints)
    families = Counter(row['constraint_family'] for row in constraints)
    row = {
        'block_id': block['block_id'], 'target': block['target_label'],
        'seed': block['seed'], 'arm': arm,
        'J_T': posterior['J_T'], 'target_trace': posterior['trace'],
        'target_logdet': posterior['logdet'],
        'accepted_keyscans': len(final_nodes) - len(before_nodes),
        'total_new_factors': len(new_edges),
        'E_T': counts[TARGET_LABEL], 'E_N': counts[NONTARGET_LABEL],
        'local_factors': counts[LOCAL_LABEL],
        'PREVIOUS_SCAN': families['PREVIOUS_SCAN'],
        'RUNNING_SCAN_CHAIN': families['RUNNING_SCAN_CHAIN'],
        'NEAR_CHAIN': families['NEAR_CHAIN'],
        'TRY_CLOSE_LOOP': families['TRY_CLOSE_LOOP'],
        'UNKNOWN_FAMILY': families['UNKNOWN'],
        **{'pre_' + key: value for key, value in
           graph_connectivity(before).items()},
    }
    detail = {
        'target_ids': target_ids, 'target_posterior': posterior,
        'pre_graph': graph_connectivity(before),
        'new_edge_count': len(new_edges),
    }
    return row, detail, constraints, before_nodes, final_nodes


def target_stratified_bootstrap(rows):
    by_target = {target: [float(row['D_sweep']) for row in rows
                          if row['target'] == target]
                 for target in TARGETS}
    if any(len(by_target[target]) != 4 for target in TARGETS):
        return None
    rng = random.Random(BOOTSTRAP_SEED)
    values = []
    for _ in range(BOOTSTRAP_REPETITIONS):
        sample = []
        for target in TARGETS:
            sample.extend(rng.choice(by_target[target]) for _ in range(4))
        values.append(float(np.mean(sample)))
    return [float(np.percentile(values, 2.5)),
            float(np.percentile(values, 97.5))]


def support_decision(rows, complete, bootstrap_ci):
    values = [float(row['D_sweep']) for row in rows]
    positives = sum(value > 0.0 for value in values)
    by_target = {target: sum(float(row['D_sweep']) > 0.0 for row in rows
                             if row['target'] == target)
                 for target in TARGETS}
    mean = float(np.mean(values)) if values else None
    checks = {
        'complete_8_of_8': bool(complete and len(rows) == 8),
        'overall_positive_at_least_6': positives >= 6,
        'target_A_positive_at_least_3': by_target['target_A'] >= 3,
        'target_B_positive_at_least_3': by_target['target_B'] >= 3,
        'mean_D_sweep_gt_1e-4': mean is not None and mean > J_T_NONTRIVIAL_FLOOR,
        'bootstrap_CI_lower_gt_0': bool(bootstrap_ci and bootstrap_ci[0] > 0.0),
    }
    supported = all(checks.values())
    if not checks['complete_8_of_8']:
        gate = 'V14_PROSPECTIVE_TECHNICALLY_INCOMPLETE'
    elif supported:
        gate = 'V14_PROSPECTIVE_SUPPORT'
    else:
        gate = 'V14_PROSPECTIVE_NO_SUPPORT'
    recommendation = {
        'V14_PROSPECTIVE_SUPPORT': 'PROCEED_TO_REALIZATION_MODELING_DESIGN',
        'V14_PROSPECTIVE_NO_SUPPORT':
            'STOP_CURRENT_CONFIRMATORY_INTERVENTION_AND_ANALYZE_HETEROGENEITY',
        'V14_PROSPECTIVE_TECHNICALLY_INCOMPLETE':
            'STOP_AND_DIAGNOSE_TECHNICAL_FAILURE',
    }[gate]
    return gate, recommendation, checks, positives, by_target, mean


def load_tum_2d(path):
    rows = []
    with open(path) as stream:
        for line in stream:
            if not line.strip():
                continue
            values = [float(value) for value in line.split()]
            timestamp, x, y = values[0], values[1], values[2]
            qz, qw = values[6], values[7]
            yaw = 2.0 * math.atan2(qz, qw)
            rows.append([timestamp, x, y, yaw])
    return rows


def gt_block_sanity(block, arm_nodes):
    attempt = source_attempt(block['target_label'], block['seed'])
    slam = load_tum_2d(attempt / 'trajectory_slam.txt')
    gt = load_tum_2d(attempt / 'trajectory_gt.txt')
    gt_by_stamp = {row[0]: row[1:] for row in gt}
    paired = [(row[1:], gt_by_stamp[row[0]]) for row in slam
              if row[0] in gt_by_stamp]
    if len(paired) != len(slam) or len(paired) < 2:
        raise RuntimeError('strict pre-treatment SLAM/GT timestamp pairing failed')
    gauge = freeze_world_gauge([row[0] for row in paired],
                               [row[1] for row in paired])
    target_gt = [gt_by_stamp[slam[state_id][0]]
                 for state_id in block['target_state_ids']]
    output = {'gauge': gauge, 'target_gt_poses': target_gt, 'arms': {}}
    before_signatures = []
    for arm in ARMS:
        before_nodes, final_nodes = arm_nodes[arm]
        before_poses = [[before_nodes[state]['x'], before_nodes[state]['y'],
                         before_nodes[state]['theta']]
                        for state in block['target_state_ids']]
        final_poses = [[final_nodes[state]['x'], final_nodes[state]['y'],
                        final_nodes[state]['theta']]
                       for state in block['target_state_ids']]
        before_signatures.append(before_poses)
        output['arms'][arm] = estimator_effect_sanity(
            before_poses, final_poses, target_gt, gauge)
    if any(signature != before_signatures[0]
           for signature in before_signatures[1:]):
        raise RuntimeError('shared pre-treatment target estimate differs by arm')
    a2, a3 = output['arms']['A2_SWEEP90'], output['arms']['A3_MIN_TRIGGER']
    output['GT_sweep_translation'] = (
        a2['delta_translation_rmse_m'] - a3['delta_translation_rmse_m'])
    output['GT_sweep_heading_MAE'] = (
        a2['delta_heading_mae_rad'] - a3['delta_heading_mae_rad'])
    output['GT_sweep_heading_RMSE'] = (
        a2['delta_heading_rmse_rad'] - a3['delta_heading_rmse_rad'])
    return output


def render_report(path, final, primary_rows, gt_status, mechanism):
    lines = [
        '# V14 Prospective Confirmatory Validation', '',
        'All statements below are labelled as FACT, MEASURED OBSERVATION, '
        'INFERENCE, or UNKNOWN.', '',
        '## A. Provenance', '',
        '- FACT: protocol `{}`; preregistration SHA `{}`.'.format(
            PROTOCOL_ID, final['preregistration_sha256']),
        '- FACT: frozen backend replay and physical locks were required before analysis.',
        '', '## B. 32 candidate qualification ledger', '',
        '- FACT: see `qualification/history_qualification_ledger.csv`.',
        '', '## C. Frozen 4A+4B histories', '',
        '- FACT: see `qualification/frozen_history_manifest.json`.',
        '', '## D. 24 physical branches and arm order', '',
        '- FACT: see `collection/physical_collection_ledger.csv` and the frozen arm-order manifest.',
        '', '## E. Replay technical ledger', '',
        '- FACT: see `collection/backend_replay_ledger.csv`.',
        '', '## F. Eight-block primary table', '',
        '- MEASURED OBSERVATION: see `analysis/primary_block_table.csv`.',
        '', '## G. Primary summary', '',
        '- MEASURED OBSERVATION: final gate `{}`.'.format(final['final_scientific_gate']),
        '- MEASURED OBSERVATION: mean D_sweep `{}`; 95% bootstrap CI `{}`.'.format(
            final['primary_summary']['mean_D_sweep'],
            final['primary_summary']['bootstrap_95pct_CI']),
        '', '## H. GT sanity', '',
        '- MEASURED OBSERVATION: `{}`; this does not enter the primary gate.'.format(
            gt_status),
        '', '## I. Mechanism', '',
        '- MEASURED OBSERVATION: exact TRY_CLOSE_LOOP count `{}`.'.format(
            mechanism['exact_TRY_CLOSE_LOOP_count']),
        '- FACT: phase attribution is `PHASE_ATTRIBUTION_NOT_IDENTIFIABLE`.',
        '', '## J. Final scientific gate', '',
        '- INFERENCE: `{}`.'.format(final['final_scientific_gate']),
        '', '## K. Next-step recommendation', '',
        '- INFERENCE: `{}`.'.format(final['next_step_recommendation']),
        '- UNKNOWN: no claim is made about another backend or planner integration.',
    ]
    path.write_text('\n'.join(lines) + '\n')


def analyze(root=RESULT_ROOT):
    prereg, physical, backend = analysis_preflight(root)
    out = RESULT_ROOT / 'analysis'
    out.mkdir(parents=True, exist_ok=True)
    replay_rows = {('{}:{}'.format(row['block_id'], row['arm'])): row
                   for row in backend['branches']}
    metrics, constraints, details = [], [], {}
    gt_rows, gt_details = [], {}
    complete = bool(physical.get('complete') and backend.get('complete'))
    for block in frozen_blocks():
        arm_nodes = {}
        for arm in ARMS:
            replay_row = replay_rows.get('{}:{}'.format(block['block_id'], arm))
            if not replay_row or replay_row.get('status') != 'REPLAYED':
                complete = False
                continue
            row, detail, constraint_rows, before_nodes, final_nodes = \
                branch_metrics(block, arm, replay_row)
            metrics.append(row)
            constraints.extend(constraint_rows)
            details['{}:{}'.format(block['block_id'], arm)] = detail
            arm_nodes[arm] = (before_nodes, final_nodes)
        if len(arm_nodes) == 3:
            try:
                gt = gt_block_sanity(block, arm_nodes)
                gt_details[block['block_id']] = gt
                gt_rows.append({
                    'block_id': block['block_id'],
                    'target': block['target_label'],
                    'GT_sweep_translation': gt['GT_sweep_translation'],
                    'GT_sweep_heading_MAE': gt['GT_sweep_heading_MAE'],
                    'GT_sweep_heading_RMSE': gt['GT_sweep_heading_RMSE'],
                })
            except Exception as exc:
                gt_details[block['block_id']] = {
                    'status': 'GT_SANITY_UNAVAILABLE',
                    'reason': '{}: {}'.format(type(exc).__name__, exc)}
    write_csv(out / 'branch_metrics.csv', metrics)
    write_csv(out / 'constraint_mechanism.csv', constraints)
    atomic_json(out / 'branch_details.json', details)

    grouped = defaultdict(dict)
    for row in metrics:
        grouped[row['block_id']][row['arm']] = row
    primary = []
    for block in frozen_blocks():
        arms = grouped.get(block['block_id'], {})
        if not all(arm in arms for arm in ARMS):
            continue
        a1 = arms['A1_DWELL']['J_T']
        a3 = arms['A3_MIN_TRIGGER']['J_T']
        a2 = arms['A2_SWEEP90']['J_T']
        primary.append({
            'block_id': block['block_id'], 'target': block['target_label'],
            'seed': block['seed'], 'J_A1': a1, 'J_A3': a3, 'J_A2': a2,
            'D_trigger': a3 - a1, 'D_sweep': a2 - a3,
            'D_total': a2 - a1,
        })
    write_csv(out / 'primary_block_table.csv', primary)
    bootstrap = target_stratified_bootstrap(primary)
    gate, recommendation, checks, positives, target_positive, mean = \
        support_decision(primary, complete, bootstrap)
    values = [row['D_sweep'] for row in primary]
    primary_summary = {
        'complete_blocks': len(primary), 'positive_count': positives,
        'target_positive_count': target_positive, 'mean_D_sweep': mean,
        'median_D_sweep': float(np.median(values)) if values else None,
        'bootstrap_95pct_CI': bootstrap, 'bootstrap_seed': BOOTSTRAP_SEED,
        'bootstrap_repetitions': BOOTSTRAP_REPETITIONS,
        'support_conditions': checks,
    }
    atomic_json(out / 'primary_summary.json', primary_summary)

    primary_by_block = {row['block_id']: row for row in primary}
    warnings = sum(
        primary_by_block[row['block_id']]['D_sweep'] > 0.0 and
        (row['GT_sweep_translation'] < 0.0 or
         row['GT_sweep_heading_RMSE'] < 0.0)
        for row in gt_rows if row['block_id'] in primary_by_block)
    if len(gt_rows) != 8:
        gt_status = 'GT_SANITY_UNAVAILABLE'
    elif warnings >= 4:
        gt_status = 'GT_SANITY_DIRECTIONAL_WARNING'
    else:
        gt_status = 'GT_SANITY_NO_DIRECTIONAL_WARNING'
    write_csv(out / 'gt_sanity.csv', gt_rows)
    atomic_json(out / 'gt_sanity_details.json', {
        'status': gt_status, 'directional_warning_blocks': warnings,
        'rule': prereg['gt_sanity_estimands']['directional_warning_rule'],
        'blocks': gt_details,
    })

    family_counts = Counter(row['constraint_family'] for row in constraints)
    mechanism = {
        'constraint_family_counts': dict(family_counts),
        'exact_TRY_CLOSE_LOOP_count': family_counts['TRY_CLOSE_LOOP'],
        'explicit_loop_label': ('NO_EXPLICIT_TRY_CLOSE_LOOP_OBSERVED'
                                if family_counts['TRY_CLOSE_LOOP'] == 0 else
                                'EXPLICIT_TRY_CLOSE_LOOP_OBSERVED'),
        'phase_attribution': 'PHASE_ATTRIBUTION_NOT_IDENTIFIABLE',
        'accepted_keyscans_by_arm': {
            arm: sum(row['accepted_keyscans'] for row in metrics
                     if row['arm'] == arm) for arm in ARMS},
        'E_T_by_arm': {arm: sum(row['E_T'] for row in metrics
                                if row['arm'] == arm) for arm in ARMS},
        'E_N_by_arm': {arm: sum(row['E_N'] for row in metrics
                                if row['arm'] == arm) for arm in ARMS},
        'local_factors_by_arm': {
            arm: sum(row['local_factors'] for row in metrics
                     if row['arm'] == arm) for arm in ARMS},
    }
    atomic_json(out / 'mechanism_summary.json', mechanism)

    final = {
        'status': 'ANALYZED', 'protocol_id': PROTOCOL_ID,
        'preregistration_sha256': sha256(PREREGISTRATION_PATH),
        'physical_lock_sha256': sha256(PHYSICAL_LOCK),
        'backend_lock_sha256': sha256(BACKEND_LOCK),
        'statistical_unit': 'canonical-history block',
        'complete_8_block_sample': complete and len(primary) == 8,
        'v13_or_posthoc_data_pooled': False,
        'primary_effect_name': 'BROAD_SWEEP_ACTION_PACKAGE_EFFECT',
        'primary_summary': primary_summary, 'gt_sanity_status': gt_status,
        'mechanism': mechanism,
        'final_scientific_gate': gate,
        'next_step_recommendation': recommendation,
        'automatic_next_experiment_started': False,
    }
    atomic_json(out / 'v14_confirmatory_summary.json', final)
    decision = RESULT_ROOT / 'decision'
    decision.mkdir(exist_ok=True)
    atomic_json(decision / 'final_gate.json', final)
    render_report(RESULT_ROOT / 'V14_FINAL_REPORT.md', final, primary,
                  gt_status, mechanism)
    print(json.dumps(final, indent=2, sort_keys=True))
    return final


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=RESULT_ROOT)
    args = parser.parse_args()
    analyze(args.root)


if __name__ == '__main__':
    main()
