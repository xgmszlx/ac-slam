#!/usr/bin/python3
"""Frozen prefix-only serial-Karto technical screen; no treatment/suffix API."""

import argparse
import csv
import hashlib
import itertools
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

SCREEN = Path(__file__).resolve().parents[1]
ROOT = SCREEN.parents[2]
TOOLS = ROOT / 'tools/realizability_pilot'
sys.path.insert(0, str(TOOLS))
from v13_prefix_equivalence import compare_graphs, stream_sha  # noqa: E402
from serial_unified_replay import (CANDIDATE_WS, activated_environment,
                                   six_decimal_semantics, unified_replay)  # noqa: E402

ORIGINAL = ROOT / 'results/realizability_pilot/p1_context_disentangle_confirmatory_20260930'
AMENDMENT = ROOT / 'results/realizability_pilot/p1_context_disentangle_confirmatory_amendment1_20260930'
HISTORIES = [('target_A', 'target_A_H1', 101002),
             ('target_A', 'target_A_H2', 101003),
             ('target_B', 'target_B_H1', 102001)]
PROTOCOL = SCREEN / 'protocol/a1_preregistration.json'
MANIFEST = SCREEN / 'protocol/frozen_run_manifest.json'
HASHES = SCREEN / 'protocol/frozen_hashes.json'
OBSERVED = SCREEN / 'isolated_catkin_observed'
KEY_LIBRARIES = ('mapper', 'libMultiMapper.so', 'libOpenKarto.so',
                 'libSelfLocalizer.so')
CURRENT_ORDINAL = None
STOP = SCREEN / 'technical/frozen_stop_event.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def save_new(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write('\n')


