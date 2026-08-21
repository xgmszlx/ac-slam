#!/usr/bin/python3

"""Collect and summarize one Phase 1 smoke run without changing ROS behavior."""

import argparse
import ast
import json
import math
import os
import re
import shutil
import subprocess


ANSI = re.compile(r'\x1b\[[0-9;]*[A-Za-z]|\x1b\][^\x07]*\x07')


def parse_list(text):
    try:
        value = ast.literal_eval(text.strip())
    except (SyntaxError, ValueError):
        return None
    return value if isinstance(value, list) else None


def parse_paths(log_path):
    with open(log_path, errors='replace') as stream:
        lines = [ANSI.sub('', line).strip() for line in stream]
    result = {
        'initial_tsp_path': None,
        'full_tsp_path': None,
        'modified_slam_aware_path': None,
        'non_optimized_tsp_path': None,
        'planner_received_path': None,
        'is_loop': None,
        'loop_vertices': [],
    }
    for index, line in enumerate(lines):
        if line == 'tsp_path VS full_tsp_path:' and index + 2 < len(lines):
            result['initial_tsp_path'] = parse_list(lines[index + 1])
            result['full_tsp_path'] = parse_list(lines[index + 2])
        elif line.startswith('optimized tsp path:'):
            result['modified_slam_aware_path'] = parse_list(line.split(':', 1)[1])
        elif line.startswith('non-optimized tsp path:'):
            result['non_optimized_tsp_path'] = parse_list(line.split(':', 1)[1])
        elif 'Receive tsp path:' in line:
            payload = line.split('Receive tsp path:', 1)[1]
            result['planner_received_path'] = [int(v) for v in re.findall(r'-?\d+', payload)]
        elif 'Receive loop index:' in line:
            payload = line.split('Receive loop index:', 1)[1]
            result['is_loop'] = [bool(int(v)) for v in re.findall(r'\b[01]\b', payload)]
    if result['planner_received_path'] and result['is_loop']:
        result['loop_vertices'] = [
            result['planner_received_path'][i]
            for i, flag in enumerate(result['is_loop'])
            if flag and i < len(result['planner_received_path'])
        ]
    return result


def trajectory_length(path, start_time=None, end_time=None):
    points = []
    with open(path) as stream:
        for line in stream:
            fields = line.split()
            if len(fields) < 3:
                continue
            stamp, x, y = map(float, fields[:3])
            if start_time is not None and stamp < start_time:
                continue
            if end_time is not None and stamp > end_time:
                continue
            points.append((x, y))
    return sum(
        math.hypot(curr[0] - prev[0], curr[1] - prev[1])
        for prev, curr in zip(points, points[1:])
    )


def parse_explore_result(path):
    """Recover the action interval even if the observer starts late."""
    if not os.path.exists(path):
        return {}
    with open(path, errors='replace') as stream:
        text = stream.read()
    stamps = re.findall(
        r'stamp:\s*\n\s*secs:\s*(\d+)\s*\n\s*nsecs:\s*(\d+)', text
    )
    result = {}
    if stamps:
        result['end'] = int(stamps[0][0]) + int(stamps[0][1]) * 1e-9
    if len(stamps) > 1:
        result['start'] = int(stamps[1][0]) + int(stamps[1][1]) * 1e-9
    statuses = re.findall(r'^\s{2}status:\s*(\d+)\s*$', text, re.MULTILINE)
    if statuses:
        result['status'] = int(statuses[-1])
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--suffix', required=True)
    parser.add_argument('--method', required=True)
    parser.add_argument('--strategy', required=True)
    parser.add_argument('--only-use-tsp', choices=('true', 'false'), required=True)
    parser.add_argument('--map', default='map3')
    parser.add_argument('--launch-map-name', default='map3/map3')
    parser.add_argument('--start-pose', default='-28.0,-28.0,0.0')
    args = parser.parse_args()
    run_dir = os.path.abspath(args.run_dir)
    author_dir = os.path.join(run_dir, 'author_outputs')

    summary_path = os.path.join(run_dir, 'events_summary.json')
    with open(summary_path) as stream:
        summary = json.load(stream)
    action_result = parse_explore_result(os.path.join(run_dir, 'explore_result.txt'))
    if action_result.get('start') is not None:
        summary['explore_start_sim_time'] = action_result['start']
    if action_result.get('end') is not None:
        summary['explore_end_sim_time'] = action_result['end']
    if action_result.get('status') is not None:
        summary['explore_result_status'] = action_result['status']
    if (
        summary.get('explore_start_sim_time') is not None
        and summary.get('explore_end_sim_time') is not None
    ):
        summary['total_exploration_time'] = (
            summary['explore_end_sim_time'] - summary['explore_start_sim_time']
        )
    paths = parse_paths(os.path.join(run_dir, 'roslaunch.log'))

    gt_source = os.path.join(author_dir, 'gt_traj{}.txt'.format(args.suffix))
    slam_source = os.path.join(author_dir, 'slam_traj{}.txt'.format(args.suffix))
    graph_source = os.path.join(author_dir, 'graph{}.g2o'.format(args.suffix))
    for source, target in (
        (gt_source, os.path.join(run_dir, 'trajectory_gt.txt')),
        (slam_source, os.path.join(run_dir, 'trajectory_slam.txt')),
        (graph_source, os.path.join(run_dir, 'pose_graph.g2o')),
    ):
        if os.path.exists(source):
            shutil.copy2(source, target)

    if os.path.exists(gt_source):
        summary['total_path_length_gt_postprocessed'] = trajectory_length(
            gt_source,
            summary.get('explore_start_sim_time'),
            summary.get('explore_end_sim_time'),
        )
    summary['paths'] = paths
    with open(os.path.join(run_dir, 'paths.json'), 'w') as stream:
        json.dump(paths, stream, indent=2, sort_keys=True)
        stream.write('\n')
    with open(os.path.join(run_dir, 'metrics.json'), 'w') as stream:
        json.dump(summary, stream, indent=2, sort_keys=True)
        stream.write('\n')

    baseline_dir = '/home/wcqw/ac-slam/baseline/Graph-Based_SLAM-Aware_Exploration'
    commit = subprocess.check_output(
        ['git', '-C', baseline_dir, 'rev-parse', 'HEAD'], text=True
    ).strip()
    manifest = {
        'method': args.method,
        'map': args.map,
        'start_pose_xyyaw': [float(value) for value in args.start_pose.split(',')],
        'git_commit': commit,
        'launch_file': 'cpp_solver exploration.launch',
        'launch_arguments': {
            'map_name': args.launch_map_name,
            'strategy': args.strategy,
            'only_use_tsp': args.only_use_tsp == 'true',
            'suffix': args.suffix,
        },
        'python': '/usr/bin/python3 (3.8)',
        'stdout_stderr': 'roslaunch.log',
        'observer': 'tools/phase1_event_logger.py (read-only)',
    }
    with open(os.path.join(run_dir, 'manifest.json'), 'w') as stream:
        json.dump(manifest, stream, indent=2, sort_keys=True)
        stream.write('\n')


if __name__ == '__main__':
    main()
