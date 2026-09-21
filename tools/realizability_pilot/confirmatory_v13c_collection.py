#!/usr/bin/python3
"""No-peeking, resumable collection worker for v13-C."""

import argparse
import csv
import json
import os
import signal
import subprocess
import time
import traceback
from pathlib import Path

from confirmatory_v13c_protocol import (
    ARM_ORDERS, ARMS, BUDGET_GATES, MAX_CAPTURE_ATTEMPTS,
    MAX_PREFIX_ATTEMPTS, PREREGISTRATION_PATH, PROTOCOL_ID, RESULT_ROOT,
    ROOT, START_HEADING_TOLERANCE_RAD, START_POSITION_TOLERANCE_M,
    action_specs, frozen_block_rows, prefix_reference_record, sha256,
    source_attempt, write_preregistration,
)
from controlled_branch_suite import (atomic_json, pose_error,
                                     run_stage_capture)
from run_pilot import activated_environment
from stitch_probe_stream import stitch
from v13_unified_replay import unified_replay


TERMINAL_BLOCK_STATUSES = {
    'COLLECTED', 'BUDGET_INVALID_FINAL', 'TECHNICAL_INVALID_CAPTURE_FINAL',
    'TECHNICAL_INVALID_PREFIX_FINAL', 'POST_TREATMENT_TECHNICAL_FAILURE',
    'TECHNICAL_INVALID_REPLAY_FINAL',
}


def load_json(path):
    return json.loads(Path(path).read_text())


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def state_path(root):
    return Path(root) / 'collection/collection_state.json'


def save_state(root, state):
    state['updated_utc'] = now()
    atomic_json(state_path(root), state)


def initial_state(protocol_hash):
    blocks = []
    for frozen in frozen_block_rows():
        target = frozen['block_id'].split('_H')[0]
        block_number = int(frozen['block_id'].split('_H')[1])
        blocks.append({
            'block_id': frozen['block_id'],
            'target_label': target,
            'seed': frozen['seed'],
            'arm_order': ARM_ORDERS[target][block_number - 1],
            'status': 'PENDING',
            'history_source': str(source_attempt(target, frozen['seed'])),
            'history_rerun': False,
            'branches': {},
        })
    return {
        'protocol_id': PROTOCOL_ID,
        'protocol_hash': protocol_hash,
        'status': 'PLANNED',
        'created_utc': now(),
        'blocks': blocks,
        'scientific_endpoints_read': [],
    }


def block_dir(root, block):
    return Path(root) / block['target_label'] / block['block_id'].split('_H')[1]


def _frozen_block(block):
    return next(row for row in frozen_block_rows()
                if row['block_id'] == block['block_id'])


def ensure_block_inputs(root, block):
    directory = block_dir(root, block)
    directory.mkdir(parents=True, exist_ok=True)
    specs, frozen = action_specs(_frozen_block(block))
    for path, payload in ((directory / 'action_specs.json', specs),
                          (directory / 'frozen_target.json', frozen)):
        if path.exists() and load_json(path) != payload:
            raise RuntimeError('frozen block input changed: {}'.format(path))
        if not path.exists():
            atomic_json(path, payload)
    reference = prefix_reference_record(_frozen_block(block))
    reference_path = directory / 'prefix_reference.json'
    if reference_path.exists() and load_json(reference_path) != reference:
        raise RuntimeError('prefix reference changed: {}'.format(reference_path))
    if not reference_path.exists():
        atomic_json(reference_path, reference)
    return directory, Path(block['history_source']), specs, reference


def resolve_capture(arm_directory):
    attempts = sorted(arm_directory.glob('raw_attempt_*'))
    for attempt in attempts:
        result_path = attempt / 'capture_result.json'
        if result_path.exists() and load_json(result_path).get('status') == 'SUCCEEDED':
            return attempt, load_json(result_path)
    return None, None


