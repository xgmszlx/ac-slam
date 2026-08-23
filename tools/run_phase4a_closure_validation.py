#!/usr/bin/python3
"""Phase 4A Stage C: validate the observation-only /Mapper/loop_closed event 1:1.

Runs seed 21003 with oracle_mode=1 (V1 history-trace), which in Phase 3A produced an
ACCEPTED closure at v15 (scan 284). After the run we compare, per accepted closure:
  Karto internal accepted (diagnostics ACCEPTED record + 'Add one Loop' callback)
  == published loop_closed event (PHASE4A_LOOP_CLOSED in rosout, current_scan id)
Checking: count 1:1, no duplicates, no misses, no wrong attribution, no delay beyond
the loop window. Early-stop after the v15 loop finishes + grace.
"""

import argparse
import json
import re
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

SEED = 21003
TARGET_VERTEX = 15
OUT_ROOT = ROOT / 'results' / 'phase4a' / 'closure_event_validation'


def main():
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    seed_dir = OUT_ROOT / 'seed_{}_v1'.format(SEED)
    if seed_dir.exists():
        raise RuntimeError('refusing to overwrite: {}'.format(seed_dir))
    seed_dir.mkdir(parents=True)
    env = activated_environment()
    suffix = '_Phase4A_closureval_seed{}'.format(SEED)
    tsp_source = AUTHOR_RESULTS / 'tsp_record{}.json'.format(suffix)
    diagnostics_path = seed_dir / 'karto_loop_diagnostics.jsonl'
    run_id = 'seed_{}_closureval'.format(SEED)

    roscore = observer = launch = mapping_result = explore_result = None
    import csv as _csv
    monitor_stream = open(seed_dir / 'monitor.csv', 'w', newline='', buffering=1)
    monitor = _csv.writer(monitor_stream)
    try:
        if command_output(['rosparam', 'list'], env, timeout=5).returncode == 0:
            raise RuntimeError('a ROS master is already running')
        roscore = start_process(['roscore'], env, seed_dir / 'roscore.log')
        wait_for_command(['rosparam', 'list'], env, 60, 'ROS master')
        ros_run_id = write_command_result(
            ['rosparam', 'get', '/run_id'], env, seed_dir / 'ros_run_id.txt', timeout=10
        ).strip()
        observer = start_process(
            ['/usr/bin/python3', str(ROOT / 'tools' / 'phase2_observer.py'),
             '--output-dir', str(seed_dir)],
            env, seed_dir / 'observer.log')
        launch = start_process([
            'roslaunch', 'cpp_solver', 'exploration.launch',
            'suffix:={}'.format(suffix), 'strategy:=MyPlanner',
            'only_use_tsp:=false', 'tsp_seed:={}'.format(SEED),
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
                raise RuntimeError('roslaunch exited before TSP record')
            time.sleep(1)
        shutil.copy2(tsp_source, seed_dir / 'tsp_record.json')

        for service in ('/StartMapping', '/StartExploration'):
            wait_for_command(['rosservice', 'type', service], env, 120, service)

        mapping_result_stream = open(seed_dir / 'get_first_map_result.txt', 'w', buffering=1)
        mapping_result = subprocess.Popen(
            ['rostopic', 'echo', '-n', '1', '/GetFirstMap/result'], env=env,
            cwd=str(ROOT), stdout=mapping_result_stream, stderr=subprocess.STDOUT, text=True)
        time.sleep(1)
        write_command_result(['rosservice', 'call', '/StartMapping', '{}'], env,
                             seed_dir / 'start_mapping_service.txt', timeout=30)
        wait_for_topic_result(mapping_result, seed_dir / 'get_first_map_result.txt',
                              launch, observer, env, 900, monitor, 'mapping')
        mapping_result_stream.close()
        if parse_action_status(seed_dir / 'get_first_map_result.txt') != 3:
            raise RuntimeError('GetFirstMap failed')

        explore_result_stream = open(seed_dir / 'explore_result.txt', 'w', buffering=1)
        explore_result = subprocess.Popen(
            ['rostopic', 'echo', '-n', '1', '/Explore/result'], env=env,
            cwd=str(ROOT), stdout=explore_result_stream, stderr=subprocess.STDOUT, text=True)
        time.sleep(1)
        write_command_result(['rosservice', 'call', '/StartExploration', '{}'], env,
                             seed_dir / 'start_exploration_service.txt', timeout=30)

        # early stop after target loop finishes + grace
        target_seen = False
        deadline = time.monotonic() + 9000
        while time.monotonic() < deadline:
            if launch.poll() is not None or observer.poll() is not None:
                raise RuntimeError('launch/observer exited early')
            if not target_seen:
                text = seed_dir.joinpath('roslaunch.log').read_text(errors='replace')
                if 'PHASE2_LOOP_EXECUTION_FINISHED vertex={}'.format(TARGET_VERTEX) in text:
                    target_seen = True
                    deadline = time.monotonic() + 200
            time.sleep(2)

        stop_process(observer); observer = None
        stop_process(launch); launch = None
        stop_process(roscore); roscore = None
        rosout_source = Path(env['ROS_LOG_DIR']) / ros_run_id / 'rosout.log'
        if rosout_source.is_file():
            shutil.copy2(rosout_source, seed_dir / 'rosout.log')
        copy_author_outputs(suffix, seed_dir)
        write_command_result(['/usr/bin/python3', str(ROOT / 'tools' / 'finalize_phase2_run.py'),
                              '--run-dir', str(seed_dir)], env, seed_dir / 'finalize.log', timeout=120)

        # ---- validation ----
        diag_acc, cb_times, evts = [], [], []
        for line in (seed_dir / 'karto_loop_diagnostics.jsonl').read_text(errors='replace').splitlines():
            r = json.loads(line)
            if r.get('accepted'):
                diag_acc.append(r)
        rosout = (seed_dir / 'rosout.log').read_text(errors='replace')
        for line in rosout.splitlines():
            if 'Add one Loop' in line:
                m = re.match(r'^([0-9.]+) WARN', line)
                if m:
                    cb_times.append(float(m.group(1)))
            m = re.search(r'PHASE4A_LOOP_CLOSED seq=(\d+) current_scan=(\d+) chain_start=(\d+) chain_end=(\d+)', line)
            if m:
                evts.append((int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))))

        diag_scans = [(r['scan_id'], r['chain_size']) for r in diag_acc]
        result = {
            'diagnostics_accepted_records': len(diag_acc),
            'accepted_callback_times': cb_times,
            'loop_closed_events': evts,
            'one_to_one': len(diag_acc) == len(evts) == len(cb_times),
            'attribution_ok': all(e[1] == d[0] for e, d in zip(evts, diag_scans)) if evts else None,
            'no_duplicates': len({e[0] for e in evts}) == len(evts),
            'seq_contiguous': evts == sorted(evts) and (not evts or evts[-1][0] == len(evts)),
        }
        (seed_dir / 'closure_event_validation.json').write_text(
            json.dumps(result, indent=2, sort_keys=True) + '\n')
        print(json.dumps(result, indent=2, sort_keys=True))
    finally:
        for process in (mapping_result, explore_result):
            if process is not None and process.poll() is None:
                process.terminate()
        stop_process(observer); stop_process(launch); stop_process(roscore)
        monitor_stream.close()


if __name__ == '__main__':
    main()
