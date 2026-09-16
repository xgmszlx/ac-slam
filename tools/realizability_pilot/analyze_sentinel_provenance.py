#!/usr/bin/python3
"""Create the frozen v7 sentinel constraint-provenance evidence package."""

import argparse
import csv
import json
import shutil
from collections import Counter
from pathlib import Path

from provenance_analysis import (
    classify_constraint, constraint_records, covariance_quality, edge_pair,
    load_jsonl, near_linked_exclusion_evidence, new_full_graph_edges,
    reconcile_full_graph, validate_constraint_records,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_SOURCE = Path(__file__).resolve().parent / 'edge_provenance_schema.json'


SUMMARY_FIELDS = [
    'episode_id', 'condition_id', 'attempt', 'run_dir', 'valid_status',
    'analysis_eligible', 'diagnostics_enabled', 'action_completed',
    'before_node_count', 'after_node_count', 'before_edge_count',
    'after_edge_count', 'new_edge_count', 'n_target_constraints',
    'n_target_explicit_constraints', 'n_target_nonexplicit_constraints',
    'n_wrong_target_constraints', 'n_ordinary_recent_or_sequential_constraints',
    'n_ambiguous_constraints', 'has_target_constraint',
    'has_explicit_target_loop', 'try_close_loop_events',
    'provenance_available', 'provenance_validation_errors',
    'full_graph_provenance_exact_pair_set_match',
    'full_graph_provenance_exact_count_match',
    'slam_path_full_graph_before_equal', 'slam_path_full_graph_after_equal',
    'before_full_graph_age_s', 'after_full_graph_age_s',
    'observer_cut_complete',
    'target_pairs', 'wrong_target_pairs', 'ambiguous_pairs',
    'provenance_counts_new_edges', 'actual_probe_distance_m',
    'probe_duration_s',
]


LEDGER_FIELDS = [
    'episode_id', 'condition_id', 'attempt', 'run_dir', 'edge_index',
    'source_state_id', 'target_state_id', 'source_unique_id',
    'target_unique_id', 'scan_index_gap', 'attribution',
    'target_attributable', 'explicit_try_close_loop', 'nonexplicit_target',
    'creation_provenance', 'creation_function', 'creation_stage',
    'matcher_type', 'match_response', 'match_threshold', 'coarse_response',
    'coarse_threshold', 'relative_mean_x', 'relative_mean_y',
    'relative_mean_yaw', 'covariance_3x3', 'covariance_symmetric',
    'covariance_positive_definite', 'det_covariance', 'det_information',
    'logdet_information', 'source_target_spatial_separation_m',
    'before_or_during_probe', 'solver_add_constraint_called',
    'pre_try_context_observed', 'edge_present_pre_try',
    'source_in_pre_try_near_linked', 'provenance_record_status',
]


def load_json(path):
    return json.loads(Path(path).read_text())


def dump_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def covariance_from_edge(edge):
    values = [float(value) for value in edge['covariance_upper_triangle'].split()]
    if len(values) != 6:
        raise ValueError('expected six upper-triangle covariance values')
    xx, xy, xt, yy, yt, tt = values
    return [[xx, xy, xt], [xy, yy, yt], [xt, yt, tt]]


def selected_attempts(state):
    selected = []
    for episode in state['episodes']:
        attempts = [attempt for attempt in episode.get('attempts', [])
                    if attempt.get('status') == 'SUCCEEDED']
        if attempts:
            selected.append((episode, attempts[-1]))
    return selected


def node_lookup(snapshot):
    return {int(node['id']): node for node in snapshot.get('full_pose_nodes', [])}


def pair_json(pairs):
    return json.dumps([list(pair) for pair in pairs], separators=(',', ':'))


def provenance_json(counter):
    return json.dumps(dict(sorted(counter.items())), sort_keys=True,
                      separators=(',', ':'))


def analyze_episode(suite_dir, episode, attempt):
    run_dir = suite_dir / attempt['run_dir']
    result = load_json(run_dir / 'episode_result.json')
    before = load_json(run_dir / 'pose_graph_before.json')
    after = load_json(run_dir / 'pose_graph_after.json')
    frozen = load_json(run_dir / 'frozen_target.json')
    target_ids = {int(value) for value in frozen['historical_scan_ids']}
    target_unique_ids = {int(value) for value in
                         (frozen.get('historical_unique_ids') or [])}
    before_max = int(result['before_max_scan_id'])
    new_edges = new_full_graph_edges(before, after)
    records = []
    provenance_path = run_dir / 'karto_edge_provenance.jsonl'
    provenance_available = provenance_path.is_file()
    validation_errors = []
    reconciliation = None
    provenance_by_pair = {}
    if provenance_available:
        records = load_jsonl(provenance_path)
        validation_errors = validate_constraint_records(records)
        reconciliation = reconcile_full_graph(after, records)
        provenance_by_pair = {
            tuple(record['canonical_edge_identity']): record
            for record in constraint_records(records)
        }

    explicit_event_pairs = {
        (int(event['historical_scan']), int(event['current_scan']))
        for event in result.get('loop_events_during_probe', [])
        if event.get('new_pose_graph_edge_confirmed')
    }
    nodes = node_lookup(after)
    ledger = []
    attribution_counts = Counter()
    provenance_counts = Counter()
    target_pairs = []
    wrong_pairs = []
    ambiguous_pairs = []
    for edge in new_edges:
        pair = edge_pair(edge)
        record = provenance_by_pair.get(pair)
        attribution = classify_constraint(pair[0], pair[1], target_ids, before_max)
        if (attribution == 'TARGET_ATTRIBUTABLE' and target_unique_ids
                and record is not None
                and int(record['source_unique_id']) not in target_unique_ids):
            attribution = 'AMBIGUOUS'
        attribution_counts[attribution] += 1
        if attribution == 'TARGET_ATTRIBUTABLE':
            target_pairs.append(pair)
        elif attribution == 'WRONG_TARGET_HISTORICAL':
            wrong_pairs.append(pair)
        elif attribution == 'AMBIGUOUS':
            ambiguous_pairs.append(pair)

        covariance = (record['covariance_3x3'] if record is not None
                      else covariance_from_edge(edge))
        matrix = covariance_quality(covariance)
        source_node = nodes.get(pair[0], {})
        target_node = nodes.get(pair[1], {})
        if all(key in source_node and key in target_node for key in ('x', 'y')):
            spatial = ((float(source_node['x']) - float(target_node['x'])) ** 2
                       + (float(source_node['y']) - float(target_node['y'])) ** 2) ** 0.5
        else:
            spatial = None

        explicit = bool(
            (record is not None and record.get('creation_provenance') == 'TRY_CLOSE_LOOP')
            or pair in explicit_event_pairs)
        exclusion = (near_linked_exclusion_evidence(record, records)
                     if record is not None else {
                         'pre_try_context_observed': False,
                         'edge_present_pre_try': None,
                         'source_in_pre_try_near_linked': None,
                     })
        provenance = (record.get('creation_provenance') if record is not None
                      else 'UNKNOWN_NOT_RECORDED')
        provenance_counts[provenance] += 1
        relative = record.get('relative_mean', {}) if record is not None else {}
        ledger.append({
            'episode_id': episode['episode_id'],
            'condition_id': episode['spec']['condition_id'],
            'attempt': attempt['attempt'],
            'run_dir': str(run_dir),
            'edge_index': edge.get('index'),
            'source_state_id': pair[0], 'target_state_id': pair[1],
            'source_unique_id': (record.get('source_unique_id')
                                 if record is not None else ''),
            'target_unique_id': (record.get('target_unique_id')
                                 if record is not None else ''),
            'scan_index_gap': abs(pair[1] - pair[0]),
            'attribution': attribution,
            'target_attributable': attribution == 'TARGET_ATTRIBUTABLE',
            'explicit_try_close_loop': explicit,
            'nonexplicit_target': bool(
                attribution == 'TARGET_ATTRIBUTABLE' and not explicit),
            'creation_provenance': provenance,
            'creation_function': (record.get('creation_function')
                                  if record is not None else ''),
            'creation_stage': (record.get('creation_stage')
                               if record is not None else ''),
            'matcher_type': record.get('matcher_type') if record is not None else '',
            'match_response': record.get('match_response') if record is not None else '',
            'match_threshold': record.get('match_threshold') if record is not None else '',
            'coarse_response': record.get('coarse_response') if record is not None else '',
            'coarse_threshold': record.get('coarse_threshold') if record is not None else '',
            'relative_mean_x': relative.get('x', ''),
            'relative_mean_y': relative.get('y', ''),
            'relative_mean_yaw': relative.get('yaw', ''),
            'covariance_3x3': json.dumps(covariance, separators=(',', ':')),
            'covariance_symmetric': matrix['symmetric'],
            'covariance_positive_definite': matrix['positive_definite'],
            'det_covariance': matrix['det_covariance'],
            'det_information': matrix['det_information'],
            'logdet_information': matrix['logdet_information'],
            'source_target_spatial_separation_m': spatial,
            'before_or_during_probe': (record.get('before_or_during_probe')
                                       if record is not None else ''),
            'solver_add_constraint_called': (record.get('solver_add_constraint_called')
                                             if record is not None else ''),
            **exclusion,
            'provenance_record_status': ('EXACT_RECORD' if record is not None
                                         else 'UNKNOWN_NOT_RECORDED'),
        })

    target_rows = [row for row in ledger if row['target_attributable']]
    explicit_target = [row for row in target_rows if row['explicit_try_close_loop']]
    observer_ages = [before.get('full_pose_graph_age_s'),
                     after.get('full_pose_graph_age_s')]
    observer_age_fresh = all(value is not None and float(value) <= 1.0
                             for value in observer_ages)
    observer_cut_complete = bool(
        len(before['nodes']) == len(before['full_pose_nodes'])
        and len(after['nodes']) == len(after['full_pose_nodes'])
        and (not provenance_available or (
            reconciliation['exact_pair_set_match']
            and reconciliation['exact_count_match']
            and (observer_age_fresh
                 or reconciliation['records_after_snapshot_cut'] == 0))))
    summary = {
        'episode_id': episode['episode_id'],
        'condition_id': episode['spec']['condition_id'],
        'attempt': attempt['attempt'], 'run_dir': str(run_dir),
        'valid_status': 'VALID' if result.get('analysis_eligible') else 'EXCLUDED',
        'analysis_eligible': result.get('analysis_eligible'),
        'diagnostics_enabled': episode['spec']['diagnostics_enabled'],
        'action_completed': result.get('action_completed'),
        'before_node_count': len(before['nodes']),
        'after_node_count': len(after['nodes']),
        'before_edge_count': len(before['full_pose_edges']),
        'after_edge_count': len(after['full_pose_edges']),
        'new_edge_count': len(new_edges),
        'n_target_constraints': len(target_rows),
        'n_target_explicit_constraints': len(explicit_target),
        'n_target_nonexplicit_constraints': len(target_rows) - len(explicit_target),
        'n_wrong_target_constraints': attribution_counts['WRONG_TARGET_HISTORICAL'],
        'n_ordinary_recent_or_sequential_constraints':
            attribution_counts['ORDINARY_RECENT_OR_SEQUENTIAL'],
        'n_ambiguous_constraints': attribution_counts['AMBIGUOUS'],
        'has_target_constraint': bool(target_rows),
        'has_explicit_target_loop': bool(explicit_target),
        'try_close_loop_events': len(result.get('loop_events_during_probe', [])),
        'provenance_available': provenance_available,
        'provenance_validation_errors': json.dumps(validation_errors),
        'full_graph_provenance_exact_pair_set_match': (
            reconciliation['exact_pair_set_match'] if reconciliation else ''),
        'full_graph_provenance_exact_count_match': (
            reconciliation['exact_count_match'] if reconciliation else ''),
        'slam_path_full_graph_before_equal':
            len(before['nodes']) == len(before['full_pose_nodes']),
        'slam_path_full_graph_after_equal':
            len(after['nodes']) == len(after['full_pose_nodes']),
        'before_full_graph_age_s': before.get('full_pose_graph_age_s', ''),
        'after_full_graph_age_s': after.get('full_pose_graph_age_s', ''),
        'observer_cut_complete': observer_cut_complete,
        'target_pairs': pair_json(target_pairs),
        'wrong_target_pairs': pair_json(wrong_pairs),
        'ambiguous_pairs': pair_json(ambiguous_pairs),
        'provenance_counts_new_edges': provenance_json(provenance_counts),
        'actual_probe_distance_m': result.get('actual_probe_distance_m'),
        'probe_duration_s': (float(result['probe_end_time'])
                             - float(result['probe_start_time'])),
    }
    audit = {
        'episode_id': episode['episode_id'],
        'attempt': attempt['attempt'],
        'status': 'VALID',
        'outcome_selected': True,
        'target_history_state_ids': sorted(target_ids),
        'target_history_unique_ids': frozen.get('historical_unique_ids'),
        'target_selection_rule': (
            'contiguous pre-probe slam_path scans within frozen '
            'target_segment_radius_m of the preselected anchor'),
        'freeze_timestamp_sim': before.get('sim_time'),
        'before_max_state_id': before_max,
        'target_pairs': [list(pair) for pair in target_pairs],
        'wrong_target_pairs': [list(pair) for pair in wrong_pairs],
        'ambiguous_pairs': [list(pair) for pair in ambiguous_pairs],
        'provenance_validation_errors': validation_errors,
        'reconciliation': reconciliation,
    }
    return summary, ledger, audit, result, before, after


def write_csv(path, fields, rows):
    with Path(path).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def invalid_episode_summary(suite_dir, episode):
    attempts = episode.get('attempts', [])
    latest = attempts[-1] if attempts else {}
    empty = {field: '' for field in SUMMARY_FIELDS}
    empty.update({
        'episode_id': episode['episode_id'],
        'condition_id': episode['spec']['condition_id'],
        'attempt': latest.get('attempt', ''),
        'run_dir': str(suite_dir / latest['run_dir']) if latest.get('run_dir') else '',
        'valid_status': episode.get('status', 'NO_VALID_ATTEMPT'),
        'analysis_eligible': False,
        'diagnostics_enabled': episode['spec']['diagnostics_enabled'],
        'action_completed': False,
        'has_target_constraint': '',
        'has_explicit_target_loop': '',
        'provenance_validation_errors': json.dumps([
            episode.get('scientific_reason', 'no valid scientific attempt')]),
        'observer_cut_complete': False,
    })
    audit = {
        'episode_id': episode['episode_id'],
        'status': episode.get('status'),
        'scientific_status': episode.get('scientific_status'),
        'scientific_reason': episode.get('scientific_reason'),
        'attempts': attempts,
        'outcome_selected': False,
    }
    return empty, audit


def action_signature(result):
    return [{
        'label': move.get('label'),
        'target_x': move.get('target_x'),
        'target_y': move.get('target_y'),
        'target_theta': move.get('target_theta'),
        'action_state': move.get('action_state'),
        'independently_reached': move.get('independently_reached'),
    } for move in result.get('moves', [])]


def diagnostics_check(analyses):
    by_condition = {item[0]['condition_id']: item for item in analyses}
    off = by_condition.get('baseline_diag_off')
    on = by_condition.get('baseline_diag_on')
    if off is None or on is None:
        return {'status': 'INCOMPLETE_SENTINEL_PAIR'}
    off_summary, _, _, off_result, _, _ = off
    on_summary, _, _, on_result, _, _ = on
    off_spec = off_result['spec']
    on_spec = on_result['spec']
    planned_fields = ('map_id', 'target_id', 'maneuver_type', 'delta_yaw_deg',
                      'lateral_offset_m', 'history_offsets', 'start_pose')
    exact_action_plan = all(off_spec[field] == on_spec[field]
                            for field in planned_fields)
    executed_labels_match = [item['label'] for item in action_signature(off_result)] == [
        item['label'] for item in action_signature(on_result)]
    result = {
        'comparison': 'baseline_diag_off_vs_baseline_diag_on',
        'replicate_count_per_condition': 1,
        'planned_action_exact_match': exact_action_plan,
        'executed_waypoint_labels_match': executed_labels_match,
        'tsp_seed_off': 31000 + int(off_spec['sequence']),
        'tsp_seed_on': 31000 + int(on_spec['sequence']),
        'off': {
            'action_signature': action_signature(off_result),
            'summary': off_summary,
        },
        'on': {
            'action_signature': action_signature(on_result),
            'summary': on_summary,
        },
        'deltas_on_minus_off': {
            field: float(on_summary[field]) - float(off_summary[field])
            for field in ('after_node_count', 'after_edge_count', 'new_edge_count',
                          'n_target_constraints', 'try_close_loop_events',
                          'actual_probe_distance_m', 'probe_duration_s')
        },
        'limitations': [
            'The diagnostics-off episode predates edge-provenance logging, so its '
            'provenance distribution is UNKNOWN_NOT_RECORDED.',
            'The frozen runner used sequence-dependent TSP seeds (31001 versus '
            '31002), so this pair cannot causally isolate instrumentation.',
            'One pair can detect material pairwise divergence but cannot establish '
            'absence of small stochastic or systematic effects.',
        ],
    }
    gates = [
        exact_action_plan, executed_labels_match,
        bool(off_summary['action_completed']), bool(on_summary['action_completed']),
        bool(off_summary['slam_path_full_graph_before_equal']),
        bool(off_summary['slam_path_full_graph_after_equal']),
        bool(on_summary['slam_path_full_graph_before_equal']),
        bool(on_summary['slam_path_full_graph_after_equal']),
    ]
    result['pairwise_gate_checks_passed'] = all(gates)
    result['status'] = (
        'INCONCLUSIVE_FOR_CAUSAL_NON_PERTURBATION_SINGLE_PAIR_SEED_CONFOUNDED'
        if all(gates) else 'MATERIAL_OR_TECHNICAL_DIVERGENCE')
    return result


def update_pilot_csv(suite_dir, summaries):
    path = suite_dir / 'pilot_episodes.csv'
    old_rows = []
    old_fields = []
    if path.is_file():
        with path.open(newline='') as stream:
            reader = csv.DictReader(stream)
            old_fields = list(reader.fieldnames or [])
            old_rows = list(reader)
    by_episode = {row.get('episode_id'): row for row in old_rows}
    appended = [field for field in SUMMARY_FIELDS if field not in old_fields]
    fields = old_fields + appended
    for summary in summaries:
        row = by_episode.setdefault(summary['episode_id'], {})
        for key, value in summary.items():
            row[key] = value
    rows = [by_episode[summary['episode_id']] for summary in summaries]
    write_csv(path, fields, rows)


def write_aggregate_provenance(suite_dir, summaries):
    lines = []
    for summary in summaries:
        if not summary.get('provenance_available'):
            continue
        path = Path(summary['run_dir']) / 'karto_edge_provenance.jsonl'
        if path.is_file():
            lines.extend(line for line in path.read_text().splitlines() if line.strip())
    output = suite_dir / 'karto_edge_provenance.jsonl'
    output.write_text(('\n'.join(lines) + '\n') if lines else '')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--suite-dir', required=True, type=Path)
    args = parser.parse_args()
    suite_dir = args.suite_dir.resolve()
    state = load_json(suite_dir / 'suite_state.json')
    analyses = [analyze_episode(suite_dir, episode, attempt)
                for episode, attempt in selected_attempts(state)]
    summaries = [item[0] for item in analyses]
    ledger = [row for item in analyses for row in item[1]]
    audits = [item[2] for item in analyses]
    analyzed_ids = {row['episode_id'] for row in summaries}
    for episode in state['episodes']:
        if episode['episode_id'] in analyzed_ids:
            continue
        invalid_summary, invalid_audit = invalid_episode_summary(suite_dir, episode)
        summaries.append(invalid_summary)
        audits.append(invalid_audit)
    sequence = {episode['episode_id']: episode['spec']['sequence']
                for episode in state['episodes']}
    summaries.sort(key=lambda row: sequence[row['episode_id']])
    audits.sort(key=lambda row: sequence[row['episode_id']])

    write_csv(suite_dir / 'sentinel_edge_ledger.csv', LEDGER_FIELDS, ledger)
    write_csv(suite_dir / 'sentinel_constraint_summary.csv', SUMMARY_FIELDS, summaries)
    shutil.copyfile(SCHEMA_SOURCE, suite_dir / 'edge_provenance_schema.json')
    update_pilot_csv(suite_dir, summaries)
    write_aggregate_provenance(suite_dir, summaries)

    observer = {
        'status': ('PASS_FOR_VALID_EPISODES' if all(
            row['observer_cut_complete'] for row in summaries
            if row['valid_status'] == 'VALID') else 'FAIL'),
        'episodes': [{key: row[key] for key in (
            'episode_id', 'attempt', 'slam_path_full_graph_before_equal',
            'slam_path_full_graph_after_equal', 'provenance_available',
            'full_graph_provenance_exact_pair_set_match',
            'full_graph_provenance_exact_count_match',
            'before_full_graph_age_s', 'after_full_graph_age_s',
            'observer_cut_complete')}
            for row in summaries if row['valid_status'] == 'VALID'],
        'excluded_conditions': [row['episode_id'] for row in summaries
                                if row['valid_status'] != 'VALID'],
        'note': ('Exact full-graph/provenance reconciliation is required only for '
                 'runs executed after provenance instrumentation was enabled.'),
    }
    dump_json(suite_dir / 'observer_validation_summary.json', observer)
    dump_json(suite_dir / 'diagnostics_perturbation_check.json',
              diagnostics_check(analyses))
    target_audit = {
        'schema_version': 1,
        'attribution_rule': {
            'TARGET_ATTRIBUTABLE':
                'source in frozen H_target and target state id > before_max_state_id',
            'WRONG_TARGET_HISTORICAL':
                'source is pre-probe non-target, target is post-probe, and gap > 1',
            'ORDINARY_RECENT_OR_SEQUENTIAL':
                'state-id gap is 1 or source is post-probe',
            'AMBIGUOUS': 'all remaining cases; never forced into target success',
        },
        'episode_audits': audits,
        'all_provenance_runs_reconciled': all(
            audit.get('reconciliation') is None
            or (audit['reconciliation']['exact_pair_set_match']
                and audit['reconciliation']['exact_count_match'])
            for audit in audits),
    }
    dump_json(suite_dir / 'target_attribution_audit.json', target_audit)
    print(json.dumps({
        'episodes_analyzed': len(summaries),
        'ledger_edges': len(ledger),
        'observer_status': observer['status'],
        'suite_dir': str(suite_dir),
    }, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
