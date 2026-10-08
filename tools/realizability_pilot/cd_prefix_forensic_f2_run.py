#!/usr/bin/python3
"""Predeclared 24-run prefix-only CD-F2 technical replay schedule.

P and B both publish only the canonical prefix. B additionally applies the
frozen branch-style prefix-reference gate; there is no suffix file argument.
"""

import argparse
import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from cd_prefix_forensic_f2 import (F2, ROOT, cluster_graphs, frozen_block,
                                   history_inputs, read_json, sha, write_csv,
                                   write_json)
from v13_prefix_equivalence import compare_graphs, stream_sha
from v13_unified_replay import unified_replay
from run_pilot import activated_environment

HISTORIES = [('target_A', 'target_A_H1'), ('target_A', 'target_A_H2'),
             ('target_B', 'target_B_H1')]
MODES = ('P', 'B')
PLAN_PATH = F2 / 'technical/prefix_only_run_manifest.json'


def schedule():
    # Mode/history order alternates within each fresh invocation; never
    # conditional on the observed graph cluster or scientific endpoint.
    patterns = [
        [(0, 'P'), (1, 'B'), (2, 'P'), (0, 'B'), (1, 'P'), (2, 'B')],
        [(2, 'B'), (1, 'P'), (0, 'B'), (2, 'P'), (1, 'B'), (0, 'P')],
        [(1, 'P'), (2, 'B'), (0, 'P'), (1, 'B'), (2, 'P'), (0, 'B')],
        [(0, 'B'), (2, 'P'), (1, 'B'), (0, 'P'), (2, 'B'), (1, 'P')],
    ]
    rows = []
    for index, pattern in enumerate(patterns):
        session = index // 2 + 1
        repeat = index % 2 + 1
        for history_index, mode in pattern:
            target, block = HISTORIES[history_index]
            record, base, prefix, params = history_inputs(target, block)
            rows.append({
                'ordinal': len(rows) + 1,
                'session': session,
                'repeat': repeat,
                'target': target,
                'block': block,
                'seed': record['seed'],
                'mode': mode,
                'prefix_path': str(prefix),
                'prefix_sha256': sha(prefix),
                'prefix_semantic_sha256': stream_sha(prefix)[0],
                'mapper_params_path': str(params),
                'qualification_reference_path': str(base / 'prefix_replays/repeat_01/graph_pre.json'),
            })
    return rows


def validate_schedule(rows):
    if len(rows) != 24 or [r['ordinal'] for r in rows] != list(range(1, 25)):
        raise ValueError('schedule must contain exactly 24 ordered rows')
    counts = Counter((r['target'], r['block'], r['mode'], r['session']) for r in rows)
    expected = {(target, block, mode, session): 2
                for target, block in HISTORIES for mode in MODES for session in (1, 2)}
    if counts != expected:
        raise ValueError('unbalanced immutable schedule')
    return True


def freeze_plan():
    rows = schedule()
    validate_schedule(rows)
    binary = ROOT / 'catkin_ws/devel/lib/nav2d_karto/mapper'
    if not binary.is_file():
        raise RuntimeError('production mapper binary missing')
    expected_binary = '7ab54496b4572e831d7f10d615ad3d700bec3a0b89c5abdb9c562616a67d92f6'
    if sha(binary) != expected_binary:
        raise RuntimeError('production mapper binary SHA differs from frozen CD')
    for row in rows:
        frozen = frozen_block(row['target'], row['block'])
        if row['prefix_semantic_sha256'] != frozen['canonical_prefix_sha256']:
            raise RuntimeError('frozen prefix hash changed for ' + row['block'])
    payload = {
        'protocol': 'CD_F2_PREFIX_NUMERICAL_REPRODUCIBILITY',
        'task_type': 'TECHNICAL_FORENSIC_ONLY',
        'planned_run_count': 24,
        'modes': {'P': 'qualification-style prefix-only, no reference gate',
                  'B': 'branch-style frozen reference gate, forcibly prefix-only'},
        'sessions': 2,
        'independent_mapper_and_ros_master_per_run': True,
        'suffix_publication_permitted': False,
        'rate_hz': 20.0,
        'production_mapper_binary_sha256': expected_binary,
        'rows': rows,
    }
    if PLAN_PATH.exists():
        if read_json(PLAN_PATH) != payload:
            raise RuntimeError('frozen F2 run plan changed')
    else:
        write_json(PLAN_PATH, payload)
    return payload


