#!/usr/bin/python3
"""Suite runner for the continuous revisit action experiment.

One episode = one fresh Stage + Karto run (continuous chain, no stitching).
The runner owns the process lifecycle and the suite ledger; the driver owns the
route, the phases and the observation records.  Execution is strictly serial so
that two simulators never compete for CPU.

CLI:

    runner.py plan                       # write the 48-episode ledger
    runner.py run [--max-episodes N]     # execute pending episodes, serially
    runner.py resume                     # retry failed episodes, keep the record
    runner.py status
    runner.py analyze                    # delegate to analysis.py
"""

import argparse
import csv
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
ROOT = THIS_DIR.parents[2]
sys.path.insert(0, str(ROOT / 'tools'))

from run_phase2_pairs import (  # noqa: E402
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

sys.path.insert(0, str(THIS_DIR.parent))
from continuous_revisit import protocol as cr  # noqa: E402

DEFAULT_OUTPUT = ROOT / 'results' / 'realizability_pilot' / \
    'p1_continuous_revisit_actions_20261010'

ACTIVE_CHILDREN = []
TERMINAL_STATUSES = {'SUCCEEDED', 'TECHNICAL_INVALID_FINAL'}


def atomic_json(path, payload):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(payload, indent=1, sort_keys=True, default=str))
    os.replace(tmp, path)


def load_json(path):
    return json.loads(Path(path).read_text())


def interrupt_handler(_signum, _frame):
    for child in list(ACTIVE_CHILDREN):
        stop_process(child)
    raise KeyboardInterrupt


def repeatability_specs(configs, replays):
    """Same configurations as the main matrix, executed once more.

    Each spec is copied byte-for-byte from the main matrix (same place, repeat,
    action, order, ``tsp_seed``) and only the identifier is suffixed, so the
    commanded conditions are identical and the spread measures pipeline and
    backend repeatability.
    """
    main = {spec['episode_id']: spec for spec in cr.episode_specs()}
    specs = []
    for config in configs:
        place_id, repeat, action_id = config.split(':')
        base = next(spec for spec in main.values()
                    if spec['place_id'] == place_id
                    and int(spec['repeat']) == int(repeat)
                    and spec['action_id'] == action_id)
        for replay in range(1, replays + 1):
            spec = json.loads(json.dumps(base))
            spec['episode_id'] = '{}_{}_rep{}'.format(base['episode_id'],
                                                      action_id, replay)
            spec['round'] = 'repeatability'
            spec['repeatability_of'] = base['episode_id']
            spec['replay_index'] = replay
            specs.append(spec)
    return specs


def plan_suite(suite_dir, smoke=False, repeatability=None, replays=2):
    suite_dir.mkdir(parents=True, exist_ok=True)
    state_path = suite_dir / 'suite_state.json'
    episodes = []
    if repeatability:
        specs = repeatability_specs(repeatability, replays)
    elif smoke:
        specs = []
        sequence = 0
        for action_id in cr.ACTION_IDS:
            sequence += 1
            specs.append(cr.build_spec('place_B', 1, action_id, sequence, 0,
                                       sequence - 1, smoke=True))
    else:
        specs = cr.episode_specs()
    for spec in specs:
        episodes.append({'episode_id': spec['episode_id'], 'spec': spec,
                         'status': 'PENDING', 'attempts': []})
    state = {
        'schema_version': 1,
        'protocol_version': cr.PROTOCOL_VERSION,
        'created_utc': now_utc(),
        'status': 'PLANNED',
        'episodes': episodes,
    }
    atomic_json(state_path, state)
    plan = {
        'protocol_version': cr.PROTOCOL_VERSION,
        'map_id': cr.MAP_ID,
        'route_offsets': cr.ROUTE_OFFSETS,
        'places': cr.PLACES,
        'actions': {key: {k: v for k, v in value.items() if k != 'waypoints'}
                    for key, value in cr.ACTIONS.items()},
        'action_frames': cr.ACTION_FRAMES,
        'repeats': cr.REPEATS,
        'mode': ('repeatability' if repeatability
                 else ('smoke' if smoke else 'main')),
        'episode_count': len(episodes),
    }
    atomic_json(suite_dir / 'experiment_plan.json', plan)
    return state


