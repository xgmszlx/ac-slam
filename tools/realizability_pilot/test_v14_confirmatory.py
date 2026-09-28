#!/usr/bin/python3
"""Protocol-boundary tests for the v14 prospective validation."""

import math
from collections import Counter

import pytest

import v14_confirmatory_protocol as protocol
from mechanism_classifier import constraint_family, is_explicit_try_close_loop
from v14_confirmatory_analysis import support_decision
from v14_confirmatory_collection import validate_capture
from v14_confirmatory_replay import validate_replay
from v14_estimator_sanity import estimator_effect_sanity, freeze_world_gauge
from v14_history_qualification import first_four_eligible


def test_preregistration_schema_is_prospective_and_three_state():
    payload = protocol.preregistration_payload()
    assert payload['created_before_any_fresh_candidate_or_action_collection']
    assert payload['fixed_scan_controller']['N'] == 347
    assert payload['history_qualification']['candidate_seeds_in_frozen_order'] == {
        'target_A': list(range(91001, 91017)),
        'target_B': list(range(92001, 92017)),
    }
    assert set(payload['final_three_state_decision'].values()) == {
        'V14_PROSPECTIVE_SUPPORT', 'V14_PROSPECTIVE_NO_SUPPORT',
        'V14_PROSPECTIVE_TECHNICALLY_INCOMPLETE'}


def test_frozen_orders_are_position_balanced_over_eight_blocks():
    counts = {arm: Counter() for arm in protocol.ARMS}
    for target in protocol.TARGETS:
        for order in protocol.ARM_ORDERS[target]:
            assert sorted(order) == sorted(protocol.ARMS)
            for position, arm in enumerate(order, 1):
                counts[arm][position] += 1
    for arm in protocol.ARMS:
        values = [counts[arm][position] for position in (1, 2, 3)]
        assert max(values) - min(values) <= 1


def test_first_four_rule_uses_frozen_seed_order_not_record_order():
    records = [
        {'target_label': 'target_A', 'seed': seed,
         'status': ('TECHNICALLY_INELIGIBLE' if seed in (91001, 91003) else
                    'TECHNICALLY_ELIGIBLE')}
        for seed in reversed(protocol.CANDIDATE_SEEDS['target_A'])]
    assert [row['seed'] for row in first_four_eligible(
        records, 'target_A')] == [91002, 91004, 91005, 91006]


def _write_capture_files(directory):
    for name in ('capture_result.json', 'capture_spec.json',
                 'probe_stream_raw.jsonl', 'scientific_treatment_stream.jsonl',
                 'probe_gt_trajectory.txt'):
        (directory / name).write_text('{}\n')


def test_capture_validation_requires_exact_first_347(tmp_path):
    _write_capture_files(tmp_path)
    spec = {'canonical_terminal_gt_pose': [1.0, 2.0, 0.1]}
    result = {
        'status': 'SUCCEEDED', 'branch_start_gt_pose': [1.0, 2.0, 0.1],
        'scientific_treatment_scan_count': 347,
        'completion_scan_index': 300, 'completion_margin': 47,
        'scientific_stream_exact_first_N': True,
        'duplicate_timestamp_count': 0, 'nonmonotonic_timestamp_count': 0,
        'backend_started': False, 'scientific_endpoint_read': False,
    }
    assert validate_capture(spec, result, tmp_path)['valid']
    result['scientific_treatment_scan_count'] = 346
    assert not validate_capture(spec, result, tmp_path)['valid']


def test_replay_validation_requires_exact_prefix_suffix_and_backend(tmp_path):
    for name in ('graph_pre.json', 'graph_final.json',
                 'unified_replay_result.json', 'edge_provenance.jsonl',
                 'canonical_prefix.jsonl', 'probe_suffix.jsonl',
                 'combined_stream.jsonl'):
        (tmp_path / name).write_text('{}\n')
    reference = {'prefix_reference_graph_sha256': 'abc'}
    result = {
        'status': 'REPLAY_COMPLETE', 'prefix_gate_passed': True,
        'prefix_reference_comparison': {
            'structural': {'exact': True}, 'numerical': {'exact': True}},
        'suffix_record_count': 347, 'suffix_published': True,
        'prefix_record_count': 100, 'processed_final_count': 447,
        'mapper_params_sha256': protocol.EXPECTED_NORMALIZED_MAPPER_CONFIG_SHA256,
        'code_provenance': {'mapper_binary_sha256':
                            protocol.EXPECTED_MAPPER_BINARY_SHA256},
        'prefix_reference_sha256': 'abc',
    }
    assert validate_replay(tmp_path, result, reference)['valid']
    result['prefix_reference_comparison']['numerical']['exact'] = False
    assert not validate_replay(tmp_path, result, reference)['valid']


def _primary_rows(values):
    return [{'block_id': 'H{}'.format(index),
             'target': 'target_A' if index <= 4 else 'target_B',
             'D_sweep': value}
            for index, value in enumerate(values, 1)]


def test_final_gate_support_requires_every_condition():
    rows = _primary_rows([0.2] * 8)
    gate, recommendation, checks, *_ = support_decision(
        rows, True, [0.1, 0.3])
    assert gate == 'V14_PROSPECTIVE_SUPPORT'
    assert all(checks.values())
    assert recommendation == 'PROCEED_TO_REALIZATION_MODELING_DESIGN'


def test_final_gate_no_support_and_incomplete_are_distinct():
    rows = _primary_rows([0.2, 0.2, -0.1, -0.1] * 2)
    assert support_decision(rows, True, [-0.1, 0.2])[0] == \
        'V14_PROSPECTIVE_NO_SUPPORT'
    assert support_decision(rows[:7], False, None)[0] == \
        'V14_PROSPECTIVE_TECHNICALLY_INCOMPLETE'


def test_bootstrap_seed_and_repetitions_are_frozen():
    payload = protocol.preregistration_payload()
    assert payload['support_gate']['bootstrap_seed'] == 140928
    assert payload['support_gate']['bootstrap_repetitions'] == 10000


@pytest.mark.parametrize('token', [
    'ADD_EDGES_BEFORE_TRY_CLOSE_LOOP', 'TRY_CLOSE_LOOP_EXTRA',
    'PREVIOUS_SCAN', 'RUNNING_SCAN_CHAIN', 'NEAR_CHAIN'])
def test_try_close_loop_classifier_is_exact(token):
    record = {'creation_provenance': token, 'creation_stage': token,
              'matcher_type': token}
    assert not is_explicit_try_close_loop(record)


def test_exact_mechanism_families():
    for token in ('PREVIOUS_SCAN', 'RUNNING_SCAN_CHAIN', 'NEAR_CHAIN',
                  'TRY_CLOSE_LOOP'):
        record = {'creation_provenance': token}
        assert constraint_family(record) == token


def test_gt_gauge_and_shared_estimator_effect():
    slam = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    gt = [[2.0, -1.0, math.pi / 2], [2.0, 0.0, math.pi / 2],
          [1.0, -1.0, math.pi / 2]]
    gauge = freeze_world_gauge(slam, gt)
    result = estimator_effect_sanity(slam, slam, gt, gauge)
    assert result['before']['translation_rmse_m'] == pytest.approx(0.0)
    assert result['delta_translation_rmse_m'] == pytest.approx(0.0)


def test_physical_and_backend_lock_names_are_frozen():
    payload = protocol.preregistration_payload()
    assert payload['collection_and_replay_locks']['physical'] == \
        'collection/PHYSICAL_COLLECTION_LOCK.json'
    assert payload['collection_and_replay_locks']['backend'] == \
        'collection/BACKEND_REPLAY_LOCK.json'
