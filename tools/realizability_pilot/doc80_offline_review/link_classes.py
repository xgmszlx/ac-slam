#!/usr/bin/python3
"""Doc-80 section 6: historical-association classes and set-level contributions.

Classifies every *new non-chain* edge between ``G_arrival_sync`` and
``G_action_done_sync`` by the stage of its endpoints (history / return /
action) and evaluates joint information contributions with set-level edge
removal on the frozen linearised factor model.  All information values carry
``FIXED_LINEARIZATION_FACTOR_DIAGNOSTIC``: they are a sensitivity of a fixed
linearisation, not a causal effect.  Set contributions are *joint* (edges are
removed together); hierarchical differences are reported with their ordering
because they are order-dependent.

Outputs
- analysis/historical_link_classes.csv
- analysis/factor_group_contributions.csv
"""

import json
import math
import statistics
import sys
from pathlib import Path

from . import common

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'continuous_revisit'))
import analysis as frozen_analysis  # noqa: E402


def edge_class_of(source_stage, target_stage):
    """Class of a new non-chain edge from its endpoint stages."""
    stages = {source_stage, target_stage}
    if 'history' in stages:
        return 'A_FIRST_VISIT_HISTORY_LINK'
    if 'return' in stages:
        return 'B_RETURN_HISTORY_LINK'
    return 'C_ACTION_INTERNAL_NONLOCAL_LINK'


def endpoint_stage(state, accepts, scans, stage_windows):
    item = accepts.get(state)
    if item is None:
        return None
    return common.stage_of_stamp(item['sim_time'], scans, stage_windows)


def classify(run):
    result = run['result']
    stage_windows = common.windows(result)
    scans = common.jsonl(run['attempt_dir'] / 'scan_stream.jsonl')
    accepts = {item['state_id']: item for item in common.accepts(run)}
    arrival = common.sync_graph(run, 'arrival')
    action_done = common.sync_graph(run, 'action_done')
    if stage_windows is None or arrival is None or action_done is None:
        return [], {}, {}
    arrival_keys = {(edge['source_state_id'], edge['target_state_id'])
                    for edge in arrival['edges']}
    records = common.jsonl(run['attempt_dir'] / 'karto_edge_provenance.jsonl')
    record_lookup = {}
    for record in records:
        if record.get('record_type') == 'constraint_created':
            key = (int(record['source_state_id']), int(record['target_state_id']))
            record_lookup.setdefault(key, []).append(record)

    rows = []
    groups = {'A': [], 'B': [], 'C': []}
    for edge in action_done['edges']:
        key = (edge['source_state_id'], edge['target_state_id'])
        if key in arrival_keys:
            continue
        record = (record_lookup.get(key) or record_lookup.get((key[1], key[0]))
                  or [{}])[0]
        chain = abs(key[1] - key[0]) == 1
        source_stage = endpoint_stage(key[0], accepts, scans, stage_windows)
        target_stage = endpoint_stage(key[1], accepts, scans, stage_windows)
        edge_class = edge_class_of(source_stage, target_stage)
        covariance = edge.get('covariance_3x3') or []
        trace = None
        if covariance:
            try:
                trace = sum(float(covariance[i][i]) for i in range(3))
            except Exception:  # noqa: BLE001
                trace = None
        row = {
            'episode_id': run['episode_id'], 'attempt': run['attempt'],
            'place': run['spec'].get('place_id'),
            'action': run['spec'].get('action_id'),
            'edge_index_action_done': edge['index'],
            'source_state_id': key[0], 'target_state_id': key[1],
            'source_stage': source_stage, 'target_stage': target_stage,
            'is_chain': chain,
            'edge_class': 'CHAIN' if chain else edge_class,
            'creation_provenance': record.get('creation_provenance'),
            'creation_sequence': record.get('creation_sequence'),
            'creation_stage': record.get('creation_stage'),
            'creation_sim_time': record.get('sim_time'),
            'match_response': record.get('match_response'),
            'coarse_response': record.get('coarse_response'),
            'matcher_type': record.get('matcher_type'),
            'covariance_trace': trace,
        }
        rows.append(row)
        if not chain:
            groups[edge_class[0]].append(key)
    return rows, groups, record_lookup


