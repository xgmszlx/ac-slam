#!/usr/bin/python3
"""Replay one canonical history twice in fresh Karto processes."""

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

from common_prefix_signature import build_signature  # noqa: E402
from replay_compare import compare_graphs  # noqa: E402
from run_pilot import activated_environment  # noqa: E402
from same_input_replay import (  # noqa: E402
    command_output, load_input_stream, load_json_file, load_mapper_params,
    run_single_replay, start_process, stop_process,
)


# The certified replay configuration performs no provenance I/O while Karto is
# processing.  v12 accidentally used 1.0 s here while branch replay used 0.2 s,
# so identical prefix bytes did not receive an identical wrapper configuration.
DEFAULT_REPLAY_FLUSH_PERIOD_S = 0.0


def replay(input_path, mapper_params_path, frozen_target_path, out_dir,
           runs=2, rate_hz=20.0,
           flush_period_s=DEFAULT_REPLAY_FLUSH_PERIOD_S):
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    input_path = Path(input_path).resolve()
    frozen_target_path = Path(frozen_target_path).resolve()
    shutil.copy2(input_path, out_dir / 'karto_input.jsonl')
    records = load_input_stream(input_path)
    params = load_mapper_params(mapper_params_path)
    frozen = load_json_file(frozen_target_path)
    env = activated_environment()
    env['ROS_LOG_DIR'] = str(out_dir / 'ros_logs')
    Path(env['ROS_LOG_DIR']).mkdir(parents=True, exist_ok=True)

    outcomes = []
    roscore, roscore_stream = start_process(['roscore'], env, out_dir / 'roscore.log')
    try:
        for _ in range(200):
            if command_output(['rosparam', 'list'], env).returncode == 0:
                break
            time.sleep(0.3)
        else:
            raise RuntimeError('ROS master did not become ready')
        for index in range(int(runs)):
            outcome = run_single_replay(
                env, records, params, 'on', out_dir, float(rate_hz), index,
                flush_period_s=float(flush_period_s))
            signature = build_signature(
                outcome['graph'], frozen['historical_scan_ids'],
                out_dir / 'karto_input.jsonl')
            outcome['signature'] = signature
            outcome.pop('graph')
            outcomes.append(outcome)
    finally:
        stop_process(roscore)
        roscore_stream.close()

    graphs = [load_json_file(item['dump_path']) for item in outcomes]
    comparisons = [compare_graphs(graphs[0], graph) for graph in graphs[1:]]
    hashes = [item['signature']['preprobe_graph_hash'] for item in outcomes]
    input_hashes = [item['signature']['input_stream_hash'] for item in outcomes]
    exact = (len(set(hashes)) == 1 and len(set(input_hashes)) == 1 and
             all(comparison['node_ids_equal'] and
                 comparison['node_unique_ids_equal'] and
                 comparison['edge_pair_sequence_equal'] and
                 comparison['node_pose_max_difference'] == 0.0 and
                 comparison['edge_measurement_max_difference'] == 0.0 and
                 comparison['edge_covariance_max_difference'] == 0.0
                 for comparison in comparisons))
    payload = {
        'protocol': 'v9 common-prefix deterministic replay',
        'input_record_count': len(records),
        'runs_requested': int(runs),
        'instrumentation_flush_period_s': float(flush_period_s),
        'runs': outcomes,
        'comparisons_to_run_0': comparisons,
        'preprobe_graph_hashes': hashes,
        'input_stream_hashes': input_hashes,
        'exact_identity': exact,
        'verdict': ('COMMON_PREFIX_REPLAY_PASS' if exact
                    else 'COMMON_PREFIX_REPLAY_INVALID'),
    }
    with open(out_dir / 'common_prefix_replay_result.json', 'w') as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write('\n')
    with open(out_dir / 'common_prefix_signature.json', 'w') as stream:
        json.dump(outcomes[0]['signature'], stream, indent=2, sort_keys=True)
        stream.write('\n')
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--mapper-params', required=True)
    parser.add_argument('--frozen-target', required=True)
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--runs', type=int, default=2)
    parser.add_argument('--rate-hz', type=float, default=20.0)
    args = parser.parse_args()
    payload = replay(args.input, args.mapper_params, args.frozen_target,
                     args.out_dir, args.runs, args.rate_hz)
    print(json.dumps({'verdict': payload['verdict'],
                      'preprobe_graph_hashes': payload['preprobe_graph_hashes']},
                     indent=2, sort_keys=True))
    if not payload['exact_identity']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
