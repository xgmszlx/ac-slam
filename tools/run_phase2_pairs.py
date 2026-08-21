#!/usr/bin/python3
"""Run map3 Prior-TSP vs SLAM-aware pairs with fail-closed controls."""

import argparse
import csv
import datetime
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIVATE = ROOT / 'catkin_ws' / 'activate.sh'
BASELINE = ROOT / 'baseline' / 'Graph-Based_SLAM-Aware_Exploration'
AUTHOR_RESULTS = BASELINE / 'results'
CORE_NODES = {'/Stage', '/Mapper', '/Navigator', '/path_planner', '/Operator', '/pubPath'}


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def activated_environment():
    raw = subprocess.check_output([
        'bash', '-lc', 'source "{}" && env -0'.format(ACTIVATE)
    ])
    env = {}
    for item in raw.split(b'\0'):
        if b'=' in item:
            key, value = item.split(b'=', 1)
            env[key.decode()] = value.decode()
    env['DISPLAY'] = ':0'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    return env


def command_output(command, env, timeout=30):
    return subprocess.run(
        command, env=env, cwd=str(ROOT), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
    )


def wait_for_command(command, env, timeout, description):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            last = command_output(command, env, timeout=10)
        except subprocess.TimeoutExpired:
            last = None
        if last is not None and last.returncode == 0:
            return last.stdout
        time.sleep(1)
    raise RuntimeError('timeout waiting for {}: {}'.format(
        description, last.stdout if last is not None else 'no response'
    ))


def start_process(command, env, log_path):
    stream = open(log_path, 'w', buffering=1)
    process = subprocess.Popen(
        command, env=env, cwd=str(ROOT), stdout=stream,
        stderr=subprocess.STDOUT, text=True, start_new_session=True,
    )
    process._phase2_log_stream = stream
    return process


def stop_process(process, timeout=25):
    if process is None:
        return
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGINT)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                # Hard cleanup is only for this run's known process group.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
    stream = getattr(process, '_phase2_log_stream', None)
    if stream is not None and not stream.closed:
        stream.close()


def parse_action_status(path):
    text = path.read_text(errors='replace')
    statuses = re.findall(r'^\s{2}status:\s*(\d+)\s*$', text, re.MULTILINE)
    return int(statuses[-1]) if statuses else None


def descendants_rss_kb(root_pid):
    completed = subprocess.run(
        ['ps', '-eo', 'pid=,ppid=,rss='], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    rows = []
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) == 3:
            rows.append(tuple(map(int, fields)))
    descendants = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, ppid, _ in rows:
            if ppid in descendants and pid not in descendants:
                descendants.add(pid)
                changed = True
    return sum(rss for pid, _, rss in rows if pid in descendants)


def wait_for_topic_result(process, path, launch, observer, env, timeout, monitor_writer, stage):
    start = time.monotonic()
    next_monitor = 0.0
    max_rss = 0
    while process.poll() is None:
        elapsed = time.monotonic() - start
        if elapsed >= timeout:
            process.terminate()
            process.wait(timeout=10)
            raise RuntimeError('{} hard timeout after {:.1f}s'.format(stage, elapsed))
        if launch.poll() is not None:
            raise RuntimeError('roslaunch exited during {} with code {}'.format(stage, launch.returncode))
        if observer.poll() is not None:
            raise RuntimeError('phase2 observer exited during {} with code {}'.format(stage, observer.returncode))
        if elapsed >= next_monitor:
            nodes = command_output(['rosnode', 'list'], env, timeout=15)
            node_set = set(nodes.stdout.splitlines()) if nodes.returncode == 0 else set()
            missing = sorted(CORE_NODES - node_set)
            rss = descendants_rss_kb(launch.pid)
            max_rss = max(max_rss, rss)
            monitor_writer.writerow([
                now_utc(), stage, '{:.1f}'.format(elapsed), int(launch.poll() is None),
                int(observer.poll() is None), rss, ';'.join(missing),
            ])
            next_monitor += 30.0
        time.sleep(1)
    return max_rss


