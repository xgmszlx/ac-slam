#!/usr/bin/python3
"""Run Phase 2C map3 SLAM-aware mechanism-replication runs with Karto loop diagnostics.

Five runs, seeds 21001..21005, Graph-Based SLAM-aware only, same map3 / start pose /
Concorde seed as Phase 2A. Each run writes to results/phase2c/map3/seed_XXXXX/ with
the observation-only karto_loop_diagnostics.jsonl enabled. The initial TSP is
validated against the Phase 2A pair reference; if it cannot be reproduced exactly,
the run is marked not_exact_phase2a_rerun instead of being silently retried.
"""

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

from run_phase2_pairs import (
    AUTHOR_RESULTS,
    BASELINE,
    CORE_NODES,
    ROOT,
    activated_environment,
    command_output,
    copy_author_outputs,
    now_utc,
    parse_action_status,
    start_process,
    stop_process,
    wait_for_command,
    wait_for_topic_result,
    write_command_result,
)

PHASE2A_PAIR_ROOT = ROOT / 'results' / 'phase2' / 'map3_pairs'


def phase2a_reference_for_seed(seed):
    pair_index = seed - 21000
    ref = PHASE2A_PAIR_ROOT / 'pair_{:02d}'.format(pair_index) / 'slam_aware' / 'tsp_record.json'
    if not ref.is_file():
        return None
    return json.loads(ref.read_text())


def validate_tsp_vs_phase2a(seed, tsp_record, seed_dir):
    reference = phase2a_reference_for_seed(seed)
    if reference is None:
        result = {
            'seed': seed, 'reference_available': False,
            'exact_phase2a_rerun': False, 'reason': 'no Phase 2A reference record found',
        }
    else:
        required = ('solver', 'seed', 'initial_tsp_path', 'full_tsp_path', 'predicted_tsp_length')
        ref_fields = {key: reference.get(key) for key in required}
        run_fields = {key: tsp_record.get(key) for key in required}
        exact = (
            ref_fields == run_fields
            and hashlib.sha256(json.dumps(reference, sort_keys=True).encode()).hexdigest()
            == hashlib.sha256(json.dumps(tsp_record, sort_keys=True).encode()).hexdigest()
        )
        result = {
            'seed': seed, 'reference_available': True,
            'exact_phase2a_rerun': bool(exact),
            'reference_sha256': hashlib.sha256(
                json.dumps(reference, sort_keys=True).encode()).hexdigest(),
            'run_sha256': hashlib.sha256(
                json.dumps(tsp_record, sort_keys=True).encode()).hexdigest(),
            'reason': None if exact else 'TSP record differs from Phase 2A reference',
        }
    (seed_dir / 'tsp_phase2a_validation.json').write_text(
        json.dumps(result, indent=2, sort_keys=True) + '\n')
    return result