def wait_for_driver(driver, launch, env, timeout, monitor):
    start = time.monotonic()
    next_monitor = 0.0
    while driver.poll() is None:
        elapsed = time.monotonic() - start
        if elapsed >= timeout:
            stop_process(driver)
            raise RuntimeError('driver hard timeout after {:.1f}s'.format(elapsed))
        if launch.poll() is not None:
            raise RuntimeError('roslaunch exited during the episode with code {}'.
                               format(launch.returncode))
        if elapsed >= next_monitor:
            nodes = command_output(['rosnode', 'list'], env, timeout=15)
            node_set = set(nodes.stdout.splitlines()) if nodes.returncode == 0 else set()
            missing = sorted(CORE_NODES - node_set)
            rss = descendants_rss_kb(launch.pid)
            monitor.writerow([
                now_utc(), 'continuous_episode', '{:.1f}'.format(elapsed),
                int(launch.poll() is None), int(driver.poll() is None), rss,
                ';'.join(missing),
            ])
            next_monitor += 30.0
        time.sleep(1.0)
    if driver.returncode != 0:
        raise RuntimeError('driver exited with code {}'.format(driver.returncode))


def episode_dir(suite_dir, episode_id, attempt):
    return suite_dir / 'episodes' / episode_id / 'attempt_{:02d}'.format(attempt)


