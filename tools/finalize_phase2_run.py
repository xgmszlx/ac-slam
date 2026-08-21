#!/usr/bin/python3
"""Derive planned-vs-actual and loop-count summaries for one Phase 2 run."""

import argparse
import json
import pickle
from pathlib import Path


def lcs_length(left, right):
    previous = [0] * (len(right) + 1)
    for left_value in left:
        current = [0]
        for index, right_value in enumerate(right, 1):
            if left_value == right_value:
                current.append(previous[index - 1] + 1)
            else:
                current.append(max(previous[index], current[-1]))
        previous = current
    return previous[-1]


def levenshtein(left, right):
    previous = list(range(len(right) + 1))
    for left_index, left_value in enumerate(left, 1):
        current = [left_index]
        for right_index, right_value in enumerate(right, 1):
            current.append(min(
                current[-1] + 1,
                previous[right_index] + 1,
                previous[right_index - 1] + (left_value != right_value),
            ))
        previous = current
    return previous[-1]


def planned_graph_path_length(run_dir, planned):
    """Measure the recorded high-level path on the saved prior graph."""
    graph_paths = sorted((run_dir / 'author_outputs').glob('prior_map*.pickle'))
    if not graph_paths:
        return None
    with graph_paths[0].open('rb') as graph_file:
        graph = pickle.load(graph_file)
    total = 0.0
    for start, end in zip(planned, planned[1:]):
        if not graph.has_edge(start, end):
            raise ValueError('recorded high-level path has no prior edge: {} -> {}'.format(
                start, end
            ))
        total += float(graph[start][end]['weight'])
    return total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', required=True, type=Path)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()

    observer = json.loads((run_dir / 'observer_summary.json').read_text())
    loops_path = run_dir / 'loops.json'
    loops = json.loads(loops_path.read_text()).get('loops', [])
    # Recompute conservatively here as well so runs made with an earlier live
    # observer revision use the same frozen criterion.
    for loop in loops:
        graph_edges = loop.get('new_pose_graph_edges', [])
        beyond_buffer = [
            edge for edge in graph_edges
            if abs(int(edge['start']) - int(edge['end'])) > 70
        ]
        loop['new_edges_beyond_70_scan_running_buffer'] = beyond_buffer
        loop['successful_slam_loop'] = (
            loop.get('karto_closure_events_during_execution', 0) > 0
            and bool(beyond_buffer)
        )
        loop['successful_slam_loop_criterion'] = (
            'Karto accepted-loop event during execution AND a new pose-graph edge '
            'with node-index gap > default ScanBufferSize 70'
        )
    loops_path.write_text(json.dumps({'loops': loops}, indent=2, sort_keys=True) + '\n')
    tsp = json.loads((run_dir / 'tsp_record.json').read_text())
    planned = observer.get('initial_planned_high_level_path', [])
    actual = observer.get('actually_visited_high_level_vertices', [])
    edit_distance = levenshtein(planned, actual)
    lcs = lcs_length(planned, actual)
    high_level_path_length = planned_graph_path_length(run_dir, planned)

    planned_loop_vertices = [
        planned[index] for index, flag in enumerate(observer.get('initial_loop_flags', []))
        if flag and index < len(planned)
    ]
    executed_loop_vertices = [loop['loop_vertex'] for loop in loops if loop.get('executed_loop')]
    successful_loop_vertices = [
        loop['loop_vertex'] for loop in loops if loop.get('successful_slam_loop')
    ]
    mismatch = {
        'planned_high_level_vertices': planned,
        'actually_visited_high_level_vertices': actual,
        'planned_vertex_count': len(planned),
        'actual_vertex_count': len(actual),
        'levenshtein_edit_distance': edit_distance,
        'normalized_edit_distance': edit_distance / max(len(planned), len(actual), 1),
        'lcs_length': lcs,
        'planned_sequence_recall_lcs': lcs / max(len(planned), 1),
        'actual_sequence_precision_lcs': lcs / max(len(actual), 1),
        'interpretation': (
            'Order-sensitive exact vertex-sequence comparison. Normalized edit distance is '
            'Levenshtein distance divided by the longer sequence; 0 means identical. LCS '
            'recall/precision show how much order is retained without treating skipped vertices '
            'as substitutions.'
        ),
        'counts': observer.get('counts', {}),
        'planned_loop_vertices': planned_loop_vertices,
        'executed_loop_vertices': executed_loop_vertices,
        'successful_slam_loop_vertices': successful_loop_vertices,
        'planned_path_length': high_level_path_length,
        'initial_tsp_predicted_path_length': tsp.get('predicted_full_tsp_length'),
        'actual_path_length': observer.get('total_path_length_gt'),
    }
    (run_dir / 'planned_vs_actual.json').write_text(
        json.dumps(mismatch, indent=2, sort_keys=True) + '\n'
    )

    summary = {
        'solver': tsp.get('solver'),
        'seed': tsp.get('seed'),
        'initial_tsp_path': tsp.get('initial_tsp_path'),
        'full_tsp_path': tsp.get('full_tsp_path'),
        'predicted_tsp_length': tsp.get('predicted_tsp_length'),
        'predicted_full_tsp_length': tsp.get('predicted_full_tsp_length'),
        'total_exploration_time': observer.get('total_exploration_time'),
        'total_path_length_gt': observer.get('total_path_length_gt'),
        'planned_loops': len(loops),
        'executed_loops': sum(bool(loop.get('executed_loop')) for loop in loops),
        'successful_slam_loops': sum(bool(loop.get('successful_slam_loop')) for loop in loops),
        'planned_vs_actual': mismatch,
    }
    evo_path = run_dir / 'evo' / 'metrics.json'
    if evo_path.is_file():
        summary['evo'] = json.loads(evo_path.read_text()).get('whole_run')
    (run_dir / 'run_summary.json').write_text(
        json.dumps(summary, indent=2, sort_keys=True) + '\n'
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