def capture_one(root, state, block, directory, specs, arm):
    arm_directory = directory / arm
    arm_directory.mkdir(parents=True, exist_ok=True)
    successful_dir, result = resolve_capture(arm_directory)
    if successful_dir is None:
        attempt_number = len(list(arm_directory.glob('raw_attempt_*'))) + 1
        if attempt_number > MAX_CAPTURE_ATTEMPTS:
            raise RuntimeError('capture technical attempt cap exceeded')
        successful_dir = arm_directory / 'raw_attempt_{:02d}'.format(
            attempt_number)
        spec = dict(specs['common'], **specs['actions'][arm],
                    calibration_only=False,
                    protocol_role='v13C_locked_confirmatory_capture')
        try:
            result = run_stage_capture(
                activated_environment(), spec, successful_dir)
        except Exception as exc:
            successful_dir.mkdir(parents=True, exist_ok=True)
            atomic_json(successful_dir / 'CAPTURE_TECHNICAL_FAILURE.json', {
                'status': 'CAPTURE_TECHNICAL_FAILURE',
                'reason': '{}: {}'.format(type(exc).__name__, exc),
                'traceback': traceback.format_exc(),
                'recorded_utc': now(),
            })
            raise

    terminal = specs['common']['canonical_terminal_gt_pose']
    error = pose_error(result['branch_start_gt_pose'], terminal)
    start_passed = (error[0] <= START_POSITION_TOLERANCE_M and
                    error[1] <= START_HEADING_TOLERANCE_RAD)
    result.update({
        'branch_start_deviation_position_m': error[0],
        'branch_start_deviation_heading_rad': error[1],
        'branch_start_gate_passed': start_passed,
    })
    atomic_json(successful_dir / 'capture_result.json', result)
    if not start_passed:
        raise RuntimeError('branch-start gate failed')
    block['branches'][arm] = {
        'status': 'CAPTURED',
        'capture_dir': str(successful_dir),
        'capture_attempt_count': len(list(arm_directory.glob('raw_attempt_*'))),
        'distance_m': float(result['actual_distance_m']),
        'duration_s': float(result['actual_duration_s']),
        'raw_scan_count': int(result['raw_scan_count']),
        'start_position_error_m': error[0],
        'start_heading_error_rad': error[1],
    }
    save_state(root, state)


def budget_gate(block):
    rows = [block['branches'][arm] for arm in ARMS]
    distances = [row['distance_m'] for row in rows]
    durations = [row['duration_s'] for row in rows]
    scans = [row['raw_scan_count'] for row in rows]
    mean_scans = sum(scans) / float(len(scans))
    observed = {
        'distance_range_m': max(distances) - min(distances),
        'time_range_s': max(durations) - min(durations),
        'raw_scan_relative_range': (max(scans) - min(scans)) / mean_scans,
    }
    passed = (
        observed['distance_range_m'] <=
        BUDGET_GATES['pairwise_distance_range_m_max'] and
        observed['time_range_s'] <=
        BUDGET_GATES['pairwise_time_range_s_max'] and
        observed['raw_scan_relative_range'] <=
        BUDGET_GATES['raw_scan_relative_range_max'])
    return {'passed': passed, 'observed': observed,
            'thresholds': BUDGET_GATES,
            'variables_used': ['distance', 'duration', 'raw scan count'],
            'scientific_variables_used': []}


def prepare_combined(directory, block, arm, reference):
    arm_directory = directory / arm
    combined = arm_directory / 'combined_stream.jsonl'
    stitch_path = arm_directory / 'stitch_report.json'
    capture = Path(block['branches'][arm]['capture_dir'])
    prefix = ROOT / reference['canonical_prefix_path']
    if not combined.exists():
        report = stitch(prefix, capture / 'probe_stream_raw.jsonl', combined)
        atomic_json(stitch_path, report)
    else:
        report = load_json(stitch_path)
    if not report['prefix_byte_identical']:
        raise RuntimeError('combined stream prefix is not byte-identical')
    if report['prefix_hash'] != reference['canonical_prefix_sha256']:
        raise RuntimeError('combined prefix hash differs from frozen reference')
    return combined, report


