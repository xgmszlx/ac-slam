#!/usr/bin/python3
"""Deterministic parsing, attribution, and reconciliation for Karto edges.

The helpers in this module deliberately do not infer creation provenance from
scan-index gaps.  Provenance is accepted only from the record emitted at the
actual ``isNewEdge`` branch in OpenKarto.
"""

import json
import math


PROVENANCE_VALUES = (
    'PREVIOUS_SCAN',
    'RUNNING_SCAN_CHAIN',
    'NEAR_CHAIN',
    'TRY_CLOSE_LOOP',
    'FIRST_SCAN_CROSS_SENSOR',
    'CUSTOM_OBJECT_LAST_SCAN',
    'OTHER',
)

ATTRIBUTION_VALUES = (
    'TARGET_ATTRIBUTABLE',
    'WRONG_TARGET_HISTORICAL',
    'ORDINARY_RECENT_OR_SEQUENTIAL',
    'AMBIGUOUS',
)


def load_jsonl(path):
    records = []
    with open(path) as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            record['_line_number'] = line_number
            records.append(record)
    return records


def constraint_records(records):
    return [record for record in records
            if record.get('record_type') == 'constraint_created']


def validate_constraint_records(records):
    constraints = constraint_records(records)
    sequences = [int(record['creation_sequence']) for record in constraints]
    pairs = [tuple(record['canonical_edge_identity']) for record in constraints]
    errors = []
    if sequences != list(range(1, len(sequences) + 1)):
        errors.append('creation_sequence_not_contiguous_from_one')
    if len(pairs) != len(set(pairs)):
        errors.append('duplicate_new_edge_record')
    for record in constraints:
        if record.get('creation_provenance') not in PROVENANCE_VALUES:
            errors.append('unknown_provenance_line_{}'.format(record['_line_number']))
        if not record.get('solver_add_constraint_called'):
            errors.append('new_edge_not_added_to_solver_line_{}'.format(
                record['_line_number']))
    return errors


def edge_pair(edge, start_key='start', end_key='end'):
    return int(edge[start_key]), int(edge[end_key])


def classify_constraint(source, target, target_history_ids, before_max_state_id):
    """Classify one directed newly created constraint without outcome tuning."""
    source = int(source)
    target = int(target)
    target_history_ids = frozenset(int(value) for value in target_history_ids)
    before_max_state_id = int(before_max_state_id)

    if source in target_history_ids and target > before_max_state_id:
        return 'TARGET_ATTRIBUTABLE'
    if (source <= before_max_state_id and source not in target_history_ids
            and target > before_max_state_id and abs(target - source) > 1):
        return 'WRONG_TARGET_HISTORICAL'
    if abs(target - source) == 1 or source > before_max_state_id:
        return 'ORDINARY_RECENT_OR_SEQUENTIAL'
    return 'AMBIGUOUS'


def covariance_quality(covariance):
    """Return descriptive matrix quantities without calling them quality."""
    matrix = [[float(value) for value in row] for row in covariance]
    if len(matrix) != 3 or any(len(row) != 3 for row in matrix):
        raise ValueError('covariance must be 3x3')
    symmetric = all(abs(matrix[i][j] - matrix[j][i]) <= 1e-10
                    for i in range(3) for j in range(3))
    a, b, c = matrix[0]
    d, e, f = matrix[1]
    g, h, i = matrix[2]
    determinant = (a * (e * i - f * h)
                   - b * (d * i - f * g)
                   + c * (d * h - e * g))
    positive_definite = bool(
        symmetric and a > 0.0 and (a * e - b * d) > 0.0 and determinant > 0.0)
    return {
        'symmetric': symmetric,
        'positive_definite': positive_definite,
        'det_covariance': determinant,
        'det_information': (1.0 / determinant if determinant > 0.0 else None),
        'logdet_information': (-math.log(determinant) if determinant > 0.0 else None),
    }


def reconcile_full_graph(after_snapshot, records):
    full_pairs = [edge_pair(edge) for edge in after_snapshot['full_pose_edges']]
    constraints = constraint_records(records)
    # Graph edges are append-only.  The first N creation records are therefore
    # the exact provenance cut represented by an N-edge observer snapshot;
    # later records can legitimately be emitted while the run is shutting down.
    cut_constraints = constraints[:len(full_pairs)]
    provenance_pairs = [tuple(record['canonical_edge_identity'])
                        for record in cut_constraints]
    return {
        'full_graph_edge_count': len(full_pairs),
        'provenance_constraint_count': len(provenance_pairs),
        'missing_from_provenance': sorted(set(full_pairs) - set(provenance_pairs)),
        'not_in_full_graph': sorted(set(provenance_pairs) - set(full_pairs)),
        'exact_pair_set_match': set(full_pairs) == set(provenance_pairs),
        'exact_count_match': len(full_pairs) == len(provenance_pairs),
        'records_after_snapshot_cut': len(constraints) - len(cut_constraints),
        'first_record_after_snapshot_cut': (
            constraints[len(cut_constraints)] if len(constraints) > len(cut_constraints)
            else None),
    }


def new_full_graph_edges(before_snapshot, after_snapshot):
    """Return exact directed full-graph edges first observed after the probe."""
    before_pairs = {
        edge_pair(edge) for edge in before_snapshot['full_pose_edges']
    }
    return [edge for edge in after_snapshot['full_pose_edges']
            if edge_pair(edge) not in before_pairs]


def context_for_keyscan(records, state_id, stage):
    matches = [record for record in records
               if record.get('record_type') == 'try_close_loop_context'
               and int(record.get('current_keyscan_state_id', -1)) == int(state_id)
               and record.get('stage') == stage]
    return matches[-1] if matches else None


def near_linked_exclusion_evidence(record, records):
    """Test whether a just-created historical source is near-linked pre-loop."""
    context = context_for_keyscan(
        records, record['target_state_id'], 'PRE_TRY_CLOSE_LOOP')
    if context is None:
        return {
            'pre_try_context_observed': False,
            'source_in_pre_try_near_linked': None,
            'edge_present_pre_try': None,
        }
    pair = [int(record['source_state_id']), int(record['target_state_id'])]
    graph_edges = [[int(value) for value in edge]
                   for edge in context.get('graph_edges', [])]
    near_ids = {int(value) for value in
                (context.get('near_linked_scan_ids') or [])}
    return {
        'pre_try_context_observed': True,
        'source_in_pre_try_near_linked': int(record['source_state_id']) in near_ids,
        'edge_present_pre_try': pair in graph_edges,
    }
