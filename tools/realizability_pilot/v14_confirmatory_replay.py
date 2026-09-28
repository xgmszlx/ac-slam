#!/usr/bin/python3
"""Post-physical-lock v14 backend replay; no scientific contrasts."""

import argparse
import csv
import json
import os
import signal
import subprocess
import time
import traceback
from collections import Counter
from pathlib import Path

from controlled_branch_suite import atomic_json
from stitch_probe_stream import stitch
from v13_unified_replay import unified_replay
from v14_confirmatory_protocol import (
    ARMS, EXPECTED_MAPPER_BINARY_SHA256,
    EXPECTED_NORMALIZED_MAPPER_CONFIG_SHA256, MAX_REPLAY_ATTEMPTS, N_SCANS,
    PREREGISTRATION_PATH, PROTOCOL_ID, RESULT_ROOT, ROOT, frozen_blocks,
    load_json, prefix_reference_record, sha256, source_attempt,
)


PHYSICAL_LOCK = RESULT_ROOT / 'collection/PHYSICAL_COLLECTION_LOCK.json'
BACKEND_LOCK = RESULT_ROOT / 'collection/BACKEND_REPLAY_LOCK.json'


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def state_path():
    return RESULT_ROOT / 'collection/backend_replay_state.json'


def save_state(state):
    state['updated_utc'] = now()
    atomic_json(state_path(), state)


def verify_inputs():
    if not PHYSICAL_LOCK.is_file():
        raise RuntimeError('backend replay requires PHYSICAL_COLLECTION_LOCK')
    physical = load_json(PHYSICAL_LOCK)
    if (not physical.get('complete') or
            physical.get('status') != 'PHYSICAL_COLLECTION_LOCKED_COMPLETE'):
        raise RuntimeError('physical collection is technically incomplete')
    if not PREREGISTRATION_PATH.is_file():
        raise RuntimeError('v14 preregistration missing')
    prereg = load_json(PREREGISTRATION_PATH)
    for relative, expected in prereg['code_hashes'].items():
        if sha256(ROOT / relative) != expected:
            raise RuntimeError('frozen v14 code changed: {}'.format(relative))
    return physical, sha256(PREREGISTRATION_PATH), sha256(PHYSICAL_LOCK)


def branch_key(row):
    return '{}:{}'.format(row['block_id'], row['arm'])


def selected_replay(branch_dir):
    for attempt in sorted(branch_dir.glob('attempt_*')):
        result = attempt / 'technical_validation.json'
        if result.is_file() and load_json(result).get('valid'):
            return attempt, load_json(result)
    return None, None


def prepare_combined(row, block, reference, branch_dir):
    capture = ROOT / row['selected_attempt']
    science = capture / 'scientific_treatment_stream.jsonl'
    if sha256(science) != row['scientific_stream_sha256']:
        raise RuntimeError('locked scientific stream hash changed')
    if sum(1 for line in science.read_text().splitlines() if line.strip()) != N_SCANS:
        raise RuntimeError('locked scientific stream is not exact N')
    prefix = ROOT / reference['canonical_prefix_path']
    combined = branch_dir / 'combined_stream.jsonl'
    report_path = branch_dir / 'stitch_report.json'
    if not combined.exists():
        report = stitch(prefix, science, combined)
        atomic_json(report_path, report)
    else:
        report = load_json(report_path)
    if (not report['prefix_byte_identical'] or
            report['prefix_hash'] != reference['canonical_prefix_sha256'] or
            int(report['probe_record_count']) != N_SCANS):
        raise RuntimeError('combined stream violates locked prefix/suffix contract')
    return combined, report


def validate_replay(attempt, result, reference):
    required = ['graph_pre.json', 'graph_final.json',
                'unified_replay_result.json', 'edge_provenance.jsonl',
                'canonical_prefix.jsonl', 'probe_suffix.jsonl',
                'combined_stream.jsonl']
    missing = [name for name in required if not (attempt / name).is_file()]
    comparison = result.get('prefix_reference_comparison') or {}
    checks = {
        'status_complete': result.get('status') == 'REPLAY_COMPLETE',
        'prefix_gate_passed': result.get('prefix_gate_passed') is True,
        'prefix_structural_exact': comparison.get('structural', {}).get(
            'exact') is True,
        'prefix_numerical_exact': comparison.get('numerical', {}).get(
            'exact') is True,
        'suffix_exact_N': result.get('suffix_record_count') == N_SCANS,
        'suffix_published': result.get('suffix_published') is True,
        'processed_barrier_exact': result.get('processed_final_count') ==
            result.get('prefix_record_count', 0) + N_SCANS,
        'mapper_config_frozen': result.get('mapper_params_sha256') ==
            EXPECTED_NORMALIZED_MAPPER_CONFIG_SHA256,
        'mapper_binary_frozen': result.get('code_provenance', {}).get(
            'mapper_binary_sha256') == EXPECTED_MAPPER_BINARY_SHA256,
        'required_files_present': not missing,
        'reference_graph_hash_frozen': result.get('prefix_reference_sha256') ==
            reference['prefix_reference_graph_sha256'],
    }
    return {'valid': all(checks.values()), 'checks': checks,
            'missing_files': missing}


