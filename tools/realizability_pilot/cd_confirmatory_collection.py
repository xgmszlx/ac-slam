#!/usr/bin/python3
"""Physical collection and manipulation lock for the CD experiment."""

import argparse
import csv
import json
import os
import signal
import socket
import subprocess
import time
from collections import Counter
from pathlib import Path

import v14_confirmatory_collection as legacy
from cd_confirmatory_guard import assert_prelock_no_scientific_outputs
from cd_confirmatory_protocol import (
    ARM_ORDERS, ARM_ORDER_MANIFEST_PATH, ARMS, D0_YAW_MAX_RAD, DOSES,
    FINAL_HEADING_TOLERANCE_RAD, MAX_CAPTURE_ATTEMPTS,
    MIN_COMPLETION_MARGIN, N_SCANS, PREREGISTRATION_PATH, PROTOCOL_ID,
    RESULT_ROOT, ROOT, START_HEADING_TOLERANCE_RAD,
    START_POSITION_TOLERANCE_M, TARGETS, YAW_TOLERANCE_RAD,
    action_specs, frozen_blocks, load_json, sha256,
)
from controlled_branch_suite import WORLD, atomic_json, pose_error, wait_topic
from run_pilot import (
    activated_environment, command_output, start_process, stop_process,
)


LOCK_PATH = RESULT_ROOT / 'collection/PHYSICAL_COLLECTION_LOCK.json'


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def verify_preregistration():
    if not PREREGISTRATION_PATH.is_file():
        raise RuntimeError('CD preregistration missing')
    prereg = load_json(PREREGISTRATION_PATH)
    for relative, expected in prereg['code_hashes'].items():
        if sha256(ROOT / relative) != expected:
            raise RuntimeError('frozen CD code changed: {}'.format(relative))
    assert_prelock_no_scientific_outputs()
    return prereg, sha256(PREREGISTRATION_PATH)


def _free_port():
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def run_confirmatory_capture(spec, run_dir):
    spec = dict(spec)
    spec.update({
        'protocol_role': 'CD_PROSPECTIVE_PHYSICAL_COLLECTION_ONLY',
        'backend_started': False,
        'scientific_endpoint_read': False,
    })
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
            if command_output(
                    ['rosparam', 'list'], env, timeout=5).returncode == 0:
                break
            time.sleep(0.25)
        else:
            raise RuntimeError('fresh ROS master did not start')
        stage = start_process(
            ['rosrun', 'stage_ros', 'stageros', str(WORLD)], env,
            run_dir / 'stage.log')
        for topic in ('/base_pose_ground_truth', '/odom', '/base_scan',
                      '/cmd_vel'):
            wait_topic(env, topic)
        with open(run_dir / 'driver.log', 'w') as log:
            completed = subprocess.run([
                '/usr/bin/python3',
                str(ROOT /
                    'tools/realizability_pilot/cd_confirmatory_capture.py'),
                '--spec', str(spec_path), '--output-dir', str(run_dir)],
                cwd=str(ROOT), env=env, stdout=log,
                stderr=subprocess.STDOUT, timeout=600, text=True)
        result_path = run_dir / 'capture_result.json'
        if not result_path.exists():
            raise RuntimeError(
                'dose controller exited {} without result'.format(
                    completed.returncode))
        return load_json(result_path)
    finally:
        stop_process(stage)
        stop_process(roscore)


def validate_capture(spec, result, directory):
    directory = Path(directory)
    required = [
        'capture_result.json', 'capture_spec.json', 'probe_stream_raw.jsonl',
        'scientific_treatment_stream.jsonl', 'probe_gt_trajectory.txt',
        'pre_treatment_descriptor.json',
    ]
    missing = [name for name in required if not (directory / name).is_file()]
    terminal = spec['canonical_terminal_gt_pose']
    start_error = pose_error(result['branch_start_gt_pose'], terminal)
    arm = spec['action_id']
    actual = float(result.get('actual_cumulative_yaw_rad', float('inf')))
    planned = DOSES[arm]
    dose_ok = (actual <= D0_YAW_MAX_RAD if arm == 'D0_ZERO' else
               abs(actual - planned) <= YAW_TOLERANCE_RAD)
    checks = {
        'controller_status_succeeded': result.get('status') == 'SUCCEEDED',
        'branch_start_gate_passed': (
            start_error[0] <= START_POSITION_TOLERANCE_M and
            start_error[1] <= START_HEADING_TOLERANCE_RAD),
        'exact_N': result.get('scientific_treatment_scan_count') == N_SCANS,
        'completion_before_N': (
            0 < int(result.get('completion_scan_index', 0)) < N_SCANS),
        'minimum_completion_margin': (
            int(result.get('completion_margin', -1)) >=
            MIN_COMPLETION_MARGIN),
        'exact_first_N': bool(result.get('scientific_stream_exact_first_N')),
        'dose_manipulation_valid': dose_ok,
        'final_heading_valid': (
            float(result.get('final_heading_residual_rad', float('inf'))) <=
            FINAL_HEADING_TOLERANCE_RAD),
        'strict_pretreatment_descriptor': bool(
            result.get('pre_treatment_descriptor_strict')),
        'no_duplicate_timestamp': (
            result.get('duplicate_timestamp_count') == 0),
        'strictly_monotonic_timestamp': (
            result.get('nonmonotonic_timestamp_count') == 0),
        'required_files_present': not missing,
        'backend_not_started': result.get('backend_started') is False,
        'scientific_endpoint_not_read': (
            result.get('scientific_endpoint_read') is False),
    }
    return {
        'valid': all(checks.values()),
        'checks': checks,
        'missing_files': missing,
        'branch_start_position_error_m': start_error[0],
        'branch_start_heading_error_rad': start_error[1],
        'actual_dose_error_rad': actual - planned,
    }


