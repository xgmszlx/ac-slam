#!/usr/bin/python3
"""Bounded runner for the Doc-79 synchronous revisit validation.

One episode = one fresh Stage + Karto run with the Doc-79 observation chain
(native-scan telemetry barrier + serialized provenance flush + synchronous
pose-graph export at every boundary).  Strictly serial; everything counts
against the 8-episode budget: successes, technical failures, interruptions and
retries.

CLI:

    runner.py plan                  # write the 8-episode ledger
    runner.py run [--max-episodes N]
    runner.py resume                # retry the halted episode (new attempt)
    runner.py status
    runner.py analyze
"""

import argparse
import csv
import hashlib
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
sys.path.insert(0, str(THIS_DIR.parent))

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

import suite as doc79_suite  # noqa: E402

DEFAULT_OUTPUT = ROOT / 'results' / 'realizability_pilot' / \
    'p1_doc79_synchronous_revisit_validation_20261012'

ACTIVE_CHILDREN = []
TERMINAL_STATUSES = {'SUCCEEDED'}
SYNC_STEMS = ('before_return', 'arrival', 'action_done', 'final')


def atomic_json(path, payload):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(payload, indent=1, sort_keys=True, default=str))
    os.replace(tmp, path)


def load_json(path):
    return json.loads(Path(path).read_text())


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def interrupt_handler(_signum, _frame):
    for child in list(ACTIVE_CHILDREN):
        stop_process(child)
    raise KeyboardInterrupt


def doc79_environment():
    """The frozen catkin_ws environment plus the isolated observability build.

    The overlay workspace (doc79_ws) must win for both package lookup and the
    shared libraries, so its src/devel entries are prepended on top of the
    underlay environment produced by catkin_ws/activate.sh.
    """
    env = activated_environment()
    overlay_devel = str(ROOT / 'doc79_ws' / 'devel')
    overlay_src = str(ROOT / 'doc79_ws' / 'src')
    env['ROS_PACKAGE_PATH'] = overlay_src + ':' + env.get('ROS_PACKAGE_PATH', '')
    env['CMAKE_PREFIX_PATH'] = overlay_devel + ':' + env.get('CMAKE_PREFIX_PATH', '')
    env['LD_LIBRARY_PATH'] = overlay_devel + '/lib:' + env.get('LD_LIBRARY_PATH', '')
    env['PYTHONPATH'] = (overlay_devel + '/lib/python3/dist-packages:'
                         + env.get('PYTHONPATH', ''))
    env['DOC79_WS'] = overlay_devel
    return env


def write_runtime_provenance(suite_dir, env):
    payload = {
        'created_utc': now_utc(),
        'git_head': command_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                                   env, timeout=30).stdout.strip(),
        'branch': command_output(['git', '-C', str(ROOT), 'branch', '--show-current'],
                                 env, timeout=30).stdout.strip(),
        'overlay_package_path': env.get('ROS_PACKAGE_PATH', '').split(':')[0],
        'ld_library_first': env.get('LD_LIBRARY_PATH', '').split(':')[0],
        'mapper_binary': {
            'path': str(ROOT / 'doc79_ws/devel/lib/nav2d_karto/mapper'),
            'sha256': sha256_file(ROOT / 'doc79_ws/devel/lib/nav2d_karto/mapper'),
        },
        'multimapper_library': {
            'path': str(ROOT / 'doc79_ws/devel/lib/libMultiMapper.so'),
            'sha256': sha256_file(ROOT / 'doc79_ws/devel/lib/libMultiMapper.so'),
        },
        'production_multimapper_library': {
            'path': str(ROOT / 'catkin_ws/devel/lib/libMultiMapper.so'),
            'sha256': sha256_file(ROOT / 'catkin_ws/devel/lib/libMultiMapper.so'),
        },
        'driver': {'path': str(THIS_DIR / 'driver.py'),
                   'sha256': sha256_file(THIS_DIR / 'driver.py')},
        'suite_module': {'path': str(THIS_DIR / 'suite.py'),
                         'sha256': sha256_file(THIS_DIR / 'suite.py')},
    }
    atomic_json(Path(suite_dir) / 'audit' / 'runtime_provenance.json', payload)
    return payload


