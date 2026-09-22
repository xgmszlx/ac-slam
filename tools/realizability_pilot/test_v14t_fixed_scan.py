#!/usr/bin/python3
"""Regression and protocol-boundary tests for v14-T certification."""

import json
import math
from pathlib import Path

import numpy as np
import pytest

from mechanism_classifier import (constraint_family,
                                  is_explicit_try_close_loop)
from v14_estimator_sanity import (freeze_world_gauge, target_state_errors,
                                  transform_pose)
from v14t_fixed_scan_protocol import (
    POSTHOC_ROOT, ROOT, V13C_ROOT, derive_scan_budget,
    fixed_scan_stream_diagnostics, original_artifact_manifest,
    verify_original_artifacts,
)
from v14t_fixed_scan_technical import assign_phase


FROZEN_ORIGINAL_BUNDLE_SHA256 = (
    'bb4bdae0cdf2f01b561e79c4ba6fbb7aabdde59c9616ed2d12e827309de5d4e7')


@pytest.mark.parametrize('record', [
    {'creation_provenance': 'TRY_CLOSE_LOOP'},
    {'creation_stage': 'TRY_CLOSE_LOOP'},
    {'matcher_type': 'TRY_CLOSE_LOOP'},
])
def test_exact_try_close_loop_classification(record):
    assert is_explicit_try_close_loop(record)
    assert constraint_family(record) == 'TRY_CLOSE_LOOP'


@pytest.mark.parametrize('token', [
    'ADD_EDGES_BEFORE_TRY_CLOSE_LOOP',
    'RUNNING_SCAN_CHAIN',
    'NEAR_CHAIN',
    'PREVIOUS_SCAN',
])
def test_non_explicit_tokens_are_not_try_close_loop(token):
    record = {'creation_provenance': token, 'creation_stage': token,
              'matcher_type': token}
    assert not is_explicit_try_close_loop(record)


def _records(stamps):
    return [{'stamp': float(stamp), 'value': index}
            for index, stamp in enumerate(stamps)]


def test_counter_reset_exact_first_n_and_raw_tail_isolation():
    raw = _records([0, 1, 2, 3, 4, 5, 6, 7])
    result = fixed_scan_stream_diagnostics(raw, 2.0, 4.0, 4)
    assert [row['stamp'] for row in result['treatment_records']] == [2, 3, 4, 5, 6, 7]
    assert [row['stamp'] for row in result['scientific_records']] == [2, 3, 4, 5]
    assert len(raw) > len(result['scientific_records'])
    assert result['completion_scan_index'] == 3
    assert result['completion_margin'] == 1
    assert result['status'] == 'SUCCEEDED'


def test_completion_after_n_fails_closed():
    result = fixed_scan_stream_diagnostics(
        _records([10, 11, 12, 13, 14]), 10.0, 14.0, 4)
    assert result['completion_scan_index'] == 5
    assert result['status'] == (
        'TECHNICAL_INVALID_MANEUVER_EXCEEDS_SCAN_BUDGET')


def test_duplicate_timestamp_is_rejected():
    result = fixed_scan_stream_diagnostics(
        _records([10, 11, 11, 12]), 10.0, 10.0, 4)
    assert result['duplicate_timestamp_count'] == 1
    assert result['status'] == 'TECHNICAL_INVALID_DUPLICATE_TIMESTAMP'


def test_nonmonotonic_timestamp_is_rejected():
    result = fixed_scan_stream_diagnostics(
        _records([10, 12, 11, 13]), 10.0, 10.0, 4)
    assert result['nonmonotonic_timestamp_count'] == 1
    assert result['status'] == 'TECHNICAL_INVALID_NONMONOTONIC_TIMESTAMP'


def test_budget_uses_both_targets_and_is_deterministic():
    first = derive_scan_budget()
    second = derive_scan_budget()
    assert len(first['rows']) == 42
    assert {row['target'] for row in first['rows']} == {'target_A', 'target_B'}
    assert {row['source_kind'] for row in first['rows']} == {
        'V13C', 'V12B_CALIBRATION'}
    assert (first['M'], first['S'], first['N']) == (287, 60, 347)
    assert first == second


def test_phase_boundary_belongs_to_later_phase_and_final_end_is_closed():
    intervals = [('FIRST', 1.0, 2.0), ('SECOND', 2.0, 3.0)]
    assert assign_phase(1.0, intervals) == 'FIRST'
    assert assign_phase(2.0, intervals) == 'SECOND'
    assert assign_phase(3.0, intervals) == 'SECOND'
    assert assign_phase(3.000001, intervals) is None


def test_ambiguous_phase_attribution_fails_closed():
    intervals = [('FIRST', 1.0, 2.5), ('SECOND', 2.0, 3.0)]
    assert assign_phase(2.25, intervals) is None
    assert assign_phase(None, intervals) is None


def test_frozen_gt_gauge_uses_pre_treatment_history():
    source = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    yaw = math.pi / 2.0
    rotation = np.array([[0.0, -1.0], [1.0, 0.0]])
    translation = np.array([4.0, -2.0])
    target = []
    for pose in source:
        xy = rotation @ np.asarray(pose[:2]) + translation
        target.append([float(xy[0]), float(xy[1]), yaw])
    gauge = freeze_world_gauge(source, target)
    assert gauge['fit_source'] == 'PRE_TREATMENT_CANONICAL_HISTORY_ONLY'
    for observed, expected in zip(source, target):
        assert transform_pose(observed, gauge) == pytest.approx(expected)


def test_target_state_gt_error_calculation():
    gauge = {'rotation': [[1.0, 0.0], [0.0, 1.0]],
             'translation': [0.0, 0.0], 'yaw': 0.0}
    result = target_state_errors(
        [[0.0, 0.0, 0.0], [2.0, 0.0, math.pi / 2.0]],
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], gauge)
    assert result['translation_rmse_m'] == pytest.approx(math.sqrt(0.5))
    assert result['heading_mae_rad'] == pytest.approx(math.pi / 4.0)
    assert result['heading_rmse_rad'] == pytest.approx(math.pi / math.sqrt(8.0))


def test_original_v13c_and_posthoc_artifacts_are_unchanged():
    manifest = original_artifact_manifest()
    assert manifest['bundle_sha256'] == FROZEN_ORIGINAL_BUNDLE_SHA256
    assert verify_original_artifacts(manifest)['passed']


def test_original_scientific_and_posthoc_gates_are_unchanged():
    v13c = json.loads((V13C_ROOT / 'decision/final_gate.json').read_text())
    posthoc = json.loads((
        POSTHOC_ROOT / 'decision/posthoc_diagnostic_gate.json').read_text())
    assert v13c['final_scientific_gate'] == (
        'CONFIRMATORY_EXPERIMENT_TECHNICALLY_INCOMPLETE')
    assert posthoc['diagnostic_decision'] == (
        'DIAGNOSTIC_SUPPORTS_ONE_PROSPECTIVE_RETRY')

