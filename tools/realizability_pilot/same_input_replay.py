#!/usr/bin/python3
"""Same-input Karto replay: does the instrumentation change the graph?

The online matched-pair experiment cannot certify instrumentation neutrality,
because two online runs share a seed, a route and a probe but not a bit-identical
input stream.  This harness removes that ambiguity by replaying one recorded
mapper input stream (`/karto_in` messages) into the Karto constraint-generation
subsystem twice:

* ``off``: provenance instrument disabled;
* ``on``:  buffered provenance instrument enabled.

Only the mapper runs.  No Stage, no planner, no localizer: the recorded stream
already carries the localized poses that the mapper consumes, so the replay
isolates exactly the subsystem whose neutrality is in question.

Each arm is replayed twice, so the comparison can separate *replay
nondeterminism* (off1 vs off2) from the *instrument effect* (off vs on).  The
tolerance used by the verdict is the pre-registered numerical floor widened by
the measured replay repeatability, never a hand-picked constant.

Usage::

    same_input_replay.py --input <karto_input.jsonl> \
        --mapper-params <mapper_params.yaml> --out-dir <dir> [--runs 2]

The per-run graph dumps come from the mapper's own ``pose_graph_dump_path``
instrument, which is written by both arms and is independent of the provenance
instrument.
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

ROOT = THIS_DIR.parents[1]
ROS_SETUP = ROOT / 'catkin_ws' / 'devel' / 'setup.bash'

ARMS = ('off', 'on')

#: Only these mapper parameters are carried over from the recorded episode.  A
#: whitelist keeps the replay honest: the same Karto configuration as the online
#: run, with nothing else inherited.
PARAM_WHITELIST = (
    'LoopMatchMaximumVarianceCoarse',
    'LoopMatchMinimumChainSize',
    'LoopMatchMinimumResponseCoarse',
    'LoopMatchMinimumResponseFine',
    'LoopSearchMaximumDistance',
    'MinimumTravelDistance',
    'MinimumTravelHeading',
    'grid_resolution',
    'max_covariance',
    'min_map_size',
    'range_threshold',
)


def load_mapper_params(path):
    """Read the JSON-ish ROS parameter dump written by the episode runner."""
    values = {}
    with open(path) as stream:
        for line in stream:
            if ':' not in line:
                continue
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()
            if key not in PARAM_WHITELIST:
                continue
            try:
                values[key] = float(value)
            except ValueError:
                values[key] = value
    return values


def load_input_stream(path):
    records = []
    with open(path) as stream:
        for line in stream:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records



def load_json_file(path):
    with open(path) as stream:
        return json.load(stream)


def write_launch_file(path, params, arm, dump_path, provenance_path, period_s):
    lines = ['<launch>', '  <node name="MultiMapper" pkg="nav2d_karto" '
             'type="mapper" output="log">']
    for key, value in sorted(params.items()):
        lines.append('    <param name="{}" value="{}" />'.format(key, value))
    lines.append('    <param name="publish_pose_graph" value="false" />')
    lines.append('    <param name="robot_id" value="1" />')
    lines.append('    <param name="instrumentation_flush_period_s" '
                 'value="{}" />'.format(period_s))
    lines.append('    <param name="pose_graph_dump_path" value="{}" />'
                 .format(dump_path))
    if arm == 'on':
        lines.append('    <param name="enable_edge_provenance" value="true" />')
        lines.append('    <param name="edge_provenance_path" value="{}" />'
                     .format(provenance_path))
        lines.append('    <param name="edge_provenance_run_id" '
                     'value="replay_{}" />'.format(arm))
    else:
        lines.append('    <param name="enable_edge_provenance" value="false" />')
    lines.append('  </node>')
    lines.append('</launch>')
    Path(path).write_text('\n'.join(lines) + '\n')


def command_output(command, env, timeout=10):
    return subprocess.run(command, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, timeout=timeout)


def start_process(command, env, log_path):
    stream = open(log_path, 'w')
    return subprocess.Popen(command, env=env, cwd=str(ROOT), stdout=stream,
                            stderr=subprocess.STDOUT, text=True,
                            start_new_session=True), stream


def stop_process(process, timeout=15):
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGINT)
    except Exception:
        process.terminate()
    deadline = time.time() + timeout
    while time.time() < deadline and process.poll() is None:
        time.sleep(0.2)
    if process.poll() is None:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except Exception:
            process.kill()


def wait_for_json(path, timeout, description):
    """Wait until a dump file is complete and parseable.

    The dump is written with truncation and then streamed, so a plain existence
    check can observe an empty file; the parse check makes the wait safe.
    """
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        candidate = Path(path)
        if candidate.is_file() and candidate.stat().st_size > 0:
            try:
                with open(candidate) as stream:
                    return json.load(stream)
            except ValueError as exc:  # partially written
                last_error = exc
        time.sleep(0.25)
    raise RuntimeError('timed out waiting for {} ({})'.format(description,
                                                              last_error))


def run_single_replay(env, records, params, arm, out_dir, rate_hz, run_index,
                      flush_period_s=1.0):
    """One replay of the recorded stream under one instrument configuration."""
    run_dir = Path(out_dir) / 'runs'
    run_dir.mkdir(parents=True, exist_ok=True)
    # roslaunch starts nodes with its own cwd, so every path handed to the
    # mapper must be absolute.
    run_dir = run_dir.resolve()
    dump_path = (run_dir / 'graph_{}_{}.json'.format(arm, run_index)).resolve()
    provenance_path = run_dir / 'provenance_{}_{}.jsonl'.format(arm, run_index)
    if dump_path.exists():
        dump_path.unlink()
    if provenance_path.exists():
        provenance_path.unlink()
    launch_file = run_dir / 'mapper_{}_{}.launch'.format(arm, run_index)
    write_launch_file(launch_file, params, arm, dump_path, provenance_path,
                      float(flush_period_s))

    launch, launch_stream = start_process(
        ['roslaunch', '--wait', str(launch_file)], env,
        run_dir / 'roslaunch_{}_{}.log'.format(arm, run_index))
    try:
        for _ in range(100):
            if command_output(['rosnode', 'list'], env).returncode == 0:
                break
            time.sleep(0.3)
        publisher = start_process(
            ['/usr/bin/python3', str(THIS_DIR / 'replay_publisher.py'),
             '--input', str(Path(out_dir) / 'karto_input.jsonl'),
             '--rate-hz', str(rate_hz)],
            env, run_dir / 'publisher_{}_{}.log'.format(arm, run_index))
        publisher_stream = publisher[1]
        publisher_process = publisher[0]
        publisher_process.wait(timeout=600)
        publisher_stream.close()
        if publisher_process.returncode != 0:
            raise RuntimeError('replay publisher failed for arm {} run {}'.format(
                arm, run_index))
        # Let the mapper drain its subscription queue.
        time.sleep(2.0)
    finally:
        # Shutting the mapper down gracefully is what triggers the graph dump:
        # the dump is written from the mapper's own thread (at the end of a
        # processed scan or during teardown), never from a foreign thread, so a
        # clean SIGINT is part of the protocol.
        stop_process(launch, timeout=30)
        launch_stream.close()

    if not Path(dump_path).is_file():
        raise RuntimeError('no graph dump was written for arm {} run {}; see {}'
                           .format(arm, run_index,
                                   run_dir / 'roslaunch_{}_{}.log'.format(arm, run_index)))
    graph = load_json_file(dump_path)
    return {
        'arm': arm,
        'dump_path': str(dump_path),
        'provenance_path': str(provenance_path),
        'graph': graph,
    }


def replay(input_path, mapper_params_path, out_dir, runs, rate_hz):
    env = dict(os.environ)
    env['ROS_LOG_DIR'] = str(Path(out_dir) / 'ros_logs')
    Path(env['ROS_LOG_DIR']).mkdir(parents=True, exist_ok=True)
    records = load_input_stream(input_path)
    params = load_mapper_params(mapper_params_path)
    shutil.copy2(input_path, Path(out_dir) / 'karto_input.jsonl')

    results = []
    roscore, roscore_stream = start_process(['roscore'], env,
                                            Path(out_dir) / 'roscore.log')
    try:
        for _ in range(200):
            if command_output(['rosparam', 'list'], env).returncode == 0:
                break
            time.sleep(0.3)
        for index in range(runs):
            for arm in ARMS:
                outcome = run_single_replay(env, records, params, arm, out_dir,
                                            rate_hz, index)
                outcome['run_index'] = index
                results.append(outcome)
    finally:
        stop_process(roscore)
        roscore_stream.close()

    payload = {
        'input_stream': str(input_path),
        'input_message_count': len(records),
        'mapper_params_source': str(mapper_params_path),
        'mapper_params_used': params,
        'replay_rate_hz': rate_hz,
        'runs_per_arm': runs,
        'results': [{key: value for key, value in result.items()
                     if key != 'graph'} for result in results],
    }
    with open(Path(out_dir) / 'replay_run_summary.json', 'w') as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, default=str)
        stream.write('\n')
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True,
                        help='recorded karto_in JSONL')
    parser.add_argument('--mapper-params', required=True,
                        help='mapper_params.yaml from the recording episode')
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--runs', type=int, default=2,
                        help='replays per instrument arm')
    parser.add_argument('--rate-hz', type=float, default=20.0)
    args = parser.parse_args()
    results = replay(args.input, args.mapper_params, args.out_dir, args.runs,
                     args.rate_hz)
    print(json.dumps({'runs': len(results),
                      'out_dir': args.out_dir}, indent=2))


if __name__ == '__main__':
    main()
