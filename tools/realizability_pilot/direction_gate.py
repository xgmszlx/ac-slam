#!/usr/bin/python3
"""Two-stage gate for the direction-decision programme.

The programme has two independent decisions and they must never be confused:

**Measurement gate (N0)** - is the observation instrumentation neutral?
    A failure here says nothing about the research hypothesis.  It means the
    measurement infrastructure is not yet certified, so the preregistered
    intervention experiment cannot be interpreted.  The only correct state is
    ``PAUSED_INSTRUMENTATION_NOT_CERTIFIED``.

**Scientific gate (N1)** - does the active observation action deliver more
    *useful* historical constraints than the budget-matched neutral control?
    Only this gate may produce ``PROCEED_TO_MODELING`` or ``STOP_DIRECTION``.

State machine (frozen this round)::

    N0: OUTCOME_MEASUREMENT_STABLE      -> RUN_N1
    N0: INSTRUMENTATION_NOT_NEUTRAL     -> PAUSED_INSTRUMENTATION_NOT_CERTIFIED
    N1: INTERVENTION_SUPPORTED          -> PROCEED_TO_MODELING
    N1: INTERVENTION_NOT_SUPPORTED      -> STOP_DIRECTION
    N1: AMBIGUOUS_SINGLE_BLOCKER        -> INCONCLUSIVE_NEEDS_ONE_MORE_CONTROL

``STOP_DIRECTION`` therefore requires a certified N0 *and* an executed N1 that
fails the preregistered criteria.  A measurement-gate failure can never produce
it.
"""

import argparse
import csv
import json

ACTION_NEUTRAL = 'n1_a1_neutral'
ACTION_SWEEP = 'n1_a2_sweep90'
ACTION_BASELINE = 'n1_a0_baseline'

MEASUREMENT_STABLE = 'OUTCOME_MEASUREMENT_STABLE'

#: states of the frozen state machine
STATE_RUN_N1 = 'RUN_N1'
STATE_PAUSED = 'PAUSED_INSTRUMENTATION_NOT_CERTIFIED'
STATE_PAUSED_REPAIR_FAILED = 'PAUSED_INSTRUMENTATION_REPAIR_FAILED'
STATE_PROCEED = 'PROCEED_TO_MODELING'
STATE_STOP = 'STOP_DIRECTION'
STATE_INCONCLUSIVE = 'INCONCLUSIVE_NEEDS_ONE_MORE_CONTROL'

N0_FAILURE_ACTIONS = [
    'repair the instrumentation so that no serialization or file I/O happens on '
    'the constraint-creation path, then re-run the matched-pair online sanity '
    'check and the same-input replay',
    'certify neutrality with the same-input replay (identical input, '
    'instrumentation off vs on) before executing N1; the N1 design is frozen and '
    'must not be redesigned',
]

N0_INTERPRETATION = (
    'the measurement gate is a property of the instrument, not of the research '
    'hypothesis: N1 has not been executed, so nothing is known yet about whether '
    'the sweep action beats the budget-matched neutral action')


def load_rows(path):
    with open(path) as stream:
        return list(csv.DictReader(stream))


def as_float(value):
    if value in (None, '', 'None'):
        return None
    return float(value)


def series(rows, condition_id, field, target_id=None):
    values = []
    for row in rows:
        if row['condition_id'] != condition_id:
            continue
        if target_id and row['target_id'] != target_id:
            continue
        value = as_float(row.get(field))
        if value is not None:
            values.append(value)
    return values


def mean(values):
    return (sum(values) / len(values)) if values else None


def contrast_by_block(rows, field, condition_id):
    """Same-seed within-block difference against the block baseline action."""
    by_block = {}
    for row in rows:
        by_block.setdefault(row['block_id'], {})[row['condition_id']] = row
    values = []
    for _block_id, arms in sorted(by_block.items()):
        if ACTION_BASELINE not in arms or condition_id not in arms:
            continue
        action = as_float(arms[condition_id].get(field))
        baseline = as_float(arms[ACTION_BASELINE].get(field))
        if action is None or baseline is None:
            continue
        values.append(action - baseline)
    return values


def threshold_for(thresholds, field):
    if not thresholds:
        return None
    outcomes = thresholds.get('outcomes', {})
    if field == 'target_edges' and 'target_attributable_edges' in outcomes:
        return outcomes['target_attributable_edges']['mde']
    if field in ('graph_d_opt_relative', 'target_ablation_dopt_impact_relative'):
        return outcomes.get(field, {}).get('mde')
    if field in ('target_trace_relative', 'target_ablation_trace_impact_relative',
                 'target_marginal_trace_relative'):
        return outcomes.get(field, {}).get('mde')
    return None


