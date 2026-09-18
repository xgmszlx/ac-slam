#!/usr/bin/python3
"""N1-B budget-matched action intervention analysis.

Produces the artefacts the direction gate needs:

* ``edge_measurement_ledger.csv`` - SE(2) relative measurement and 3x3
  covariance per graph constraint, with the instrument that produced it
  (provenance record when the instrument was enabled, corrected-pose
  reconstruction otherwise) plus provenance, creation order and phase flags.
* ``posterior_uncertainty_ablation.csv`` - gauge-anchored posterior marginals
  for three information-matrix builds (all constraints / target-removed /
  history-removed) over the frozen target segment, the current pose, the
  historical region and the new scans.
* ``graph_utility_ablation.csv`` - per-constraint D-opt of the 3x3 information
  matrix by attribution group, plus the graph-level D-opt of each build.
* ``n1_matched_action_blocks.csv`` - per-block action comparison against the
  block's own baseline action, including measured cost and cost-normalised
  effects.
* ``n1_effect_summary.json`` - the frozen-threshold comparison.

All numbers are read-only analyses of recorded episodes.
"""

import argparse
import csv
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

import edge_analytics  # noqa: E402
import n0_analysis  # noqa: E402
import se2_information  # noqa: E402

ABLATION_VARIANTS = ('all_constraints', 'target_removed', 'history_removed')
METRIC_GROUPS = ('target_segment', 'current_pose', 'historical_region',
                 'history_all', 'new_scan_region')

# Thresholds frozen from N0 (instrument-validity block) before any intervention
# outcome was analysed.  Values are filled by ``freeze_thresholds``.
DEFAULT_THRESHOLD_FILENAME = 'effect_threshold_preregistration.json'


