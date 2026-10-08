#!/usr/bin/python3
"""Backend replay for CD technical amendment 1."""

import argparse
import json
import os
import signal
import subprocess
import time
from collections import Counter
from pathlib import Path

import cd_confirmatory_guard as guard
import cd_confirmatory_replay as base
import cd_confirmatory_amendment_protocol as protocol
from controlled_branch_suite import atomic_json


PHYSICAL_LOCK = protocol.RESULT_ROOT / \
    'collection/PHYSICAL_COLLECTION_LOCK.json'
BACKEND_LOCK = protocol.RESULT_ROOT / \
    'collection/BACKEND_REPLAY_LOCK.json'


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def verify_inputs():
    if not PHYSICAL_LOCK.is_file():
        raise RuntimeError('backend replay requires physical lock')
    physical = protocol.load_json(PHYSICAL_LOCK)
    if (not physical.get('complete') or
            physical.get('status') !=
            'PHYSICAL_COLLECTION_LOCKED_COMPLETE'):
        raise RuntimeError('physical collection is technically incomplete')
    if not physical.get('fresh_manipulation_gate', {}).get('passed'):
        raise RuntimeError('fresh manipulation/deconfounding gate failed')
    prereg = protocol.load_json(protocol.PREREGISTRATION_PATH)
    for relative, expected in prereg['code_hashes'].items():
        if protocol.sha256(protocol.ROOT / relative) != expected:
            raise RuntimeError(
                'frozen amendment code changed: {}'.format(relative))
    if not protocol.original_run_audit()['passed']:
        raise RuntimeError('original incomplete run changed after amendment')
    guard.assert_prelock_no_scientific_outputs(
        protocol.RESULT_ROOT / 'analysis',
        protocol.RESULT_ROOT / 'decision')
    return (physical, protocol.sha256(protocol.PREREGISTRATION_PATH),
            protocol.sha256(PHYSICAL_LOCK))


def configure_base():
    base.ARMS = protocol.ARMS
    base.BACKEND_LOCK = BACKEND_LOCK
    base.EXPECTED_MAPPER_BINARY_SHA256 = \
        protocol.EXPECTED_MAPPER_BINARY_SHA256
    base.EXPECTED_NORMALIZED_MAPPER_CONFIG_SHA256 = \
        protocol.EXPECTED_NORMALIZED_MAPPER_CONFIG_SHA256
    base.MAX_REPLAY_ATTEMPTS = protocol.MAX_REPLAY_ATTEMPTS
    base.N_SCANS = protocol.N_SCANS
    base.PHYSICAL_LOCK = PHYSICAL_LOCK
    base.PREREGISTRATION_PATH = protocol.PREREGISTRATION_PATH
    base.PROTOCOL_ID = protocol.PROTOCOL_ID
    base.RESULT_ROOT = protocol.RESULT_ROOT
    base.ROOT = protocol.ROOT
    base.frozen_blocks = protocol.frozen_blocks
    base.load_json = protocol.load_json
    base.prefix_reference_record = protocol.prefix_reference_record
    base.sha256 = protocol.sha256
    base.source_attempt = protocol.source_attempt
    base.verify_inputs = verify_inputs
    base.configure_legacy()


def live_worker():
    path = protocol.RESULT_ROOT / 'collection/backend_replay_state.json'
    if not path.exists():
        return None
    state = protocol.load_json(path)
    pid = state.get('worker_pid')
    cmdline = Path('/proc') / str(pid) / 'cmdline' if pid else None
    if not cmdline or not cmdline.exists():
        return None
    command = cmdline.read_bytes().replace(
        b'\0', b' ').decode(errors='replace')
    if ('cd_confirmatory_amendment_replay.py' in command or
            'cd_confirmatory_amendment_pipeline.py' in command):
        return int(pid), int(state['worker_pgid'])
    return None


def status():
    path = protocol.RESULT_ROOT / 'collection/backend_replay_state.json'
    state = protocol.load_json(path) if path.exists() else {
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
    configure_base()
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('run', 'start', 'status', 'stop'))
    args = parser.parse_args()
    if args.command == 'run':
        print(json.dumps(base.legacy.run(), indent=2, sort_keys=True))
    elif args.command == 'start':
        if BACKEND_LOCK.exists():
            raise SystemExit('backend replay already locked')
        if live_worker():
            raise SystemExit('amendment backend worker already live')
        verify_inputs()
        log_path = protocol.RESULT_ROOT / 'collection/backend_replay.log'
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = open(log_path, 'a', buffering=1)
        command = ['/usr/bin/python3', str(Path(__file__).resolve()), 'run']
        process = subprocess.Popen(
            command, cwd=str(protocol.ROOT), stdout=log,
            stderr=subprocess.STDOUT, text=True, start_new_session=True)
        atomic_json(
            protocol.RESULT_ROOT / 'collection/backend_replay_launcher.json', {
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
            raise SystemExit('no verified amendment backend worker')
        os.killpg(worker[1], signal.SIGINT)
        print('sent SIGINT to amendment backend worker')


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(
        KeyboardInterrupt()))
    main()
