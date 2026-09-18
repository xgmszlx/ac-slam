#!/usr/bin/python3
"""Frozen post-lock scientific analysis for the fresh v12b experiment.

This module must be hashed into the v12b preregistration before collection.
It intentionally reuses the already-audited v12 graph extraction routine, but
defines the v12b block-level support, heterogeneity, replication, and mechanism
gates here so that no v12 observations enter the v12b statistical sample.
"""

import argparse
import itertools
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from common_prefix_analysis import (
    TARGET_LABEL, edges_from_graph, nodes_from_graph, paper_graph_utilities,
)
from confirmatory_v12_analysis import (
    atomic_json, branch_data, load_json, sign_test_one_sided, write_csv,
)
from confirmatory_v12b_protocol import (
    ARMS, BOOTSTRAP_SEED, J_T_NONTRIVIAL_FLOOR, PROTOCOL_ID, RESULT_ROOT,
    sha256,
)


TARGETS = ('target_A', 'target_B')
BOOTSTRAP_REPETITIONS = 10000
V12_TARGET_A_REFERENCE = {
    'D_view': {'positive': 4, 'total': 4, 'mean': 0.07086829572408293},
    'D_trigger': {'positive': 3, 'total': 4, 'mean': 0.05766937777245884},
    'D_total': {'positive': 4, 'total': 4, 'mean': 0.12853767349654177},
}


def analysis_preflight(root):
    """Fail closed unless collection and the preregistered code are sealed."""
    root = Path(root).resolve()
    lock_path = root / 'COLLECTION_LOCKED.json'
    if not lock_path.exists():
        raise RuntimeError('analysis locked until COLLECTION_LOCKED')
    lock = load_json(lock_path)
    state = load_json(root / 'collection_state.json')
    prereg_path = root / 'preregistration/v12b_confirmatory_preregistration.json'
    prereg = load_json(prereg_path)
    protocol_hash = sha256(prereg_path)
    if lock.get('status') != 'COLLECTION_LOCKED':
        raise RuntimeError('invalid collection lock status')
    if state.get('status') != 'COLLECTION_COMPLETE':
        raise RuntimeError('collection state is not complete')
    if not (protocol_hash == state.get('protocol_hash') ==
            lock.get('protocol_hash')):
        raise RuntimeError('v12b preregistration hash mismatch')
    if prereg.get('protocol_id') != PROTOCOL_ID:
        raise RuntimeError('unexpected protocol id')
    relative = 'tools/realizability_pilot/confirmatory_v12b_analysis.py'
    expected = prereg.get('code_hashes', {}).get(relative)
    if not expected or expected != sha256(Path(__file__)):
        raise RuntimeError('analysis code hash differs from preregistration')
    return state, prereg, lock


def exact_sign_flip_p(values):
    """One-sided exact paired sign-flip statistic for the mean."""
    values = [float(value) for value in values]
    if not values:
        return None
    observed = float(np.mean(values))
    distribution = [
        float(np.mean([sign * value for sign, value in zip(signs, values)]))
        for signs in itertools.product((-1.0, 1.0), repeat=len(values))
    ]
    tolerance = 1e-15
    return sum(value >= observed - tolerance for value in distribution) / float(
        len(distribution))