def plan_suite(suite_dir):
    suite_dir.mkdir(parents=True, exist_ok=True)
    specs = doc79_suite.doc79_specs()
    if len(specs) > doc79_suite.BUDGET_EPISODES:
        raise RuntimeError('plan exceeds the frozen budget')
    episodes = [{'episode_id': spec['episode_id'], 'spec': spec,
                 'status': 'PENDING', 'attempts': []} for spec in specs]
    state = {
        'schema_version': 1,
        'protocol_version': 'p1_doc79_synchronous_revisit_validation_v1',
        'doc79_order': [spec['episode_id'] for spec in specs],
        'budget_episodes': doc79_suite.BUDGET_EPISODES,
        'created_utc': now_utc(),
        'status': 'PLANNED',
        'episodes': episodes,
    }
    atomic_json(suite_dir / 'suite_state.json', state)
    return state


def attempts_used(state):
    return sum(len(episode['attempts']) for episode in state['episodes'])


def wait_for_driver(driver, launch, env, timeout, monitor, suite_dir):
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
            monitor.writerow([now_utc(), 'doc79_episode', '{:.1f}'.format(elapsed),
                              int(launch.poll() is None), int(driver.poll() is None),
                              rss, ';'.join(missing)])
            next_monitor += 30.0
        time.sleep(1.0)
    if driver.returncode != 0:
        raise RuntimeError('driver exited with code {}'.format(driver.returncode))


def technical_check(run_dir):
    """Observation-chain eligibility of one finished attempt (read-only)."""
    reasons = []
    details = {}
    manifest_path = run_dir / 'boundary_manifest.json'
    if not manifest_path.is_file():
        return False, ['boundary_manifest.json missing'], details
    manifest = load_json(manifest_path)
    missing = [name for name in ('G_before_return', 'G_arrival',
                                 'G_action_done', 'G_final')
               if name not in manifest]
    if missing:
        reasons.append('boundaries missing from manifest: {}'.format(missing))
    spec = load_json(run_dir / 'episode_spec.json')
    run_id = spec.get('provenance_run_id')
    for name in ('G_before_return', 'G_arrival', 'G_action_done', 'G_final'):
        entry = manifest.get(name)
        if not entry:
            continue
        if not entry.get('all_checks_passed'):
            failed = [key for key, value in (entry.get('checks') or {}).items()
                      if not value]
            reasons.append('{} checks failed: {}'.format(name, failed))
        sync_file = (entry.get('sync_file') or {}).get('path')
        if not sync_file or not Path(sync_file).is_file():
            reasons.append('{} sync file missing'.format(name))
            continue
        try:
            parsed = load_json(sync_file)
        except Exception as exc:  # noqa: BLE001
            reasons.append('{} sync file unreadable: {}'.format(name, exc))
            continue
        if parsed.get('run_id') != run_id:
            reasons.append('{} run_id mismatch'.format(name))
        recorded = (entry.get('sync_file') or {}).get('sha256')
        if recorded != sha256_file(sync_file):
            reasons.append('{} sha256 mismatch'.format(name))
        details[name] = {
            'nodes': len(parsed.get('nodes', [])),
            'edges': len(parsed.get('edges', [])),
            'topic_nodes': (entry.get('topic_cache') or {}).get('node_count'),
            'topic_edges': (entry.get('topic_cache') or {}).get('edge_count'),
        }
    provenance = run_dir / 'karto_edge_provenance.jsonl'
    if not provenance.is_file() or provenance.stat().st_size == 0:
        reasons.append('provenance file missing or empty')
    else:
        first = None
        count = 0
        with open(provenance) as handle:
            for line in handle:
                if line.strip():
                    count += 1
                    if first is None:
                        first = json.loads(line)
        details['provenance_records'] = count
        if first is None or first.get('run_id') != run_id:
            reasons.append('provenance run_id mismatch')
    ledger = run_dir / 'native_processing_ledger.jsonl'
    if not ledger.is_file():
        reasons.append('native_processing_ledger.jsonl missing')
    else:
        boundaries = set()
        with open(ledger) as handle:
            for line in handle:
                if line.strip():
                    boundaries.add(json.loads(line).get('boundary'))
        if len([name for name in boundaries if name]) < 4:
            reasons.append('ledger covers fewer than four boundaries')
    result = run_dir / 'episode_result.json'
    if result.is_file():
        payload = load_json(result)
        if payload.get('status') != 'SUCCEEDED':
            reasons.append('driver status {}'.format(payload.get('status')))
    else:
        reasons.append('episode_result.json missing')
    return (not reasons), reasons, details


