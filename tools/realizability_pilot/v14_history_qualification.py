#!/usr/bin/python3
"""Fresh, outcome-blind history qualification for v14.

This worker never launches an action branch and never computes a scientific
endpoint.  Every frozen candidate receives at most one history attempt.  The
first-four rule is applied only after the complete 32-candidate pool exists.
"""

import argparse
import csv
import json
import os
import signal
import subprocess
import time
import traceback
from pathlib import Path

from controlled_branch_suite import atomic_json
from normalize_replay_timestamps import normalize
from run_pilot import activated_environment, run_episode
from v13_prefix_equivalence import certify_repeatability, stream_sha
from v13_target_selector import select_block_local_target
from v13_unified_replay import unified_replay
from v14_confirmatory_protocol import (
    CANDIDATE_SEEDS, EXPECTED_MAPPER_BINARY_SHA256,
    EXPECTED_NORMALIZED_MAPPER_CONFIG_SHA256, FROZEN_ZERO_TOLERANCE,
    HISTORY_MANIFEST_PATH, PREFIX_RATE_HZ, PREFIX_REPEAT_COUNT, PROTOCOL_ID,
    PREREGISTRATION_PATH, RESULT_ROOT, ROOT, TARGET_IDS, TARGETS,
    candidate_dir, history_spec, load_json, sha256, source_attempt,
)


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def verify_preregistration():
    if not PREREGISTRATION_PATH.is_file():
        raise RuntimeError('v14 preregistration must be frozen before qualification')
    prereg = load_json(PREREGISTRATION_PATH)
    for relative, expected in prereg['code_hashes'].items():
        if sha256(ROOT / relative) != expected:
            raise RuntimeError('frozen v14 code changed: {}'.format(relative))
    return prereg, sha256(PREREGISTRATION_PATH)


