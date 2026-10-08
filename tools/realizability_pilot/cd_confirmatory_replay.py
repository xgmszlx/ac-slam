#!/usr/bin/python3
"""Post-physical-lock backend replay for the CD experiment."""

import argparse
import json
import os
import signal
import subprocess
import time
from collections import Counter
from pathlib import Path

import v14_confirmatory_replay as legacy
from cd_confirmatory_guard import assert_prelock_no_scientific_outputs
from cd_confirmatory_protocol import (
    ARMS, EXPECTED_MAPPER_BINARY_SHA256,
    EXPECTED_NORMALIZED_MAPPER_CONFIG_SHA256, MAX_REPLAY_ATTEMPTS, N_SCANS,
    PREREGISTRATION_PATH, PROTOCOL_ID, RESULT_ROOT, ROOT, frozen_blocks,
    load_json, prefix_reference_record, sha256, source_attempt,
)
from controlled_branch_suite import atomic_json


PHYSICAL_LOCK = RESULT_ROOT / 'collection/PHYSICAL_COLLECTION_LOCK.json'
BACKEND_LOCK = RESULT_ROOT / 'collection/BACKEND_REPLAY_LOCK.json'


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def verify_inputs():
    if not PHYSICAL_LOCK.is_file():
        raise RuntimeError('backend replay requires PHYSICAL_COLLECTION_LOCK')
    physical = load_json(PHYSICAL_LOCK)
    if (not physical.get('complete') or
            physical.get('status') != 'PHYSICAL_COLLECTION_LOCKED_COMPLETE'):
        raise RuntimeError('physical collection is technically incomplete')
    if not physical.get('fresh_manipulation_gate', {}).get('passed'):
        raise RuntimeError('fresh manipulation/deconfounding gate failed')
    if not PREREGISTRATION_PATH.is_file():
        raise RuntimeError('CD preregistration missing')
    prereg = load_json(PREREGISTRATION_PATH)
    for relative, expected in prereg['code_hashes'].items():
        if sha256(ROOT / relative) != expected:
            raise RuntimeError('frozen CD code changed: {}'.format(relative))
    assert_prelock_no_scientific_outputs()
    return physical, sha256(PREREGISTRATION_PATH), sha256(PHYSICAL_LOCK)


def create_lock(state, prereg_hash, physical_hash):
    rows = legacy.write_ledger(state)
    complete = (len(rows) == 48 and all(
        row['status'] == 'REPLAYED' for row in rows))
    payload = {
        'protocol_id': PROTOCOL_ID,
        'status': ('BACKEND_REPLAY_LOCKED_COMPLETE' if complete else
                   'BACKEND_REPLAY_LOCKED_TECHNICALLY_INCOMPLETE'),
        'complete': complete,
        'planned_branches': 48,
        'replayed_branches': sum(row['status'] == 'REPLAYED' for row in rows),
        'preregistration_sha256': prereg_hash,
        'physical_collection_lock_sha256': physical_hash,
        'branches': rows,
        'scientific_contrasts_computed': False,
        'analysis_authorized_after_this_lock': complete,
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
    legacy.save_state(state)
    return payload


def configure_legacy():
    legacy.ARMS = ARMS
    legacy.BACKEND_LOCK = BACKEND_LOCK
    legacy.EXPECTED_MAPPER_BINARY_SHA256 = EXPECTED_MAPPER_BINARY_SHA256
    legacy.EXPECTED_NORMALIZED_MAPPER_CONFIG_SHA256 = \
        EXPECTED_NORMALIZED_MAPPER_CONFIG_SHA256
    legacy.MAX_REPLAY_ATTEMPTS = MAX_REPLAY_ATTEMPTS
    legacy.N_SCANS = N_SCANS
    legacy.PHYSICAL_LOCK = PHYSICAL_LOCK
    legacy.PREREGISTRATION_PATH = PREREGISTRATION_PATH
    legacy.PROTOCOL_ID = PROTOCOL_ID
    legacy.RESULT_ROOT = RESULT_ROOT
    legacy.ROOT = ROOT
    legacy.frozen_blocks = frozen_blocks
    legacy.load_json = load_json
    legacy.prefix_reference_record = prefix_reference_record
    legacy.sha256 = sha256
    legacy.source_attempt = source_attempt
    legacy.verify_inputs = verify_inputs
    legacy.create_lock = create_lock


def validate_replay(attempt, result, reference):
    configure_legacy()
    return legacy.validate_replay(attempt, result, reference)


def live_worker():
    path = RESULT_ROOT / 'collection/backend_replay_state.json'
    if not path.exists():
        return None
    state = load_json(path)
    pid = state.get('worker_pid')
    cmdline = Path('/proc') / str(pid) / 'cmdline' if pid else None
    if not cmdline or not cmdline.exists():
        return None
    command = cmdline.read_bytes().replace(b'\0', b' ').decode(errors='replace')
    return ((int(pid), int(state['worker_pgid']))
            if 'cd_confirmatory_replay.py' in command else None)


def status():
    path = RESULT_ROOT / 'collection/backend_replay_state.json'
    state = load_json(path) if path.exists() else {
        'status': 'NOT_STARTED', 'branches': {}}
    return {
        'status': state['status'],
        'live_worker': bool(live_worker()),
        'branch_statuses': dict(Counter(
            row['status'] for row in state.get('branches', {}).values())),
        'backend_lock_exists': BACKEND_LOCK.exists(),
        'updated_utc': state.get('updated_utc'),
    }


def main():
    configure_legacy()
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('run', 'start', 'status', 'stop'))
    args = parser.parse_args()
    if args.command == 'run':
        print(json.dumps(legacy.run(), indent=2, sort_keys=True))
    elif args.command == 'start':
        if BACKEND_LOCK.exists():
            raise SystemExit('backend replay already locked')
        if live_worker():
            raise SystemExit('CD backend replay worker already live')
        verify_inputs()
        log_path = RESULT_ROOT / 'collection/backend_replay.log'
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = open(log_path, 'a', buffering=1)
        command = ['/usr/bin/python3', str(Path(__file__).resolve()), 'run']
        process = subprocess.Popen(
            command, cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT,
            text=True, start_new_session=True)
        atomic_json(RESULT_ROOT / 'collection/backend_replay_launcher.json', {
            'pid': process.pid,
            'pgid': process.pid,
            'command': command,
            'started_utc': now(),
        })
        print(json.dumps({'status': 'STARTED', 'pid': process.pid}, indent=2))
    elif args.command == 'status':
        print(json.dumps(status(), indent=2, sort_keys=True))
    else:
        worker = live_worker()
        if not worker:
            raise SystemExit('no verified CD replay worker')
        os.killpg(worker[1], signal.SIGINT)
        print('sent SIGINT to CD replay worker')


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(
        KeyboardInterrupt()))
    main()
