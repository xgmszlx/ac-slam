#!/usr/bin/python3
"""No-peeking, resumable collection worker for the v12 experiment.

The collection state deliberately contains only preregistered engineering
fields.  Backend outcomes are written by the replay process but are not read or
summarised until ``COLLECTION_COMPLETE`` exists and the separate analysis
program is invoked.
"""

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

from branch_replay import replay_branch
from common_prefix_replay import replay as replay_prefix
from controlled_branch_suite import atomic_json, pose_error, run_stage_capture
from normalize_replay_timestamps import normalize
from run_pilot import activated_environment, run_episode
from stitch_probe_stream import stitch
from confirmatory_v12_protocol import (
    ARM_ORDERS, ARMS, BUDGET_GATES, MAX_BRANCH_ATTEMPTS,
    MAX_HISTORY_ATTEMPTS_PER_SEED, PRIMARY_SEEDS, PROTOCOL_ID, RESERVE_SEEDS,
    RESULT_ROOT, START_HEADING_TOLERANCE_RAD, START_POSITION_TOLERANCE_M,
    action_specs, freeze_target, history_spec, preregistration_payload,
    sha256, write_initial_preregistration,
)


def load_json(path):
    return json.loads(Path(path).read_text())


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def calibration_source():
    return (RESULT_ROOT.parents[0] / 'p1_common_prefix_v9_20260917' /
            'canonical_history/episodes/0001_v9_canonical_history_anchor_01/'
            'attempt_01')


def v10_metrics():
    root = RESULT_ROOT.parents[0] / 'p1_dwell_control_v10_20260917/branches'
    rows = []
    for arm in ('A1_dwell', 'A2_sweep90'):
        data = load_json(root / arm / 'raw/capture_result.json')
        rows.append({'arm': arm, 'distance_m': data['actual_distance_m'],
                     'duration_s': data['actual_duration_s'],
                     'raw_scan_count': data['raw_scan_count']})
    return rows


def run_calibration(root):
    prereg = root / 'preregistration'
    prereg.mkdir(parents=True, exist_ok=True)
    final_path = prereg / 'a3_budget_calibration.json'
    if final_path.exists():
        return load_json(final_path)
    source = calibration_source()
    frozen_path = prereg / 'calibration_target.json'
    if not frozen_path.exists():
        freeze_target(source, 'target_A', frozen_path)
    frozen = load_json(frozen_path)
    initial_dwell = 3.2
    specs = action_specs(source, frozen, initial_dwell)
    spec = dict(specs['common'], **specs['actions']['A3_MIN_TRIGGER'],
                calibration_only=False,
                protocol_role='outcome_blind_A3_budget_calibration')
    plan = {
        'status': 'CALIBRATION_PLANNED', 'initial_dwell_s': initial_dwell,
        'allowed_observables': ['GT distance', 'duration', 'raw scan count',
                                'yaw trajectory', 'start pose'],
        'forbidden_observables': ['Karto keyscans', 'constraints', 'utility',
                                  'posterior'],
        'reference_arms': v10_metrics(),
        'selection_rule': ('selected dwell = initial dwell + mean v10 A1/A2 '
                           'duration - observed calibration duration, rounded '
                           'to 0.1 s and clipped at zero'),
        'single_physical_calibration': True,
    }
    atomic_json(prereg / 'a3_budget_calibration_plan.json', plan)
    capture_dir = root / 'calibration/A3_single'
    if (capture_dir / 'capture_result.json').exists():
        result = load_json(capture_dir / 'capture_result.json')
    else:
        result = run_stage_capture(activated_environment(), spec, capture_dir)
    allowed = {'distance_m': float(result['actual_distance_m']),
               'duration_s': float(result['actual_duration_s']),
               'raw_scan_count': int(result['raw_scan_count']),
               'yaw_excursion_rad': float(result['actual_yaw_excursion_rad']),
               'branch_start_gt_pose': result['branch_start_gt_pose']}
    references = plan['reference_arms']
    target_duration = sum(row['duration_s'] for row in references) / 2.0
    selected = max(0.0, round(
        initial_dwell + target_duration - allowed['duration_s'], 1))
    decision = dict(plan, status='CALIBRATION_COMPLETE',
                    observed_allowed_metrics=allowed,
                    target_duration_s=target_duration,
                    selected_a3_dwell_s=selected,
                    backend_was_not_launched=True,
                    science_outcomes_inspected=False,
                    completed_utc=now())
    atomic_json(final_path, decision)
    return decision