def contrast_summary(rows, left, right, name,
                     bootstrap_repetitions=BOOTSTRAP_REPETITIONS):
    by_block = defaultdict(dict)
    for row in rows:
        by_block[row['block_id']][row['arm']] = row
    paired = []
    for block_id, arms in sorted(by_block.items()):
        if left not in arms or right not in arms:
            continue
        paired.append({
            'block_id': block_id,
            'target': arms[left]['target'],
            'contrast': name,
            'left_arm': left,
            'right_arm': right,
            'difference': float(arms[left]['J_T'] - arms[right]['J_T']),
        })
    values = [row['difference'] for row in paired]
    by_target = {
        target: [row['difference'] for row in paired
                 if row['target'] == target]
        for target in TARGETS
    }
    positive = sum(value > 0.0 for value in values)
    target_positive = {
        target: sum(value > 0.0 for value in target_values)
        for target, target_values in by_target.items()
    }
    evaluable = (len(values) == 8 and
                 all(len(by_target[target]) == 4 for target in TARGETS))
    rng = random.Random(BOOTSTRAP_SEED)
    bootstrap = []
    if all(by_target.values()):
        for _ in range(int(bootstrap_repetitions)):
            sample = []
            for target in TARGETS:
                sample.extend(rng.choice(by_target[target])
                              for _ in range(len(by_target[target])))
            bootstrap.append(float(np.mean(sample)))
    interval = ([float(np.percentile(bootstrap, 2.5)),
                 float(np.percentile(bootstrap, 97.5))]
                if bootstrap else None)
    mean = float(np.mean(values)) if values else None
    supported = bool(
        evaluable and positive >= 6 and
        all(target_positive[target] >= 3 for target in TARGETS) and
        mean is not None and mean > J_T_NONTRIVIAL_FLOOR and
        interval is not None and interval[0] > 0.0)
    target_means = {
        target: (float(np.mean(target_values)) if target_values else None)
        for target, target_values in by_target.items()
    }
    heterogeneous = bool(
        evaluable and (
            ((target_positive['target_A'] >= 3 and
              target_positive['target_B'] <= 2) or
             (target_positive['target_B'] >= 3 and
              target_positive['target_A'] <= 2)) or
            (target_means['target_A'] * target_means['target_B'] < 0.0)))
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
            for target, target_values in by_target.items()
        },
        'one_sided_exact_sign_test_p': (
            sign_test_one_sided(positive, len(values)) if values else None),
        'one_sided_exact_sign_flip_mean_p': exact_sign_flip_p(values),
        'target_stratified_block_bootstrap_mean_95pct_CI': interval,
        'numerical_repeatability_floor': J_T_NONTRIVIAL_FLOOR,
        'confirmatory_evaluable': evaluable,
        'target_dependent_heterogeneity': heterogeneous,
        'supported_by_preregistered_rule': supported,
        'confirmatory_verdict': (
            'SUPPORTED' if supported else
            'NOT_SUPPORTED' if evaluable else
            'NOT_EVALUABLE_TECHNICAL_INCOMPLETENESS'),
    }


def block_dir(root, state_block):
    return (Path(root) / state_block['target_label'] /
            state_block['block_id'].split('_')[-1])


def mechanism_supplement(root, state_block, arm, detail):
    replay = block_dir(root, state_block) / arm / 'replay'
    final_graph = load_json(replay / 'graph_final.json')
    nodes = nodes_from_graph(final_graph)
    edges = edges_from_graph(final_graph, nodes)
    utilities = paper_graph_utilities(nodes, edges, detail['new_edges'])
    target_pairs = sorted({
        tuple(sorted((int(edge['start']), int(edge['end']))))
        for edge in detail['new_edges']
        if edge['attribution'] == TARGET_LABEL
    })
    return {
        'target_edge_pairs': target_pairs,
        'target_removed_disconnects_graph':
            utilities['target_removed_disconnects_graph'],
        'history_removed_disconnects_graph':
            utilities['history_removed_disconnects_graph'],
        'delta_U_T_interpretable':
            not utilities['target_removed_disconnects_graph'],
    }