def save_derived(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')


def scheduled_slots():
    """References first, then fixed interleaving; no result-dependent order."""
    blocks = [block for _, block, _ in HISTORIES]
    slots = []
    for session in (1, 2):
        if session == 1:
            phases = [('P', 1), ('B', 1), ('P', 2), ('B', 2)]
        else:
            phases = [('B', 1), ('P', 1), ('B', 2), ('P', 2)]
        for mode, repeat in phases:
            order = blocks if (session, mode, repeat) != (2, 'P', 2) else list(reversed(blocks))
            for block in order:
                slots.append((session, mode, repeat, block))
    return slots


def validate_slots(slots):
    if len(slots) != 24:
        raise ValueError('expected 24 frozen slots')
    expected = Counter((s, m, r, b) for s in (1, 2) for m in ('P', 'B')
                       for r in (1, 2) for _, b, _ in HISTORIES)
    if Counter(slots) != expected:
        raise ValueError('schedule missing or duplicating a slot')
    refs = {block: next(index + 1 for index, row in enumerate(slots)
                        if row == (1, 'P', 1, block))
            for _, block, _ in HISTORIES}
    if refs != {'target_A_H1': 1, 'target_A_H2': 2, 'target_B_H1': 3}:
        raise ValueError('serial reference selection changed')
    return refs


def frozen_inputs():
    frozen = load(AMENDMENT / 'qualification/frozen_history_manifest.json')
    out = {}
    for target, block, seed in HISTORIES:
        selected = [row for row in frozen['selected_blocks'][target]
                    if row['block_id'] == block]
        if len(selected) != 1 or selected[0]['seed'] != seed:
            raise RuntimeError('frozen history metadata mismatch: ' + block)
        base = ORIGINAL / 'qualification/candidates' / target / ('seed_%s' % seed)
        prefix = base / 'canonical_prefix.jsonl'
        params = base / 'attempt_01/mapper_params.yaml'
        if not prefix.is_file() or not params.is_file():
            raise FileNotFoundError((prefix, params))
        semantic_sha, count = stream_sha(prefix)
        if semantic_sha != selected[0]['canonical_prefix_sha256']:
            raise RuntimeError('frozen canonical input hash mismatch: ' + block)
        out[block] = {'target': target, 'block': block, 'seed': seed,
                      'prefix_path': str(prefix.resolve()),
                      'prefix_byte_sha256': sha(prefix),
                      'prefix_semantic_sha256': semantic_sha,
                      'expected_count': count,
                      'params_path': str(params.resolve()),
                      'params_byte_sha256': sha(params),
                      'target_state_ids': selected[0]['target_state_ids']}
    return out


def freeze():
    if any(path.exists() for path in (PROTOCOL, MANIFEST, HASHES)):
        raise RuntimeError('protocol files already exist; never rewrite a frozen protocol')
    if CANDIDATE_WS != OBSERVED.resolve():
        raise RuntimeError('freeze requires observed serial candidate workspace')
    build = load(SCREEN / 'audit/isolated_build_manifest.json')
    integrity = load(SCREEN / 'audit/production_integrity_before_after.json')
    if not integrity['all_equal']:
        raise RuntimeError('production integrity check failed')
    slots = scheduled_slots()
    references = validate_slots(slots)
    inputs = frozen_inputs()
    rows = []
    for ordinal, (session, mode, repeat, block) in enumerate(slots, 1):
        rows.append({'ordinal': ordinal, 'session': session, 'mode': mode,
                     'repeat': repeat, 'block': block,
                     'target': inputs[block]['target'],
                     'seed': inputs[block]['seed'],
                     'expected_prefix_count': inputs[block]['expected_count'],
                     'prefix_path': inputs[block]['prefix_path'],
                     'params_path': inputs[block]['params_path'],
                     'reference_ordinal': references[block],
                     'output_path': str((SCREEN / 'technical/runs' /
                                         ('run_%02d' % ordinal)).resolve())})
    prereg = {
        'protocol_id': 'CD_A1_SERIAL_KARTO_PREFIX_ONLY_20261008',
        'task_type': 'TECHNICAL_ARCHITECTURE_SCREENING_ONLY',
        'source_baseline_commit': '32b295d7599531bc913d7a19fb0c7de09a1ce495',
        'candidate': 'SERIAL_KARTO_CANDIDATE_OBSERVED',
        'candidate_binary_sha256': build['observed_binaries']['mapper']['sha256'],
        'pure_candidate_binary_sha256': build['pure_binaries']['mapper']['sha256'],
        'runs': 24, 'sessions': 2, 'rate_hz': 20.0,
        'history_roles': {'target_A_H1': 'previously multistable',
                          'target_A_H2': 'Target A technical control',
                          'target_B_H1': 'Target B technical control'},
        'reference_rule': ('Each history session1/P/repeat1 is its sole new serial '
                           'reference; reference cannot be replaced after failure'),
        'mode_P': 'qualification-style prefix-only without reference check',
        'mode_B': ('branch-style prefix gate against new serial reference; '
                   'same strict six-decimal semantics, no combined stream or suffix'),
        'comparison': {
            'structure': 'exact node IDs, unique IDs, edge endpoints and insertion order',
            'numeric_6dp': '%.6f round-trip per float, then exact elementwise comparison',
            'high_precision': 'max_digits10 graph JSON; any nonzero numerical difference leads REVIEW if 6dp exact',
            'angles': 'compare Karto-dumped normalized radians directly; no posthoc wrap/alignment',
            'covariance': 'all 3x3 elements in edge insertion order',
            'tolerance': 0.0,
        },
        'no_treatment_suffix': True,
        'stop_rule': ('Stop immediately on missing/changed frozen input, binary/library SHA mismatch, '
                      'reference run technical failure, crashed/partial run, callback/count/barrier '
                      'failure, or provenance absence. Do not rerun failed slot. Continue all planned '
                      'slots after a valid numerical mismatch to characterize clusters.'),
        'gate_rule': {
            'BUILD_ISOLATION_FAILED': 'runtime binary/library source or false mode unverified',
            'SERIAL_KARTO_SCREENING_PASS': '24/24 valid, all same-history pairs structure/6dp/high-precision exact',
            'SERIAL_KARTO_NUMERICAL_REVIEW_REQUIRED': '24/24 valid and 6dp exact but high-precision differs',
            'SERIAL_KARTO_SCREENING_FAIL': 'any valid structural or 6dp numerical divergence',
            'SERIAL_KARTO_TECHNICALLY_INCOMPLETE': 'missing/failed run or unavailable required evidence',
        },
    }
    manifest = {'protocol_id': prereg['protocol_id'], 'rows': rows,
                'references': references, 'inputs': inputs}
    save_new(PROTOCOL, prereg)
    save_new(MANIFEST, manifest)
    files = {
        'protocol': PROTOCOL, 'manifest': MANIFEST,
        'a1_runner': Path(__file__),
        'replay_runner': SCREEN / 'technical/serial_unified_replay.py',
        'static_tests': SCREEN / 'technical/test_a1_screen.py',
        'comparison_code': TOOLS / 'v13_prefix_equivalence.py',
        'a0_build_manifest': SCREEN / 'audit/isolated_build_manifest.json',
        'a0_runtime_provenance': SCREEN / 'audit/runtime_library_provenance.json',
    }
    for key in KEY_LIBRARIES:
        files['candidate_' + key] = Path(build['observed_binaries'][key]['path'])
        files['pure_' + key] = Path(build['pure_binaries'][key]['path'])
    for block, row in inputs.items():
        files[block + '_prefix'] = Path(row['prefix_path'])
        files[block + '_params'] = Path(row['params_path'])
    save_new(HASHES, {'protocol_id': prereg['protocol_id'],
                      'sha256': {key: sha(path) for key, path in files.items()},
                      'paths': {key: str(path.resolve()) for key, path in files.items()}})
    save_new(SCREEN / 'technical/prefix_input_inventory.json', inputs)
    return {'protocol_sha256': sha(PROTOCOL), 'manifest_sha256': sha(MANIFEST),
            'hashes_sha256': sha(HASHES), 'count': len(rows)}


def verify_frozen():
    frozen = load(HASHES)
    for key, expected in frozen['sha256'].items():
        path = Path(frozen['paths'][key])
        if not path.is_file() or sha(path) != expected:
            raise RuntimeError('frozen SHA mismatch: {} {}'.format(key, path))
    if CANDIDATE_WS != OBSERVED.resolve():
        raise RuntimeError('runtime workspace not frozen observed candidate')
    return load(PROTOCOL), load(MANIFEST)


def check_runtime(record, build):
    if record['executable_sha256'] != build['observed_binaries']['mapper']['sha256']:
        raise RuntimeError('runtime mapper SHA mismatch')
    paths = set(record['mapped_paths'])
    for key in KEY_LIBRARIES[1:]:
        entry = build['observed_binaries'][key]
        if entry['path'] not in paths or sha(entry['path']) != entry['sha256']:
            raise RuntimeError('runtime isolated library mismatch: ' + key)
    if any('/home/wcqw/ac-slam/catkin_ws/devel/lib/' in path for path in paths):
        raise RuntimeError('production library loaded in candidate mapper')


def environment_snapshot():
    env = activated_environment()
    return {'platform': platform.platform(), 'kernel': platform.release(),
            'python': sys.executable, 'ROS_DISTRO': env.get('ROS_DISTRO'),
            'CMAKE_PREFIX_PATH': env.get('CMAKE_PREFIX_PATH'),
            'ROS_PACKAGE_PATH': env.get('ROS_PACKAGE_PATH'),
            'LD_LIBRARY_PATH': env.get('LD_LIBRARY_PATH'),
            'PATH_sha256': hashlib.sha256(env.get('PATH', '').encode()).hexdigest(),
            'cpu_affinity': sorted(os.sched_getaffinity(0)),
            'rospack_nav2d_karto': subprocess.check_output(
                ['rospack', 'find', 'nav2d_karto'], env=env, text=True).strip()}


def run_session(session):
    global CURRENT_ORDINAL
    if STOP.exists():
        raise RuntimeError('frozen stop event already exists; no further runs')
    protocol, manifest = verify_frozen()
    rows = [row for row in manifest['rows'] if row['session'] == session]
    if len(rows) != 12:
        raise RuntimeError('frozen session does not have 12 rows')
    build = load(SCREEN / 'audit/isolated_build_manifest.json')
    session_path = SCREEN / 'technical' / ('session_%02d.json' % session)
    if session_path.exists():
        if load(session_path)['frozen_hashes_sha256'] != sha(HASHES):
            raise RuntimeError('session snapshot belongs to different protocol')
    else:
        save_new(session_path, {'session': session, 'started_utc': time.strftime(
            '%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'runner_pid': os.getpid(), 'environment': environment_snapshot(),
            'frozen_hashes_sha256': sha(HASHES)})
    for row in rows:
        CURRENT_ORDINAL = row['ordinal']
        verify_frozen()
        out = Path(row['output_path'])
        status = out / 'a1_result.json'
        if status.exists():
            previous = load(status)
            if previous['ordinal'] != row['ordinal'] or previous['status'] != 'COMPLETE':
                raise RuntimeError('prior partial/invalid result; no reattempt: ' + str(out))
            continue
        if out.exists() and any(out.iterdir()):
            raise RuntimeError('partial run exists; no reattempt: ' + str(out))
        reference = (SCREEN / 'technical/runs' /
                     ('run_%02d' % row['reference_ordinal']) / 'graph_pre.json')
        is_reference = row['ordinal'] == row['reference_ordinal']
        if not is_reference and not reference.is_file():
            raise RuntimeError('preselected serial reference missing: ' + str(reference))
        print('START A1 {}/24 {} {} S{} R{}'.format(row['ordinal'], row['block'],
              row['mode'], session, row['repeat']), flush=True)
        result = unified_replay(row['prefix_path'], row['params_path'], out,
                                rate_hz=protocol['rate_hz'],
                                target_ids=manifest['inputs'][row['block']]['target_state_ids'],
                                prefix_reference_path=(reference if row['mode'] == 'B' else None))
        if result['status'] != 'REPLAY_COMPLETE' or result['suffix_published'] or \
                result['suffix_record_count'] != 0:
            raise RuntimeError('replay incomplete or FORBIDDEN suffix: ' + str(out))
        expected = row['expected_prefix_count']
        if not (result['prefix_record_count'] == expected ==
                result['processed_prefix_count'] == result['prefix_publisher']['published']):
            raise RuntimeError('prefix/callback count mismatch: ' + str(out))
        if result['background_graph_dump_used'] or result['fixed_sleep_used_as_drain_barrier']:
            raise RuntimeError('invalid graph snapshot barrier: ' + str(out))
        check_runtime(result['mapper_runtime'], build)
        graph = load(out / 'graph_pre.json')
        provenance = out / 'edge_provenance.jsonl'
        constraints = [json.loads(line) for line in provenance.read_text().splitlines()
                       if line and json.loads(line).get('record_type') == 'constraint_created']
        if len(constraints) != len(graph['edges']):
            raise RuntimeError('constraint provenance count mismatch: ' + str(out))
        graph6 = six_decimal_semantics(graph)
        save_derived(out / 'graph_pre_6dp.json', graph6)
        ref_graph = graph if is_reference else load(reference)
        comparison6 = compare_graphs(six_decimal_semantics(ref_graph), graph6,
                                     target_ids=manifest['inputs'][row['block']]['target_state_ids'])
        comparison_high = compare_graphs(ref_graph, graph,
                                         target_ids=manifest['inputs'][row['block']]['target_state_ids'])
        payload = {
            'status': 'COMPLETE', 'ordinal': row['ordinal'], 'session': session,
            'mode': row['mode'], 'repeat': row['repeat'], 'block': row['block'],
            'reference_ordinal': row['reference_ordinal'],
            'is_preselected_reference': is_reference,
            'input_byte_sha256': sha(row['prefix_path']),
            'input_semantic_sha256': result['prefix_input_sha256'],
            'expected_count': expected, 'processed_count': result['processed_prefix_count'],
            'graph_high_sha256': sha(out / 'graph_pre.json'),
            'graph_6dp_sha256': sha(out / 'graph_pre_6dp.json'),
            'nodes': len(graph['nodes']), 'edges': len(graph['edges']),
            'constraint_provenance_count': len(constraints),
            'provenance_kinds': dict(Counter(x['creation_provenance'] for x in constraints)),
            'comparison_6dp': comparison6, 'comparison_high': comparison_high,
            'branch_style_would_pass': bool(comparison6['structural']['exact'] and
                                             comparison6['numerical']['exact']),
            'no_suffix': True, 'wall_s': result['elapsed_wall_s'],
            'mapper_cpu_user_s': result['mapper_runtime']['mapper_cpu_user_s'],
            'mapper_cpu_system_s': result['mapper_runtime']['mapper_cpu_system_s'],
            'mapper_peak_rss_bytes': result['mapper_runtime']['peak_mapper_rss_bytes'],
            'runtime_sha256': result['mapper_runtime']['executable_sha256'],
        }
        save_new(status, payload)
        print('DONE A1 {}/24 6dp={} high={}'.format(row['ordinal'],
              comparison6['numerical']['exact'], comparison_high['numerical']['exact']), flush=True)


def write_csv(path, rows):
    if not rows:
        return
    with Path(path).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def summarize():
    protocol, manifest = verify_frozen()
    analysis = SCREEN / 'analysis'
    technical = SCREEN / 'technical'
    rows = []
    for row in manifest['rows']:
        path = Path(row['output_path']) / 'a1_result.json'
        if path.is_file():
            rows.append(load(path))
    ledger = []
    for row in manifest['rows']:
        result = next((x for x in rows if x['ordinal'] == row['ordinal']), None)
        stop = load(STOP) if STOP.exists() else None
        missing_status = ('NOT_RUN_DUE_TO_FROZEN_STOP_RULE'
                          if stop and row['ordinal'] > stop['ordinal'] else
                          'NOT_RUN_OR_INTERRUPTED')
        ledger.append({'ordinal': row['ordinal'], 'session': row['session'],
                       'mode': row['mode'], 'repeat': row['repeat'],
                       'block': row['block'],
                       'status': result['status'] if result else missing_status,
                       'count': result['processed_count'] if result else '',
                       'nodes': result['nodes'] if result else '',
                       'edges': result['edges'] if result else '',
                       'graph_6dp_sha256': result['graph_6dp_sha256'] if result else '',
                       'branch_style_would_pass': result['branch_style_would_pass'] if result else '',
                       'wall_s': result['wall_s'] if result else '',
                       'mapper_cpu_user_s': result['mapper_cpu_user_s'] if result else '',
                       'mapper_cpu_system_s': result['mapper_cpu_system_s'] if result else '',
                       'mapper_peak_rss_bytes': result['mapper_peak_rss_bytes'] if result else ''})
    write_csv(technical / 'a1_run_ledger.csv', ledger)
    comparisons = []
    clusters = {}
    high_diffs = []
    references = {}
    for block, ref_ord in manifest['references'].items():
        matching = [x for x in rows if x['block'] == block]
        refs = [x for x in matching if x['ordinal'] == ref_ord]
        if refs:
            references[block] = {'ordinal': ref_ord,
                                 'graph_path': manifest['rows'][ref_ord - 1]['output_path'] + '/graph_pre.json',
                                 'graph_high_sha256': refs[0]['graph_high_sha256'],
                                 'graph_6dp_sha256': refs[0]['graph_6dp_sha256']}
        by_numeric = defaultdict(list)
        for item in matching:
            path = Path(manifest['rows'][item['ordinal'] - 1]['output_path']) / 'graph_pre_6dp.json'
            graph = load(path)
            numeric = {'nodes': [[n[k] for k in ('x', 'y', 'theta')] for n in graph['nodes']],
                       'edges': [[e.get('measurement'), e.get('covariance_3x3')]
                                 for e in graph['edges']]}
            key = hashlib.sha256(json.dumps(numeric, sort_keys=True).encode()).hexdigest()
            by_numeric[key].append(item['ordinal'])
        clusters[block] = [{'numeric_sha256': key, 'ordinals': value}
                           for key, value in by_numeric.items()]
        for left, right in itertools.combinations(matching, 2):
            g1 = load(Path(manifest['rows'][left['ordinal'] - 1]['output_path']) / 'graph_pre.json')
            g2 = load(Path(manifest['rows'][right['ordinal'] - 1]['output_path']) / 'graph_pre.json')
            c6 = compare_graphs(six_decimal_semantics(g1), six_decimal_semantics(g2))
            ch = compare_graphs(g1, g2)
            comparisons.append({'block': block, 'left': left['ordinal'],
                                'right': right['ordinal'],
                                'structural_exact': c6['structural']['exact'],
                                'numerical_exact_6dp': c6['numerical']['exact'],
                                'numerical_exact_high': ch['numerical']['exact'],
                                **{'high_' + k: v for k, v in ch['numerical'].items()
                                   if k != 'exact'}})
        for item in matching:
            high_diffs.append({'block': block, 'ordinal': item['ordinal'],
                               **{k: v for k, v in item['comparison_high']['numerical'].items()
                                  if k != 'exact'}})
    write_csv(analysis / 'graph_pairwise_comparison.csv', comparisons)
    write_csv(analysis / 'high_precision_differences.csv', high_diffs)
    save_derived(analysis / 'serial_reference_manifest.json', references)
    save_derived(analysis / 'serialized_numeric_clusters.json', clusters)
    performance = {block: {'n': len(x), 'wall_median_s': statistics.median(x) if x else None,
                           'wall_min_s': min(x) if x else None,
                           'wall_max_s': max(x) if x else None}
                   for block in manifest['references']
                   for x in [[r['wall_s'] for r in rows if r['block'] == block]]}
    save_derived(analysis / 'performance_summary.json', performance)
    if STOP.exists() and load(STOP)['gate'] == 'BUILD_ISOLATION_FAILED':
        gate = 'BUILD_ISOLATION_FAILED'
    elif len(rows) != 24:
        gate = 'SERIAL_KARTO_TECHNICALLY_INCOMPLETE'
    elif any(not c['structural_exact'] or not c['numerical_exact_6dp'] for c in comparisons):
        gate = 'SERIAL_KARTO_SCREENING_FAIL'
    elif any(not c['numerical_exact_high'] for c in comparisons):
        gate = 'SERIAL_KARTO_NUMERICAL_REVIEW_REQUIRED'
    else:
        gate = 'SERIAL_KARTO_SCREENING_PASS'
    verdict = {'gate': gate, 'planned': 24, 'completed': len(rows),
               'pairwise_count': len(comparisons),
               'no_suffix_all': all(r['no_suffix'] for r in rows),
               'protocol_sha256': sha(PROTOCOL), 'manifest_sha256': sha(MANIFEST),
               'frozen_hashes_sha256': sha(HASHES)}
    save_derived(analysis / 'screening_verdict.json', verdict)
    return verdict


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('freeze', 'run-session', 'summarize'))
    parser.add_argument('--session', type=int, choices=(1, 2))
    args = parser.parse_args()
    if args.action == 'freeze':
        result = freeze()
    elif args.action == 'run-session':
        if args.session is None:
            parser.error('--session required')
        try:
            result = run_session(args.session)
        except Exception as error:
            if CURRENT_ORDINAL is not None and not STOP.exists():
                reason = str(error)
                gate = ('BUILD_ISOLATION_FAILED' if any(x in reason for x in (
                    'runtime mapper SHA', 'runtime isolated library',
                    'production library loaded', 'runtime workspace',
                    'frozen SHA mismatch: candidate_')) else
                    'SERIAL_KARTO_TECHNICALLY_INCOMPLETE')
                save_new(STOP, {'ordinal': CURRENT_ORDINAL, 'reason': reason,
                                'gate': gate, 'time_utc': time.strftime(
                                    '%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
            raise
    else:
        result = summarize()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
