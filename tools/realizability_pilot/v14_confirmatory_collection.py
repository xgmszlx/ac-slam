#!/usr/bin/python3
"""Physical-only v14 collection with an irreversible collection lock."""

import argparse
import csv
import json
import os
import signal
import socket
import subprocess
import time
import traceback
from collections import Counter
from pathlib import Path

from controlled_branch_suite import WORLD, atomic_json, pose_error, wait_topic
from run_pilot import (activated_environment, command_output, start_process,
                       stop_process)
from v14_confirmatory_protocol import (
    ARM_ORDERS, ARM_ORDER_MANIFEST_PATH, ARMS, MAX_CAPTURE_ATTEMPTS, N_SCANS,
    PREREGISTRATION_PATH, PROTOCOL_ID, RESULT_ROOT, ROOT,
    START_HEADING_TOLERANCE_RAD, START_POSITION_TOLERANCE_M, TARGETS,
    action_specs, frozen_blocks, load_json, sha256,
)


LOCK_PATH = RESULT_ROOT / 'collection/PHYSICAL_COLLECTION_LOCK.json'


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def state_path():
    return RESULT_ROOT / 'collection/physical_collection_state.json'


def save_state(state):
    state['updated_utc'] = now()
    state_path().parent.mkdir(parents=True, exist_ok=True)
    atomic_json(state_path(), state)


def verify_preregistration():
    if not PREREGISTRATION_PATH.is_file():
        raise RuntimeError('v14 preregistration missing')
    prereg = load_json(PREREGISTRATION_PATH)
    for relative, expected in prereg['code_hashes'].items():
        if sha256(ROOT / relative) != expected:
            raise RuntimeError('frozen v14 code changed: {}'.format(relative))
    return prereg, sha256(PREREGISTRATION_PATH)


def freeze_arm_order():
    blocks = frozen_blocks()
    rows = []
    for block in blocks:
        index = int(block['block_id'].split('_H')[1]) - 1
        rows.append({
            'block_id': block['block_id'],
            'target_label': block['target_label'], 'seed': block['seed'],
            'arm_order': ARM_ORDERS[block['target_label']][index],
        })
    counts = {arm: Counter() for arm in ARMS}
    for row in rows:
        for position, arm in enumerate(row['arm_order'], 1):
            counts[arm][position] += 1
    balance = {arm: {str(pos): counts[arm][pos] for pos in (1, 2, 3)}
               for arm in ARMS}
    if any(max(values.values()) - min(values.values()) > 1
           for values in balance.values()):
        raise RuntimeError('frozen arm order is not position-balanced')
    payload = {
        'protocol_id': PROTOCOL_ID, 'blocks': rows,
        'position_counts': balance,
        'max_position_count_difference': 1,
        'history_property_used': False, 'frozen_utc': now(),
    }
    if ARM_ORDER_MANIFEST_PATH.exists():
        existing = load_json(ARM_ORDER_MANIFEST_PATH)
        stable_existing = dict(existing)
        stable_existing.pop('frozen_utc', None)
        stable_payload = dict(payload)
        stable_payload.pop('frozen_utc', None)
        if stable_existing != stable_payload:
            raise RuntimeError('refusing to modify frozen arm-order manifest')
        return existing
    ARM_ORDER_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(ARM_ORDER_MANIFEST_PATH, payload)
    return payload


def block_dir(block):
    return (RESULT_ROOT / 'collection/captures' / block['target_label'] /
            block['block_id'])


def prepare_block(block):
    directory = block_dir(block)
    directory.mkdir(parents=True, exist_ok=True)
    specs, frozen = action_specs(block)
    specs['common']['scientific_treatment_scan_budget'] = N_SCANS
    for path, payload in ((directory / 'action_specs.json', specs),
                          (directory / 'frozen_target.json', frozen)):
        if path.exists() and load_json(path) != payload:
            raise RuntimeError('frozen collection input changed: {}'.format(path))
        if not path.exists():
            atomic_json(path, payload)
    return directory, specs


