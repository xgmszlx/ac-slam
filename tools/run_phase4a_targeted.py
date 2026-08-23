#!/usr/bin/python3
"""Phase 4A Stage D: three targeted validation cases (oracle_mode=2, selective).

Case 1 (D1 rescue):     seed 21003, target v15  (short-span D1, span ~3.92 < 4.0)
Case 2 (C3 opportunity):seed 21005, target v26  (short-span C3, span ~3.63 < 4.0)
Case 3 (S reference):   seed 21001, target v26  (span ~4.81 >= 4.0 -> NO_REPAIR)

Each run uses oracle_mode=2 + enable_loop_diagnostics, early-stops after the target
loop + grace, and records the gate decision, repair path, early-stop status, and the
evaluation-only Karto evidence. TSP must stay byte-identical to Phase 2C.
"""

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from run_phase2c_pairs import (
    AUTHOR_RESULTS,
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

OUT_ROOT = ROOT / 'results' / 'phase4a' / 'targeted_cases'

CASES = [
    (21003, 'D1-rescue-v15', 15),
    (21005, 'C3-opp-v26', 26),
    (21001, 'S-ref-v26', 26),
]


def run_case(seed, label, target_vertex, env, index):
    seed_dir = OUT_ROOT / '{:02d}_{}_{}'.format(index, label, seed)
    if seed_dir.exists():
        raise RuntimeError('refusing to overwrite: {}'.format(seed_dir))
    seed_dir.mkdir(parents=True)
    suffix = '_Phase4A_{}_seed{}'.format(label, seed)
    tsp_source = AUTHOR_RESULTS / 'tsp_record{}.json'.format(suffix)
    diagnostics_path = seed_dir / 'karto_loop_diagnostics.jsonl'
    run_id = 'seed_{}_{}'.format(seed, label)
    import csv as _csv
    monitor_stream = open(seed_dir / 'monitor.csv', 'w', newline='', buffering=1)
    monitor = _csv.writer(monitor_stream)
    roscore = observer = launch = mapping_result = explore_result = None
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
             '--output-dir', str(seed_dir)], env, seed_dir / 'observer.log')
        launch = start_process([
            'roslaunch', 'cpp_solver', 'exploration.launch',
            'suffix:={}'.format(suffix), 'strategy:=MyPlanner',
            'only_use_tsp:=false', 'tsp_seed:={}'.format(seed),
            'map_name:=map3/map3', 'robot_position:=-28.0 -28.0 0',
            'map_width:=74.0', 'need_noise:=false', 'variance:=0',
            'enable_loop_diagnostics:=true',
            'loop_diagnostics_path:={}'.format(diagnostics_path),
            'loop_diagnostics_run_id:={}'.format(run_id),
            'oracle_mode:=2',
            'oracle_span_gate:=4.0', 'oracle_repair_max_len:=12.0',
            'oracle_repair_max_wp:=24', 'oracle_repair_densify:=0.5',
            'oracle_dir_lambda:=1.0',
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
        target_seen = False
        deadline = time.monotonic() + 9000
        while time.monotonic() < deadline:
            if launch.poll() is not None or observer.poll() is not None:
                raise RuntimeError('launch/observer exited early')
            if not target_seen:
                text = seed_dir.joinpath('roslaunch.log').read_text(errors='replace')
                if 'PHASE2_LOOP_EXECUTION_FINISHED vertex={}'.format(target_vertex) in text:
                    target_seen = True
                    deadline = time.monotonic() + 200
            time.sleep(2)
        if not target_seen:
            raise RuntimeError('target loop never finished')
        stop_process(observer); observer = None
        stop_process(launch); launch = None
        stop_process(roscore); roscore = None
        rosout_source = Path(env['ROS_LOG_DIR']) / ros_run_id / 'rosout.log'
        if rosout_source.is_file():
            shutil.copy2(rosout_source, seed_dir / 'rosout.log')
        copy_author_outputs(suffix, seed_dir)
        write_command_result(['/usr/bin/python3', str(ROOT / 'tools' / 'finalize_phase2_run.py'),
                              '--run-dir', str(seed_dir)], env, seed_dir / 'finalize.log', timeout=120)
        # ---- post-processing summary ----
        rl = (seed_dir / 'roslaunch.log').read_text(errors='replace')
        decisions = re.findall(r'PHASE4A_SELECTIVE_DECISION vertex=(\d+) span_m=([0-9.]+|None) '
                               r'gate=([0-9.]+) decision=(\w+)', rl)
        repairs = re.findall(r'PHASE4A_SELECTIVE_REPAIR vertex=(\d+) span_m=([0-9.]+) '
                             r'planned_len_m=([0-9.]+) waypoints=(\d+)', rl)
        early = re.findall(r'PHASE4A_EARLY_STOP vertex=(\d+) at_waypoint=(\d+) of (\d+)', rl)
        closure_attr = re.findall(r'PHASE4A_CLOSURE_ATTRIBUTED seq=(\d+) scan=(\d+) '
                                  r'chain=\[(\d+),(\d+)\]', rl)
        closure_unattr = len(re.findall(r'PHASE4A_CLOSURE_UNATTRIBUTED', rl))
        diag_acc = []
        for line in diagnostics_path.read_text(errors='replace').splitlines():
            r = json.loads(line)
            if r.get('accepted'):
                diag_acc.append(r)
        summary = {
            'seed': seed, 'case': label, 'target_vertex': target_vertex,
            'gate_decisions': decisions, 'repairs': repairs,
            'early_stop': early, 'closure_attributed': closure_attr,
            'closure_unattributed': closure_unattr,
            'accepted_diag_records': [(r['scan_id'], round(r['coarse_response'] or 0, 3),
                                       round(r['fine_response'] or 0, 3)) for r in diag_acc],
            'accepted_callbacks': len(re.findall(r'Add one Loop', rl)),
        }
        (seed_dir / 'targeted_summary.json').write_text(
            json.dumps(summary, indent=2, sort_keys=True) + '\n')
        print(json.dumps(summary, indent=2, sort_keys=True))
    finally:
        for process in (mapping_result, explore_result):
            if process is not None and process.poll() is None:
                process.terminate()
        stop_process(observer); stop_process(launch); stop_process(roscore)
        monitor_stream.close()


def main():
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    env = activated_environment()
    for index, (seed, label, target) in enumerate(CASES, start=1):
        print('\n===== CASE {}: {} (seed {}, target v{}) ====='.format(index, label, seed, target))
        run_case(seed, label, target, env, index)


if __name__ == '__main__':
    main()
