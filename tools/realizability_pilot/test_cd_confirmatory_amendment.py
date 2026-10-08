"""Outcome-blind static regression tests for CD technical amendment 1."""

import copy
from collections import Counter

import cd_confirmatory_amendment_collection as collection
import cd_confirmatory_amendment_pipeline as pipeline
import cd_confirmatory_amendment_protocol as amendment
import cd_confirmatory_analysis as original_analysis
import cd_confirmatory_protocol as original


EXPECTED_SELECTED = {
    'target_A': [101002, 101003, 101004, 101006,
                 101007, 101008, 101009, 101010],
    'target_B': [102001, 102002, 102003, 102004,
                 102005, 102006, 102007, 102008],
}


def original_selected_seeds():
    manifest = amendment.load_json(amendment.ORIGINAL_HISTORY_MANIFEST_PATH)
    return {
        target: [int(row['seed'])
                 for row in manifest['selected_blocks'][target]]
        for target in amendment.TARGETS}


def test_original_incomplete_run_is_immutable_and_outcome_blind():
    audit = amendment.original_run_audit()
    assert audit['passed']
    assert audit['original_file_count'] == 3881
    assert audit['original_aggregate_manifest_sha256'] == \
        amendment.EXPECTED_ORIGINAL_AGGREGATE_SHA256
    assert audit['checks']['scientific_endpoint_not_read']
    assert audit['checks']['no_physical_branch_before_amendment']
    assert audit['checks']['no_backend_replay_before_amendment']
    assert audit['checks']['no_scientific_analysis_before_amendment']


def test_original_gate_and_original_report_are_preserved():
    final = amendment.load_json(amendment.ORIGINAL_FINAL_GATE_PATH)
    assert final['final_scientific_gate'] == \
        'CD_PROSPECTIVE_TECHNICALLY_INCOMPLETE'
    assert final['reason'] == \
        'RuntimeError: frozen arm order is not position-balanced'
    assert amendment.sha256(amendment.ORIGINAL_FINAL_GATE_PATH) == \
        amendment.EXPECTED_ORIGINAL_FINAL_GATE_SHA256
    assert amendment.sha256(amendment.ORIGINAL_DOC_PATH) == \
        amendment.EXPECTED_ORIGINAL_DOC_SHA256


def test_exact_frozen_first_eight_histories_are_reused():
    assert original_selected_seeds() == EXPECTED_SELECTED
    assert amendment.sha256(amendment.ORIGINAL_HISTORY_MANIFEST_PATH) == \
        amendment.EXPECTED_ORIGINAL_HISTORY_MANIFEST_SHA256


def test_arm_orders_are_exactly_original_and_not_reordered():
    assert amendment.ARM_ORDERS == original.ARM_ORDERS
    assert amendment.canonical_sha(amendment.ARM_ORDERS) == \
        amendment.EXPECTED_ARM_ORDERS_SHA256


def test_per_target_stratum_position_balance_passes():
    rows = []
    for target, orders in amendment.ARM_ORDERS.items():
        for index, order in enumerate(orders, 1):
            rows.append({
                'block_id': '{}_H{:02d}'.format(target, index),
                'target_label': target,
                'seed': EXPECTED_SELECTED[target][index - 1],
                'arm_order': order,
            })
    result = amendment.validate_per_target_arm_balance(rows)
    assert result['passed']
    assert result['validation_unit'] == 'Target stratum'
    for target in amendment.TARGETS:
        for arm in amendment.ARMS:
            values = list(result['position_counts'][target][arm].values())
            assert max(values) - min(values) <= 1


def test_legacy_pooled_gate_fails_only_for_d1():
    counts = {arm: Counter() for arm in amendment.ARMS}
    for orders in amendment.ARM_ORDERS.values():
        for order in orders:
            for position, arm in enumerate(order, 1):
                counts[arm][position] += 1
    differences = {
        arm: max(counts[arm].values()) - min(counts[arm].values())
        for arm in amendment.ARMS}
    assert differences == {
        'D0_ZERO': 1, 'D1_THRESHOLD': 2, 'D2_HIGH': 1}


def test_only_validation_semantics_change_in_preregistered_design():
    original_prereg = amendment.load_json(
        amendment.ORIGINAL_PREREGISTRATION_PATH)
    amended = copy.deepcopy(original_prereg)
    amended['protocol_id'] = amendment.PROTOCOL_ID
    for field in amendment.SCIENTIFIC_FIELDS:
        assert amended[field] == original_prereg[field]
    assert amended['arm_order_rule']['deterministic_orders'] == \
        original_prereg['arm_order_rule']['deterministic_orders']
    assert amended['history_qualification'][
        'candidate_seeds_in_frozen_order'] == original_prereg[
            'history_qualification']['candidate_seeds_in_frozen_order']
    assert amendment.DOSES == original.DOSES
    assert amendment.N_SCANS == original.N_SCANS == 347


def test_analysis_implementation_is_reused_unchanged():
    assert original_analysis.__file__.endswith('cd_confirmatory_analysis.py')
    assert amendment.sha256(original_analysis.__file__) == \
        amendment.sha256(
            amendment.ROOT /
            'tools/realizability_pilot/cd_confirmatory_analysis.py')


def test_pipeline_has_no_history_generation_or_qualification_stage():
    source = (amendment.ROOT /
              'tools/realizability_pilot/'
              'cd_confirmatory_amendment_pipeline.py').read_text()
    assert 'cd_confirmatory_qualification' not in source
    assert 'CANDIDATE_QUALIFICATION' not in source
    assert "state['current_stage'] = 'PHYSICAL_COLLECTION'" in source


def test_collection_freeze_accepts_exact_per_stratum_order(
        tmp_path, monkeypatch):
    rows = []
    for target, orders in amendment.ARM_ORDERS.items():
        for index, order in enumerate(orders, 1):
            rows.append({
                'block_id': '{}_H{:02d}'.format(target, index),
                'target_label': target,
                'seed': EXPECTED_SELECTED[target][index - 1],
                'arm_order': order,
            })
    path = tmp_path / 'arm_order.json'
    monkeypatch.setattr(amendment, 'ARM_ORDER_MANIFEST_PATH', path)
    monkeypatch.setattr(amendment, 'arm_order_rows', lambda: rows)
    first = collection.freeze_arm_order()
    second = collection.freeze_arm_order()
    assert first == second
    assert first['balance_validation']['passed']
    assert first['exact_original_arm_orders_sha256'] == \
        amendment.EXPECTED_ARM_ORDERS_SHA256


def test_amendment_root_does_not_exist_before_freeze():
    assert not amendment.RESULT_ROOT.exists()


def test_pipeline_prepare_is_the_only_authorization_entrypoint():
    assert pipeline.prepare.__module__ == \
        'cd_confirmatory_amendment_pipeline'
    assert pipeline.protocol.prepare_amendment is amendment.prepare_amendment


def test_original_tree_still_matches_after_all_static_checks():
    count, digest = amendment.aggregate_tree_sha(amendment.ORIGINAL_ROOT)
    assert count == amendment.EXPECTED_ORIGINAL_FILE_COUNT
    assert digest == amendment.EXPECTED_ORIGINAL_AGGREGATE_SHA256