def contributions_for(run, groups, rows):
    """Joint set-level removal contributions on the action_done graph."""
    import numpy as np  # noqa: F401  (scipy dependency warm-up)
    action_done = common.sync_graph(run, 'action_done')
    arrival = common.sync_graph(run, 'arrival')
    targets = [int(value) for value in run['frozen']['target_state_ids']]
    if action_done is None or arrival is None:
        return None
    full_graph = common.graph_as_analysis(action_done)
    try:
        j_full = frozen_analysis.target_score(full_graph, targets)['J_T']
    except Exception as exc:  # noqa: BLE001
        return {'error': '{}: {}'.format(type(exc).__name__, exc)}

    arrival_keys = {(edge['source_state_id'], edge['target_state_id'])
                    for edge in arrival['edges']}
    nonchain_keys = set()
    historic_keys = set()
    for row in rows:
        if row['is_chain']:
            continue
        key = (row['source_state_id'], row['target_state_id'])
        nonchain_keys.add(key)
        if row['source_stage'] in ('history', 'return') or \
                row['target_stage'] in ('history', 'return'):
            historic_keys.add(key)

    def score_without(keys):
        reduced = {'nodes': full_graph['nodes'],
                   'edges': [edge for edge in full_graph['edges']
                             if (edge['source_state_id'],
                                 edge['target_state_id']) not in keys]}
        try:
            return frozen_analysis.target_score(reduced, targets)['J_T']
        except Exception:  # noqa: BLE001
            return None

    def contribution(keys):
        if not keys:
            return 0.0, j_full
        reduced = score_without(keys)
        if reduced is None:
            return None, None
        return j_full - reduced, reduced

    result = {'run_id': run['spec'].get('provenance_run_id'),
              'J_full': j_full,
              'diagnostic_label': 'FIXED_LINEARIZATION_FACTOR_DIAGNOSTIC'}
    result['nonchain_edges'] = len(nonchain_keys)
    result['historic_edges'] = len(historic_keys)
    result['contribution_all_nonseq'], _ = contribution(nonchain_keys)
    result['contribution_historic_only'], _ = contribution(historic_keys)
    # single-class joint contributions
    for name in ('A', 'B', 'C'):
        keys = set(groups.get(name, []))
        result['contribution_class_{}'.format(name)], _ = contribution(keys)
        result['count_class_{}'.format(name)] = len(keys)
    # hierarchical removal A -> B -> C (ordering documented; result dependent)
    j_after_a = score_without(set(groups['A']))
    j_after_ab = score_without(set(groups['A']) | set(groups['B']))
    j_after_abc = score_without(nonchain_keys)
    result['hierarchical_removal_order'] = 'A, then B, then C'
    result['hierarchical_A'] = None if j_after_a is None else j_full - j_after_a
    result['hierarchical_B_after_A'] = (
        None if j_after_a is None or j_after_ab is None else j_after_a - j_after_ab)
    result['hierarchical_C_after_AB'] = (
        None if j_after_ab is None or j_after_abc is None else j_after_ab - j_after_abc)

    # Doc-79 recorded values for the two-comparison statement
    recorded = run['result']
    return result


def doc79_comparison(doc80_root=common.DOC80, doc79_root=common.DOC79):
    """Exact doc-79 vs doc-80 differences for the two reported equalities."""
    import csv
    rows = []
    mechanism_path = Path(doc79_root) / 'analysis' / 'action_mechanism.csv'
    metrics_path = Path(doc79_root) / 'analysis' / 'per_episode_metrics.csv'
    if not mechanism_path.is_file() or not metrics_path.is_file():
        return rows
    delta_by_run = {}
    with open(metrics_path) as handle:
        for row in csv.DictReader(handle):
            key = (row['episode_id'], row['attempt'])
            value = row.get('delta_J_action_sync')
            delta_by_run[key] = float(value) if value not in (None, '') else None
    with open(mechanism_path) as handle:
        for row in csv.DictReader(handle):
            if row['stage'] != 'action':
                continue
            key = (row['episode_id'], row['attempt'])
            closure = row.get('closure_contribution')
            historic = row.get('historic_contribution')
            rows.append({
                'episode_id': row['episode_id'], 'attempt': row['attempt'],
                'delta_J_action_sync': delta_by_run.get(key),
                'closure_contribution': float(closure) if closure not in (None, '') else None,
                'historic_contribution': float(historic) if historic not in (None, '') else None,
            })
    for row in rows:
        closure = row['closure_contribution']
        historic = row['historic_contribution']
        delta = row['delta_J_action_sync']
        row['closure_minus_historic'] = (
            None if closure is None or historic is None else closure - historic)
        row['delta_minus_historic'] = (
            None if delta is None or historic is None else delta - historic)
        row['delta_minus_closure'] = (
            None if delta is None or closure is None else delta - closure)
    common.write_csv(Path(doc80_root) / 'analysis' /
                     'doc79_contribution_comparisons.csv', rows)
    return rows


def run(doc80_root=common.DOC80):
    edge_rows = []
    contribution_rows = []
    for run_ in common.valid_runs():
        rows, groups, _ = classify(run_)
        edge_rows.extend(rows)
        result = contributions_for(run_, groups, rows)
        if result is not None:
            result.update({
                'episode_id': run_['episode_id'], 'attempt': run_['attempt'],
                'place': run_['spec'].get('place_id'),
                'action': run_['spec'].get('action_id'),
            })
            contribution_rows.append(result)
    common.write_csv(Path(doc80_root) / 'analysis' / 'historical_link_classes.csv',
                     edge_rows)
    common.write_csv(Path(doc80_root) / 'analysis' /
                     'factor_group_contributions.csv', contribution_rows)
    comparisons = doc79_comparison(doc80_root)
    return {'edges': edge_rows, 'contributions': contribution_rows,
            'doc79_comparisons': comparisons}


if __name__ == '__main__':
    out = run()
    print('edges:', len(out['edges']), 'contributions:', len(out['contributions']))
