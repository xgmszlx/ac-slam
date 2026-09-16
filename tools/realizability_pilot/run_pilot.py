#!/usr/bin/python3
"""Plan, run, detach, stop, and resume controlled pilot episodes.

Each episode owns a fresh ROS master, Stage process, mapper, and history-building
trajectory.  SIGINT/SIGTERM are caught by the normal Python cleanup path, so an
interrupted suite can be resumed without reusing the partial episode directory.
"""

import argparse
import csv
import datetime
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
TOOLS_DIR = THIS_DIR.parent
ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(THIS_DIR))

from protocol import PROTOCOL_VERSION, episode_specs  # noqa: E402
from run_phase2_pairs import (  # noqa: E402
    AUTHOR_RESULTS,
    BASELINE,
    CORE_NODES,
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


DEFAULT_ROOT = ROOT / 'results' / 'realizability_pilot'
ACTIVE_CHILDREN = []
TERMINAL_EPISODE_STATUSES = {'SUCCEEDED', 'TECHNICAL_INVALID_FINAL'}


def interrupt_handler(_signum, _frame):
    """Route SIGTERM through the same cleanup path as Ctrl-C."""
    raise KeyboardInterrupt


def atomic_json(path, payload):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def load_json(path):
    return json.loads(Path(path).read_text())


def suite_id(profile):
    stamp = datetime.datetime.now().strftime('%Y%m%dT%H%M%S')
    return '{}_{}'.format(PROTOCOL_VERSION if profile == 'preflight' else profile, stamp)


def create_suite(output_dir, profile, repeats, targets):
    if output_dir.exists():
        raise RuntimeError('refusing to overwrite suite directory: {}'.format(output_dir))
    output_dir.mkdir(parents=True)
    specs = episode_specs(profile, repeats, targets)
    state = {
        'schema_version': 1,
        'protocol_version': PROTOCOL_VERSION,
        'profile': profile,
        'repeats': repeats,
        'status': 'PLANNED',
        'created_utc': now_utc(),
        'episodes': [
            {
                'episode_id': spec['episode_id'],
                'status': 'PENDING',
                'attempts': [],
                'spec': spec,
            }
            for spec in specs
        ],
    }
    atomic_json(output_dir / 'suite_state.json', state)
    return state


def episode_attempt_dir(suite_dir, episode, attempt_number):
    return suite_dir / 'episodes' / episode['episode_id'] / 'attempt_{:02d}'.format(attempt_number)


def wait_for_driver(driver, launch, env, timeout, monitor):
    start = time.monotonic()
    next_monitor = 0.0
    max_rss = 0
    while driver.poll() is None:
        elapsed = time.monotonic() - start
        if elapsed >= timeout:
            raise RuntimeError('pilot driver hard timeout after {:.1f}s'.format(elapsed))
        if launch.poll() is not None:
            raise RuntimeError('roslaunch exited during pilot episode with code {}'.format(
                launch.returncode))
        if elapsed >= next_monitor:
            nodes = command_output(['rosnode', 'list'], env, timeout=15)
            node_set = set(nodes.stdout.splitlines()) if nodes.returncode == 0 else set()
            missing = sorted(CORE_NODES - node_set)
            rss = descendants_rss_kb(launch.pid)
            max_rss = max(max_rss, rss)
            monitor.writerow([
                now_utc(), 'controlled_episode', '{:.1f}'.format(elapsed),
                int(launch.poll() is None), int(driver.poll() is None), rss,
                ';'.join(missing),
            ])
            next_monitor += 30.0
        time.sleep(1.0)
    if driver.returncode != 0:
        raise RuntimeError('pilot driver exited with code {}'.format(driver.returncode))
    return max_rss


def run_episode(spec, run_dir, env, episode_timeout):
    if run_dir.exists():
        raise RuntimeError('refusing to overwrite attempt: {}'.format(run_dir))
    run_dir.mkdir(parents=True)
    spec_path = run_dir / 'episode_spec.json'
    atomic_json(spec_path, spec)
    state_path = run_dir / 'run_state.json'
    state = {'status': 'RUNNING', 'started_utc': now_utc(), 'episode_id': spec['episode_id']}
    atomic_json(state_path, state)

    suffix = '_RealizabilityPilot_{}'.format(spec['episode_id'])
    diagnostics_path = run_dir / 'karto_loop_diagnostics.jsonl'
    edge_provenance_path = run_dir / 'karto_edge_provenance.jsonl'
    run_id = 'realizability_{}'.format(spec['episode_id'])
    roscore = launch = mapping_result = driver = None
    mapping_stream = None
    monitor_stream = open(run_dir / 'monitor.csv', 'w', newline='', buffering=1)
    monitor = csv.writer(monitor_stream)
    monitor.writerow([
        'wall_time_utc', 'stage', 'elapsed_wall_s', 'launch_alive',
        'driver_alive', 'rss_kb', 'missing_core_nodes',
    ])
    max_rss = 0
    try:
        existing = command_output(['rosparam', 'list'], env, timeout=5)
        if existing.returncode == 0:
            raise RuntimeError('a ROS master is already running; refusing to mix experiments')

        roscore = start_process(['roscore'], env, run_dir / 'roscore.log')
        ACTIVE_CHILDREN.append(roscore)
        wait_for_command(['rosparam', 'list'], env, 60, 'ROS master')
        ros_run_id = write_command_result(
            ['rosparam', 'get', '/run_id'], env, run_dir / 'ros_run_id.txt', timeout=10
        ).strip()

        launch_args = [
            'roslaunch', 'cpp_solver', 'exploration.launch',
            'suffix:={}'.format(suffix),
            'strategy:=NearestFrontierPlanner',
            'only_use_tsp:=true',
            'tsp_seed:={}'.format(31000 + int(spec['sequence'])),
            'map_name:={}'.format(spec['map_name']),
            'robot_position:={}'.format(spec['robot_position']),
            'map_width:={}'.format(spec['map_width']),
            'need_noise:=false', 'variance:=0', 'oracle_mode:=0',
            'enable_loop_diagnostics:={}'.format(
                'true' if spec['diagnostics_enabled'] else 'false'),
            'enable_edge_provenance:=true',
            'edge_provenance_path:={}'.format(edge_provenance_path),
            'edge_provenance_run_id:={}'.format(run_id),
            'enable_full_pose_graph_observer:=true',
        ]
        if spec['diagnostics_enabled']:
            launch_args.extend([
                'loop_diagnostics_path:={}'.format(diagnostics_path),
                'loop_diagnostics_run_id:={}'.format(run_id),
            ])
        launch = start_process(launch_args, env, run_dir / 'roslaunch.log')
        ACTIVE_CHILDREN.append(launch)

        for service in ('/StartMapping', '/StartExploration'):
            wait_for_command(['rosservice', 'type', service], env, 180, service)
        wait_for_command(['rostopic', 'type', '/slam_pose_graph'], env, 120,
                         '/slam_pose_graph')
        wait_for_command(['rostopic', 'type', '/Mapper/loop_closed'], env, 120,
                         '/Mapper/loop_closed')
        write_command_result(['rosparam', 'get', '/Mapper'], env,
                             run_dir / 'mapper_params.yaml')
        write_command_result(['rosnode', 'list'], env, run_dir / 'initial_rosnode_list.txt')

        # Subscribe to the incremental pose-graph stream before mapping starts.
        # The planner advances the mapper's global publication cursor, so a
        # driver launched after GetFirstMap can permanently miss early nodes.
        start_gate = '/constraint_realizability_pilot/start_gate'
        write_command_result(['rosparam', 'set', start_gate, 'false'], env,
                             run_dir / 'pilot_start_gate_closed.txt', timeout=10)
        driver = start_process([
            '/usr/bin/python3', str(THIS_DIR / 'pilot_driver.py'),
            '--spec', str(spec_path), '--output-dir', str(run_dir),
            '--start-gate-param', start_gate,
        ], env, run_dir / 'driver.log')
        ACTIVE_CHILDREN.append(driver)
        wait_for_command(['rosparam', 'get', start_gate + '_subscriber_ready'],
                         env, 60, 'pilot subscriber readiness')

        mapping_stream = open(run_dir / 'get_first_map_result.txt', 'w', buffering=1)
        mapping_result = subprocess.Popen(
            ['rostopic', 'echo', '-n', '1', '/GetFirstMap/result'], env=env,
            cwd=str(ROOT), stdout=mapping_stream, stderr=subprocess.STDOUT,
            text=True, start_new_session=True,
        )
        ACTIVE_CHILDREN.append(mapping_result)
        time.sleep(1)
        write_command_result(['rosservice', 'call', '/StartMapping', '{}'], env,
                             run_dir / 'start_mapping_service.txt', timeout=30)
        max_rss = max(max_rss, wait_for_topic_result(
            mapping_result, run_dir / 'get_first_map_result.txt', launch, launch,
            env, min(1200, episode_timeout), monitor, 'initial_mapping'))
        mapping_stream.close()
        mapping_stream = None
        if parse_action_status(run_dir / 'get_first_map_result.txt') != 3:
            raise RuntimeError('GetFirstMap did not SUCCEED')

        write_command_result(['rosparam', 'set', start_gate, 'true'], env,
                             run_dir / 'pilot_start_gate_opened.txt', timeout=10)
        max_rss = max(max_rss, wait_for_driver(
            driver, launch, env, episode_timeout, monitor))

        result = load_json(run_dir / 'episode_result.json')
        if result.get('status') != 'SUCCEEDED':
            raise RuntimeError('pilot driver failed: {}'.format(result.get('reason')))

        try:
            write_command_result(
                ['rosrun', 'map_server', 'map_saver', '-f', str(run_dir / 'final_map')],
                env, run_dir / 'map_saver.log', timeout=90)
        except Exception as exc:
            (run_dir / 'map_saver_warning.txt').write_text('{}\n'.format(exc))

        stop_process(launch); launch = None
        stop_process(roscore); roscore = None
        rosout_source = Path(env['ROS_LOG_DIR']) / ros_run_id / 'rosout.log'
        if rosout_source.is_file():
            shutil.copy2(rosout_source, run_dir / 'rosout.log')
        copy_author_outputs(suffix, run_dir)
        manifest = {
            'episode_id': spec['episode_id'],
            'protocol_version': spec['protocol_version'],
            'map_id': spec['map_id'],
            'baseline_commit': subprocess.check_output(
                ['git', '-C', str(BASELINE), 'rev-parse', 'HEAD'], text=True).strip(),
            'navigation_2d_commit': subprocess.check_output(
                ['git', '-C', str(ROOT / 'dependencies' / 'navigation_2d'),
                 'rev-parse', 'HEAD'], text=True).strip(),
            'diagnostics_enabled': spec['diagnostics_enabled'],
            'edge_provenance_enabled': True,
            'max_process_tree_rss_kb': max_rss,
            'analysis_eligible': result['analysis_eligible'],
            'target_constraint': result['target_constraint'],
            'target_backend_measurement': result.get('target_backend_measurement'),
            'target_nonexplicit_marker_constraint': result.get(
                'target_nonexplicit_marker_constraint'),
            'target_nonexplicit_full_graph_constraint': result.get(
                'target_nonexplicit_full_graph_constraint'),
            'wrong_target_constraint': result['wrong_target_constraint'],
        }
        atomic_json(run_dir / 'manifest.json', manifest)
        state.update({
            'status': 'SUCCEEDED', 'finished_utc': now_utc(),
            'analysis_eligible': result['analysis_eligible'],
            'target_constraint': result['target_constraint'],
            'target_backend_measurement': result.get('target_backend_measurement'),
            'target_nonexplicit_full_graph_constraint': result.get(
                'target_nonexplicit_full_graph_constraint'),
        })
        atomic_json(state_path, state)
        return state
    except KeyboardInterrupt:
        state.update({'status': 'INTERRUPTED', 'finished_utc': now_utc()})
        atomic_json(state_path, state)
        raise
    except Exception as exc:
        state.update({
            'status': 'FAILED', 'finished_utc': now_utc(),
            'reason': '{}: {}'.format(type(exc).__name__, exc),
        })
        atomic_json(state_path, state)
        raise
    finally:
        if mapping_stream is not None and not mapping_stream.closed:
            mapping_stream.close()
        stop_process(driver)
        stop_process(mapping_result)
        stop_process(launch)
        stop_process(roscore)
        for process in (driver, mapping_result, launch, roscore):
            if process in ACTIVE_CHILDREN:
                ACTIVE_CHILDREN.remove(process)
        monitor_stream.close()


def execute_suite(suite_dir, max_episodes=None, retry_failed=False):
    state_path = suite_dir / 'suite_state.json'
    state = load_json(state_path)
    completed_this_invocation = 0
    # A resumed worker owns a new suite-level lifecycle. Preserve failed attempt
    # records, but do not leave their terminal reason attached to a later
    # RUNNING/PAUSED/SUCCEEDED suite state.
    state.pop('reason', None)
    state.pop('finished_utc', None)
    state.update({
        'status': 'RUNNING', 'worker_pid': os.getpid(),
        'worker_pgid': os.getpgrp(), 'last_started_utc': now_utc(),
    })
    atomic_json(state_path, state)
    env = activated_environment()
    try:
        for episode in state['episodes']:
            if episode['status'] in TERMINAL_EPISODE_STATUSES:
                continue
            if episode['status'] == 'FAILED' and not retry_failed:
                continue
            if max_episodes is not None and completed_this_invocation >= max_episodes:
                break
            attempt_number = len(episode['attempts']) + 1
            run_dir = episode_attempt_dir(suite_dir, episode, attempt_number)
            attempt = {
                'attempt': attempt_number, 'run_dir': str(run_dir.relative_to(suite_dir)),
                'status': 'RUNNING', 'started_utc': now_utc(),
            }
            episode['attempts'].append(attempt)
            episode['status'] = 'RUNNING'
            atomic_json(state_path, state)
            try:
                result = run_episode(episode['spec'], run_dir, env, episode_timeout=2700)
                attempt.update(result)
                attempt['status'] = 'SUCCEEDED'
                episode['status'] = 'SUCCEEDED'
                completed_this_invocation += 1
            except KeyboardInterrupt:
                attempt['status'] = 'INTERRUPTED'
                attempt['finished_utc'] = now_utc()
                episode['status'] = 'INTERRUPTED'
                raise
            except Exception as exc:
                attempt.update({
                    'status': 'FAILED', 'finished_utc': now_utc(),
                    'reason': '{}: {}'.format(type(exc).__name__, exc),
                })
                episode['status'] = 'FAILED'
                # Fail closed: do not silently continue after an infrastructure or
                # navigation failure.  Resume explicitly with --retry-failed.
                raise
            finally:
                atomic_json(state_path, state)

        unfinished = [episode for episode in state['episodes']
                      if episode['status'] not in TERMINAL_EPISODE_STATUSES]
        invalid = [episode for episode in state['episodes']
                   if episode['status'] == 'TECHNICAL_INVALID_FINAL']
        state['status'] = ('SUCCEEDED' if not unfinished and not invalid else 'PAUSED')
        state['finished_utc'] = now_utc()
        atomic_json(state_path, state)
    except KeyboardInterrupt:
        state.update({'status': 'INTERRUPTED', 'finished_utc': now_utc()})
        atomic_json(state_path, state)
        return 130
    except Exception as exc:
        state.update({
            'status': 'FAILED', 'finished_utc': now_utc(),
            'reason': '{}: {}'.format(type(exc).__name__, exc),
        })
        atomic_json(state_path, state)
        raise
    finally:
        state.pop('worker_pid', None)
        state.pop('worker_pgid', None)
        atomic_json(state_path, state)
    return 0


def verified_worker(state):
    pid = state.get('worker_pid')
    pgid = state.get('worker_pgid')
    if not pid or not pgid:
        return None
    proc = Path('/proc') / str(pid) / 'cmdline'
    if not proc.is_file():
        return None
    command = proc.read_bytes().replace(b'\0', b' ').decode(errors='replace')
    if 'realizability_pilot/run_pilot.py' not in command:
        return None
    return int(pid), int(pgid), command


def main():
    # SIGINT already raises KeyboardInterrupt.  Give detached workers the same
    # cleanup path for a normal SIGTERM from a session manager.
    signal.signal(signal.SIGTERM, interrupt_handler)
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)

    plan = sub.add_parser('plan')
    plan.add_argument('--profile', choices=('preflight', 'screening'), default='preflight')
    plan.add_argument('--repeats', type=int, default=1)
    plan.add_argument('--target', action='append', dest='targets')
    plan.add_argument('--suite-dir', type=Path)

    run = sub.add_parser('run')
    run.add_argument('--suite-dir', required=True, type=Path)
    run.add_argument('--max-episodes', type=int)
    run.add_argument('--retry-failed', action='store_true')

    start = sub.add_parser('start')
    start.add_argument('--suite-dir', required=True, type=Path)
    start.add_argument('--max-episodes', type=int)
    start.add_argument('--retry-failed', action='store_true')

    status = sub.add_parser('status')
    status.add_argument('--suite-dir', required=True, type=Path)

    stop = sub.add_parser('stop')
    stop.add_argument('--suite-dir', required=True, type=Path)

    args = parser.parse_args()

    if args.command == 'plan':
        directory = args.suite_dir or (DEFAULT_ROOT / suite_id(args.profile))
        state = create_suite(directory.resolve(), args.profile, args.repeats, args.targets)
        print(json.dumps({'suite_dir': str(directory.resolve()),
                          'episodes': len(state['episodes'])}, indent=2))
        return
    if args.command == 'run':
        raise SystemExit(execute_suite(args.suite_dir.resolve(), args.max_episodes,
                                       args.retry_failed))
    if args.command == 'start':
        suite_dir = args.suite_dir.resolve()
        state = load_json(suite_dir / 'suite_state.json')
        if verified_worker(state):
            raise SystemExit('suite already has a verified live worker')
        command = ['/usr/bin/python3', str(Path(__file__).resolve()), 'run',
                   '--suite-dir', str(suite_dir)]
        if args.max_episodes is not None:
            command.extend(['--max-episodes', str(args.max_episodes)])
        if args.retry_failed:
            command.append('--retry-failed')
        log = open(suite_dir / 'suite.log', 'a', buffering=1)
        process = subprocess.Popen(command, cwd=str(ROOT), stdout=log,
                                   stderr=subprocess.STDOUT, text=True,
                                   start_new_session=True)
        # The worker writes its own authoritative pid/pgid after starting.
        atomic_json(suite_dir / 'launcher.json', {
            'launcher_pid': process.pid, 'command': command, 'started_utc': now_utc(),
            'log': str(suite_dir / 'suite.log'),
        })
        print(json.dumps({'pid': process.pid, 'suite_dir': str(suite_dir),
                          'log': str(suite_dir / 'suite.log')}, indent=2))
        return
    if args.command == 'status':
        state = load_json(args.suite_dir.resolve() / 'suite_state.json')
        live = verified_worker(state)
        summary = {
            'status': state['status'],
            'live_worker': bool(live),
            'counts': {},
        }
        for episode in state['episodes']:
            summary['counts'][episode['status']] = summary['counts'].get(episode['status'], 0) + 1
        if live:
            summary['worker_pid'], summary['worker_pgid'], _ = live
        print(json.dumps(summary, indent=2, sort_keys=True))
        return
    if args.command == 'stop':
        suite_dir = args.suite_dir.resolve()
        state = load_json(suite_dir / 'suite_state.json')
        live = verified_worker(state)
        if not live:
            raise SystemExit('no verified live worker for this suite')
        _, pgid, command = live
        os.killpg(pgid, signal.SIGINT)
        print('sent SIGINT to verified pilot worker group {}: {}'.format(pgid, command))


if __name__ == '__main__':
    main()