def mechanism_summary(metrics, constraints, details):
    by_block = defaultdict(dict)
    identity_rows = []
    for key, detail in sorted(details.items()):
        block_id, arm = key.split(':', 1)
        pairs = [tuple(pair) for pair in detail['mechanism'][
            'target_edge_pairs']]
        by_block[block_id][arm] = set(pairs)
        identity_rows.append({
            'block_id': block_id,
            'arm': arm,
            'target_edge_count': len(pairs),
            'target_edge_pairs': json.dumps(pairs, separators=(',', ':')),
        })
    swap_blocks = {}
    for block_id, arms in sorted(by_block.items()):
        complete = all(arm in arms for arm in ARMS)
        exact = complete and all(arms[arm] == arms[ARMS[0]]
                                 for arm in ARMS[1:])
        swap_blocks[block_id] = {
            'all_arms_present': complete,
            'exact_target_edge_sets_equal': exact,
            'target_edge_counts': {arm: len(arms.get(arm, set()))
                                   for arm in ARMS},
            'shared_target_edge_pairs': sorted(
                set.intersection(*(arms[arm] for arm in ARMS)))
                if complete else [],
        }
    swap_identifiable = bool(swap_blocks) and all(
        row['exact_target_edge_sets_equal'] for row in swap_blocks.values())
    provenance = {
        arm: dict(Counter(
            row.get('creation_provenance') or 'UNKNOWN'
            for row in constraints if row['arm'] == arm))
        for arm in ARMS
    }
    matcher = {
        arm: dict(Counter(
            row.get('matcher_type') or 'UNKNOWN'
            for row in constraints if row['arm'] == arm))
        for arm in ARMS
    }
    history_disconnected = [
        bool(detail['mechanism']['history_removed_disconnects_graph'])
        for detail in details.values()
    ]
    target_disconnected = [
        bool(detail['mechanism']['target_removed_disconnects_graph'])
        for detail in details.values()
    ]
    return identity_rows, {
        'constraint_counts_by_arm': {
            arm: {
                'all_new': sum(row['arm'] == arm for row in constraints),
                'E_T': sum(row['arm'] == arm and
                           row['attribution'] == TARGET_LABEL
                           for row in constraints),
            } for arm in ARMS
        },
        'creation_provenance_by_arm': provenance,
        'matcher_type_by_arm': matcher,
        'target_edge_identity_by_block': swap_blocks,
        'covariance_swap': {
            'identifiable': swap_identifiable,
            'verdict': ('IDENTIFIABLE' if swap_identifiable else
                        'COUNTERFACTUAL_SWAP_NOT_IDENTIFIABLE'),
        },
        'history_removal': {
            'disconnected_branches': sum(history_disconnected),
            'analyzed_branches': len(history_disconnected),
            'verdict': ('HISTORY_CONNECTIVITY_CRITICAL'
                        if any(history_disconnected) else
                        'NUMERICALLY_EVALUABLE'),
        },
        'target_removal': {
            'disconnected_branches': sum(target_disconnected),
            'delta_U_T_interpretable_branches':
                len(target_disconnected) - sum(target_disconnected),
        },
        'arm_means': {
            arm: {
                field: float(np.mean([row[field] for row in metrics
                                      if row['arm'] == arm]))
                for field in ('accepted_keyscan_count',
                              'heading_triggered_keyscan_count',
                              'new_edge_count', 'E_T_count', 'E_N_count',
                              'local_edge_count', 'delta_U_T')
            } for arm in ARMS if any(row['arm'] == arm for row in metrics)
        },
    }


