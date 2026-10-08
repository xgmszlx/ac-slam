#!/usr/bin/python3
"""Pre-collection boundary tests for the prospective CD experiment."""

import hashlib
import json
from collections import Counter

import pytest

import cd_confirmatory_protocol as protocol
from cd_confirmatory_analysis import (
    interaction_point, primary_decision,
    target_stratified_interaction_bootstrap,
)
from cd_confirmatory_collection import (
    fresh_manipulation_gate, validate_capture,
)
from cd_confirmatory_guard import (
    assert_backend_lock_allows_analysis,
    assert_prelock_no_scientific_outputs,
)
from cd_confirmatory_qualification import first_eight_eligible
from v14t_fixed_scan_protocol import fixed_scan_stream_diagnostics


def test_preregistration_is_prospective_and_immutable(tmp_path):
    payload = protocol.preregistration_payload()
    assert payload['created_before_any_fresh_history_generation']
    assert payload['intervention']['N'] == 347
    assert payload['estimands']['primary_I_HT'] == 'C_HT_B-C_HT_A'
    assert payload['estimands']['co_primary_contrasts'] == []
    path = tmp_path / 'prereg.json'
    protocol.write_frozen_json(path, payload)
    protocol.write_frozen_json(path, payload)
    changed = dict(payload, label='changed')
    with pytest.raises(RuntimeError):
        protocol.write_frozen_json(path, changed)


def test_first_eight_eligible_uses_frozen_order_without_substitution():
    records = [{
        'target_label': 'target_A',
        'seed': seed,
        'status': ('TECHNICALLY_INELIGIBLE'
                   if seed in (101001, 101003) else 'TECHNICALLY_ELIGIBLE'),
    } for seed in reversed(protocol.CANDIDATE_SEEDS['target_A'])]
    selected = first_eight_eligible(records, 'target_A')
    assert [row['seed'] for row in selected] == [
        101002, 101004, 101005, 101006, 101007, 101008, 101009, 101010]
    payload = protocol.preregistration_payload()
    qualification = payload['history_qualification']
    assert qualification['reserve_or_substitution_allowed'] is False
    assert qualification['first_eight_eligible_rule'] is True


def test_reserve_history_substitution_is_forbidden():
    payload = protocol.preregistration_payload()
    assert payload['history_qualification'][
        'reserve_or_substitution_allowed'] is False
    assert payload['technical_retry_rule'][
        'reserve_history_substitution_forbidden'] is True


def test_repeated_measure_arm_orders_are_complete_and_balanced():
    for target in protocol.TARGETS:
        assert len(protocol.ARM_ORDERS[target]) == 8
        counts = {arm: Counter() for arm in protocol.ARMS}
        for order in protocol.ARM_ORDERS[target]:
            assert sorted(order) == sorted(protocol.ARMS)
            for position, arm in enumerate(order, 1):
                counts[arm][position] += 1
        for arm in protocol.ARMS:
            values = [counts[arm][position] for position in (1, 2, 3)]
            assert max(values) - min(values) <= 1


def test_exact_first_347_and_completion_margin():
    records = [{'stamp': float(value)} for value in range(400)]
    result = fixed_scan_stream_diagnostics(records, 10.0, 60.0, 347)
    assert len(result['scientific_records']) == 347
    assert result['scientific_records'] == result['treatment_records'][:347]
    assert result['completion_scan_index'] < 347
    assert result['completion_margin'] >= protocol.MIN_COMPLETION_MARGIN


def _write_capture_files(directory):
    for name in (
            'capture_result.json', 'capture_spec.json',
            'probe_stream_raw.jsonl', 'scientific_treatment_stream.jsonl',
            'probe_gt_trajectory.txt', 'pre_treatment_descriptor.json'):
        (directory / name).write_text('{}\n')


def test_dose_manipulation_capture_checks(tmp_path):
    _write_capture_files(tmp_path)
    spec = {
        'canonical_terminal_gt_pose': [1.0, 2.0, 0.1],
        'action_id': 'D1_THRESHOLD',
    }
    result = {
        'status': 'SUCCEEDED',
        'branch_start_gt_pose': [1.0, 2.0, 0.1],
        'scientific_treatment_scan_count': 347,
        'completion_scan_index': 50,
        'completion_margin': 297,
        'scientific_stream_exact_first_N': True,
        'actual_cumulative_yaw_rad': 1.05,
        'final_heading_residual_rad': 0.02,
        'pre_treatment_descriptor_strict': True,
        'duplicate_timestamp_count': 0,
        'nonmonotonic_timestamp_count': 0,
        'backend_started': False,
        'scientific_endpoint_read': False,
    }
    assert validate_capture(spec, result, tmp_path)['valid']
    result['actual_cumulative_yaw_rad'] = 0.9
    assert not validate_capture(spec, result, tmp_path)['valid']