def _free_port():
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def run_fixed_stage_capture(spec, run_dir):
    run_dir = Path(run_dir)
    if run_dir.exists():
        raise RuntimeError('refusing to overwrite {}'.format(run_dir))
    run_dir.mkdir(parents=True)
    spec_path = run_dir / 'capture_spec.json'
    atomic_json(spec_path, spec)
    env = activated_environment()
    port = _free_port()
    env['ROS_MASTER_URI'] = 'http://127.0.0.1:{}'.format(port)
    env['ROS_HOSTNAME'] = '127.0.0.1'
    env['ROS_LOG_DIR'] = str(run_dir / 'ros_logs')
    Path(env['ROS_LOG_DIR']).mkdir(parents=True)
    roscore = stage = None
    try:
        roscore = start_process(['roscore', '-p', str(port)], env,
                                run_dir / 'roscore.log')
        for _ in range(120):
            if command_output(['rosparam', 'list'], env, timeout=5).returncode == 0:
                break
            time.sleep(0.25)
        else:
            raise RuntimeError('fresh ROS master did not start')
        stage = start_process(['rosrun', 'stage_ros', 'stageros', str(WORLD)],
                              env, run_dir / 'stage.log')
        for topic in ('/base_pose_ground_truth', '/odom', '/base_scan', '/cmd_vel'):
            wait_topic(env, topic)
        with open(run_dir / 'driver.log', 'w') as log:
            completed = subprocess.run([
                '/usr/bin/python3', str(ROOT /
                'tools/realizability_pilot/fixed_scan_capture.py'),
                '--spec', str(spec_path), '--output-dir', str(run_dir)],
                cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT,
                timeout=600, text=True)
        path = run_dir / 'capture_result.json'
        if not path.exists():
            raise RuntimeError('fixed-scan controller exited {} without result'.format(
                completed.returncode))
        return load_json(path)
    finally:
        stop_process(stage)
        stop_process(roscore)


def validate_capture(spec, result, directory):
    required = ['capture_result.json', 'capture_spec.json',
                'probe_stream_raw.jsonl', 'scientific_treatment_stream.jsonl',
                'probe_gt_trajectory.txt']
    missing = [name for name in required if not (directory / name).is_file()]
    terminal = spec['canonical_terminal_gt_pose']
    start_error = pose_error(result['branch_start_gt_pose'], terminal)
    start_ok = (start_error[0] <= START_POSITION_TOLERANCE_M and
                start_error[1] <= START_HEADING_TOLERANCE_RAD)
    checks = {
        'controller_status_succeeded': result.get('status') == 'SUCCEEDED',
        'branch_start_gate_passed': start_ok,
        'exact_N': result.get('scientific_treatment_scan_count') == N_SCANS,
        'completion_within_N': 0 < int(result.get('completion_scan_index', 0)) <= N_SCANS,
        'nonnegative_completion_margin': int(result.get('completion_margin', -1)) >= 0,
        'exact_first_N': bool(result.get('scientific_stream_exact_first_N')),
        'no_duplicate_timestamp': result.get('duplicate_timestamp_count') == 0,
        'strictly_monotonic_timestamp': result.get(
            'nonmonotonic_timestamp_count') == 0,
        'required_files_present': not missing,
        'backend_not_started': result.get('backend_started') is False,
        'scientific_endpoint_not_read': result.get('scientific_endpoint_read') is False,
    }
    return {
        'valid': all(checks.values()), 'checks': checks,
        'missing_files': missing,
        'branch_start_position_error_m': start_error[0],
        'branch_start_heading_error_rad': start_error[1],
    }


def initial_state(prereg_hash, order_manifest):
    by_block = {row['block_id']: row for row in order_manifest['blocks']}
    return {
        'protocol_id': PROTOCOL_ID, 'preregistration_sha256': prereg_hash,
        'status': 'PLANNED', 'created_utc': now(),
        'scientific_endpoints_read': [], 'backend_started': False,
        'blocks': [{
            'block_id': block['block_id'],
            'target_label': block['target_label'], 'seed': block['seed'],
            'arm_order': by_block[block['block_id']]['arm_order'],
            'status': 'PENDING', 'branches': {},
        } for block in frozen_blocks()],
    }


