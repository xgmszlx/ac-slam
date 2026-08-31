#!/usr/bin/python3
"""Fresh controlled map3 A/B/C suite for Phase 4B.

The runner is fail-closed on TSP mismatch and technical faults. Navigation or
exploration failures are retained as experimental outcomes and do not trigger an
automatic retry.
"""

import argparse
import csv
import datetime
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path

from run_phase2_pairs import (
    AUTHOR_RESULTS,
    BASELINE,
    ROOT,
    activated_environment,
    command_output,
    copy_author_outputs,
    now_utc,
    parse_action_status,
    start_process,
    stop_process,
    validate_tsp,
    wait_for_command,
    wait_for_topic_result,
    write_command_result,
)


OUTPUT_ROOT = ROOT / 'results' / 'phase4b' / 'map3'
GT_MAP_YAML = BASELINE / 'world' / 'map3' / 'map3.yaml'
MAPPER_PARAMS = BASELINE / 'param' / 'mapper.yaml'
NAVIGATION = ROOT / 'dependencies' / 'navigation_2d'
CONDITIONS = {
    'A': {'directory': 'A_original', 'name': 'Original', 'oracle_mode': 0},
    'B': {'directory': 'B_always_trace', 'name': 'Always-Trace', 'oracle_mode': 1},
    'C': {'directory': 'C_selective', 'name': 'Selective', 'oracle_mode': 2},
}
ORDERS = {
    21001: ('A', 'B', 'C'),
    21002: ('B', 'C', 'A'),
    21003: ('C', 'A', 'B'),
    21004: ('A', 'C', 'B'),
    21005: ('B', 'A', 'C'),
}


class TechnicalInvalid(RuntimeError):
    pass


def git_commit(repo):
    return subprocess.check_output(
        ['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True
    ).strip()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ensure_preflight_and_source():
    manifest_path = OUTPUT_ROOT / 'protocol_manifest.json'
    if not manifest_path.is_file():
        raise TechnicalInvalid('protocol_manifest.json missing; run preflight first')
    manifest = json.loads(manifest_path.read_text())
    current = {
        'root': git_commit(ROOT),
        'baseline': git_commit(BASELINE),
        'navigation_2d': git_commit(NAVIGATION),
    }
    if manifest.get('commits') != current:
        raise TechnicalInvalid(
            'source commits differ from preflight: {} != {}'.format(current, manifest.get('commits'))
        )
    tracked = subprocess.check_output(
        ['git', '-C', str(ROOT), 'status', '--porcelain', '--untracked-files=no'],
        text=True,
    ).strip()
    if tracked:
        raise TechnicalInvalid('tracked source changes exist after preflight:\n{}'.format(tracked))
    return manifest_path, manifest


def no_ros_master(env):
    return command_output(['rosparam', 'list'], env, timeout=5).returncode != 0


def launch_command(seed, condition, suffix, map_config=None):
    map_config = map_config or {
        'map_name': 'map3/map3', 'robot_position': '-28.0 -28.0 0',
        'map_width': 74.0,
    }
    return [
        'roslaunch', 'cpp_solver', 'exploration.launch',
        'suffix:={}'.format(suffix), 'strategy:=MyPlanner',
        'only_use_tsp:=false', 'tsp_solver:=concorde',
        'tsp_seed:={}'.format(seed),
        'map_name:={}'.format(map_config['map_name']),
        'robot_position:={}'.format(map_config['robot_position']),
        'map_width:={}'.format(map_config['map_width']),
        'need_noise:=false', 'variance:=0',
        'enable_loop_diagnostics:=false',
        'loop_diagnostics_path:=', 'loop_diagnostics_run_id:=',
        'oracle_mode:={}'.format(condition['oracle_mode']),
        'oracle_before:=8', 'oracle_after:=8', 'oracle_densify_m:=0.5',
        'oracle_span_gate:=4.0', 'oracle_repair_max_len:=12.0',
        'oracle_repair_max_wp:=24', 'oracle_repair_densify:=0.5',
        'oracle_dir_lambda:=1.0',
    ]


def save_command_result_allow_failure(command, env, path, timeout=60):
    try:
        completed = command_output(command, env, timeout=timeout)
        text = completed.stdout
        code = completed.returncode
    except subprocess.TimeoutExpired as exc:
        text = 'TIMEOUT\n{}\n'.format(exc)
        code = None
    path.write_text(text, encoding='utf-8')
    return code


def write_manifest(run_dir, seed, label, condition, command, protocol_manifest,
                   map_config=None, phase='4B'):
    map_config = map_config or {
        'id': 'map3', 'start_pose': [-28.0, -28.0, 0.0],
        'frozen_sha256': {},
    }
    launch_args = {}
    for token in command[3:]:
        if ':=' in token:
            key, value = token.split(':=', 1)
            launch_args[key] = value
    manifest = {
        'phase': phase,
        'seed': seed,
        'condition': label,
        'method': condition['name'],
        'oracle_mode': condition['oracle_mode'],
        'map': map_config['id'],
        'start_pose_xyyaw': map_config['start_pose'],
        'frozen_environment_sha256': map_config.get('frozen_sha256', {}),
        'launch_file': 'cpp_solver exploration.launch',
        'launch_arguments': launch_args,
        'scientific_variable': {'oracle_mode': condition['oracle_mode']},
        'diagnostics_enabled': False,
        'accepted_closure_source': '/Mapper/loop_closed',
        'commits': {
            'root': git_commit(ROOT),
            'baseline': git_commit(BASELINE),
            'navigation_2d': git_commit(NAVIGATION),
        },
        'protocol_manifest': str(protocol_manifest.relative_to(ROOT)),
        'protocol_manifest_sha256': sha256(protocol_manifest),
        'full_command': 'full_command.txt',
        'mapper_params': 'mapper_params.yaml',
        'created_utc': now_utc(),
    }
    (run_dir / 'manifest.json').write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )


