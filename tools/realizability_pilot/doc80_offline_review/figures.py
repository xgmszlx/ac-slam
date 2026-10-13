#!/usr/bin/python3
"""Doc-80 figures (offline; matplotlib 3.1-compatible).

fig1_target_gt_correction          corrected vs original target map error
fig2_historical_association_structure   link classes and contributions
fig3_pre_action_directional_visibility  L+/L- swept-sector visibility
fig4_final_research_evidence       decision evidence panels
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
STAGES = ['before_return', 'arrival', 'action_done', 'final']


def read_rows(path):
    with open(path) as handle:
        return list(csv.DictReader(handle))


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def save(fig, figures, name):
    figures = Path(figures)
    figures.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.subplots_adjust(top=0.84)
    fig.savefig(figures / (name + '.png'), dpi=140)
    fig.savefig(figures / (name + '.svg'))
    plt.close(fig)
    print('wrote', name)


def fig1(analysis, figures):
    rows = read_rows(Path(analysis) / 'corrected_target_map_gt.csv')
    comparison = read_rows(Path(analysis) / 'target_gt_original_comparison.csv')
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4))
    ax = axes[0]
    per_run = defaultdict(dict)
    for row in rows:
        if row['status'] != 'EVALUABLE':
            continue
        per_run[row['episode_id']][row['stage']] = number(
            row['map_error_translation_m'])
    for episode, values in sorted(per_run.items()):
        xs = [STAGES.index(stage) for stage in STAGES if stage in values]
        ys = [values[stage] for stage in STAGES if stage in values]
        ax.plot(xs, ys, marker='o', linewidth=1.0, alpha=0.85)
    ax.set_xticks(range(len(STAGES)))
    ax.set_xticklabels(['before\nreturn', 'arrival', 'action\ndone', 'final'])
    ax.set_ylabel('target map error [m]')
    ax.set_title('A. corrected per-target map error\n(each line = one run, sync graphs)')
    ax.grid(alpha=0.3, axis='y')
    ax = axes[1]
    labels, deltas = [], []
    for row in comparison:
        if row['stage'] != 'action_done':
            continue
        labels.append(row['episode_id'].replace('D79_', ''))
        deltas.append(number(row['mean_difference_m']))
    ax.bar(range(len(labels)), deltas, color='#4c72b0')
    ax.axhline(0.0, color='k', linewidth=0.8)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=60, fontsize=7, ha='right')
    ax.set_ylabel('corrected - doc79 [m]')
    ax.set_title('B. difference vs the Doc-79 metric\n(TF-lag band, no stage movement)')
    ax.grid(alpha=0.3, axis='y')
    fig.suptitle('target map GT correction: values are small and do not improve '
                 'with the action', fontsize=9)
    save(fig, figures, 'fig1_target_gt_correction')


def fig2(analysis, figures):
    classes = read_rows(Path(analysis) / 'historical_link_classes.csv')
    contributions = read_rows(Path(analysis) / 'factor_group_contributions.csv')
    counts = defaultdict(lambda: defaultdict(int))
    for row in classes:
        if row['is_chain'] == 'True':
            continue
        counts[row['episode_id']][row['edge_class'][0]] += 1
    contrib = defaultdict(dict)
    for row in contributions:
        for name in ('A', 'B', 'C'):
            value = number(row.get('contribution_class_{}'.format(name)))
            if value is not None:
                contrib[row['episode_id']][name] = max(0.0, value)
    episodes = sorted(counts)
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4))
    ax = axes[0]
    width = 0.26
    for offset, name, color in ((-width, 'A', '#d62728'),
                                (0.0, 'B', '#ff7f0e'),
                                (width, 'C', '#1f77b4')):
        ax.bar([index + offset for index in range(len(episodes))],
               [counts[episode].get(name, 0) for episode in episodes],
               width=width, color=color, label=name)
    ax.set_xticks(range(len(episodes)))
    ax.set_xticklabels([e.replace('D79_', '') for e in episodes],
                       rotation=60, fontsize=7, ha='right')
    ax.set_ylabel('new non-chain edges (action stage)')
    ax.set_title('A. association classes per run\nA first-visit / B return / C action-internal')
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis='y')
    ax = axes[1]
    for offset, name, color in ((-width, 'A', '#d62728'),
                                (0.0, 'B', '#ff7f0e'),
                                (width, 'C', '#1f77b4')):
        ax.bar([index + offset for index in range(len(episodes))],
               [contrib[episode].get(name, 0.0) for episode in episodes],
               width=width, color=color)
    ax.set_xticks(range(len(episodes)))
    ax.set_xticklabels([e.replace('D79_', '') for e in episodes],
                       rotation=60, fontsize=7, ha='right')
    ax.set_ylabel('joint contribution [nats]')
    ax.set_title('B. set-level contribution\nFIXED_LINEARIZATION_FACTOR_DIAGNOSTIC')
    ax.grid(alpha=0.3, axis='y')
    fig.suptitle('historical association structure: gains ride on first-visit links',
                 fontsize=9)
    save(fig, figures, 'fig2_historical_association_structure')


def fig3(analysis, figures):
    features = read_rows(Path(analysis) / 'directional_visibility_features.csv')
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.3))
    ax = axes[0]
    for index, row in enumerate(features):
        plus = int(row['history_visible_Lplus'])
        minus = int(row['history_visible_Lminus'])
        ax.plot([index - 0.18, index + 0.18], [plus, minus], color='0.6',
                linewidth=1.0, zorder=1)
        ax.scatter([index - 0.18], [plus], s=26, color='#d62728', zorder=2)
        ax.scatter([index + 0.18], [minus], s=26, color='#2ca02c', zorder=2)
        ax.annotate(row['action'], (index, max(plus, minus) + 0.6),
                    ha='center', fontsize=7)
    ax.set_xticks(range(len(features)))
    ax.set_xticklabels([r['episode_id'].replace('D79_', '') for r in features],
                       rotation=60, fontsize=7, ha='right')
    ax.set_ylabel('history nodes visible [count]')
    ax.set_title('A. directional historical visibility\n(red swept-L+ / green swept-L-)')
    ax.grid(alpha=0.3, axis='y')
    ax = axes[1]
    for index, row in enumerate(features):
        ax.bar([index - 0.16], [int(row['history_exclusive_Lplus'])], width=0.3,
               color='#d62728')
        ax.bar([index + 0.16], [int(row['history_exclusive_Lminus'])], width=0.3,
               color='#2ca02c')
    ax.set_xticks(range(len(features)))
    ax.set_xticklabels([r['episode_id'].replace('D79_', '') for r in features],
                       rotation=60, fontsize=7, ha='right')
    ax.set_ylabel('exclusive nodes')
    ax.set_title('B. exclusive swept sectors\n(common sector ~pi rad for both)')
    ax.grid(alpha=0.3, axis='y')
    fig.suptitle('pre-action directional visibility: almost all history is visible '
                 'in both directions', fontsize=9)
    save(fig, figures, 'fig3_pre_action_directional_visibility')


def fig4(analysis, figures):
    joined = read_rows(Path(analysis) / 'feature_outcome_join.csv')
    comparison = read_rows(Path(analysis) / 'place_direction_comparison.csv') \
        if (Path(analysis) / 'place_direction_comparison.csv').is_file() else []
    robot = read_rows(Path(analysis) / 'corrected_robot_relative_gt.csv')
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4))
    ax = axes[0]
    for row in joined:
        delta = number(row['visible_delta_frac'])
        gain = number(row['delta_J_action_sync'])
        novelty = number(row['novelty_delta'])
        if delta is None or gain is None:
            continue
        ax.scatter(delta, gain, s=40, color=ARM_COLORS.get(row['action'], '#555'),
                   alpha=0.9)
        ax.annotate(row['episode_id'].replace('D79_', ''),
                    (delta, gain), fontsize=6, xytext=(3, 3),
                    textcoords='offset points')
    ax.set_xlabel('pre-action visibility delta (L+ - L-) [fraction of history]')
    ax.set_ylabel('action information increment [nats]')
    ax.set_title('A. pre-action visibility vs outcome\n(colour = executed direction)')
    ax.grid(alpha=0.3)
    ax = axes[1]
    # recompute per-place direction contrast from the doc-80 stats file
    stats = json.loads((Path(analysis) / 'statistical_corrections.json').read_text())
    per_run = stats['per_run']
    labels = []
    for place in ('place_B', 'place_C'):
        for action in ('L+', 'L-'):
            values = [row['action_gain_sync'] for row in per_run
                      if row['place'] == place and row['action'] == action]
            labels.append('{}\n{}'.format(place.replace('place_', ''),
                                          action))
            ax.scatter([len(labels) - 1] * len(values), values, s=34,
                       color=ARM_COLORS[action], alpha=0.9)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=8)
    ax.axhline(0.0, color='k', linewidth=0.8)
    ax.set_ylabel('action information increment [nats]')
    ax.set_title('B. direction contrast (raw runs)')
    ax.grid(alpha=0.3, axis='y')
    fig.suptitle('decision evidence: no pre-action separation; all pairs favour L+; '
                 'no localisation benefit', fontsize=9)
    save(fig, figures, 'fig4_final_research_evidence')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--suite-dir', required=True)
    args = parser.parse_args()
    suite = Path(args.suite_dir)
    analysis = suite / 'analysis'
    figures = suite / 'figures'
    fig1(analysis, figures)
    fig2(analysis, figures)
    fig3(analysis, figures)
    fig4(analysis, figures)


if __name__ == '__main__':
    main()