def initial_state(root):
    blocks = []
    for target_label in ('target_A', 'target_B'):
        for index, seed in enumerate(PRIMARY_SEEDS[target_label]):
            blocks.append({
                'block_id': '{}_H{}'.format(target_label, index + 1),
                'target_label': target_label, 'planned_seed': seed,
                'active_seed': seed, 'reserve_seeds': RESERVE_SEEDS[target_label],
                'reserve_cursor': 0, 'arm_order': ARM_ORDERS[target_label][index],
                'status': 'PENDING', 'history_attempts': [], 'branches': {},
            })
    return {'protocol_id': PROTOCOL_ID, 'status': 'PLANNED',
            'created_utc': now(), 'blocks': blocks}


def state_path(root):
    return root / 'collection_state.json'


def save_state(root, state):
    state['updated_utc'] = now()
    atomic_json(state_path(root), state)


def existing_successful_history(block_dir):
    for attempt in sorted((block_dir / 'history').glob('attempt_*')):
        run_state = attempt / 'run_state.json'
        if (run_state.exists() and
                load_json(run_state).get('status') == 'SUCCEEDED' and
                not (attempt / 'TECHNICAL_INVALID_HISTORY.json').exists()):
            return attempt
    return None


def run_history(root, block, state):
    block_dir = root / block['target_label'] / block['block_id'].split('_')[-1]
    block_dir.mkdir(parents=True, exist_ok=True)
    successful = existing_successful_history(block_dir)
    if successful is not None:
        frozen_path = block_dir / 'frozen_target.json'
        if not frozen_path.exists():
            freeze_target(successful, block['target_label'], frozen_path)
        normalized = block_dir / 'canonical_prefix.jsonl'
        if not normalized.exists():
            report = normalize(successful / 'replay_stream.jsonl', normalized)
            atomic_json(block_dir / 'prefix_normalization.json', report)
        replay_path = block_dir / 'canonical_replay/common_prefix_replay_result.json'
        if replay_path.exists():
            replay = load_json(replay_path)
        else:
            replay = replay_prefix(
                normalized, successful / 'mapper_params.yaml', frozen_path,
                block_dir / 'canonical_replay', runs=2, rate_hz=20.0)
        if not replay['exact_identity']:
            raise RuntimeError('canonical history replay not exact')
        block['canonical_prefix_hash'] = replay['preprobe_graph_hashes'][0]
        block['history_status'] = 'VALID'
        if not any(row.get('status') == 'SUCCEEDED'
                   and Path(row.get('dir', '')) == successful
                   for row in block['history_attempts']):
            block['history_attempts'].append({
                'attempt': len(block['history_attempts']) + 1,
                'seed': block['active_seed'], 'status': 'SUCCEEDED',
                'dir': str(successful),
                'prefix_hash': replay['preprobe_graph_hashes'][0]})
        save_state(root, state)
        return block_dir, successful
    while True:
        seed = block['active_seed']
        failures_for_seed = sum(row['seed'] == seed for row in block['history_attempts'])
        if failures_for_seed >= MAX_HISTORY_ATTEMPTS_PER_SEED:
            # Reserve seeds are a target-level ordered pool, not a private copy
            # per block.  A reserve already consumed by any sibling block can
            # never be reused as another independent canonical history.
            target_reserves = list(RESERVE_SEEDS[block['target_label']])
            used_reserves = {
                sibling.get('active_seed') for sibling in state['blocks']
                if sibling['target_label'] == block['target_label'] and
                sibling.get('active_seed') in target_reserves
            }
            available = [value for value in target_reserves
                         if value not in used_reserves]
            if not available:
                block['status'] = 'PROTOCOL_NOT_ROBUST'
                save_state(root, state)
                raise RuntimeError('reserve histories exhausted for {}'.format(
                    block['block_id']))
            block['active_seed'] = available[0]
            block['reserve_cursor'] = target_reserves.index(available[0]) + 1
            continue
        attempt_number = len(block['history_attempts']) + 1
        attempt = block_dir / 'history/attempt_{:02d}'.format(attempt_number)
        episode_id = 'v12_{}_s{}'.format(block['block_id'], seed)
        try:
            run_episode(history_spec(block['target_label'], seed, episode_id),
                        attempt, activated_environment(), 2700)
            frozen_path = block_dir / 'frozen_target.json'
            freeze_target(attempt, block['target_label'], frozen_path)
            normalized = block_dir / 'canonical_prefix.jsonl'
            report = normalize(attempt / 'replay_stream.jsonl', normalized)
            atomic_json(block_dir / 'prefix_normalization.json', report)
            replay = replay_prefix(
                normalized, attempt / 'mapper_params.yaml', frozen_path,
                block_dir / 'canonical_replay', runs=2, rate_hz=20.0)
            if not replay['exact_identity']:
                raise RuntimeError('canonical history replay not exact')
            block['history_attempts'].append({
                'attempt': attempt_number, 'seed': seed, 'status': 'SUCCEEDED',
                'dir': str(attempt),
                'prefix_hash': replay['preprobe_graph_hashes'][0]})
            block['canonical_prefix_hash'] = replay['preprobe_graph_hashes'][0]
            block['history_status'] = 'VALID'
            save_state(root, state)
            return block_dir, attempt
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            if attempt.exists():
                atomic_json(attempt / 'TECHNICAL_INVALID_HISTORY.json', {
                    'status': 'TECHNICAL_INVALID_HISTORY',
                    'reason': '{}: {}'.format(type(exc).__name__, exc),
                    'recorded_utc': now()})
            block['history_attempts'].append({
                'attempt': attempt_number, 'seed': seed,
                'status': 'TECHNICAL_INVALID_HISTORY',
                'reason': '{}: {}'.format(type(exc).__name__, exc),
                'dir': str(attempt)})
            block['history_status'] = 'TECHNICAL_INVALID_HISTORY'
            save_state(root, state)


