#!/usr/bin/python3
"""Durable orchestrator for CD technical amendment 1."""

import argparse
import json
import os
import signal
import subprocess
import time
import traceback
from collections import Counter
from pathlib import Path

import cd_confirmatory_amendment_analysis as analysis
import cd_confirmatory_amendment_collection as collection
import cd_confirmatory_amendment_protocol as protocol
import cd_confirmatory_amendment_replay as replay
from controlled_branch_suite import atomic_json


STATE_PATH = protocol.RESULT_ROOT / 'pipeline_state.json'
LAUNCHER_PATH = protocol.RESULT_ROOT / 'pipeline_launcher.json'


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def save_state(state):
    state['updated_utc'] = now()
    protocol.RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    atomic_json(STATE_PATH, state)


def verify_preregistration():
    prereg, digest = collection.verify_preregistration()
    if not protocol.scientific_design_unchanged(prereg)['passed']:
        raise RuntimeError('scientific design changed in amendment')
    return prereg, digest


def prepare():
    result = protocol.prepare_amendment()
    state = {
        'protocol_id': protocol.PROTOCOL_ID,
        'status': 'PREREGISTERED',
        'current_stage': 'PRE_COLLECTION',
        'preregistration_sha256': result['preregistration_sha256'],
        'histories_regenerated': False,
        'original_run_preserved': True,
        'created_utc': now(),
    }
    save_state(state)
    return result


def run_pipeline():
    _prereg, digest = verify_preregistration()
    state = protocol.load_json(STATE_PATH)
    if state['preregistration_sha256'] != digest:
        raise RuntimeError('preregistration hash changed')
    state.update({
        'status': 'RUNNING',
        'worker_pid': os.getpid(),
        'worker_pgid': os.getpgrp(),
        'started_utc': state.get('started_utc', now()),
    })
    save_state(state)
    try:
        if not protocol.original_run_audit()['passed']:
            raise RuntimeError('original run immutability audit failed')
        state['current_stage'] = 'PHYSICAL_COLLECTION'
        save_state(state)
        collection.configure_base()
        physical = collection.base.legacy.collect()
        if physical.get('status') == 'INTERRUPTED':
            state.update(status='INTERRUPTED',
                         current_stage='PHYSICAL_COLLECTION')
            state.pop('worker_pid', None)
            state.pop('worker_pgid', None)
            save_state(state)
            return physical
        if not physical.get('complete'):
            final = analysis.write_technical_incomplete(
                'PHYSICAL_COLLECTION', physical.get('status', 'UNKNOWN'))
            state.update(status='COMPLETE_TECHNICALLY_INCOMPLETE',
                         current_stage='HARD_STOP',
                         final_gate=final['final_scientific_gate'])
            save_state(state)
            return final

        if not protocol.original_run_audit()['passed']:
            raise RuntimeError('original run changed during collection')
        state['current_stage'] = 'BACKEND_REPLAY'
        save_state(state)
        replay.configure_base()
        backend = replay.base.legacy.run()
        if backend.get('status') == 'INTERRUPTED':
            state.update(status='INTERRUPTED',
                         current_stage='BACKEND_REPLAY')
            state.pop('worker_pid', None)
            state.pop('worker_pgid', None)
            save_state(state)
            return backend
        if not backend.get('complete'):
            final = analysis.write_technical_incomplete(
                'BACKEND_REPLAY', backend.get('status', 'UNKNOWN'))
            state.update(status='COMPLETE_TECHNICALLY_INCOMPLETE',
                         current_stage='HARD_STOP',
                         final_gate=final['final_scientific_gate'])
            save_state(state)
            return final

        if not protocol.original_run_audit()['passed']:
            raise RuntimeError('original run changed during backend replay')
        state['current_stage'] = 'FROZEN_SCIENTIFIC_ANALYSIS'
        save_state(state)
        final = analysis.analyze()
        state.update(status='COMPLETE', current_stage='HARD_STOP',
                     final_gate=final['final_scientific_gate'])
        state.pop('worker_pid', None)
        state.pop('worker_pgid', None)
        save_state(state)
        return final
    except KeyboardInterrupt:
        state.update(status='INTERRUPTED', interrupted_utc=now())
        state.pop('worker_pid', None)
        state.pop('worker_pgid', None)
        save_state(state)
        return {'status': 'INTERRUPTED',
                'current_stage': state.get('current_stage')}
    except Exception as exc:
        failure = '{}: {}'.format(type(exc).__name__, exc)
        final = analysis.write_technical_incomplete(
            state.get('current_stage', 'UNKNOWN'), failure)
        state.update(
            status='COMPLETE_TECHNICALLY_INCOMPLETE',
            current_stage='HARD_STOP',
            final_gate=final['final_scientific_gate'],
            failure=failure,
            traceback=traceback.format_exc())
        state.pop('worker_pid', None)
        state.pop('worker_pgid', None)
        save_state(state)
        return final


def live_worker():
    state = protocol.load_json(STATE_PATH) if STATE_PATH.exists() else {}
    pid = state.get('worker_pid')
    cmdline = Path('/proc') / str(pid) / 'cmdline' if pid else None
    if not cmdline or not cmdline.exists():
        return None
    command = cmdline.read_bytes().replace(
        b'\0', b' ').decode(errors='replace')
    if 'cd_confirmatory_amendment_pipeline.py' in command:
        return int(pid), int(state['worker_pgid'])
    return None


def status():
    state = protocol.load_json(STATE_PATH) if STATE_PATH.exists() else {
        'status': 'NOT_PREPARED', 'current_stage': 'NONE'}
    output = {
        'protocol_id': protocol.PROTOCOL_ID,
        'status': state.get('status'),
        'current_stage': state.get('current_stage'),
        'live_worker': bool(live_worker()),
        'updated_utc': state.get('updated_utc'),
        'final_gate': state.get('final_gate'),
    }
    physical = protocol.RESULT_ROOT / \
        'collection/physical_collection_state.json'
    if physical.exists():
        data = protocol.load_json(physical)
        output['physical_block_statuses'] = dict(Counter(
            row['status'] for row in data.get('blocks', [])))
    backend = protocol.RESULT_ROOT / 'collection/backend_replay_state.json'
    if backend.exists():
        data = protocol.load_json(backend)
        output['replay_branch_statuses'] = dict(Counter(
            row['status'] for row in data.get('branches', {}).values()))
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=(
        'prepare', 'run', 'start', 'status', 'stop'))
    args = parser.parse_args()
    if args.command == 'prepare':
        print(json.dumps(prepare(), indent=2, sort_keys=True))
    elif args.command == 'run':
        print(json.dumps(run_pipeline(), indent=2, sort_keys=True))
    elif args.command == 'start':
        if live_worker():
            raise SystemExit('amendment pipeline worker already live')
        verify_preregistration()
        log = open(protocol.RESULT_ROOT / 'pipeline.log', 'a', buffering=1)
        command = ['/usr/bin/python3', str(Path(__file__).resolve()), 'run']
        process = subprocess.Popen(
            command, cwd=str(protocol.ROOT), stdout=log,
            stderr=subprocess.STDOUT, text=True, start_new_session=True)
        atomic_json(LAUNCHER_PATH, {
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
            raise SystemExit('no verified amendment pipeline worker')
        os.killpg(worker[1], signal.SIGINT)
        print('sent SIGINT to amendment pipeline worker')


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(
        KeyboardInterrupt()))
    main()
