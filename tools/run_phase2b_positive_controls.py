#!/usr/bin/python3
"""Run three independent map3 Karto loop-closure positive controls."""

import argparse
import csv
import json
import os
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
    descendants_rss_kb,
    now_utc,
    parse_action_status,
    start_process,
    stop_process,
    wait_for_command,
    wait_for_topic_result,
    write_command_result,
)


def wait_for_driver(driver, launch, env, timeout, monitor, trial):
    start = time.monotonic()
    next_monitor = 0.0
    max_rss = 0
    while driver.poll() is None:
        elapsed = time.monotonic() - start
        if elapsed >= timeout:
            raise RuntimeError('positive-control driver hard timeout after {:.1f}s'.format(elapsed))
        if launch.poll() is not None:
            raise RuntimeError('roslaunch exited while positive-control driver was active')
        if elapsed >= next_monitor:
            nodes = command_output(['rosnode', 'list'], env, timeout=15)
            node_set = set(nodes.stdout.splitlines()) if nodes.returncode == 0 else set()
            missing = sorted(CORE_NODES - node_set)
            rss = descendants_rss_kb(launch.pid)
            max_rss = max(max_rss, rss)
            monitor.writerow([
                now_utc(), 'positive_revisit', '{:.1f}'.format(elapsed),
                int(launch.poll() is None), int(driver.poll() is None), rss,
                ';'.join(missing),
            ])
            next_monitor += 30.0
        time.sleep(1)
    if driver.returncode != 0:
        raise RuntimeError('positive-control driver exited with code {}'.format(driver.returncode))
    return max_rss