def run_episode(spec, run_dir, env, episode_timeout, attempt):
    if run_dir.exists():
        raise RuntimeError('refusing to overwrite attempt: {}'.format(run_dir))
    run_dir.mkdir(parents=True)
    run_id = 'doc79_{}_a{:02d}'.format(spec['episode_id'], attempt)
    spec = dict(spec)
    spec['edge_provenance_path'] = str(run_dir / 'karto_edge_provenance.jsonl')
    spec['provenance_run_id'] = run_id
    spec_path = run_dir / 'episode_spec.json'
    atomic_json(spec_path, spec)
    state_path = run_dir / 'run_state.json'
    atomic_json(state_path, {'status': 'RUNNING', 'started_utc': now_utc(),
                             'episode_id': spec['episode_id'], 'run_id': run_id})

    suffix = '_Doc79_{}'.format(spec['episode_id'])
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
            'edge_provenance_path:={}'.format(spec['edge_provenance_path']),
            'edge_provenance_run_id:={}'.format(run_id),
            'enable_full_pose_graph_observer:=true',
            # serialized export only: no maintenance-thread flush, so the
            # single writer of the provenance file is the boundary export
            'instrumentation_flush_period_s:=0.0',
        ]
        launch = start_process(launch_args, env, run_dir / 'roslaunch.log')
        ACTIVE_CHILDREN.append(launch)
        for service in ('/StartMapping', '/StartExploration'):
            wait_for_command(['rosservice', 'type', service], env, 180, service)
        wait_for_command(['rostopic', 'type', '/slam_pose_graph'], env, 120,
                         '/slam_pose_graph')
        wait_for_command(['rosservice', 'type', '/Mapper/doc79_sync_boundary_export'],
                         env, 120, 'doc79 export service')
        write_command_result(['rosparam', 'get', '/Mapper'], env,
                             run_dir / 'mapper_params.yaml')
        write_command_result(['rosnode', 'list'], env,
                             run_dir / 'initial_rosnode_list.txt')

        start_gate = '/doc79_sync/start_gate'
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
        wait_for_driver(driver, launch, env, episode_timeout, monitor, run_dir)

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
        except Exception as exc:  # noqa: BLE001
            (run_dir / 'author_outputs_warning.txt').write_text('{}\n'.format(exc))

        eligible, reasons, details = technical_check(run_dir)
        manifest = {
            'episode_id': spec['episode_id'],
            'attempt': attempt,
            'run_id': run_id,
            'place_id': spec['place_id'],
            'action_id': spec['action_id'],
            'tsp_seed': spec.get('tsp_seed'),
            'doc79_order': spec.get('doc79_order'),
            'doc79_run_index': spec.get('doc79_run_index'),
            'source_episode_id': spec.get('source_episode_id'),
            'protocol_version': spec['protocol_version'],
            'map_id': spec['map_id'],
            'sync_export_enabled': True,
            'technical_validity': 'MEASUREMENT_VALIDATED' if eligible
                                  else 'MEASUREMENT_NOT_VALIDATED',
            'technical_reasons': reasons,
            'technical_details': details,
            'baseline_commit': command_output(
                ['git', '-C', str(ROOT / 'baseline' / 'Graph-Based_SLAM-Aware_Exploration'),
                 'rev-parse', 'HEAD'], env, timeout=30).stdout.strip(),
        }
        atomic_json(run_dir / 'run_manifest.json', manifest)
        state = {'status': 'SUCCEEDED', 'finished_utc': now_utc(),
                 'analysis_eligible': result.get('analysis_eligible', False),
                 'technical_validity': manifest['technical_validity'],
                 'technical_reasons': reasons}
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
        if mapping_stream is not None and not mapping_stream.closed:
            mapping_stream.close()
        for process in (driver, mapping_result, launch, roscore):
            stop_process(process)
        for process in (driver, mapping_result, launch, roscore):
            if process in ACTIVE_CHILDREN:
                ACTIVE_CHILDREN.remove(process)
        monitor_stream.close()


