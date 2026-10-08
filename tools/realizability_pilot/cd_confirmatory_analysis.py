#!/usr/bin/python3
"""Frozen post-lock scientific analysis for the CD experiment."""

import argparse
import csv
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

import v14_confirmatory_analysis as legacy
from cd_confirmatory_guard import (
    BACKEND_LOCK, PHYSICAL_LOCK, assert_backend_lock_allows_analysis,
)
from cd_confirmatory_protocol import (
    ARMS, BOOTSTRAP_REPETITIONS, BOOTSTRAP_SEED, PREREGISTRATION_PATH,
    PROTOCOL_ID, RESULT_ROOT, ROOT, TARGETS, frozen_blocks, load_json, sha256,
    source_attempt,
)
from controlled_branch_suite import atomic_json
from common_prefix_analysis import LOCAL_LABEL
from v14_estimator_sanity import estimator_effect_sanity, freeze_world_gauge


DOC_PATH = ROOT / 'docs/research_log/70_context_disentanglement_prospective.md'


def write_csv(path, rows):
    rows = list(rows)
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='') as stream:
        if fields:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)


def analysis_preflight(root=RESULT_ROOT):
    root = Path(root).resolve()
    if root != RESULT_ROOT.resolve():
        raise RuntimeError('CD analysis only accepts frozen result root')
    physical, backend = assert_backend_lock_allows_analysis()
    prereg = load_json(PREREGISTRATION_PATH)
    relative = 'tools/realizability_pilot/cd_confirmatory_analysis.py'
    if prereg['code_hashes'].get(relative) != sha256(Path(__file__)):
        raise RuntimeError('analysis code differs from preregistration')
    return prereg, physical, backend


def target_stratified_interaction_bootstrap(rows):
    by_target = {
        target: [float(row['C_HT']) for row in rows
                 if row['target'] == target]
        for target in TARGETS}
    if any(len(by_target[target]) != 8 for target in TARGETS):
        return None
    rng = random.Random(BOOTSTRAP_SEED)
    values = []
    for _ in range(BOOTSTRAP_REPETITIONS):
        sample_a = [rng.choice(by_target['target_A']) for _ in range(8)]
        sample_b = [rng.choice(by_target['target_B']) for _ in range(8)]
        values.append(float(np.mean(sample_b) - np.mean(sample_a)))
    return {
        'lower_2_5pct': float(np.percentile(values, 2.5)),
        'upper_97_5pct': float(np.percentile(values, 97.5)),
        'mean': float(np.mean(values)),
        'median': float(np.median(values)),
        'standard_deviation': float(np.std(values, ddof=1)),
        'minimum': float(min(values)),
        'maximum': float(max(values)),
        'repetitions': BOOTSTRAP_REPETITIONS,
        'seed': BOOTSTRAP_SEED,
    }


def interaction_point(rows):
    """Compute the preregistered B-minus-A mean paired contrast."""
    means = {}
    for target in TARGETS:
        values = [float(row['C_HT']) for row in rows
                  if row['target'] == target]
        means[target] = float(np.mean(values)) if values else None
    interaction = (means['target_B'] - means['target_A']
                   if all(value is not None for value in means.values())
                   else None)
    return means, interaction


def primary_decision(rows, complete, bootstrap):
    counts = Counter(row['target'] for row in rows)
    sample_complete = bool(
        complete and len(rows) == 16 and
        counts['target_A'] == 8 and counts['target_B'] == 8)
    ci_excludes_zero = bool(
        bootstrap and (bootstrap['lower_2_5pct'] > 0.0 or
                       bootstrap['upper_97_5pct'] < 0.0))
    if not sample_complete:
        gate = 'CD_PROSPECTIVE_TECHNICALLY_INCOMPLETE'
    elif ci_excludes_zero:
        gate = 'CD_PROSPECTIVE_INTERACTION_SUPPORT'
    else:
        gate = 'CD_PROSPECTIVE_NO_INTERACTION_SUPPORT'
    recommendation = {
        'CD_PROSPECTIVE_INTERACTION_SUPPORT':
            'EXPAND_CONTEXT_SET_BEFORE_PREDICTOR',
        'CD_PROSPECTIVE_NO_INTERACTION_SUPPORT':
            'REASSESS_PLAN_A_MECHANISM_AFTER_DOSE_DECONFOUNDING',
        'CD_PROSPECTIVE_TECHNICALLY_INCOMPLETE':
            'STOP_AND_DIAGNOSE_CD_TECHNICAL_FAILURE',
    }[gate]
    return gate, recommendation, {
        'complete_8A_plus_8B': sample_complete,
        'two_sided_95pct_CI_excludes_zero': ci_excludes_zero,
    }