def resolve_capture_dir(arm_dir):
    for candidate in sorted(arm_dir.glob('raw_attempt_*')):
        path = candidate / 'capture_result.json'
        if path.exists() and load_json(path).get('status') == 'SUCCEEDED':
            return candidate, True
    index = len(list(arm_dir.glob('raw_attempt_*'))) + 1
    return arm_dir / 'raw_attempt_{:02d}'.format(index), False


def capture_arm(root, state, block, block_dir, attempt, arm, specs):
    arm_dir = block_dir / arm
    arm_dir.mkdir(parents=True, exist_ok=True)
    capture_dir, complete = resolve_capture_dir(arm_dir)
    if complete:
        result = load_json(capture_dir / 'capture_result.json')
    else:
        prior = len(list(arm_dir.glob('raw_attempt_*')))
        if prior >= MAX_BRANCH_ATTEMPTS:
            raise RuntimeError('branch technical attempt cap exceeded')
        spec = dict(specs['common'], **specs['actions'][arm],
                    calibration_only=False, protocol_role='v12_formal_branch')
        result = run_stage_capture(activated_environment(), spec, capture_dir)
    terminal = specs['common']['canonical_terminal_gt_pose']
    error = pose_error(result['branch_start_gt_pose'], terminal)
    passed = (error[0] <= START_POSITION_TOLERANCE_M and
              error[1] <= START_HEADING_TOLERANCE_RAD)
    result.update({'branch_start_deviation_position_m': error[0],
                   'branch_start_deviation_heading_rad': error[1],
                   'branch_start_gate_passed': passed})
    atomic_json(capture_dir / 'capture_result.json', result)
    if not passed:
        raise RuntimeError('branch-start gate failed')
    block['branches'][arm] = {
        'status': 'CAPTURED', 'capture_dir': str(capture_dir),
        'distance_m': float(result['actual_distance_m']),
        'duration_s': float(result['actual_duration_s']),
        'raw_scan_count': int(result['raw_scan_count']),
        'start_position_error_m': error[0],
        'start_heading_error_rad': error[1],
    }
    save_state(root, state)
    return capture_dir


def budget_gate(block):
    rows = [block['branches'][arm] for arm in ARMS]
    distances = [row['distance_m'] for row in rows]
    durations = [row['duration_s'] for row in rows]
    scans = [row['raw_scan_count'] for row in rows]
    spread = ((max(scans) - min(scans)) / (sum(scans) / len(scans)))
    observed = {'distance_range_m': max(distances) - min(distances),
                'time_range_s': max(durations) - min(durations),
                'raw_scan_relative_range': spread}
    passed = (observed['distance_range_m'] <=
              BUDGET_GATES['pairwise_distance_range_m_max'] and
              observed['time_range_s'] <=
              BUDGET_GATES['pairwise_time_range_s_max'] and
              observed['raw_scan_relative_range'] <=
              BUDGET_GATES['raw_scan_relative_range_max'])
    return {'passed': passed, 'observed': observed,
            'thresholds': BUDGET_GATES}


