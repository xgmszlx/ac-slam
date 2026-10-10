#!/usr/bin/python3
"""Figures for the continuous revisit action experiment.

Every figure is written twice: a raster preview (PNG) and an editable vector
copy (SVG).  The figure code reads only ``analysis/`` tables produced by
``analysis.py`` plus the recorded run directories, so figures can be rebuilt
offline at any time.
"""

import csv
import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

import analysis as an  # noqa: E402
import protocol as cr  # noqa: E402

ACTION_COLOURS = {'S0': '#4c72b0', 'S1': '#55a868', 'L+': '#c44e52',
                  'L-': '#8172b2'}
PHASE_COLOURS = {'history': '#999999', 'return': '#dd8452',
                 'action': '#c44e52', 'tail': '#55a868'}
PLACE_MARKERS = {'place_A': 'o', 'place_B': 's', 'place_C': '^', 'place_D': 'D'}


def read_table(path):
    path = Path(path)
    if not path.is_file():
        return []
    with path.open() as stream:
        return list(csv.DictReader(stream))


def as_float(value):
    if value in (None, '', 'None'):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def save(fig, out_dir, name):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for extension in ('png', 'svg'):
        fig.savefig(out_dir / '{}.{}'.format(name, extension), dpi=160,
                    bbox_inches='tight')
    plt.close(fig)
    return str(out_dir / name)