def load_tum_2d(path):
    rows = []
    with open(path) as stream:
        for line in stream:
            if not line.strip():
                continue
            values = [float(value) for value in line.split()]
            rows.append([
                values[0], values[1], values[2],
                2.0 * math.atan2(values[6], values[7])])
    return rows


def gt_block_sanity(block, arm_nodes):
    attempt = source_attempt(block['target_label'], block['seed'])
    slam = load_tum_2d(attempt / 'trajectory_slam.txt')
    gt = load_tum_2d(attempt / 'trajectory_gt.txt')
    gt_by_stamp = {row[0]: row[1:] for row in gt}
    paired = [(row[1:], gt_by_stamp[row[0]]) for row in slam
              if row[0] in gt_by_stamp]
    if len(paired) != len(slam) or len(paired) < 2:
        raise RuntimeError('strict pre-treatment timestamp pairing failed')
    gauge = freeze_world_gauge([row[0] for row in paired],
                               [row[1] for row in paired])
    target_gt = [gt_by_stamp[slam[state_id][0]]
                 for state_id in block['target_state_ids']]
    output = {'gauge': gauge, 'target_gt_poses': target_gt, 'arms': {}}
    before_signatures = []
    for arm in ARMS:
        before_nodes, final_nodes = arm_nodes[arm]
        before_poses = [[before_nodes[state]['x'], before_nodes[state]['y'],
                         before_nodes[state]['theta']]
                        for state in block['target_state_ids']]
        final_poses = [[final_nodes[state]['x'], final_nodes[state]['y'],
                        final_nodes[state]['theta']]
                       for state in block['target_state_ids']]
        before_signatures.append(before_poses)
        output['arms'][arm] = estimator_effect_sanity(
            before_poses, final_poses, target_gt, gauge)
    if any(signature != before_signatures[0]
           for signature in before_signatures[1:]):
        raise RuntimeError('shared pre-treatment estimate differs by arm')
    high = output['arms']['D2_HIGH']
    threshold = output['arms']['D1_THRESHOLD']
    output['GT_HT_translation'] = (
        high['delta_translation_rmse_m'] -
        threshold['delta_translation_rmse_m'])
    output['GT_HT_heading_MAE'] = (
        high['delta_heading_mae_rad'] -
        threshold['delta_heading_mae_rad'])
    output['GT_HT_heading_RMSE'] = (
        high['delta_heading_rmse_rad'] -
        threshold['delta_heading_rmse_rad'])
    return output


def descriptor_table(physical):
    rows = []
    for branch in physical['branches']:
        directory = ROOT / branch['selected_attempt']
        descriptor = load_json(directory / 'pre_treatment_descriptor.json')
        row = {
            'block_id': branch['block_id'],
            'target': branch['target'],
            'seed': branch['seed'],
            'arm': branch['arm'],
            'descriptor_sha256': sha256(
                directory / 'pre_treatment_descriptor.json'),
        }
        for key, value in descriptor.items():
            row[key] = (json.dumps(value, sort_keys=True)
                        if isinstance(value, (dict, list)) else value)
        rows.append(row)
    return rows


