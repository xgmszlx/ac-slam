#!/usr/bin/python3
"""Aggregate the fixed five-pair Phase 2A experiment without inference tests."""

import csv
import json
import statistics
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
PAIR_ROOT = ROOT / 'results' / 'phase2' / 'map3_pairs'
OUT = PAIR_ROOT / 'aggregate'


def rmse(summary, name):
    return summary['evo'][name]['rmse']


def describe(values):
    return {
        'values': values,
        'mean': statistics.mean(values),
        'median': statistics.median(values),
        'min': min(values),
        'max': max(values),
    }


def main():
    OUT.mkdir(exist_ok=True)
    pairs = []
    loop_rows = []
    reproducibility = []
    for pair in range(1, 6):
        pair_dir = PAIR_ROOT / 'pair_{:02d}'.format(pair)
        prior = json.loads((pair_dir / 'prior_tsp' / 'run_summary.json').read_text())
        slam = json.loads((pair_dir / 'slam_aware' / 'run_summary.json').read_text())
        prior_manifest = json.loads((pair_dir / 'prior_tsp' / 'manifest.json').read_text())
        slam_manifest = json.loads((pair_dir / 'slam_aware' / 'manifest.json').read_text())
        validations = [
            json.loads((pair_dir / method / 'tsp_pair_validation.json').read_text())
            for method in ('prior_tsp', 'slam_aware')
        ]
        reproducibility.append({
            'pair': pair,
            'seed': prior['seed'],
            'both_match_reference': all(item['matches_pair_reference'] for item in validations),
            'prior_sha256': validations[0]['record_sha256'],
            'slam_sha256': validations[1]['record_sha256'],
            'sha256_identical': validations[0]['record_sha256'] == validations[1]['record_sha256'],
            'initial_tsp_identical': prior['initial_tsp_path'] == slam['initial_tsp_path'],
            'full_tsp_identical': prior['full_tsp_path'] == slam['full_tsp_path'],
            'predicted_tsp_length_identical': prior['predicted_tsp_length'] == slam['predicted_tsp_length'],
            'execution_order': (
                'Prior-TSP -> SLAM-aware' if pair % 2 else 'SLAM-aware -> Prior-TSP'
            ),
            'git_commit_identical': prior_manifest['git_commit'] == slam_manifest['git_commit'],
        })
        row = {
            'pair': pair,
            'seed': prior['seed'],
            'prior_time_s': prior['total_exploration_time'],
            'slam_time_s': slam['total_exploration_time'],
            'delta_time_s': slam['total_exploration_time'] - prior['total_exploration_time'],
            'prior_distance_m': prior['total_path_length_gt'],
            'slam_distance_m': slam['total_path_length_gt'],
            'delta_distance_m': slam['total_path_length_gt'] - prior['total_path_length_gt'],
            'prior_planned_path_m': prior['planned_vs_actual']['planned_path_length'],
            'slam_planned_path_m': slam['planned_vs_actual']['planned_path_length'],
            'delta_planned_path_m': (
                slam['planned_vs_actual']['planned_path_length']
                - prior['planned_vs_actual']['planned_path_length']
            ),
            'prior_ape_rmse_m': rmse(prior, 'ape_se2_translation_m'),
            'slam_ape_rmse_m': rmse(slam, 'ape_se2_translation_m'),
            'delta_ape_rmse_m': rmse(slam, 'ape_se2_translation_m') - rmse(prior, 'ape_se2_translation_m'),
            'prior_rpe_trans_rmse_m': rmse(prior, 'rpe_translation_1m_m'),
            'slam_rpe_trans_rmse_m': rmse(slam, 'rpe_translation_1m_m'),
            'delta_rpe_trans_rmse_m': rmse(slam, 'rpe_translation_1m_m') - rmse(prior, 'rpe_translation_1m_m'),
            'prior_rpe_rot_rmse_deg': rmse(prior, 'rpe_rotation_1m_deg'),
            'slam_rpe_rot_rmse_deg': rmse(slam, 'rpe_rotation_1m_deg'),
            'delta_rpe_rot_rmse_deg': rmse(slam, 'rpe_rotation_1m_deg') - rmse(prior, 'rpe_rotation_1m_deg'),
            'planned_loops': slam['planned_loops'],
            'executed_loops': slam['executed_loops'],
            'successful_slam_loops': slam['successful_slam_loops'],
            'prior_path_mismatch_normalized_edit': prior['planned_vs_actual']['normalized_edit_distance'],
            'slam_path_mismatch_normalized_edit': slam['planned_vs_actual']['normalized_edit_distance'],
            'prior_path_lcs_recall': prior['planned_vs_actual']['planned_sequence_recall_lcs'],
            'slam_path_lcs_recall': slam['planned_vs_actual']['planned_sequence_recall_lcs'],
            'prior_planned_vertex_count': prior['planned_vs_actual']['planned_vertex_count'],
            'slam_planned_vertex_count': slam['planned_vs_actual']['planned_vertex_count'],
            'prior_actual_vertex_count': prior['planned_vs_actual']['actual_vertex_count'],
            'slam_actual_vertex_count': slam['planned_vs_actual']['actual_vertex_count'],
            'prior_no_frontier_at_vertex': prior['planned_vs_actual']['counts']['no_frontier_at_vertex'],
            'slam_no_frontier_at_vertex': slam['planned_vs_actual']['counts']['no_frontier_at_vertex'],
            'prior_repeated_visit_skip': prior['planned_vs_actual']['counts']['repeated_visit_skip'],
            'slam_repeated_visit_skip': slam['planned_vs_actual']['counts']['repeated_visit_skip'],
            'prior_goal_skip': prior['planned_vs_actual']['counts']['goal_skip_seen_no_frontier'],
            'slam_goal_skip': slam['planned_vs_actual']['counts']['goal_skip_seen_no_frontier'],
            'prior_local_replanning_calls': prior['planned_vs_actual']['counts']['local_replanning_calls'],
            'slam_local_replanning_calls': slam['planned_vs_actual']['counts']['local_replanning_calls'],
        }
        pairs.append(row)

        loops = json.loads((pair_dir / 'slam_aware' / 'loops.json').read_text())['loops']
        evo_loops = {
            str(item['loop_id']): item
            for item in json.loads((pair_dir / 'slam_aware' / 'evo' / 'metrics.json').read_text())['loops']
        }
        for loop in loops:
            evo_loop = evo_loops.get(str(loop['loop_id']), {})
            loop_row = {
                'pair': pair,
                'loop_id': loop['loop_id'],
                'loop_vertex': loop['loop_vertex'],
                'planned_start_time': loop['planned_start_time'],
                'actual_start_time': loop['actual_start_time'],
                'actual_end_time': loop['actual_end_time'],
                'extra_distance_m': loop['extra_distance'],
                'extra_time_s': loop['extra_time'],
                'reliable_loop_service_success': loop['reliable_loop_service_success'],
                'fallback': loop['fallback'],
                'waypoints_planned': loop['waypoints_planned'],
                'waypoints_reached': len(set(loop['waypoints_reached'])),
                'executed_loop': loop['executed_loop'],
                'karto_accepted_loop_events': loop['karto_closure_events_during_execution'],
                'new_edges_beyond_70_scan_buffer': len(loop.get('new_edges_beyond_70_scan_running_buffer', [])),
                'karto_marker_edge_delta_auxiliary': loop.get('karto_closure_edge_delta'),
                'pose_graph_node_delta': loop.get('pose_graph_node_delta'),
                'pose_graph_edge_delta': loop.get('pose_graph_edge_delta'),
                'successful_slam_loop': loop['successful_slam_loop'],
                'planned_loop_path_file': 'pair_{:02d}/slam_aware/loops.json'.format(pair),
                'snapshot_before': loop['snapshot_before'],
                'snapshot_after': loop['snapshot_after'],
                'evo_status': evo_loop.get('status'),
            }
            if evo_loop.get('status') == 'COMPUTED':
                for key, output_name in (
                    ('ape_se2_translation_m', 'ape_rmse_m'),
                    ('rpe_translation_1m_m', 'rpe_trans_rmse_m'),
                    ('rpe_rotation_1m_deg', 'rpe_rot_rmse_deg'),
                ):
                    before = evo_loop['cumulative_before'][key]['rmse']
                    after = evo_loop['cumulative_after'][key]['rmse']
                    loop_row[output_name + '_cumulative_before'] = before
                    loop_row[output_name + '_cumulative_after'] = after
                    loop_row[output_name + '_cumulative_delta'] = after - before
            loop_rows.append(loop_row)

    pair_fields = list(pairs[0])
    with open(OUT / 'paired_results.csv', 'w', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=pair_fields)
        writer.writeheader()
        writer.writerows(pairs)
    loop_fields = sorted({key for row in loop_rows for key in row})
    with open(OUT / 'per_loop_effectiveness.csv', 'w', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=loop_fields)
        writer.writeheader()
        writer.writerows(loop_rows)
    (OUT / 'reproducibility_check.json').write_text(
        json.dumps(reproducibility, indent=2, sort_keys=True) + '\n'
    )

    deltas = {
        key: describe([row[key] for row in pairs]) for key in (
            'delta_time_s', 'delta_distance_m', 'delta_planned_path_m', 'delta_ape_rmse_m',
            'delta_rpe_trans_rmse_m', 'delta_rpe_rot_rmse_deg',
        )
    }
    summary = {
        'runs_succeeded': 10,
        'pairs': 5,
        'all_tsp_inputs_identical_within_pair': all(
            item['both_match_reference'] and item['sha256_identical']
            and item['initial_tsp_identical'] and item['full_tsp_identical']
            for item in reproducibility
        ),
        'planned_loops': sum(row['planned_loops'] for row in pairs),
        'executed_loops': sum(row['executed_loops'] for row in pairs),
        'successful_slam_loops': sum(row['successful_slam_loops'] for row in pairs),
        'fallback_loops': sum(bool(row['fallback']) for row in loop_rows),
        'total_loop_extra_distance_m': sum(row['extra_distance_m'] for row in loop_rows),
        'total_loop_extra_time_s': sum(row['extra_time_s'] for row in loop_rows),
        'paired_differences': deltas,
        'prior_mismatch_normalized_edit': describe([
            row['prior_path_mismatch_normalized_edit'] for row in pairs
        ]),
        'slam_mismatch_normalized_edit': describe([
            row['slam_path_mismatch_normalized_edit'] for row in pairs
        ]),
        'note': 'descriptive raw points and paired differences only; no significance test',
    }
    (OUT / 'aggregate_summary.json').write_text(
        json.dumps(summary, indent=2, sort_keys=True) + '\n'
    )

    metrics = [
        ('time_s', 'Exploration time (s)'), ('distance_m', 'GT path length (m)'),
        ('ape_rmse_m', 'APE RMSE (m)'), ('rpe_trans_rmse_m', 'Trans. RPE RMSE (m)'),
        ('rpe_rot_rmse_deg', 'Rot. RPE RMSE (deg)'),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(13, 8))
    axes = axes.ravel()
    for axis, (stem, label) in zip(axes, metrics):
        for row in pairs:
            axis.plot(
                [0, 1], [row['prior_' + stem], row['slam_' + stem]],
                marker='o', alpha=0.75,
            )
        axis.set_xticks([0, 1])
        axis.set_xticklabels(['Prior-TSP', 'SLAM-aware'])
        axis.set_ylabel(label)
        axis.grid(alpha=0.25)
    axes[-1].axis('off')
    fig.suptitle('Map3 paired raw points (n=5)')
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(OUT / 'paired_raw_points.png', dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(2, 3, figsize=(13, 8))
    axes = axes.ravel()
    for axis, (stem, label) in zip(axes, metrics):
        values = [row['delta_' + stem] for row in pairs]
        axis.axhline(0, color='black', linewidth=1)
        axis.scatter(range(1, 6), values, s=45)
        axis.plot(range(1, 6), values, alpha=0.45)
        axis.set_xticks(range(1, 6))
        axis.set_xlabel('Pair')
        axis.set_ylabel('SLAM-aware - TSP\n' + label)
        axis.grid(alpha=0.25)
    axes[-1].axis('off')
    fig.suptitle('Map3 paired differences (n=5)')
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(OUT / 'paired_differences.png', dpi=180)
    plt.close(fig)

    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