def write_csv(path, rows, fields=None):
    rows = list(rows)
    if not rows:
        with open(path, 'w') as stream:
            stream.write('')
        return
    if not fields:
        fields = []
        for row in rows:
            for key in row:
                if key not in fields:
                    fields.append(key)
    with open(path, 'w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def measurement_ledger_rows(record):
    """One row per graph constraint of the episode (both phases)."""
    run_dir = record['run_dir']
    rows = []
    rows.extend(edge_analytics.measurement_rows(record['provenance_constraints']))
    for row in rows:
        row['measurement_source'] = 'PROVENANCE_RELATIVE_MEAN'
    reconstructed = edge_analytics.reconstructed_measurements(
        record['after_edges'], record['after_nodes'])
    for row in reconstructed:
        row['measurement_source'] = 'RECONSTRUCTED_FROM_CORRECTED_POSES'
    if not rows:
        rows = reconstructed
    else:
        covered = {(row['source_state_id'], row['target_state_id']) for row in rows}
        for row in reconstructed:
            if (row['source_state_id'], row['target_state_id']) not in covered:
                rows.append(row)
    frozen = record['frozen']
    target_ids = set(int(value) for value in frozen['historical_scan_ids'])
    history_ids = record['history_ids']
    freeze_max = int(record['result']['before_max_scan_id'])
    for row in rows:
        source = int(row['source_state_id'])
        target = int(row['target_state_id'])
        pair = {source, target}
        if pair & target_ids and not pair <= target_ids:
            row['attribution'] = 'target_attributable'
        elif pair & history_ids and not pair <= history_ids:
            row['attribution'] = 'history_touching'
        else:
            row['attribution'] = 'local_or_history_internal'
        row['probe_phase'] = bool(source > freeze_max or target > freeze_max)
        row['episode_id'] = record['spec']['episode_id']
        row['condition_id'] = record['spec']['condition_id']
        row['target_id'] = record['spec']['target_id']
        row['run_dir'] = str(run_dir)
        row['instrument'] = ('provenance_enabled' if record['spec'].get(
            'provenance_enabled', True) else 'provenance_disabled')
    return rows


def information_builds(record):
    """Build the three information matrices used by both ablations."""
    node_ids = sorted(record['after_nodes'])
    edges = record['after_edges']
    groups = record['groups']
    target_pairs = [(edge['start'], edge['end'])
                    for edge in groups['target_attributable']]
    history_pairs = [(edge['start'], edge['end'])
                     for edge in groups['target_attributable']]
    history_pairs += [(edge['start'], edge['end'])
                      for edge in groups['history_touching']]
    builds = {}
    for variant in ABLATION_VARIANTS:
        excluded = ()
        if variant == 'target_removed':
            excluded = target_pairs
        elif variant == 'history_removed':
            excluded = history_pairs
        information, contributors, rejected = se2_information.build_information(
            node_ids, edges, excluded_pairs=excluded)
        marginal, nullity, _eigenvalues = se2_information.pseudoinverse_information(
            information)
        builds[variant] = {
            'node_ids': node_ids,
            'information': information,
            'marginal': marginal,
            'contributors': contributors,
            'rejected': rejected,
            'nullity': nullity,
            'excluded_edge_count': len(excluded),
        }
    return builds


def metric_positions(record, node_ids):
    """Position index sets (in ``node_ids`` order) of each metric group."""
    index_of = {node_id: position for position, node_id in enumerate(node_ids)}
    frozen = record['frozen']
    target_ids = [int(value) for value in frozen['historical_scan_ids']
                  if int(value) in index_of]
    history_all = [int(value) for value in sorted(record['history_ids'])
                   if int(value) in index_of]
    historical_region = [value for value in history_all if value not in set(target_ids)]
    freeze_max = int(record['result']['before_max_scan_id'])
    new_scan = [int(value) for value in sorted(index_of) if int(value) > freeze_max]
    groups = {
        'target_segment': target_ids,
        'historical_region': historical_region,
        'history_all': history_all,
        'new_scan_region': new_scan,
        'current_pose': ([int(max(index_of))] if index_of else []),
    }
    return {name: [index_of[value] for value in values]
            for name, values in groups.items() if values}


def posterior_rows(record):
    builds = information_builds(record)
    node_ids = builds['all_constraints']['node_ids']
    positions = metric_positions(record, node_ids)
    rows = []
    for variant in ABLATION_VARIANTS:
        build = builds[variant]
        for group, group_positions in sorted(positions.items()):
            metrics = se2_information.group_block_metrics(
                build['marginal'], group_positions)
            rows.append({
                'episode_id': record['spec']['episode_id'],
                'condition_id': record['spec']['condition_id'],
                'target_id': record['spec']['target_id'],
                'block_id': record['spec'].get('block_id'),
                'variant': variant,
                'group': group,
                'node_count': metrics['node_count'],
                'trace_mean': metrics['trace_mean'],
                'trace_median': metrics['trace_median'],
                'trace_max': metrics['trace_max'],
                'logdet_mean': metrics['logdet_mean'],
                'logdet_sum': metrics['logdet_sum'],
                'all_finite': metrics['all_finite'],
                'all_psd': metrics['all_psd'],
                'information_contributors': build['contributors'],
                'information_nullity': build['nullity'],
                'excluded_edge_count': build['excluded_edge_count'],
                'graph_d_opt': se2_information.d_opt(build['information']),
            })
    return rows


def prepare_record(run_dir):
    """Load one episode attempt with everything the N1 analyses need."""
    return n0_analysis.episode_record({'run_dir': Path(run_dir)})


def graph_utility_rows(record):
    """Per-constraint D-opt of the 3x3 information matrix, by attribution."""
    frozen = record['frozen']
    target_ids = set(int(value) for value in frozen['historical_scan_ids'])
    history_ids = record['history_ids']
    freeze_max = int(record['result']['before_max_scan_id'])
    groups = record['groups']
    buckets = {
        'target_attributable': groups['target_attributable'],
        'history_touching': groups['history_touching'],
        'local': groups['local'],
    }
    rows = []
    for name, edges in buckets.items():
        for edge in edges:
            covariance = edge_analytics.covariance_from_upper_triangle(
                edge['covariance_upper_triangle'])
            rows.append({
                'episode_id': record['spec']['episode_id'],
                'condition_id': record['spec']['condition_id'],
                'target_id': record['spec']['target_id'],
                'block_id': record['spec'].get('block_id'),
                'edge_index': edge['index'],
                'source': edge['start'],
                'target': edge['end'],
                'attribution': name,
                'constraint_d_opt': se2_information.constraint_d_opt(covariance),
                'cov_trace': float(np.trace(covariance)),
                'touches_target': bool({edge['start'], edge['end']} & target_ids),
                'touches_history': bool({edge['start'], edge['end']} & history_ids),
                'endpoint_max': max(edge['start'], edge['end']),
                'post_freeze': bool(max(edge['start'], edge['end']) > freeze_max),
            })
    return rows


def insertion_rows(record):
    """Insertion-time non-locality metrics for every probe-phase constraint."""
    groups = record['groups']
    probe_edges = [edge for group in ('target_attributable', 'history_touching',
                                      'local') for edge in groups[group]]
    pairs = [(edge['start'], edge['end']) for edge in probe_edges]
    metrics = edge_analytics.insertion_time_metrics(
        record['after_edges'], record['after_nodes'], pairs)
    before_degrees = edge_analytics.local_degrees(
        record['before_edges'], record['frozen']['historical_scan_ids'])
    after_degrees = edge_analytics.local_degrees(
        record['after_edges'], record['frozen']['historical_scan_ids'])
    rows = []
    for edge in probe_edges:
        pair = tuple(sorted((edge['start'], edge['end'])))
        entry = metrics.get(pair, {})
        attribution = 'target_attributable'
        if edge in groups['history_touching']:
            attribution = 'history_touching'
        elif edge in groups['local']:
            attribution = 'local'
        rows.append({
            'episode_id': record['spec']['episode_id'],
            'condition_id': record['spec']['condition_id'],
            'target_id': record['spec']['target_id'],
            'block_id': record['spec'].get('block_id'),
            'edge_index': edge['index'],
            'source': edge['start'],
            'target': edge['end'],
            'attribution': attribution,
            'geodesic_at_insertion_m': entry.get('geodesic_m'),
            'hops_at_insertion': entry.get('hops'),
            'euclidean_m': math.hypot(
                record['after_nodes'][edge['end']]['x']
                - record['after_nodes'][edge['start']]['x'],
                record['after_nodes'][edge['end']]['y']
                - record['after_nodes'][edge['start']]['y']),
        })
    return rows, {'before_degrees': before_degrees, 'after_degrees': after_degrees}


def budget_row(record):
    result = record['result']
    signature = record['signature']
    groups = record['groups']
    probe_edges = sum(len(groups[name]) for name in ('target_attributable',
                                                     'history_touching', 'local'))
    probe_gt = result.get('actual_probe_trajectory_gt') or []
    return {
        'episode_id': record['spec']['episode_id'],
        'condition_id': record['spec']['condition_id'],
        'action_id': record['spec'].get('action_id'),
        'target_id': record['spec']['target_id'],
        'block_id': record['spec'].get('block_id'),
        'tsp_seed': record['spec'].get('tsp_seed'),
        'maneuver_type': record['spec'].get('maneuver_type'),
        'probe_distance_m': float(result['actual_probe_distance_m']),
        'probe_duration_s': float(result['probe_end_time'] - result['probe_start_time']),
        'probe_gt_samples': len(probe_gt),
        'new_keyscans': len(result['new_keyscan_ids']),
        'new_keyscans_near_target': len(result['near_target_keyscan_ids']),
        'new_edges_total': probe_edges,
        'new_edges_target': len(groups['target_attributable']),
        'new_edges_history': len(groups['history_touching']),
        'new_edges_local': len(groups['local']),
        'preprobe_nodes': int(signature['node_count']),
        'preprobe_edges': int(signature['edge_count']),
        'preprobe_target_segment_size': int(signature['target_segment_size']),
        'backend_events_target': len(result['target_match_events']),
        'explicit_loop_acceptances_target': len(result['target_constraint_events']),
        'analysis_eligible': bool(result['analysis_eligible']),
    }


def aggregate(rows, key_fields, value_fields):
    grouped = {}
    for row in rows:
        key = tuple(row[field] for field in key_fields)
        grouped.setdefault(key, []).append(row)
    out = []
    for key, members in sorted(grouped.items(), key=lambda item: str(item[0])):
        entry = dict(zip(key_fields, key))
        entry['count'] = len(members)
        for field in value_fields:
            values = [row[field] for row in members if row[field] is not None]
            if not values:
                entry[field] = None
                continue
            ordered = sorted(float(value) for value in values)
            entry[field] = sum(ordered) / len(ordered)
            entry['{}_min'.format(field)] = ordered[0]
            entry['{}_max'.format(field)] = ordered[-1]
        out.append(entry)
    return out


def freeze_thresholds(n0_suite_dir, n1_suite_dir, out_path):
    """Freeze effect thresholds from N0 repeatability before N1 was analysed."""
    _state, blocks = n0_analysis.load_block_records(n0_suite_dir)
    outcomes = n0_analysis.outcome_tables(blocks)
    thresholds = {
        'frozen_before_n1_outcome_inspection': True,
        'source': {
            'n0_suite_dir': str(n0_suite_dir),
            'n0_blocks': len(blocks),
            'n1_suite_dir': str(n1_suite_dir) if n1_suite_dir else None,
        },
        'derivation': (
            'MDE = max(numerical tolerance, 2x measured same-input '
            'repeatability). Repeatability is the mean absolute deviation of an '
            'outcome across the N0 arms, which execute the identical frozen '
            'route and baseline probe and differ only in which observation '
            'instrument is enabled. Counts use absolute integers; '
            'scale-dependent quantities use relative deviation.'),
        'multiplier': 2.0,
        'outcomes': {},
    }
    count_outcomes = ('target_attributable_edges', 'history_touching_edges',
                      'local_edges', 'total_new_edges', 'final_node_count',
                      'final_edge_count', 'loop_events_during_probe')
    continuous_outcomes = ('probe_distance_m', 'probe_duration_s')
    for name, by_arm in sorted(outcomes.items()):
        values = [float(value) for seed_values in by_arm.values()
                  for value in seed_values.values()]
        if not values:
            continue
        if name in count_outcomes:
            mad = n0_analysis.mean_absolute_deviation(values) or 0.0
            thresholds['outcomes'][name] = {
                'kind': 'count',
                'measured_values': values,
                'repeatability_mad': mad,
                'numerical_tolerance': 0.0,
                'mde': max(1.0 if max(values) <= 4 else 0.0, 2.0 * mad),
                'mde_units': 'constraints',
            }
        elif name in continuous_outcomes:
            mad = n0_analysis.mean_absolute_deviation(values) or 0.0
            centre = sum(values) / len(values)
            thresholds['outcomes'][name] = {
                'kind': 'continuous',
                'measured_values': values,
                'repeatability_mad': mad,
                'relative_repeatability': mad / centre if centre else None,
                'numerical_tolerance': 1e-6 * max(abs(centre), 1.0),
                'mde': max(1e-6 * max(abs(centre), 1.0), 2.0 * mad),
                'mde_units': 'physical units',
            }
    # Posterior-uncertainty and graph-utility thresholds are expressed
    # relatively, because their absolute scale depends on the graph size.
    thresholds['outcomes']['target_ablation_dopt_impact_relative'] = {
        'kind': 'relative',
        'numerical_tolerance': 1e-6,
        'mde': 0.05,
        'mde_units': ('change in the target-attributable share of the graph-level '
                      'D-opt, relative to the block baseline graph D-opt'),
    }
    thresholds['outcomes']['target_ablation_trace_impact_relative'] = {
        'kind': 'relative',
        'numerical_tolerance': 1e-6,
        'mde': 0.05,
        'mde_units': ('change in the target-attributable uncertainty reduction, '
                      'relative to the block baseline target-segment trace'),
    }
    thresholds['outcomes']['target_marginal_trace_relative'] = {
        'kind': 'relative',
        'numerical_tolerance': 1e-6,
        'mde': 0.05,
        'mde_units': 'relative change vs the block baseline action',
    }
    with open(out_path, 'w') as stream:
        json.dump(thresholds, stream, indent=2, sort_keys=True, default=str)
        stream.write('\n')
    return thresholds


def block_gate_status(blocks):
    """Evaluate the pre-probe comparability gate inside every block.

    A block whose pre-probe graphs are not comparable is marked
    INVALID_FOR_CAUSAL_PAIR: its action contrast cannot be attributed to the
    action, so it is reported and excluded instead of being silently averaged in.
    """
    status = {}
    for block_id, block in sorted(blocks.items()):
        arms = sorted(block['arms'])
        if len(arms) < 2:
            status[block_id] = {
                'status': 'INCOMPLETE_BLOCK',
                'passed': False,
                'arms_present': arms,
                'failed_pairs': [],
            }
            continue
        failed = []
        for index, arm_a in enumerate(arms):
            for arm_b in arms[index + 1:]:
                record_a = block['arms'][arm_a]
                record_b = block['arms'][arm_b]
                deviations = n0_analysis.route_anchor_deviations(
                    record_a['before_nodes'], record_b['before_nodes'],
                    [record_a['result']['frozen_target']['target_reference']])
                gate = n0_analysis.compare_signatures(
                    record_a['signature'], record_b['signature'], deviations)
                if not gate['passed']:
                    failed.append({'arms': [arm_a, arm_b],
                                   'failed_checks': gate['failed_checks'],
                                   'observed': gate['observed']})
        status[block_id] = {
            'status': ('COMPARABLE' if not failed
                       else 'INVALID_FOR_CAUSAL_PAIR'),
            'passed': not failed,
            'target_id': block['arms'][arms[0]]['spec']['target_id'],
            'seed': block['seed'],
            'arms_present': arms,
            'failed_pairs': failed,
        }
    return status


def episode_metrics(record):
    """Action-relevant metrics of one episode, all from recorded artefacts.

    The posterior numbers come from the gauge-anchored linearised information
    build.  Two kinds of quantity are reported:

    * absolute values of the full-constraint build (`graph_d_opt_all`,
      `target_trace_all`), which describe the graph as it is;
    * ablation *impacts* (`target_ablation_dopt_impact`,
      `target_ablation_trace_impact`), which describe how much the
      target-attributable constraints themselves contribute to information
      (positive) and to uncertainty reduction (positive).  A constraint that
      merely duplicates an already short cycle moves the absolute value much
      less than one that closes a long non-local cycle, which is exactly the
      distinction this round has to make.
    """
    budget = budget_row(record)
    posterior = {(row['variant'], row['group']): row for row in posterior_rows(record)}
    insertion, _degrees = insertion_rows(record)
    target_edges = [row for row in insertion
                    if row['attribution'] == 'target_attributable']

    def value(variant, group, field):
        entry = posterior.get((variant, group))
        return None if entry is None else entry.get(field)

    graph_d_opt_all = value('all_constraints', 'target_segment', 'graph_d_opt')
    graph_d_opt_no_target = value('target_removed', 'target_segment', 'graph_d_opt')
    target_trace_all = value('all_constraints', 'target_segment', 'trace_mean')
    target_trace_no_target = value('target_removed', 'target_segment', 'trace_mean')
    current_trace_all = value('all_constraints', 'current_pose', 'trace_mean')
    history_trace_all = value('all_constraints', 'historical_region', 'trace_mean')
    target_logdet_all = value('all_constraints', 'target_segment', 'logdet_mean')
    target_logdet_no_target = value('target_removed', 'target_segment', 'logdet_mean')

    def geodesic_mean(rows_list):
        values = [row['geodesic_at_insertion_m'] for row in rows_list
                  if row['geodesic_at_insertion_m'] is not None]
        return (sum(values) / len(values)) if values else None

    def hops_mean(rows_list):
        values = [row['hops_at_insertion'] for row in rows_list
                  if row['hops_at_insertion'] is not None]
        return (sum(values) / len(values)) if values else None

    def attribution_sum(rows_list, field):
        return sum(row[field] for row in rows_list if row.get(field) is not None)

    utility_rows = graph_utility_rows(record)
    target_d_opt_sum = attribution_sum(
        [row for row in utility_rows if row['attribution'] == 'target_attributable'],
        'constraint_d_opt')

    metrics = dict(budget)
    metrics.update({
        'target_edges': budget['new_edges_target'],
        'target_geodesic_mean_m': geodesic_mean(target_edges),
        'target_geodesic_max_m': (max(
            [row['geodesic_at_insertion_m'] for row in target_edges
             if row['geodesic_at_insertion_m'] is not None], default=None)),
        'target_hops_mean': hops_mean(target_edges),
        'target_constraint_d_opt_sum': target_d_opt_sum,
        'graph_d_opt_all': graph_d_opt_all,
        'graph_d_opt_no_target': graph_d_opt_no_target,
        'target_ablation_dopt_impact': (
            None if graph_d_opt_all is None or graph_d_opt_no_target is None
            else graph_d_opt_all - graph_d_opt_no_target),
        'target_trace_all': target_trace_all,
        'target_trace_no_target': target_trace_no_target,
        'target_ablation_trace_impact': (
            None if target_trace_all is None or target_trace_no_target is None
            else target_trace_no_target - target_trace_all),
        'target_logdet_all': target_logdet_all,
        'target_logdet_no_target': target_logdet_no_target,
        'target_ablation_logdet_impact': (
            None if target_logdet_all is None or target_logdet_no_target is None
            else target_logdet_no_target - target_logdet_all),
        'current_pose_trace_all': current_trace_all,
        'historical_region_trace_all': history_trace_all,
    })
    return metrics


def episode_deltas(records, threshold_path=None, gate_status=None):
    """Compare each action against its own block's baseline action."""
    by_block = {}
    for record in records:
        by_block.setdefault(record['spec']['block_id'], {})[record['spec'][
            'condition_id']] = record
    rows = []
    for block_id, arms in sorted(by_block.items()):
        baseline = arms.get('n1_a0_baseline')
        if baseline is None:
            continue
        baseline_metrics = episode_metrics(baseline)
        for condition_id, record in sorted(arms.items()):
            metrics = episode_metrics(record)
            extra_distance = (metrics['probe_distance_m']
                              - baseline_metrics['probe_distance_m'])
            extra_time = (metrics['probe_duration_s']
                          - baseline_metrics['probe_duration_s'])
            extra_keyscans = (metrics['new_keyscans']
                              - baseline_metrics['new_keyscans'])
            target_edges_delta = (metrics['target_edges']
                                  - baseline_metrics['target_edges'])

            def delta(field):
                left = metrics.get(field)
                right = baseline_metrics.get(field)
                if left is None or right is None:
                    return None
                return left - right

            def relative(field, denominator_field=None):
                left = metrics.get(field)
                base = baseline_metrics.get(field)
                if left is None or base is None:
                    return None
                if denominator_field:
                    base_scale = baseline_metrics.get(denominator_field)
                else:
                    base_scale = base
                if not base_scale:
                    return None
                return (left - base) / abs(base_scale)

            def per_cost(field, cost):
                difference = delta(field)
                if difference is None or not cost:
                    return None
                return difference / cost

            target_trace_reduction = None
            base_target_trace_reduction = None
            if metrics['target_trace_all'] is not None \
                    and metrics['target_trace_no_target'] is not None:
                target_trace_reduction = (metrics['target_trace_no_target']
                                          - metrics['target_trace_all'])
            if baseline_metrics['target_trace_all'] is not None \
                    and baseline_metrics['target_trace_no_target'] is not None:
                base_target_trace_reduction = (
                    baseline_metrics['target_trace_no_target']
                    - baseline_metrics['target_trace_all'])
            rows.append({
                'block_id': block_id,
                'target_id': metrics['target_id'],
                'tsp_seed': metrics['tsp_seed'],
                'condition_id': condition_id,
                'is_baseline': condition_id == 'n1_a0_baseline',
                'preprobe_gate_passed': (
                    True if gate_status is None
                    else bool(gate_status.get(block_id, {}).get('passed'))),
                'probe_distance_m': metrics['probe_distance_m'],
                'probe_duration_s': metrics['probe_duration_s'],
                'extra_distance_vs_baseline_m': extra_distance,
                'extra_time_vs_baseline_s': extra_time,
                'extra_keyscans_vs_baseline': extra_keyscans,
                'target_edges': metrics['target_edges'],
                'target_edges_delta': target_edges_delta,
                'local_edges': metrics['new_edges_local'],
                'local_edges_delta': delta('new_edges_local'),
                'target_geodesic_mean_m': metrics['target_geodesic_mean_m'],
                'target_geodesic_delta_m': delta('target_geodesic_mean_m'),
                'target_hops_mean': metrics['target_hops_mean'],
                'target_hops_delta': delta('target_hops_mean'),
                'graph_d_opt_all': metrics['graph_d_opt_all'],
                'graph_d_opt_all_relative': relative('graph_d_opt_all'),
                'target_ablation_dopt_impact': metrics[
                    'target_ablation_dopt_impact'],
                'target_ablation_dopt_impact_delta': delta(
                    'target_ablation_dopt_impact'),
                'target_ablation_dopt_impact_relative': relative(
                    'target_ablation_dopt_impact', 'graph_d_opt_all'),
                'target_ablation_trace_impact': metrics[
                    'target_ablation_trace_impact'],
                'target_ablation_trace_impact_delta': (
                    None if target_trace_reduction is None
                    or base_target_trace_reduction is None
                    else target_trace_reduction - base_target_trace_reduction),
                'target_ablation_trace_impact_relative': (
                    None if target_trace_reduction is None
                    or base_target_trace_reduction is None
                    or not baseline_metrics['target_trace_all']
                    else (target_trace_reduction - base_target_trace_reduction)
                    / abs(baseline_metrics['target_trace_all'])),
                'target_ablation_logdet_impact': metrics[
                    'target_ablation_logdet_impact'],
                'target_trace_all': metrics['target_trace_all'],
                'target_trace_all_relative': relative('target_trace_all'),
                'target_trace_relative': relative('target_trace_all'),
                'current_pose_trace_all': metrics['current_pose_trace_all'],
                'current_pose_trace_delta': delta('current_pose_trace_all'),
                'target_edges_per_extra_m': (
                    None if not extra_distance else target_edges_delta
                    / extra_distance),
                'target_ablation_dopt_impact_per_extra_m': per_cost(
                    'target_ablation_dopt_impact', extra_distance),
                'target_ablation_trace_impact_per_extra_m': per_cost(
                    'target_ablation_trace_impact', extra_distance),
                'target_ablation_dopt_impact_per_extra_s': per_cost(
                    'target_ablation_dopt_impact', extra_time),
                'target_ablation_trace_impact_per_extra_s': per_cost(
                    'target_ablation_trace_impact', extra_time),
                'graph_d_opt_delta_per_extra_m': per_cost(
                    'graph_d_opt_all', extra_distance),
                'graph_d_opt_delta_per_extra_s': per_cost(
                    'graph_d_opt_all', extra_time),
                'trace_reduction_per_extra_m': (
                    None if target_trace_reduction is None
                    or base_target_trace_reduction is None or not extra_distance
                    else (target_trace_reduction - base_target_trace_reduction)
                    / extra_distance),
                'analysis_eligible': metrics['analysis_eligible'],
            })
    return rows


def effect_summary(rows, thresholds=None, gate_status=None):
    """Aggregate the paired block deltas per action and target."""
    rows = [row for row in rows if row.get('preprobe_gate_passed', True)]
    summary = {'actions': {}, 'targets': {}, 'eligibility': {}}
    for condition_id in ('n1_a1_neutral', 'n1_a2_sweep90'):
        members = [row for row in rows if row['condition_id'] == condition_id]
        entry = {'block_count': len(members)}
        for field in ('extra_distance_vs_baseline_m', 'extra_time_vs_baseline_s',
                      'extra_keyscans_vs_baseline', 'target_edges_delta',
                      'target_geodesic_delta_m', 'target_hops_delta',
                      'target_ablation_dopt_impact_relative',
                      'target_ablation_dopt_impact_delta',
                      'target_ablation_trace_impact_delta',
                      'target_ablation_trace_impact_relative',
                      'target_trace_all_relative',
                      'target_ablation_dopt_impact_per_extra_m',
                      'target_ablation_trace_impact_per_extra_m'):
            values = [float(row[field]) for row in members
                      if row.get(field) is not None]
            entry[field] = {
                'count': len(values),
                'mean': (sum(values) / len(values)) if values else None,
                'min': min(values) if values else None,
                'max': max(values) if values else None,
                'values': values,
            }
        summary['actions'][condition_id] = entry
    for target_id in sorted({row['target_id'] for row in rows}):
        summary['targets'][target_id] = {}
        for condition_id in ('n1_a1_neutral', 'n1_a2_sweep90'):
            members = [row for row in rows if row['condition_id'] == condition_id
                       and row['target_id'] == target_id]
            summary['targets'][target_id][condition_id] = {
                'block_count': len(members),
                'target_edges_delta': [row['target_edges_delta'] for row in members],
                'target_ablation_dopt_impact_relative': [
                    row['target_ablation_dopt_impact_relative'] for row in members],
                'target_ablation_trace_impact_delta': [
                    row['target_ablation_trace_impact_delta'] for row in members],
                'target_ablation_trace_impact_relative': [
                    row['target_ablation_trace_impact_relative'] for row in members],
                'target_trace_all_relative': [
                    row['target_trace_all_relative'] for row in members],
            }
    if thresholds:
        summary['thresholds'] = thresholds
    if gate_status is not None:
        summary['preprobe_gate'] = gate_status
        summary['blocks_usable'] = sorted(
            block_id for block_id, entry in gate_status.items() if entry['passed'])
        summary['blocks_invalid'] = sorted(
            block_id for block_id, entry in gate_status.items()
            if not entry['passed'])
    return summary


def analyze_suite(suite_dir, out_dir=None, threshold_path=None):
    suite_dir = Path(suite_dir)
    out_dir = Path(out_dir) if out_dir else suite_dir
    _state, blocks = n0_analysis.load_block_records(suite_dir)
    all_records = [record for block in blocks.values()
                   for record in block['arms'].values()]
    all_records.sort(key=lambda record: record['spec']['episode_id'])
    eligible = [record for record in all_records
                if record['result'].get('analysis_eligible')]
    excluded = [
        {'episode_id': record['spec']['episode_id'],
         'reason': record['result'].get('exclusion_reason'),
         'history_contaminated_by_closure': record['result'].get(
             'history_contaminated_by_closure'),
         'condition_id': record['spec']['condition_id'],
         'block_id': record['spec'].get('block_id')}
        for record in all_records if record not in eligible]
    ledger = [row for record in all_records for row in measurement_ledger_rows(record)]
    posterior = [row for record in all_records for row in posterior_rows(record)]
    utility = [row for record in all_records for row in graph_utility_rows(record)]
    insertion = []
    for record in all_records:
        rows, _degrees = insertion_rows(record)
        insertion.extend(rows)
    budgets = [budget_row(record) for record in all_records]
    gate_status = block_gate_status(
        {block_id: block for block_id, block in blocks.items()
         if all(record['result'].get('analysis_eligible')
                for record in block['arms'].values())})
    deltas = episode_deltas(eligible, gate_status=gate_status)
    thresholds = None
    if threshold_path and Path(threshold_path).is_file():
        thresholds = edge_analytics.load_json(threshold_path)
    summary = effect_summary(deltas, thresholds, gate_status)
    summary['excluded_episodes'] = excluded
    summary['episode_counts'] = {
        'observed': len(all_records),
        'eligible': len(eligible),
        'excluded': len(excluded),
    }
    os.makedirs(out_dir, exist_ok=True)
    write_csv(out_dir / 'edge_measurement_ledger.csv', ledger)
    write_csv(out_dir / 'posterior_uncertainty_ablation.csv', posterior)
    write_csv(out_dir / 'graph_utility_ablation.csv', utility)
    write_csv(out_dir / 'insertion_nonlocality.csv', insertion)
    write_csv(out_dir / 'action_budget_rows.csv', budgets)
    write_csv(out_dir / 'n1_matched_action_blocks.csv', deltas)
    write_csv(out_dir / 'preprobe_pair_validation.csv',
              n0_analysis.build_pairs_rows(blocks))
    with open(out_dir / 'n1_effect_summary.json', 'w') as stream:
        json.dump(summary, stream, indent=2, sort_keys=True, default=str)
        stream.write('\n')
    return summary


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    freeze = sub.add_parser('freeze-thresholds')
    freeze.add_argument('--n0-suite', required=True)
    freeze.add_argument('--n1-suite')
    freeze.add_argument('--out', required=True)
    analyze = sub.add_parser('analyze')
    analyze.add_argument('--suite-dir', required=True)
    analyze.add_argument('--out')
    analyze.add_argument('--thresholds')
    args = parser.parse_args()
    if args.command == 'freeze-thresholds':
        thresholds = freeze_thresholds(args.n0_suite, args.n1_suite, args.out)
        print(json.dumps({'out': args.out,
                          'outcomes': sorted(thresholds['outcomes'])},
                         indent=2, sort_keys=True))
        return
    summary = analyze_suite(args.suite_dir, args.out, args.thresholds)
    print(json.dumps({'actions': {name: {
        'extra_distance_vs_baseline_m': entry[
            'extra_distance_vs_baseline_m']['mean'],
        'extra_keyscans_vs_baseline': entry[
            'extra_keyscans_vs_baseline']['mean'],
        'target_edges_delta': entry['target_edges_delta']['mean'],
        'target_ablation_dopt_impact_relative': entry[
            'target_ablation_dopt_impact_relative']['mean'],
        'target_ablation_trace_impact_delta': entry[
            'target_ablation_trace_impact_delta']['mean'],
    } for name, entry in summary['actions'].items()},
        'episode_counts': summary.get('episode_counts'),
        'blocks_usable': summary.get('blocks_usable'),
        'blocks_invalid': summary.get('blocks_invalid')},
        indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