def mechanism_tables(metrics, constraints, primary_rows):
    branch_rows = []
    endpoints = {}
    for row in metrics:
        key = '{}:{}'.format(row['block_id'], row['arm'])
        branch_constraints = [item for item in constraints
                              if item['block_id'] == row['block_id'] and
                              item['arm'] == row['arm']]
        historical = [item for item in branch_constraints
                      if item['attribution'] != LOCAL_LABEL]
        pairs = sorted({
            '{}:{}'.format(*sorted((int(item['source_state_id']),
                                    int(item['target_state_id']))))
            for item in historical})
        endpoints[key] = set(pairs)
        branch_rows.append({
            **row,
            'historical_factor_total': row['E_T'] + row['E_N'],
            'historical_endpoint_set': json.dumps(pairs),
        })
    block_rows = []
    primary_by_block = {row['block_id']: row for row in primary_rows}
    grouped = defaultdict(dict)
    for row in branch_rows:
        grouped[row['block_id']][row['arm']] = row
    for block_id, arms in sorted(grouped.items()):
        if not all(arm in arms for arm in ARMS):
            continue
        high = arms['D2_HIGH']
        threshold = arms['D1_THRESHOLD']
        high_set = endpoints['{}:D2_HIGH'.format(block_id)]
        threshold_set = endpoints['{}:D1_THRESHOLD'.format(block_id)]
        block_rows.append({
            'block_id': block_id,
            'target': high['target'],
            'seed': high['seed'],
            'H_HT': (high['historical_factor_total'] -
                     threshold['historical_factor_total']),
            'accepted_keyscan_HT': (high['accepted_keyscans'] -
                                    threshold['accepted_keyscans']),
            'endpoint_novelty_D2_minus_D1': json.dumps(
                sorted(high_set - threshold_set)),
            'endpoint_loss_D2_vs_D1': json.dumps(
                sorted(threshold_set - high_set)),
            'endpoint_novelty_count': len(high_set - threshold_set),
            'endpoint_loss_count': len(threshold_set - high_set),
            'C_HT': primary_by_block[block_id]['C_HT'],
        })
    means = {
        target: float(np.mean([row['H_HT'] for row in block_rows
                               if row['target'] == target]))
        for target in TARGETS}
    if not block_rows:
        means = {target: None for target in TARGETS}
        interaction = None
    else:
        interaction = means['target_B'] - means['target_A']
    primary_interaction = None
    if primary_rows:
        by_target = {
            target: np.mean([row['C_HT'] for row in primary_rows
                             if row['target'] == target])
            for target in TARGETS}
        primary_interaction = float(by_target['target_B'] -
                                    by_target['target_A'])
    concordant = bool(
        interaction is not None and primary_interaction is not None and
        interaction != 0 and primary_interaction != 0 and
        math.copysign(1.0, interaction) ==
        math.copysign(1.0, primary_interaction))
    summary = {
        'H_HT_target_means': means,
        'I_HIST_HT': interaction,
        'I_HT': primary_interaction,
        'direction_label': (
            'MECHANISM_DIRECTION_CONCORDANT' if concordant else
            'MECHANISM_DIRECTION_NOT_CONCORDANT'),
        'causal_mediation_claim': False,
    }
    return branch_rows, block_rows, summary


