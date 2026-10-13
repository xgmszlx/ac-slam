#!/usr/bin/python3
"""Doc-79 figures - each one answers one review question.

1. topic vs sync per boundary (publication lag, missing historic links)
2. B/C L+/L- synchronous information gains (every run shown)
3. mechanism: accepted keyframes + provenance-classified edges
4. zero-gain vs effective run contrast (real constraint endpoints)
5. GT error change vs information increment
6. decision-evidence summary
"""

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

ARM_COLORS = {'L+': '#d62728', 'L-': '#2ca02c'}
PLACE_X = {'place_B': 0, 'place_C': 1}


def read_rows(path):
    path = Path(path)
    if not path.is_file():
        return []
    with open(path) as handle:
        return list(csv.DictReader(handle))


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def save(fig, out_dir, name):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_dir / (name + '.png'), dpi=160)
    fig.savefig(out_dir / (name + '.svg'))
    plt.close(fig)
    print('wrote', name)


# ---------------------------------------------------------------- figure 1
def fig1_topic_vs_sync(analysis, figures):
    rows = read_rows(analysis / 'topic_vs_sync_graph.csv')
    if not rows:
        print('fig1 skipped: no data')
        return
    boundaries = ['G_before_return', 'G_arrival', 'G_action_done', 'G_final']
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.2))
    ax = axes[0]
    for position, boundary in enumerate(boundaries):
        subset = [row for row in rows if row['boundary'] == boundary]
        topic = [number(row['topic_nodes']) for row in subset]
        sync = [number(row['sync_nodes']) for row in subset]
        for t, s in zip(topic, sync):
            if t is None or s is None:
                continue
            ax.plot([position - 0.18, position + 0.18], [t, s], color='#888888',
                    marker='o', markersize=3, linewidth=0.8, alpha=0.8)
    ax.set_xticks(range(len(boundaries)))
    ax.set_xticklabels(['before\nreturn', 'arrival', 'action\ndone', 'final'])
    ax.set_ylabel('graph nodes')
    ax.set_title('A. old topic cache vs synchronous dump\n(each line = one boundary export)')
    ax.grid(alpha=0.3, axis='y')
    ax = axes[1]
    for position, boundary in enumerate(boundaries):
        subset = [row for row in rows if row['boundary'] == boundary]
        deficits = [number(row['edge_deficit']) for row in subset]
        node_deficits = [number(row['node_deficit']) for row in subset]
        ax.scatter([position - 0.12] * len(node_deficits), node_deficits,
                   s=24, color='#1f77b4', alpha=0.85)
        ax.scatter([position + 0.12] * len(deficits), deficits,
                   s=24, color='#d62728', alpha=0.85)
    ax.set_xticks(range(len(boundaries)))
    ax.set_xticklabels(['before\nreturn', 'arrival', 'action\ndone', 'final'])
    ax.set_ylabel('missing in topic cache')
    ax.set_title('B. nodes (blue) and edges (red) only in the sync dump')
    ax.grid(alpha=0.3, axis='y')
    save(fig, figures, 'fig1_topic_vs_sync')


# ---------------------------------------------------------------- figure 2
def fig2_direction_gains(analysis, figures):
    metrics = [row for row in read_rows(analysis / 'per_episode_metrics.csv')
               if row.get('technical_validity') == 'MEASUREMENT_VALIDATED']
    if not metrics:
        print('fig2 skipped: no validated runs')
        return
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4))
    for ax, field, title in (
            (axes[0], 'delta_J_action_sync', 'A. action-stage information (sync)'),
            (axes[1], 'delta_J_total_sync', 'B. total post-history information (sync)')):
        for position, (place, action) in enumerate(
                [(p, a) for p in ('place_B', 'place_C') for a in ('L+', 'L-')]):
            subset = [row for row in metrics
                      if row['place'] == place and row['action'] == action]
            values = [number(row.get(field)) for row in subset]
            values = [value for value in values if value is not None]
            x = position + (0.0 if action == 'L+' else 0.18)
            ax.scatter([x] * len(values), values, s=32,
                       color=ARM_COLORS[action], alpha=0.9)
            if values:
                ax.plot([x - 0.08, x + 0.08],
                        [sum(values) / len(values)] * 2, color='k', linewidth=1.4)
        ax.axhline(0.0, color='k', linewidth=0.7)
        ax.set_xticks([0.09, 1.09, 2.09, 3.09])
        ax.set_xticklabels(['B\nL+', 'B\nL-', 'C\nL+', 'C\nL-'], fontsize=8)
        ax.set_ylabel('J_T increment [nats]')
        ax.set_title(title)
        ax.grid(alpha=0.3, axis='y')
    fig.suptitle('synchronous dumps only; every run shown (n=2 per condition)', fontsize=9)
    save(fig, figures, 'fig2_direction_gains')


