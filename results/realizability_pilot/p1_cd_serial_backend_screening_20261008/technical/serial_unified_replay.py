#!/usr/bin/python3
"""Isolated SERIAL_KARTO_CANDIDATE prefix-only technical replay.

No fixed drain sleep is used.  The publisher exits only after publishing the
exact stream; the harness then waits for the mapper's completed-callback count
and invokes a synchronous dump service on the mapper callback thread.
"""

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

SCREEN = Path(__file__).resolve().parents[1]
ROOT = SCREEN.parents[2]
THIS_DIR = ROOT / 'tools' / 'realizability_pilot'
sys.path.insert(0, str(THIS_DIR))

from common_prefix_signature import stream_hash  # noqa: E402
from same_input_replay import load_input_stream, load_mapper_params  # noqa: E402
from v13_prefix_equivalence import (check_final_prefix_preservation,
                                    compare_graphs,
                                    structural_signature)  # noqa: E402

CANDIDATE_WS = Path(os.environ.get('CD_SERIAL_WS', str(SCREEN / 'isolated_catkin'))).resolve()


def activated_environment():
    raw = subprocess.check_output([
        'bash', '-lc', 'source /opt/ros/noetic/setup.bash && source "{}" && env -0'.format(
            CANDIDATE_WS / 'devel/setup.bash')])
    env = dict(item.decode().split('=', 1) for item in raw.split(b'\0')
               if b'=' in item)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    return env


def _write_json(path, payload):
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')


def _write_records(path, records):
    with open(path, 'w') as stream:
        for row in records:
            stream.write(json.dumps(row, sort_keys=True,
                                    separators=(',', ':')) + '\n')


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _mapper_resource_monitor(launch_process):
    expected = (CANDIDATE_WS / 'devel/lib/nav2d_karto/mapper').resolve()
    descendants = psutil.Process(launch_process.pid).children(recursive=True)
    matches = [p for p in descendants if p.is_running() and
               Path(p.exe()).resolve() == expected]
    if len(matches) != 1:
        raise RuntimeError('expected exactly one isolated mapper child; found {}'.format(
            [(p.pid, p.exe()) for p in matches]))
    process = matches[0]
    mapped_paths = sorted({line.rsplit(None, 1)[-1] for line in
                           Path('/proc/{}/maps'.format(process.pid)).read_text().splitlines()
                           if '/' in line.rsplit(None, 1)[-1]})
    stop = threading.Event()
    record = {'pid': process.pid, 'executable': process.exe(),
              'executable_sha256': _sha(expected),
              'mapped_paths': mapped_paths,
              'peak_mapper_rss_bytes': process.memory_info().rss,
              'mapper_cpu_user_s': 0.0, 'mapper_cpu_system_s': 0.0}

    def sample():
        while not stop.is_set():
            try:
                record['peak_mapper_rss_bytes'] = max(
                    record['peak_mapper_rss_bytes'], process.memory_info().rss)
                cpu = process.cpu_times()
                record['mapper_cpu_user_s'] = cpu.user
                record['mapper_cpu_system_s'] = cpu.system
            except psutil.Error:
                break
            stop.wait(0.05)

    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    return stop, thread, record


def _free_port():
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _run(command, env, timeout=20):
    return subprocess.run(command, env=env, cwd=str(ROOT), text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=timeout)


def _start(command, env, log_path):
    stream = open(log_path, 'w')
    process = subprocess.Popen(command, env=env, cwd=str(ROOT), stdout=stream,
                               stderr=subprocess.STDOUT, text=True,
                               start_new_session=True)
    return process, stream


def _stop(process, timeout=20):
    if process is None or process.poll() is not None:
        return
    os.killpg(process.pid, 2)
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, 15)
        process.wait(timeout=5)


