#!/usr/bin/python3
"""Run and close the no-backend CD-T controller certification."""

import argparse
import csv
import json
import math
import os
import signal
import socket
import statistics
import subprocess
import time
import traceback
from pathlib import Path

from controlled_branch_suite import WORLD, atomic_json, pose_error, wait_topic
from context_disentangle_protocol import (
    ARM_ORDERS, ARMS, DOSES, DOSE_MEAN_MATCH_TOLERANCE_RAD,
    DOSE_OVERLAP_MIN_FRACTION, D0_YAW_MAX_RAD, FINAL_HEADING_TOLERANCE_RAD,
    MIN_COMPLETION_MARGIN, N_SCANS, PROTOCOL_ID, RESULT_ROOT, ROOT,
    START_HEADING_TOLERANCE_RAD, START_POSITION_TOLERANCE_M, TARGETS,
    V14_ROOT, dose_motion, frozen_provenance, load_json, sha256,
    YAW_TOLERANCE_RAD,
)
from run_pilot import (activated_environment, command_output, start_process,
                       stop_process)


PROTOCOL_PATH = RESULT_ROOT / 'preregistration/CDT_protocol.json'


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def _free_port():
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def write_csv(path, rows):
    rows = list(rows)
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with open(path, 'w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def source_specs_path(target, index):
    block_id = '{}_H{}'.format(target, index)
    return V14_ROOT / 'collection/captures' / target / block_id / 'action_specs.json'


def controlled_spec(target, index, arm):
    source_path = source_specs_path(target, index)
    payload = load_json(source_path)
    common = dict(payload['common'])
    source = payload['actions']['A1_DWELL']
    core = int(source['core_action_start_index'])
    waypoints = [list(row) for row in source['action_waypoints'][:core + 1]]
    labels = list(source['action_labels'][:core + 1])
    anchor = list(waypoints[core])
    theta0 = float(anchor[2])
    motion = dose_motion(theta0, arm)
    for label, heading in zip(motion['post_start_labels'],
                              motion['headings_rad'][1:]):
        labels.append(label)
        waypoints.append([float(anchor[0]), float(anchor[1]), float(heading)])
    spec = dict(common)
    spec.update({
        'action_id': arm,
        'action_labels': labels,
        'action_waypoints': waypoints,
        'core_action_start_index': core,
        'theta0_rad': theta0,
        'planned_cumulative_yaw_rad': DOSES[arm],
        'scientific_treatment_scan_budget': N_SCANS,
        'protocol_role': 'CDT_TECHNICAL_CERTIFICATION_ONLY',
        'technical_only': True, 'backend_started': False,
        'scientific_endpoint_read': False,
        'source_old_geometry': str(source_path.relative_to(ROOT)),
        'source_old_geometry_sha256': sha256(source_path),
        'standardized_new_intervention': True,
        'not_old_A1_A3_A2_replication': True,
        'controller_properties': {
            'max_angular_velocity_rad_s': 0.65,
            'proportional_gain': 1.8,
            'heading_tolerance_rad': 0.018,
            'stable_cycles': 3,
            'control_period_s': 0.05,
            'zero_twist_hold': True,
        },
    })
    return spec


def block_rows():
    rows = []
    for target in TARGETS:
        for index in range(1, 5):
            rows.append({
                'target': target, 'index': index,
                'block': '{}_H{}'.format(target, index),
                'arm_order': ARM_ORDERS[target][index - 1],
            })
    return rows


def run_stage_capture(spec, run_dir):
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
            if command_output(['rosparam', 'list'], env,
                              timeout=5).returncode == 0:
                break
            time.sleep(0.25)
        else:
            raise RuntimeError('fresh ROS master did not start')
        stage = start_process(['rosrun', 'stage_ros', 'stageros', str(WORLD)],
                              env, run_dir / 'stage.log')
        for topic in ('/base_pose_ground_truth', '/odom', '/base_scan',
                      '/cmd_vel'):
            wait_topic(env, topic)
        with open(run_dir / 'driver.log', 'w') as log:
            completed = subprocess.run([
                '/usr/bin/python3', str(
                    ROOT / 'tools/realizability_pilot' /
                    'context_disentangle_capture.py'),
                '--spec', str(spec_path), '--output-dir', str(run_dir)],
                cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT,
                timeout=600, text=True)
        result_path = run_dir / 'capture_result.json'
        if not result_path.is_file():
            raise RuntimeError('controller exited {} without result'.format(
                completed.returncode))
        return load_json(result_path)
    finally:
        stop_process(stage)
        stop_process(roscore)


def validate_result(spec, result, directory):
    anchor = spec['action_waypoints'][spec['core_action_start_index']]
    terminal = spec['canonical_terminal_gt_pose']
    branch_start_error = pose_error(result['branch_start_gt_pose'], terminal)
    treatment_start_error = pose_error(
        result['common_treatment_start_gt_pose'], anchor)
    planned = float(DOSES[spec['action_id']])
    actual = float(result['actual_cumulative_yaw_rad'])
    yaw_ok = (actual <= D0_YAW_MAX_RAD if spec['action_id'] == 'D0_ZERO'
              else abs(actual - planned) <= YAW_TOLERANCE_RAD)
    required = [
        'capture_spec.json', 'capture_result.json', 'probe_stream_raw.jsonl',
        'scientific_treatment_stream.jsonl', 'probe_gt_trajectory.txt',
        'pre_treatment_descriptor.json']
    checks = {
        'controller_status': result.get('status') == 'SUCCEEDED',
        'branch_start_position': (
            branch_start_error[0] <= START_POSITION_TOLERANCE_M),
        'branch_start_heading': (
            branch_start_error[1] <= START_HEADING_TOLERANCE_RAD),
        'common_anchor_position': treatment_start_error[0] <= 0.08,
        'common_theta0': (
            treatment_start_error[1] <= FINAL_HEADING_TOLERANCE_RAD),
        'exact_N': result.get('scientific_treatment_scan_count') == N_SCANS,
        'completion_before_N': 0 <= int(result.get(
            'completion_scan_index', N_SCANS + 1)) < N_SCANS,
        'minimum_completion_margin': int(result.get(
            'completion_margin', -1)) >= MIN_COMPLETION_MARGIN,
        'exact_first_N': result.get('scientific_stream_exact_first_N') is True,
        'no_duplicate_timestamp': result.get('duplicate_timestamp_count') == 0,
        'strict_timestamp_order': result.get(
            'nonmonotonic_timestamp_count') == 0,
        'actual_dose': yaw_ok,
        'final_heading': (float(result.get(
            'final_heading_residual_rad', math.inf)) <=
            FINAL_HEADING_TOLERANCE_RAD),
        'strict_pretreatment_descriptor': result.get(
            'pre_treatment_descriptor_strict') is True,
        'backend_not_started': result.get('backend_started') is False,
        'scientific_endpoint_not_read': result.get(
            'scientific_endpoint_read') is False,
        'required_files': all((directory / name).is_file()
                              for name in required),
    }
    return {
        'valid': all(checks.values()), 'checks': checks,
        'branch_start_position_error_m': branch_start_error[0],
        'branch_start_heading_error_rad': branch_start_error[1],
        'treatment_start_position_error_m': treatment_start_error[0],
        'treatment_start_heading_error_rad': treatment_start_error[1],
    }


def result_row(block, arm, result, validation, directory):
    return {
        'key': '{}:{}'.format(block['block'], arm),
        'target': block['target'], 'block': block['block'], 'arm': arm,
        'arm_position': block['arm_order'].index(arm) + 1,
        'planned_dose_rad': DOSES[arm],
        'actual_cumulative_yaw_rad': result['actual_cumulative_yaw_rad'],
        'actual_dose_error_rad': result['actual_dose_error_rad'],
        'maneuver_duration_s': result['maneuver_duration_s'],
        'moving_scan_count': result['moving_scan_count'],
        'completion_scan_index': result['completion_scan_index'],
        'completion_margin': result['completion_margin'],
        'mean_abs_angular_velocity_rad_s': result[
            'mean_abs_angular_velocity_rad_s'],
        'max_abs_angular_velocity_rad_s': result[
            'max_abs_angular_velocity_rad_s'],
        'final_heading_residual_rad': result['final_heading_residual_rad'],
        'treatment_path_length_m': result['treatment_path_length_m'],
        'scientific_treatment_scan_count': result[
            'scientific_treatment_scan_count'],
        'duplicate_timestamp_count': result['duplicate_timestamp_count'],
        'nonmonotonic_timestamp_count': result[
            'nonmonotonic_timestamp_count'],
        'scientific_stream_exact_first_N': result[
            'scientific_stream_exact_first_N'],
        'branch_start_position_error_m': validation[
            'branch_start_position_error_m'],
        'branch_start_heading_error_rad': validation[
            'branch_start_heading_error_rad'],
        'treatment_start_position_error_m': validation[
            'treatment_start_position_error_m'],
        'treatment_start_heading_error_rad': validation[
            'treatment_start_heading_error_rad'],
        'pre_treatment_descriptor_sha256': sha256(
            directory / 'pre_treatment_descriptor.json'),
        'backend_started': result['backend_started'],
        'scientific_endpoint_read': result['scientific_endpoint_read'],
        'technical_status': ('TECHNICALLY_VALID' if validation['valid'] else
                             'TECHNICALLY_INVALID'),
        'capture_dir': str(directory.relative_to(ROOT)),
    }


def state_path():
    return RESULT_ROOT / 'technical/controller_preflight_state.json'


def save_state(state):
    state['updated_utc'] = now()
    atomic_json(state_path(), state)


def live_worker():
    if not state_path().is_file():
        return None
    state = load_json(state_path())
    pid = state.get('worker_pid')
    if not pid or not (Path('/proc') / str(pid) / 'cmdline').is_file():
        return None
    command = (Path('/proc') / str(pid) / 'cmdline').read_bytes().replace(
        b'\0', b' ').decode(errors='replace')
    if 'context_disentangle_technical.py' not in command:
        return None
    return int(pid), int(state['worker_pgid'])


def verify_frozen_protocol():
    if not PROTOCOL_PATH.is_file():
        raise RuntimeError('CD-T protocol is not frozen')
    protocol = load_json(PROTOCOL_PATH)
    for relative, expected in protocol['code_hashes'].items():
        if sha256(ROOT / relative) != expected:
            raise RuntimeError('frozen CD-T code changed: {}'.format(relative))
    provenance = frozen_provenance()
    # HEAD changes only after this entire certification is committed.  During
    # collection it must remain the audited heterogeneity baseline.
    if not provenance['passed']:
        raise RuntimeError('frozen v14/v14-H provenance changed')
    return protocol


def _interval_overlap(left, right):
    left_min, left_max = min(left), max(left)
    right_min, right_max = min(right), max(right)
    intersection = max(0.0, min(left_max, right_max) -
                       max(left_min, right_min))
    smaller_width = min(left_max - left_min, right_max - right_min)
    if smaller_width == 0.0:
        fraction = 1.0 if (left_min <= right_min <= left_max or
                           right_min <= left_min <= right_max) else 0.0
    else:
        fraction = intersection / smaller_width
    return {
        'target_A_range': [left_min, left_max],
        'target_B_range': [right_min, right_max],
        'raw_ranges_overlap': intersection > 0.0 or bool(
            set(left) & set(right)),
        'overlap_fraction_of_smaller_range': fraction,
        'target_mean_absolute_difference': abs(
            statistics.mean(left) - statistics.mean(right)),
    }


def deconfounding_summary(rows):
    output = {'arms': {}}
    for arm in ARMS:
        by_target = {
            target: [float(row['actual_cumulative_yaw_rad']) for row in rows
                     if row['arm'] == arm and row['target'] == target]
            for target in TARGETS}
        completion = {
            target: [int(row['completion_scan_index']) for row in rows
                     if row['arm'] == arm and row['target'] == target]
            for target in TARGETS}
        dose = _interval_overlap(by_target['target_A'], by_target['target_B'])
        scans = _interval_overlap(completion['target_A'],
                                  completion['target_B'])
        dose_gate = (dose['raw_ranges_overlap'] and
                     dose['overlap_fraction_of_smaller_range'] >=
                     DOSE_OVERLAP_MIN_FRACTION and
                     dose['target_mean_absolute_difference'] <=
                     DOSE_MEAN_MATCH_TOLERANCE_RAD)
        scan_gate = scans['raw_ranges_overlap']
        output['arms'][arm] = {
            'actual_dose': dose, 'completion_scans': scans,
            'dose_overlap_gate': dose_gate,
            'completion_scan_overlap_gate': scan_gate,
        }
    output['dose_target_deconfounding_certified'] = all(
        value['dose_overlap_gate'] and value['completion_scan_overlap_gate']
        for value in output['arms'].values())
    output['machine_label'] = (
        'DOSE_TARGET_DECONFOUNDING_TECHNICALLY_CERTIFIED'
        if output['dose_target_deconfounding_certified'] else
        'DOSE_TARGET_DECONFOUNDING_FAILED')
    return output


def dose_monotonicity(rows):
    checks = []
    for block in sorted({row['block'] for row in rows}):
        values = {row['arm']: float(row['actual_cumulative_yaw_rad'])
                  for row in rows if row['block'] == block}
        passed = (set(values) == set(ARMS) and
                  values['D0_ZERO'] < values['D1_THRESHOLD'] <
                  values['D2_HIGH'])
        checks.append({'block': block, 'actual_doses': values,
                       'D0_lt_D1_lt_D2': passed})
    return {'checks': checks, 'passed': len(checks) == 8 and all(
        row['D0_lt_D1_lt_D2'] for row in checks)}


def forbidden_scientific_outputs():
    forbidden = []
    tokens = ('graph_pre', 'graph_final', 'branch_metrics',
              'primary_block_table', 'constraint_mechanism', 'backend_endpoint')
    capture_root = RESULT_ROOT / 'technical/captures'
    if capture_root.exists():
        for path in capture_root.rglob('*'):
            if path.is_file() and any(token in path.name for token in tokens):
                forbidden.append(str(path.relative_to(ROOT)))
    return forbidden


def finalize(state):
    rows = state['branches']
    deconfounding = deconfounding_summary(rows) if len(rows) == 24 else {
        'dose_target_deconfounding_certified': False,
        'machine_label': 'DOSE_TARGET_DECONFOUNDING_FAILED', 'arms': {}}
    monotonicity = dose_monotonicity(rows)
    forbidden = forbidden_scientific_outputs()
    controller_valid = (len(rows) == 24 and
                        len({row['key'] for row in rows}) == 24 and
                        all(row['technical_status'] == 'TECHNICALLY_VALID'
                            for row in rows))
    fixed_exposure = controller_valid and all(
        int(row['scientific_treatment_scan_count']) == N_SCANS and
        int(row['completion_margin']) >= MIN_COMPLETION_MARGIN
        for row in rows)
    no_endpoint = (not forbidden and all(
        row['backend_started'] is False and
        row['scientific_endpoint_read'] is False for row in rows))
    plan_frozen = all(path.is_file() for path in (
        RESULT_ROOT / 'design/sample_size_recommendation.json',
        RESULT_ROOT / 'design/future_statistical_analysis_plan.json',
        PROTOCOL_PATH))
    checks = {
        'controller_24_of_24_valid': controller_valid,
        'identical_start_final_heading_semantics': controller_valid and all(
            float(row['treatment_start_heading_error_rad']) <=
            FINAL_HEADING_TOLERANCE_RAD and
            float(row['final_heading_residual_rad']) <=
            FINAL_HEADING_TOLERANCE_RAD for row in rows),
        'fixed_N_and_minimum_margin': fixed_exposure,
        'dose_separation_monotonic': monotonicity['passed'],
        'target_dose_deconfounding': deconfounding[
            'dose_target_deconfounding_certified'],
        'primary_and_sample_size_plans_frozen': plan_frozen,
        'no_scientific_endpoint_produced': no_endpoint,
    }
    gate = ('CONTEXT_DISENTANGLEMENT_TECHNICALLY_READY'
            if all(checks.values()) else
            'CONTEXT_DISENTANGLEMENT_REDESIGN_REQUIRED')
    summary = {
        'status': 'CDT_TECHNICAL_PREFLIGHT_COMPLETE',
        'planned_branches': 24, 'completed_branches': len(rows),
        'technically_valid_branches': sum(
            row['technical_status'] == 'TECHNICALLY_VALID' for row in rows),
        'N': N_SCANS, 'minimum_completion_margin': MIN_COMPLETION_MARGIN,
        'observed_minimum_completion_margin': min(
            [int(row['completion_margin']) for row in rows], default=None),
        'dose_monotonicity': monotonicity,
        'target_dose_deconfounding': deconfounding,
        'forbidden_scientific_outputs': forbidden,
        'backend_started': False, 'scientific_endpoint_produced': not no_endpoint,
        'rows': rows,
    }
    write_csv(RESULT_ROOT / 'technical/controller_preflight.csv', rows)
    atomic_json(RESULT_ROOT / 'technical/controller_preflight_summary.json',
                summary)
    atomic_json(RESULT_ROOT / 'technical/target_dose_deconfounding.json',
                deconfounding)
    decision = {
        'protocol_id': PROTOCOL_ID, 'gate': gate, 'checks': checks,
        'formal_scientific_gate_unchanged': 'V14_PROSPECTIVE_NO_SUPPORT',
        'universal_broad_sweep_hypothesis': 'STOPPED',
        'scientific_experiment_started': False,
        'scientific_backend_endpoint_produced': not no_endpoint,
        'no_context_disentanglement_scientific_experiment_was_started': True,
        'frozen_provenance_after': frozen_provenance(),
    }
    atomic_json(RESULT_ROOT / 'decision/CDT_gate.json', decision)
    state['status'] = gate
    state['completed_utc'] = now()
    state.pop('worker_pid', None)
    state.pop('worker_pgid', None)
    save_state(state)
    return decision


def collect():
    verify_frozen_protocol()
    protocol_hash = sha256(PROTOCOL_PATH)
    if state_path().exists():
        state = load_json(state_path())
    else:
        state = {
            'protocol_id': PROTOCOL_ID,
            'protocol_sha256': protocol_hash,
            'status': 'PLANNED', 'created_utc': now(), 'branches': [],
            'backend_started': False, 'scientific_endpoint_read': False,
        }
    if state['protocol_sha256'] != protocol_hash:
        raise RuntimeError('frozen protocol hash changed')
    state.update(status='RUNNING', worker_pid=os.getpid(),
                 worker_pgid=os.getpgrp(),
                 started_utc=state.get('started_utc', now()))
    save_state(state)
    completed = {row['key'] for row in state['branches']}
    try:
        for block in block_rows():
            for arm in block['arm_order']:
                key = '{}:{}'.format(block['block'], arm)
                if key in completed:
                    continue
                spec = controlled_spec(block['target'], block['index'], arm)
                directory = (RESULT_ROOT / 'technical/captures' /
                             block['target'] / 'H{}'.format(block['index']) / arm)
                try:
                    result = run_stage_capture(spec, directory)
                    validation = validate_result(spec, result, directory)
                    atomic_json(directory / 'technical_validation.json', validation)
                    row = result_row(block, arm, result, validation, directory)
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    directory.mkdir(parents=True, exist_ok=True)
                    atomic_json(directory / 'TECHNICAL_FAILURE.json', {
                        'status': 'CONTROLLER_EXCEPTION',
                        'reason': '{}: {}'.format(type(exc).__name__, exc),
                        'traceback': traceback.format_exc(),
                        'automatic_retry': False,
                    })
                    row = {
                        'key': key, 'target': block['target'],
                        'block': block['block'], 'arm': arm,
                        'arm_position': block['arm_order'].index(arm) + 1,
                        'planned_dose_rad': DOSES[arm],
                        'technical_status': 'CONTROLLER_EXCEPTION',
                        'reason': '{}: {}'.format(type(exc).__name__, exc),
                        'backend_started': False,
                        'scientific_endpoint_read': False,
                        'capture_dir': str(directory.relative_to(ROOT)),
                    }
                state['branches'].append(row)
                completed.add(key)
                save_state(state)
        return finalize(state)
    except KeyboardInterrupt:
        state['status'] = 'INTERRUPTED'
        state['interrupted_utc'] = now()
        state.pop('worker_pid', None)
        state.pop('worker_pgid', None)
        save_state(state)
        return {'gate': 'INTERRUPTED'}


def main():
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(
        KeyboardInterrupt()))
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('run', 'start', 'status', 'stop'))
    args = parser.parse_args()
    if args.command == 'run':
        output = collect()
    elif args.command == 'start':
        if live_worker():
            raise SystemExit('verified CD-T worker already live')
        verify_frozen_protocol()
        log = open(RESULT_ROOT / 'technical/controller_preflight.log',
                   'a', buffering=1)
        command = ['/usr/bin/python3', str(Path(__file__).resolve()), 'run']
        process = subprocess.Popen(
            command, cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT,
            text=True, start_new_session=True)
        atomic_json(RESULT_ROOT / 'technical/launcher.json', {
            'pid': process.pid, 'pgid': process.pid,
            'command': command, 'started_utc': now()})
        output = {'status': 'STARTED', 'pid': process.pid}
    elif args.command == 'status':
        state = load_json(state_path()) if state_path().is_file() else {
            'status': 'NOT_STARTED', 'branches': []}
        output = {
            'status': state['status'], 'live_worker': bool(live_worker()),
            'completed_branches': len(state.get('branches', [])),
            'valid_branches': sum(row.get('technical_status') ==
                                  'TECHNICALLY_VALID'
                                  for row in state.get('branches', [])),
            'updated_utc': state.get('updated_utc'),
        }
    else:
        worker = live_worker()
        if not worker:
            raise SystemExit('no verified CD-T worker')
        os.killpg(worker[1], signal.SIGINT)
        output = {'status': 'SIGINT_SENT', 'pgid': worker[1]}
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