# ---------------------------------------------------------------- figure 3
def fig3_mechanism(analysis, figures):
    rows = read_rows(analysis / 'action_mechanism.csv')
    if not rows:
        print('fig3 skipped: no data')
        return
    stages = ['return', 'action', 'tail']
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.2))
    ax = axes[0]
    for position, stage in enumerate(stages):
        subset = [row for row in rows if row['stage'] == stage]
        historic = [number(row['historic_links']) for row in subset]
        local = [number(row['local_only_closures']) for row in subset]
        chains = [number(row['new_edges']) - number(row['new_closures'])
                  for row in subset]
        ax.scatter([position - 0.15] * len(historic), historic, s=24,
                   color='#d62728', alpha=0.85)
        ax.scatter([position] * len(local), local, s=24, color='#ff7f0e', alpha=0.85)
        ax.scatter([position + 0.15] * len(chains), chains, s=24,
                   color='#1f77b4', alpha=0.6)
    ax.set_xticks(range(len(stages)))
    ax.set_xticklabels(stages)
    ax.set_ylabel('edges added in the stage (sync difference)')
    ax.set_title('A. edge classes per stage\nred historic links, orange local-only closures, blue chains')
    ax.grid(alpha=0.3, axis='y')
    ax = axes[1]
    counters = defaultdict(int)
    for row in rows:
        try:
            counts = json.loads(row['provenance_counts'])
        except Exception:  # noqa: BLE001
            continue
        for key, value in counts.items():
            counters[key or 'UNKNOWN'] += value
    if counters:
        labels = sorted(counters, key=counters.get, reverse=True)
        ax.bar(range(len(labels)), [counters[label] for label in labels],
               color='#4c72b0')
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels([label.replace('_', '\n') for label in labels], fontsize=7)
        ax.set_ylabel('edges (all runs, all stages)')
        ax.set_title('B. creation provenance of new edges')
        ax.grid(alpha=0.3, axis='y')
    save(fig, figures, 'fig3_mechanism')


# ---------------------------------------------------------------- figure 4
def fig4_zero_vs_effective(analysis, figures):
    metrics = [row for row in read_rows(analysis / 'per_episode_metrics.csv')]
    mechanism = read_rows(analysis / 'action_mechanism.csv')
    if not metrics:
        print('fig4 skipped: no data')
        return
    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    for row in metrics:
        gain = number(row.get('delta_J_action_sync'))
        if gain is None:
            continue
        links = next((number(item['historic_links']) for item in mechanism
                      if item['episode_id'] == row['episode_id']
                      and item['stage'] == 'action'), None)
        if links is None:
            continue
        ax.scatter(links + 0.04 * (hash(row['episode_id']) % 3 - 1), gain,
                   s=40, color=ARM_COLORS.get(row['action'], '#555555'), alpha=0.9)
        ax.annotate('{} {}'.format(row['episode_id'].split('_')[1],
                                   row['action']),
                    (links, gain), fontsize=6.5, xytext=(3, 3),
                    textcoords='offset points')
    ax.axhline(0.0, color='k', linewidth=0.7)
    ax.set_xlabel('historic links created during the action (sync)')
    ax.set_ylabel('action information increment [nats]')
    ax.set_title('zero-gain runs vs effective runs\n(all validated runs, sync dumps)')
    ax.grid(alpha=0.3)
    save(fig, figures, 'fig4_zero_vs_effective')