def candidate_record(target, seed):
    directory = candidate_dir(target, seed)
    record_path = directory / 'technical_status.json'
    if record_path.exists():
        return load_json(record_path)
    attempt = source_attempt(target, seed)
    directory.mkdir(parents=True, exist_ok=True)
    record = {
        'target_label': target, 'target_id': TARGET_IDS[target],
        'seed': int(seed), 'attempt_count': 1, 'status': 'RUNNING',
        'started_utc': now(), 'failure_reasons': [],
        'action_branch_launched': False, 'scientific_endpoints_read': [],
    }
    atomic_json(record_path, record)
    try:
        if attempt.exists():
            state = load_json(attempt / 'run_state.json') \
                if (attempt / 'run_state.json').is_file() else {}
            if state.get('status') != 'SUCCEEDED':
                raise RuntimeError('partial history exists; one-attempt rule forbids rerun')
        else:
            env = activated_environment()
            env['ROS_LOG_DIR'] = str(attempt / 'ros_logs')
            run_episode(history_spec(target, seed), attempt, env, 1800)
        episode = load_json(attempt / 'episode_result.json')
        if (episode.get('status') != 'SUCCEEDED' or
                not episode.get('canonical_history_complete')):
            raise RuntimeError('canonical history route did not complete')
        raw_stream = attempt / 'replay_stream.jsonl'
        if not raw_stream.is_file():
            raise RuntimeError('history replay stream missing')
        prefix = directory / 'canonical_prefix.jsonl'
        normalization = normalize(raw_stream, prefix, period_s=0.1, start_s=0.0)
        atomic_json(directory / 'prefix_normalization.json', normalization)
        if int(normalization['output_record_count']) <= 0:
            raise RuntimeError('canonical prefix is empty')

        selection = select_block_local_target(attempt, target, TARGET_IDS[target])
        atomic_json(directory / 'block_local_target.json', selection)
        if not selection['selection_valid']:
            raise RuntimeError('five-state block-local selection invalid')

        graphs, replays = [], []
        for repeat in range(1, PREFIX_REPEAT_COUNT + 1):
            out = directory / 'prefix_replays/repeat_{:02d}'.format(repeat)
            replay = unified_replay(
                prefix, attempt / 'mapper_params.yaml', out,
                rate_hz=PREFIX_RATE_HZ,
                target_ids=selection['historical_scan_ids'])
            replays.append(replay)
            graphs.append(load_json(out / 'graph_pre.json'))
        repeatability = certify_repeatability(
            graphs, ['repeat_{:02d}'.format(i)
                     for i in range(1, PREFIX_REPEAT_COUNT + 1)])
        atomic_json(directory / 'prefix_repeatability.json', repeatability)
        if not repeatability['structural_exact_all_pairs']:
            raise RuntimeError('prefix structure is not exactly repeatable')
        if not repeatability['numerical_exact_all_pairs']:
            raise RuntimeError('prefix numerics are not exactly repeatable')
        if repeatability['frozen_numerical_tolerance'] != FROZEN_ZERO_TOLERANCE:
            raise RuntimeError('prefix repeatability did not use zero tolerance')
        config_hashes = {row['mapper_params_sha256'] for row in replays}
        binary_hashes = {row['code_provenance']['mapper_binary_sha256']
                         for row in replays}
        if config_hashes != {EXPECTED_NORMALIZED_MAPPER_CONFIG_SHA256}:
            raise RuntimeError('mapper normalized config differs from certified v14-T')
        if binary_hashes != {EXPECTED_MAPPER_BINARY_SHA256}:
            raise RuntimeError('mapper binary differs from certified v14-T')
        record.update({
            'status': 'TECHNICALLY_ELIGIBLE',
            'history_route_complete': True,
            'canonical_input_record_count': normalization['output_record_count'],
            'canonical_input_sha256': stream_sha(prefix)[0],
            'target_state_ids': [int(x) for x in selection['historical_scan_ids']],
            'target_unique_ids': [int(x) for x in selection['historical_unique_ids']],
            'target_state_count': int(selection['exact_state_count']),
            'target_states_distinct': bool(selection['distinct_states']),
            'target_states_strictly_ordered': bool(
                selection['strictly_ordered_states']),
            'anchor_state_id': int(selection['action_anchor']['id']),
            'prefix_replay_structural_exact': True,
            'prefix_replay_numerical_exact': True,
            'mapper_params_normalized_sha256': next(iter(config_hashes)),
            'mapper_binary_sha256': next(iter(binary_hashes)),
        })
    except KeyboardInterrupt:
        record.update(status='INTERRUPTED_NO_RETRY',
                      failure_reasons=['qualification worker interrupted'])
        atomic_json(record_path, record)
        raise
    except Exception as exc:
        record.update(status='TECHNICALLY_INELIGIBLE',
                      failure_reasons=['{}: {}'.format(type(exc).__name__, exc)],
                      traceback=traceback.format_exc())
    record['finished_utc'] = now()
    atomic_json(record_path, record)
    return record


def first_four_eligible(records, target):
    """Apply the first-four rule in frozen seed order."""
    by_seed = {int(row['seed']): row for row in records
               if row['target_label'] == target}
    return [by_seed[seed] for seed in CANDIDATE_SEEDS[target]
            if seed in by_seed and
            by_seed[seed]['status'] == 'TECHNICALLY_ELIGIBLE'][:4]