def sweep_minus_neutral_by_block(rows, field):
    """Within one block: (sweep - baseline) - (neutral - baseline).

    This is the comparison the programme actually cares about: both actions pay
    a comparable sensing/motion cost, so a difference that survives this
    contrast cannot be explained by extra time, extra motion or extra key scans.
    """
    by_block = {}
    for row in rows:
        by_block.setdefault(row['block_id'], {})[row['condition_id']] = row
    values = []
    for _block_id, arms in sorted(by_block.items()):
        if not all(name in arms for name in (ACTION_BASELINE, ACTION_NEUTRAL,
                                            ACTION_SWEEP)):
            continue

        def value(name, metric):
            return as_float(arms[name].get(metric))

        sweep = value(ACTION_SWEEP, field)
        neutral = value(ACTION_NEUTRAL, field)
        baseline = value(ACTION_BASELINE, field)
        if None in (sweep, neutral, baseline):
            continue
        values.append((sweep - baseline) - (neutral - baseline))
    return values


def measurement_gate(n0_decision):
    """Stage 1: may the intervention experiment be interpreted at all?"""
    outcome = n0_decision.get('outcome')
    if n0_decision.get('state') == STATE_PAUSED_REPAIR_FAILED:
        return {
            'state': STATE_PAUSED_REPAIR_FAILED,
            'certified': False,
            'n0_outcome': outcome,
            'reason': 'the repaired instrumentation still shows a same-direction '
                      'shift in the online sanity check',
            'next_required_action': [
                'inspect the instrumentation implementation again; do not run '
                'N1 and do not interpret any intervention outcome',
            ],
        }
    if outcome == MEASUREMENT_STABLE:
        return {
            'state': STATE_RUN_N1,
            'certified': True,
            'n0_outcome': outcome,
            'reason': 'the instrumentation is neutral for the measured outcomes',
        }
    return {
        'state': STATE_PAUSED,
        'certified': False,
        'n0_outcome': outcome,
        'n0_nonperturbation_outcome': n0_decision.get('nonperturbation_outcome'),
        'n0_preprobe_gate': n0_decision.get('preprobe_gate'),
        'detectable_shifts': n0_decision.get('nonperturbation', {}).get(
            'detectable_shifts'),
        'reason': 'the matched online experiment failed to certify instrumentation '
                  'neutrality (it did not prove a causal perturbation either)',
        'next_required_action': N0_FAILURE_ACTIONS,
        'interpretation': N0_INTERPRETATION,
    }


def _blocks_by_arm(blocks_rows):
    blocks = {}
    for row in blocks_rows:
        blocks.setdefault(row['block_id'], {})[row['condition_id']] = row
    return blocks


def _gate_passed(row):
    value = row.get('preprobe_gate_passed')
    if isinstance(value, str):
        return value.strip().lower() not in ('false', '0', '')
    return bool(value) if value is not None else True


