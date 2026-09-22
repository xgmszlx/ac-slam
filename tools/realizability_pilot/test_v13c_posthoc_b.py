#!/usr/bin/python3
"""Tests for the frozen Target-B post-hoc diagnostic tooling."""

import json
import math
import sys
from pathlib import Path
from unittest import mock

import pytest

import v13c_posthoc_b_protocol

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

from common_prefix_analysis import edges_from_graph, nodes_from_graph
from confirmatory_v13c_analysis import target_information
from stitch_probe_stream import stitch
from v13_unified_replay import evaluate_prefix_reference
from v13c_posthoc_b_analysis import decision
from v13c_posthoc_b_protocol import (
    DECISION_LABELS, ROOT, SOURCE_ROOT, preregistration_payload,
    source_immutability_manifest, verify_source_immutable,
)
from v13c_posthoc_b_replay import (
    crop_records, decompose_capture, replay_directory, wrap_angle,
)


def _records(count, start=10.0):
    return [{'stamp': start + 0.1 * index, 'x': float(index), 'y': 0.0,
             'yaw': 0.0, 'ranges': [1.0], 'angle_min': -1.0,
             'angle_max': 1.0, 'angle_increment': 1.0,
             'range_min': 0.0, 'range_max': 10.0,
             'frame_id': 'laser', 'robot_id': 1, 'laser_type': 0}
            for index in range(count)]


def _summary(values):
    return {'D_sweep': {
        'values': values,
        'positive': sum(value > 0 for value in values),
        'mean': sum(values) / len(values),
        'H1_H3_values': values[:3],
        'H1_H3_positive': sum(value > 0 for value in values[:3]),
        'H1_H3_mean': sum(values[:3]) / 3.0,
    }}


def test_wrap_angle_geometry():
    assert wrap_angle(3.0 * math.pi) == pytest.approx(math.pi)
    assert wrap_angle(-3.0 * math.pi) == pytest.approx(-math.pi)
    assert abs(wrap_angle(0.2 - (2.0 * math.pi + 0.2))) < 1e-12


def test_action_timing_decomposition_closes():
    path = (SOURCE_ROOT / 'target_B/1/A2_SWEEP90/raw_attempt_01/'
            'capture_result.json')
    row = decompose_capture(path, 'V13C', 'B-H1')
    assert row['arm'] == 'A2_SWEEP90'
    assert row['action_motion_duration_s'] > 0.0
    assert abs(row['timing_decomposition_residual_s']) < 1e-9
    assert row['A2_sweep_plus30_duration_s'] > 0.0


def test_crop_exact_n_and_order_and_static_tail():
    records = _records(8)
    gt = [[10.0 + 0.1 * index, 0.0, 0.0, 0.0]
          for index in range(8)]
    kept, report = crop_records(records, 5, 10.5, gt)
    assert kept == records[:5]
    assert len(kept) == 5
    assert report['removed_scans'] == 3
    assert report['record_order_preserved']
    assert report['cropping_valid']


def test_crop_refuses_action_phase_deletion():
    records = _records(8)
    gt = [[10.0 + 0.1 * index, 0.0, 0.0, 0.0]
          for index in range(8)]
    with pytest.raises(ValueError, match='action-phase deletion'):
        crop_records(records, 5, 10.7, gt)


def test_crop_refuses_moving_tail():
    records = _records(8)
    gt = [[10.0 + 0.1 * index, 0.02 * index, 0.0, 0.0]
          for index in range(8)]
    with pytest.raises(ValueError, match='removed tail moved'):
        crop_records(records, 5, 10.5, gt)


def test_stitch_preserves_exact_prefix(tmp_path):
    prefix = tmp_path / 'prefix.jsonl'
    probe = tmp_path / 'probe.jsonl'
    combined = tmp_path / 'combined.jsonl'
    prefix_rows = _records(3, 0.0)
    probe_rows = _records(2, 10.0)
    prefix.write_text(''.join(json.dumps(row, separators=(',', ':')) + '\n'
                              for row in prefix_rows))
    probe.write_text(''.join(json.dumps(row, separators=(',', ':')) + '\n'
                             for row in probe_rows))
    report = stitch(prefix, probe, combined)
    assert report['prefix_byte_identical']
    assert combined.read_bytes().startswith(prefix.read_bytes())


