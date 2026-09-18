#!/usr/bin/python3
"""Prepare and execute the bounded v9 Stage calibration/branch captures."""

import argparse
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

from frame_gauge_audit import estimate_se2, transform_pose, wrap_angle  # noqa: E402
from run_pilot import (activated_environment, command_output, start_process,
                       stop_process)  # noqa: E402

ROOT = THIS_DIR.parents[1]
WORLD = ROOT / 'baseline/Graph-Based_SLAM-Aware_Exploration/world/map3/map3.world'


def load_json(path):
    with open(path) as stream:
        return json.load(stream)


def atomic_json(path, payload):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with open(temporary, 'w') as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write('\n')
    os.replace(temporary, path)


def prepare_specs(canonical_dir, output_dir):
    result = load_json(Path(canonical_dir) / 'episode_result.json')
    frozen = load_json(Path(canonical_dir) / 'frozen_target.json')
    history = [move for move in result['moves'] if move['label'].startswith('history_')]
    rotation, translation = estimate_se2(
        [move['tf_pose_after'][:2] for move in history],
        [move['gt_pose_after'][:2] for move in history])
    anchor = frozen['anchor_scan']
    anchor_map = [anchor['x'], anchor['y'], anchor['theta']]
    anchor_world = transform_pose(anchor_map, rotation, translation)
    segment = frozen['segment_nodes']
    centroid_x = sum(float(node['x']) for node in segment) / len(segment)
    centroid_y = sum(float(node['y']) for node in segment) / len(segment)
    terminal = result['terminal_gt_pose']
    setup = [move['gt_pose_after'] for move in history[:-1]] + [terminal]
    # The left side of the nominal rectangle is blocked in map3.  Use the
    # already validated history corridor in reverse as a uniform, outcome-blind
    # approach for every arm: terminal -> history_03 -> history_02 -> anchor.
    # Only the route to the frozen anchor changes; each core observation action
    # below is byte-for-byte the old A0/A1/A2 geometry.
    approach = [
        [float(history[2]['gt_pose_after'][0]),
         float(history[2]['gt_pose_after'][1]), -math.pi / 2.0],
        [float(history[1]['gt_pose_after'][0]),
         float(history[1]['gt_pose_after'][1]), math.pi],
    ]
    approach_labels = ['probe_approach_history_03',
                       'probe_approach_history_02']

    actions = {}
    actions['A0_baseline'] = {
        'action_id': 'n1_a0_baseline',
        'action_labels': approach_labels + ['probe_arrival'],
        'action_waypoints': approach + [anchor_world],
        'core_action_start_index': len(approach),
    }
    arrival = anchor_map
    radial = ((anchor_map[0] - centroid_x) * math.cos(arrival[2]) +
              (anchor_map[1] - centroid_y) * math.sin(arrival[2]))
    sign = 1.0 if radial >= 0.0 else -1.0
    neutral_out_map = [anchor_map[0] + sign * 1.5 * math.cos(arrival[2]),
                       anchor_map[1] + sign * 1.5 * math.sin(arrival[2]),
                       arrival[2]]
    actions['A1_neutral'] = {
        'action_id': 'n1_a1_neutral',
        'action_labels': approach_labels + [
            'probe_arrival', 'neutral_out', 'neutral_back'],
        'action_waypoints': approach + [anchor_world,
                             transform_pose(neutral_out_map, rotation, translation),
                             anchor_world],
        'core_action_start_index': len(approach),
        'neutral_sign_from_frozen_segment': sign,
    }
    sweep_maps = [
        [anchor_map[0], anchor_map[1], wrap_angle(anchor_map[2] + math.pi / 2.0)],
        [anchor_map[0], anchor_map[1], wrap_angle(anchor_map[2] - math.pi / 6.0)],
        [anchor_map[0], anchor_map[1], anchor_map[2]],
        [anchor_map[0], anchor_map[1], wrap_angle(anchor_map[2] + math.pi / 6.0)],
    ]
    actions['A2_sweep90'] = {
        'action_id': 'n1_a2_sweep90',
        'action_labels': approach_labels + [
            'probe_arrival', 'sweep_-30deg', 'sweep_+0deg', 'sweep_+30deg'],
        'action_waypoints': approach + [
            transform_pose(pose, rotation, translation) for pose in sweep_maps],
        'core_action_start_index': len(approach),
        'semantic_note': ('preserves old suite: +90 degree arrival followed by '
                          '-30/0/+30 degrees relative to anchor'),
    }
    common = {'setup_waypoints': setup, 'hold_s': 6.0,
              'canonical_terminal_gt_pose': terminal,
              'target_anchor_map': anchor_map,
              'target_anchor_world_by_history_only_se2': anchor_world,
              'T_W_M': {'tx': float(translation[0]), 'ty': float(translation[1]),
                        'yaw': math.atan2(rotation[1, 0], rotation[0, 0])}}
    output_dir = Path(output_dir)
    prereg = output_dir / 'preregistration'
    prereg.mkdir(parents=True, exist_ok=True)
    payload = {'protocol': 'p1_common_prefix_v9', 'target_id': 'map3_grid_anchor_01',
               'source_canonical_dir': str(Path(canonical_dir).resolve()),
               'common': common, 'actions': actions,
               'actions_frozen_before_branch_capture': True}
    primary = prereg / 'controlled_action_specs.json'
    spec_path = (prereg / 'controlled_action_specs_v2_uniform_approach.json'
                 if primary.exists() else primary)
    payload['preregistration_file'] = str(spec_path)
    payload['uniform_approach_amendment'] = {
        'reason': ('direct terminal-to-anchor line is collision blocked; use the '
                   'previously successful history corridor in reverse'),
        'outcome_blind': True,
        'applies_identically_to_all_actions': True,
        'changes_core_action_geometry': False,
    }
    atomic_json(spec_path, payload)
    return payload