def _manipulation_rows(separate=False):
    rows = []
    for target in protocol.TARGETS:
        for index in range(8):
            offset = (0.0 if target == 'target_A' else
                      (0.2 if separate else 0.002))
            for arm, dose, scan in (
                    ('D0_ZERO', 0.0, 3),
                    ('D1_THRESHOLD', 1.05 + offset + index * 0.001, 49),
                    ('D2_HIGH', 3.10 + offset + index * 0.001, 81)):
                rows.append({
                    'block_id': '{}_H{}'.format(target, index + 1),
                    'target': target,
                    'arm': arm,
                    'actual_cumulative_yaw_rad': dose,
                    'completion_scan_index': scan,
                })
    return rows


def test_fresh_target_dose_overlap_gate():
    assert fresh_manipulation_gate(_manipulation_rows())['passed']
    failed = fresh_manipulation_gate(_manipulation_rows(separate=True))
    assert not failed['passed']
    assert failed['machine_label'] == 'DOSE_TARGET_DECONFOUNDING_FAILED'


def test_no_peeking_guard_and_backend_lock_requirement(tmp_path):
    analysis = tmp_path / 'analysis'
    decision = tmp_path / 'decision'
    assert assert_prelock_no_scientific_outputs(analysis, decision)
    analysis.mkdir()
    (analysis / 'J_T.csv').write_text('forbidden\n')
    with pytest.raises(RuntimeError):
        assert_prelock_no_scientific_outputs(analysis, decision)

    prereg = tmp_path / 'prereg.json'
    physical = tmp_path / 'physical.json'
    backend = tmp_path / 'backend.json'
    prereg.write_text('{}\n')
    physical.write_text(json.dumps({'complete': True}) + '\n')
    backend.write_text(json.dumps({
        'complete': True,
        'preregistration_sha256': hashlib.sha256(
            prereg.read_bytes()).hexdigest(),
        'physical_collection_lock_sha256': hashlib.sha256(
            physical.read_bytes()).hexdigest(),
    }) + '\n')
    assert assert_backend_lock_allows_analysis(
        prereg, physical, backend)[0]['complete']
    backend.unlink()
    with pytest.raises(RuntimeError):
        assert_backend_lock_allows_analysis(prereg, physical, backend)


def test_backend_lock_is_required_before_analysis(tmp_path):
    prereg = tmp_path / 'prereg.json'
    physical = tmp_path / 'physical.json'
    prereg.write_text('{}\n')
    physical.write_text(json.dumps({'complete': True}) + '\n')
    with pytest.raises(RuntimeError):
        assert_backend_lock_allows_analysis(
            prereg, physical, tmp_path / 'missing_backend.json')


def _primary_rows(a_values, b_values):
    return ([{'block_id': 'target_A_H{}'.format(index + 1),
              'target': 'target_A', 'C_HT': value}
             for index, value in enumerate(a_values)] +
            [{'block_id': 'target_B_H{}'.format(index + 1),
              'target': 'target_B', 'C_HT': value}
             for index, value in enumerate(b_values)])


def test_interaction_and_stratified_bootstrap_are_deterministic():
    rows = _primary_rows([0.0] * 8, [1.0] * 8)
    means, interaction = interaction_point(rows)
    assert means == {'target_A': 0.0, 'target_B': 1.0}
    assert interaction == pytest.approx(1.0)
    first = target_stratified_interaction_bootstrap(rows)
    second = target_stratified_interaction_bootstrap(rows)
    assert first == second
    assert first['lower_2_5pct'] == pytest.approx(1.0)
    assert first['upper_97_5pct'] == pytest.approx(1.0)


def test_primary_interaction_calculation_is_B_minus_A():
    rows = _primary_rows([0.1, 0.2] * 4, [0.4, 0.6] * 4)
    means, interaction = interaction_point(rows)
    assert means['target_A'] == pytest.approx(0.15)
    assert means['target_B'] == pytest.approx(0.50)
    assert interaction == pytest.approx(0.35)


def test_three_state_gate_truth_table():
    rows = _primary_rows([0.0] * 8, [1.0] * 8)
    support = primary_decision(rows, True, {
        'lower_2_5pct': 0.2, 'upper_97_5pct': 1.5})
    assert support[0] == 'CD_PROSPECTIVE_INTERACTION_SUPPORT'
    no_support = primary_decision(rows, True, {
        'lower_2_5pct': -0.2, 'upper_97_5pct': 1.5})
    assert no_support[0] == 'CD_PROSPECTIVE_NO_INTERACTION_SUPPORT'
    incomplete = primary_decision(rows[:-1], False, None)
    assert incomplete[0] == 'CD_PROSPECTIVE_TECHNICALLY_INCOMPLETE'


def test_frozen_v14_v14h_and_cdt_provenance_unchanged():
    provenance = protocol.frozen_source_provenance()
    assert provenance['passed']
    assert provenance['failures'] == []
    assert provenance['cdt_protocol_sha256'] == \
        protocol.EXPECTED_CDT_PROTOCOL_SHA256


def test_no_scientific_output_exists_before_collection():
    assert not (protocol.RESULT_ROOT / 'analysis').exists()
    assert not (protocol.RESULT_ROOT / 'decision').exists()