def run_episode(spec, run_dir, env, episode_timeout):
    if run_dir.exists():
        raise RuntimeError('refusing to overwrite attempt: {}'.format(run_dir))
    run_dir.mkdir(parents=True)
    spec_path = run_dir / 'episode_spec.json'
    atomic_json(spec_path, spec)
    state_path = run_dir / 'run_state.json'
    atomic_json(state_path, {'status': 'RUNNING', 'started_utc': now_utc(),
                             'episode_id': spec['episode_id']})

    suffix = '_ContinuousRevisit_{}'.format(spec['episode_id'])
    edge_provenance_path = run_dir / 'karto_edge_provenance.jsonl'
    run_id = 'continuous_revisit_{}'.format(spec['episode_id'])
    roscore = launch = mapping_result = driver = None
    monitor_stream = open(run_dir / 'monitor.csv', 'w', newline='', buffering=1)
    monitor = csv.writer(monitor_stream)
    monitor.writerow(['wall_time_utc', 'stage', 'elapsed_wall_s',
                      'launch_alive', 'driver_alive', 'rss_kb',
                      'missing_core_nodes'])
    try:
        existing = command_output(['rosparam', 'list'], env, timeout=5)
        if existing.returncode == 0:
            raise RuntimeError('a ROS master is already running')

        roscore = start_process(['roscore'], env, run_dir / 'roscore.log')
        ACTIVE_CHILDREN.append(roscore)
        wait_for_command(['rosparam', 'list'], env, 60, 'ROS master')
        ros_run_id = write_command_result(
            ['rosparam', 'get', '/run_id'], env, run_dir / 'ros_run_id.txt',
            timeout=10).strip()

        launch_args = [
            'roslaunch', 'cpp_solver', 'exploration.launch',
            'suffix:={}'.format(suffix),
            'strategy:=NearestFrontierPlanner',
            'only_use_tsp:=true',
            'tsp_seed:={}'.format(int(spec.get('tsp_seed', 44000))),
            'map_name:={}'.format(spec['map_name']),
            'robot_position:={}'.format(spec['robot_position']),
            'map_width:={}'.format(spec['map_width']),
            'need_noise:=false', 'variance:=0', 'oracle_mode:=0',
            'enable_loop_diagnostics:=false',
            'enable_edge_provenance:=true',
            'edge_provenance_path:={}'.format(edge_provenance_path),
            'edge_provenance_run_id:={}'.format(run_id),
            'enable_full_pose_graph_observer:=true',
            'instrumentation_flush_period_s:=0.0',
            'pose_graph_dump_path:={}'.format(run_dir / 'pose_graph_dump.json'),
        ]
        launch = start_process(launch_args, env, run_dir / 'roslaunch.log')
        ACTIVE_CHILDREN.append(launch)
        for service in ('/StartMapping', '/StartExploration'):
            wait_for_command(['rosservice', 'type', service], env, 180, service)
        wait_for_command(['rostopic', 'type', '/slam_pose_graph'], env, 120,
                         '/slam_pose_graph')
        write_command_result(['rosparam', 'get', '/Mapper'], env,
                             run_dir / 'mapper_params.yaml')
        write_command_result(['rosnode', 'list'], env,
                             run_dir / 'initial_rosnode_list.txt')

        start_gate = '/continuous_revisit/start_gate'
        write_command_result(['rosparam', 'set', start_gate, 'false'], env,
                             run_dir / 'start_gate_closed.txt', timeout=10)
        driver = start_process([
            '/usr/bin/python3', str(THIS_DIR / 'driver.py'),
            '--spec', str(spec_path), '--output-dir', str(run_dir),
            '--start-gate-param', start_gate,
        ], env, run_dir / 'driver.log')
        ACTIVE_CHILDREN.append(driver)
        wait_for_command(['rosparam', 'get', start_gate + '_subscriber_ready'],
                         env, 60, 'driver subscriber readiness')

        mapping_stream = open(run_dir / 'get_first_map_result.txt', 'w',
                              buffering=1)
        mapping_result = subprocess.Popen(
            ['rostopic', 'echo', '-n', '1', '/GetFirstMap/result'], env=env,
            cwd=str(ROOT), stdout=mapping_stream, stderr=subprocess.STDOUT,
            text=True, start_new_session=True)
        ACTIVE_CHILDREN.append(mapping_result)
        time.sleep(1)
        write_command_result(['rosservice', 'call', '/StartMapping', '{}'], env,
                             run_dir / 'start_mapping_service.txt', timeout=30)
        wait_for_topic_result(mapping_result, run_dir / 'get_first_map_result.txt',
                              launch, launch, env, min(1200, episode_timeout),
                              monitor, 'initial_mapping')
        mapping_stream.close()
        mapping_stream = None
        if parse_action_status(run_dir / 'get_first_map_result.txt') != 3:
            raise RuntimeError('GetFirstMap did not succeed')

        write_command_result(['rosparam', 'set', start_gate, 'true'], env,
                             run_dir / 'start_gate_opened.txt', timeout=10)
        wait_for_driver(driver, launch, env, episode_timeout, monitor)

        result = load_json(run_dir / 'episode_result.json')
        if result.get('status') != 'SUCCEEDED':
            raise RuntimeError('driver reported {}'.format(result.get('status')))

        write_command_result(['rosrun', 'map_server', 'map_saver', '-f',
                              str(run_dir / 'final_map')], env,
                             run_dir / 'map_saver.log', timeout=90)

        stop_process(launch); launch = None
        stop_process(roscore); roscore = None
        rosout_source = Path(env.get('ROS_LOG_DIR', '/tmp')) / ros_run_id / 'rosout.log'
        if rosout_source.is_file():
            shutil.copy2(rosout_source, run_dir / 'rosout.log')
        try:
            copy_author_outputs(suffix, run_dir)
        except Exception as exc:  # author outputs are a convenience only
            (run_dir / 'author_outputs_warning.txt').write_text('{}\n'.format(exc))

        manifest = {
            'episode_id': spec['episode_id'],
            'place_id': spec['place_id'],
            'action_id': spec['action_id'],
            'group_id': spec['group_id'],
            'order_position': spec['order_position'],
            'protocol_version': spec['protocol_version'],
            'map_id': spec['map_id'],
            'provenance_enabled': True,
            'observer_enabled': True,
            'analysis_eligible': result.get('analysis_eligible', False),
            'baseline_commit': command_output(
                ['git', '-C', str(ROOT / 'baseline' / 'Graph-Based_SLAM-Aware_Exploration'),
                 'rev-parse', 'HEAD'], env, timeout=30).stdout.strip(),
        }
        atomic_json(run_dir / 'manifest.json', manifest)
        state = {'status': 'SUCCEEDED', 'finished_utc': now_utc(),
                 'analysis_eligible': result.get('analysis_eligible', False)}
        atomic_json(state_path, state)
        return state
    except KeyboardInterrupt:
        atomic_json(state_path, {'status': 'INTERRUPTED', 'finished_utc': now_utc()})
        raise
    except Exception as exc:
        atomic_json(state_path, {
            'status': 'FAILED', 'finished_utc': now_utc(),
            'reason': '{}: {}'.format(type(exc).__name__, exc)})
        raise
    finally:
        if 'mapping_stream' in dir() and mapping_stream is not None \
                and not mapping_stream.closed:
            mapping_stream.close()
        for process in (driver, mapping_result, launch, roscore):
            stop_process(process)
        for process in (driver, mapping_result, launch, roscore):
            if process in ACTIVE_CHILDREN:
                ACTIVE_CHILDREN.remove(process)
        monitor_stream.close()


