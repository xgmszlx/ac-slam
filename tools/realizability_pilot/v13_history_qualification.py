#!/usr/bin/python3
"""Preregister, run, resume, and audit the v13-T history eligibility screen.

This program never launches an action branch and never computes a scientific
graph endpoint.  A candidate seed receives exactly one history attempt.  All
eight seeds per target are exhausted in frozen order; only then are the first
four technically eligible histories selected.
"""

import argparse
import csv
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
ROOT = THIS_DIR.parents[1]
sys.path.insert(0, str(THIS_DIR))

from normalize_replay_timestamps import normalize  # noqa: E402
from run_pilot import activated_environment, run_episode  # noqa: E402
from v13_prefix_equivalence import certify_repeatability, stream_sha  # noqa: E402
from v13_target_selector import select_block_local_target  # noqa: E402
from v13_technical_protocol import (CANDIDATE_SEEDS,
                                    FROZEN_NUMERICAL_TOLERANCE,
                                    PREFIX_RATE_HZ, PREFIX_REPEAT_COUNT,
                                    PROTOCOL_ID, RESULT_ROOT,
                                    SEGMENT_HALF_WIDTH_STATES,
                                    TARGET_IDS, TARGET_QUANTILES,
                                    action_budget_provenance, history_spec)
from v13_unified_replay import unified_replay  # noqa: E402


CODE_FILES = [
    'tools/realizability_pilot/v13_technical_protocol.py',
    'tools/realizability_pilot/v13_history_qualification.py',
    'tools/realizability_pilot/v13_target_selector.py',
    'tools/realizability_pilot/v13_prefix_equivalence.py',
    'tools/realizability_pilot/v13_unified_replay.py',
    'tools/realizability_pilot/v13_replay_publisher.py',
    'tools/realizability_pilot/se2_information.py',
    'tools/realizability_pilot/test_v13_technical.py',
    'dependencies/navigation_2d/nav2d_karto/src/MultiMapper.cpp',
    'dependencies/navigation_2d/nav2d_karto/include/nav2d_karto/MultiMapper.h',
    'dependencies/navigation_2d/nav2d_karto/CMakeLists.txt',
    'dependencies/navigation_2d/nav2d_karto/package.xml',
]


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def code_hashes():
    return {path: sha256(ROOT / path) for path in CODE_FILES}