def write_command_result(command, env, path, timeout=60):
    try:
        completed = command_output(command, env, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        path.write_text('TIMEOUT\n{}\n'.format(exc), encoding='utf-8')
        raise
    path.write_text(completed.stdout, encoding='utf-8')
    if completed.returncode != 0:
        raise RuntimeError('command failed: {}\n{}'.format(command, completed.stdout))
    return completed.stdout


def validate_tsp(run_record, reference_path, validation_path):
    raw = run_record.read_bytes()
    record = json.loads(raw)
    required = {
        key: record.get(key) for key in (
            'solver', 'seed', 'initial_tsp_path', 'full_tsp_path',
            'predicted_tsp_length', 'predicted_full_tsp_length',
        )
    }
    if reference_path.exists():
        reference_raw = reference_path.read_bytes()
        reference = json.loads(reference_raw)
        reference_required = {key: reference.get(key) for key in required}
        matches = required == reference_required and raw == reference_raw
    else:
        reference_path.write_bytes(raw)
        reference_raw = raw
        matches = True
    validation = {
        'matches_pair_reference': matches,
        'record_sha256': hashlib.sha256(raw).hexdigest(),
        'reference_sha256': hashlib.sha256(reference_raw).hexdigest(),
        'compared_fields': list(required),
        'record': required,
    }
    validation_path.write_text(json.dumps(validation, indent=2, sort_keys=True) + '\n')
    if not matches:
        raise RuntimeError('initial TSP mismatch; exploration is blocked before StartMapping')


def copy_author_outputs(suffix, run_dir):
    author_dir = run_dir / 'author_outputs'
    author_dir.mkdir(exist_ok=True)
    for source in sorted(AUTHOR_RESULTS.glob('*{}*'.format(suffix))):
        if source.is_file():
            shutil.copy2(source, author_dir / source.name)
    mappings = {
        'gt_traj{}.txt'.format(suffix): 'trajectory_gt.txt',
        'slam_traj{}.txt'.format(suffix): 'trajectory_slam.txt',
        'graph{}.g2o'.format(suffix): 'pose_graph.g2o',
    }
    for source_name, target_name in mappings.items():
        source = AUTHOR_RESULTS / source_name
        if source.is_file():
            shutil.copy2(source, run_dir / target_name)


def run_one(pair_index, method, seed, pair_dir, env, explore_timeout):
    method_key = 'prior_tsp' if method == 'Prior-TSP' else 'slam_aware'
    only_use_tsp = method == 'Prior-TSP'
    run_dir = pair_dir / method_key
    if run_dir.exists():
        raise RuntimeError('refusing to overwrite existing run directory: {}'.format(run_dir))
    run_dir.mkdir(parents=True)
    suffix = '_Phase2_pair{:02d}_{}_seed{}'.format(
        pair_index, 'PriorTSP' if only_use_tsp else 'SLAMAware', seed
    )
    tsp_source = AUTHOR_RESULTS / 'tsp_record{}.json'.format(suffix)
    if tsp_source.exists():
        raise RuntimeError('refusing to reuse pre-existing author output: {}'.format(tsp_source))

    roscore = observer = launch = mapping_result = explore_result = None
    run_state = {'status': 'RUNNING', 'started_wall_time_utc': now_utc()}
    (run_dir / 'run_state.json').write_text(json.dumps(run_state, indent=2) + '\n')
    monitor_stream = open(run_dir / 'monitor.csv', 'w', newline='', buffering=1)
    monitor = csv.writer(monitor_stream)
    monitor.writerow([
        'wall_time_utc', 'stage', 'elapsed_wall_s', 'launch_alive',
        'observer_alive', 'rss_kb', 'missing_core_nodes',
    ])
    try:
        existing_master = command_output(['rosparam', 'list'], env, timeout=5)
        if existing_master.returncode == 0:
            raise RuntimeError('a ROS master is already running; refusing to mix experiments')

        roscore = start_process(['roscore'], env, run_dir / 'roscore.log')
        wait_for_command(['rosparam', 'list'], env, 60, 'ROS master')
        run_id = write_command_result(
            ['rosparam', 'get', '/run_id'], env, run_dir / 'ros_run_id.txt', timeout=10
        ).strip()
        observer = start_process(
            ['/usr/bin/python3', str(ROOT / 'tools' / 'phase2_observer.py'),
             '--output-dir', str(run_dir)],
            env, run_dir / 'observer.log',
        )
        launch = start_process([
            'roslaunch', 'cpp_solver', 'exploration.launch',
            'suffix:={}'.format(suffix), 'strategy:=MyPlanner',
            'only_use_tsp:={}'.format(str(only_use_tsp).lower()),
            'tsp_seed:={}'.format(seed), 'map_name:=map3/map3',
            'robot_position:=-28.0 -28.0 0', 'map_width:=74.0',
            'need_noise:=false', 'variance:=0',
        ], env, run_dir / 'roslaunch.log')

        deadline = time.monotonic() + 180
        while time.monotonic() < deadline and not tsp_source.is_file():
            if launch.poll() is not None:
                raise RuntimeError('roslaunch exited before TSP record was generated')
            if observer.poll() is not None:
                raise RuntimeError('observer exited before TSP record was generated')
            time.sleep(1)
        if not tsp_source.is_file():
            raise RuntimeError('TSP record was not generated within 180 s')
        shutil.copy2(tsp_source, run_dir / 'tsp_record.json')
        validate_tsp(
            run_dir / 'tsp_record.json', pair_dir / 'initial_tsp_reference.json',
            run_dir / 'tsp_pair_validation.json',
        )

        for service in ('/StartMapping', '/StartExploration', '/prior_graph_service',
                        '/path_plan_service', '/reliable_loop_service'):
            wait_for_command(['rosservice', 'type', service], env, 120, service)
        write_command_result(['rosnode', 'list'], env, run_dir / 'initial_rosnode_list.txt')
        write_command_result(['rosservice', 'list'], env, run_dir / 'initial_rosservice_list.txt')
        write_command_result(['rostopic', 'list'], env, run_dir / 'initial_rostopic_list.txt')

        mapping_result_stream = open(run_dir / 'get_first_map_result.txt', 'w', buffering=1)
        mapping_result = subprocess.Popen(
            ['rostopic', 'echo', '-n', '1', '/GetFirstMap/result'], env=env,
            cwd=str(ROOT), stdout=mapping_result_stream, stderr=subprocess.STDOUT, text=True,
        )
        time.sleep(1)
        write_command_result(
            ['rosservice', 'call', '/StartMapping', '{}'], env,
            run_dir / 'start_mapping_service.txt', timeout=30,
        )
        wait_for_topic_result(
            mapping_result, run_dir / 'get_first_map_result.txt', launch, observer,
            env, 900, monitor, 'mapping',
        )
        mapping_result_stream.close()
        if parse_action_status(run_dir / 'get_first_map_result.txt') != 3:
            raise RuntimeError('GetFirstMap action did not SUCCEED')

        explore_result_stream = open(run_dir / 'explore_result.txt', 'w', buffering=1)
        explore_result = subprocess.Popen(
            ['rostopic', 'echo', '-n', '1', '/Explore/result'], env=env,
            cwd=str(ROOT), stdout=explore_result_stream, stderr=subprocess.STDOUT, text=True,
        )
        time.sleep(1)
        write_command_result(
            ['rosservice', 'call', '/StartExploration', '{}'], env,
            run_dir / 'start_exploration_service.txt', timeout=30,
        )
        max_rss = wait_for_topic_result(
            explore_result, run_dir / 'explore_result.txt', launch, observer,
            env, explore_timeout, monitor, 'exploration',
        )
        explore_result_stream.close()
        if parse_action_status(run_dir / 'explore_result.txt') != 3:
            raise RuntimeError('Explore action did not SUCCEED')

        # Allow the next periodic Karto marker to close any pending loop snapshot.
        marker_wait_start = time.monotonic()
        while time.monotonic() - marker_wait_start < 7:
            if launch.poll() is not None or observer.poll() is not None:
                break
            time.sleep(1)
        write_command_result(
            ['rosrun', 'map_server', 'map_saver', '-f', str(run_dir / 'final_map')],
            env, run_dir / 'map_saver.log', timeout=90,
        )
        for command, filename in (
            (['rosnode', 'list'], 'final_rosnode_list.txt'),
            (['rosservice', 'list'], 'final_rosservice_list.txt'),
            (['rostopic', 'list'], 'final_rostopic_list.txt'),
        ):
            write_command_result(command, env, run_dir / filename)

        stop_process(observer)
        observer = None
        stop_process(launch)
        launch = None
        stop_process(roscore)
        roscore = None

        rosout_source = Path(env['ROS_LOG_DIR']) / run_id / 'rosout.log'
        if rosout_source.is_file():
            shutil.copy2(rosout_source, run_dir / 'rosout.log')
        copy_author_outputs(suffix, run_dir)
        if not (run_dir / 'trajectory_gt.txt').is_file() or not (run_dir / 'trajectory_slam.txt').is_file():
            raise RuntimeError('trajectory outputs are missing after successful action')

        eval_command = [
            '/usr/bin/python3', str(ROOT / 'tools' / 'evaluate_slam_run.py'),
            '--gt', str(run_dir / 'trajectory_gt.txt'),
            '--slam', str(run_dir / 'trajectory_slam.txt'),
            '--output-dir', str(run_dir / 'evo'),
            '--loops-json', str(run_dir / 'loops.json'),
        ]
        write_command_result(eval_command, env, run_dir / 'evo_evaluation.log', timeout=900)
        write_command_result([
            '/usr/bin/python3', str(ROOT / 'tools' / 'finalize_phase2_run.py'),
            '--run-dir', str(run_dir),
        ], env, run_dir / 'finalize.log', timeout=120)

        commit = subprocess.check_output(
            ['git', '-C', str(BASELINE), 'rev-parse', 'HEAD'], text=True
        ).strip()
        manifest = {
            'method': method, 'map': 'map3', 'pair_index': pair_index,
            'start_pose_xyyaw': [-28.0, -28.0, 0.0], 'git_commit': commit,
            'launch_file': 'cpp_solver exploration.launch',
            'launch_arguments': {
                'strategy': 'MyPlanner', 'only_use_tsp': only_use_tsp,
                'map_name': 'map3/map3', 'tsp_solver': 'concorde',
                'tsp_seed': seed, 'need_noise': False, 'variance': 0,
                'suffix': suffix,
            },
            'python': '/usr/bin/python3 3.8.10', 'evo': '1.31.1',
            'observer': 'tools/phase2_observer.py (passive)',
            'stdout_stderr': 'roslaunch.log', 'max_process_tree_rss_kb': max_rss,
            'initial_tsp_gate': 'tsp_pair_validation.json',
        }
        (run_dir / 'manifest.json').write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + '\n'
        )
        run_state.update({'status': 'SUCCEEDED', 'finished_wall_time_utc': now_utc()})
        (run_dir / 'run_state.json').write_text(json.dumps(run_state, indent=2) + '\n')
        return max_rss
    except Exception as exc:
        run_state.update({
            'status': 'FAILED', 'finished_wall_time_utc': now_utc(),
            'reason': '{}: {}'.format(type(exc).__name__, exc),
        })
        (run_dir / 'run_state.json').write_text(json.dumps(run_state, indent=2) + '\n')
        raise
    finally:
        for process in (mapping_result, explore_result):
            if process is not None and process.poll() is None:
                process.terminate()
        stop_process(observer)
        stop_process(launch)
        stop_process(roscore)
        monitor_stream.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pairs', type=int, default=5)
    parser.add_argument('--start-pair', type=int, default=1)
    parser.add_argument('--explore-timeout', type=int, default=2700)
    parser.add_argument(
        '--output-root', type=Path,
        default=ROOT / 'results' / 'phase2' / 'map3_pairs',
    )
    args = parser.parse_args()
    if args.pairs < 1 or args.start_pair < 1 or args.start_pair + args.pairs - 1 > 5:
        raise SystemExit('the fixed Phase 2 design contains pair indices 1..5')
    env = activated_environment()
    args.output_root.mkdir(parents=True, exist_ok=True)
    suite_state_path = args.output_root / 'suite_state.json'
    requested_end = args.start_pair + args.pairs - 1
    if suite_state_path.is_file():
        state = json.loads(suite_state_path.read_text())
        previous_range = state.get('pair_range', [args.start_pair, requested_end])
        state['pair_range'] = [min(previous_range[0], args.start_pair), max(previous_range[1], requested_end)]
        state['seeds'] = sorted(set(state.get('seeds', [])) | {
            21000 + index for index in range(args.start_pair, requested_end + 1)
        })
        state['status'] = 'RUNNING'
        state.pop('finished_wall_time_utc', None)
        state.pop('reason', None)
        state['resumed_wall_time_utc'] = now_utc()
    else:
        state = {
            'status': 'RUNNING', 'started_wall_time_utc': now_utc(),
            'pair_range': [args.start_pair, requested_end],
            'seeds': [21000 + index for index in range(args.start_pair, requested_end + 1)],
            'order_rule': 'odd pairs Prior-TSP then SLAM-aware; even pairs reverse order',
            'completed_runs': [],
        }
    suite_state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + '\n')
    try:
        for pair_index in range(args.start_pair, args.start_pair + args.pairs):
            seed = 21000 + pair_index
            pair_dir = args.output_root / 'pair_{:02d}'.format(pair_index)
            pair_dir.mkdir(parents=True, exist_ok=True)
            order = (
                ['Prior-TSP', 'Graph-Based SLAM-aware'] if pair_index % 2 == 1
                else ['Graph-Based SLAM-aware', 'Prior-TSP']
            )
            for method in order:
                max_rss = run_one(
                    pair_index, method, seed, pair_dir, env, args.explore_timeout
                )
                state['completed_runs'].append({
                    'pair': pair_index, 'method': method,
                    'finished_wall_time_utc': now_utc(), 'max_rss_kb': max_rss,
                })
                suite_state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + '\n')
    except Exception as exc:
        state.update({
            'status': 'FAILED', 'finished_wall_time_utc': now_utc(),
            'reason': '{}: {}'.format(type(exc).__name__, exc),
            'retry_policy': 'no automatic retry; raw failed run preserved',
        })
        suite_state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + '\n')
        raise
    state.update({'status': 'SUCCEEDED', 'finished_wall_time_utc': now_utc()})
    suite_state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