def run_one(seed, seed_dir, env, explore_timeout):
    if seed_dir.exists():
        raise RuntimeError('refusing to overwrite existing run directory: {}'.format(seed_dir))
    seed_dir.mkdir(parents=True)
    suffix = '_Phase2C_seed{}'.format(seed)
    tsp_source = AUTHOR_RESULTS / 'tsp_record{}.json'.format(suffix)
    if tsp_source.exists():
        raise RuntimeError('refusing to reuse pre-existing author output: {}'.format(tsp_source))
    diagnostics_path = seed_dir / 'karto_loop_diagnostics.jsonl'
    run_id = 'seed_{}'.format(seed)

    roscore = observer = launch = mapping_result = explore_result = None
    run_state = {'status': 'RUNNING', 'started_wall_time_utc': now_utc()}
    (seed_dir / 'run_state.json').write_text(json.dumps(run_state, indent=2) + '\n')
    monitor_stream = open(seed_dir / 'monitor.csv', 'w', newline='', buffering=1)
    monitor = csv.writer(monitor_stream)
    monitor.writerow([
        'wall_time_utc', 'stage', 'elapsed_wall_s', 'launch_alive',
        'observer_alive', 'rss_kb', 'missing_core_nodes',
    ])
    max_rss = 0
    try:
        if command_output(['rosparam', 'list'], env, timeout=5).returncode == 0:
            raise RuntimeError('a ROS master is already running; refusing to mix experiments')

        roscore = start_process(['roscore'], env, seed_dir / 'roscore.log')
        wait_for_command(['rosparam', 'list'], env, 60, 'ROS master')
        ros_run_id = write_command_result(
            ['rosparam', 'get', '/run_id'], env, seed_dir / 'ros_run_id.txt', timeout=10
        ).strip()
        observer = start_process(
            ['/usr/bin/python3', str(ROOT / 'tools' / 'phase2_observer.py'),
             '--output-dir', str(seed_dir)],
            env, seed_dir / 'observer.log',
        )
        launch = start_process([
            'roslaunch', 'cpp_solver', 'exploration.launch',
            'suffix:={}'.format(suffix), 'strategy:=MyPlanner',
            'only_use_tsp:=false', 'tsp_seed:={}'.format(seed),
            'map_name:=map3/map3', 'robot_position:=-28.0 -28.0 0',
            'map_width:=74.0', 'need_noise:=false', 'variance:=0',
            'enable_loop_diagnostics:=true',
            'loop_diagnostics_path:={}'.format(diagnostics_path),
            'loop_diagnostics_run_id:={}'.format(run_id),
        ], env, seed_dir / 'roslaunch.log')

        deadline = time.monotonic() + 180
        while time.monotonic() < deadline and not tsp_source.is_file():
            if launch.poll() is not None:
                raise RuntimeError('roslaunch exited before TSP record was generated')
            if observer.poll() is not None:
                raise RuntimeError('observer exited before TSP record was generated')
            time.sleep(1)
        if not tsp_source.is_file():
            raise RuntimeError('TSP record was not generated within 180 s')
        tsp_record = json.loads(tsp_source.read_text())
        shutil.copy2(tsp_source, seed_dir / 'tsp_record.json')
        tsp_validation = validate_tsp_vs_phase2a(seed, tsp_record, seed_dir)

        for service in ('/StartMapping', '/StartExploration', '/prior_graph_service',
                        '/path_plan_service', '/reliable_loop_service'):
            wait_for_command(['rosservice', 'type', service], env, 120, service)
        write_command_result(['rosnode', 'list'], env, seed_dir / 'initial_rosnode_list.txt')

        mapping_result_stream = open(seed_dir / 'get_first_map_result.txt', 'w', buffering=1)
        mapping_result = subprocess.Popen(
            ['rostopic', 'echo', '-n', '1', '/GetFirstMap/result'], env=env,
            cwd=str(ROOT), stdout=mapping_result_stream, stderr=subprocess.STDOUT, text=True,
        )
        time.sleep(1)
        write_command_result(
            ['rosservice', 'call', '/StartMapping', '{}'], env,
            seed_dir / 'start_mapping_service.txt', timeout=30,
        )
        wait_for_topic_result(
            mapping_result, seed_dir / 'get_first_map_result.txt', launch, observer,
            env, 900, monitor, 'mapping',
        )
        mapping_result_stream.close()
        if parse_action_status(seed_dir / 'get_first_map_result.txt') != 3:
            raise RuntimeError('GetFirstMap action did not SUCCEED')

        explore_result_stream = open(seed_dir / 'explore_result.txt', 'w', buffering=1)
        explore_result = subprocess.Popen(
            ['rostopic', 'echo', '-n', '1', '/Explore/result'], env=env,
            cwd=str(ROOT), stdout=explore_result_stream, stderr=subprocess.STDOUT, text=True,
        )
        time.sleep(1)
        write_command_result(
            ['rosservice', 'call', '/StartExploration', '{}'], env,
            seed_dir / 'start_exploration_service.txt', timeout=30,
        )
        max_rss = wait_for_topic_result(
            explore_result, seed_dir / 'explore_result.txt', launch, observer,
            env, explore_timeout, monitor, 'exploration',
        )
        explore_result_stream.close()
        if parse_action_status(seed_dir / 'explore_result.txt') != 3:
            raise RuntimeError('Explore action did not SUCCEED')

        marker_wait_start = time.monotonic()
        while time.monotonic() - marker_wait_start < 7:
            if launch.poll() is not None or observer.poll() is not None:
                break
            time.sleep(1)
        write_command_result(
            ['rosrun', 'map_server', 'map_saver', '-f', str(seed_dir / 'final_map')],
            env, seed_dir / 'map_saver.log', timeout=90,
        )

        stop_process(observer)
        observer = None
        stop_process(launch)
        launch = None
        stop_process(roscore)
        roscore = None

        rosout_source = Path(env['ROS_LOG_DIR']) / ros_run_id / 'rosout.log'
        if rosout_source.is_file():
            shutil.copy2(rosout_source, seed_dir / 'rosout.log')
        copy_author_outputs(suffix, seed_dir)
        if not diagnostics_path.is_file():
            raise RuntimeError('karto_loop_diagnostics.jsonl was not produced')

        write_command_result([
            '/usr/bin/python3', str(ROOT / 'tools' / 'finalize_phase2_run.py'),
            '--run-dir', str(seed_dir),
        ], env, seed_dir / 'finalize.log', timeout=120)

        commit = subprocess.check_output(
            ['git', '-C', str(BASELINE), 'rev-parse', 'HEAD'], text=True
        ).strip()
        nav_commit = subprocess.check_output(
            ['git', '-C', str(ROOT / 'dependencies' / 'navigation_2d'), 'rev-parse', 'HEAD'],
            text=True,
        ).strip()
        manifest = {
            'phase': '2C', 'method': 'Graph-Based SLAM-aware', 'map': 'map3',
            'seed': seed, 'start_pose_xyyaw': [-28.0, -28.0, 0.0],
            'git_commit_baseline': commit,
            'git_commit_navigation_2d': nav_commit,
            'launch_file': 'cpp_solver exploration.launch',
            'launch_arguments': {
                'strategy': 'MyPlanner', 'only_use_tsp': False,
                'map_name': 'map3/map3', 'tsp_solver': 'concorde',
                'tsp_seed': seed, 'need_noise': False, 'variance': 0,
                'enable_loop_diagnostics': True,
                'loop_diagnostics_path': str(diagnostics_path),
                'loop_diagnostics_run_id': run_id,
                'suffix': suffix,
            },
            'python': '/usr/bin/python3 3.8.10', 'observer': 'tools/phase2_observer.py (passive)',
            'stdout_stderr': 'roslaunch.log', 'max_process_tree_rss_kb': max_rss,
            'tsp_phase2a_validation': tsp_validation,
        }
        (seed_dir / 'manifest.json').write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + '\n'
        )
        run_state.update({'status': 'SUCCEEDED', 'finished_wall_time_utc': now_utc()})
        (seed_dir / 'run_state.json').write_text(json.dumps(run_state, indent=2) + '\n')
        return {'seed': seed, 'success': True, 'tsp_validation': tsp_validation}
    except Exception as exc:
        run_state.update({
            'status': 'FAILED', 'finished_wall_time_utc': now_utc(),
            'reason': '{}: {}'.format(type(exc).__name__, exc),
        })
        (seed_dir / 'run_state.json').write_text(json.dumps(run_state, indent=2) + '\n')
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
    parser.add_argument('--start-seed', type=int, default=21001)
    parser.add_argument('--end-seed', type=int, default=21005)
    # Generous wall-clock timeout: on this host the Stage sim intermittently runs
    # at ~0.2x real time (environmental, confirmed with an isolated Stage), so a
    # ~1400 s-sim SLAM-aware run needs up to ~7000 s of wall time.
    parser.add_argument('--explore-timeout', type=int, default=9000)
    parser.add_argument(
        '--output-root', type=Path,
        default=ROOT / 'results' / 'phase2c' / 'map3',
    )
    args = parser.parse_args()
    env = activated_environment()
    args.output_root.mkdir(parents=True, exist_ok=True)
    suite_state_path = args.output_root / 'suite_state.json'
    state = {'status': 'RUNNING', 'started_wall_time_utc': now_utc(),
             'seeds': list(range(args.start_seed, args.end_seed + 1)),
             'completed_runs': []}
    suite_state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + '\n')
    try:
        for seed in range(args.start_seed, args.end_seed + 1):
            seed_dir = args.output_root / 'seed_{}'.format(seed)
            outcome = run_one(seed, seed_dir, env, args.explore_timeout)
            state['completed_runs'].append({
                'seed': seed, 'finished_wall_time_utc': now_utc(),
                'exact_phase2a_rerun': bool(outcome['tsp_validation'].get('exact_phase2a_rerun')),
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


if __name__ == '__main__':
    main()