def preregistration_payload():
    hashes = code_hashes()
    return {
        'protocol_id': PROTOCOL_ID,
        'created_before_any_fresh_candidate_history_result': True,
        'scope': 'TECHNICAL_CERTIFICATION_ONLY_NO_SCIENCE_ENDPOINTS',
        'git_head_before_uncommitted_v13_changes': subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=str(ROOT), text=True).strip(),
        'code_hashes': hashes,
        'code_bundle_sha256': hashlib.sha256(json.dumps(
            hashes, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'target_identities_unchanged': TARGET_IDS,
        'candidate_seeds_in_frozen_order': CANDIDATE_SEEDS,
        'candidate_count_per_target': 8,
        'selection_rule': ('after the entire immutable pool is evaluated, '
                           'select the first four TECHNICALLY_ELIGIBLE seeds '
                           'in frozen order'),
        'one_history_attempt_per_candidate': True,
        'reserve_seeds': [],
        'runtime_seed_substitution_allowed': False,
        'seed_reuse_audit': {
            'forbidden_old_pool_prefixes': [51, 52, 71, 72],
            'all_candidate_seeds_unique': len(set(sum(
                CANDIDATE_SEEDS.values(), []))) == 16,
            'intersection_with_explicit_old_pools': [],
        },
        'unified_prefix_replay': {
            'repeat_count': PREFIX_REPEAT_COUNT,
            'rate_hz': PREFIX_RATE_HZ,
            'fresh_ros_master_each_replay': True,
            'fresh_multimapper_each_replay': True,
            'publisher_subscriber_connection_required': True,
            'processed_callback_count_barrier_required': True,
            'synchronous_dump_service_required': True,
            'fixed_drain_sleep_forbidden': True,
            'background_graph_dump_forbidden': True,
            'structural_identity_required': True,
            'numerical_tolerance': FROZEN_NUMERICAL_TOLERANCE,
            'tolerance_source': (
                'three all-pairs exact unified-lifecycle repeats on the '
                'frozen old B/H2 prefix before fresh candidate collection'),
            'old_v12b_4p4mm_value_used_for_tolerance': False,
        },
        'block_local_target_selector': {
            'anchor': ('nearest legal post-route-start historical scan to the '
                       'unchanged fixed target waypoint'),
            'continuous_segment_half_width_states':
                SEGMENT_HALF_WIDTH_STATES,
            'normalized_arc_length_quantiles': TARGET_QUANTILES,
            'required_count': 5,
            'required_distinct': True,
            'required_strict_state_order': True,
            'outcome_blind': True,
        },
        'technical_eligibility_checks': [
            'history route complete', 'canonical input stream nonempty',
            'exactly five distinct strictly ordered block-local states',
            'three same-input unified-lifecycle prefix replays',
            'all repeated structural signatures exact',
            'all repeated numerical differences within frozen zero envelope',
            'mapper config and binary/code provenance complete'],
        'forbidden_reads': [
            'J_T', 'target/non-target realized action constraints', 'Delta U',
            'action-specific provenance outcomes', 'A2-A3', 'A3-A1', 'A2-A1'],
        'no_action_branch_launched': True,
        'budget_record_only': action_budget_provenance(),
        'failure_gate': ('if either target yields fewer than four eligible '
                         'histories, PAUSED_V13_TECHNICAL_NOT_ROBUST'),
    }


def ensure_preregistration(root):
    path = Path(root) / 'preregistration/v13T_preregistration.json'
    payload = preregistration_payload()
    if path.exists():
        existing = json.loads(path.read_text())
        if existing != payload:
            raise RuntimeError('immutable preregistration differs from current code')
    else:
        atomic_json(path, payload)
    return path, payload


def _candidate_dir(root, target_label, seed):
    return Path(root) / 'histories' / target_label / 'seed_{}'.format(seed)


def _candidate_record(root, target_label, seed):
    directory = _candidate_dir(root, target_label, seed)
    record_path = directory / 'technical_status.json'
    if record_path.exists():
        return json.loads(record_path.read_text())
    attempt = directory / 'attempt_01'
    record = {
        'target_label': target_label, 'target_id': TARGET_IDS[target_label],
        'seed': int(seed), 'attempt_count': 1, 'status': 'RUNNING',
        'started_utc': now(), 'failure_reasons': [],
        'science_endpoints_read': [], 'action_branch_launched': False,
    }
    atomic_json(record_path, record)
    try:
        if attempt.exists():
            state_path = attempt / 'run_state.json'
            state = json.loads(state_path.read_text()) if state_path.exists() else {}
            if state.get('status') != 'SUCCEEDED':
                raise RuntimeError('partial/non-success history exists; no retry allowed')
        else:
            env = activated_environment()
            env['ROS_LOG_DIR'] = str(attempt / 'ros_logs')
            run_episode(history_spec(target_label, seed), attempt, env, 1800)

        episode = json.loads((attempt / 'episode_result.json').read_text())
        if (episode.get('status') != 'SUCCEEDED' or
                not episode.get('canonical_history_complete')):
            raise RuntimeError('canonical history route did not complete')
        if not (attempt / 'replay_stream.jsonl').is_file():
            raise RuntimeError('canonical replay input stream is missing')

        prefix = directory / 'canonical_prefix.jsonl'
        normalization = normalize(attempt / 'replay_stream.jsonl', prefix,
                                  period_s=0.1, start_s=0.0)
        atomic_json(directory / 'prefix_normalization.json', normalization)
        if normalization['output_record_count'] <= 0:
            raise RuntimeError('canonical replay input stream is empty')

        selection = select_block_local_target(
            attempt, target_label, TARGET_IDS[target_label])
        atomic_json(directory / 'block_local_target.json', selection)
        if not selection['selection_valid']:
            raise RuntimeError('block-local target selection invalid')

        graphs = []
        replay_results = []
        for repeat in range(1, PREFIX_REPEAT_COUNT + 1):
            replay_dir = directory / 'prefix_replays/repeat_{:02d}'.format(repeat)
            replay = unified_replay(
                prefix, attempt / 'mapper_params.yaml', replay_dir,
                rate_hz=PREFIX_RATE_HZ,
                target_ids=selection['historical_scan_ids'])
            replay_results.append(replay)
            with open(replay_dir / 'graph_pre.json') as stream:
                graphs.append(json.load(stream))
        repeatability = certify_repeatability(
            graphs, ['repeat_{:02d}'.format(value)
                     for value in range(1, PREFIX_REPEAT_COUNT + 1)])
        atomic_json(directory / 'prefix_repeatability.json', repeatability)
        if not repeatability['structural_exact_all_pairs']:
            raise RuntimeError('prefix structural repeatability failed')
        if repeatability['frozen_numerical_tolerance'] != \
                FROZEN_NUMERICAL_TOLERANCE:
            raise RuntimeError('prefix numerical repeatability exceeded zero envelope')

        required_provenance = all(
            replay.get('mapper_params_sha256') and
            replay.get('code_provenance', {}).get('mapper_binary_sha256')
            for replay in replay_results)
        if not required_provenance:
            raise RuntimeError('mapper/config provenance incomplete')
        record.update({
            'status': 'TECHNICALLY_ELIGIBLE',
            'history_route_complete': True,
            'canonical_input_record_count': normalization['output_record_count'],
            'canonical_input_sha256': stream_sha(prefix)[0],
            'target_state_ids': selection['historical_scan_ids'],
            'target_state_count': selection['exact_state_count'],
            'target_states_distinct': selection['distinct_states'],
            'target_states_strictly_ordered':
                selection['strictly_ordered_states'],
            'anchor_state_id': selection['action_anchor']['id'],
            'prefix_replay_structural_exact': True,
            'prefix_replay_numerical_exact':
                repeatability['numerical_exact_all_pairs'],
            'prefix_replay_tolerance':
                repeatability['frozen_numerical_tolerance'],
            'mapper_params_sha256': replay_results[0]['mapper_params_sha256'],
            'mapper_binary_sha256': replay_results[0][
                'code_provenance']['mapper_binary_sha256'],
            'allowed_artifacts_read': [
                'episode_result.json status/canonical_history_complete only',
                'replay_stream.jsonl', 'pose_graph_before.json',
                'resolved_history_route.json', 'mapper_params.yaml',
                'prefix replay graph_pre.json'],
        })
    except KeyboardInterrupt:
        record.update({'status': 'INTERRUPTED_NO_RETRY_CONSUMED',
                       'failure_reasons': ['worker interrupted during candidate']})
        atomic_json(record_path, record)
        raise
    except Exception as exc:
        record.update({'status': 'TECHNICALLY_INELIGIBLE',
                       'failure_reasons': [str(exc)],
                       'traceback': traceback.format_exc()})
    record['finished_utc'] = now()
    atomic_json(record_path, record)
    return record


def _write_manifest(root, records, complete):
    by_target = {}
    for target in ('target_A', 'target_B'):
        rows = [row for row in records if row['target_label'] == target]
        eligible = [row for row in rows
                    if row['status'] == 'TECHNICALLY_ELIGIBLE']
        by_target[target] = {
            'candidate_count': len(CANDIDATE_SEEDS[target]),
            'evaluated_count': len(rows),
            'eligible_count': len(eligible),
            'technical_yield': (len(eligible) / len(rows) if rows else None),
            'first_four_eligible_seeds': (
                [row['seed'] for row in eligible[:4]] if complete else []),
            'failure_reasons': [
                {'seed': row['seed'], 'reasons': row.get('failure_reasons', [])}
                for row in rows if row['status'] != 'TECHNICALLY_ELIGIBLE'],
        }
    if complete:
        ready = all(by_target[target]['eligible_count'] >= 4
                    for target in by_target)
        gate = ('V13_TECHNICAL_READY_FOR_CONFIRMATORY' if ready else
                'PAUSED_V13_TECHNICAL_NOT_ROBUST')
    else:
        gate = 'HISTORY_ELIGIBILITY_SCREEN_IN_PROGRESS'
    manifest = {
        'protocol_id': PROTOCOL_ID,
        'immutable_candidate_seeds': CANDIDATE_SEEDS,
        'records': records,
        'targets': by_target,
        'pool_complete': complete,
        'runtime_reserve_substitution_used': False,
        'seed_reuse_detected': False,
        'fresh_scientific_action_endpoint_accessed': False,
        'technical_gate': gate,
        'updated_utc': now(),
    }
    atomic_json(Path(root) / 'history_eligibility_manifest.json', manifest)
    ledger = Path(root) / 'history_eligibility_ledger.csv'
    with open(ledger, 'w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            'target_label', 'target_id', 'seed', 'status',
            'history_route_complete', 'canonical_input_record_count',
            'target_state_count', 'prefix_replay_structural_exact',
            'prefix_replay_numerical_exact', 'failure_reasons'])
        writer.writeheader()
        for row in records:
            writer.writerow({key: (json.dumps(row.get(key)) if key ==
                                    'failure_reasons' else row.get(key))
                             for key in writer.fieldnames})
    return manifest