def figure_trajectory(suite_dir, out_dir, episode_id=None):
    """Continuity case: one episode's odometric trajectory with all phases."""
    suite_dir = Path(suite_dir)
    state = an.load_json(suite_dir / 'suite_state.json')
    rows = read_table(suite_dir / 'analysis' / 'per_episode_metrics.csv')
    if not rows:
        return None
    chosen = None
    for row in rows:
        if episode_id is None or row['episode_id'] == episode_id:
            chosen = row
            break
    if chosen is None:
        chosen = rows[0]
    run_dir = Path(chosen['run_dir'])
    scans = an.jsonl(run_dir / 'scan_stream.jsonl')
    frozen = an.load_json(run_dir / 'frozen_target.json')
    result = an.load_json(run_dir / 'episode_result.json')
    bounds = an.phase_bounds(result)
    reference = frozen['reference_mapper_pose']

    fig, axes = plt.subplots(1, 2, figsize=(13.5, 6.0),
                             gridspec_kw={'width_ratios': [1.35, 1.0]})
    ax = axes[0]
    for phase, window in bounds.items():
        records = [record for record in scans if an._in_window(record, window)]
        poses = [record['odom_base'] for record in records
                 if record['odom_base'] is not None]
        if not poses:
            continue
        ax.plot([pose[0] for pose in poses], [pose[1] for pose in poses],
                color=PHASE_COLOURS[phase], linewidth=2.0,
                label='{} ({} frames)'.format(phase, len(records)))
    nodes = an.snapshot_graph(an.load_json(run_dir / 'graph_final.json'))['nodes']
    target_ids = {int(state) for state in frozen['target_state_ids']}
    historical = [node for node in nodes if node['state_id'] in target_ids]
    ax.scatter([node['x'] for node in nodes], [node['y'] for node in nodes],
               s=6, color='#cccccc', zorder=1, label='graph states (final)')
    ax.scatter([node['x'] for node in historical],
               [node['y'] for node in historical], s=60, marker='*',
               color='#ff9900', edgecolor='black', zorder=3,
               label='frozen target states')
    ax.scatter([reference[0]], [reference[1]], s=110, marker='X',
               color='black', zorder=4, label='executed arrival pose')
    for node in historical:
        ax.annotate('', xy=(node['x'] + 1.0 * math.cos(node['theta']),
                            node['y'] + 1.0 * math.sin(node['theta'])),
                    xytext=(node['x'], node['y']),
                    arrowprops={'arrowstyle': '->', 'color': '#ff9900',
                                'linewidth': 1.2})
    ax.set_title('Continuous chain, one episode (no stitching)\n{}'.format(
        chosen['episode_id']))
    ax.set_xlabel('map x [m]')
    ax.set_ylabel('map y [m]')
    ax.legend(loc='best', fontsize=8)
    ax.grid(alpha=0.25)

    ax = axes[1]
    for phase, window in bounds.items():
        records = [record for record in scans if an._in_window(record, window)]
        poses = [record['odom_base'] for record in records
                 if record['odom_base'] is not None]
        if not poses:
            continue
        x = [pose[0] - reference[0] for pose in poses]
        y = [pose[1] - reference[1] for pose in poses]
        if phase == 'tail':
            x = x[:12]
            y = y[:12]
        ax.plot(x, y, color=PHASE_COLOURS[phase], linewidth=2.0, label=phase)
    ax.scatter([0.0], [0.0], marker='X', s=110, color='black', zorder=4)
    for node in historical:
        ax.annotate('', xy=(node['x'] - reference[0] + 1.0 * math.cos(node['theta']),
                            node['y'] - reference[1] + 1.0 * math.sin(node['theta'])),
                    xytext=(node['x'] - reference[0], node['y'] - reference[1]),
                    arrowprops={'arrowstyle': '->', 'color': '#ff9900',
                                'linewidth': 1.2})
    # action-phase observation headings (sampled) so the rotation is visible even
    # though an in-place action does not move the trajectory
    action_records = an.slice_records(scans, bounds['action'])
    action_poses = [record['odom_base'] for record in action_records
                    if record['odom_base'] is not None]
    stride = max(1, len(action_poses) // 12)
    for pose in action_poses[::stride]:
        ax.annotate('', xy=(pose[0] - reference[0] + 0.9 * math.cos(pose[2]),
                            pose[1] - reference[1] + 0.9 * math.sin(pose[2])),
                    xytext=(pose[0] - reference[0], pose[1] - reference[1]),
                    arrowprops={'arrowstyle': '->', 'color': '#c44e52',
                                'linewidth': 1.0, 'alpha': 0.8})
    ax.set_aspect('equal')
    ax.set_xlim(-3.0, 3.0)
    ax.set_ylim(-3.0, 3.0)
    ax.set_title('same episode, zoom on the place\n(orange arrows: historical '
                 'target headings)')
    ax.set_xlabel('x - reference [m]')
    ax.set_ylabel('y - reference [m]')
    ax.grid(alpha=0.25)
    ax.legend(loc='best', fontsize=8)
    return save(fig, out_dir, 'fig1_continuous_trajectory')


def figure_information_decomposition(suite_dir, out_dir):
    rows = read_table(Path(suite_dir) / 'analysis' / 'per_episode_metrics.csv')
    rows = [row for row in rows if as_float(row.get('total_gain')) is not None]
    if not rows:
        return None
    rows.sort(key=lambda row: as_float(row['return_gain']) or 0.0)
    x = np.arange(len(rows))
    stages = (('return_gain', 'return leg'), ('action_gain', 'action phase'),
              ('tail_gain', 'tail'))
    fig, axes = plt.subplots(2, 1, figsize=(13.0, 7.6), sharex=True,
                             gridspec_kw={'height_ratios': [2.2, 1.0]})
    ax = axes[0]
    bottom = np.zeros(len(rows))
    positive = np.zeros(len(rows))
    negative = np.zeros(len(rows))
    for key, label in stages:
        values = np.array([as_float(row[key]) or 0.0 for row in rows])
        ax.bar(x, values, bottom=np.where(values >= 0, positive, negative),
               color={'return_gain': '#dd8452', 'action_gain': '#c44e52',
                      'tail_gain': '#55a868'}[key], label=label, width=0.8)
        positive = positive + np.where(values >= 0, values, 0.0)
        negative = negative + np.where(values < 0, values, 0.0)
    ax.axhline(0.0, color='black', linewidth=0.8)
    ax.set_ylabel('J_T gain [nats, 15 dof]')
    ax.set_title('Information gain decomposition per episode '
                 '(ordered by return-leg gain)')
    ax.legend(loc='best', fontsize=8)
    ax.grid(alpha=0.25, axis='y')
    ax = axes[1]
    ax.bar(x, [as_float(row.get('new_heading_fraction')) or 0.0 for row in rows],
           color=[ACTION_COLOURS[row['action_id']] for row in rows], width=0.8)
    ax.set_ylabel('new view fraction')
    ax.set_xlabel('episode (ordered by return-leg gain)')
    ax.set_ylim(0, 1.05)
    ax.grid(alpha=0.25, axis='y')
    ax.set_title('share of action-phase scans whose observation heading is at '
                 'least 15 deg away from every historical target heading')
    return save(fig, out_dir, 'fig2_information_decomposition')


def figure_per_action_gains(suite_dir, out_dir):
    rows = read_table(Path(suite_dir) / 'analysis' / 'within_place_action_comparison.csv')
    if not rows:
        return None
    fig, axes = plt.subplots(1, 3, figsize=(14.5, 5.2), sharey=False)
    panels = (('return_gain', 'return leg'), ('action_gain', 'action phase'),
              ('total_gain', 'total'))
    for ax, (key, label) in zip(axes, panels):
        for place_id in cr.PLACE_IDS:
            for action_id in cr.ACTION_IDS:
                values = [as_float(row[key]) for row in rows
                          if row['place_id'] == place_id
                          and row['action_id'] == action_id]
                values = [value for value in values if value is not None]
                if not values:
                    continue
                offset = (cr.ACTION_IDS.index(action_id) - 1.5) * 0.18
                position = cr.PLACE_IDS.index(place_id) + offset
                ax.scatter([position] * len(values), values,
                           color=ACTION_COLOURS[action_id], s=28,
                           marker=PLACE_MARKERS[place_id], alpha=0.85)
                ax.scatter([position], [float(np.mean(values))], s=90,
                           facecolor='none', edgecolor=ACTION_COLOURS[action_id],
                           linewidth=1.6, zorder=3)
        ax.axhline(0.0, color='black', linewidth=0.8)
        ax.set_xticks(range(len(cr.PLACE_IDS)))
        ax.set_xticklabels(cr.PLACE_IDS)
        ax.set_title('{} J_T gain'.format(label))
        ax.grid(alpha=0.25, axis='y')
    handles = [plt.Line2D([], [], color=ACTION_COLOURS[action_id], marker='o',
                          linestyle='', label=action_id)
               for action_id in cr.ACTION_IDS]
    axes[0].legend(handles=handles, fontsize=8, loc='best')
    axes[0].set_ylabel('J_T gain [nats]')
    fig.suptitle('Stage gains by place and action (circles: per-repeat values, '
                 'rings: place mean)', y=1.02)
    return save(fig, out_dir, 'fig3_place_action_gains')


def figure_differences(suite_dir, out_dir):
    summary = an.load_json(Path(suite_dir) / 'analysis' / 'summary.json', {})
    differences = summary.get('difference_summary', {})
    keys = [key for key in ('L+_L-', 'L+_S1', 'L+_S0', 'S1_S0')
            if key in differences]
    if not keys:
        return None
    rows = read_table(Path(suite_dir) / 'analysis' / 'within_place_action_comparison.csv')
    fig, axes = plt.subplots(1, 2, figsize=(13.0, 5.4))
    ax = axes[0]
    for index, key in enumerate(keys):
        values = differences[key]['action_gain_values']
        ax.scatter([index] * len(values), values, s=34, alpha=0.75,
                   color='#333333', zorder=3)
        if values:
            mean = float(np.mean(values))
            ax.plot([index - 0.28, index + 0.28], [mean, mean],
                    color=ACTION_COLOURS['L+'], linewidth=2.2, zorder=4)
            ax.annotate('{:.3f}'.format(mean), (index + 0.32, mean), fontsize=8,
                        va='center')
    ax.axhline(0.0, color='black', linewidth=0.8)
    ax.set_xticks(range(len(keys)))
    ax.set_xticklabels([key.replace('_', ' - ') for key in keys])
    ax.set_ylabel('action-phase J_T gain difference [nats]')
    ax.set_title('Paired differences inside each place/repeat group\n'
                 '(points: one group of four arms, bar: group mean)')
    ax.grid(alpha=0.25, axis='y')

    ax = axes[1]
    place_index = {place: index for index, place in enumerate(cr.PLACE_IDS)}
    groups = {}
    for row in rows:
        groups.setdefault((row['place_id'], row['repeat']), {})[row['action_id']] = row
    if 'L+_L-' in differences:
        for (place_id, repeat), arms in sorted(groups.items()):
            first, second = arms.get('L+'), arms.get('L-')
            if not first or not second:
                continue
            delta = (as_float(first['action_gain']) or 0.0) - \
                    (as_float(second['action_gain']) or 0.0)
            ax.scatter([place_index[place_id]], [delta],
                       color=ACTION_COLOURS['L+'], s=44,
                       marker=PLACE_MARKERS[place_id])
        ax.axhline(0.0, color='black', linewidth=0.8)
        ax.set_xticks(range(len(cr.PLACE_IDS)))
        ax.set_xticklabels(cr.PLACE_IDS)
        ax.set_ylabel('L+ minus L- action J_T gain [nats]')
        ax.set_title('Direction effect of the large rotation, per place\n'
                     '(markers: place identity, one point per complete group)')
        ax.grid(alpha=0.25, axis='y')
    return save(fig, out_dir, 'fig4_direction_and_contrast')


def figure_constraints(suite_dir, out_dir):
    """Historical constraint endpoints and the observation directions."""
    rows = read_table(Path(suite_dir) / 'analysis' / 'per_episode_metrics.csv')
    rows = [row for row in rows if row.get('run_dir')]
    if not rows:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.8))
    ax = axes[0]
    # target-state positions for every episode, aligned to its arrival pose
    for row in rows:
        run_dir = Path(row['run_dir'])
        frozen = an.load_json(run_dir / 'frozen_target.json')
        reference = frozen['reference_mapper_pose']
        node_stamps = None
        for node in frozen['target_states']:
            ax.scatter([node['x'] - reference[0]], [node['y'] - reference[1]],
                       s=18, color=ACTION_COLOURS[row['action_id']], alpha=0.5,
                       marker=PLACE_MARKERS[row['place_id']])
        ax.scatter([0.0], [0.0], marker='X', s=80, color='black', zorder=4)
    ax.set_aspect('equal')
    ax.set_title('Frozen target states relative to the executed arrival pose\n'
                 '(all places and arms overlaid)')
    ax.set_xlabel('x - arrival [m]')
    ax.set_ylabel('y - arrival [m]')
    ax.grid(alpha=0.25)

    ax = axes[1]
    summary = an.load_json(Path(suite_dir) / 'analysis' / 'summary.json', {})
    view = summary.get('view_summary', {})
    labels, values = [], []
    for action_id in cr.ACTION_IDS:
        if action_id not in view:
            continue
        labels.append(action_id)
        values.append(view[action_id]['new_heading_fraction_mean'] or 0.0)
    if labels:
        ax.bar(labels, values, color=[ACTION_COLOURS[label] for label in labels])
        for index, value in enumerate(values):
            ax.text(index, value + 0.02, '{:.2f}'.format(value), ha='center',
                    fontsize=9)
    ax.set_ylim(0, 1.1)
    ax.set_ylabel('mean new-heading fraction')
    ax.set_title('Share of action-phase scans whose observation heading is new\n'
                 '(>= 15 deg away from every historical target heading)')
    ax.grid(alpha=0.25, axis='y')
    return save(fig, out_dir, 'fig5_historical_constraints')