def _wait_for(env, command, predicate, label, timeout=60.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = _run(command, env, timeout=10)
        if predicate(last):
            return last
        time.sleep(0.1)
    raise RuntimeError('{} did not become ready; last={}'.format(
        label, last.stdout if last else None))


def _write_launch(path, params, dump_path, provenance_path):
    lines = ['<launch>',
             '  <node name="MultiMapper" pkg="nav2d_karto" '
             'type="mapper" output="log">']
    for key, value in sorted(params.items()):
        lines.append('    <param name="{}" value="{}" />'.format(key, value))
    lines.extend([
        '    <param name="publish_pose_graph" value="false" />',
        '    <param name="robot_id" value="1" />',
        '    <param name="instrumentation_flush_period_s" value="0" />',
        '    <param name="pose_graph_dump_path" value="{}" />'.format(dump_path),
        '    <param name="enable_edge_provenance" value="true" />',
        '    <param name="edge_provenance_path" value="{}" />'.format(
            provenance_path),
        '    <param name="edge_provenance_run_id" value="cd_serial_technical" />',
        '  </node>', '</launch>'])
    Path(path).write_text('\n'.join(lines) + '\n')


def _publish(env, input_path, rate_hz, out_dir, label):
    status_path = out_dir / 'publisher_{}_status.json'.format(label)
    process, stream = _start([
        '/usr/bin/python3', str(THIS_DIR / 'v13_replay_publisher.py'),
        '--input', str(input_path), '--rate-hz', str(rate_hz),
        '--status-out', str(status_path)], env,
        out_dir / 'publisher_{}.log'.format(label))
    try:
        process.wait(timeout=900)
    finally:
        stream.close()
    if process.returncode != 0 or not status_path.is_file():
        raise RuntimeError('{} publisher failed'.format(label))
    status = json.loads(status_path.read_text())
    if not status['connection_confirmed'] or status['published'] != status['expected']:
        raise RuntimeError('{} publisher did not complete exactly'.format(label))
    return status


def _processed_count(env):
    result = _run(['rosservice', 'call',
                   '/MultiMapper/get_processed_localized_scan_count', '{}'],
                  env, timeout=10)
    if result.returncode != 0:
        raise RuntimeError('count service failed: ' + result.stdout)
    for line in result.stdout.splitlines():
        if line.startswith('message:'):
            return int(line.split(':', 1)[1].strip().strip('"'))
    raise RuntimeError('could not parse count service: ' + result.stdout)


def _wait_count(env, expected, timeout=120.0):
    deadline = time.time() + timeout
    observed = None
    while time.time() < deadline:
        observed = _processed_count(env)
        if observed == expected:
            return observed
        if observed > expected:
            raise RuntimeError('processed count {} exceeded expected {}'.format(
                observed, expected))
        time.sleep(0.05)
    raise RuntimeError('processed count {} did not reach {}'.format(observed,
                                                                    expected))


def _dump(env, path):
    if path.exists():
        path.unlink()
    set_result = _run(['rosparam', 'set',
                       '/MultiMapper/pose_graph_dump_path', str(path)], env)
    if set_result.returncode != 0:
        raise RuntimeError('failed to set dump path: ' + set_result.stdout)
    result = _run(['rosservice', 'call', '/MultiMapper/dump_pose_graph_now', '{}'],
                  env, timeout=60)
    if result.returncode != 0 or 'success: True' not in result.stdout:
        raise RuntimeError('synchronous dump failed: ' + result.stdout)
    deadline = time.time() + 10.0
    while time.time() < deadline:
        if path.is_file():
            with open(path) as stream:
                return json.load(stream), result.stdout
        time.sleep(0.05)
    raise RuntimeError('dump service succeeded without output file')


def evaluate_prefix_reference(reference_graph, observed_graph, target_ids=None):
    """Apply zero tolerance to legacy six-decimal graph JSON semantics."""
    comparison = compare_graphs(six_decimal_semantics(reference_graph),
                                six_decimal_semantics(observed_graph),
                                target_ids=target_ids)
    comparison['zero_tolerance_required'] = True
    comparison['passed'] = bool(
        comparison['structural']['exact'] and
        comparison['numerical']['exact'])
    return comparison


def six_decimal_semantics(value):
    if isinstance(value, list):
        return [six_decimal_semantics(item) for item in value]
    if isinstance(value, dict):
        return {key: six_decimal_semantics(item) for key, item in value.items()}
    if isinstance(value, float):
        return float('%.6f' % value)
    return value


def unified_replay(prefix_path, mapper_params_path, out_dir, rate_hz=20.0,
                   combined_path=None, target_ids=None,
                   prefix_reference_path=None):
    if combined_path is not None:
        raise ValueError('CD-A1 forbids any combined stream or suffix')
    prefix_path = Path(prefix_path).resolve()
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix_records = load_input_stream(prefix_path)
    combined_records = None
    suffix_records = []
    if combined_path:
        combined_records = load_input_stream(combined_path)
        if combined_records[:len(prefix_records)] != prefix_records:
            raise ValueError('combined stream prefix is not exactly canonical')
        suffix_records = combined_records[len(prefix_records):]
        if not suffix_records:
            raise ValueError('branch suffix is empty')

    prefix_copy = out_dir / 'canonical_prefix.jsonl'
    shutil.copy2(prefix_path, prefix_copy)
    suffix_path = None
    if suffix_records:
        suffix_path = out_dir / 'probe_suffix.jsonl'
        _write_records(suffix_path, suffix_records)
        shutil.copy2(combined_path, out_dir / 'combined_stream.jsonl')

    params = load_mapper_params(mapper_params_path)
    params_sha = hashlib.sha256(json.dumps(
        params, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    dump_work = out_dir / 'graph_work.json'
    provenance = out_dir / 'edge_provenance.jsonl'
    launch_path = out_dir / 'mapper.launch'
    _write_launch(launch_path, params, dump_work, provenance)

    env = activated_environment()
    port = _free_port()
    env['ROS_MASTER_URI'] = 'http://127.0.0.1:{}'.format(port)
    env['ROS_HOSTNAME'] = '127.0.0.1'
    env['ROS_LOG_DIR'] = str(out_dir / 'ros_logs')
    Path(env['ROS_LOG_DIR']).mkdir(parents=True, exist_ok=True)
    roscore, roscore_stream = _start(['roscore', '-p', str(port)], env,
                                     out_dir / 'roscore.log')
    mapper = mapper_stream = None
    timeline = []
    monitor_stop = monitor_thread = runtime_record = None
    replay_start = time.monotonic()
    try:
        _wait_for(env, ['rosparam', 'list'], lambda x: x.returncode == 0,
                  'fresh ROS master')
        timeline.append('fresh_ros_master_ready')
        mapper, mapper_stream = _start(
            ['roslaunch', '--wait', str(launch_path)], env,
            out_dir / 'mapper.log')
        _wait_for(env, ['rosnode', 'list'],
                  lambda x: (x.returncode == 0 and
                             '/MultiMapper' in x.stdout.split()),
                  'fresh MultiMapper')
        _wait_for(env, ['rosservice', 'list'],
                  lambda x: (x.returncode == 0 and
                             '/MultiMapper/dump_pose_graph_now' in x.stdout and
                             '/MultiMapper/get_processed_localized_scan_count'
                             in x.stdout), 'v13 synchronous services')
        timeline.append('fresh_multimapper_and_services_ready')
        monitor_stop, monitor_thread, runtime_record = _mapper_resource_monitor(mapper)

        prefix_publish = _publish(env, prefix_copy, rate_hz, out_dir, 'prefix')
        timeline.extend(['publisher_subscriber_connection_confirmed',
                         'exact_prefix_published'])
        prefix_count = len(prefix_records)
        observed_prefix_count = _wait_count(env, prefix_count)
        timeline.append('processed_count_equals_expected_prefix_count')
        pre_graph_path = out_dir / 'graph_pre.json'
        pre_graph, dump_response = _dump(env, pre_graph_path)
        timeline.append('synchronous_G_pre_saved')

        prefix_reference_comparison = None
        prefix_gate_passed = True
        if prefix_reference_path is not None:
            reference_graph = json.loads(Path(prefix_reference_path).read_text())
            prefix_reference_comparison = evaluate_prefix_reference(
                reference_graph, pre_graph, target_ids=target_ids)
            prefix_gate_passed = prefix_reference_comparison['passed']
            timeline.append('frozen_prefix_reference_' +
                            ('passed' if prefix_gate_passed else 'failed'))

        final_graph = None
        final_preservation = None
        suffix_publish = None
        observed_final_count = None
        if suffix_path is not None and prefix_gate_passed:
            suffix_publish = _publish(env, suffix_path, rate_hz, out_dir, 'suffix')
            observed_final_count = _wait_count(
                env, len(prefix_records) + len(suffix_records))
            final_graph, _ = _dump(env, out_dir / 'graph_final.json')
            final_preservation = check_final_prefix_preservation(pre_graph,
                                                                  final_graph)
            timeline.extend(['exact_suffix_published',
                             'processed_count_equals_expected_total_count',
                             'synchronous_final_graph_saved'])
    finally:
        if monitor_stop is not None:
            monitor_stop.set()
            monitor_thread.join(timeout=2)
        _stop(mapper, timeout=30)
        if mapper_stream is not None:
            mapper_stream.close()
        _stop(roscore)
        roscore_stream.close()

    input_sha, input_count = stream_hash(prefix_copy)
    binary_path = CANDIDATE_WS / 'devel/lib/nav2d_karto/mapper'
    code_provenance = {
        'git_head': _run(['git', 'rev-parse', 'HEAD'], env=os.environ.copy()).stdout.strip(),
        'mapper_binary_path': str(binary_path),
        'mapper_binary_sha256': _sha(binary_path),
        'mapper_launch_sha256': _sha(launch_path),
    }
    signature = structural_signature(
        pre_graph, target_ids=target_ids, input_sha=input_sha,
        input_count=input_count, mapper_config_sha=params_sha,
        code_provenance=code_provenance)
    result = {
        'protocol': 'CD-A0/A1 isolated serial prefix-only replay v1',
        'elapsed_wall_s': time.monotonic() - replay_start,
        'mapper_runtime': runtime_record,
        'mode': 'branch' if suffix_records else 'prefix_only',
        'status': (
            'TECHNICAL_INVALID_PREFIX_PRETREATMENT'
            if suffix_records and not prefix_gate_passed else
            'REPLAY_COMPLETE'),
        'timeline': timeline,
        'fixed_sleep_used_as_drain_barrier': False,
        'background_graph_dump_used': False,
        'prefix_record_count': len(prefix_records),
        'processed_prefix_count': observed_prefix_count,
        'prefix_publisher': prefix_publish,
        'prefix_input_sha256': input_sha,
        'prefix_structural_signature': signature,
        'prefix_graph_file_sha256': _sha(pre_graph_path),
        'prefix_reference_path': (str(Path(prefix_reference_path).resolve())
                                  if prefix_reference_path is not None else None),
        'prefix_reference_sha256': (_sha(prefix_reference_path)
                                    if prefix_reference_path is not None else None),
        'prefix_reference_comparison': prefix_reference_comparison,
        'prefix_gate_passed': prefix_gate_passed,
        'suffix_publication_authorized': bool(
            suffix_path is not None and prefix_gate_passed),
        'suffix_published': suffix_publish is not None,
        'mapper_params_sha256': params_sha,
        'code_provenance': code_provenance,
        'dump_service_response': dump_response,
        'suffix_record_count': len(suffix_records),
        'processed_final_count': observed_final_count,
        'suffix_publisher': suffix_publish,
        'final_prefix_structural_preservation': final_preservation,
    }
    _write_json(out_dir / 'unified_replay_result.json', result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--mapper-params', required=True)
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--rate-hz', type=float, default=20.0)
    parser.add_argument('--combined')
    parser.add_argument('--prefix-reference')
    parser.add_argument('--target-ids', nargs='*', type=int, default=[])
    args = parser.parse_args()
    result = unified_replay(
        args.prefix, args.mapper_params, args.out_dir, args.rate_hz,
        combined_path=args.combined, target_ids=args.target_ids,
        prefix_reference_path=args.prefix_reference)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
