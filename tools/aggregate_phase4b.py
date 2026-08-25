#!/usr/bin/python3
"""Aggregate Phase 4B raw runs and generate all frozen tables/figures."""

import argparse
import csv
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


METHODS = {
    'A': ('A_original', 'Original'),
    'B': ('B_always_trace', 'Always-Trace'),
    'C': ('C_selective', 'Selective'),
}
METRICS = (
    'acceptance_rate', 'active_loop_distance_m', 'active_loop_time_s',
    'ape_rmse_m', 'rpe_translation_rmse_m', 'rpe_rotation_rmse_deg',
    'occupied_iou', 'boundary_f1',
)


def finite(value):
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def write_csv(path, rows, fields):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def flatten_run(seed, label, summary):
    realization = summary.get('loop_realization', {})
    cost = summary.get('execution_cost', {})
    trajectory = summary.get('trajectory', {})
    mapping = summary.get('mapping', {})
    exploration = summary.get('exploration', {})
    return {
        'seed': seed,
        'condition': label,
        'method': METHODS[label][1],
        'validity': summary.get('validity'),
        'planned_active_loops': realization.get('planned_active_loops'),
        'executed_active_loops': realization.get('executed_active_loops'),
        'accepted_active_loops': realization.get('accepted_active_loops'),
        'acceptance_rate': realization.get('acceptance_rate'),
        'active_loop_distance_m': cost.get('active_loop_distance_m'),
        'active_loop_time_s': cost.get('active_loop_time_s'),
        'repair_trigger_count': cost.get('repair_trigger_count'),
        'no_repair_count': cost.get('no_repair_count'),
        'repair_distance_m': cost.get('repair_distance_m'),
        'repair_time_s': cost.get('repair_time_s'),
        'early_stop_count': cost.get('early_stop_count'),
        'early_stop_saved_planned_distance_m_estimate': cost.get(
            'early_stop_saved_planned_distance_m_estimate'
        ),
        'total_exploration_distance_m': exploration.get('total_distance_m'),
        'total_exploration_sim_time_s': exploration.get('sim_time_s'),
        'total_exploration_wall_time_s': exploration.get('wall_time_s'),
        'wall_sim_ratio': exploration.get('wall_sim_ratio'),
        'ape_rmse_m': trajectory.get('ape_se2_translation_rmse_m'),
        'rpe_translation_rmse_m': trajectory.get('rpe_translation_1m_rmse_m'),
        'rpe_rotation_rmse_deg': trajectory.get('rpe_rotation_1m_rmse_deg'),
        'occupied_iou': mapping.get('occupied_iou'),
        'boundary_f1': mapping.get('occupied_boundary_f1'),
        'estimated_unknown_ratio': mapping.get('estimated_unknown_ratio'),
    }


def summary_stats(values):
    clean = [float(value) for value in values if finite(value)]
    if not clean:
        return {'n': 0, 'mean': None, 'median': None, 'min': None, 'max': None}
    return {
        'n': len(clean), 'mean': float(np.mean(clean)),
        'median': float(np.median(clean)), 'min': min(clean), 'max': max(clean),
    }


def paired_rows(run_lookup):
    rows = []
    for seed in sorted(run_lookup):
        conditions = run_lookup[seed]
        for left, right, label in (('C', 'A', 'C-A'), ('B', 'A', 'B-A'), ('C', 'B', 'C-B')):
            for metric in METRICS:
                left_value = conditions.get(left, {}).get(metric)
                right_value = conditions.get(right, {}).get(metric)
                rows.append({
                    'seed': seed, 'contrast': label, 'metric': metric,
                    'left_value': left_value, 'right_value': right_value,
                    'difference': (
                        float(left_value) - float(right_value)
                        if finite(left_value) and finite(right_value) else None
                    ),
                })
    return rows


def grouped_plot(rows, metric, ylabel, path):
    fig, ax = plt.subplots(figsize=(7, 4.5))
    x = np.arange(3)
    for method_index, label in enumerate(('A', 'B', 'C')):
        values = [row[metric] for row in rows if row['condition'] == label and finite(row[metric])]
        if values:
            jitter = np.linspace(-0.08, 0.08, len(values))
            ax.scatter(np.full(len(values), method_index) + jitter, values, color='black', zorder=3)
            ax.plot([method_index - 0.18, method_index + 0.18],
                    [np.mean(values), np.mean(values)], color='tab:blue', linewidth=3)
    ax.set_xticks(x)
    ax.set_xticklabels([METHODS[label][1] for label in ('A', 'B', 'C')])
    ax.set_ylabel(ylabel)
    ax.grid(axis='y', alpha=0.25)
    fig.tight_layout()
    fig.savefig(str(path), dpi=180)
    plt.close(fig)