def scientific_gate(blocks_rows, thresholds):
    """Stage 2: after a certified N0, does the sweep action carry its weight?

    The decisive contrast is sweep minus budget-matched neutral inside the same
    block, evaluated on two independent outcome families and normalised by the
    extra cost the sweep actually paid.
    """
    thresholds = thresholds or {}
    edge_threshold = threshold_for(thresholds, 'target_edges') or 1.0
    utility_threshold = threshold_for(
        thresholds, 'target_ablation_dopt_impact_relative') or 0.05
    trace_threshold = threshold_for(
        thresholds, 'target_ablation_trace_impact_relative') or 0.05

    all_rows = list(blocks_rows or [])
    # Only blocks whose pre-probe graphs are comparable may be contrasted; the
    # rest are reported, never used as evidence.
    blocks_rows = [row for row in all_rows if _gate_passed(row)]
    targets = sorted({row['target_id'] for row in all_rows})

    contrast = {
        'edges': sweep_minus_neutral_by_block(blocks_rows, 'target_edges_delta'),
        'uncertainty': sweep_minus_neutral_by_block(
            blocks_rows, 'target_ablation_trace_impact_relative'),
        'utility': sweep_minus_neutral_by_block(
            blocks_rows, 'target_ablation_dopt_impact_relative'),
        'uncertainty_per_m': sweep_minus_neutral_by_block(
            blocks_rows, 'target_ablation_trace_impact_per_extra_m'),
        'utility_per_m': sweep_minus_neutral_by_block(
            blocks_rows, 'target_ablation_dopt_impact_per_extra_m'),
    }
    baseline_gain = {
        'edges': contrast_by_block(blocks_rows, 'target_edges_delta', ACTION_SWEEP),
    }

    criteria = {
        'sweep_gains_target_constraints_over_baseline': {
            'passed': (mean(baseline_gain['edges']) is not None
                       and mean(baseline_gain['edges']) > edge_threshold),
            'observed_mean_delta': mean(baseline_gain['edges']),
            'threshold': edge_threshold,
        },
        'sweep_beats_budget_matched_neutral_on_constraints': {
            'passed': (mean(contrast['edges']) is not None
                       and mean(contrast['edges']) > edge_threshold),
            'observed_mean_contrast': mean(contrast['edges']),
            'per_block': contrast['edges'],
            'threshold': edge_threshold,
        },
        'sweep_beats_neutral_on_uncertainty_per_cost': {
            'passed': (mean(contrast['uncertainty_per_m']) is not None
                       and mean(contrast['uncertainty_per_m']) > 0.0),
            'observed_mean_contrast_per_m': mean(contrast['uncertainty_per_m']),
            'per_block': contrast['uncertainty_per_m'],
            'note': 'outcome family 1: posterior-uncertainty reduction per metre',
        },
        'sweep_beats_neutral_on_utility_per_cost': {
            'passed': (mean(contrast['utility_per_m']) is not None
                       and mean(contrast['utility_per_m']) > 0.0),
            'observed_mean_contrast_per_m': mean(contrast['utility_per_m']),
            'per_block': contrast['utility_per_m'],
            'note': 'outcome family 2: realised graph utility per metre',
        },
    }

    def target_contrast(field, target_id):
        return sweep_minus_neutral_by_block(
            [row for row in blocks_rows if row['target_id'] == target_id], field)

    per_target = {}
    for target_id in targets:
        edges = target_contrast('target_edges_delta', target_id)
        uncertainty = target_contrast(
            'target_ablation_trace_impact_relative', target_id)
        utility = target_contrast(
            'target_ablation_dopt_impact_relative', target_id)
        uncertainty_per_m = target_contrast(
            'target_ablation_trace_impact_per_extra_m', target_id)
        utility_per_m = target_contrast(
            'target_ablation_dopt_impact_per_extra_m', target_id)
        per_target[target_id] = {
            'blocks': len(edges),
            'edge_contrast': edges,
            'edge_contrast_mean': mean(edges),
            'uncertainty_contrast': uncertainty,
            'uncertainty_contrast_mean': mean(uncertainty),
            'utility_contrast': utility,
            'utility_contrast_mean': mean(utility),
            'uncertainty_per_m_contrast': uncertainty_per_m,
            'uncertainty_per_m_contrast_mean': mean(uncertainty_per_m),
            'utility_per_m_contrast': utility_per_m,
            'utility_per_m_contrast_mean': mean(utility_per_m),
            'uncertainty_family_positive': bool(
                mean(uncertainty_per_m) is not None
                and mean(uncertainty_per_m) > 0.0),
            'utility_family_positive': bool(
                mean(utility_per_m) is not None
                and mean(utility_per_m) > 0.0),
        }
    criteria['both_outcome_families_positive_on_both_targets'] = {
        'passed': bool(targets) and all(
            entry['uncertainty_family_positive']
            and entry['utility_family_positive']
            for entry in per_target.values()),
        'per_target': per_target,
    }

    # Interpretation cases from the round specification.
    edges_up_over_baseline = criteria[
        'sweep_gains_target_constraints_over_baseline']['passed']
    edges_equivalent_to_neutral = bool(
        mean(contrast['edges']) is not None
        and abs(mean(contrast['edges'])) <= edge_threshold)
    uncertainty_equivalent_to_neutral = bool(
        mean(contrast['uncertainty']) is not None
        and abs(mean(contrast['uncertainty'])) <= trace_threshold)
    utility_equivalent_to_neutral = bool(
        mean(contrast['utility']) is not None
        and abs(mean(contrast['utility'])) <= utility_threshold)
    case = None
    if edges_up_over_baseline and edges_equivalent_to_neutral:
        # Case 1: the neutral control reaches the same constraint count, so the
        # baseline-to-sweep gain is an extra sensing/motion opportunity effect.
        case = 'CASE_1_EDGE_GAIN_FROM_SENSING_OPPORTUNITY'
    if (edges_up_over_baseline and not edges_equivalent_to_neutral
            and uncertainty_equivalent_to_neutral
            and utility_equivalent_to_neutral
            and not criteria[
                'sweep_beats_neutral_on_uncertainty_per_cost']['passed']
            and not criteria['sweep_beats_neutral_on_utility_per_cost']['passed']):
        # Case 2: the sweep really does create more target constraints than the
        # neutral control, but they buy nothing in either outcome family.
        case = 'CASE_2_EDGE_GAIN_IS_LOCAL_REINFORCEMENT'
    per_target_positive = [entry for entry in per_target.values()
                           if entry['uncertainty_family_positive']
                           and entry['utility_family_positive']]
    if per_target and len(per_target_positive) == len(per_target):
        case = case or 'CASE_3_BOTH_OUTCOME_FAMILIES_FAVOUR_SWEEP'
    elif per_target and 0 < len(per_target_positive) < len(per_target):
        case = 'CASE_4_TARGET_DISAGREEMENT'

    blocker = None
    if case == 'CASE_4_TARGET_DISAGREEMENT':
        dissenting = sorted(target for target, entry in per_target.items()
                            if not (entry['uncertainty_family_positive']
                                    and entry['utility_family_positive']))
        blocker = ('one target does not show the sweep advantage in both outcome '
                   'families: {}'.format(', '.join(dissenting)))
    complete_blocks = [block_id for block_id, arms in
                       _blocks_by_arm(all_rows).items()
                       if all(name in arms for name in
                              (ACTION_BASELINE, ACTION_NEUTRAL, ACTION_SWEEP))]
    rejected = [block_id for block_id in
                {row['block_id'] for row in all_rows}
                if not all(_gate_passed(row) for row in all_rows
                           if row['block_id'] == block_id)]
    block_accounting = {
        'rows': len(all_rows),
        'rows_used': len(blocks_rows),
        'blocks_seen': len({row['block_id'] for row in all_rows}),
        'blocks_with_three_arms': len(complete_blocks),
        'blocks_incomplete': sorted(
            {row['block_id'] for row in all_rows} - set(complete_blocks)),
        'blocks_rejected_by_comparability_gate': sorted(rejected),
        'evaluable_blocks': len(contrast['edges']),
        'targets': targets,
    }
    return {
        'criteria': criteria,
        'contrasts': contrast,
        'case': case,
        'single_remaining_blocker': blocker,
        'block_accounting': block_accounting,
    }


