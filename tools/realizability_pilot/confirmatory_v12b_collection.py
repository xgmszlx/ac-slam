#!/usr/bin/python3
"""No-peeking collection lifecycle for the fresh v12b experiment."""

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path

import confirmatory_v12_collection as engine
from controlled_branch_suite import atomic_json
from confirmatory_v12b_protocol import (
    ARM_ORDERS, ARMS, BUDGET_GATES, MAX_BRANCH_ATTEMPTS,
    MAX_HISTORY_ATTEMPTS_PER_SEED, PRIMARY_SEEDS, PROTOCOL_ID, RESERVE_SEEDS,
    RESULT_ROOT, START_HEADING_TOLERANCE_RAD, START_POSITION_TOLERANCE_M,
    action_specs, calibration_record, freeze_target, history_spec,
    preregistration_payload, sha256, write_preregistration,
)


def configure_engine(root):
    engine.ARM_ORDERS = ARM_ORDERS
    engine.ARMS = ARMS
    engine.BUDGET_GATES = BUDGET_GATES
    engine.MAX_BRANCH_ATTEMPTS = MAX_BRANCH_ATTEMPTS
    engine.MAX_HISTORY_ATTEMPTS_PER_SEED = MAX_HISTORY_ATTEMPTS_PER_SEED
    engine.PRIMARY_SEEDS = PRIMARY_SEEDS
    engine.PROTOCOL_ID = PROTOCOL_ID
    engine.RESERVE_SEEDS = RESERVE_SEEDS
    engine.RESULT_ROOT = Path(root)
    engine.START_HEADING_TOLERANCE_RAD = START_HEADING_TOLERANCE_RAD
    engine.START_POSITION_TOLERANCE_M = START_POSITION_TOLERANCE_M
    engine.freeze_target = freeze_target
    engine.history_spec = history_spec

    calibration = calibration_record(root)
    dwell_by_target = calibration['dwell_durations_s']
    engine.action_specs = lambda attempt, frozen, _ignored: action_specs(
        attempt, frozen, dwell_by_target)
    engine.run_calibration = lambda _root: {
        'status': 'TARGET_SPECIFIC_BUDGET_FROZEN',
        'selected_a3_dwell_s': dwell_by_target,
        'dwell_durations_s': dwell_by_target,
        'source': str(Path(root) / 'preregistration/target_specific_budget_preregistration.json'),
        'backend_was_not_launched': True,
        'science_outcomes_inspected': False,
    }
    engine.preregistration_payload = lambda *_args, **_kwargs: preregistration_payload(root)
    engine.write_initial_preregistration = lambda path: write_preregistration(path, root)


def named_preregistration(root):
    root = Path(root)
    named = root / 'preregistration/v12b_confirmatory_preregistration.json'
    payload = write_preregistration(named, root)
    # The reused v12 collection engine has frozen internal filenames.  Keep
    # byte-identical aliases so its hash guard protects the named v12b record.
    for name in ('v12_preregistration_initial.json', 'v12_preregistration.json'):
        path = root / 'preregistration' / name
        if path.exists() and json.loads(path.read_text()) != payload:
            raise RuntimeError('legacy engine preregistration alias differs')
        if not path.exists():
            atomic_json(path, payload)
    return payload


def collection_state_path(root):
    return Path(root) / 'collection_state.json'


def live_worker(root):
    path = collection_state_path(root)
    if not path.exists():
        return None
    state = json.loads(path.read_text())
    pid = state.get('worker_pid')
    if not pid or not (Path('/proc') / str(pid) / 'cmdline').exists():
        return None
    command = (Path('/proc') / str(pid) / 'cmdline').read_bytes().replace(
        b'\0', b' ').decode(errors='replace')
    if 'confirmatory_v12b_collection.py' not in command:
        return None
    return int(pid), int(state['worker_pgid'])


def collect(root):
    root = Path(root).resolve()
    named_preregistration(root)
    configure_engine(root)
    code = engine.collect(root)
    if code == 0:
        state = json.loads(collection_state_path(root).read_text())
        if state['status'] != 'COLLECTION_COMPLETE':
            raise RuntimeError('engine returned success without complete collection')
        atomic_json(root / 'COLLECTION_LOCKED.json', {
            'status': 'COLLECTION_LOCKED',
            'protocol_id': PROTOCOL_ID,
            'protocol_hash': state['protocol_hash'],
            'locked_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'scientific_analysis_not_yet_run': True,
        })
    return code


def main():
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(
        KeyboardInterrupt()))
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('plan', 'run', 'start', 'status', 'stop'))
    parser.add_argument('--root', type=Path, default=RESULT_ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == 'plan':
        root.mkdir(parents=True, exist_ok=True)
        payload = named_preregistration(root)
        print(json.dumps({'status': 'PREREGISTERED', 'protocol_id': PROTOCOL_ID,
                          'blocks': 8, 'branches': 24,
                          'analysis_code_hash': payload['code_hashes'][
                              'tools/realizability_pilot/confirmatory_v12b_analysis.py']},
                         indent=2, sort_keys=True))
    elif args.command == 'run':
        raise SystemExit(collect(root))
    elif args.command == 'start':
        root.mkdir(parents=True, exist_ok=True)
        if live_worker(root):
            raise SystemExit('verified v12b worker already live')
        named_preregistration(root)
        log = open(root / 'collection.log', 'a', buffering=1)
        command = ['/usr/bin/python3', str(Path(__file__).resolve()), 'run',
                   '--root', str(root)]
        process = subprocess.Popen(
            command, cwd=str(RESULT_ROOT.parents[2]), stdout=log,
            stderr=subprocess.STDOUT, text=True, start_new_session=True)
        atomic_json(root / 'launcher.json', {
            'pid': process.pid, 'pgid': process.pid, 'command': command,
            'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
        print(json.dumps({'status': 'STARTED', 'pid': process.pid,
                          'root': str(root)}, indent=2))
    elif args.command == 'status':
        path = collection_state_path(root)
        state = json.loads(path.read_text()) if path.exists() else {
            'status': 'NOT_STARTED', 'blocks': []}
        counts = {}
        for block in state.get('blocks', []):
            counts[block['status']] = counts.get(block['status'], 0) + 1
        print(json.dumps({'status': state['status'],
                          'live_worker': bool(live_worker(root)),
                          'block_counts': counts,
                          'updated_utc': state.get('updated_utc')},
                         indent=2, sort_keys=True))
    else:
        worker = live_worker(root)
        if not worker:
            raise SystemExit('no verified v12b worker')
        os.killpg(worker[1], signal.SIGINT)
        print('sent SIGINT to verified v12b worker group {}'.format(worker[1]))


if __name__ == '__main__':
    main()