def _suffix_started(replay_directory):
    path = replay_directory / 'publisher_suffix_status.json'
    if not path.exists():
        return False
    try:
        return int(load_json(path).get('published', 0)) > 0
    except Exception:
        return True


def replay_one(root, state, block, directory, history, arm, reference):
    branch = block['branches'][arm]
    combined, report = prepare_combined(directory, block, arm, reference)
    branch['combined_prefix_sha256'] = report['combined_prefix_hash']
    branch['combined_prefix_byte_identical'] = report['prefix_byte_identical']
    arm_directory = directory / arm
    prior_attempts = branch.setdefault('prefix_replay_attempts', [])
    while len(prior_attempts) < MAX_PREFIX_ATTEMPTS:
        attempt_number = len(prior_attempts) + 1
        replay_directory = arm_directory / 'replay_attempt_{:02d}'.format(
            attempt_number)
        if replay_directory.exists():
            raise RuntimeError('refusing to overwrite {}'.format(
                replay_directory))
        try:
            result = unified_replay(
                ROOT / reference['canonical_prefix_path'],
                history / 'mapper_params.yaml', replay_directory,
                rate_hz=20.0, combined_path=combined,
                target_ids=reference['local_five_target_state_ids'],
                prefix_reference_path=ROOT /
                reference['prefix_reference_graph_path'])
        except Exception as exc:
            treated = _suffix_started(replay_directory)
            prior_attempts.append({
                'attempt': attempt_number,
                'status': ('POST_TREATMENT_TECHNICAL_FAILURE' if treated else
                           'TECHNICAL_INVALID_REPLAY_FINAL'),
                'suffix_started': treated,
                'reason': '{}: {}'.format(type(exc).__name__, exc),
                'replay_dir': str(replay_directory),
            })
            branch['status'] = prior_attempts[-1]['status']
            save_state(root, state)
            return False

        if result['status'] == 'TECHNICAL_INVALID_PREFIX_PRETREATMENT':
            if result['suffix_published']:
                raise AssertionError('failed prefix gate published suffix')
            prior_attempts.append({
                'attempt': attempt_number,
                'status': 'TECHNICAL_INVALID_PREFIX_PRETREATMENT',
                'suffix_started': False,
                'replay_dir': str(replay_directory),
            })
            branch['status'] = 'TECHNICAL_INVALID_PREFIX_PRETREATMENT'
            save_state(root, state)
            if attempt_number < MAX_PREFIX_ATTEMPTS:
                continue
            branch['status'] = 'TECHNICAL_INVALID_PREFIX_FINAL'
            save_state(root, state)
            return False

        required = [replay_directory / name for name in (
            'graph_pre.json', 'graph_final.json', 'unified_replay_result.json')]
        if not all(path.exists() for path in required):
            branch['status'] = 'POST_TREATMENT_TECHNICAL_FAILURE'
            prior_attempts.append({
                'attempt': attempt_number,
                'status': branch['status'],
                'suffix_started': True,
                'reason': 'required post-treatment artifact missing',
                'replay_dir': str(replay_directory),
            })
            save_state(root, state)
            return False
        prior_attempts.append({
            'attempt': attempt_number,
            'status': 'REPLAYED',
            'suffix_started': True,
            'replay_dir': str(replay_directory),
            'prefix_reference_exact': True,
        })
        branch['status'] = 'REPLAYED'
        branch['replay_dir'] = str(replay_directory)
        branch['prefix_reference_exact'] = True
        save_state(root, state)
        return True
    return False


