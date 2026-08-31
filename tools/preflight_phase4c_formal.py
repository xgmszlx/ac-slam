#!/usr/bin/python3
"""Fail-closed startup-only preflight for the frozen Phase 4C formal matrix."""

import datetime
import hashlib
import json
import platform
import shutil
import subprocess
import time
from pathlib import Path

import run_phase4b_suite as phase4b
from phase4c_formal_common import (
    BASELINE, CONDITIONS, FORMAL_ROOT, MAPS, ORDERS, ROOT,
    SCIENTIFIC_BASE_COMMIT, materialize_runtime_environment,
)
from preflight_phase4b import check_no_residual_ros, run_logged
from run_phase2_pairs import AUTHOR_RESULTS, CORE_NODES, start_process, stop_process, wait_for_command


NAVIGATION = ROOT / 'dependencies' / 'navigation_2d'
TSP_FIELDS = (
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


def canonical_hash(value):
    raw = json.dumps(value, separators=(',', ':'), ensure_ascii=True).encode('ascii')
    return hashlib.sha256(raw).hexdigest()


def frozen_opportunity(map_id, seed):
    if map_id == 'map8':
        path = ROOT / 'results/phase4c0/opportunity_adequacy/high_level_plans.json'
    else:
        path = ROOT / 'results/phase4c1/high_level_plans.json'
    return json.loads(path.read_text())[map_id][str(seed)]


def source_manifest():
    paths = [
        'baseline/Graph-Based_SLAM-Aware_Exploration/launch/exploration.launch',
        'baseline/Graph-Based_SLAM-Aware_Exploration/param/mapper.yaml',
        'baseline/Graph-Based_SLAM-Aware_Exploration/param/navigator.yaml',
        'baseline/Graph-Based_SLAM-Aware_Exploration/param/operator.yaml',
        'baseline/Graph-Based_SLAM-Aware_Exploration/param/costmap.yaml',
        'baseline/Graph-Based_SLAM-Aware_Exploration/param/ros.yaml',
        'baseline/Graph-Based_SLAM-Aware_Exploration/scripts/path_planner.py',
        'baseline/Graph-Based_SLAM-Aware_Exploration/src/MyPlanner.cpp',
        'dependencies/navigation_2d/nav2d_karto/OpenKarto/source/OpenMapper.cpp',
        'dependencies/navigation_2d/nav2d_karto/src/MultiMapper.cpp',
        'tools/phase2_observer.py', 'tools/evaluate_slam_run.py',
        'tools/evaluate_mapping.py', 'tools/evaluate_mapping_v2.py',
        'tools/finalize_phase2_run.py', 'tools/finalize_phase4b_run.py',
        'tools/audit_phase4c05_neutrality.py',
        'tools/phase4c_formal_common.py', 'tools/run_phase4b_suite.py',
        'tools/run_phase4c_formal.py', 'tools/preflight_phase4c_formal.py',
        'tools/analyze_phase4c_formal.py',
        'tools/test_phase4c_formal_runner.py',
    ]
    return {name: sha256(ROOT / name) for name in paths}


def launch_probe(map_id, mode, seed, attempt_dir, env, token):
    config = MAPS[map_id]
    probe_dir = attempt_dir / '{}_mode_{}'.format(map_id, mode)
    probe_dir.mkdir()
    suffix = '_Phase4C_preflight_{}_{}_mode{}'.format(token, map_id, mode)
    tsp_source = AUTHOR_RESULTS / 'tsp_record{}.json'.format(suffix)
    if tsp_source.exists():
        raise RuntimeError('pre-existing preflight output: {}'.format(tsp_source))
    roscore = launch = None
    try:
        check_no_residual_ros(env)
        roscore = start_process(['roscore'], env, probe_dir / 'roscore.log')
        wait_for_command(['rosparam', 'list'], env, 60, 'ROS master')
        condition = next(value for value in CONDITIONS.values() if value['oracle_mode'] == mode)
        command = phase4b.launch_command(seed, condition, suffix, config)
        (probe_dir / 'full_command.txt').write_text(
            subprocess.list2cmdline(command) + '\n', encoding='utf-8'
        )
        launch = start_process(command, env, probe_dir / 'roslaunch.log')
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline and not tsp_source.is_file():
            if launch.poll() is not None:
                raise RuntimeError('{} mode {} exited before TSP'.format(map_id, mode))
            time.sleep(1)
        if not tsp_source.is_file():
            raise RuntimeError('{} mode {} TSP timeout'.format(map_id, mode))
        shutil.copy2(tsp_source, probe_dir / 'tsp_record.json')
        for service in (
            '/StartMapping', '/StartExploration', '/prior_graph_service',
            '/path_plan_service', '/reliable_loop_service',
        ):
            wait_for_command(['rosservice', 'type', service], env, 180, service)
        wait_for_command(['rostopic', 'type', '/Mapper/loop_closed'], env, 180, 'loop_closed')
        nodes = set(wait_for_command(['rosnode', 'list'], env, 60, 'core nodes').splitlines())
        missing = sorted(CORE_NODES - nodes)
        if missing:
            raise RuntimeError('{} mode {} missing nodes {}'.format(map_id, mode, missing))
        diagnostics = wait_for_command(
            ['rosparam', 'get', '/Mapper/enable_loop_diagnostics'], env, 30, 'diagnostics'
        ).strip().lower()
        actual_mode = int(wait_for_command(
            ['rosparam', 'get', '/path_planner/oracle_mode'], env, 30, 'oracle_mode'
        ).strip())
        if diagnostics not in ('false', '0') or actual_mode != mode:
            raise RuntimeError('runtime parameter mismatch diagnostics={} mode={}'.format(
                diagnostics, actual_mode
            ))
        record = json.loads((probe_dir / 'tsp_record.json').read_text())
        actual = {key: record.get(key) for key in TSP_FIELDS}
        frozen = frozen_opportunity(map_id, seed)
        if canonical_hash(record['initial_tsp_path']) != frozen['initial_tsp_hash']:
            raise RuntimeError('{} initial TSP differs from frozen opportunity audit'.format(map_id))
        if canonical_hash(record['full_tsp_path']) != frozen['full_tsp_hash']:
            raise RuntimeError('{} full TSP differs from frozen opportunity audit'.format(map_id))
        return {
            'map': map_id, 'mode': mode, 'tsp': actual,
            'tsp_record_sha256': sha256(probe_dir / 'tsp_record.json'),
            'frozen_initial_tsp_hash': frozen['initial_tsp_hash'],
            'frozen_full_tsp_hash': frozen['full_tsp_hash'],
            'diagnostics': False, 'core_nodes': sorted(CORE_NODES),
        }
    finally:
        stop_process(launch)
        stop_process(roscore)
        time.sleep(2)


def main():
    env = phase4b.activated_environment()
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    FORMAL_ROOT.mkdir(parents=True, exist_ok=True)
    token = datetime.datetime.now().strftime('%Y%m%dT%H%M%S')
    attempt_dir = FORMAL_ROOT / 'preflight' / ('attempt_' + token)
    attempt_dir.mkdir(parents=True)
    summary = {'status': 'RUNNING', 'attempt': token, 'checks': {}}
    summary_path = attempt_dir / 'preflight_summary.json'
    summary_path.write_text(json.dumps(summary, indent=2) + '\n')
    try:
        check_no_residual_ros(env)
        summary['checks']['no_residual_ros'] = 'PASS'
        for repo in (ROOT, BASELINE, NAVIGATION):
            tracked = git_output(repo, 'status', '--porcelain', '--untracked-files=no')
            if tracked:
                raise RuntimeError('tracked changes in {}:\n{}'.format(repo, tracked))
        summary['checks']['all_tracked_worktrees_clean'] = 'PASS'
        free_bytes = shutil.disk_usage(str(ROOT)).free
        if free_bytes < 4 * 1024 ** 3:
            raise RuntimeError('less than 4 GiB free disk before formal suite')
        summary['checks']['free_disk_bytes'] = free_bytes

        environment_hashes = {
            map_id: materialize_runtime_environment(config)
            for map_id, config in MAPS.items()
        }
        summary['checks']['frozen_environment_hashes'] = environment_hashes

        run_logged(
            ['bash', '-lc', 'source catkin_ws/activate.sh && cd catkin_ws && catkin_make'],
            env, attempt_dir / 'catkin_build.log', timeout=1800,
        )
        run_logged(
            ['/usr/bin/python3', 'tools/test_phase4a_selective.py'],
            env, attempt_dir / 'phase4a_unit_tests.log', timeout=300,
        )
        run_logged(
            ['/usr/bin/python3', '-m', 'unittest', '-v',
             'tools/test_phase4b_mapping.py', 'tools/test_phase4c0_mapping.py',
             'tools/test_phase4c_formal_runner.py'],
            env, attempt_dir / 'mapping_unit_tests.log', timeout=300,
        )
        summary['checks']['build_and_tests'] = 'PASS'

        probes = []
        for map_id in MAPS:
            map_probes = [
                launch_probe(map_id, mode, 21001, attempt_dir, env, token)
                for mode in (0, 1, 2)
            ]
            if any(probe['tsp'] != map_probes[0]['tsp'] for probe in map_probes[1:]):
                raise RuntimeError('{} TSP differs across oracle modes'.format(map_id))
            probes.extend(map_probes)
        summary['checks']['startup_probes'] = probes
        summary['checks']['tsp_pairing_and_frozen_match'] = 'PASS'
        summary['checks']['diagnostics_off'] = 'PASS'
        check_no_residual_ros(env)
        summary['checks']['post_probe_no_residual_ros'] = 'PASS'

        manifest = {
            'phase': '4C_FORMAL', 'status': 'PREFLIGHT_PASS_NOT_STARTED',
            'scientific_base_commit': SCIENTIFIC_BASE_COMMIT,
            'commits': {
                'root': git_output(ROOT, 'rev-parse', 'HEAD'),
                'baseline': git_output(BASELINE, 'rev-parse', 'HEAD'),
                'navigation_2d': git_output(NAVIGATION, 'rev-parse', 'HEAD'),
            },
            'source_sha256': source_manifest(),
            'environment_sha256': environment_hashes,
            'formal_maps': list(MAPS), 'formal_seeds': list(ORDERS),
            'counterbalanced_order': {
                str(seed): list(order) for seed, order in ORDERS.items()
            },
            'conditions': CONDITIONS, 'only_scientific_variable': 'oracle_mode',
            'diagnostics_enabled': False, 'automatic_retry': False,
            'technical_invalid_preservation': 'attempt_N; no deletion or automatic retry',
            'initial_tsp_mismatch': 'BLOCKER before StartMapping',
            'experimental_failures_retained': True,
            'outcome_based_stopping': False,
            'mapping_protocol': {
                'boundary_f1_tolerance_m': 0.20,
                'symmetric_boundary_distance': True,
                'secondary': 'occupied_iou', 'local_roi_radius_m': 5.0,
            },
            'trajectory_protocol': {
                'evo_version': '1.31.1', 'timestamp_max_diff_s': 0.05,
                'alignment': 'none', 'projection': 'xy',
            },
            'runtime': {
                'platform': platform.platform(), 'ros': 'Noetic',
                'ros_python': '/usr/bin/python3 3.8',
                'explore_wall_timeout_s': 18000,
            },
            'preflight_attempt': str(attempt_dir.relative_to(FORMAL_ROOT)),
            'formal_performance_runs_started': False,
        }
        (FORMAL_ROOT / 'protocol_manifest.json').write_text(
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