def figure_information_vs_error(suite_dir, out_dir):
    rows = read_table(Path(suite_dir) / 'analysis' / 'per_episode_metrics.csv')
    if not rows:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(13.0, 5.4))
    panels = (('return_gain', 'G_before_return_target_error_mean_m',
               'G_arrival_target_error_mean_m', 'return leg'),
              ('action_gain', 'G_arrival_target_error_mean_m',
               'G_action_done_target_error_mean_m', 'action phase'))
    for ax, (gain_key, before_key, after_key, label) in zip(axes, panels):
        for action_id in cr.ACTION_IDS:
            gains, deltas = [], []
            for row in rows:
                if row['action_id'] != action_id:
                    continue
                gain = as_float(row.get(gain_key))
                before = as_float(row.get(before_key))
                after = as_float(row.get(after_key))
                if gain is None or before is None or after is None:
                    continue
                gains.append(gain)
                deltas.append(after - before)
            if not gains:
                continue
            ax.scatter(gains, deltas, color=ACTION_COLOURS[action_id], s=34,
                       label=action_id)
        ax.axhline(0.0, color='black', linewidth=0.8)
        ax.set_xlabel('{} J_T gain [nats]'.format(label))
        ax.set_ylabel('change in mean target map error [m]')
        ax.set_title('Graph information vs real target error ({} )'.format(label))
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8, loc='best')
    return save(fig, out_dir, 'fig6_information_vs_error')