def selected_attempt(arm_dir):
    for attempt in sorted(arm_dir.glob('attempt_*')):
        validation = attempt / 'technical_validation.json'
        if validation.is_file() and load_json(validation).get('valid'):
            return attempt, load_json(attempt / 'capture_result.json'), \
                load_json(validation)
    return None, None, None


def capture_branch(state, block_state, block, specs, arm):
    directory = block_dir(block) / arm
    directory.mkdir(parents=True, exist_ok=True)
    selected, result, validation = selected_attempt(directory)
    while selected is None:
        number = len(list(directory.glob('attempt_*'))) + 1
        if number > MAX_CAPTURE_ATTEMPTS:
            break
        attempt = directory / 'attempt_{:02d}'.format(number)
        spec = dict(specs['common'], **specs['actions'][arm])
        spec.update({
            'scientific_treatment_scan_budget': N_SCANS,
            'protocol_role': 'v14_prospective_physical_collection_only',
            'backend_started': False, 'scientific_endpoint_read': False,
        })
        try:
            result = run_fixed_stage_capture(spec, attempt)
            validation = validate_capture(spec, result, attempt)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            attempt.mkdir(parents=True, exist_ok=True)
            validation = {
                'valid': False, 'technical_exception':
                    '{}: {}'.format(type(exc).__name__, exc),
                'traceback': traceback.format_exc(),
            }
        atomic_json(attempt / 'technical_validation.json', validation)
        if validation.get('valid'):
            selected = attempt
        block_state['branches'][arm] = {
            'status': ('TECHNICALLY_VALID' if selected else
                       'TECHNICAL_ATTEMPT_FAILED'),
            'attempt_count': number,
            'last_attempt': str(attempt.relative_to(ROOT)),
        }
        save_state(state)
    if selected is None:
        block_state['branches'][arm] = {
            'status': 'TECHNICALLY_INVALID_FINAL',
            'attempt_count': len(list(directory.glob('attempt_*'))),
        }
        save_state(state)
        return False
    block_state['branches'][arm] = {
        'status': 'TECHNICALLY_VALID',
        'attempt_count': len(list(directory.glob('attempt_*'))),
        'selected_attempt': str(selected.relative_to(ROOT)),
        'scientific_treatment_scan_count': result['scientific_treatment_scan_count'],
        'completion_scan_index': result['completion_scan_index'],
        'completion_margin': result['completion_margin'],
        'duration_s': result['wall_clock_duration_s'],
        'distance_m': result['treatment_path_length_m'],
        'yaw_excursion_rad': result['treatment_yaw_excursion_rad'],
    }
    save_state(state)
    return True


def write_ledger(state):
    rows = []
    for block in state['blocks']:
        for position, arm in enumerate(block['arm_order'], 1):
            branch = block['branches'].get(arm, {})
            rows.append({
                'block_id': block['block_id'], 'target': block['target_label'],
                'seed': block['seed'], 'arm': arm, 'arm_position': position,
                **branch,
            })
    path = RESULT_ROOT / 'collection/physical_collection_ledger.csv'
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


def create_lock(state):
    rows = write_ledger(state)
    branches = []
    for row in rows:
        selected = row.get('selected_attempt')
        entry = dict(row)
        if selected:
            directory = ROOT / selected
            entry.update({
                'raw_stream_sha256': sha256(directory / 'probe_stream_raw.jsonl'),
                'scientific_stream_sha256': sha256(
                    directory / 'scientific_treatment_stream.jsonl'),
                'capture_result_sha256': sha256(directory / 'capture_result.json'),
                'gt_trajectory_sha256': sha256(
                    directory / 'probe_gt_trajectory.txt'),
                'exact_N': N_SCANS,
            })
        branches.append(entry)
    complete = (len(branches) == 24 and all(
        row.get('status') == 'TECHNICALLY_VALID' for row in branches))
    payload = {
        'protocol_id': PROTOCOL_ID,
        'status': ('PHYSICAL_COLLECTION_LOCKED_COMPLETE' if complete else
                   'PHYSICAL_COLLECTION_LOCKED_TECHNICALLY_INCOMPLETE'),
        'complete': complete, 'planned_branches': 24,
        'valid_branches': sum(row.get('status') == 'TECHNICALLY_VALID'
                              for row in branches),
        'N': N_SCANS, 'branches': branches,
        'no_further_capture_authorized': True,
        'scientific_endpoints_read': [], 'backend_started': False,
        'locked_utc': now(),
    }
    if LOCK_PATH.exists() and load_json(LOCK_PATH) != payload:
        raise RuntimeError('physical collection is already locked')
    if not LOCK_PATH.exists():
        atomic_json(LOCK_PATH, payload)
    state['status'] = payload['status']
    state['completed_utc'] = now()
    state.pop('worker_pid', None)
    state.pop('worker_pgid', None)
    save_state(state)
    return payload