def write_ledger(root, state):
    collection = Path(root) / 'collection'
    collection.mkdir(parents=True, exist_ok=True)
    rows = []
    for block in state['blocks']:
        budget = block.get('budget_gate', {})
        observed = budget.get('observed', {})
        branches = block.get('branches', {})
        rows.append({
            'block_id': block['block_id'],
            'target_label': block['target_label'],
            'seed': block['seed'],
            'status': block['status'],
            'budget_valid': budget.get('passed'),
            'distance_range_m': observed.get('distance_range_m'),
            'time_range_s': observed.get('time_range_s'),
            'raw_scan_relative_range': observed.get('raw_scan_relative_range'),
            **{arm + '_status': branches.get(arm, {}).get('status')
               for arm in ARMS},
        })
    atomic_json(collection / 'collection_ledger.json', rows)
    with open(collection / 'collection_ledger.csv', 'w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def collect(root=RESULT_ROOT):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    prereg = write_preregistration(root /
                                    'preregistration/v13C_preregistration.json')
    protocol_hash = sha256(root / 'preregistration/v13C_preregistration.json')
    if state_path(root).exists():
        state = load_json(state_path(root))
    else:
        state = initial_state(protocol_hash)
    if state.get('protocol_hash') != protocol_hash:
        raise RuntimeError('preregistration hash changed after collection began')
    state.update(status='RUNNING', worker_pid=os.getpid(),
                 worker_pgid=os.getpgrp(), started_utc=state.get(
                     'started_utc', now()))
    save_state(root, state)
    try:
        for block in state['blocks']:
            if block['status'] in TERMINAL_BLOCK_STATUSES:
                continue
            directory, history, specs, reference = ensure_block_inputs(root,
                                                                        block)
            block['status'] = 'CAPTURING'
            save_state(root, state)
            capture_failed = False
            for arm in block['arm_order']:
                if block['branches'].get(arm, {}).get('status') == 'CAPTURED':
                    continue
                while True:
                    try:
                        capture_one(root, state, block, directory, specs, arm)
                        break
                    except KeyboardInterrupt:
                        raise
                    except Exception as exc:
                        attempts = len(list((directory / arm).glob(
                            'raw_attempt_*')))
                        block['branches'][arm] = {
                            'status': 'CAPTURE_TECHNICAL_FAILURE',
                            'capture_attempt_count': attempts,
                            'last_reason': '{}: {}'.format(
                                type(exc).__name__, exc),
                        }
                        save_state(root, state)
                        if attempts >= MAX_CAPTURE_ATTEMPTS:
                            capture_failed = True
                            break
                if capture_failed:
                    break
            if capture_failed:
                block['status'] = 'TECHNICAL_INVALID_CAPTURE_FINAL'
                save_state(root, state)
                continue

            block['budget_gate'] = budget_gate(block)
            if not block['budget_gate']['passed']:
                block['status'] = 'BUDGET_INVALID_FINAL'
                save_state(root, state)
                continue
            block['status'] = 'REPLAYING'
            save_state(root, state)
            replay_failed = False
            for arm in block['arm_order']:
                if block['branches'][arm].get('status') == 'REPLAYED':
                    continue
                if not replay_one(root, state, block, directory, history, arm,
                                  reference):
                    replay_failed = True
                    break
            if replay_failed:
                statuses = {branch.get('status')
                            for branch in block['branches'].values()}
                if 'POST_TREATMENT_TECHNICAL_FAILURE' in statuses:
                    block['status'] = 'POST_TREATMENT_TECHNICAL_FAILURE'
                elif 'TECHNICAL_INVALID_PREFIX_FINAL' in statuses:
                    block['status'] = 'TECHNICAL_INVALID_PREFIX_FINAL'
                else:
                    block['status'] = 'TECHNICAL_INVALID_REPLAY_FINAL'
                save_state(root, state)
                continue
            block['status'] = 'COLLECTED'
            save_state(root, state)

        rows = write_ledger(root, state)
        complete = all(row['status'] == 'COLLECTED' for row in rows)
        lock_status = ('COLLECTION_LOCKED_CONFIRMATORY_COMPLETE' if complete
                       else 'COLLECTION_LOCKED_TECHNICALLY_INCOMPLETE')
        state['status'] = lock_status
        state['completed_utc'] = now()
        state.pop('worker_pid', None)
        state.pop('worker_pgid', None)
        save_state(root, state)
        atomic_json(root / 'COLLECTION_LOCKED.json', {
            'status': lock_status,
            'protocol_id': PROTOCOL_ID,
            'protocol_hash': protocol_hash,
            'planned_blocks': 8,
            'complete_blocks': sum(row['status'] == 'COLLECTED'
                                   for row in rows),
            'analysis_not_yet_run': True,
            'locked_utc': now(),
        })
        return 0
    except KeyboardInterrupt:
        state['status'] = 'INTERRUPTED'
        state['interrupted_utc'] = now()
        state.pop('worker_pid', None)
        state.pop('worker_pgid', None)
        save_state(root, state)
        return 130
    except Exception as exc:
        state['status'] = 'FAILED'
        state['reason'] = '{}: {}'.format(type(exc).__name__, exc)
        state['traceback'] = traceback.format_exc()
        state.pop('worker_pid', None)
        state.pop('worker_pgid', None)
        save_state(root, state)
        raise