def interval_overlap(left, right):
    return max(left[0], right[0]) <= min(left[1], right[1])


def fresh_manipulation_gate(branches):
    checks = []
    for target in TARGETS:
        blocks = sorted({row['block_id'] for row in branches
                         if row['target'] == target})
        for block_id in blocks:
            by_arm = {row['arm']: row for row in branches
                      if row['block_id'] == block_id}
            values = [float(by_arm[arm]['actual_cumulative_yaw_rad'])
                      for arm in ARMS]
            checks.append({
                'block_id': block_id,
                'strict_D0_lt_D1_lt_D2': values[0] < values[1] < values[2],
                'actual_doses': dict(zip(ARMS, values)),
            })
    target_overlap = {}
    for arm in ('D1_THRESHOLD', 'D2_HIGH'):
        dose_ranges = {}
        scan_ranges = {}
        for target in TARGETS:
            rows = [row for row in branches
                    if row['target'] == target and row['arm'] == arm]
            doses = [float(row['actual_cumulative_yaw_rad']) for row in rows]
            scans = [int(row['completion_scan_index']) for row in rows]
            dose_ranges[target] = [min(doses), max(doses)]
            scan_ranges[target] = [min(scans), max(scans)]
        target_overlap[arm] = {
            'actual_dose_ranges': dose_ranges,
            'actual_dose_ranges_overlap': interval_overlap(
                dose_ranges['target_A'], dose_ranges['target_B']),
            'completion_scan_ranges': scan_ranges,
            'completion_scan_ranges_overlap': interval_overlap(
                scan_ranges['target_A'], scan_ranges['target_B']),
        }
    passed = (all(row['strict_D0_lt_D1_lt_D2'] for row in checks) and
              all(row['actual_dose_ranges_overlap'] and
                  row['completion_scan_ranges_overlap']
                  for row in target_overlap.values()))
    return {
        'passed': passed,
        'machine_label': (
            'DOSE_TARGET_DECONFOUNDING_TECHNICALLY_CERTIFIED' if passed else
            'DOSE_TARGET_DECONFOUNDING_FAILED'),
        'block_dose_monotonicity': checks,
        'target_overlap': target_overlap,
    }


def write_enhanced_ledger(rows):
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


