#!/usr/bin/python3
"""One isolated, bounded H1 matcher trace; production binary stays untouched."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import v13_unified_replay as replay_module

from cd_prefix_forensic_f2 import F2, ROOT, history_inputs, read_json, sha, write_json
from v13_prefix_equivalence import compare_graphs

TECHNICAL = F2 / 'technical'
PLAN = TECHNICAL / 'instrumented_plan.json'


def activated_forensic_environment(workspace, trace_path):
    command = 'source "{}" && source "{}" && env -0'.format(
        ROOT / 'catkin_ws/activate.sh', workspace / 'devel/setup.bash')
    inherited = os.environ.copy()
    inherited['ACSLAM_F2_TRACE_PATH'] = str(trace_path)
    raw = subprocess.check_output(['bash', '-lc', command], env=inherited)
    env = {}
    for item in raw.split(b'\0'):
        if b'=' in item:
            key, value = item.split(b'=', 1)
            env[key.decode()] = value.decode()
    env['DISPLAY'] = ':0'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    resolved = subprocess.check_output(['rospack', 'find', 'nav2d_karto'],
                                       env=env, text=True).strip()
    expected = workspace / 'src/navigation_2d/nav2d_karto'
    if Path(resolved).resolve() != expected.resolve():
        raise RuntimeError('forensic ROS package did not resolve to isolated source')
    if env.get('ACSLAM_F2_TRACE_PATH') != str(trace_path):
        raise RuntimeError('trace destination not propagated')
    return env


def freeze(workspace):
    binary = workspace / 'devel/lib/nav2d_karto/mapper'
    source = workspace / 'src/navigation_2d/nav2d_karto/OpenKarto/source/OpenMapper.cpp'
    original_binary = ROOT / 'catkin_ws/devel/lib/nav2d_karto/mapper'
    if sha(original_binary) != '7ab54496b4572e831d7f10d615ad3d700bec3a0b89c5abdb9c562616a67d92f6':
        raise RuntimeError('production binary changed')
    record, _, prefix, params = history_inputs('target_A', 'target_A_H1')
    payload = {
        'task': 'CD_F2_ISOLATED_MATCHER_TRACE',
        'history': 'target_A_H1', 'seed': record['seed'],
        'run_ids': ['I1', 'I2', 'I3', 'I4'],
        'mode': 'prefix_only_no_reference_gate',
        'suffix_publication_allowed': False,
        'forensic_workspace': str(workspace),
        'forensic_binary_sha256': sha(binary),
        'forensic_source_sha256': sha(source),
        'production_binary_sha256': sha(original_binary),
        'prefix_sha256': sha(prefix),
        'mapper_params_sha256': sha(params),
        'limitation': 'Instrumented build can perturb timing; never treat it as production backend.'}
    if PLAN.exists() and read_json(PLAN) != payload:
        raise RuntimeError('forensic instrumentation plan changed')
    if not PLAN.exists():
        write_json(PLAN, payload)
    return payload


def run(workspace):
    plan = freeze(workspace)
    _, base, prefix, params = history_inputs('target_A', 'target_A_H1')
    reference = read_json(base / 'prefix_replays/repeat_01/graph_pre.json')
    original_activate = replay_module.activated_environment
    try:
        for run_id in plan['run_ids']:
            run_dir = TECHNICAL / 'instrumented' / run_id
            result_path = run_dir / 'instrumented_result.json'
            if result_path.is_file():
                continue
            if run_dir.exists() and any(run_dir.iterdir()):
                raise RuntimeError('partial instrumented run exists: ' + str(run_dir))
            run_dir.mkdir(parents=True)
            trace = run_dir / 'matcher_trace.jsonl'
            replay_module.activated_environment = lambda: activated_forensic_environment(workspace, trace)
            print('START F2 instrumented {}'.format(run_id), flush=True)
            result = replay_module.unified_replay(prefix, params, run_dir, rate_hz=20.0)
            if result['suffix_published'] or result['suffix_record_count']:
                raise RuntimeError('forbidden suffix publication')
            observed = read_json(run_dir / 'graph_pre.json')
            comparison = compare_graphs(reference, observed)
            traces = [json.loads(line) for line in trace.open() if line.strip()] if trace.is_file() else []
            payload = {'run_id': run_id, 'forensic_binary_sha256': plan['forensic_binary_sha256'],
                       'production_binary_sha256': plan['production_binary_sha256'],
                       'graph_sha256': sha(run_dir / 'graph_pre.json'),
                       'reference_numerical_exact_6dp': comparison['numerical']['exact'],
                       'reference_structure_exact': comparison['structural']['exact'],
                       'processed_prefix_count': result['processed_prefix_count'],
                       'prefix_published': result['prefix_publisher']['published'],
                       'trace_count': len(traces), 'trace_sha256': sha(trace) if trace.is_file() else None,
                       'trace': traces,
                       'provenance_warning': 'unified_replay_result.json code_provenance resolves production path '
                                             'even though isolated environment resolves forensic mapper; '
                                             'this file records the actual forensic binary SHA.'}
            write_json(result_path, payload)
            print('DONE F2 instrumented {} exact={} trace={}'.format(
                run_id, payload['reference_numerical_exact_6dp'], len(traces)), flush=True)
    finally:
        replay_module.activated_environment = original_activate


def summarize(workspace):
    plan = freeze(workspace)
    rows = [read_json(TECHNICAL / 'instrumented' / run_id / 'instrumented_result.json')
            for run_id in plan['run_ids']]
    if any(row['trace_count'] != 2 for row in rows):
        raise RuntimeError('instrumented scan 15 did not produce coarse+fine traces')
    trace = {
        'status': 'ONE_FOCUSED_ISOLATED_INSTRUMENTATION_COMPLETED',
        'instrumented_run_count': len(rows),
        'actual_forensic_binary_sha256': plan['forensic_binary_sha256'],
        'production_binary_sha256': plan['production_binary_sha256'],
        'production_binary_unchanged': sha(ROOT / 'catkin_ws/devel/lib/nav2d_karto/mapper') == plan['production_binary_sha256'],
        'runs': [
            {'run_id': row['run_id'], 'graph_sha256': row['graph_sha256'],
             'reference_numerical_exact_6dp': row['reference_numerical_exact_6dp'],
             'pre_match_odometry_x': row['trace'][0]['odom_x'],
             'coarse': row['trace'][0], 'fine': row['trace'][1],
             'fine_response_margin': row['trace'][1]['best_response'] - row['trace'][1]['second_response']}
            for row in rows],
        'interpretation_limit': 'Search centers already differ when scan 15 enters the matcher; '
                                'this trace does not identify the earlier state variable or a TBB race.',
    }
    write_json(TECHNICAL / 'matcher_divergence_trace.json', trace)
    write_json(TECHNICAL / 'threading_comparison.json', {
        'production_backend_tbb_enabled': True,
        'isolated_forensic_build_tbb_enabled': True,
        'single_thread_counterfactual_run': False,
        'causal_parallel_sensitivity_identified': False,
        'evidence': 'OpenMapper.cpp uses tbb::parallel_for, but the four isolated runs '
                    'used the same parallel configuration and still reached multiple prefix graphs.',
        'limitation': 'Multistability under TBB does not prove a parallel data race. '
                      'No change to the production backend is justified.'})
    return trace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('plan', 'run', 'summarize'))
    parser.add_argument('--forensic-workspace', required=True)
    args = parser.parse_args()
    workspace = Path(args.forensic_workspace).resolve()
    if args.command == 'plan':
        print(json.dumps(freeze(workspace), indent=2, sort_keys=True))
    elif args.command == 'run':
        run(workspace)
    else:
        result = summarize(workspace)
        print(json.dumps({'instrumented_run_count': result['instrumented_run_count'],
                          'production_binary_unchanged': result['production_binary_unchanged']}, indent=2))


if __name__ == '__main__':
    main()