def environment_fingerprint():
    env = activated_environment()
    binary = ROOT / 'catkin_ws/devel/lib/nav2d_karto/mapper'
    libraries = subprocess.run(['ldd', str(binary)], text=True,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, timeout=15)
    return {
        'platform': platform.platform(),
        'kernel': platform.release(),
        'cpu_affinity': sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None,
        'cpu_count': os.cpu_count(),
        'python_executable': sys.executable,
        'ros_distribution': env.get('ROS_DISTRO'),
        'ros_python_version': env.get('ROS_PYTHON_VERSION'),
        'path_sha256': hashlib.sha256(env.get('PATH', '').encode()).hexdigest(),
        'ld_library_path_sha256': hashlib.sha256(env.get('LD_LIBRARY_PATH', '').encode()).hexdigest(),
        'omp_num_threads': env.get('OMP_NUM_THREADS'),
        'tbb_num_threads': env.get('TBB_NUM_THREADS'),
        'tbb_global_control': env.get('TBB_GLOBAL_CONTROL'),
        'library_paths': normalize_library_resolution(libraries.stdout),
        'library_resolution_returncode': libraries.returncode,
    }


def normalize_library_resolution(output):
    """Discard ASLR load addresses, retaining resolved library identities."""
    paths = []
    for line in output.splitlines():
        if '=>' in line:
            paths.append(line.split('=>', 1)[1].strip().split(' (', 1)[0])
        elif line.strip().startswith('/'):
            paths.append(line.strip().split(' (', 1)[0])
    return sorted(paths)


def run_session(session):
    plan = freeze_plan()
    rows = [r for r in plan['rows'] if r['session'] == session]
    if len(rows) != 12:
        raise RuntimeError('session does not have 12 frozen rows')
    technical = F2 / 'technical'
    technical.mkdir(parents=True, exist_ok=True)
    session_path = technical / ('session_%02d.json' % session)
    if session_path.exists():
        previous = read_json(session_path)
        if previous['plan_sha256'] != sha(PLAN_PATH):
            raise RuntimeError('session plan SHA changed')
    else:
        write_json(session_path, {
            'session': session, 'plan_sha256': sha(PLAN_PATH),
            'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'runner_pid': os.getpid(),
            'environment_fingerprint': environment_fingerprint(),
        })
    for row in rows:
        run_dir = technical / 'runs' / ('run_%02d' % row['ordinal'])
        result_path = run_dir / 'forensic_result.json'
        if result_path.exists():
            continue
        if run_dir.exists() and any(run_dir.iterdir()):
            raise RuntimeError('partial run exists; preserve it and diagnose before retry: ' + str(run_dir))
        run_dir.mkdir(parents=True)
        print('START F2 prefix run {}/24 session={} block={} mode={}'.format(
            row['ordinal'], session, row['block'], row['mode']), flush=True)
        started = time.time()
        reference = row['qualification_reference_path'] if row['mode'] == 'B' else None
        replay = unified_replay(row['prefix_path'], row['mapper_params_path'],
                                run_dir, rate_hz=plan['rate_hz'],
                                prefix_reference_path=reference)
        if replay['suffix_published'] or replay['suffix_record_count']:
            raise RuntimeError('FORBIDDEN: forensic run published suffix')
        if replay['processed_prefix_count'] != replay['prefix_record_count']:
            raise RuntimeError('prefix processed count mismatch')
        reference_graph = read_json(row['qualification_reference_path'])
        graph = read_json(run_dir / 'graph_pre.json')
        comparison = compare_graphs(reference_graph, graph)
        payload = {
            'ordinal': row['ordinal'], 'session': session,
            'repeat': row['repeat'], 'mode': row['mode'],
            'target': row['target'], 'block': row['block'],
            'seed': row['seed'], 'prefix_sha256': replay['prefix_input_sha256'],
            'actual_published_count': replay['prefix_publisher']['published'],
            'processed_callback_count': replay['processed_prefix_count'],
            'graph_sha256': sha(run_dir / 'graph_pre.json'),
            'mapper_config_sha256': replay['mapper_params_sha256'],
            'mapper_binary_sha256': replay['code_provenance']['mapper_binary_sha256'],
            'structure_exact_vs_qualification': comparison['structural']['exact'],
            'numerical_exact_vs_qualification_6dp': comparison['numerical']['exact'],
            'comparison': comparison,
            'elapsed_wall_s': time.time() - started,
            'suffix_published': False,
            'environment_fingerprint_sha256': hashlib.sha256(json.dumps(
                environment_fingerprint(), sort_keys=True).encode()).hexdigest(),
        }
        write_json(result_path, payload)
        print('DONE F2 prefix run {} exact={} elapsed={:.1f}s'.format(
            row['ordinal'], payload['numerical_exact_vs_qualification_6dp'],
            payload['elapsed_wall_s']), flush=True)
    return {'session': session, 'completed': 12}