# ---------------------------------------------------------------- figure 5
def fig5_gt_vs_information(analysis, figures):
    gt = read_rows(analysis / 'corrected_gt_metrics.csv')
    metrics = read_rows(analysis / 'per_episode_metrics.csv')
    cost = read_rows(analysis / 'cost_quality_comparison.csv')
    if not cost:
        print('fig5 skipped: no data')
        return
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.2))
    ax = axes[0]
    for row in cost:
        gain = number(row.get('action_gain_sync'))
        change = number(row.get('robot_gt_error_change_m'))
        if gain is None or change is None:
            continue
        ax.scatter(gain, change, s=36,
                   color=ARM_COLORS.get(row['action'], '#555555'), alpha=0.9)
    ax.axhline(0.0, color='k', linewidth=0.7)
    ax.axvline(0.0, color='k', linewidth=0.7)
    ax.set_xlabel('action information increment [nats]')
    ax.set_ylabel('robot GT error change (tail - return) [m]')
    ax.set_title('A. information gain vs localisation change')
    ax.grid(alpha=0.3)
    ax = axes[1]
    for position, stage in enumerate(('arrival', 'action_done', 'final')):
        stage_key = {'arrival': 'arrival', 'action_done': 'action_done',
                     'final': 'final'}[stage]
        values = [number(row['value']) for row in gt
                  if row['family'] == 'TARGET_MAP_ERROR'
                  and row['stage'] == stage_key and row['metric'] == 'mean_m']
        values = [value for value in values if value is not None]
        if values:
            ax.scatter([position] * len(values), values, s=26, alpha=0.8,
                       color='#1f77b4')
    ax.set_xticks(range(3))
    ax.set_xticklabels(['arrival', 'action done', 'final'])
    ax.set_ylabel('frozen-target map error [m]')
    ax.set_title('B. target-state map error at synchronous boundaries')
    ax.grid(alpha=0.3, axis='y')
    save(fig, figures, 'fig5_gt_vs_information')


# ---------------------------------------------------------------- figure 6
def fig6_decision(analysis, figures):
    comparison = read_rows(analysis / 'place_direction_comparison.csv')
    features = read_rows(analysis / 'pre_action_feature_audit.csv')
    gate = json.loads((Path(analysis) / 'final_gate.json').read_text()) \
        if (Path(analysis) / 'final_gate.json').is_file() else {}
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4))
    ax = axes[0]
    for place in ('place_B', 'place_C'):
        subset = [row for row in comparison
                  if row['place'] == place and row['action'] in ('L+', 'L-')]
        for row in subset:
            values = [number(v) for v in row['action_gain_values'].split(';')
                      if v]
            values = [v for v in values if v is not None]
            x = PLACE_X[place] + (0.0 if row['action'] == 'L+' else 0.2)
            ax.scatter([x] * len(values), values, s=32,
                       color=ARM_COLORS[row['action']], alpha=0.9)
        pair = next((row for row in comparison
                     if row['place'] == place and row['action'] == 'L+_minus_L-'),
                    None)
        if pair and number(pair['action_gain_mean']) is not None:
            ax.scatter([PLACE_X[place] + 0.45], [number(pair['action_gain_mean'])],
                       marker='D', s=48, color='k')
    ax.axhline(0.0, color='k', linewidth=0.7)
    ax.set_xticks([0.1, 1.1])
    ax.set_xticklabels(['place B', 'place C'])
    ax.set_ylabel('action information increment [nats]')
    ax.set_title('A. direction contrast under synchronous observation\n(diamonds: mean L+ - L-)')
    ax.grid(alpha=0.3, axis='y')
    ax = axes[1]
    for row in features:
        gain = number(row.get('action_gain_sync'))
        residual = number(row.get('gate_residual_rad'))
        if gain is None or residual is None:
            continue
        ax.scatter(residual, gain, s=36,
                   color=ARM_COLORS.get(row.get('action'), '#555555'),
                   alpha=0.9)
    ax.set_xlabel('pre-action keyframe-gate residual [rad]')
    ax.set_ylabel('action information increment [nats]')
    ax.set_title('B. one allowed pre-action candidate vs outcome')
    ax.grid(alpha=0.3)
    fig.suptitle('decision evidence: raw values, two runs per condition, no significance claims',
                 fontsize=9)
    save(fig, figures, 'fig6_decision')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite-dir', required=True)
    args = parser.parse_args()
    suite = Path(args.suite_dir).resolve()
    analysis = suite / 'analysis'
    figures = suite / 'figures'
    fig1_topic_vs_sync(analysis, figures)
    fig2_direction_gains(analysis, figures)
    fig3_mechanism(analysis, figures)
    fig4_zero_vs_effective(analysis, figures)
    fig5_gt_vs_information(analysis, figures)
    fig6_decision(analysis, figures)


if __name__ == '__main__':
    main()