def execute(suite_dir, max_episodes=None, retry_failed=False):
    state_path = suite_dir / 'suite_state.json'
    state = load_json(state_path)
    env = activated_environment()
    executed = 0
    for episode in state['episodes']:
        if episode['status'] in TERMINAL_STATUSES:
            continue
        if episode['status'] == 'FAILED' and not retry_failed:
            continue
        if max_episodes is not None and executed >= max_episodes:
            break
        attempt = len(episode['attempts']) + 1
        run_dir = episode_dir(suite_dir, episode['episode_id'], attempt)
        state['status'] = 'RUNNING'
        state['last_started_utc'] = now_utc()
        atomic_json(state_path, state)
        started = now_utc()
        try:
            run_episode(episode['spec'], run_dir, env, 3600)
            episode['status'] = 'SUCCEEDED'
            record = {'attempt': attempt, 'status': 'SUCCEEDED',
                      'run_dir': str(run_dir.relative_to(suite_dir)),
                      'started_utc': started, 'finished_utc': now_utc()}
        except KeyboardInterrupt:
            episode['status'] = 'INTERRUPTED'
            record = {'attempt': attempt, 'status': 'INTERRUPTED',
                      'run_dir': str(run_dir.relative_to(suite_dir)),
                      'started_utc': started, 'finished_utc': now_utc()}
            episode['attempts'].append(record)
            state['status'] = 'INTERRUPTED'
            atomic_json(state_path, state)
            raise
        except Exception as exc:
            episode['status'] = 'FAILED'
            record = {'attempt': attempt, 'status': 'FAILED',
                      'run_dir': str(run_dir.relative_to(suite_dir)),
                      'reason': '{}: {}'.format(type(exc).__name__, exc),
                      'started_utc': started, 'finished_utc': now_utc()}
        episode['attempts'].append(record)
        executed += 1
        atomic_json(state_path, state)

    unfinished = [episode for episode in state['episodes']
                  if episode['status'] not in TERMINAL_STATUSES]
    failed = [episode for episode in state['episodes']
              if episode['status'] == 'FAILED']
    state['status'] = ('SUCCEEDED' if not unfinished
                       else ('PAUSED_ON_FAILURE' if failed else 'RUNNING'))
    state['finished_utc'] = now_utc()
    atomic_json(state_path, state)
    return state


def status(suite_dir):
    state = load_json(suite_dir / 'suite_state.json')
    counts = {}
    for episode in state['episodes']:
        counts[episode['status']] = counts.get(episode['status'], 0) + 1
    return {'status': state['status'], 'counts': counts,
            'total': len(state['episodes'])}


def main():
    signal.signal(signal.SIGTERM, interrupt_handler)
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('plan', 'run', 'resume', 'status', 'analyze'):
        item = sub.add_parser(name)
        item.add_argument('--suite-dir', default=str(DEFAULT_OUTPUT))
        if name == 'run':
            item.add_argument('--max-episodes', type=int)
        if name == 'plan':
            item.add_argument('--smoke', action='store_true')
            item.add_argument('--repeatability',
                              help='comma separated place:repeat:action configs')
            item.add_argument('--replays', type=int, default=2)
    args = parser.parse_args()
    suite_dir = Path(args.suite_dir)
    if args.command == 'plan':
        repeatability = getattr(args, 'repeatability', None)
        state = plan_suite(suite_dir, smoke=getattr(args, 'smoke', False),
                           repeatability=(repeatability.split(',')
                                          if repeatability else None),
                           replays=getattr(args, 'replays', 2))
        print(json.dumps({'planned': len(state['episodes']),
                          'suite': str(suite_dir)}, indent=1))
    elif args.command == 'run':
        state = execute(suite_dir, args.max_episodes, retry_failed=False)
        print(json.dumps(status(suite_dir), indent=1, default=str))
    elif args.command == 'resume':
        state = execute(suite_dir, None, retry_failed=True)
        print(json.dumps(status(suite_dir), indent=1, default=str))
    elif args.command == 'status':
        print(json.dumps(status(suite_dir), indent=1, default=str))
    elif args.command == 'analyze':
        sys.path.insert(0, str(THIS_DIR))
        import analysis
        payload = analysis.analyze_suite(suite_dir)
        print(json.dumps(payload, indent=1, default=str))


if __name__ == '__main__':
    main()