def live_worker(root):
    path = state_path(root)
    if not path.exists():
        return None
    state = load_json(path)
    pid = state.get('worker_pid')
    if not pid or not (Path('/proc') / str(pid) / 'cmdline').exists():
        return None
    command = (Path('/proc') / str(pid) / 'cmdline').read_bytes().replace(
        b'\0', b' ').decode(errors='replace')
    if 'confirmatory_v13c_collection.py' not in command:
        return None
    return int(pid), int(state['worker_pgid'])


def main():
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(
        KeyboardInterrupt()))
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('plan', 'run', 'start', 'status',
                                           'stop'))
    parser.add_argument('--root', type=Path, default=RESULT_ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == 'plan':
        payload = write_preregistration(
            root / 'preregistration/v13C_preregistration.json')
        print(json.dumps({
            'status': 'PREREGISTERED',
            'protocol_id': payload['protocol_id'],
            'planned_blocks': payload['planned_blocks'],
            'planned_branches': payload['planned_branches'],
            'analysis_hash': payload['code_hashes'][
                'tools/realizability_pilot/confirmatory_v13c_analysis.py'],
        }, indent=2, sort_keys=True))
    elif args.command == 'run':
        raise SystemExit(collect(root))
    elif args.command == 'start':
        root.mkdir(parents=True, exist_ok=True)
        (root / 'collection').mkdir(parents=True, exist_ok=True)
        if live_worker(root):
            raise SystemExit('verified v13-C worker already live')
        write_preregistration(root /
                              'preregistration/v13C_preregistration.json')
        log = open(root / 'collection/collection.log', 'a', buffering=1)
        command = ['/usr/bin/python3', str(Path(__file__).resolve()), 'run',
                   '--root', str(root)]
        process = subprocess.Popen(
            command, cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT,
            text=True, start_new_session=True)
        atomic_json(root / 'collection/launcher.json', {
            'pid': process.pid, 'pgid': process.pid, 'command': command,
            'started_utc': now()})
        print(json.dumps({'status': 'STARTED', 'pid': process.pid,
                          'root': str(root)}, indent=2))
    elif args.command == 'status':
        state = load_json(state_path(root)) if state_path(root).exists() else {
            'status': 'NOT_STARTED', 'blocks': []}
        counts = {}
        for block in state.get('blocks', []):
            counts[block['status']] = counts.get(block['status'], 0) + 1
        print(json.dumps({
            'status': state['status'],
            'live_worker': bool(live_worker(root)),
            'block_counts': counts,
            'updated_utc': state.get('updated_utc'),
        }, indent=2, sort_keys=True))
    else:
        worker = live_worker(root)
        if not worker:
            raise SystemExit('no verified v13-C worker')
        os.killpg(worker[1], signal.SIGINT)
        print('sent SIGINT to verified v13-C worker group {}'.format(
            worker[1]))


if __name__ == '__main__':
    main()
