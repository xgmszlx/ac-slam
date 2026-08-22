#!/usr/bin/python3
"""Phase 3A minimal causal/oracle experiment runner (V1 history-trace revisit).

Each case re-runs one Phase 2C seed with the revisit-realization oracle enabled
(oracle_mode=1, default-off switch) while keeping loop selection, planning, Karto and
all thresholds identical to Phase 2C (V0 baseline). The run is stopped shortly after
the target loop(s) finish (diagnostics are flushed per record, so no loop evidence is
lost), then finalized like Phase 2C. A short isolated-Stage timing probe is run first
and wall/sim is recorded per run.

V1 = history-trace revisit: the reliable_loop_service returns a longer contiguous
window of SLAM-estimated historical poses spanning the loop vertex, densified for
position-only navigation. GT is never used by the service (evaluation only).
"""

import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path

from run_phase2c_pairs import (
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
    wait_for_command,
    wait_for_topic_result,
    write_command_result,
)

# Test cases: seed -> (label, [target vertices in order], stop after last target).
# The Phase 2C V0 baseline for each case is recorded in 16_phase3a_causal_validation.md.
CASES = [
    # (seed, label, target_loop_vertex, stop_after_sim_grace_s)
    (21001, 'S-reference-v26', 26, 40.0),    # V0 success (S) must be preserved
    (21003, 'D1-v15', 15, 40.0),             # V0 D1 (best coarse 0.40)
    (21004, 'C3-v26+D1-v22', 22, 40.0),      # V0 C3 (v26) + D1 near-threshold (v22, 0.57)
    (21005, 'C3-v26+D1-v22', 22, 40.0),      # V0 C3 (v26) + D1 very-low (v22, 0.31)
]


def probe_stage(env, probe_dir):
    """Short isolated Stage timing probe: count /clock messages over 20 s wall.
    Stage publishes /clock at the sim rate, so msgs/20 s is the sim rate in Hz;
    wall/sim = 20.0 * (1.0 / (msgs / 20.0)) = 400.0 / msgs (for a 1 Hz clock)."""
    probe_dir.mkdir(parents=True, exist_ok=True)
    roscore = stage = None
    try:
        if command_output(['rosparam', 'list'], env, timeout=5).returncode == 0:
            raise RuntimeError('a ROS master is already running; refusing probe')
        roscore = start_process(['roscore'], env, probe_dir / 'roscore.log')
        wait_for_command(['rosparam', 'list'], env, 60, 'ROS master')
        stage = start_process([
            'rosrun', 'stage_ros', 'stageros',
            str(ROOT / 'baseline' / 'Graph-Based_SLAM-Aware_Exploration' / 'world' /
                'map3' / 'map3.world'),
        ], env, probe_dir / 'stage.log')
        time.sleep(8)
        out = command_output([
            '/usr/bin/python3', '-c',
            "import time, rospy;"
            "from rosgraph_msgs.msg import Clock;"
            "n=[0];"
            "def cb(m): n[0]+=1\n"
            "rospy.init_node('probe', anonymous=True);"
            "rospy.Subscriber('/clock', Clock, cb);"
            "time.sleep(20);"
            "print('CLOCK_MSGS', n[0])",
        ], env, timeout=40)
        return out.stdout.strip()
    finally:
        stop_process(stage)
        stop_process(roscore)