def replay_branch(state, row, block):
    directory = (RESULT_ROOT / 'collection/replays' / block['target_label'] /
                 block['block_id'] / row['arm'])
    directory.mkdir(parents=True, exist_ok=True)
    reference = prefix_reference_record(block)
    reference_path = directory.parent / 'prefix_reference.json'
    if reference_path.exists() and load_json(reference_path) != reference:
        raise RuntimeError('prefix reference changed')
    if not reference_path.exists():
        atomic_json(reference_path, reference)
    combined, stitch_report = prepare_combined(row, block, reference, directory)
    selected, validation = selected_replay(directory)
    attempts = []
    for old in sorted(directory.glob('attempt_*')):
        path = old / 'technical_validation.json'
        attempts.append(load_json(path) if path.exists() else {
            'valid': False, 'reason': 'missing technical validation'})
    while selected is None and len(attempts) < MAX_REPLAY_ATTEMPTS:
        number = len(attempts) + 1
        attempt = directory / 'attempt_{:02d}'.format(number)
        try:
            result = unified_replay(
                ROOT / reference['canonical_prefix_path'],
                source_attempt(block['target_label'], block['seed']) /
                'mapper_params.yaml', attempt, rate_hz=20.0,
                combined_path=combined,
                target_ids=reference['local_five_target_state_ids'],
                prefix_reference_path=ROOT /
                reference['prefix_reference_graph_path'])
            validation = validate_replay(attempt, result, reference)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            attempt.mkdir(parents=True, exist_ok=True)
            validation = {
                'valid': False,
                'technical_exception': '{}: {}'.format(type(exc).__name__, exc),
                'traceback': traceback.format_exc(),
            }
        validation.update({'attempt': number, 'replay_dir': str(
            attempt.relative_to(ROOT))})
        atomic_json(attempt / 'technical_validation.json', validation)
        attempts.append(validation)
        if validation.get('valid'):
            selected = attempt
        state['branches'][branch_key(row)] = {
            'status': ('REPLAYED' if selected else 'TECHNICAL_ATTEMPT_FAILED'),
            'attempt_count': len(attempts),
            'last_attempt': str(attempt.relative_to(ROOT)),
        }
        save_state(state)
    if selected is None:
        return {
            'status': 'TECHNICALLY_INVALID_REPLAY_FINAL',
            'attempt_count': len(attempts), 'selected_replay': None,
        }
    result = load_json(selected / 'unified_replay_result.json')
    return {
        'status': 'REPLAYED', 'attempt_count': len(attempts),
        'selected_replay': str(selected.relative_to(ROOT)),
        'prefix_reference_exact': True,
        'prefix_record_count': result['prefix_record_count'],
        'suffix_record_count': result['suffix_record_count'],
        'processed_final_count': result['processed_final_count'],
        'combined_stream_sha256': sha256(combined),
        'stitch_report_sha256': sha256(directory / 'stitch_report.json'),
        'graph_pre_sha256': sha256(selected / 'graph_pre.json'),
        'graph_final_sha256': sha256(selected / 'graph_final.json'),
        'provenance_sha256': sha256(selected / 'edge_provenance.jsonl'),
    }