def execute(suite_dir, max_episodes=None, retry_failed=False, policy='stop'):
    state_path = suite_dir / 'suite_state.json'
    state = load_json(state_path)
    env = doc79_environment()
    write_runtime_provenance(suite_dir, env)
    executed = 0
    halt_reason = None
    for episode in state['episodes']:
        if episode['status'] in TERMINAL_STATUSES:
            continue
        if episode['status'] == 'FAILED' and not retry_failed:
            continue
        if max_episodes is not None and executed >= max_episodes:
            break
        used = attempts_used(state)
        if used >= state.get('budget_episodes', doc79_suite.BUDGET_EPISODES):
            halt_reason = 'budget exhausted ({} attempts)'.format(used)
            break
        attempt = len(episode['attempts']) + 1
        run_dir = suite_dir / 'runs' / episode['episode_id'] / \
            'attempt_{:02d}'.format(attempt)
        state['status'] = 'RUNNING'
        state['last_started_utc'] = now_utc()
        state['attempts_used'] = attempts_used(state) + 1
        atomic_json(state_path, state)
        started = now_utc()
        try:
            outcome = run_episode(episode['spec'], run_dir, env, 3600, attempt)
            if outcome.get('technical_validity') == 'MEASUREMENT_VALIDATED':
                episode['status'] = 'SUCCEEDED'
            else:
                episode['status'] = 'TECHNICAL_FAILED'
                halt_reason = '{} failed technical checks: {}'.format(
                    episode['episode_id'], outcome.get('technical_reasons'))
            record = {'attempt': attempt, 'status': episode['status'],
                      'run_dir': str(run_dir.relative_to(suite_dir)),
                      'technical_validity': outcome.get('technical_validity'),
                      'technical_reasons': outcome.get('technical_reasons'),
                      'started_utc': started, 'finished_utc': now_utc()}
        except KeyboardInterrupt:
            episode['status'] = 'INTERRUPTED'
            record = {'attempt': attempt, 'status': 'INTERRUPTED',
                      'run_dir': str(run_dir.relative_to(suite_dir)),
                      'started_utc': started, 'finished_utc': now_utc()}
            episode['attempts'].append(record)
            state['status'] = 'INTERRUPTED'
            state['attempts_used'] = attempts_used(state)
            atomic_json(state_path, state)
            raise
        except Exception as exc:
            episode['status'] = 'FAILED'
            halt_reason = '{} threw {}'.format(episode['episode_id'], exc)
            record = {'attempt': attempt, 'status': 'FAILED',
                      'run_dir': str(run_dir.relative_to(suite_dir)),
                      'reason': '{}: {}'.format(type(exc).__name__, exc),
                      'started_utc': started, 'finished_utc': now_utc()}
        episode['attempts'].append(record)
        executed += 1
        state['attempts_used'] = attempts_used(state)
        atomic_json(state_path, state)
        if halt_reason and policy == 'stop':
            break

    unfinished = [episode for episode in state['episodes']
                  if episode['status'] not in TERMINAL_STATUSES]
    if halt_reason:
        state['status'] = 'PAUSED_ON_TECHNICAL_FAILURE'
        state['halt_reason'] = halt_reason
    else:
        state['status'] = 'SUCCEEDED' if not unfinished else 'RUNNING'
    state['finished_utc'] = now_utc()
    state['attempts_used'] = attempts_used(state)
    atomic_json(state_path, state)
    return state


def status(suite_dir):
    state = load_json(suite_dir / 'suite_state.json')
    counts = {}
    for episode in state['episodes']:
        counts[episode['status']] = counts.get(episode['status'], 0) + 1
    return {'status': state['status'],
            'counts': counts,
            'total_planned': len(state['episodes']),
            'attempts_used': attempts_used(state),
            'budget': state.get('budget_episodes'),
            'episodes': [{'episode_id': episode['episode_id'],
                          'status': episode['status'],
                          'attempts': len(episode['attempts'])}
                         for episode in state['episodes']]}


def main():
    signal.signal(signal.SIGTERM, interrupt_handler)
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('plan', 'run', 'resume', 'status', 'analyze'):
        item = sub.add_parser(name)
        item.add_argument('--suite-dir', default=str(DEFAULT_OUTPUT))
        if name in ('run', 'resume'):
            item.add_argument('--max-episodes', type=int)
            item.add_argument('--policy', choices=('stop', 'continue'),
                              default='stop')
    args = parser.parse_args()
    suite_dir = Path(args.suite_dir)
    if args.command == 'plan':
        state = plan_suite(suite_dir)
        print(json.dumps({'planned': len(state['episodes']),
                          'suite': str(suite_dir)}, indent=1))
    elif args.command == 'run':
        execute(suite_dir, args.max_episodes, retry_failed=False, policy=args.policy)
        print(json.dumps(status(suite_dir), indent=1, default=str))
    elif args.command == 'resume':
        execute(suite_dir, args.max_episodes, retry_failed=True, policy=args.policy)
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