def render_report(final, physical, backend, primary_rows, secondary,
                  mechanism, gt_status):
    summary = final['primary_summary']
    lines = [
        '# 70 — Prospective context-dose disentanglement experiment', '',
        '## A. Provenance', '',
        '- Protocol: `{}`.'.format(PROTOCOL_ID),
        '- Preregistration SHA256: `{}`.'.format(
            final['preregistration_sha256']),
        '- Prior state remains `V14_PROSPECTIVE_NO_SUPPORT`; '
        '`UNIVERSAL_BROAD_SWEEP_HYPOTHESIS = STOPPED`.',
        '', '## B. Candidate qualification 16+16', '',
        '- The complete frozen candidate ledger is under `qualification/`.',
        '', '## C. Frozen 8A+8B blocks', '',
        '- The first eight technically eligible histories in each frozen '
        'seed order were selected without descriptor or outcome selection.',
        '', '## D. 48 physical branches', '',
        '- Valid branches: {}/48.'.format(physical['valid_branches']),
        '', '## E. Dose manipulation/deconfounding validation', '',
        '- Gate: `{}`.'.format(physical['fresh_manipulation_gate'][
            'machine_label']),
        '', '## F. 48 backend replays', '',
        '- Replayed branches: {}/48.'.format(backend['replayed_branches']),
        '', '## G. Per-block J(D0), J(D1), J(D2)', '',
        '- See `analysis/primary_block_contrasts.csv` for all raw block values.',
        '', '## H. Per-block C_HT', '',
        '- `C_HT = J(D2_HIGH)-J(D1_THRESHOLD)` is reported for all 16 blocks.',
        '', '## I. C_HT_A / C_HT_B', '',
        '- C_HT_A: `{}`.'.format(summary['C_HT_A']),
        '- C_HT_B: `{}`.'.format(summary['C_HT_B']),
        '', '## J. Primary I_HT + 95% CI', '',
        '- I_HT: `{}`.'.format(summary['I_HT']),
        '- Target-stratified bootstrap 95% CI: `[{lower_2_5pct}, '
        '{upper_97_5pct}]`.'.format(**summary['bootstrap']),
        '', '## K. Secondary dose-response', '',
        '- Secondary contrasts are descriptive and cannot rescue the primary '
        'gate. See `analysis/secondary_dose_response.json`.',
        '- Summary: `{}`.'.format(json.dumps(secondary, sort_keys=True)),
        '', '## L. Historical realization mechanism', '',
        '- I_HIST_HT: `{}`.'.format(mechanism['I_HIST_HT']),
        '- Direction label: `{}`.'.format(mechanism['direction_label']),
        '- This is not causal mediation proof.',
        '', '## M. GT sanity', '',
        '- `{}`; GT sanity does not enter the primary gate.'.format(gt_status),
        '', '## N. Final gate', '',
        '- `{}`.'.format(final['final_scientific_gate']),
        '', '## O. Next recommendation', '',
        '- `{}`.'.format(final['next_step_recommendation']),
        '- No predictor, planner integration, backend switch, or automatic '
        'follow-up experiment was started.',
    ]
    if final['final_scientific_gate'] == \
            'CD_PROSPECTIVE_INTERACTION_SUPPORT':
        lines.extend([
            '', 'Permitted interpretation:', '',
            '> Under standardized rotational-action doses, the two '
            'preregistered target contexts exhibit different realized '
            'backend-information responses to the HIGH-versus-THRESHOLD '
            'action contrast.',
            '', 'This does not establish a universal adaptive-dose rule or a '
            'pure-yaw causal effect.',
        ])
    elif final['final_scientific_gate'] == \
            'CD_PROSPECTIVE_NO_INTERACTION_SUPPORT':
        lines.extend([
            '', 'Permitted interpretation:', '',
            '> The previously observed Target-A/Target-B split was not '
            'reproduced after standardizing rotational-action dose.',
        ])
    text = '\n'.join(lines) + '\n'
    report = RESULT_ROOT / 'CD_FINAL_REPORT.md'
    report.write_text(text)
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(text)


def write_technical_incomplete(stage, reason):
    gate = 'CD_PROSPECTIVE_TECHNICALLY_INCOMPLETE'
    recommendation = 'STOP_AND_DIAGNOSE_CD_TECHNICAL_FAILURE'
    final = {
        'status': 'ANALYZED',
        'protocol_id': PROTOCOL_ID,
        'final_scientific_gate': gate,
        'next_step_recommendation': recommendation,
        'incomplete_stage': stage,
        'reason': reason,
        'scientific_endpoint_read': False,
        'automatic_followup_experiment_started': False,
        'prior_scientific_state': 'V14_PROSPECTIVE_NO_SUPPORT',
        'universal_broad_sweep_hypothesis': 'STOPPED',
    }
    decision = RESULT_ROOT / 'decision'
    decision.mkdir(parents=True, exist_ok=True)
    atomic_json(decision / 'final_gate.json', final)
    text = '\n'.join([
        '# 70 — Prospective context-dose disentanglement experiment', '',
        'The experiment stopped at `{}` before a complete scientific sample '
        'was available.'.format(stage), '',
        'Reason: `{}`.'.format(reason), '',
        'Final gate: `{}`.'.format(gate), '',
        'Next recommendation: `{}`.'.format(recommendation), '',
        'No incomplete scientific endpoint was used to alter the protocol.',
    ]) + '\n'
    (RESULT_ROOT / 'CD_FINAL_REPORT.md').write_text(text)
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(text)
    return final