def write_ledger(state):
    rows = []
    for key, row in sorted(state['branches'].items()):
        block_id, arm = key.split(':', 1)
        rows.append({'block_id': block_id, 'arm': arm, **row})
    path = RESULT_ROOT / 'collection/backend_replay_ledger.csv'
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with open(path, 'w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    atomic_json(path.with_suffix('.json'), rows)
    return rows


def create_lock(state, prereg_hash, physical_hash):
    rows = write_ledger(state)
    complete = (len(rows) == 24 and all(
        row['status'] == 'REPLAYED' for row in rows))
    payload = {
        'protocol_id': PROTOCOL_ID,
        'status': ('BACKEND_REPLAY_LOCKED_COMPLETE' if complete else
                   'BACKEND_REPLAY_LOCKED_TECHNICALLY_INCOMPLETE'),
        'complete': complete, 'planned_branches': 24,
        'replayed_branches': sum(row['status'] == 'REPLAYED' for row in rows),
        'preregistration_sha256': prereg_hash,
        'physical_collection_lock_sha256': physical_hash,
        'branches': rows, 'scientific_contrasts_computed': False,
        'analysis_authorized_after_this_lock': True,
        'locked_utc': now(),
    }
    if BACKEND_LOCK.exists() and load_json(BACKEND_LOCK) != payload:
        raise RuntimeError('backend replay already locked')
    if not BACKEND_LOCK.exists():
        atomic_json(BACKEND_LOCK, payload)
    state['status'] = payload['status']
    state['completed_utc'] = now()
    state.pop('worker_pid', None)
    state.pop('worker_pgid', None)
    save_state(state)
    return payload


def run():
    if BACKEND_LOCK.exists():
        return load_json(BACKEND_LOCK)
    physical, prereg_hash, physical_hash = verify_inputs()
    state = load_json(state_path()) if state_path().exists() else {
        'protocol_id': PROTOCOL_ID, 'status': 'PLANNED',
        'preregistration_sha256': prereg_hash,
        'physical_collection_lock_sha256': physical_hash,
        'branches': {}, 'scientific_contrasts_computed': False,
        'created_utc': now(),
    }
    if (state['preregistration_sha256'] != prereg_hash or
            state['physical_collection_lock_sha256'] != physical_hash):
        raise RuntimeError('frozen replay inputs changed')
    state.update(status='RUNNING', worker_pid=os.getpid(),
                 worker_pgid=os.getpgrp(), started_utc=state.get(
                     'started_utc', now()))
    save_state(state)
    block_map = {row['block_id']: row for row in frozen_blocks()}
    try:
        for row in physical['branches']:
            key = branch_key(row)
            if state['branches'].get(key, {}).get('status') == 'REPLAYED':
                continue
            result = replay_branch(state, row, block_map[row['block_id']])
            state['branches'][key] = result
            save_state(state)
        return create_lock(state, prereg_hash, physical_hash)
    except KeyboardInterrupt:
        state['status'] = 'INTERRUPTED'
        state['interrupted_utc'] = now()
        state.pop('worker_pid', None)
        state.pop('worker_pgid', None)
        save_state(state)
        return {'status': 'INTERRUPTED'}


def live_worker():
    if not state_path().exists():
        return None
    state = load_json(state_path())
    pid = state.get('worker_pid')
    if not pid or not (Path('/proc') / str(pid) / 'cmdline').exists():
        return None
    command = (Path('/proc') / str(pid) / 'cmdline').read_bytes().replace(
        b'\0', b' ').decode(errors='replace')
    return (int(pid), int(state['worker_pgid'])) \
        if 'v14_confirmatory_replay.py' in command else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('run', 'start', 'status', 'stop'))
    args = parser.parse_args()
    if args.command == 'run':
        print(json.dumps(run(), indent=2, sort_keys=True))
    elif args.command == 'start':
        if BACKEND_LOCK.exists():
            raise SystemExit('backend replay already locked')
        if live_worker():
            raise SystemExit('v14 backend replay worker already live')
        verify_inputs()
        log = open(RESULT_ROOT / 'collection/backend_replay.log', 'a', buffering=1)
        command = ['/usr/bin/python3', str(Path(__file__).resolve()), 'run']
        process = subprocess.Popen(command, cwd=str(ROOT), stdout=log,
                                   stderr=subprocess.STDOUT, text=True,
                                   start_new_session=True)
        atomic_json(RESULT_ROOT / 'collection/backend_replay_launcher.json', {
            'pid': process.pid, 'pgid': process.pid, 'command': command,
            'started_utc': now()})
        print(json.dumps({'status': 'STARTED', 'pid': process.pid}, indent=2))
    elif args.command == 'status':
        state = load_json(state_path()) if state_path().exists() else {
            'status': 'NOT_STARTED', 'branches': {}}
        print(json.dumps({
            'status': state['status'], 'live_worker': bool(live_worker()),
            'branch_statuses': dict(Counter(
                row['status'] for row in state.get('branches', {}).values())),
            'backend_lock_exists': BACKEND_LOCK.exists(),
            'updated_utc': state.get('updated_utc'),
        }, indent=2, sort_keys=True))
    else:
        worker = live_worker()
        if not worker:
            raise SystemExit('no verified v14 replay worker')
        os.killpg(worker[1], signal.SIGINT)
        print('sent SIGINT to v14 replay worker')


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(
        KeyboardInterrupt()))
    main()