def test_full_and_matched_directories_are_separate(tmp_path):
    full = replay_directory(tmp_path, 'FULL', 'B-H1', 'A1_DWELL')
    matched = replay_directory(tmp_path, 'MATCHED', 'B-H1', 'A1_DWELL')
    assert full != matched
    assert '/FULL/' in str(full)
    assert '/MATCHED/' in str(matched)


def test_original_v13c_root_manifest_is_immutable():
    manifest = source_immutability_manifest()
    check = verify_source_immutable(manifest)
    assert check['passed']
    assert not check['mismatched_files']


def test_zero_tolerance_prefix_gate():
    graph = json.loads((
        ROOT / 'results/realizability_pilot/p1_v13_technical_20260920/'
        'histories/target_B/seed_82005/prefix_replays/repeat_01/'
        'graph_pre.json').read_text())
    result = evaluate_prefix_reference(graph, graph, target_ids=[19, 20, 22])
    assert result['passed']
    changed = json.loads(json.dumps(graph))
    changed['nodes'][0]['x'] += 1e-12
    result = evaluate_prefix_reference(graph, changed, target_ids=[19, 20, 22])
    assert not result['passed']


def test_primary_j_t_matches_original_b_h4():
    graph = json.loads((
        SOURCE_ROOT / 'target_B/4/A1_DWELL/replay_attempt_01/'
        'graph_final.json').read_text())
    nodes = nodes_from_graph(graph)
    edges = edges_from_graph(graph, nodes)
    result = target_information(nodes, edges, [19, 20, 22, 24, 25])
    rows = list(__import__('csv').DictReader(open(
        SOURCE_ROOT / 'analysis/branch_metrics.csv')))
    expected = next(float(row['J_T']) for row in rows
                    if row['block_id'] == 'target_B_H4' and
                    row['arm'] == 'A1_DWELL')
    assert result['J_T'] == expected


@pytest.mark.parametrize('full,matched,crop,expected', [
    ([0.1, 0.2, -0.1, 0.3], [0.1, 0.1, -0.1, 0.2], True,
     DECISION_LABELS[0]),
    ([-0.1, -0.2, 0.1, -0.1], [-0.1, -0.2, 0.1, -0.1], True,
     DECISION_LABELS[2]),
    ([0.1, -0.2, 0.1, 0.3], [0.1, -0.2, -0.1, 0.3], True,
     DECISION_LABELS[1]),
    ([0.1, 0.2, -0.1, 0.3], [0.1, 0.1, -0.1, 0.2], False,
     DECISION_LABELS[1]),
])
def test_decision_gate_edges(full, matched, crop, expected):
    assert decision(_summary(full), _summary(matched), crop) == expected


def test_preregistration_schema_and_nonconfirmatory_label():
    # The builder is intentionally locked to its historical source commit.
    # Exercise its frozen schema without making every later research commit
    # fail this regression test solely because HEAD advanced.
    with mock.patch('v13c_posthoc_b_protocol.git_head', return_value=(
            v13c_posthoc_b_protocol.BASE_COMMIT)):
        payload = preregistration_payload()
    required = {
        'protocol_id', 'label', 'source_commit',
        'original_v13C_protocol_sha256', 'source_capture_hashes',
        'code_hashes', 'code_bundle_sha256', 'analysis_sha256', 'blocks',
        'full_replay_definition', 'exposure_matched_definition',
        'budget_geometry_forensic', 'estimand', 'mechanism_metrics',
        'decision_gate', 'posthoc_descriptive_only',
    }
    assert required <= set(payload)
    assert payload['label'] == 'POSTHOC_NONCONFIRMATORY_TARGET_B_DIAGNOSTIC'
    assert payload['confirmatory'] is False
    assert payload['B_H4_ENDPOINT_PREVIOUSLY_OBSERVED'] is True
    assert len(payload['blocks']) == 4