def analyze(root=RESULT_ROOT):
    prereg, physical, backend = analysis_preflight(root)
    out = RESULT_ROOT / 'analysis'
    out.mkdir(parents=True, exist_ok=True)
    replay_rows = {
        '{}:{}'.format(row['block_id'], row['arm']): row
        for row in backend['branches']}
    metrics, constraints, details = [], [], {}
    gt_rows, gt_details = [], {}
    complete = bool(physical.get('complete') and backend.get('complete'))
    for block in frozen_blocks():
        arm_nodes = {}
        for arm in ARMS:
            replay_row = replay_rows.get('{}:{}'.format(
                block['block_id'], arm))
            if not replay_row or replay_row.get('status') != 'REPLAYED':
                complete = False
                continue
            row, detail, constraint_rows, before_nodes, final_nodes = \
                legacy.branch_metrics(block, arm, replay_row)
            metrics.append(row)
            constraints.extend(constraint_rows)
            details['{}:{}'.format(block['block_id'], arm)] = detail
            arm_nodes[arm] = (before_nodes, final_nodes)
        if len(arm_nodes) == 3:
            try:
                gt = gt_block_sanity(block, arm_nodes)
                gt_details[block['block_id']] = gt
                for arm in ARMS:
                    result = gt['arms'][arm]
                    gt_rows.append({
                        'block_id': block['block_id'],
                        'target': block['target_label'],
                        'arm': arm,
                        'translation_rmse_before_m': result['before'][
                            'translation_rmse_m'],
                        'translation_rmse_after_m': result['after'][
                            'translation_rmse_m'],
                        'heading_mae_before_rad': result['before'][
                            'heading_mae_rad'],
                        'heading_mae_after_rad': result['after'][
                            'heading_mae_rad'],
                        'heading_rmse_before_rad': result['before'][
                            'heading_rmse_rad'],
                        'heading_rmse_after_rad': result['after'][
                            'heading_rmse_rad'],
                        'delta_translation_rmse_m': result[
                            'delta_translation_rmse_m'],
                        'delta_heading_mae_rad': result[
                            'delta_heading_mae_rad'],
                        'delta_heading_rmse_rad': result[
                            'delta_heading_rmse_rad'],
                        'GT_HT_translation': gt['GT_HT_translation'],
                        'GT_HT_heading_MAE': gt['GT_HT_heading_MAE'],
                        'GT_HT_heading_RMSE': gt['GT_HT_heading_RMSE'],
                    })
            except Exception as exc:
                gt_details[block['block_id']] = {
                    'status': 'GT_SANITY_UNAVAILABLE',
                    'reason': '{}: {}'.format(type(exc).__name__, exc),
                }
    write_csv(out / 'branch_metrics.csv', metrics)
    write_csv(out / 'constraint_mechanism.csv', constraints)
    atomic_json(out / 'branch_details.json', details)

    grouped = defaultdict(dict)
    for row in metrics:
        grouped[row['block_id']][row['arm']] = row
    primary = []
    for block in frozen_blocks():
        arms = grouped.get(block['block_id'], {})
        if not all(arm in arms for arm in ARMS):
            continue
        d0 = arms['D0_ZERO']['J_T']
        d1 = arms['D1_THRESHOLD']['J_T']
        d2 = arms['D2_HIGH']['J_T']
        primary.append({
            'block_id': block['block_id'],
            'target': block['target_label'],
            'seed': block['seed'],
            'J_D0': d0,
            'J_D1': d1,
            'J_D2': d2,
            'C_HT': d2 - d1,
            'C_T0': d1 - d0,
            'C_H0': d2 - d0,
        })
    write_csv(out / 'primary_block_contrasts.csv', primary)
    by_target = {
        target: [row for row in primary if row['target'] == target]
        for target in TARGETS}
    c_ht_means, interaction = interaction_point(primary)
    bootstrap = target_stratified_interaction_bootstrap(primary)
    gate, recommendation, gate_checks = primary_decision(
        primary, complete, bootstrap)
    primary_summary = {
        'complete_blocks': len(primary),
        'C_HT_A': c_ht_means['target_A'],
        'C_HT_B': c_ht_means['target_B'],
        'I_HT': interaction,
        'bootstrap': bootstrap,
        'gate_checks': gate_checks,
        'raw_C_HT': [{key: row[key] for key in
                      ('block_id', 'target', 'seed', 'C_HT')}
                     for row in primary],
    }
    atomic_json(out / 'primary_interaction_summary.json', primary_summary)

    secondary = {}
    for contrast in ('C_T0', 'C_H0'):
        means = {
            target: float(np.mean([row[contrast]
                                   for row in by_target[target]]))
            for target in TARGETS}
        secondary[contrast] = means
        secondary['I_{}'.format(contrast[2:])] = (
            means['target_B'] - means['target_A'])
    atomic_json(out / 'secondary_dose_response.json', secondary)

    branch_mechanism, block_mechanism, mechanism_summary = mechanism_tables(
        metrics, constraints, primary)
    write_csv(out / 'historical_mechanism_branches.csv', branch_mechanism)
    write_csv(out / 'historical_realization_mechanism.csv', block_mechanism)
    atomic_json(out / 'historical_realization_mechanism_summary.json',
                mechanism_summary)

    gt_status = ('GT_SANITY_AVAILABLE' if len(gt_details) == 16 and
                 all(row.get('status') != 'GT_SANITY_UNAVAILABLE'
                     for row in gt_details.values()) else
                 'GT_SANITY_UNAVAILABLE')
    write_csv(out / 'gt_sanity.csv', gt_rows)
    atomic_json(out / 'gt_sanity_details.json', {
        'status': gt_status,
        'shared_pre_treatment_gauge': True,
        'per_arm_after_realignment': False,
        'blocks': gt_details,
    })
    write_csv(out / 'pre_treatment_descriptors.csv',
              descriptor_table(physical))

    final = {
        'status': 'ANALYZED',
        'protocol_id': PROTOCOL_ID,
        'preregistration_sha256': sha256(PREREGISTRATION_PATH),
        'physical_lock_sha256': sha256(PHYSICAL_LOCK),
        'backend_lock_sha256': sha256(BACKEND_LOCK),
        'statistical_unit': 'canonical-history block',
        'complete_8A_plus_8B_sample': gate_checks[
            'complete_8A_plus_8B'],
        'primary_effect_name': 'CONTEXT_BY_STANDARDIZED_DOSE_INTERACTION',
        'primary_summary': primary_summary,
        'secondary_summary': secondary,
        'mechanism': mechanism_summary,
        'gt_sanity_status': gt_status,
        'final_scientific_gate': gate,
        'next_step_recommendation': recommendation,
        'prior_scientific_state': 'V14_PROSPECTIVE_NO_SUPPORT',
        'universal_broad_sweep_hypothesis': 'STOPPED',
        'automatic_followup_experiment_started': False,
    }
    decision = RESULT_ROOT / 'decision'
    decision.mkdir(parents=True, exist_ok=True)
    atomic_json(decision / 'final_gate.json', final)
    render_report(final, physical, backend, primary, secondary,
                  mechanism_summary, gt_status)
    print(json.dumps(final, indent=2, sort_keys=True))
    return final


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=RESULT_ROOT)
    args = parser.parse_args()
    analyze(args.root)


if __name__ == '__main__':
    main()