def replay_arm(root, state, block, block_dir, attempt, arm):
    branch = block['branches'][arm]
    arm_dir = block_dir / arm
    replay_dir = arm_dir / 'replay'
    technical_attempts = branch.setdefault('technical_replay_attempts', [])
    for replay_attempt in range(len(technical_attempts) + 1, 3):
        if (replay_dir / 'branch_replay_result.json').exists():
            replay = load_json(replay_dir / 'branch_replay_result.json')
        else:
            capture_dir = Path(branch['capture_dir'])
            combined = arm_dir / 'combined_stream.jsonl'
            report = stitch(block_dir / 'canonical_prefix.jsonl',
                            capture_dir / 'probe_stream_raw.jsonl', combined)
            atomic_json(arm_dir / 'stitch_report.json', report)
            replay = replay_branch(
                combined, block_dir / 'canonical_prefix.jsonl',
                attempt / 'mapper_params.yaml', block_dir / 'frozen_target.json',
                replay_dir, rate_hz=20.0)
        observed_hash = replay['preprobe_signature']['preprobe_graph_hash']
        prefix_ok = (replay['prefix_stream_identical'] and
                     observed_hash == block['canonical_prefix_hash'])
        if prefix_ok:
            branch['prefix_hash'] = observed_hash
            branch['prefix_identity_passed'] = True
            branch['status'] = 'REPLAYED'
            save_state(root, state)
            return True
        preserved = arm_dir / 'replay_attempt_{:02d}_prefix_mismatch'.format(
            replay_attempt)
        if preserved.exists():
            raise RuntimeError('refusing to overwrite {}'.format(preserved))
        shutil.move(str(replay_dir), str(preserved))
        technical_attempts.append({
            'attempt': replay_attempt, 'status': 'TECHNICAL_INVALID_PREFIX',
            'failed_prefix_hash': observed_hash,
            'preserved_dir': str(preserved.relative_to(root))})
        branch['status'] = 'TECHNICAL_REPLAY_RETRY'
        save_state(root, state)
    branch['prefix_identity_passed'] = False
    branch['status'] = 'TECHNICAL_INVALID_PREFIX_FINAL'
    save_state(root, state)
    return False


def collect(root):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    initial_prereg = root / 'preregistration/v12_preregistration_initial.json'
    initial_prereg.parent.mkdir(parents=True, exist_ok=True)
    write_initial_preregistration(initial_prereg)
    calibration = run_calibration(root)
    final_prereg = root / 'preregistration/v12_preregistration.json'
    if not final_prereg.exists():
        atomic_json(final_prereg, preregistration_payload(
            calibration['selected_a3_dwell_s'], calibration))
    protocol_hash = sha256(final_prereg)
    if state_path(root).exists():
        state = load_json(state_path(root))
    else:
        state = initial_state(root)
        state['protocol_hash'] = protocol_hash
        save_state(root, state)
    if state.get('protocol_hash') != protocol_hash:
        raise RuntimeError('preregistration hash changed after collection began')
    state.update(status='RUNNING', worker_pid=os.getpid(),
                 worker_pgid=os.getpgrp(), started_utc=now())
    state.pop('reason', None)
    state.pop('interrupted_utc', None)
    save_state(root, state)
    try:
        for block in state['blocks']:
            if block['status'] in ('COLLECTED', 'COLLECTED_BUDGET_INVALID',
                                   'TECHNICAL_INVALID_BRANCH',
                                   'TECHNICAL_INVALID_PREFIX'):
                continue
            block['status'] = 'HISTORY'
            save_state(root, state)
            block_dir, attempt = run_history(root, block, state)
            frozen = load_json(block_dir / 'frozen_target.json')
            specs = action_specs(
                attempt, frozen, calibration['selected_a3_dwell_s'])
            atomic_json(block_dir / 'action_specs.json', specs)
            branch_failed = False
            for arm in block['arm_order']:
                if block['branches'].get(arm, {}).get('status') in (
                        'CAPTURED', 'REPLAYED'):
                    continue
                while True:
                    try:
                        capture_arm(root, state, block, block_dir, attempt,
                                    arm, specs)
                        break
                    except KeyboardInterrupt:
                        raise
                    except Exception as exc:
                        attempts = len(list((block_dir / arm).glob(
                            'raw_attempt_*')))
                        block['branches'][arm] = {
                            'status': 'TECHNICAL_ATTEMPT_FAILED',
                            'attempts': attempts,
                            'last_reason': '{}: {}'.format(
                                type(exc).__name__, exc)}
                        save_state(root, state)
                        if attempts >= MAX_BRANCH_ATTEMPTS:
                            branch_failed = True
                            break
                if branch_failed:
                    break
            if branch_failed:
                block['status'] = 'TECHNICAL_INVALID_BRANCH'
                save_state(root, state)
                continue
            block['budget_gate'] = budget_gate(block)
            save_state(root, state)
            for arm in block['arm_order']:
                if block['branches'][arm].get('status') == 'REPLAYED':
                    continue
                if not replay_arm(root, state, block, block_dir, attempt, arm):
                    branch_failed = True
                    break
            if branch_failed:
                block['status'] = 'TECHNICAL_INVALID_PREFIX'
                save_state(root, state)
                continue
            block['status'] = ('COLLECTED' if block['budget_gate']['passed']
                               else 'COLLECTED_BUDGET_INVALID')
            save_state(root, state)
        state['status'] = 'COLLECTION_COMPLETE'
        state['completed_utc'] = now()
        state.pop('worker_pid', None); state.pop('worker_pgid', None)
        save_state(root, state)
        atomic_json(root / 'COLLECTION_COMPLETE.json', {
            'status': 'COLLECTION_COMPLETE', 'protocol_hash': protocol_hash,
            'completed_utc': state['completed_utc'],
            'analysis_not_yet_run': True})
    except KeyboardInterrupt:
        state['status'] = 'INTERRUPTED'; state['interrupted_utc'] = now()
        state.pop('worker_pid', None); state.pop('worker_pgid', None)
        save_state(root, state)
        return 130
    except Exception as exc:
        state['status'] = 'FAILED'
        state['reason'] = '{}: {}'.format(type(exc).__name__, exc)
        state.pop('worker_pid', None); state.pop('worker_pgid', None)
        save_state(root, state)
        raise
    return 0