def decide(blocks_rows, thresholds, n0_decision):
    """Full two-stage state machine."""
    blocks_rows = list(blocks_rows or [])
    measurement = measurement_gate(n0_decision)
    if not measurement['certified']:
        return {
            'state': measurement['state'],
            'measurement_gate': measurement,
            'scientific_gate': None,
            'intervention_executed': bool(blocks_rows),
            'reason': measurement['reason'],
            'next_required_action': measurement.get('next_required_action'),
            'interpretation': measurement.get('interpretation'),
        }
    if not blocks_rows:
        return {
            'state': STATE_RUN_N1,
            'measurement_gate': measurement,
            'scientific_gate': None,
            'intervention_executed': False,
            'reason': 'N0 certified the instrumentation; the frozen N1 suite is '
                      'cleared to run and has not been executed yet',
            'next_required_action': [
                'execute results/realizability_pilot/p1_dir_dec_v8_20260916/'
                'n1_blocks/suite_state.json without redesigning it',
            ],
        }

    scientific = scientific_gate(blocks_rows, thresholds)
    criteria = scientific['criteria']
    case = scientific['case']
    accounting = scientific.get('block_accounting') or {}
    if not accounting.get('evaluable_blocks'):
        # No block survived the pre-registered validity and comparability
        # requirements.  That is a statement about the experiment, not about the
        # intervention hypothesis, so the gate must abstain rather than claim a
        # reversal.
        return {
            'state': STATE_INCONCLUSIVE,
            'measurement_gate': measurement,
            'scientific_gate': {
                'criteria': criteria,
                'case': case,
                'single_remaining_blocker': scientific.get(
                    'single_remaining_blocker'),
                'block_accounting': accounting,
            },
            'intervention_executed': True,
            'reason': ('the frozen N1 suite was executed but no block yielded a '
                       'usable sweep-minus-neutral contrast: of {} block(s) '
                       'seen, {} failed the pre-registered pre-probe '
                       'comparability gate and {} lacked at least one required '
                       'arm after the independent ground-truth validity check '
                       'rejected episodes'.format(
                           accounting.get('blocks_seen'),
                           accounting.get('blocks_rejected_by_comparability_'
                                          'gate'),
                           accounting.get('blocks_seen', 0)
                           - accounting.get('blocks_with_three_arms', 0))),
            'next_required_action': [
                'do not read any N1 outcome as evidence about the intervention',
                'the blocking limitation is reproducibility of the mapping '
                'phase (map-frame translation and rotation between runs of the '
                'same route) and navigation accuracy at the probe pose; a '
                'future round needs either a route whose mapping phase is '
                'reproducible within the pre-registered tolerances or a design '
                'that does not require matched pre-probe graphs',
            ],
        }
    per_target = criteria[
        'both_outcome_families_positive_on_both_targets']['per_target']
    both_families = criteria[
        'both_outcome_families_positive_on_both_targets']['passed']
    edges_neutral = criteria[
        'sweep_beats_budget_matched_neutral_on_constraints']['passed']
    uncertainty_per_cost = criteria[
        'sweep_beats_neutral_on_uncertainty_per_cost']['passed']
    utility_per_cost = criteria[
        'sweep_beats_neutral_on_utility_per_cost']['passed']

    if case in ('CASE_1_EDGE_GAIN_FROM_SENSING_OPPORTUNITY',
                'CASE_2_EDGE_GAIN_IS_LOCAL_REINFORCEMENT'):
        state = STATE_STOP
        reason = ('the sweep gains target constraints over the baseline but not '
                  'over the budget-matched neutral control, and neither '
                  'uncertainty reduction per metre nor graph utility per metre '
                  'improves: the gain is a sensing-opportunity or '
                  'local-reinforcement effect')
    elif both_families and (uncertainty_per_cost or utility_per_cost):
        state = STATE_PROCEED
        reason = ('the sweep beats the budget-matched neutral on both targets in '
                  'both independent outcome families, normalised by the extra '
                  'cost it paid')
    elif not edges_neutral and not uncertainty_per_cost and not utility_per_cost:
        state = STATE_STOP
        reason = ('the sweep does not beat the budget-matched neutral on '
                  'constraints, on uncertainty reduction per metre or on graph '
                  'utility per metre')
    elif case == 'CASE_4_TARGET_DISAGREEMENT':
        state = STATE_INCONCLUSIVE
        reason = 'the two targets disagree, so half the picture is missing'
    else:
        state = STATE_INCONCLUSIVE
        reason = ('mixed evidence: at least one preregistered criterion is '
                  'unresolved and the failure is not a clean reversal')
    return {
        'state': state,
        'measurement_gate': measurement,
        'scientific_gate': {
            'criteria': criteria,
            'case': case,
            'single_remaining_blocker': scientific['single_remaining_blocker'],
            'block_accounting': accounting,
        },
        'intervention_executed': True,
        'reason': reason,
        'per_target': per_target,
    }


def evaluate(blocks_rows, thresholds, n0_decision):
    """Backward-compatible alias used by the unit tests and the CLI."""
    return decide(blocks_rows, thresholds, n0_decision)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--blocks',
                        help='n1_matched_action_blocks.csv (absent when the N0 '
                             'gate stopped the round before N1)')
    parser.add_argument('--thresholds', required=True,
                        help='effect_threshold_preregistration.json')
    parser.add_argument('--n0-decision', required=True,
                        help='N0 certification decision, e.g. '
                              'n0_certification_decision_final.json')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    blocks_rows = load_rows(args.blocks) if args.blocks else []
    thresholds = json.load(open(args.thresholds))
    n0_decision = json.load(open(args.n0_decision))
    payload = evaluate(blocks_rows, thresholds, n0_decision)
    payload['inputs'] = {
        'blocks': args.blocks,
        'thresholds': args.thresholds,
        'n0_decision': args.n0_decision,
    }
    with open(args.out, 'w') as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, default=str)
        stream.write('\n')
    print(json.dumps({'state': payload['state'],
                      'reason': payload['reason']}, indent=2))


if __name__ == '__main__':
    main()