def wait_topic(env, topic, timeout=45.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = command_output(['rostopic', 'type', topic], env, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            return
        time.sleep(0.25)
    raise RuntimeError('{} unavailable'.format(topic))


def run_stage_capture(env, spec, run_dir):
    run_dir = Path(run_dir)
    if run_dir.exists():
        raise RuntimeError('refusing to overwrite {}'.format(run_dir))
    run_dir.mkdir(parents=True)
    spec_path = run_dir / 'capture_spec.json'
    atomic_json(spec_path, spec)
    local_env = dict(env)
    local_env['ROS_LOG_DIR'] = str(run_dir / 'ros_logs')
    Path(local_env['ROS_LOG_DIR']).mkdir(parents=True)
    roscore = stage = None
    try:
        if command_output(['rosparam', 'list'], local_env, timeout=5).returncode == 0:
            raise RuntimeError('ROS master already running')
        roscore = start_process(['roscore'], local_env, run_dir / 'roscore.log')
        for _ in range(120):
            if command_output(['rosparam', 'list'], local_env, timeout=5).returncode == 0:
                break
            time.sleep(0.25)
        stage = start_process(
            ['rosrun', 'stage_ros', 'stageros', str(WORLD)], local_env,
            run_dir / 'stage.log')
        for topic in ('/base_pose_ground_truth', '/odom', '/base_scan', '/cmd_vel'):
            wait_topic(local_env, topic)
        driver_log = open(run_dir / 'driver.log', 'w')
        try:
            completed = subprocess.run(
                ['/usr/bin/python3', str(THIS_DIR / 'controlled_probe_capture.py'),
                 '--spec', str(spec_path), '--output-dir', str(run_dir)],
                env=local_env, cwd=str(ROOT), stdout=driver_log,
                stderr=subprocess.STDOUT, timeout=600, text=True)
        finally:
            driver_log.close()
        if completed.returncode != 0:
            raise RuntimeError('controlled capture failed; see {}'.format(
                run_dir / 'driver.log'))
        return load_json(run_dir / 'capture_result.json')
    finally:
        stop_process(stage); stop_process(roscore)


def pose_error(observed, target):
    return [math.hypot(observed[0] - target[0], observed[1] - target[1]),
            abs(wrap_angle(observed[2] - target[2]))]


def execute(canonical_dir, output_dir, resume_after_calibration=False):
    output_dir = Path(output_dir).resolve()
    payload = prepare_specs(canonical_dir, output_dir)
    env = activated_environment()
    terminal = payload['common']['canonical_terminal_gt_pose']
    tolerance_path = output_dir / 'preregistration/branch_start_tolerance.json'
    if resume_after_calibration:
        calibration_payload = load_json(tolerance_path)
        tolerance = calibration_payload['branch_start_tolerance']
    else:
        calibrations = []
        for index in range(3):
            spec = dict(payload['common'], calibration_only=True,
                        action_id='calibration_{:02d}'.format(index + 1),
                        action_waypoints=[], action_labels=[])
            result = run_stage_capture(
                env, spec,
                output_dir / 'calibration' / 'run_{:02d}'.format(index + 1))
            error = pose_error(result['branch_start_gt_pose'], terminal)
            calibrations.append({'run': index + 1,
                                 'branch_start_gt_pose': result['branch_start_gt_pose'],
                                 'deviation_from_canonical': error})
        max_position = max(row['deviation_from_canonical'][0]
                           for row in calibrations)
        max_heading = max(row['deviation_from_canonical'][1]
                          for row in calibrations)
        tolerance = {
            'position_m': max(0.08, 1.25 * max_position),
            'heading_rad': max(0.04, 1.25 * max_heading),
            'rule': ('max(fixed controller floor, 1.25 x maximum deviation in '
                     'three pre-branch calibration runs)'),
            'frozen_before_branch_outcomes': True,
        }
        calibration_payload = {'canonical_terminal_gt_pose': terminal,
                               'calibration_runs': calibrations,
                               'branch_start_tolerance': tolerance}
        atomic_json(tolerance_path, calibration_payload)

    branch_results = []
    for directory_name in ('A0_baseline', 'A1_neutral', 'A2_sweep90'):
        action = payload['actions'][directory_name]
        spec = dict(payload['common'], **action, calibration_only=False)
        branch_root = output_dir / 'branches' / directory_name
        branch_dir = branch_root / 'raw'
        if branch_dir.exists():
            attempt = 2
            while (branch_root / 'raw_attempt_{:02d}'.format(attempt)).exists():
                attempt += 1
            branch_dir = branch_root / 'raw_attempt_{:02d}'.format(attempt)
        result = run_stage_capture(env, spec, branch_dir)
        deviation = pose_error(result['branch_start_gt_pose'], terminal)
        passed = (deviation[0] <= tolerance['position_m'] and
                  deviation[1] <= tolerance['heading_rad'])
        result.update({'branch_name': directory_name,
                       'branch_start_deviation_position_m': deviation[0],
                       'branch_start_deviation_heading_rad': deviation[1],
                       'branch_start_gate_passed': passed})
        atomic_json(branch_dir / 'capture_result.json', result)
        branch_results.append(result)
        if not passed:
            raise RuntimeError('{} branch-start identity gate failed'.format(
                directory_name))
    summary = {'status': 'SUCCEEDED', 'calibration': calibration_payload,
               'branches': branch_results,
               'all_branch_starts_passed': all(
                   row['branch_start_gate_passed'] for row in branch_results)}
    analysis_dir = output_dir / 'analysis'
    analysis_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(analysis_dir / 'controlled_capture_summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--canonical-dir', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--resume-after-calibration', action='store_true')
    args = parser.parse_args()
    result = execute(args.canonical_dir, args.output_dir,
                     args.resume_after_calibration)
    print(json.dumps({'status': result['status'],
                      'all_branch_starts_passed': result['all_branch_starts_passed'],
                      'branches': [row['action_id'] for row in result['branches']]},
                     indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
