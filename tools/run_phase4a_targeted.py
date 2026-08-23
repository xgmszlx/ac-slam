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
import sys
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

# Set by --no-diagnostics on the CLI. Phase 4A trial 9 proved that the
# per-loop-search diagnostic file I/O perturbs Karto closure acceptance
# (no-diagnostics positive control: accepted closure; every diagnostics-enabled
# trial: zero). Targeted cases must therefore run diagnostics-OFF.
NO_DIAGNOSTICS = False


def validate_callback_vs_event(seed_dir):
    """Diagnostics-free 1:1: 'Add one Loop closure.' callbacks vs PHASE4A_LOOP_CLOSED."""
    rosout = (seed_dir / 'rosout.log').read_text(errors='replace')
    cb_times, evts = [], []
    for line in rosout.splitlines():
        if 'Add one Loop closure.' in line:
            m = re.match(r'^([0-9.]+) WARN', line)
            if m:
                cb_times.append(float(m.group(1)))
        m = re.search(r'PHASE4A_LOOP_CLOSED seq=(\d+) current_scan=(\d+) '
                      r'chain_start=(\d+) chain_end=(\d+)', line)
        if m:
            evts.append((int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))))
    n = len(evts)
    delays = None
    if n and len(cb_times) == n:
        delays = [et - ct for ct, (et, *_) in zip(cb_times, evts)]
    result = {
        'mode': 'diagnostics_off',
        'accepted_callbacks_count': len(cb_times),
        'accepted_callback_times': cb_times,
        'loop_closed_events': evts,
        'inconclusive_no_closure': n == 0,
        'one_to_one': (n > 0) and len(cb_times) == n,
        'attribution_ok': all(0 <= e[1] and e[2] <= e[3] for e in evts) if n else None,
        'no_duplicates': len({e[0] for e in evts}) == n,
        'seq_contiguous': evts == sorted(evts) and (not evts or evts[-1][0] == n),
        'event_after_callback_ok': (delays is not None and all(d >= 0 for d in delays)),
        'max_callback_to_event_delay_s': max(delays) if delays else None,
    }
    (seed_dir / 'closure_event_validation.json').write_text(
        json.dumps(result, indent=2, sort_keys=True) + '\n')
    return result


def closure_validate(seed_dir, diagnostics_path, ros_run_id, env):
    """Phase 4A Stage C: 1:1 validation of the /Mapper/loop_closed event.

    Compares, per accepted closure:
      Karto internal accepted  (diagnostics ACCEPTED record + 'Add one Loop' callback)
      == published loop_closed event (PHASE4A_LOOP_CLOSED in rosout, current_scan id)
    Checks: count 1:1, no duplicates, no wrong attribution, seq contiguous.
    Writes closure_event_validation.json into seed_dir.
    """
    diag_acc = []
    for line in diagnostics_path.read_text(errors='replace').splitlines():
        r = json.loads(line)
        if r.get('accepted'):
            diag_acc.append(r)
    rosout_path = seed_dir / 'rosout.log'
    cb_times, evts = [], []
    if rosout_path.is_file():
        rosout = rosout_path.read_text(errors='replace')
        for line in rosout.splitlines():
            if 'Add one Loop' in line:
                m = re.match(r'^([0-9.]+) WARN', line)
                if m:
                    cb_times.append(float(m.group(1)))
            m = re.search(r'PHASE4A_LOOP_CLOSED seq=(\d+) current_scan=(\d+) '
                          r'chain_start=(\d+) chain_end=(\d+)', line)
            if m:
                evts.append((int(m.group(1)), int(m.group(2)),
                             int(m.group(3)), int(m.group(4))))
    diag_scans = [(r['scan_id'], r['chain_size']) for r in diag_acc]
    n = len(evts)
    result = {
        'diagnostics_accepted_records': len(diag_acc),
        'accepted_callback_times': cb_times,
        'loop_closed_events': evts,
        'inconclusive_no_closure': n == 0,
        'one_to_one': (n > 0) and len(diag_acc) == len(evts) == len(cb_times),
        'attribution_ok': all(e[1] == d[0] for e, d in zip(evts, diag_scans)) if n else None,
        'no_duplicates': len({e[0] for e in evts}) == n,
        'seq_contiguous': evts == sorted(evts) and (not evts or evts[-1][0] == n),
    }
    (seed_dir / 'closure_event_validation.json').write_text(
        json.dumps(result, indent=2, sort_keys=True) + '\n')
    return result


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
        launch_args = [
            'roslaunch', 'cpp_solver', 'exploration.launch',
            'suffix:={}'.format(suffix), 'strategy:=MyPlanner',
            'only_use_tsp:=false', 'tsp_seed:={}'.format(seed),
            'map_name:=map3/map3', 'robot_position:=-28.0 -28.0 0',
            'map_width:=74.0', 'need_noise:=false', 'variance:=0',
        ]
        if not NO_DIAGNOSTICS:
            launch_args += [
                'enable_loop_diagnostics:=true',
                'loop_diagnostics_path:={}'.format(diagnostics_path),
                'loop_diagnostics_run_id:={}'.format(run_id),
            ]
        launch = start_process(launch_args + [
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
        if diagnostics_path.is_file():
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
        if NO_DIAGNOSTICS:
            cv = validate_callback_vs_event(seed_dir)
        else:
            cv = closure_validate(seed_dir, diagnostics_path, ros_run_id, env)
        print(json.dumps(summary, indent=2, sort_keys=True))
        print('CLOSURE_VALIDATION: {}'.format(json.dumps(cv)))
    finally:
        for process in (mapping_result, explore_result):
            if process is not None and process.poll() is None:
                process.terminate()
        stop_process(observer); stop_process(launch); stop_process(roscore)
        monitor_stream.close()


def main():
    global NO_DIAGNOSTICS
    only = None
    if '--case' in sys.argv:
        only = int(sys.argv[sys.argv.index('--case') + 1])
    if '--no-diagnostics' in sys.argv:
        NO_DIAGNOSTICS = True
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    env = activated_environment()
    for index, (seed, label, target) in enumerate(CASES, start=1):
        if only is not None and index != only:
            continue
        print('\n===== CASE {}: {} (seed {}, target v{}) ====='.format(index, label, seed, target))
        run_case(seed, label, target, env, index)


if __name__ == '__main__':
    main()