def replication_check(summaries):
    fresh = {}
    for name, reference in V12_TARGET_A_REFERENCE.items():
        summary = summaries[name]
        values = [row for row in summary['values']]
        # Paired rows are deterministically ordered target_A then target_B.
        target_a = values[:4]
        fresh[name] = {
            'v12_descriptive_reference': reference,
            'v12b_fresh_target_A_values': target_a,
            'v12b_positive': sum(value > 0.0 for value in target_a),
            'v12b_mean': float(np.mean(target_a)) if target_a else None,
            'pooled': False,
        }
    complete_reverse = (len(fresh['D_view']['v12b_fresh_target_A_values']) == 4
                        and all(value < 0.0 for value in
                                fresh['D_view']['v12b_fresh_target_A_values']))
    return {
        'role': 'DESCRIPTIVE_PRIOR_EVIDENCE_NOT_POOLED',
        'contrasts': fresh,
        'verdict': ('TARGET_A_REPLICATION_FAILURE' if complete_reverse else
                    'NO_COMPLETE_DIRECTION_REVERSAL'),
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
            'planned_seed': block['planned_seed'],
            'active_seed': block['active_seed'],
            'status': block['status'],
            'budget_valid': budget.get('passed'),
            'budget_distance_range_m': observed.get('distance_range_m'),
            'budget_time_range_s': observed.get('time_range_s'),
            'budget_raw_scan_relative_range': observed.get(
                'raw_scan_relative_range'),
            'history_attempt_count': len(block.get('history_attempts', [])),
            'reserve_used': block['active_seed'] != block['planned_seed'],
            'prefix_hash': block.get('canonical_prefix_hash'),
            'A1_status': branches.get('A1_DWELL', {}).get('status'),
            'A3_status': branches.get('A3_MIN_TRIGGER', {}).get('status'),
            'A2_status': branches.get('A2_SWEEP90', {}).get('status'),
            'primary_analysis_eligible': block['status'] == 'COLLECTED',
        })
        if block['status'] != 'COLLECTED':
            continue
        for arm in ARMS:
            row, detail, constraint_rows = branch_data(root, block, arm)
            detail['mechanism'] = mechanism_supplement(root, block, arm, detail)
            row.update({
                'target_removed_disconnects_graph':
                    detail['mechanism']['target_removed_disconnects_graph'],
                'delta_U_T_interpretable':
                    detail['mechanism']['delta_U_T_interpretable'],
            })
            metrics.append(row)
            for constraint in constraint_rows:
                hops = constraint.get('hops_at_insertion')
                constraint['cycle_length_edges'] = (
                    int(hops) + 1 if hops is not None else None)
            constraints.extend(constraint_rows)
            details['{}:{}'.format(block['block_id'], arm)] = detail
    write_csv(out / 'block_ledger.csv', ledger)
    write_csv(out / 'branch_metrics.csv', metrics)
    write_csv(out / 'constraint_mechanism.csv', constraints)
    atomic_json(out / 'branch_details.json', details)

    definitions = (
        ('D_view', 'A2_SWEEP90', 'A3_MIN_TRIGGER'),
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

    identity_rows, mechanism = mechanism_summary(metrics, constraints, details)
    write_csv(out / 'target_edge_identity.csv', identity_rows)
    atomic_json(out / 'mechanism_summary.json', mechanism)
    replication = replication_check(summaries)
    atomic_json(out / 'v12_target_A_replication.json', replication)

    usable_ids = {row['block_id'] for row in metrics}
    usable_by_target = {
        target: len({row['block_id'] for row in metrics
                     if row['target'] == target})
        for target in TARGETS
    }
    complete = (len(usable_ids) == 8 and
                usable_by_target == {'target_A': 4, 'target_B': 4} and
                len(metrics) == 24)
    heterogeneous = any(summaries[name]['target_dependent_heterogeneity']
                        for name in ('D_view', 'D_trigger'))
    view = summaries['D_view']['supported_by_preregistered_rule']
    trigger = summaries['D_trigger']['supported_by_preregistered_rule']
    if not complete:
        classification = 'CONFIRMATORY_EXPERIMENT_TECHNICALLY_INCOMPLETE'
        gate = classification
    elif heterogeneous:
        classification = 'TARGET_DEPENDENT_HETEROGENEITY'
        gate = 'PAUSE_FOR_CONTEXT_CONDITIONED_REFRAMING'
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
    final = {
        'status': 'ANALYZED',
        'protocol_id': PROTOCOL_ID,
        'protocol_hash': lock['protocol_hash'],
        'analysis_scope': ('PREREGISTERED_FRESH_V12B_CONFIRMATORY'
                           if complete else
                           'TECHNICALLY_INCOMPLETE_DESCRIPTIVE_ONLY'),
        'confirmatory_complete': complete,
        'planned_blocks': 8,
        'usable_blocks': len(usable_ids),
        'usable_blocks_by_target': usable_by_target,
        'planned_branches': 24,
        'analyzed_branches': len(metrics),
        'contrasts': summaries,
        'target_heterogeneity': heterogeneous,
        'mechanism': mechanism,
        'v12_target_A_replication': replication,
        'classification': classification,
        'final_gate': gate,
        'technical_incompleteness_phase_r_recurrence': (
            not complete and prereg['phase_r_gate']['status'] ==
            'TARGET_B_TECHNICAL_READY'),
        'technical_exclusion_counts': dict(Counter(
            block['status'] for block in state['blocks'])),
        'statistical_unit': 'canonical-history block',
        'pseudo_replication_used': False,
        'v12_blocks_pooled': False,
        'language_boundary': ('executed action -> actual factor generation -> '
                              'realized factor set -> local Gaussian posterior'),
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