def create_lock(state):
    raw_rows = legacy.write_ledger(state)
    branches = []
    for row in raw_rows:
        entry = dict(row)
        selected = row.get('selected_attempt')
        if selected:
            directory = ROOT / selected
            result = load_json(directory / 'capture_result.json')
            descriptor = directory / 'pre_treatment_descriptor.json'
            entry.update({
                'actual_cumulative_yaw_rad': result[
                    'actual_cumulative_yaw_rad'],
                'planned_cumulative_yaw_rad': result[
                    'planned_cumulative_yaw_rad'],
                'actual_dose_error_rad': result['actual_dose_error_rad'],
                'maneuver_duration_s': result['maneuver_duration_s'],
                'moving_scan_count': result['moving_scan_count'],
                'final_heading_residual_rad': result[
                    'final_heading_residual_rad'],
                'duplicate_timestamp_count': result[
                    'duplicate_timestamp_count'],
                'nonmonotonic_timestamp_count': result[
                    'nonmonotonic_timestamp_count'],
                'raw_stream_sha256': sha256(
                    directory / 'probe_stream_raw.jsonl'),
                'scientific_stream_sha256': sha256(
                    directory / 'scientific_treatment_stream.jsonl'),
                'capture_result_sha256': sha256(
                    directory / 'capture_result.json'),
                'gt_trajectory_sha256': sha256(
                    directory / 'probe_gt_trajectory.txt'),
                'pre_treatment_descriptor_sha256': sha256(descriptor),
                'exact_N': N_SCANS,
            })
        branches.append(entry)
    valid_48 = (len(branches) == 48 and all(
        row.get('status') == 'TECHNICALLY_VALID' for row in branches))
    manipulation = (fresh_manipulation_gate(branches)
                    if valid_48 else {'passed': False,
                                      'machine_label': 'NOT_EVALUABLE'})
    complete = valid_48 and manipulation['passed']
    write_enhanced_ledger(branches)
    atomic_json(RESULT_ROOT / 'collection/fresh_manipulation_gate.json',
                manipulation)
    payload = {
        'protocol_id': PROTOCOL_ID,
        'status': ('PHYSICAL_COLLECTION_LOCKED_COMPLETE' if complete else
                   'PHYSICAL_COLLECTION_LOCKED_TECHNICALLY_INCOMPLETE'),
        'complete': complete,
        'planned_branches': 48,
        'valid_branches': sum(row.get('status') == 'TECHNICALLY_VALID'
                              for row in branches),
        'N': N_SCANS,
        'minimum_completion_margin': MIN_COMPLETION_MARGIN,
        'branches': branches,
        'fresh_manipulation_gate': manipulation,
        'no_further_capture_authorized': True,
        'scientific_endpoints_read': [],
        'backend_started': False,
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
    legacy.save_state(state)
    return payload


def configure_legacy():
    legacy.ARM_ORDERS = ARM_ORDERS
    legacy.ARM_ORDER_MANIFEST_PATH = ARM_ORDER_MANIFEST_PATH
    legacy.ARMS = ARMS
    legacy.LOCK_PATH = LOCK_PATH
    legacy.MAX_CAPTURE_ATTEMPTS = MAX_CAPTURE_ATTEMPTS
    legacy.N_SCANS = N_SCANS
    legacy.PREREGISTRATION_PATH = PREREGISTRATION_PATH
    legacy.PROTOCOL_ID = PROTOCOL_ID
    legacy.RESULT_ROOT = RESULT_ROOT
    legacy.ROOT = ROOT
    legacy.START_HEADING_TOLERANCE_RAD = START_HEADING_TOLERANCE_RAD
    legacy.START_POSITION_TOLERANCE_M = START_POSITION_TOLERANCE_M
    legacy.TARGETS = TARGETS
    legacy.action_specs = action_specs
    legacy.frozen_blocks = frozen_blocks
    legacy.load_json = load_json
    legacy.sha256 = sha256
    legacy.verify_preregistration = verify_preregistration
    legacy.run_fixed_stage_capture = run_confirmatory_capture
    legacy.validate_capture = validate_capture
    legacy.create_lock = create_lock


def live_worker():
    path = RESULT_ROOT / 'collection/physical_collection_state.json'
    if not path.exists():
        return None
    state = load_json(path)
    pid = state.get('worker_pid')
    cmdline = Path('/proc') / str(pid) / 'cmdline' if pid else None
    if not cmdline or not cmdline.exists():
        return None
    command = cmdline.read_bytes().replace(b'\0', b' ').decode(errors='replace')
    return ((int(pid), int(state['worker_pgid']))
            if 'cd_confirmatory_collection.py' in command else None)


def status():
    path = RESULT_ROOT / 'collection/physical_collection_state.json'
    state = load_json(path) if path.exists() else {
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
    configure_legacy()
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('run', 'start', 'status', 'stop'))
    args = parser.parse_args()
    if args.command == 'run':
        print(json.dumps(legacy.collect(), indent=2, sort_keys=True))
    elif args.command == 'start':
        if LOCK_PATH.exists():
            raise SystemExit('physical collection already locked')
        if live_worker():
            raise SystemExit('CD physical collection worker already live')
        verify_preregistration()
        legacy.freeze_arm_order()
        log_path = RESULT_ROOT / 'collection/physical_collection.log'
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = open(log_path, 'a', buffering=1)
        command = ['/usr/bin/python3', str(Path(__file__).resolve()), 'run']
        process = subprocess.Popen(
            command, cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT,
            text=True, start_new_session=True)
        atomic_json(RESULT_ROOT / 'collection/physical_launcher.json', {
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
            raise SystemExit('no verified CD physical worker')
        os.killpg(worker[1], signal.SIGINT)
        print('sent SIGINT to CD physical collection worker')


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(
        KeyboardInterrupt()))
    main()