def run_one(seed, label, target_vertex, stop_grace_sim, seed_dir, env, explore_timeout):
    if seed_dir.exists():
        raise RuntimeError('refusing to overwrite existing run directory: {}'.format(seed_dir))
    seed_dir.mkdir(parents=True)
    suffix = '_Phase3A_{}_seed{}'.format(label, seed)
    tsp_source = AUTHOR_RESULTS / 'tsp_record{}.json'.format(suffix)
    if tsp_source.exists():
        raise RuntimeError('refusing to reuse pre-existing author output: {}'.format(tsp_source))
    diagnostics_path = seed_dir / 'karto_loop_diagnostics.jsonl'
    run_id = 'seed_{}_{}'.format(seed, label)

    roscore = observer = launch = mapping_result = explore_result = None
    run_state = {'status': 'RUNNING', 'started_wall_time_utc': now_utc()}
    (seed_dir / 'run_state.json').write_text(json.dumps(run_state, indent=2) + '\n')
    import csv as _csv
    monitor_stream = open(seed_dir / 'monitor.csv', 'w', newline='', buffering=1)
    monitor = _csv.writer(monitor_stream)
    monitor.writerow(['wall_time_utc', 'stage', 'elapsed_wall_s', 'launch_alive',
                      'observer_alive', 'rss_kb', 'missing_core_nodes'])
    max_rss = 0
    keyscan_first_last = None
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
            'oracle_mode:=1', 'oracle_before:=8', 'oracle_after:=8', 'oracle_densify_m:=0.5',
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

        for service in ('/StartMapping', '/StartExploration', '/prior_graph_service',
                        '/path_plan_service', '/reliable_loop_service'):
            wait_for_command(['rosservice', 'type', service], env, 120, service)

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
        max_rss = wait_for_topic_result(
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

        # Monitor for the target loop finish, then stop after a sim grace period.
        # Stop exactly when the target loop execution finishes (plus grace) to save
        # wall time; diagnostics are flushed per record so no loop evidence is lost.
        target_seen = None
        stop_deadline = time.monotonic() + explore_timeout
        while time.monotonic() < stop_deadline:
            if launch.poll() is not None or observer.poll() is not None:
                raise RuntimeError('launch/observer exited while waiting for target loop')
            if target_seen is None:
                text = ''
                try:
                    text = seed_dir.joinpath('roslaunch.log').read_text(errors='replace')
                except OSError:
                    pass
                for line in text.splitlines():
                    if ('PHASE2_LOOP_EXECUTION_FINISHED vertex={}'.format(target_vertex)
                            in line):
                        target_seen = line.split()[0]
                        break
                if target_seen is not None:
                    (seed_dir / 'early_stop_target.txt').write_text(
                        'target_vertex={} finished_sim={}\n'.format(target_vertex, target_seen))
                    # grace: enough wall time for the loop's tail processing
                    grace_wall_s = stop_grace_sim * 5.0 + 180.0
                    stop_deadline = time.monotonic() + grace_wall_s
            else:
                # wait out the grace period (loop just idles until deadline)
                time.sleep(5)
                continue
            time.sleep(2)
        if target_seen is None:
            raise RuntimeError(
                'target loop vertex={} never finished within timeout'.format(target_vertex))

        # capture keyscan span for wall/sim ratio
        if diagnostics_path.is_file():
            first_t = last_t = None
            import re as _re
            for line in diagnostics_path.read_text(errors='replace').splitlines():
                m = _re.search(r'"wall_time_ms":(\d+)', line)
                if m:
                    t = int(m.group(1))
                    first_t = t if first_t is None else first_t
                    last_t = t
            if first_t is not None:
                keyscan_first_last = (first_t, last_t)
            (seed_dir / 'keyscan_wall_span_ms.txt').write_text(
                '{}\n{}\n'.format(first_t, last_t) if first_t is not None else 'none\n')

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
            'phase': '3A-oracle', 'variant': 'V1-history-trace', 'oracle_mode': 1,
            'oracle_before': 8, 'oracle_after': 8, 'oracle_densify_m': 0.5,
            'method': 'Graph-Based SLAM-aware', 'map': 'map3',
            'seed': seed, 'case_label': label, 'target_loop_vertex': target_vertex,
            'target_loop_finished_sim': target_seen,
            'early_stopped': True, 'stop_grace_sim': stop_grace_sim,
            'start_pose_xyyaw': [-28.0, -28.0, 0.0],
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
                'oracle_mode': 1, 'oracle_before': 8, 'oracle_after': 8,
                'oracle_densify_m': 0.5,
                'suffix': suffix,
            },
            'python': '/usr/bin/python3 3.8.10', 'observer': 'tools/phase2_observer.py (passive)',
            'stdout_stderr': 'roslaunch.log',
            'keyscan_wall_span_ms': keyscan_first_last,
        }
        (seed_dir / 'manifest.json').write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + '\n'
        )
        run_state.update({'status': 'SUCCEEDED', 'finished_wall_time_utc': now_utc()})
        (seed_dir / 'run_state.json').write_text(json.dumps(run_state, indent=2) + '\n')
        return {'seed': seed, 'success': True}
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
        try:
            monitor_stream.close()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start-case', type=int, default=0)
    parser.add_argument('--end-case', type=int, default=len(CASES) - 1)
    parser.add_argument('--explore-timeout', type=int, default=9000)
    parser.add_argument(
        '--output-root', type=Path,
        default=ROOT / 'results' / 'phase3a' / 'oracle',
    )
    args = parser.parse_args()
    env = activated_environment()
    args.output_root.mkdir(parents=True, exist_ok=True)

    # Timing probe before the batch (spec: record wall/sim; do not silently ignore >1.5).
    probe_out = probe_stage(env, args.output_root / 'timing_probe')
    probe_state = {'probe_clock_msgs': probe_out}
    (args.output_root / 'timing_probe' / 'probe_result.txt').write_text(
        'CLOCK_MSGS {}\n'.format(probe_out) if probe_out else 'probe failed\n')
    probe_state['status'] = 'recorded'
    (args.output_root / 'timing_probe.json').write_text(
        json.dumps(probe_state, indent=2) + '\n')

    suite_state_path = args.output_root / 'suite_state.json'
    state = {'status': 'RUNNING', 'started_wall_time_utc': now_utc(),
             'cases': [c[1] for c in CASES], 'completed_runs': []}
    suite_state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + '\n')
    try:
        for idx in range(args.start_case, args.end_case + 1):
            seed, label, target_vertex, grace = CASES[idx]
            seed_dir = args.output_root / 'seed_{}_{}'.format(seed, label)
            outcome = run_one(seed, label, target_vertex, grace, seed_dir, env,
                              args.explore_timeout)
            state['completed_runs'].append({
                'case': label, 'seed': seed, 'finished_wall_time_utc': now_utc(),
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