def collect():
    if LOCK_PATH.exists():
        return load_json(LOCK_PATH)
    _prereg, prereg_hash = verify_preregistration()
    order = freeze_arm_order()
    state = (load_json(state_path()) if state_path().exists()
             else initial_state(prereg_hash, order))
    if state['preregistration_sha256'] != prereg_hash:
        raise RuntimeError('preregistration hash changed after collection began')
    state.update(status='RUNNING', worker_pid=os.getpid(),
                 worker_pgid=os.getpgrp(),
                 started_utc=state.get('started_utc', now()))
    save_state(state)
    blocks = {row['block_id']: row for row in frozen_blocks()}
    try:
        for block_state in state['blocks']:
            block = blocks[block_state['block_id']]
            _directory, specs = prepare_block(block)
            block_state['status'] = 'CAPTURING'
            save_state(state)
            valid = True
            for arm in block_state['arm_order']:
                if block_state['branches'].get(arm, {}).get('status') == \
                        'TECHNICALLY_VALID':
                    continue
                if not capture_branch(state, block_state, block, specs, arm):
                    valid = False
            block_state['status'] = ('PHYSICALLY_COLLECTED' if valid else
                                     'TECHNICALLY_INVALID_FINAL')
            save_state(state)
        return create_lock(state)
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
        if 'v14_confirmatory_collection.py' in command else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('run', 'start', 'status', 'stop'))
    args = parser.parse_args()
    if args.command == 'run':
        print(json.dumps(collect(), indent=2, sort_keys=True))
    elif args.command == 'start':
        if LOCK_PATH.exists():
            raise SystemExit('physical collection already locked')
        if live_worker():
            raise SystemExit('v14 physical collection worker already live')
        verify_preregistration()
        freeze_arm_order()
        log_path = RESULT_ROOT / 'collection/physical_collection.log'
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = open(log_path, 'a', buffering=1)
        command = ['/usr/bin/python3', str(Path(__file__).resolve()), 'run']
        process = subprocess.Popen(command, cwd=str(ROOT), stdout=log,
                                   stderr=subprocess.STDOUT, text=True,
                                   start_new_session=True)
        atomic_json(RESULT_ROOT / 'collection/physical_launcher.json', {
            'pid': process.pid, 'pgid': process.pid, 'command': command,
            'started_utc': now()})
        print(json.dumps({'status': 'STARTED', 'pid': process.pid}, indent=2))
    elif args.command == 'status':
        state = load_json(state_path()) if state_path().exists() else {
            'status': 'NOT_STARTED', 'blocks': []}
        print(json.dumps({
            'status': state['status'], 'live_worker': bool(live_worker()),
            'block_statuses': dict(Counter(
                row['status'] for row in state.get('blocks', []))),
            'physical_lock_exists': LOCK_PATH.exists(),
            'updated_utc': state.get('updated_utc'),
        }, indent=2, sort_keys=True))
    else:
        worker = live_worker()
        if not worker:
            raise SystemExit('no verified v14 physical worker')
        os.killpg(worker[1], signal.SIGINT)
        print('sent SIGINT to v14 physical collection worker')


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(
        KeyboardInterrupt()))
    main()
