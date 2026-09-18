#!/usr/bin/python3
"""Create descriptive mechanism closeout artifacts from frozen v12 outputs.

This is deliberately separate from ``confirmatory_v12_analysis.py``.  It does
not alter eligibility, endpoints, contrasts, or the final gate; it only makes
the already-open descriptive mechanism evidence easier to audit.
"""

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


DEFAULT_ROOT = Path(
    'results/realizability_pilot/p1_confirmatory_v12_20260917')
ARMS = ('A1_DWELL', 'A3_MIN_TRIGGER', 'A2_SWEEP90')
TARGET_EDGE_LABEL = 'E_T_target'


def load_json(path):
    return json.loads(Path(path).read_text())


def load_csv(path):
    with open(path, newline='') as stream:
        return list(csv.DictReader(stream))


def atomic_json(path, payload):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def write_csv(path, rows):
    rows = list(rows)
    with open(path, 'w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def mean(values):
    return sum(values) / len(values) if values else None


def summarize(root):
    root = Path(root).resolve()
    analysis = root / 'analysis'
    final = load_json(root / 'decision/final_gate.json')
    if final['final_gate'] != 'CONFIRMATORY_EXPERIMENT_TECHNICALLY_INCOMPLETE':
        raise RuntimeError('closeout is scoped to the technically incomplete v12 run')
    if final['analysis_scope'] != 'DESCRIPTIVE_ONLY_VALID_TARGET_A_BLOCKS':
        raise RuntimeError('unexpected v12 analysis scope')

    ledger = load_csv(analysis / 'block_ledger.csv')
    metrics = load_csv(analysis / 'branch_metrics.csv')
    constraints = load_csv(analysis / 'constraint_mechanism.csv')
    details = load_json(analysis / 'branch_details.json')

    means = {}
    numeric = (
        'J_T', 'target_trace', 'terminal_trace', 'accepted_keyscan_count',
        'heading_triggered_keyscan_count', 'distance_triggered_keyscan_count',
        'new_edge_count', 'E_T_count', 'E_N_count', 'local_edge_count',
        'delta_U_T', 'distance_m', 'duration_s', 'raw_scan_count',
        'yaw_excursion_rad', 'fov_union_deg')
    for arm in ARMS:
        arm_rows = [row for row in metrics if row['arm'] == arm]
        means[arm] = {
            field: mean([float(row[field]) for row in arm_rows])
            for field in numeric
        }

    mechanism = {}
    for arm in ARMS:
        arm_rows = [row for row in constraints if row['arm'] == arm]
        mechanism[arm] = {
            'edge_total': len(arm_rows),
            'attribution': dict(Counter(row['attribution'] for row in arm_rows)),
            'creation_provenance': dict(Counter(
                row['creation_provenance'] for row in arm_rows)),
            'creation_stage': dict(Counter(
                row['creation_stage'] for row in arm_rows)),
            'matcher_type': dict(Counter(row['matcher_type'] for row in arm_rows)),
        }

    identity_rows = []
    swap_by_block = {}
    by_block = defaultdict(dict)
    for key, detail in details.items():
        block_id, arm = key.split(':', 1)
        pairs = sorted(
            (int(edge['start']), int(edge['end']))
            for edge in detail['new_edges']
            if edge['attribution'] == TARGET_EDGE_LABEL)
        by_block[block_id][arm] = pairs
        identity_rows.append({
            'block_id': block_id,
            'arm': arm,
            'target_edge_count': len(pairs),
            'target_edge_pairs': json.dumps(pairs, separators=(',', ':')),
        })
    for block_id, arms in sorted(by_block.items()):
        sets = {arm: set(arms.get(arm, [])) for arm in ARMS}
        exact = all(sets[arm] == sets[ARMS[0]] for arm in ARMS[1:])
        shared = set.intersection(*(sets[arm] for arm in ARMS))
        swap_by_block[block_id] = {
            'exact_target_edge_sets_equal': exact,
            'shared_target_edge_pairs': sorted(shared),
            'target_edge_counts': {arm: len(sets[arm]) for arm in ARMS},
        }
    swap_identifiable = all(
        row['exact_target_edge_sets_equal'] for row in swap_by_block.values())

    target_matching = {}
    for target in ('target_A', 'target_B'):
        target_matching[target] = {}
        for history in ('H1', 'H2', 'H3', 'H4'):
            frozen = load_json(root / target / history / 'frozen_target.json')
            target_matching[target][history] = {
                'status': frozen['status'],
                'state_ids': frozen['historical_scan_ids'],
                'maximum_position_error_m': max(
                    row['position_error_m'] for row in frozen['matches']),
                'maximum_heading_error_rad': max(
                    row['heading_error_rad'] for row in frozen['matches']),
            }

    history_disconnects = all(
        row['history_removed_disconnects_graph'] == 'True' for row in metrics)
    budget_invalid = [row['block_id'] for row in ledger
                      if row['budget_valid'] == 'False']
    payload = {
        'artifact_role': 'POST_ANALYSIS_DESCRIPTIVE_CLOSEOUT',
        'changes_confirmatory_analysis': False,
        'analysis_scope': final['analysis_scope'],
        'final_gate': final['final_gate'],
        'usable_blocks': final['usable_blocks'],
        'usable_blocks_by_target': final['usable_blocks_by_target'],
        'budget_invalid_blocks': budget_invalid,
        'arm_means_valid_target_A_only': means,
        'constraint_mechanism_valid_target_A_only': mechanism,
        'target_reference_matching_all_final_histories': target_matching,
        'target_edge_identity_valid_target_A_only': swap_by_block,
        'covariance_swap': {
            'identifiable': swap_identifiable,
            'verdict': ('IDENTIFIABLE' if swap_identifiable else
                        'COUNTERFACTUAL_SWAP_NOT_IDENTIFIABLE'),
            'reason': ('Exact target-edge endpoint sets differ between arms; '
                       'a covariance exchange would also change factor '
                       'identity/topology.') if not swap_identifiable else None,
        },
        'history_removal': {
            'all_analyzed_branches_disconnected': history_disconnects,
            'reporting': ('HISTORY_CONNECTIVITY_CRITICAL'
                          if history_disconnects else 'NUMERICALLY_EVALUABLE'),
        },
    }
    atomic_json(analysis / 'descriptive_mechanism_closeout.json', payload)
    write_csv(analysis / 'target_edge_identity.csv', identity_rows)
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    print(json.dumps(summarize(args.root), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
