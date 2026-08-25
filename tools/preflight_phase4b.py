#!/usr/bin/python3
"""Fail-closed Phase 4B preflight and protocol-manifest generator."""

import argparse
import datetime
import hashlib
import json
import os
import platform
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
    start_process,
    stop_process,
    wait_for_command,
)


OUTPUT_ROOT = ROOT / 'results' / 'phase4b' / 'map3'
NAVIGATION = ROOT / 'dependencies' / 'navigation_2d'
FIELDS = (
    'solver', 'seed', 'initial_tsp_path', 'full_tsp_path',
    'predicted_tsp_length', 'predicted_full_tsp_length',
)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def git_output(repo, *args):
    return subprocess.check_output(
        ['git', '-C', str(repo)] + list(args), text=True
    ).strip()


def run_logged(command, env, path, timeout):
    completed = subprocess.run(
        command, cwd=str(ROOT), env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
    )
    path.write_text(completed.stdout, encoding='utf-8')
    if completed.returncode != 0:
        raise RuntimeError('command failed: {} (see {})'.format(command, path))
    return completed.stdout


def check_no_residual_ros(env):
    master = command_output(['rosparam', 'list'], env, timeout=5)
    if master.returncode == 0:
        raise RuntimeError('a ROS master is already running')
    listing = subprocess.check_output(['ps', '-eo', 'pid=,cmd='], text=True)
    needles = ('roscore', 'rosmaster', 'roslaunch', 'stageros')
    residual = [
        line.strip() for line in listing.splitlines()
        if any(needle in line for needle in needles)
        and 'preflight_phase4b.py' not in line
    ]
    if residual:
        raise RuntimeError('residual ROS/Stage processes: {}'.format(residual))


def launch_probe(mode, seed, attempt_dir, env, token):
    probe_dir = attempt_dir / 'mode_{}'.format(mode)
    probe_dir.mkdir()
    suffix = '_Phase4B_preflight_{}_mode{}'.format(token, mode)
    tsp_source = AUTHOR_RESULTS / 'tsp_record{}.json'.format(suffix)
    if tsp_source.exists():
        raise RuntimeError('pre-existing preflight author output: {}'.format(tsp_source))
    roscore = launch = None
    try:
        check_no_residual_ros(env)
        roscore = start_process(['roscore'], env, probe_dir / 'roscore.log')
        wait_for_command(['rosparam', 'list'], env, 60, 'ROS master')
        command = [
            'roslaunch', 'cpp_solver', 'exploration.launch',
            'suffix:={}'.format(suffix), 'strategy:=MyPlanner',
            'only_use_tsp:=false', 'tsp_solver:=concorde',
            'tsp_seed:={}'.format(seed), 'map_name:=map3/map3',
            'robot_position:=-28.0 -28.0 0', 'map_width:=74.0',
            'need_noise:=false', 'variance:=0',
            'enable_loop_diagnostics:=false',
            'loop_diagnostics_path:=', 'loop_diagnostics_run_id:=',
            'oracle_mode:={}'.format(mode),
            'oracle_before:=8', 'oracle_after:=8', 'oracle_densify_m:=0.5',
            'oracle_span_gate:=4.0', 'oracle_repair_max_len:=12.0',
            'oracle_repair_max_wp:=24', 'oracle_repair_densify:=0.5',
            'oracle_dir_lambda:=1.0',
        ]
        (probe_dir / 'full_command.txt').write_text(
            subprocess.list2cmdline(command) + '\n', encoding='utf-8'
        )
        launch = start_process(command, env, probe_dir / 'roslaunch.log')
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline and not tsp_source.is_file():
            if launch.poll() is not None:
                raise RuntimeError('mode {} roslaunch exited before TSP'.format(mode))
            time.sleep(1)
        if not tsp_source.is_file():
            raise RuntimeError('mode {} TSP timeout'.format(mode))
        shutil.copy2(tsp_source, probe_dir / 'tsp_record.json')
        for service in ('/StartMapping', '/StartExploration', '/prior_graph_service',
                        '/path_plan_service', '/reliable_loop_service'):
            wait_for_command(['rosservice', 'type', service], env, 120, service)
        wait_for_command(['rostopic', 'type', '/Mapper/loop_closed'], env, 120,
                         '/Mapper/loop_closed topic')
        nodes = wait_for_command(['rosnode', 'list'], env, 60, 'core nodes')
        missing = sorted(CORE_NODES - set(nodes.splitlines()))
        if missing:
            raise RuntimeError('mode {} missing core nodes: {}'.format(mode, missing))
        diagnostics = wait_for_command(
            ['rosparam', 'get', '/Mapper/enable_loop_diagnostics'], env, 30,
            'diagnostics parameter',
        ).strip().lower()
        actual_mode = int(wait_for_command(
            ['rosparam', 'get', '/path_planner/oracle_mode'], env, 30,
            'oracle_mode parameter',
        ).strip())
        if diagnostics not in ('false', '0'):
            raise RuntimeError('diagnostics unexpectedly enabled: {}'.format(diagnostics))
        if actual_mode != mode:
            raise RuntimeError('oracle_mode parse mismatch {} != {}'.format(actual_mode, mode))
        record = json.loads((probe_dir / 'tsp_record.json').read_text())
        return {
            'mode': mode,
            'diagnostics': False,
            'loop_closed_topic_type': 'cpp_solver/LoopClosureEvent',
            'core_nodes': sorted(CORE_NODES),
            'tsp_sha256': sha256(probe_dir / 'tsp_record.json'),
            'tsp': {key: record.get(key) for key in FIELDS},
        }
    finally:
        stop_process(launch)
        stop_process(roscore)
        time.sleep(2)