def summarize():
    plan = freeze_plan()
    technical = F2 / 'technical'
    rows = []
    for entry in plan['rows']:
        path = technical / 'runs' / ('run_%02d' % entry['ordinal']) / 'forensic_result.json'
        if path.is_file():
            record = read_json(path)
            rows.append({key: value for key, value in record.items() if key != 'comparison'})
        else:
            rows.append({**{k: entry[k] for k in ('ordinal', 'session', 'repeat', 'target', 'block', 'mode')},
                         'status': 'NOT_RUN_OR_INTERRUPTED'})
    fields = sorted(set().union(*(row.keys() for row in rows)))
    write_csv(technical / 'repetition_results.csv', rows, fields)
    completed = [r for r in rows if r.get('graph_sha256')]
    comparisons = []
    for target, block in HISTORIES:
        run_rows = [r for r in completed if r['target'] == target and r['block'] == block]
        for left, right in __import__('itertools').combinations(run_rows, 2):
            g1 = read_json(technical / 'runs' / ('run_%02d' % left['ordinal']) / 'graph_pre.json')
            g2 = read_json(technical / 'runs' / ('run_%02d' % right['ordinal']) / 'graph_pre.json')
            result = compare_graphs(g1, g2)
            comparisons.append({'target': target, 'block': block,
                                'left_run': left['ordinal'], 'right_run': right['ordinal'],
                                'left_mode': left['mode'], 'right_mode': right['mode'],
                                'left_session': left['session'], 'right_session': right['session'],
                                'structure_exact': result['structural']['exact'],
                                'numerical_exact_6dp': result['numerical']['exact'],
                                **{k: v for k, v in result['numerical'].items() if k != 'exact'}})
    if comparisons:
        write_csv(technical / 'reproducibility_matrix.csv', comparisons, list(comparisons[0]))
    groups = defaultdict(list)
    for row in completed:
        groups[(row['block'], row['mode'], row['session'])].append(row)
    summary = {'planned_count': 24, 'completed_count': len(completed),
               'all_suffix_absent': all(not row['suffix_published'] for row in completed),
               'by_block_mode_session': [
                   {'block': key[0], 'mode': key[1], 'session': key[2],
                    'runs': [r['ordinal'] for r in value],
                    'qualification_exact_count': sum(r['numerical_exact_vs_qualification_6dp'] for r in value),
                    'unique_graph_hashes': len({r['graph_sha256'] for r in value})}
                   for key, value in sorted(groups.items())],
               'pairwise_structural_exact': all(r['structure_exact'] for r in comparisons),
               'pairwise_numerical_exact': all(r['numerical_exact_6dp'] for r in comparisons) if comparisons else None}
    write_json(technical / 'session_effect_summary.json', summary)
    cluster_summary = {}
    for target, block in HISTORIES:
        record, base, _, _ = history_inputs(target, block)
        _ = record
        graphs = {'Q1': (base / 'prefix_replays/repeat_01/graph_pre.json',
                         read_json(base / 'prefix_replays/repeat_01/graph_pre.json'))}
        for row in completed:
            if row['target'] == target and row['block'] == block:
                label = 'F2_%02d' % row['ordinal']
                path = technical / 'runs' / ('run_%02d' % row['ordinal']) / 'graph_pre.json'
                graphs[label] = (path, read_json(path))
        cluster_summary[block] = [{'cluster_id': i + 1, 'labels': labels,
                                   'graph_sha256': sha(graphs[labels[0]][0])}
                                  for i, labels in enumerate(cluster_graphs(graphs))]
    write_json(technical / 'prefix_cluster_membership.json', cluster_summary)
    normalized_env = {}
    for session in (1, 2):
        path = technical / ('session_%02d.json' % session)
        if not path.is_file():
            continue
        original = read_json(path)['environment_fingerprint']
        # `ldd` prints ASLR load addresses; they must not enter a semantic
        # environment comparison or all otherwise identical runs differ.
        normalized_env[str(session)] = {
            key: value for key, value in original.items()
            if key != 'library_resolution'}
        if 'library_resolution' in original:
            normalized_env[str(session)]['library_paths'] = normalize_library_resolution(
                original['library_resolution'])
    write_json(technical / 'normalized_session_environment.json', {
        'sessions': normalized_env,
        'semantically_equal': (normalized_env.get('1') == normalized_env.get('2')),
        'caveat': 'Per-run fingerprint hashes include ASLR addresses from ldd and are not compared; '
                  'recorded session-level environment excludes ASLR but cannot prove hidden runtime-state equality.'})
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('plan', 'run', 'summarize'))
    parser.add_argument('--session', type=int, choices=(1, 2))
    args = parser.parse_args()
    if args.command == 'plan':
        result = freeze_plan()
        print(json.dumps({'planned_run_count': len(result['rows']),
                          'manifest_sha256': sha(PLAN_PATH)}, indent=2))
    elif args.command == 'run':
        if args.session is None:
            parser.error('run requires --session 1 or 2')
        print(json.dumps(run_session(args.session), indent=2))
    else:
        print(json.dumps(summarize(), indent=2))


if __name__ == '__main__':
    main()
