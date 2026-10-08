#!/usr/bin/python3
"""Durable gated orchestrator for the prospective CD experiment."""

import argparse
import json
import os
import signal
import subprocess
import time
import traceback
from collections import Counter
from pathlib import Path

import cd_confirmatory_analysis as analysis
import cd_confirmatory_collection as collection
import cd_confirmatory_qualification as qualification
import cd_confirmatory_replay as replay
from cd_confirmatory_protocol import (
    PREREGISTRATION_PATH, PROTOCOL_ID, RESULT_ROOT, ROOT, load_json, sha256,
    write_preregistration,
)
from controlled_branch_suite import atomic_json


STATE_PATH = RESULT_ROOT / 'pipeline_state.json'
LAUNCHER_PATH = RESULT_ROOT / 'pipeline_launcher.json'


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def save_state(state):
    state['updated_utc'] = now()
    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    atomic_json(STATE_PATH, state)


def verify_preregistration():
    if not PREREGISTRATION_PATH.is_file():
        raise RuntimeError('frozen preregistration missing')
    prereg = load_json(PREREGISTRATION_PATH)
    for relative, expected in prereg['code_hashes'].items():
        if sha256(ROOT / relative) != expected:
            raise RuntimeError('frozen CD code changed: {}'.format(relative))
    return prereg


def prepare():
    payload = write_preregistration()
    digest = sha256(PREREGISTRATION_PATH)
    state = {
        'protocol_id': PROTOCOL_ID,
        'status': 'PREREGISTERED',
        'current_stage': 'PRE_COLLECTION',
        'preregistration_sha256': digest,
        'fresh_history_started': False,
        'created_utc': now(),
    }
    save_state(state)
    return {'status': 'PREREGISTERED', 'sha256': digest,
            'protocol': payload['protocol_id']}


def run_pipeline():
    verify_preregistration()
    state = load_json(STATE_PATH) if STATE_PATH.exists() else {
        'protocol_id': PROTOCOL_ID,
        'status': 'PREREGISTERED',
        'preregistration_sha256': sha256(PREREGISTRATION_PATH),
        'fresh_history_started': False,
        'created_utc': now(),
    }
    if state['preregistration_sha256'] != sha256(PREREGISTRATION_PATH):
        raise RuntimeError('preregistration hash changed')
    state.update({
        'status': 'RUNNING',
        'worker_pid': os.getpid(),
        'worker_pgid': os.getpgrp(),
        'started_utc': state.get('started_utc', now()),
    })
    save_state(state)
    try:
        state.update(current_stage='CANDIDATE_QUALIFICATION',
                     fresh_history_started=True)
        save_state(state)
        qualified = qualification.collect()
        if qualified['technical_gate'] != 'CD_HISTORY_QUALIFICATION_PASS':
            final = analysis.write_technical_incomplete(
                'CANDIDATE_QUALIFICATION', qualified['technical_gate'])
            state.update(status='COMPLETE_TECHNICALLY_INCOMPLETE',
                         current_stage='HARD_STOP', final_gate=final[
                             'final_scientific_gate'])
            save_state(state)
            return final

        state['current_stage'] = 'PHYSICAL_COLLECTION'
        save_state(state)
        collection.configure_legacy()
        physical = collection.legacy.collect()
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
                         current_stage='HARD_STOP', final_gate=final[
                             'final_scientific_gate'])
            save_state(state)
            return final

        state['current_stage'] = 'BACKEND_REPLAY'
        save_state(state)
        replay.configure_legacy()
        backend = replay.legacy.run()
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
                         current_stage='HARD_STOP', final_gate=final[
                             'final_scientific_gate'])
            save_state(state)
            return final

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
    state = load_json(STATE_PATH) if STATE_PATH.exists() else {}
    pid = state.get('worker_pid')
    cmdline = Path('/proc') / str(pid) / 'cmdline' if pid else None
    if not cmdline or not cmdline.exists():
        return None
    command = cmdline.read_bytes().replace(b'\0', b' ').decode(errors='replace')
    return ((int(pid), int(state['worker_pgid']))
            if 'cd_confirmatory_pipeline.py' in command else None)


def status():
    state = load_json(STATE_PATH) if STATE_PATH.exists() else {
        'status': 'NOT_PREPARED', 'current_stage': 'NONE'}
    output = {
        'status': state.get('status'),
        'current_stage': state.get('current_stage'),
        'live_worker': bool(live_worker()),
        'updated_utc': state.get('updated_utc'),
        'final_gate': state.get('final_gate'),
    }
    manifest = RESULT_ROOT / 'qualification/history_eligibility_manifest.json'
    if manifest.exists():
        qualified = load_json(manifest)
        output['qualification_evaluated'] = len(qualified.get('records', []))
        output['qualification_gate'] = qualified.get('technical_gate')
    physical = RESULT_ROOT / 'collection/physical_collection_state.json'
    if physical.exists():
        data = load_json(physical)
        output['physical_block_statuses'] = dict(Counter(
            row['status'] for row in data.get('blocks', [])))
    backend = RESULT_ROOT / 'collection/backend_replay_state.json'
    if backend.exists():
        data = load_json(backend)
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
            raise SystemExit('CD pipeline worker already live')
        verify_preregistration()
        log = open(RESULT_ROOT / 'pipeline.log', 'a', buffering=1)
        command = ['/usr/bin/python3', str(Path(__file__).resolve()), 'run']
        process = subprocess.Popen(
            command, cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT,
            text=True, start_new_session=True)
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
            raise SystemExit('no verified CD pipeline worker')
        os.killpg(worker[1], signal.SIGINT)
        print('sent SIGINT to CD pipeline worker')


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(
        KeyboardInterrupt()))
    main()