def source_manifest():
    relative_paths = [
        'baseline/Graph-Based_SLAM-Aware_Exploration/launch/exploration.launch',
        'baseline/Graph-Based_SLAM-Aware_Exploration/param/mapper.yaml',
        'baseline/Graph-Based_SLAM-Aware_Exploration/param/navigator.yaml',
        'baseline/Graph-Based_SLAM-Aware_Exploration/param/operator.yaml',
        'baseline/Graph-Based_SLAM-Aware_Exploration/param/costmap.yaml',
        'baseline/Graph-Based_SLAM-Aware_Exploration/param/ros.yaml',
        'baseline/Graph-Based_SLAM-Aware_Exploration/scripts/path_planner.py',
        'baseline/Graph-Based_SLAM-Aware_Exploration/src/MyPlanner.cpp',
        'baseline/Graph-Based_SLAM-Aware_Exploration/src/MyPlanner.h',
        'baseline/Graph-Based_SLAM-Aware_Exploration/srv/ReliableLoop.srv',
        'baseline/Graph-Based_SLAM-Aware_Exploration/msg/LoopClosureEvent.msg',
        'dependencies/navigation_2d/nav2d_karto/OpenKarto/source/OpenMapper.cpp',
        'dependencies/navigation_2d/nav2d_karto/OpenKarto/source/OpenKarto/OpenMapper.h',
        'dependencies/navigation_2d/nav2d_karto/src/MultiMapper.cpp',
        'dependencies/navigation_2d/nav2d_karto/include/nav2d_karto/MultiMapper.h',
        'baseline/Graph-Based_SLAM-Aware_Exploration/world/map3/map3.world',
        'baseline/Graph-Based_SLAM-Aware_Exploration/world/map3/map3.yaml',
        'baseline/Graph-Based_SLAM-Aware_Exploration/world/map3/map3.png',
        'baseline/Graph-Based_SLAM-Aware_Exploration/world/map3/map3.xml',
        'tools/phase2_observer.py',
        'tools/evaluate_slam_run.py',
        'tools/evaluate_mapping.py',
        'tools/finalize_phase4b_run.py',
        'tools/aggregate_phase4b.py',
        'tools/run_phase4b_suite.py',
        'tools/preflight_phase4b.py',
        'tools/test_phase4a_selective.py',
        'tools/test_phase4b_mapping.py',
        'docs/research_log/26_phase4b_protocol_freeze.md',
        'docs/research_log/27_mapping_evaluation_protocol.md',
    ]
    return {
        path: sha256(ROOT / path) for path in relative_paths if (ROOT / path).is_file()
    }