def evaluate_offline(run_dir, env, oracle_mode, seed, validity, exploration_wall_s,
                     gt_map_yaml=None):
    gt_map_yaml = Path(gt_map_yaml) if gt_map_yaml else GT_MAP_YAML
    evaluation_errors = []
    if (run_dir / 'trajectory_gt.txt').is_file() and (run_dir / 'trajectory_slam.txt').is_file():
        try:
            write_command_result([
                '/usr/bin/python3', str(ROOT / 'tools' / 'evaluate_slam_run.py'),
                '--gt', str(run_dir / 'trajectory_gt.txt'),
                '--slam', str(run_dir / 'trajectory_slam.txt'),
                '--output-dir', str(run_dir / 'evo'),
                '--loops-json', str(run_dir / 'loops.json'),
            ], env, run_dir / 'evo_evaluation.log', timeout=1800)
        except Exception as exc:
            evaluation_errors.append('trajectory: {}: {}'.format(type(exc).__name__, exc))
    else:
        evaluation_errors.append('trajectory: required files missing')

    if (run_dir / 'final_map.yaml').is_file() and (run_dir / 'final_map.pgm').is_file():
        try:
            write_command_result([
                '/usr/bin/python3', str(ROOT / 'tools' / 'evaluate_mapping.py'),
                '--gt-yaml', str(gt_map_yaml),
                '--estimated-yaml', str(run_dir / 'final_map.yaml'),
                '--output', str(run_dir / 'mapping_metrics.json'),
                '--boundary-tolerance-m', '0.20',
            ], env, run_dir / 'mapping_evaluation.log', timeout=300)
        except Exception as exc:
            evaluation_errors.append('mapping: {}: {}'.format(type(exc).__name__, exc))
    else:
        evaluation_errors.append('mapping: final map files missing')

    try:
        write_command_result([
            '/usr/bin/python3', str(ROOT / 'tools' / 'finalize_phase2_run.py'),
            '--run-dir', str(run_dir),
        ], env, run_dir / 'phase2_finalize.log', timeout=300)
    except Exception as exc:
        evaluation_errors.append('phase2 finalize: {}: {}'.format(type(exc).__name__, exc))

    summary_validity = (
        'TECHNICAL_INVALID' if evaluation_errors and validity == 'VALID' else validity
    )
    write_command_result([
        '/usr/bin/python3', str(ROOT / 'tools' / 'finalize_phase4b_run.py'),
        '--run-dir', str(run_dir), '--oracle-mode', str(oracle_mode),
        '--seed', str(seed), '--validity', summary_validity,
        '--exploration-wall-s', str(exploration_wall_s),
    ], env, run_dir / 'phase4b_finalize.log', timeout=300)
    (run_dir / 'evaluation_status.json').write_text(
        json.dumps({
            'status': 'PASS' if not evaluation_errors else 'PARTIAL',
            'errors': evaluation_errors,
            'offline_only': True,
        }, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )
    return evaluation_errors


def run_one(seed, label, condition, seed_dir, env, explore_timeout,
            protocol_manifest, map_config=None, phase_tag='Phase4B',
            attempt_name=None):
    map_config = map_config or {
        'id': 'map3', 'map_name': 'map3/map3',
        'robot_position': '-28.0 -28.0 0', 'map_width': 74.0,
        'start_pose': [-28.0, -28.0, 0.0],
        'gt_yaml': str(GT_MAP_YAML), 'frozen_sha256': {},
    }
    run_dir = seed_dir / condition['directory']
    if attempt_name:
        run_dir = run_dir / attempt_name
    if run_dir.exists():
        raise TechnicalInvalid('refusing to overwrite existing run: {}'.format(run_dir))
    run_dir.mkdir(parents=True)
    if phase_tag == 'Phase4B' and map_config['id'] == 'map3':
        suffix = '_Phase4B_seed{}_{}'.format(seed, label)
        manifest_phase = '4B'
    else:
        suffix = '_{}_{}_seed{}_{}_{}'.format(
            phase_tag, map_config['id'], seed, label, attempt_name or 'attempt_01'
        )
        manifest_phase = '4C_FORMAL'
    tsp_source = AUTHOR_RESULTS / 'tsp_record{}.json'.format(suffix)
    if tsp_source.exists():
        raise TechnicalInvalid('pre-existing author output: {}'.format(tsp_source))
    command = launch_command(seed, condition, suffix, map_config)
    (run_dir / 'full_command.txt').write_text(
        shlex.join(command) + '\n', encoding='utf-8'
    )
    shutil.copy2(MAPPER_PARAMS, run_dir / 'mapper_params.yaml')
    write_manifest(
        run_dir, seed, label, condition, command, protocol_manifest,
        map_config=map_config, phase=manifest_phase,
    )
    run_state = {
        'status': 'RUNNING', 'validity': None,
        'started_wall_time_utc': now_utc(),
    }
    (run_dir / 'run_state.json').write_text(json.dumps(run_state, indent=2) + '\n')

    monitor_stream = (run_dir / 'monitor.csv').open('w', newline='', buffering=1)
    monitor = csv.writer(monitor_stream)
    monitor.writerow([
        'wall_time_utc', 'stage', 'elapsed_wall_s', 'launch_alive',
        'observer_alive', 'rss_kb', 'missing_core_nodes',
    ])
    roscore = observer = launch = mapping_result = explore_result = None
    run_id = None
    validity = 'VALID'
    experimental_reason = None
    exploration_wall_s = 0.0
    max_rss = 0
    try:
        if not no_ros_master(env):
            raise TechnicalInvalid('a ROS master is already running')
        roscore = start_process(['roscore'], env, run_dir / 'roscore.log')
        wait_for_command(['rosparam', 'list'], env, 60, 'ROS master')
        run_id = write_command_result(
            ['rosparam', 'get', '/run_id'], env, run_dir / 'ros_run_id.txt', timeout=10
        ).strip()
        # The observer starts before exploration.launch. Set the same global value
        # explicitly so rospy uses simulated time from initialization; launch later
        # writes the identical value.
        write_command_result(
            ['rosparam', 'set', '/use_sim_time', 'true'], env,
            run_dir / 'use_sim_time_pre_observer.txt', timeout=10,
        )
        observer = start_process([
            '/usr/bin/python3', str(ROOT / 'tools' / 'phase2_observer.py'),
            '--output-dir', str(run_dir),
        ], env, run_dir / 'observer.log')
        launch = start_process(command, env, run_dir / 'roslaunch.log')

        deadline = time.monotonic() + 240
        while time.monotonic() < deadline and not tsp_source.is_file():
            if launch.poll() is not None:
                raise TechnicalInvalid('roslaunch exited before TSP record')
            if observer.poll() is not None:
                raise TechnicalInvalid('observer exited before TSP record')
            time.sleep(1)
        if not tsp_source.is_file():
            raise TechnicalInvalid('TSP record timeout')
        shutil.copy2(tsp_source, run_dir / 'tsp_record.json')
        try:
            validate_tsp(
                run_dir / 'tsp_record.json', seed_dir / 'initial_tsp_reference.json',
                run_dir / 'tsp_pair_validation.json',
            )
        except Exception as exc:
            raise TechnicalInvalid(str(exc))

        for service in ('/StartMapping', '/StartExploration', '/prior_graph_service',
                        '/path_plan_service', '/reliable_loop_service'):
            wait_for_command(['rosservice', 'type', service], env, 120, service)
        wait_for_command(['rostopic', 'type', '/Mapper/loop_closed'], env, 120,
                         '/Mapper/loop_closed')
        diagnostics = wait_for_command(
            ['rosparam', 'get', '/Mapper/enable_loop_diagnostics'], env, 30,
            'diagnostics parameter',
        ).strip().lower()
        if diagnostics not in ('false', '0'):
            raise TechnicalInvalid('formal diagnostics unexpectedly enabled')
        actual_mode = int(wait_for_command(
            ['rosparam', 'get', '/path_planner/oracle_mode'], env, 30,
            'oracle_mode parameter',
        ).strip())
        if actual_mode != condition['oracle_mode']:
            raise TechnicalInvalid('oracle_mode runtime mismatch')
        for cmd, filename in (
            (['rosnode', 'list'], 'initial_rosnode_list.txt'),
            (['rosservice', 'list'], 'initial_rosservice_list.txt'),
            (['rostopic', 'list'], 'initial_rostopic_list.txt'),
        ):
            write_command_result(cmd, env, run_dir / filename)

        mapping_stream = (run_dir / 'get_first_map_result.txt').open('w', buffering=1)
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
            mapping_result, run_dir / 'get_first_map_result.txt', launch, observer,
            env, 1800, monitor, 'mapping',
        ))
        mapping_stream.close()
        if parse_action_status(run_dir / 'get_first_map_result.txt') != 3:
            raise TechnicalInvalid('GetFirstMap action did not succeed')

        explore_stream = (run_dir / 'explore_result.txt').open('w', buffering=1)
        explore_result = subprocess.Popen(
            ['rostopic', 'echo', '-n', '1', '/Explore/result'], env=env,
            cwd=str(ROOT), stdout=explore_stream, stderr=subprocess.STDOUT, text=True,
        )
        time.sleep(1)
        write_command_result(
            ['rosservice', 'call', '/StartExploration', '{}'], env,
            run_dir / 'start_exploration_service.txt', timeout=30,
        )
        explore_wall_start = time.monotonic()
        try:
            max_rss = max(max_rss, wait_for_topic_result(
                explore_result, run_dir / 'explore_result.txt', launch, observer,
                env, explore_timeout, monitor, 'exploration',
            ))
        except RuntimeError as exc:
            if 'hard timeout' in str(exc) and launch.poll() is None and observer.poll() is None:
                validity = 'EXPERIMENTAL_FAILURE'
                experimental_reason = str(exc)
                save_command_result_allow_failure(
                    ['rosservice', 'call', '/Stop', '{}'], env,
                    run_dir / 'stop_after_timeout_service.txt', timeout=30,
                )
            else:
                raise TechnicalInvalid(str(exc))
        exploration_wall_s = time.monotonic() - explore_wall_start
        explore_stream.close()
        if validity == 'VALID':
            status = parse_action_status(run_dir / 'explore_result.txt')
            if status != 3:
                validity = 'EXPERIMENTAL_FAILURE'
                experimental_reason = 'Explore action status {}'.format(status)

        time.sleep(7)
        if launch.poll() is None:
            rc = save_command_result_allow_failure([
                'rosrun', 'map_server', 'map_saver', '-f', str(run_dir / 'final_map')
            ], env, run_dir / 'map_saver.log', timeout=120)
            if rc != 0 and validity == 'VALID':
                raise TechnicalInvalid('map_saver failed with code {}'.format(rc))
            for cmd, filename in (
                (['rosnode', 'list'], 'final_rosnode_list.txt'),
                (['rosservice', 'list'], 'final_rosservice_list.txt'),
                (['rostopic', 'list'], 'final_rostopic_list.txt'),
            ):
                save_command_result_allow_failure(cmd, env, run_dir / filename)

        stop_process(observer)
        observer = None
        stop_process(launch)
        launch = None
        stop_process(roscore)
        roscore = None
        time.sleep(2)

        if run_id:
            rosout_source = Path(env['ROS_LOG_DIR']) / run_id / 'rosout.log'
            if rosout_source.is_file():
                shutil.copy2(rosout_source, run_dir / 'rosout.log')
        copy_author_outputs(suffix, run_dir)
        if not (run_dir / 'loops.json').is_file() or not (run_dir / 'observer_summary.json').is_file():
            raise TechnicalInvalid('observer final artifacts missing')
        errors = evaluate_offline(
            run_dir, env, condition['oracle_mode'], seed, validity,
            exploration_wall_s, gt_map_yaml=map_config['gt_yaml'],
        )
        if errors and validity == 'VALID':
            raise TechnicalInvalid('offline evaluation incomplete: {}'.format(errors))

        run_state.update({
            'status': 'COMPLETED', 'validity': validity,
            'experimental_failure_reason': experimental_reason,
            'finished_wall_time_utc': now_utc(),
            'exploration_wall_s': exploration_wall_s,
            'max_process_tree_rss_kb': max_rss,
        })
        (run_dir / 'run_state.json').write_text(
            json.dumps(run_state, indent=2, sort_keys=True) + '\n'
        )
        return {'validity': validity, 'reason': experimental_reason}
    except Exception as exc:
        run_state.update({
            'status': 'FAILED', 'validity': 'TECHNICAL_INVALID',
            'reason': '{}: {}'.format(type(exc).__name__, exc),
            'finished_wall_time_utc': now_utc(),
        })
        (run_dir / 'run_state.json').write_text(
            json.dumps(run_state, indent=2, sort_keys=True) + '\n'
        )
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
    parser.add_argument('--seeds', type=int, nargs='+', default=list(ORDERS))
    parser.add_argument('--explore-timeout', type=int, default=18000)
    parser.add_argument('--resume', action='store_true',
                        help='append only new seed directories to an existing suite state')
    args = parser.parse_args()
    if any(seed not in ORDERS for seed in args.seeds):
        raise SystemExit('seeds must be selected from {}'.format(sorted(ORDERS)))
    protocol_manifest, _ = ensure_preflight_and_source()
    env = activated_environment()
    suite_state_path = OUTPUT_ROOT / 'suite_state.json'
    if suite_state_path.exists():
        if not args.resume:
            raise SystemExit(
                'suite_state.json exists; use --resume only after inspecting the prior stop'
            )
        state = json.loads(suite_state_path.read_text())
        history_dir = OUTPUT_ROOT / 'suite_state_history'
        history_dir.mkdir(exist_ok=True)
        token = datetime.datetime.now().strftime('%Y%m%dT%H%M%S')
        shutil.copy2(suite_state_path, history_dir / ('before_resume_' + token + '.json'))
        state.setdefault('resume_events', []).append({
            'resumed_wall_time_utc': now_utc(), 'requested_seeds': args.seeds,
            'previous_status': state.get('status'),
        })
        previous_seeds = set(state.get('seeds', []))
        state['seeds'] = sorted(previous_seeds | set(args.seeds))
        state.setdefault('orders', {}).update({
            str(seed): ORDERS[seed] for seed in args.seeds
        })
        state['status'] = 'RUNNING'
    else:
        if args.resume:
            raise SystemExit('--resume requested but suite_state.json does not exist')
        state = {
            'status': 'RUNNING', 'started_wall_time_utc': now_utc(),
            'seeds': args.seeds,
            'orders': {str(seed): ORDERS[seed] for seed in args.seeds},
            'completed_runs': [],
        }
    suite_state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + '\n')
    try:
        for seed in args.seeds:
            seed_dir = OUTPUT_ROOT / 'seed_{}'.format(seed)
            if seed_dir.exists():
                raise TechnicalInvalid(
                    'resume refuses existing seed directory: {}'.format(seed_dir)
                )
            seed_dir.mkdir(parents=True, exist_ok=False)
            for label in ORDERS[seed]:
                outcome = run_one(
                    seed, label, CONDITIONS[label], seed_dir, env,
                    args.explore_timeout, protocol_manifest,
                )
                state['completed_runs'].append({
                    'seed': seed, 'condition': label,
                    'validity': outcome['validity'], 'finished_wall_time_utc': now_utc(),
                })
                suite_state_path.write_text(
                    json.dumps(state, indent=2, sort_keys=True) + '\n'
                )
        state.update({'status': 'COMPLETED', 'finished_wall_time_utc': now_utc()})
    except Exception as exc:
        state.update({
            'status': 'STOPPED_TECHNICAL_FAILURE',
            'reason': '{}: {}'.format(type(exc).__name__, exc),
            'finished_wall_time_utc': now_utc(),
            'retry_policy': 'no automatic retry; diagnose and preserve raw attempt',
        })
        raise
    finally:
        suite_state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + '\n')
        print(json.dumps(state, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