def write_ledgers(records, complete):
    qualification = RESULT_ROOT / 'qualification'
    qualification.mkdir(parents=True, exist_ok=True)
    targets = {}
    for target in TARGETS:
        rows = [r for r in records if r['target_label'] == target]
        eligible = [r for r in rows if r['status'] == 'TECHNICALLY_ELIGIBLE']
        targets[target] = {
            'evaluated_count': len(rows), 'eligible_count': len(eligible),
            'first_four_eligible_seeds': (
                [r['seed'] for r in first_four_eligible(records, target)]
                if complete else []),
        }
    ready = complete and all(targets[t]['eligible_count'] >= 4 for t in TARGETS)
    mutable = {
        'protocol_id': PROTOCOL_ID, 'pool_complete': bool(complete),
        'candidate_seeds': CANDIDATE_SEEDS, 'records': records,
        'targets': targets,
        'technical_gate': ('V14_HISTORY_QUALIFICATION_PASS' if ready else
                           'V14_PROSPECTIVE_TECHNICALLY_INCOMPLETE' if complete else
                           'HISTORY_QUALIFICATION_IN_PROGRESS'),
        'updated_utc': now(), 'scientific_endpoint_read': False,
    }
    atomic_json(qualification / 'history_eligibility_manifest.json', mutable)
    with open(qualification / 'history_qualification_ledger.csv', 'w',
              newline='') as stream:
        fields = ['target_label', 'target_id', 'seed', 'status',
                  'history_route_complete', 'canonical_input_record_count',
                  'target_state_count', 'prefix_replay_structural_exact',
                  'prefix_replay_numerical_exact', 'failure_reasons']
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in records:
            writer.writerow({key: (json.dumps(row.get(key)) if key ==
                                    'failure_reasons' else row.get(key))
                             for key in fields})
    if ready:
        selected = {}
        for target in TARGETS:
            eligible = first_four_eligible(records, target)
            selected[target] = [{
                'block_id': '{}_H{}'.format(target, index),
                'target_label': target, 'target_id': TARGET_IDS[target],
                'seed': row['seed'],
                'target_state_ids': row['target_state_ids'],
                'target_unique_ids': row['target_unique_ids'],
                'anchor_state_id': row['anchor_state_id'],
            } for index, row in enumerate(eligible, 1)]
        frozen = {
            'protocol_id': PROTOCOL_ID, 'pool_complete': True,
            'technical_gate': 'V14_HISTORY_QUALIFICATION_PASS',
            'selection_rule': 'first four eligible after complete pool',
            'selected_blocks': selected,
            'source_manifest_sha256': sha256(
                qualification / 'history_eligibility_manifest.json'),
            'frozen_utc': now(), 'reserve_substitution_allowed': False,
        }
        if HISTORY_MANIFEST_PATH.exists():
            existing = load_json(HISTORY_MANIFEST_PATH)
            if (existing.get('selected_blocks') != frozen['selected_blocks'] or
                    existing.get('technical_gate') != frozen['technical_gate']):
                raise RuntimeError('refusing to modify frozen history manifest')
        else:
            atomic_json(HISTORY_MANIFEST_PATH, frozen)
    return mutable


def collect():
    prereg, prereg_hash = verify_preregistration()
    records = []
    total = sum(len(v) for v in CANDIDATE_SEEDS.values())
    result = None
    for target in TARGETS:
        for seed in CANDIDATE_SEEDS[target]:
            records.append(candidate_record(target, seed))
            result = write_ledgers(records, len(records) == total)
    result['preregistration_sha256'] = prereg_hash
    return result


def launcher_state():
    launcher = RESULT_ROOT / 'qualification/launcher.json'
    payload = load_json(launcher) if launcher.exists() else {}
    pid = payload.get('pid')
    live = bool(pid and (Path('/proc') / str(pid) / 'cmdline').exists())
    manifest = RESULT_ROOT / 'qualification/history_eligibility_manifest.json'
    status = load_json(manifest) if manifest.exists() else {}
    return {'live_worker': live,
            'technical_gate': status.get('technical_gate', 'NOT_STARTED'),
            'evaluated': len(status.get('records', [])),
            'updated_utc': status.get('updated_utc')}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('run', 'start', 'status', 'stop'))
    args = parser.parse_args()
    if args.command == 'run':
        print(json.dumps(collect(), indent=2, sort_keys=True))
    elif args.command == 'start':
        if launcher_state()['live_worker']:
            raise SystemExit('v14 qualification worker already live')
        verify_preregistration()
        directory = RESULT_ROOT / 'qualification'
        directory.mkdir(parents=True, exist_ok=True)
        log = open(directory / 'qualification.log', 'a', buffering=1)
        command = ['/usr/bin/python3', str(Path(__file__).resolve()), 'run']
        process = subprocess.Popen(command, cwd=str(ROOT), stdout=log,
                                   stderr=subprocess.STDOUT,
                                   start_new_session=True, text=True)
        atomic_json(directory / 'launcher.json', {
            'pid': process.pid, 'pgid': process.pid, 'command': command,
            'started_utc': now()})
        print(json.dumps({'status': 'STARTED', 'pid': process.pid}, indent=2))
    elif args.command == 'status':
        print(json.dumps(launcher_state(), indent=2, sort_keys=True))
    else:
        launcher = load_json(RESULT_ROOT / 'qualification/launcher.json')
        if not launcher_state()['live_worker']:
            raise SystemExit('no verified v14 qualification worker')
        os.killpg(int(launcher['pgid']), signal.SIGINT)
        print('sent SIGINT to v14 qualification worker')


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(
        KeyboardInterrupt()))
    main()
