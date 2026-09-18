#!/usr/bin/python3
"""Close an incomplete v12b collection without reading scientific outcomes."""

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULT_ROOT = (
    ROOT / 'results/realizability_pilot/p1_confirmatory_v12b_20260918')
TERMINAL_STATUS = 'CONFIRMATORY_EXPERIMENT_TECHNICALLY_INCOMPLETE'


def load_json(path):
    return json.loads(Path(path).read_text())


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def write_csv(path, rows):
    rows = list(rows)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def closeout(root=DEFAULT_RESULT_ROOT):
    root = Path(root).resolve()
    if (root / 'COLLECTION_LOCKED.json').exists():
        raise RuntimeError('refusing technical closeout of a locked collection')
    state = load_json(root / 'collection_state.json')
    if state.get('status') != 'FAILED':
        raise RuntimeError('technical closeout requires FAILED collection state')
    prereg_path = root / 'preregistration/v12b_confirmatory_preregistration.json'
    prereg = load_json(prereg_path)
    phase_r = load_json(root / 'decision/phase_r_gate.json')
    amendment = load_json(
        root / 'preregistration/technical_amendment_01_pose_graph_dump_polling.json')

    ledger = []
    history_failures = Counter()
    reserve_use = defaultdict(list)
    for block in state['blocks']:
        for attempt in block.get('history_attempts', []):
            if attempt.get('status') != 'SUCCEEDED':
                reason = attempt.get('reason') or 'UNKNOWN'
                history_failures[reason] += 1
            if attempt.get('seed') in block.get('reserve_seeds', []):
                reserve_use[int(attempt['seed'])].append(block['block_id'])
        branches = block.get('branches', {})
        budget = block.get('budget_gate', {})
        observed = budget.get('observed', {})
        ledger.append({
            'block_id': block['block_id'],
            'target': block['target_label'],
            'planned_seed': block['planned_seed'],
            'active_seed': block['active_seed'],
            'status': block['status'],
            'history_attempts': len(block.get('history_attempts', [])),
            'reserve_used': block['active_seed'] != block['planned_seed'],
            'budget_passed': budget.get('passed'),
            'distance_range_m': observed.get('distance_range_m'),
            'duration_range_s': observed.get('time_range_s'),
            'raw_scan_relative_range': observed.get(
                'raw_scan_relative_range'),
            'A1_status': branches.get('A1_DWELL', {}).get('status'),
            'A3_status': branches.get('A3_MIN_TRIGGER', {}).get('status'),
            'A2_status': branches.get('A2_SWEEP90', {}).get('status'),
            'confirmatory_eligible': block['status'] == 'COLLECTED',
        })

    status_counts = Counter(row['status'] for row in ledger)
    usable_by_target = {
        target: sum(row['target'] == target and row['confirmatory_eligible']
                    for row in ledger)
        for target in ('target_A', 'target_B')
    }
    prefix_failures = []
    for block in state['blocks']:
        for arm, branch in block.get('branches', {}).items():
            if branch.get('status') == 'TECHNICAL_INVALID_PREFIX_FINAL':
                prefix_failures.append({
                    'block_id': block['block_id'],
                    'arm': arm,
                    'canonical_prefix_hash': block.get(
                        'canonical_prefix_hash'),
                    'attempts': branch.get('technical_replay_attempts', []),
                })
    reused_reserves = {
        str(seed): blocks for seed, blocks in reserve_use.items()
        if len(set(blocks)) > 1
    }
    payload = {
        'status': 'CLOSED',
        'final_gate': TERMINAL_STATUS,
        'protocol_id': state['protocol_id'],
        'collection_state': state['status'],
        'collection_failure_reason': state.get('reason'),
        'collection_complete_marker_present':
            (root / 'COLLECTION_COMPLETE.json').exists(),
        'collection_locked_marker_present':
            (root / 'COLLECTION_LOCKED.json').exists(),
        'preregistration_sha256': sha256(prereg_path),
        'phase_r_gate': phase_r['status'],
        'planned_blocks': 8,
        'usable_blocks': sum(row['confirmatory_eligible'] for row in ledger),
        'usable_blocks_by_target': usable_by_target,
        'block_status_counts': dict(status_counts),
        'history_failure_counts': dict(history_failures),
        'prefix_failures': prefix_failures,
        'reserve_seed_attempt_blocks': {
            str(seed): blocks for seed, blocks in sorted(reserve_use.items())},
        'reserve_reuse_anomaly': {
            'detected': bool(reused_reserves),
            'seeds': reused_reserves,
            'code_fact': (
                'The allocator tracks only each sibling current active_seed; '
                'a reserve attempted and then superseded can be selected again.'),
            'accepted_duplicate_history_entered_sample': False,
        },
        'phase_r_problem_recurred': True,
        'phase_r_recurrence': [
            'Target-B canonical-prefix identity failure',
            'Target-B physical target-reference matching failure',
        ],
        'scientific_analysis_executed': False,
        'scientific_conclusion': None,
        'no_peeking': {
            'fresh_formal_J_T_or_contrasts_read': False,
            'fresh_formal_graph_outcomes_read': False,
            'pre_amendment_excluded_incident':
                amendment['endpoint_access_incident'],
        },
        'v12_target_A_reference_role':
            prereg['v12_target_A_role'],
        'v12_or_pre_amendment_blocks_pooled': False,
        'interpretation': (
            'The repaired protocol was not technically robust enough to '
            'deliver four usable blocks per target. No confirmatory action '
            'effect is estimable under the preregistered gate.'),
    }
    output = root / 'technical_closeout'
    write_csv(output / 'block_ledger.csv', ledger)
    atomic_json(output / 'technical_closeout.json', payload)
    atomic_json(root / 'COLLECTION_TERMINATED_TECHNICALLY_INCOMPLETE.json', {
        'status': TERMINAL_STATUS,
        'technical_closeout': str(output / 'technical_closeout.json'),
        'preregistration_sha256': payload['preregistration_sha256'],
        'scientific_analysis_executed': False,
    })
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=DEFAULT_RESULT_ROOT)
    args = parser.parse_args()
    print(json.dumps(closeout(args.root), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