def seedwise_plot(rows, metric, ylabel, path):
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    for seed in sorted({row['seed'] for row in rows}):
        values = []
        for label in ('A', 'B', 'C'):
            match = [row for row in rows if row['seed'] == seed and row['condition'] == label]
            values.append(match[0][metric] if match and finite(match[0][metric]) else np.nan)
        ax.plot(range(3), values, marker='o', label=str(seed), alpha=0.8)
    ax.set_xticks(range(3))
    ax.set_xticklabels([METHODS[label][1] for label in ('A', 'B', 'C')])
    ax.set_ylabel(ylabel)
    ax.grid(axis='y', alpha=0.25)
    ax.legend(title='seed', fontsize=8)
    fig.tight_layout()
    fig.savefig(str(path), dpi=180)
    plt.close(fig)


def scatter_plot(rows, x_key, y_key, xlabel, ylabel, path):
    fig, ax = plt.subplots(figsize=(6, 4.8))
    colors = {'A': 'tab:gray', 'B': 'tab:orange', 'C': 'tab:blue'}
    for label in ('A', 'B', 'C'):
        subset = [
            row for row in rows if row['condition'] == label
            and finite(row[x_key]) and finite(row[y_key])
        ]
        ax.scatter([row[x_key] for row in subset], [row[y_key] for row in subset],
                   label=METHODS[label][1], color=colors[label])
        for row in subset:
            ax.annotate(str(row['seed']), (row[x_key], row[y_key]), fontsize=7)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(str(path), dpi=180)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-root', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'results/phase4b/map3')
    args = parser.parse_args()
    root = args.input_root.resolve()
    aggregate = root / 'aggregate'
    aggregate.mkdir(parents=True, exist_ok=True)
    runs = []
    loops = []
    lookup = {}
    for seed_dir in sorted(root.glob('seed_*')):
        try:
            seed = int(seed_dir.name.split('_', 1)[1])
        except ValueError:
            continue
        lookup[seed] = {}
        for label, (directory, _) in METHODS.items():
            run_dir = seed_dir / directory
            summary_path = run_dir / 'run_summary.json'
            if not summary_path.is_file():
                continue
            summary = json.loads(summary_path.read_text())
            row = flatten_run(seed, label, summary)
            runs.append(row)
            lookup[seed][label] = row
            loops_path = run_dir / 'loops.json'
            if loops_path.is_file():
                for loop in json.loads(loops_path.read_text()).get('loops', []):
                    loops.append({
                        'seed': seed, 'condition': label, 'method': METHODS[label][1],
                        'loop_id': loop.get('loop_id'), 'loop_vertex': loop.get('loop_vertex'),
                        'execution_started': loop.get('phase4b_execution_started'),
                        'execution_finished': loop.get('phase4b_execution_finished'),
                        'accepted': loop.get('phase4b_accepted_active_loop'),
                        'execution_policy': loop.get('phase4b_execution_policy'),
                        'distance_m': loop.get('extra_distance'),
                        'time_s': loop.get('phase4b_active_loop_time_s'),
                        'planned_waypoints': loop.get('waypoints_planned'),
                        'reached_waypoints': len(set(loop.get('waypoints_reached') or [])),
                        'early_stopped': loop.get('early_stopped'),
                        'span_m': (loop.get('gate_decision') or {}).get('span_m'),
                        'saved_planned_distance_m_estimate': loop.get(
                            'early_stop_saved_planned_distance_m_estimate'
                        ),
                    })

    if not runs:
        raise SystemExit('no completed Phase 4B run summaries found')
    run_fields = list(runs[0])
    loop_fields = list(loops[0]) if loops else [
        'seed', 'condition', 'method', 'loop_id', 'loop_vertex'
    ]
    write_csv(aggregate / 'run_table.csv', runs, run_fields)
    write_csv(aggregate / 'loop_table.csv', loops, loop_fields)
    paired = paired_rows(lookup)
    write_csv(aggregate / 'paired_seed_effects.csv', paired, list(paired[0]))

    acceptance_rows = [
        {key: row.get(key) for key in (
            'seed', 'condition', 'method', 'validity', 'executed_active_loops',
            'accepted_active_loops', 'acceptance_rate',
        )} for row in runs
    ]
    write_csv(aggregate / 'acceptance_by_method.csv', acceptance_rows,
              list(acceptance_rows[0]))
    overhead_fields = [
        'seed', 'condition', 'method', 'active_loop_distance_m', 'active_loop_time_s',
        'total_exploration_distance_m', 'total_exploration_sim_time_s',
        'total_exploration_wall_time_s', 'wall_sim_ratio',
    ]
    write_csv(aggregate / 'active_loop_overhead.csv', runs, overhead_fields)
    trajectory_fields = [
        'seed', 'condition', 'method', 'ape_rmse_m', 'rpe_translation_rmse_m',
        'rpe_rotation_rmse_deg',
    ]
    write_csv(aggregate / 'trajectory_accuracy.csv', runs, trajectory_fields)
    mapping_fields = [
        'seed', 'condition', 'method', 'occupied_iou', 'boundary_f1',
        'estimated_unknown_ratio',
    ]
    write_csv(aggregate / 'mapping_quality.csv', runs, mapping_fields)
    repair_fields = [
        'seed', 'condition', 'method', 'repair_trigger_count', 'no_repair_count',
        'repair_distance_m', 'repair_time_s', 'early_stop_count',
        'early_stop_saved_planned_distance_m_estimate',
    ]
    write_csv(aggregate / 'repair_summary.csv', runs, repair_fields)

    method_stats = {}
    for label in ('A', 'B', 'C'):
        subset = [row for row in runs if row['condition'] == label]
        method_stats[label] = {
            metric: summary_stats([row.get(metric) for row in subset]) for metric in METRICS
        }
    contrast_stats = {}
    for contrast in ('C-A', 'B-A', 'C-B'):
        contrast_stats[contrast] = {}
        for metric in METRICS:
            contrast_stats[contrast][metric] = summary_stats([
                row['difference'] for row in paired
                if row['contrast'] == contrast and row['metric'] == metric
            ])
    phase_summary = {
        'run_count': len(runs),
        'seed_count': len(lookup),
        'validity_counts': {
            status: sum(row['validity'] == status for row in runs)
            for status in ('VALID', 'EXPERIMENTAL_FAILURE', 'TECHNICAL_INVALID')
        },
        'method_stats': method_stats,
        'paired_contrast_stats': contrast_stats,
        'inference_unit': 'seed',
        'p_values_reported': False,
    }
    (aggregate / 'phase4b_summary.json').write_text(
        json.dumps(phase_summary, indent=2, sort_keys=True) + '\n'
    )

    grouped_plot(runs, 'acceptance_rate', 'Active-loop acceptance rate',
                 aggregate / 'acceptance_rate.png')
    grouped_plot(runs, 'active_loop_distance_m', 'Active-loop distance (m)',
                 aggregate / 'active_loop_distance.png')
    grouped_plot(runs, 'active_loop_time_s', 'Active-loop time (s)',
                 aggregate / 'active_loop_time.png')
    seedwise_plot(runs, 'acceptance_rate', 'Active-loop acceptance rate',
                  aggregate / 'seedwise_acceptance.png')
    scatter_plot(runs, 'active_loop_distance_m', 'acceptance_rate',
                 'Active-loop distance (m)', 'Acceptance rate',
                 aggregate / 'success_cost_tradeoff.png')
    grouped_plot(runs, 'ape_rmse_m', 'APE translation RMSE (m)',
                 aggregate / 'ape_by_method.png')
    grouped_plot(runs, 'rpe_translation_rmse_m', 'RPE translation RMSE (m)',
                 aggregate / 'rpe_by_method.png')
    grouped_plot(runs, 'occupied_iou', 'Occupied-space IoU',
                 aggregate / 'map_iou_by_method.png')
    grouped_plot(runs, 'boundary_f1', 'Occupied-boundary F1',
                 aggregate / 'boundary_f1_by_method.png')
    scatter_plot(runs, 'acceptance_rate', 'boundary_f1',
                 'Acceptance rate', 'Occupied-boundary F1',
                 aggregate / 'mapping_vs_acceptance.png')
    print(json.dumps(phase_summary, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