def figure_cost(suite_dir, out_dir):
    rows = read_table(Path(suite_dir) / 'analysis' / 'per_episode_metrics.csv')
    if not rows:
        return None
    fig, axes = plt.subplots(1, 3, figsize=(14.0, 4.8))
    panels = (('action_duration_s', 'action-phase duration [s]'),
              ('action_measured_rotation_rad', 'measured rotation [rad]'),
              ('action_gain', 'action-phase J_T gain [nats]'))
    for ax, (key, label) in zip(axes, panels):
        values, labels = [], []
        for action_id in cr.ACTION_IDS:
            arm_values = [as_float(row.get(key)) for row in rows
                          if row['action_id'] == action_id]
            arm_values = [value for value in arm_values if value is not None]
            if not arm_values:
                continue
            values.append(arm_values)
            labels.append(action_id)
        if values:
            ax.boxplot(values, labels=labels, showmeans=True)
            for index, arm_values in enumerate(values):
                ax.scatter([index + 1] * len(arm_values), arm_values, s=18,
                           color='#333333', alpha=0.55, zorder=3)
        ax.set_title(label)
        ax.grid(alpha=0.25, axis='y')
    fig.suptitle('Fixed-budget execution: cost and information per action', y=1.02)
    return save(fig, out_dir, 'fig7_cost_and_information')


def run(suite_dir, out_dir=None):
    suite_dir = Path(suite_dir)
    out_dir = Path(out_dir) if out_dir else suite_dir / 'analysis' / 'figures'
    written = []
    for function in (figure_trajectory, figure_information_decomposition,
                     figure_per_action_gains, figure_differences,
                     figure_constraints, figure_information_vs_error,
                     figure_cost):
        try:
            result = function(suite_dir, out_dir)
            if result is not None:
                written.append(function.__name__)
        except Exception as exc:
            print('figure {} failed: {}: {}'.format(function.__name__,
                                                    type(exc).__name__, exc))
    return written


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('suite_dir')
    parser.add_argument('--out-dir')
    args = parser.parse_args()
    written = run(Path(args.suite_dir), args.out_dir)
    print(json.dumps({'figures': written}, indent=1))


if __name__ == '__main__':
    main()