def run_trial(trial, output_root, env, explore_timeout, revisit_timeout):
    run_dir = output_root / 'trial_{:02d}'.format(trial)
    if run_dir.exists():
        raise RuntimeError('refusing to overwrite existing trial: {}'.format(run_dir))
    run_dir.mkdir(parents=True)
    suffix = '_Phase2B_PositiveControl_trial{:02d}'.format(trial)
    seed = 22000 + trial
    state = {'status': 'RUNNING', 'started_wall_time_utc': now_utc(), 'trial': trial}
    (run_dir / 'run_state.json').write_text(json.dumps(state, indent=2) + '\n')

    roscore = launch = driver = mapping_result = explore_result = None
    monitor_stream = open(run_dir / 'monitor.csv', 'w', newline='', buffering=1)
    monitor = csv.writer(monitor_stream)
    monitor.writerow([
        'wall_time_utc', 'stage', 'elapsed_wall_s', 'launch_alive',
        'driver_alive', 'rss_kb', 'missing_core_nodes',
    ])
    max_rss = 0
    try:
        if command_output(['rosparam', 'list'], env, timeout=5).returncode == 0:
            raise RuntimeError('a ROS master is already running; refusing to mix experiments')
        roscore = start_process(['roscore'], env, run_dir / 'roscore.log')
        wait_for_command(['rosparam', 'list'], env, 60, 'ROS master')
        run_id = write_command_result(
            ['rosparam', 'get', '/run_id'], env, run_dir / 'ros_run_id.txt', timeout=10
        ).strip()

        driver = start_process([
            '/usr/bin/python3', str(ROOT / 'tools' / 'phase2b_positive_control_driver.py'),
            '--output-dir', str(run_dir), '--first-history-index', '30',
            '--target-count', '7', '--target-stride', '5',
        ], env, run_dir / 'driver.log')

        launch = start_process([
            'roslaunch', 'cpp_solver', 'exploration.launch',
            'suffix:={}'.format(suffix), 'strategy:=NearestFrontierPlanner',
            'only_use_tsp:=true', 'tsp_seed:={}'.format(seed),
            'map_name:=map3/map3', 'robot_position:=-28.0 -28.0 0',
            'map_width:=74.0', 'need_noise:=false', 'variance:=0',
        ], env, run_dir / 'roslaunch.log')

        for service in ('/StartMapping', '/StartExploration', '/Mapper/get_loggers'):
            wait_for_command(['rosservice', 'type', service], env, 180, service)
        wait_for_command(['rostopic', 'type', '/slam_pose_graph'], env, 120, 'pose graph topic')
        write_command_result(
            ['rosservice', 'call', '/Mapper/get_loggers', '{}'], env,
            run_dir / 'mapper_loggers.txt', timeout=30,
        )
        write_command_result(['rosparam', 'get', '/Mapper'], env, run_dir / 'mapper_params.yaml')
        write_command_result(['rosnode', 'list'], env, run_dir / 'initial_rosnode_list.txt')

        mapping_stream = open(run_dir / 'get_first_map_result.txt', 'w', buffering=1)
        mapping_result = subprocess.Popen(
            ['rostopic', 'echo', '-n', '1', '/GetFirstMap/result'], env=env,
            cwd=str(ROOT), stdout=mapping_stream, stderr=subprocess.STDOUT, text=True,
        )
        time.sleep(1)
        write_command_result(
            ['rosservice', 'call', '/StartMapping', '{}'], env,
            run_dir / 'start_mapping_service.txt', timeout=30,
        )
        max_rss = max(max_rss, wait_for_topic_result(
            mapping_result, run_dir / 'get_first_map_result.txt', launch, driver,
            env, 900, monitor, 'mapping',
        ))
        mapping_stream.close()
        if parse_action_status(run_dir / 'get_first_map_result.txt') != 3:
            raise RuntimeError('GetFirstMap action did not SUCCEED')

        explore_stream = open(run_dir / 'explore_result.txt', 'w', buffering=1)
        explore_result = subprocess.Popen(
            ['rostopic', 'echo', '-n', '1', '/Explore/result'], env=env,
            cwd=str(ROOT), stdout=explore_stream, stderr=subprocess.STDOUT, text=True,
        )
        time.sleep(1)
        write_command_result(
            ['rosservice', 'call', '/StartExploration', '{}'], env,
            run_dir / 'start_exploration_service.txt', timeout=30,
        )
        max_rss = max(max_rss, wait_for_topic_result(
            explore_result, run_dir / 'explore_result.txt', launch, driver,
            env, explore_timeout, monitor, 'history_exploration',
        ))
        explore_stream.close()
        if parse_action_status(run_dir / 'explore_result.txt') != 3:
            raise RuntimeError('Nearest-Frontier history exploration did not SUCCEED')

        max_rss = max(max_rss, wait_for_driver(
            driver, launch, env, revisit_timeout, monitor, trial
        ))
        result = json.loads((run_dir / 'positive_control.json').read_text())
        if result.get('status') != 'SUCCEEDED':
            raise RuntimeError('positive-control execution failed: {}'.format(result.get('reason')))

        write_command_result(
            ['rosrun', 'map_server', 'map_saver', '-f', str(run_dir / 'final_map')],
            env, run_dir / 'map_saver.log', timeout=90,
        )
        stop_process(launch)
        launch = None
        stop_process(roscore)
        roscore = None

        rosout_source = Path(env['ROS_LOG_DIR']) / run_id / 'rosout.log'
        if rosout_source.is_file():
            shutil.copy2(rosout_source, run_dir / 'rosout.log')
        copy_author_outputs(suffix, run_dir)
        commit = subprocess.check_output(
            ['git', '-C', str(BASELINE), 'rev-parse', 'HEAD'], text=True
        ).strip()
        manifest = {
            'trial': trial, 'map': 'map3', 'robot': 'Pioneer 3-AT',
            'karto_config': 'cpp_solver/param/mapper.yaml (unchanged)',
            'history_method': 'NearestFrontierPlanner to normal completion',
            'revisit_method': 'independent /MoveTo action client',
            'history_target_indices': result.get('selected_history_indices'),
            'move_tolerance_m': 0.25, 'heading_tolerance_rad': 0.1,
            'launch_seed_irrelevant_to_revisit': seed, 'git_commit': commit,
            'max_process_tree_rss_kb': max_rss,
            'positive_control_success': result['positive_control_success'],
        }
        (run_dir / 'manifest.json').write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + '\n'
        )
        state.update({
            'status': 'SUCCEEDED', 'finished_wall_time_utc': now_utc(),
            'positive_control_success': result['positive_control_success'],
        })
        (run_dir / 'run_state.json').write_text(json.dumps(state, indent=2) + '\n')
        return result['positive_control_success']
    except Exception as exc:
        state.update({
            'status': 'FAILED', 'finished_wall_time_utc': now_utc(),
            'reason': '{}: {}'.format(type(exc).__name__, exc),
        })
        (run_dir / 'run_state.json').write_text(json.dumps(state, indent=2) + '\n')
        raise
    finally:
        for process in (mapping_result, explore_result):
            if process is not None and process.poll() is None:
                process.terminate()
        stop_process(driver)
        stop_process(launch)
        stop_process(roscore)
        monitor_stream.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--trials', type=int, default=3, choices=range(3, 6))
    parser.add_argument('--explore-timeout', type=int, default=1800)
    parser.add_argument('--revisit-timeout', type=int, default=1800)
    parser.add_argument(
        '--output-root', type=Path,
        default=ROOT / 'results' / 'phase2b' / 'positive_control',
    )
    args = parser.parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)
    suite_path = args.output_root / 'suite_state.json'
    if suite_path.exists():
        raise SystemExit('refusing to overwrite an existing positive-control suite')
    state = {
        'status': 'RUNNING', 'started_wall_time_utc': now_utc(),
        'requested_trials': args.trials, 'completed_trials': [],
    }
    suite_path.write_text(json.dumps(state, indent=2) + '\n')
    env = activated_environment()
    try:
        for trial in range(1, args.trials + 1):
            success = run_trial(
                trial, args.output_root, env, args.explore_timeout, args.revisit_timeout
            )
            state['completed_trials'].append({'trial': trial, 'success': success})
            suite_path.write_text(json.dumps(state, indent=2) + '\n')
        successes = sum(item['success'] for item in state['completed_trials'])
        state.update({
            'status': 'SUCCEEDED', 'finished_wall_time_utc': now_utc(),
            'successes': successes,
            'positive_control_success_rate': successes / args.trials,
        })
        suite_path.write_text(json.dumps(state, indent=2) + '\n')
    except Exception as exc:
        state.update({
            'status': 'FAILED', 'finished_wall_time_utc': now_utc(),
            'reason': '{}: {}'.format(type(exc).__name__, exc),
        })
        suite_path.write_text(json.dumps(state, indent=2) + '\n')
        raise


if __name__ == '__main__':
    main()
