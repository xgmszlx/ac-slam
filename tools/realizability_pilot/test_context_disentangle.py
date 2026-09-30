#!/usr/bin/python3
"""Protocol and controller-boundary tests for CD-T certification."""

import pytest

import context_disentangle_protocol as protocol
from context_disentangle_technical import (
    controlled_spec, deconfounding_summary, forbidden_scientific_outputs,
)
from v14t_fixed_scan_protocol import fixed_scan_stream_diagnostics


@pytest.mark.parametrize('arm', protocol.ARMS)
def test_exact_cumulative_yaw_generator(arm):
    motion = protocol.dose_motion(0.73, arm)
    assert motion['planned_cumulative_abs_yaw_rad'] == pytest.approx(
        protocol.DOSES[arm], abs=1e-12)


def test_same_final_heading_for_all_doses():
    theta0 = -2.4
    motions = [protocol.dose_motion(theta0, arm) for arm in protocol.ARMS]
    assert all(protocol.wrap_angle(row['final_heading_rad'] - theta0) ==
               pytest.approx(0.0, abs=1e-12) for row in motions)


def test_planned_dose_monotonicity():
    assert (protocol.DOSES['D0_ZERO'] < protocol.DOSES['D1_THRESHOLD'] <
            protocol.DOSES['D2_HIGH'])


def test_fixed_first_n_sensing_stream_and_completion_before_n():
    records = [{'stamp': float(value)} for value in range(400)]
    result = fixed_scan_stream_diagnostics(records, 10.0, 60.0, 347)
    assert len(result['scientific_records']) == 347
    assert result['scientific_records'] == result['treatment_records'][:347]
    assert result['completion_scan_index'] < 347
    assert result['completion_margin'] >= protocol.MIN_COMPLETION_MARGIN


def _technical_rows():
    rows = []
    values = {
        'D0_ZERO': ([0.003, 0.005, 0.004, 0.006],
                    [0.004, 0.006, 0.005, 0.007], [3, 4, 3, 4], [3, 4, 3, 4]),
        'D1_THRESHOLD': ([1.04, 1.05, 1.06, 1.07],
                         [1.05, 1.06, 1.07, 1.08], [24, 25, 26, 27],
                         [25, 26, 27, 28]),
        'D2_HIGH': ([3.09, 3.10, 3.11, 3.12],
                    [3.10, 3.11, 3.12, 3.13], [65, 66, 67, 68],
                    [66, 67, 68, 69]),
    }
    for arm, (a_dose, b_dose, a_scan, b_scan) in values.items():
        for target, doses, scans in (
                ('target_A', a_dose, a_scan),
                ('target_B', b_dose, b_scan)):
            for index, (dose, scan) in enumerate(zip(doses, scans), 1):
                rows.append({'target': target, 'block': '{}_H{}'.format(
                    target, index), 'arm': arm,
                    'actual_cumulative_yaw_rad': dose,
                    'completion_scan_index': scan})
    return rows


def test_target_dose_overlap_gate():
    result = deconfounding_summary(_technical_rows())
    assert result['dose_target_deconfounding_certified']
    assert result['machine_label'] == (
        'DOSE_TARGET_DECONFOUNDING_TECHNICALLY_CERTIFIED')


def test_block_paired_statistical_unit_and_interaction():
    rows = [
        {'target': 'target_A', 'J_D1_THRESHOLD': 1.0, 'J_D2_HIGH': 1.1},
        {'target': 'target_A', 'J_D1_THRESHOLD': 2.0, 'J_D2_HIGH': 2.2},
        {'target': 'target_B', 'J_D1_THRESHOLD': 1.0, 'J_D2_HIGH': 1.4},
        {'target': 'target_B', 'J_D1_THRESHOLD': 2.0, 'J_D2_HIGH': 2.6},
    ]
    result = protocol.interaction_contrast(rows)
    assert result['C_HT_A'] == pytest.approx(0.15)
    assert result['C_HT_B'] == pytest.approx(0.50)
    assert result['I_HT'] == pytest.approx(0.35)
    plan = protocol.statistical_analysis_plan(8)
    assert plan['statistical_unit'] == 'canonical-history block'
    assert plan['design']['branch_count_not_independent_n'] == 48
    assert plan['inference']['branch_pseudoreplication_forbidden']


def test_sample_size_simulation_is_deterministic():
    first, first_source = protocol.simulate_sample_size(repetitions=300, seed=7)
    second, second_source = protocol.simulate_sample_size(repetitions=300, seed=7)
    assert first == second
    assert first_source == second_source


def test_old_geometry_specs_share_start_and_final_theta0():
    for target in protocol.TARGETS:
        specs = {arm: controlled_spec(target, 1, arm)
                 for arm in protocol.ARMS}
        anchors = [row['action_waypoints'][row['core_action_start_index']]
                   for row in specs.values()]
        assert anchors[0] == anchors[1] == anchors[2]
        theta0 = anchors[0][2]
        assert all(protocol.wrap_angle(
            row['action_waypoints'][-1][2] - theta0) ==
            pytest.approx(0.0, abs=1e-12) for row in specs.values())


def test_pretreatment_descriptor_is_capture_side_only():
    record = {
        'stamp': 4.0, 'x': 1.0, 'y': 2.0, 'yaw': 0.3,
        'range_min': 0.1, 'range_max': 10.0,
        'ranges': [0.2, 0.5, 1.0, 2.0, 5.0, float('inf')],
    }
    result = protocol.pretreatment_scan_descriptor(
        record, sectors=3, histogram_bins=5)
    assert result['strictly_pretreatment']
    assert result['descriptor_affects_backend_input'] is False
    assert result['valid_return_ratio'] == pytest.approx(5 / 6)


def test_frozen_v14_and_heterogeneity_artifacts_unchanged():
    result = protocol.frozen_provenance()
    assert result['passed']
    assert result['v14_worktree_clean']
    assert result['v14h_worktree_clean']
    assert result['v14_critical_failures'] == []


def test_no_scientific_endpoint_generation():
    assert forbidden_scientific_outputs() == []
