#!/usr/bin/python3
"""Integrity tests for the post-confirmatory v14 heterogeneity audit."""

import json
from pathlib import Path

import v14_heterogeneity_audit as audit


RESULT = audit.RESULT_ROOT / 'analysis'


def _rows(name):
    return audit.read_csv(RESULT / name)


def test_feature_extraction_is_deterministic():
    block_id = 'target_A_H1'
    replay = (audit.V14_ROOT / 'collection/replays/target_A' / block_id)
    first = audit.extract_pretreatment_features(
        block_id, 91001, 'target_A', replay)
    second = audit.extract_pretreatment_features(
        block_id, 91001, 'target_A', replay)
    assert first == second


def test_pretreatment_contract_excludes_post_treatment_features():
    contract = json.loads((RESULT / 'pretreatment_feature_contract.json').read_text())
    allowed = contract['future_predictor_allowlist']
    forbidden_tokens = ('Delta_', 'accepted_keyscan', 'historical_factor',
                        'D_sweep', 'D_trigger', 'outcome')
    assert contract['post_treatment_feature_leakage_allowed'] is False
    assert not any(token in feature for feature in allowed
                   for token in forbidden_tokens)
    rows = _rows('pretreatment_feature_table.csv')
    for feature, available in contract['features'].items():
        marker = feature + '__PRETREATMENT_AVAILABLE'
        assert marker in rows[0]
        assert {row[marker] for row in rows} == {str(available)}


def test_exact_endpoint_set_comparison():
    def row(left, right, hops):
        return {'source_state_id': left, 'target_state_id': right,
                'hops_at_insertion': hops}
    result = audit.endpoint_set_summary(
        [row(1, 2, 2), row(3, 4, 1)],
        [row(2, 1, 2), row(5, 6, 3)])
    assert json.loads(result['intersection_pairs']) == [[1, 2]]
    assert json.loads(result['A2_only_pairs']) == [[3, 4]]
    assert json.loads(result['A3_only_pairs']) == [[5, 6]]
    assert result['endpoint_jaccard_similarity'] == 1 / 3


def test_historical_factor_counts_match_exact_endpoint_sets():
    realized = {row['block_id']: row for row in
                _rows('realized_measurement_difference_table.csv')}
    endpoints = {row['block_id']: row for row in
                 _rows('endpoint_set_comparison.csv')}
    assert set(realized) == set(endpoints)
    for block_id in realized:
        assert int(realized[block_id]['A2_historical_factors']) == int(
            endpoints[block_id]['A2_endpoint_count'])
        assert int(realized[block_id]['A3_historical_factors']) == int(
            endpoints[block_id]['A3_endpoint_count'])


def test_frozen_v14_hashes_are_unchanged():
    verification = audit.verify_v14_immutable()
    assert verification['passed']
    assert verification['checked'] >= 10
    assert verification['failures'] == []


def test_target_label_confounding_detection():
    rows = [
        {'target_B_indicator': 0, 'dose': value}
        for value in (0.1, 0.2, 0.3, 0.4)] + [
        {'target_B_indicator': 1, 'dose': value}
        for value in (1.1, 1.2, 1.3, 1.4)]
    result = audit.target_confounding(rows, ['dose'])[0]
    assert result['target_ranges_nonoverlapping']
    assert result['status'] == 'TARGET_FEATURE_CONFOUNDING_NOT_IDENTIFIABLE'


def test_cross_protocol_rows_are_never_pooled():
    rows = audit.cross_protocol_context()
    assert rows
    assert all(row['comparability_to_v14'] == 'NOT_DIRECTLY_COMPARABLE'
               for row in rows)
    assert all(row['pooled_with_v14'] is False for row in rows)
    guard = json.loads((RESULT / 'cross_protocol_non_pooling_guard.json').read_text())
    assert guard['pooled_analysis_allowed'] is False
    assert guard['all_legacy_rows_marked_not_directly_comparable'] is True


def test_next_experiment_is_design_only():
    design = json.loads((audit.RESULT_ROOT / 'design' /
                         'CONTEXT_DISENTANGLEMENT_EXPERIMENT.json').read_text())
    assert design['status'] == 'DESIGN_ONLY_NOT_EXECUTED'
    assert design['execution_authorized'] is False
