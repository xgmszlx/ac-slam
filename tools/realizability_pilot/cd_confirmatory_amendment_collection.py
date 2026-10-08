#!/usr/bin/python3
"""Physical collection for CD technical amendment 1."""

import argparse
import json
import os
import signal
import subprocess
import time
from collections import Counter
from pathlib import Path

import cd_confirmatory_collection as base
import cd_confirmatory_guard as guard
import cd_confirmatory_amendment_protocol as protocol
from controlled_branch_suite import atomic_json


LOCK_PATH = protocol.RESULT_ROOT / \
    'collection/PHYSICAL_COLLECTION_LOCK.json'


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def verify_preregistration():
    if not protocol.PREREGISTRATION_PATH.is_file():
        raise RuntimeError('amendment preregistration missing')
    prereg = protocol.load_json(protocol.PREREGISTRATION_PATH)
    for relative, expected in prereg['code_hashes'].items():
        if protocol.sha256(protocol.ROOT / relative) != expected:
            raise RuntimeError(
                'frozen amendment code changed: {}'.format(relative))
    audit = protocol.original_run_audit()
    if not audit['passed']:
        raise RuntimeError('original incomplete run changed after amendment')
    protocol.frozen_history_manifest()
    if protocol.canonical_sha(protocol.ARM_ORDERS) != \
            protocol.EXPECTED_ARM_ORDERS_SHA256:
        raise RuntimeError('frozen arm orders changed')
    guard.assert_prelock_no_scientific_outputs(
        protocol.RESULT_ROOT / 'analysis',
        protocol.RESULT_ROOT / 'decision')
    return prereg, protocol.sha256(protocol.PREREGISTRATION_PATH)


def freeze_arm_order():
    rows = protocol.arm_order_rows()
    validation = protocol.validate_per_target_arm_balance(rows)
    if not validation['passed']:
        raise RuntimeError(
            'frozen arm order is not balanced within Target strata')
    payload = protocol.arm_order_manifest_payload(now())
    path = protocol.ARM_ORDER_MANIFEST_PATH
    if path.exists():
        existing = protocol.load_json(path)
        stable_existing = dict(existing)
        stable_existing.pop('frozen_utc', None)
        stable_payload = dict(payload)
        stable_payload.pop('frozen_utc', None)
        if stable_existing != stable_payload:
            raise RuntimeError('refusing to modify frozen arm-order manifest')
        return existing
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(path, payload)
    return payload


def configure_base():
    base.ARM_ORDERS = protocol.ARM_ORDERS
    base.ARM_ORDER_MANIFEST_PATH = protocol.ARM_ORDER_MANIFEST_PATH
    base.ARMS = protocol.ARMS
    base.LOCK_PATH = LOCK_PATH
    base.MAX_CAPTURE_ATTEMPTS = protocol.MAX_CAPTURE_ATTEMPTS
    base.N_SCANS = protocol.N_SCANS
    base.PREREGISTRATION_PATH = protocol.PREREGISTRATION_PATH
    base.PROTOCOL_ID = protocol.PROTOCOL_ID
    base.RESULT_ROOT = protocol.RESULT_ROOT
    base.ROOT = protocol.ROOT
    base.TARGETS = protocol.TARGETS
    base.action_specs = protocol.action_specs
    base.frozen_blocks = protocol.frozen_blocks
    base.load_json = protocol.load_json
    base.sha256 = protocol.sha256
    base.verify_preregistration = verify_preregistration
    base.configure_legacy()
    base.legacy.freeze_arm_order = freeze_arm_order


def live_worker():
    path = protocol.RESULT_ROOT / \
        'collection/physical_collection_state.json'
    if not path.exists():
        return None
    state = protocol.load_json(path)
    pid = state.get('worker_pid')
    cmdline = Path('/proc') / str(pid) / 'cmdline' if pid else None
    if not cmdline or not cmdline.exists():
        return None
    command = cmdline.read_bytes().replace(
        b'\0', b' ').decode(errors='replace')
    if ('cd_confirmatory_amendment_collection.py' in command or
            'cd_confirmatory_amendment_pipeline.py' in command):
        return int(pid), int(state['worker_pgid'])
    return None


def status():
    path = protocol.RESULT_ROOT / \
        'collection/physical_collection_state.json'
    state = protocol.load_json(path) if path.exists() else {
        'status': 'NOT_STARTED', 'blocks': []}
    return {
        'status': state['status'],
        'live_worker': bool(live_worker()),
        'block_statuses': dict(Counter(
            row['status'] for row in state.get('blocks', []))),
        'physical_lock_exists': LOCK_PATH.exists(),
        'updated_utc': state.get('updated_utc'),
    }


def main():
    configure_base()
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('run', 'start', 'status', 'stop'))
    args = parser.parse_args()
    if args.command == 'run':
        print(json.dumps(base.legacy.collect(), indent=2, sort_keys=True))
    elif args.command == 'start':
        if LOCK_PATH.exists():
            raise SystemExit('physical collection already locked')
        if live_worker():
            raise SystemExit('amendment physical worker already live')
        verify_preregistration()
        freeze_arm_order()
        log_path = protocol.RESULT_ROOT / \
            'collection/physical_collection.log'
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = open(log_path, 'a', buffering=1)
        command = ['/usr/bin/python3', str(Path(__file__).resolve()), 'run']
        process = subprocess.Popen(
            command, cwd=str(protocol.ROOT), stdout=log,
            stderr=subprocess.STDOUT, text=True, start_new_session=True)
        atomic_json(
            protocol.RESULT_ROOT / 'collection/physical_launcher.json', {
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
            raise SystemExit('no verified amendment physical worker')
        os.killpg(worker[1], signal.SIGINT)
        print('sent SIGINT to amendment physical worker')


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(
        KeyboardInterrupt()))
    main()
