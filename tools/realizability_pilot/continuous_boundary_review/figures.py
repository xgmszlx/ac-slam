#!/usr/bin/python3
"""Review figures for doc 78 - one figure per research question.

1. ``fig1_boundary_coverage``   Did every snapshot contain the graph state the
                                stage actually had accepted?
2. ``fig2_gain_mechanism``      Where do the stage gains come from, and what
                                changes when attribution follows creation time?
3. ``fig3_statistics``          How do the run-to-run statistics change under the
                                corrected estimator?
4. ``fig4_ground_truth``        Did any action change the real localisation error?
5. ``fig5_timeline_case``       How did the boundary timing mis-assign the 0016
                                return-leg closures to the action stage?
6. ``fig6_diagnostic_bounds``   Upper bound (labelled diagnostic) of the impact
                                of the never-published keyframes.

Run after ``review.py`` (same ``--out`` directory).
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

ARM_COLORS = {'S0': '#7f7f7f', 'S1': '#1f77b4', 'L+': '#d62728', 'L-': '#2ca02c'}
BOUNDARY_ORDER = ['G_before_return', 'G_arrival', 'G_action_done', 'G_final']


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
def fig1_boundary_coverage(out_dir, root):
    audit = read_rows(Path(root) / 'boundary_event_audit.csv')
    recover = read_rows(Path(root) / 'recoverability_matrix.csv')
    main_runs = sorted({row['episode_id'] for row in audit if row['suite_round'] == 'main'})
    missing = defaultdict(list)
    for row in recover:
        if row['suite_round'] != 'main':
            continue
        missing[row['episode_id']].append(row)
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.2))
    # panel A: never-published keyframes per run, stacked by accept stage
    ax = axes[0]
    stages = ['history', 'return', 'action']
    colors = {'history': '#bbbbbb', 'return': '#1f77b4', 'action': '#d62728'}
    xs = range(len(main_runs))
    bottoms = [0] * len(main_runs)
    for stage in stages:
        heights = [sum(1 for item in missing.get(episode, [])
                       if item['stage_by_time'] == stage) for episode in main_runs]
        ax.bar(xs, heights, bottom=bottoms, width=0.75, color=colors[stage],
               label='accepted in ' + stage)
        bottoms = [bottom + height for bottom, height in zip(bottoms, heights)]
    arm_of = {}
    for row in audit:
        arm_of[row['episode_id']] = row['action_id']
    labels = ['{}\n{}'.format(episode.split('_')[0], arm_of.get(episode, ''))
              for episode in main_runs]
    ax.set_xticks(list(xs))
    ax.set_xticklabels(labels, fontsize=4.5, rotation=90)
    ax.set_ylabel('never-published keyframes')
    ax.set_title('A. keyframes absent from every snapshot (48 main runs)')
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3, axis='y')
    # panel B: content lag per boundary, flagged when the stage motion already ended
    ax = axes[1]
    for position, boundary in enumerate(BOUNDARY_ORDER):
        lags = [number(row['content_lag_s']) for row in audit
                if row['boundary'] == boundary and row['suite_round'] == 'main']
        lags = [lag for lag in lags if lag is not None]
        flagged = [number(row['content_lag_s']) for row in audit
                   if row['boundary'] == boundary and row['suite_round'] == 'main'
                   and row['content_before_stage_motion_end'] == 'True']
        flagged = [lag for lag in flagged if lag is not None]
        ax.scatter([position] * len(lags), lags, s=12, alpha=0.45, color='#444444')
        ax.scatter([position + 0.25] * len(flagged), flagged, s=14, alpha=0.8,
                   color='#d62728', marker='x')
    ax.set_xticks([position + 0.12 for position in range(len(BOUNDARY_ORDER))])
    ax.set_xticklabels(['before\nreturn', 'arrival', 'action\ndone', 'final'])
    ax.set_ylabel('snapshot time - graph content time  [s]')
    ax.set_title('B. publication lag of each boundary snapshot\n'
                 'red x: content predates the stage motion end')
    ax.grid(alpha=0.3, axis='y')
    save(fig, out_dir, 'fig1_boundary_coverage')


# ---------------------------------------------------------------- figure 2
def fig2_gain_mechanism(out_dir, root, mechanism_rows):
    attribution = read_rows(Path(root) / 'stage_attribution_correction.csv')
    main = [row for row in attribution if row['suite_round'] == 'main']
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4))
    ax = axes[0]
    for row in main:
        arm = row['action_id']
        created = number(row['created_action_increment'])
        closures = number(row['created_action_effective_closures'])
        if created is None or closures is None:
            continue
        ax.scatter(closures + 0.06 * (hash(row['episode_id']) % 3 - 1), created,
                   s=26, alpha=0.85, color=ARM_COLORS.get(arm, 'k'),
                   label=arm if arm not in ax.get_legend_handles_labels()[1] else None)
    ax.axhline(0.0, color='k', linewidth=0.7)
    ax.set_xlabel('effective closure edges created during the action (accepted-time)')
    ax.set_ylabel('created action increment [nats]')
    ax.set_title('A. action information only exists when the action\n'
                 'itself creates an effective closure edge')
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)
    # panel B: dumbbell of recorded vs created action gain
    ax = axes[1]
    ordered = sorted(main, key=lambda row: number(row['created_action_increment']) or 0.0)
    ys = range(len(ordered))
    for y, row in zip(ys, ordered):
        recorded = number(row['recorded_action_gain']) or 0.0
        created = number(row['created_action_increment']) or 0.0
        arm = row['action_id']
        ax.plot([recorded, created], [y, y], color=ARM_COLORS.get(arm, 'k'),
                marker='o', markersize=3, linewidth=0.9, alpha=0.85)
    ax.axvline(0.0, color='k', linewidth=0.7)
    ax.set_yticks([])
    ax.set_xlabel('action-stage gain [nats]')
    ax.set_title('B. recorded (left end) vs created-time (right end)\n'
                 'action gain per main run, sorted by created value')
    ax.grid(alpha=0.3, axis='x')
    save(fig, out_dir, 'fig2_gain_mechanism')


# ---------------------------------------------------------------- figure 3
def fig3_statistics(out_dir, root):
    summary = read_rows(Path(root) / 'statistical_correction.csv')
    configs = ['0003_place_A_r1_L+', '0004_place_A_r1_L-',
               '0016_place_B_r1_L+', '0013_place_B_r1_L-']
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 4.2))
    # panel A: triplets with old and new spread estimates
    ax = axes[0]
    for position, config in enumerate(configs):
        row = next((item for item in summary
                    if item['row_type'] == 'REPEATABILITY_CONFIG'
                    and item['config'] == config), None)
        if not row:
            continue
        values = [float(value) for value in row['values'].split(';')]
        ax.scatter([position] * len(values), values, s=28,
                   color=ARM_COLORS.get(config[-2:], '#333333'), zorder=3)
        ax.plot([position - 0.22, position - 0.22], [0, number(row['sd_ddof0']) * 3],
                color='#888888', linewidth=2)
        ax.plot([position + 0.22, position + 0.22], [0, number(row['sd_ddof1']) * 3],
                color='#d62728', linewidth=2)
    ax.set_xticks(range(len(configs)))
    ax.set_xticklabels([config.split('_')[1] + '\n' + config.split('_')[-1]
                        for config in configs], fontsize=8)
    ax.set_ylabel('action_gain [nats]')
    ax.set_title('A. same-configuration triplets\nbars: 3x spread, grey=old ddof0, red=new ddof1')
    ax.grid(alpha=0.3, axis='y')
    # panel B: arm means, recorded vs created
    ax = axes[1]
    arms = ['S0', 'S1', 'L+', 'L-']
    width = 0.35
    recorded, created = {}, {}
    for row in summary:
        if row['row_type'] == 'ARM_ATTRIBUTION' and row['config'] == 'main':
            recorded[row['action_id']] = row['values']
            created[row['action_id']] = number(row['mean'])
    def recorded_mean(arm):
        detail = recorded.get(arm, '')
        try:
            part = detail.split('recorded mean ')[1].split(' ')[0]
            return float(part)
        except (IndexError, ValueError):
            return 0.0
    ax.bar([index - width / 2 for index in range(len(arms))],
           [recorded_mean(arm) for arm in arms], width,
           color='#999999', label='recorded (snapshot difference)')
    ax.bar([index + width / 2 for index in range(len(arms))],
           [created.get(arm, 0.0) for arm in arms], width,
           color='#d62728', alpha=0.8, label='created-time attribution (diagnostic)')
    ax.set_xticks(range(len(arms)))
    ax.set_xticklabels(arms)
    ax.set_ylabel('mean action gain [nats], 12 main runs per arm')
    ax.set_title('B. arm means before/after attribution correction\n'
                 'grey dashed: same-configuration re-execution sd 0.127')
    pooled = next((number(row['sd_ddof1']) for row in summary
                   if row['row_type'] == 'POOLED_SD_RECONCILIATION'), None)
    if pooled:
        ax.axhline(pooled, color='#555555', linestyle='--', linewidth=1)
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3, axis='y')
    # panel C: paired L+ - L- contrasts, recorded vs corrected
    ax = axes[2]
    gains = {}
    for row in read_rows(Path(root) / 'gain_recomputation.csv'):
        gains[row['episode_id']] = number(row['action_gain_recomputed'])
    corrected = {}
    spec = {}
    for row in read_rows(Path(root) / 'stage_attribution_correction.csv'):
        if row['suite_round'] != 'main':
            continue
        corrected[row['episode_id']] = number(row['created_action_increment'])
        spec[(row['place_id'], row['repeat'], row['action_id'])] = row['episode_id']
    recorded_diffs, created_diffs = [], []
    for (place, repeat, arm) in sorted(spec):
        if arm != 'L+':
            continue
        plus = spec[(place, repeat, 'L+')]
        minus = spec.get((place, repeat, 'L-'))
        if minus is None or gains.get(plus) is None or gains.get(minus) is None \
                or corrected.get(plus) is None or corrected.get(minus) is None:
            continue
        recorded_diffs.append(gains[plus] - gains[minus])
        created_diffs.append(corrected[plus] - corrected[minus])
    positions = [0, 1]
    for values, position, color in ((recorded_diffs, 0, '#999999'),
                                    (created_diffs, 1, '#d62728')):
        ax.scatter([position] * len(values), values, s=26, color=color, alpha=0.9,
                   zorder=3)
        ax.plot([position - 0.18, position + 0.18],
                [sum(values) / len(values)] * 2, color='k', linewidth=1.6)
    ax.axhline(0.0, color='k', linewidth=0.7)
    ax.set_xticks(positions)
    ax.set_xticklabels(['recorded', 'created-time\n(diagnostic)'], fontsize=8)
    ax.set_ylabel('paired L+ minus L- [nats]')
    ax.set_title('C. the direction contrast collapses\nunder creation-time attribution')
    ax.grid(alpha=0.3, axis='y')
    save(fig, out_dir, 'fig3_statistics')


# ---------------------------------------------------------------- figure 4
def fig4_ground_truth(out_dir, root):
    gt = read_rows(Path(root) / 'corrected_gt_metrics.csv')
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 4.0))
    # panel A: target error change final - before
    per_run = defaultdict(dict)
    for row in gt:
        if row['family'] == 'TARGET_MAP_ERROR' and row['metric'] == 'mean_m' \
                and row['suite_round'] == 'main':
            per_run[row['episode_id']][row['stage']] = number(row['value'])
    changes = [values['final'] - values['before_return'] for values in per_run.values()
               if 'final' in values and 'before_return' in values
               and values['final'] is not None and values['before_return'] is not None]
    ax = axes[0]
    ax.hist(changes, bins=25, color='#1f77b4', alpha=0.8)
    ax.axvline(0.0, color='k', linewidth=0.8)
    ax.set_xlabel('target map error change, final - before  [m]')
    ax.set_ylabel('main runs')
    ax.set_title('A. target-state map error does not improve\n(mean {:+.2e} m)'.format(
        sum(changes) / len(changes) if changes else float('nan')))
    ax.grid(alpha=0.3)
    # panel B: robot SLAM error by stage
    ax = axes[1]
    stages = ['history', 'return', 'action', 'tail']
    data = {stage: [] for stage in stages}
    for row in gt:
        if row['family'] == 'ROBOT_LOCALIZATION_ERROR' and row['metric'] == 'mean_m' \
                and row['suite_round'] == 'main' and row['stage'] in data:
            value = number(row['value'])
            if value is not None:
                data[row['stage']].append(value)
    for position, stage in enumerate(stages):
        values = data[stage]
        ax.boxplot(values, positions=[position], widths=0.5, showfliers=False)
        ax.scatter([position] * len(values), values, s=6, alpha=0.4, color='#d62728')
    ax.set_xticks(range(len(stages)))
    ax.set_xticklabels(stages)
    ax.set_ylabel('SLAM map pose vs GT error [m]')
    ax.set_title('B. robot localisation error per stage\n(no improvement through the action)')
    ax.grid(alpha=0.3, axis='y')
    # panel C: relative pose error during the action
    ax = axes[2]
    translation, heading = [], []
    for row in gt:
        if row['family'] == 'RELATIVE_POSE_ERROR' and row['suite_round'] == 'main':
            value = number(row['value'])
            if value is None:
                continue
            (translation if row['metric'] == 'translation_mean_m' else heading).append(value)
    ax.scatter(translation, heading, s=22, alpha=0.75, color='#2ca02c')
    ax.set_xlabel('robot-to-anchor distance error [m]')
    ax.set_ylabel('robot-to-anchor heading error [rad]')
    ax.set_title('C. relative pose error during the action\n(median {:.3f} m / {:.3f} rad)'.format(
        sorted(translation)[len(translation) // 2] if translation else float('nan'),
        sorted(heading)[len(heading) // 2] if heading else float('nan')))
    ax.grid(alpha=0.3)
    save(fig, out_dir, 'fig4_ground_truth')


# ---------------------------------------------------------------- figure 5
def fig5_timeline_case(out_dir, root, episode='0016_place_B_r1_L+'):
    audit = [row for row in read_rows(Path(root) / 'boundary_event_audit.csv')
             if row['episode_id'] == episode]
    recover = [row for row in read_rows(Path(root) / 'recoverability_matrix.csv')
               if row['episode_id'] == episode]
    mechanism = [row for row in read_rows(Path(root) / 'historical_factor_mechanism.csv')
                 if row['episode_id'] == episode]
    attribution = [row for row in read_rows(Path(root) / 'stage_attribution_correction.csv')
                   if row['episode_id'] == episode]
    if not audit or not attribution:
        print('figure 5 skipped: no rows for', episode)
        return
    fig, ax = plt.subplots(figsize=(11.5, 4.2))
    # stage spans from the audit's stage motion end times are not enough; use the
    # recorded marks through the mechanism rows' detail JSON
    times = {}
    for row in audit:
        if row['boundary'] == 'G_arrival':
            times['arrival_content'] = number(row['content_time_ros'])
            times['arrival_snapshot'] = number(row['snapshot_time_ros'])
            times['return_motion_end'] = number(row['stage_motion_end_time'])
        if row['boundary'] == 'G_action_done':
            times['action_content'] = number(row['content_time_ros'])
            times['action_snapshot'] = number(row['snapshot_time_ros'])
            times['action_motion_end'] = number(row['stage_motion_end_time'])
        if row['boundary'] == 'G_final':
            times['final_content'] = number(row['content_time_ros'])
            times['final_snapshot'] = number(row['snapshot_time_ros'])
    # accepted states from the recoverability table: missing ones are explicit
    missing = {row['state_id']: row for row in recover}
    span_start = times.get('arrival_content') or 320.0
    span_end = times.get('final_snapshot') or 366.0
    ax.axhspan(0.02, 0.14, xmin=0.0, xmax=1.0, color='#f2f2f2', zorder=0)
    # motion window as a thick line on the time axis
    for label, color in (('return_motion_end', '#1f77b4'),):
        value = times.get(label)
        if value:
            ax.annotate('return motion end\n{:.1f}s'.format(value), (value, 0.18),
                        fontsize=7, color=color, ha='center')
            ax.plot([value, value], [0.02, 0.14], color=color, linewidth=2)
    for label, color, text in (('action_motion_end', '#d62728', 'action motion end'),
                               ('final_content', '#8c564b', 'last graph message'),
                               ('action_snapshot', '#9467bd', 'action snapshot'),
                               ('final_snapshot', '#7f7f7f', 'final snapshot')):
        value = times.get(label)
        if value:
            ax.plot([value, value], [0.02, 0.14], color=color, linewidth=1.4,
                    linestyle='--')
            vertical = 0.015 if label in ('final_content', 'final_snapshot') else -0.035
            ax.annotate('{}\n{:.1f}s'.format(text, value), (value, vertical),
                        fontsize=7, color=color, ha='center',
                        va='top' if vertical < 0 else 'bottom')
    # keyframes: dots, missing ones red
    mechanism_edges = {}
    for row in mechanism:
        for item in json.loads(row['individual_contributions'] or '[]'):
            mechanism_edges[item['index']] = item
    for state, row in sorted(missing.items(), key=lambda item: item[0]):
        stamp = number(row['accept_sim_time'])
        if stamp is None:
            continue
        color = '#d62728' if row['recoverability_class'].startswith('NEVER_PUBLISHED') else '#2ca02c'
        ax.scatter([stamp], [0.10], s=40, color=color, zorder=3,
                   marker='o' if color == '#d62728' else 's')
        ax.annotate(str(state), (stamp, 0.105), fontsize=6.5, ha='center')
    # closure edges with creation time = later endpoint accept time
    for position, row in enumerate(sorted(mechanism, key=lambda item: item['stage'])):
        for item in json.loads(row['individual_contributions'] or '[]'):
            source_time = min(item['source_accept'] or 0, item['target_accept'] or 0)
            target_time = max(item['source_accept'] or 0, item['target_accept'] or 0)
            level = 0.22 + 0.05 * position
            ax.annotate('', xy=(target_time, level), xytext=(source_time, level),
                        arrowprops={'arrowstyle': '->', 'color': '#d62728', 'lw': 1.4})
            ax.annotate('{}->{} (contrib {:.1e})'.format(
                item['source'], item['target'], item['contribution'] or 0.0),
                ((source_time + target_time) / 2.0, level + 0.012), fontsize=6.5,
                color='#d62728', ha='center')
    ax.set_xlim(span_start - 2.0, span_end + 1.0)
    ax.set_ylim(-0.06, 0.36)
    ax.set_yticks([])
    ax.set_xlabel('simulation time [s]')
    ax.set_title('{} - boundary timing, keyframe acceptance and closure creation'.format(
        episode))
    save(fig, out_dir, 'fig5_timeline_case')


# ---------------------------------------------------------------- figure 6
def fig6_diagnostic_bounds(out_dir, root, mechanism_rows):
    rows = [row for row in mechanism_rows
            if row.get('diagnostic_relevant') == 'True'
            and row.get('diagnostic_delta_jt_worst_case') not in (None, 'None', '')]
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    xs, ys, colors = [], [], []
    for row in rows:
        recorded = number(row['stage_gain_recomputed'])
        diagnostic = number(row['diagnostic_delta_jt_worst_case'])
        if recorded is None or diagnostic is None:
            continue
        xs.append(abs(recorded))
        ys.append(abs(diagnostic))
        colors.append(ARM_COLORS.get(row['action_id'], 'k'))
    ax.scatter(xs, ys, s=26, c=colors, alpha=0.85)
    ax.plot([1e-9, 1.0], [1e-9, 1.0], color='k', linewidth=0.7, linestyle=':')
    ax.set_xscale('log')
    ax.set_yscale('log')
    ax.set_xlabel('|recorded stage gain| of the boundary [nats]')
    ax.set_ylabel('|worst-case missing-keyframe diagnostic| [nats]')
    ax.set_title('FIXED_LINEARIZATION_FACTOR_DIAGNOSTIC upper bound\n'
                 'per run (worst case: one synthetic back closure per missing keyframe)')
    ax.grid(alpha=0.3, which='both')
    save(fig, out_dir, 'fig6_diagnostic_bounds')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True,
                        help='review root (same as review.py --out)')
    args = parser.parse_args()
    root = Path(args.out).resolve()
    figures = root / 'figures'
    mechanism_rows = read_rows(root / 'historical_factor_mechanism.csv')
    fig1_boundary_coverage(figures, root)
    fig2_gain_mechanism(figures, root, mechanism_rows)
    fig3_statistics(figures, root)
    fig4_ground_truth(figures, root)
    fig5_timeline_case(figures, root)
    fig6_diagnostic_bounds(figures, root, mechanism_rows)


if __name__ == '__main__':
    main()