def main():
    parser = argparse.ArgumentParser()
    parser.parse_args()
    env = activated_environment()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    token = datetime.datetime.now().strftime('%Y%m%dT%H%M%S')
    attempt_dir = OUTPUT_ROOT / 'preflight' / ('attempt_' + token)
    attempt_dir.mkdir(parents=True)
    summary = {'status': 'RUNNING', 'attempt': token, 'checks': {}}
    summary_path = attempt_dir / 'preflight_summary.json'
    summary_path.write_text(json.dumps(summary, indent=2) + '\n')
    try:
        check_no_residual_ros(env)
        summary['checks']['no_residual_ros'] = 'PASS'
        tracked = git_output(ROOT, 'status', '--porcelain', '--untracked-files=no')
        if tracked:
            raise RuntimeError('tracked worktree changes exist:\n{}'.format(tracked))
        summary['checks']['tracked_worktree_clean'] = 'PASS'
        free_bytes = shutil.disk_usage(str(ROOT)).free
        if free_bytes < 4 * 1024 ** 3:
            raise RuntimeError('less than 4 GiB free disk space')
        summary['checks']['free_disk_bytes'] = free_bytes

        run_logged(
            ['bash', '-lc', 'source catkin_ws/activate.sh && cd catkin_ws && catkin_make'],
            env, attempt_dir / 'catkin_build.log', timeout=1800,
        )
        summary['checks']['catkin_build'] = 'PASS'
        run_logged(
            ['/usr/bin/python3', 'tools/test_phase4a_selective.py'],
            env, attempt_dir / 'phase4a_unit_tests.log', timeout=300,
        )
        run_logged(
            ['/usr/bin/python3', '-m', 'unittest', '-v', 'tools/test_phase4b_mapping.py'],
            env, attempt_dir / 'mapping_unit_tests.log', timeout=300,
        )
        summary['checks']['unit_tests'] = 'PASS'

        for mode in (0, 1, 2):
            run_logged([
                'roslaunch', '--dump-params', 'cpp_solver', 'exploration.launch',
                'oracle_mode:={}'.format(mode), 'enable_loop_diagnostics:=false',
                'oracle_span_gate:=4.0', 'oracle_repair_max_len:=12.0',
                'oracle_repair_max_wp:=24', 'oracle_repair_densify:=0.5',
                'oracle_dir_lambda:=1.0',
            ], env, attempt_dir / 'launch_params_mode_{}.yaml'.format(mode), timeout=120)
        summary['checks']['launch_parse_modes_0_1_2'] = 'PASS'

        probes = [launch_probe(mode, 21001, attempt_dir, env, token) for mode in (0, 1, 2)]
        reference = probes[0]['tsp']
        if any(probe['tsp'] != reference for probe in probes[1:]):
            raise RuntimeError('preflight TSP differs across oracle modes')
        summary['checks']['startup_probe'] = probes
        summary['checks']['tsp_seed_control'] = 'PASS'
        summary['checks']['loop_closed_topic'] = 'PASS'
        summary['checks']['diagnostics_off'] = 'PASS'

        planner_sources = '\n'.join(
            (ROOT / path).read_text(errors='replace') for path in (
                'baseline/Graph-Based_SLAM-Aware_Exploration/scripts/path_planner.py',
                'baseline/Graph-Based_SLAM-Aware_Exploration/src/MyPlanner.cpp',
            )
        )
        forbidden = ('base_pose_ground_truth', 'trajectory_gt', 'ground_truth_samples')
        if any(token in planner_sources for token in forbidden):
            raise RuntimeError('ground-truth reference found in online planner sources')
        evaluator_source = (ROOT / 'tools/evaluate_mapping.py').read_text()
        if 'import rospy' in evaluator_source or 'rosservice' in evaluator_source:
            raise RuntimeError('offline mapping evaluator contains ROS runtime access')
        summary['checks']['gt_not_online_control'] = 'PASS'
        summary['checks']['offline_mapping_evaluator'] = 'PASS'
        check_no_residual_ros(env)
        summary['checks']['post_probe_no_residual_ros'] = 'PASS'

        manifest = {
            'phase': '4B',
            'protocol_frozen_date': '2026-08-25',
            'formal_seeds': [21001, 21002, 21003, 21004, 21005],
            'counterbalanced_order': {
                '21001': ['A', 'B', 'C'], '21002': ['B', 'C', 'A'],
                '21003': ['C', 'A', 'B'], '21004': ['A', 'C', 'B'],
                '21005': ['B', 'A', 'C'],
            },
            'conditions': {
                'A': {'name': 'Original', 'oracle_mode': 0},
                'B': {'name': 'Always-Trace', 'oracle_mode': 1},
                'C': {'name': 'Selective', 'oracle_mode': 2},
            },
            'only_scientific_variable': 'oracle_mode',
            'diagnostics_enabled': False,
            'commits': {
                'root': git_output(ROOT, 'rev-parse', 'HEAD'),
                'baseline': git_output(BASELINE, 'rev-parse', 'HEAD'),
                'navigation_2d': git_output(NAVIGATION, 'rev-parse', 'HEAD'),
            },
            'source_sha256': source_manifest(),
            'runtime': {
                'platform': platform.platform(),
                'os_release': Path('/etc/os-release').read_text(errors='replace'),
                'ros_distribution': run_logged(
                    ['rosversion', '-d'], env, attempt_dir / 'ros_version.txt', timeout=30
                ).strip(),
                'python': run_logged(
                    ['/usr/bin/python3', '--version'], env,
                    attempt_dir / 'python_version.txt', timeout=30
                ).strip(),
                'evo': '1.31.1 (workspace-pinned)',
            },
            'mapping_protocol': {
                'registration': 'identity map frame',
                'occupied_thresh': 0.65,
                'free_thresh': 0.196,
                'gt_unknown': 'excluded',
                'boundary_tolerance_m': 0.20,
            },
            'trajectory_protocol': {
                'timestamp_max_diff_s': 0.05,
                'alignment': 'none',
                'projection': 'xy',
            },
            'preflight_attempt': str(attempt_dir.relative_to(OUTPUT_ROOT)),
        }
        (OUTPUT_ROOT / 'protocol_manifest.json').write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8'
        )
        summary['status'] = 'PASS'
    except Exception as exc:
        summary['status'] = 'FAIL'
        summary['reason'] = '{}: {}'.format(type(exc).__name__, exc)
        raise
    finally:
        summary['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
        print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