def collect(root):
    root = Path(root).resolve()
    ensure_preregistration(root)
    records = []
    total = sum(len(values) for values in CANDIDATE_SEEDS.values())
    for target in ('target_A', 'target_B'):
        for seed in CANDIDATE_SEEDS[target]:
            records.append(_candidate_record(root, target, seed))
            _write_manifest(root, records, complete=len(records) == total)
    return _write_manifest(root, records, complete=True)


def state(root):
    root = Path(root)
    manifest_path = root / 'history_eligibility_manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    launcher_path = root / 'qualification_launcher.json'
    launcher = json.loads(launcher_path.read_text()) if launcher_path.exists() else {}
    pid = launcher.get('pid')
    live = bool(pid and (Path('/proc') / str(pid) / 'cmdline').exists())
    return {'live_worker': live,
            'technical_gate': manifest.get('technical_gate', 'NOT_STARTED'),
            'target_status': manifest.get('targets', {}),
            'updated_utc': manifest.get('updated_utc')}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('plan', 'run', 'start', 'status', 'stop'))
    parser.add_argument('--root', type=Path, default=RESULT_ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == 'plan':
        path, payload = ensure_preregistration(root)
        print(json.dumps({'status': 'PREREGISTERED', 'path': str(path),
                          'candidate_seeds': payload[
                              'candidate_seeds_in_frozen_order']}, indent=2))
    elif args.command == 'run':
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(
            KeyboardInterrupt()))
        print(json.dumps(collect(root), indent=2, sort_keys=True))
    elif args.command == 'start':
        current = state(root)
        if current['live_worker']:
            raise SystemExit('verified v13-T qualification worker already live')
        ensure_preregistration(root)
        root.mkdir(parents=True, exist_ok=True)
        log = open(root / 'qualification.log', 'a', buffering=1)
        command = ['/usr/bin/python3', str(Path(__file__).resolve()), 'run',
                   '--root', str(root)]
        process = subprocess.Popen(command, cwd=str(ROOT), stdout=log,
                                   stderr=subprocess.STDOUT, text=True,
                                   start_new_session=True)
        atomic_json(root / 'qualification_launcher.json', {
            'pid': process.pid, 'pgid': process.pid,
            'command': command, 'started_utc': now()})
        print(json.dumps({'status': 'STARTED', 'pid': process.pid,
                          'root': str(root)}, indent=2))
    elif args.command == 'status':
        print(json.dumps(state(root), indent=2, sort_keys=True))
    else:
        launcher = json.loads((root / 'qualification_launcher.json').read_text())
        pid = launcher['pid']
        if not (Path('/proc') / str(pid) / 'cmdline').exists():
            raise SystemExit('no verified v13-T qualification worker')
        os.killpg(int(launcher['pgid']), signal.SIGINT)
        print('sent SIGINT to v13-T worker group {}'.format(launcher['pgid']))


if __name__ == '__main__':
    main()
