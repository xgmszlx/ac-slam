#!/usr/bin/python3
"""Replay one v9 common-prefix branch with an exact mid-stream graph cut.

The prefix and suffix are published into the same fresh Karto process.  The
mapper is asked for a graph dump after the prefix publisher exits and before
the suffix publisher starts.  This supplies direct evidence that all action
arms begin from the identical backend state.
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

from common_prefix_signature import build_signature, stream_hash  # noqa: E402
from run_pilot import activated_environment  # noqa: E402
from same_input_replay import (  # noqa: E402
    command_output, load_input_stream, load_json_file, load_mapper_params,
    start_process, stop_process, wait_for_json, write_launch_file,
)


DEFAULT_REPLAY_FLUSH_PERIOD_S = 0.0


def write_records(path, records):
    with open(path, 'w') as stream:
        for record in records:
            stream.write(json.dumps(record, sort_keys=True,
                                    separators=(',', ':')) + '\n')


def wait_for_master(env):
    for _ in range(200):
        if command_output(['rosparam', 'list'], env).returncode == 0:
            return
        time.sleep(0.3)
    raise RuntimeError('ROS master did not become ready')


def publish(env, input_path, rate_hz, log_path):
    process, stream = start_process(
        ['/usr/bin/python3', str(THIS_DIR / 'replay_publisher.py'),
         '--input', str(input_path), '--rate-hz', str(rate_hz)], env, log_path)
    try:
        process.wait(timeout=900)
    finally:
        stream.close()
    if process.returncode != 0:
        raise RuntimeError('replay publisher failed; see {}'.format(log_path))


def request_dump(env, node_name, request, source_path, copy_path):
    source_path = Path(source_path)
    if source_path.exists():
        source_path.unlink()
    result = command_output(
        ['rosparam', 'set', '/{}/pose_graph_dump_request'.format(node_name),
         str(int(request))], env)
    if result.returncode != 0:
        raise RuntimeError('failed to request pose-graph dump: {}'.format(
            result.stdout))
    graph = wait_for_json(source_path, 30.0, 'pose-graph dump request {}'.format(
        request))
    shutil.copy2(source_path, copy_path)
    return graph


def replay_branch(combined_path, prefix_path, mapper_params_path,
                  frozen_target_path, out_dir, rate_hz=20.0,
                  flush_period_s=DEFAULT_REPLAY_FLUSH_PERIOD_S):
    combined_path = Path(combined_path).resolve()
    prefix_path = Path(prefix_path).resolve()
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    records = load_input_stream(combined_path)
    prefix_records = load_input_stream(prefix_path)
    if records[:len(prefix_records)] != prefix_records:
        raise ValueError('combined stream does not begin with exact prefix records')
    suffix_records = records[len(prefix_records):]
    if not suffix_records:
        raise ValueError('branch suffix is empty')

    input_copy = out_dir / 'combined_stream.jsonl'
    shutil.copy2(combined_path, input_copy)
    prefix_copy = out_dir / 'prefix_stream.jsonl'
    shutil.copy2(prefix_path, prefix_copy)
    suffix_path = out_dir / 'probe_suffix.jsonl'
    write_records(suffix_path, suffix_records)

    params = load_mapper_params(mapper_params_path)
    frozen = load_json_file(frozen_target_path)
    dump_work = out_dir / 'graph_current.json'
    provenance_path = out_dir / 'edge_provenance.jsonl'
    launch_path = out_dir / 'mapper.launch'
    write_launch_file(launch_path, params, 'on', dump_work,
                      provenance_path, float(flush_period_s))

    env = activated_environment()
    env['ROS_LOG_DIR'] = str(out_dir / 'ros_logs')
    Path(env['ROS_LOG_DIR']).mkdir(parents=True, exist_ok=True)
    roscore, roscore_stream = start_process(
        ['roscore'], env, out_dir / 'roscore.log')
    launch = launch_stream = None
    try:
        wait_for_master(env)
        launch, launch_stream = start_process(
            ['roslaunch', '--wait', str(launch_path)], env,
            out_dir / 'mapper.log')
        for _ in range(200):
            nodes = command_output(['rosnode', 'list'], env)
            if nodes.returncode == 0 and '/MultiMapper' in nodes.stdout.split():
                break
            time.sleep(0.2)
        else:
            raise RuntimeError('MultiMapper did not become ready')

        publish(env, prefix_copy, rate_hz, out_dir / 'publisher_prefix.log')
        time.sleep(2.0)
        preprobe_graph = request_dump(
            env, 'MultiMapper', 1, dump_work, out_dir / 'graph_preprobe.json')

        publish(env, suffix_path, rate_hz, out_dir / 'publisher_probe.log')
        time.sleep(2.0)
        final_graph = request_dump(
            env, 'MultiMapper', 2, dump_work, out_dir / 'graph_final.json')
    finally:
        stop_process(launch, timeout=30)
        if launch_stream is not None:
            launch_stream.close()
        stop_process(roscore)
        roscore_stream.close()

    signature = build_signature(
        preprobe_graph, frozen['historical_scan_ids'], input_copy,
        len(prefix_records))
    source_prefix_hash, source_prefix_count = stream_hash(prefix_path)
    result = {
        'protocol': 'v9 common-prefix branched replay',
        'combined_stream': str(combined_path),
        'prefix_record_count': len(prefix_records),
        'probe_record_count': len(suffix_records),
        'combined_record_count': len(records),
        'source_prefix_hash': source_prefix_hash,
        'source_prefix_record_count': source_prefix_count,
        'replayed_prefix_hash': signature['input_stream_hash'],
        'prefix_stream_identical': source_prefix_hash == signature['input_stream_hash'],
        'preprobe_signature': signature,
        'preprobe_node_count': len(preprobe_graph['nodes']),
        'preprobe_edge_count': len(preprobe_graph['edges']),
        'final_node_count': len(final_graph['nodes']),
        'final_edge_count': len(final_graph['edges']),
        'accepted_probe_keyscan_count': (len(final_graph['nodes']) -
                                         len(preprobe_graph['nodes'])),
        'new_edge_count': (len(final_graph['edges']) -
                           len(preprobe_graph['edges'])),
        'instrumentation_flush_period_s': float(flush_period_s),
        'mapper_params': params,
        'edge_provenance_path': str(provenance_path),
    }
    with open(out_dir / 'branch_replay_result.json', 'w') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--combined', required=True)
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--mapper-params', required=True)
    parser.add_argument('--frozen-target', required=True)
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--rate-hz', type=float, default=20.0)
    args = parser.parse_args()
    result = replay_branch(
        args.combined, args.prefix, args.mapper_params, args.frozen_target,
        args.out_dir, args.rate_hz)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