def live_worker(state):
    pid = state.get('worker_pid')
    if not pid or not (Path('/proc') / str(pid) / 'cmdline').exists():
        return None
    command = (Path('/proc') / str(pid) / 'cmdline').read_bytes().replace(
        b'\0', b' ').decode(errors='replace')
    if 'confirmatory_v12_collection.py' not in command:
        return None
    return int(pid), int(state['worker_pgid'])


def main():
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(
        KeyboardInterrupt()))
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest='command', required=True)
    for command in ('plan', 'calibrate', 'run', 'start', 'status', 'stop'):
        child = subs.add_parser(command)
        child.add_argument('--root', type=Path, default=RESULT_ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == 'plan':
        root.mkdir(parents=True, exist_ok=True)
        path = root / 'preregistration/v12_preregistration_initial.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = write_initial_preregistration(path)
        print(json.dumps({'status': 'PREREGISTERED', 'path': str(path),
                          'blocks': 8, 'branches': 24,
                          'protocol_id': payload['protocol_id']}, indent=2))
    elif args.command == 'calibrate':
        print(json.dumps(run_calibration(root), indent=2, sort_keys=True))
    elif args.command == 'run':
        raise SystemExit(collect(root))
    elif args.command == 'start':
        root.mkdir(parents=True, exist_ok=True)
        state = load_json(state_path(root)) if state_path(root).exists() else {}
        if live_worker(state):
            raise SystemExit('verified v12 worker already live')
        log = open(root / 'collection.log', 'a', buffering=1)
        command = ['/usr/bin/python3', str(Path(__file__).resolve()), 'run',
                   '--root', str(root)]
        process = subprocess.Popen(command, cwd=str(RESULT_ROOT.parents[2]),
                                   stdout=log, stderr=subprocess.STDOUT,
                                   text=True, start_new_session=True)
        atomic_json(root / 'launcher.json', {'pid': process.pid,
                    'command': command, 'started_utc': now()})
        print(json.dumps({'status': 'STARTED', 'pid': process.pid,
                          'root': str(root)}, indent=2))
    elif args.command == 'status':
        state = load_json(state_path(root)) if state_path(root).exists() else {
            'status': 'NOT_STARTED', 'blocks': []}
        counts = {}
        for block in state.get('blocks', []):
            counts[block['status']] = counts.get(block['status'], 0) + 1
        print(json.dumps({'status': state['status'],
                          'live_worker': bool(live_worker(state)),
                          'block_counts': counts,
                          'updated_utc': state.get('updated_utc')},
                         indent=2, sort_keys=True))
    else:
        state = load_json(state_path(root))
        worker = live_worker(state)
        if not worker:
            raise SystemExit('no verified v12 worker')
        os.killpg(worker[1], signal.SIGINT)
        print('sent SIGINT to verified worker group {}'.format(worker[1]))


if __name__ == '__main__':
    main()
