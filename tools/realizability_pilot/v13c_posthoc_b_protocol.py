#!/usr/bin/python3
"""Frozen protocol and preregistration for the v13-C Target-B diagnostic."""

import hashlib
import json
import subprocess
from pathlib import Path

from controlled_branch_suite import atomic_json


ROOT = Path(__file__).resolve().parents[2]
BASE_COMMIT = '9edba1dbe2e397aa074f4cf11d9035bc40bf4b5c'
PROTOCOL_ID = 'p1_v13c_posthoc_targetB_20260921'
SOURCE_ROOT = (ROOT / 'results/realizability_pilot' /
               'p1_confirmatory_v13c_20260921')
RESULT_ROOT = (ROOT / 'results/realizability_pilot' /
               'p1_v13c_posthoc_targetB_20260921')
V12B_ROOT = (ROOT / 'results/realizability_pilot' /
             'p1_confirmatory_v12b_20260918')
PREREGISTRATION_PATH = (
    RESULT_ROOT / 'preregistration/posthoc_diagnostic_preregistration.json')

ARMS = ('A1_DWELL', 'A3_MIN_TRIGGER', 'A2_SWEEP90')
BLOCKS = ('B-H1', 'B-H2', 'B-H3', 'B-H4')
BLOCK_NUMBERS = {'B-H1': 1, 'B-H2': 2, 'B-H3': 3, 'B-H4': 4}
REPLAY_MODES = ('FULL', 'MATCHED')
RATE_HZ = 20.0

# Frozen before inspecting backend endpoints.  They are physical/controller
# tolerances only and are never tuned against J_T or graph outcomes.
TAIL_TRANSLATION_TOLERANCE_M = 0.01
TAIL_YAW_TOLERANCE_RAD = 0.01
CROP_STAMP_EPSILON_S = 1e-9

# Outcome-blind budget-geometry forensic rule.  The thresholds exceed the
# controller's 0.1 s timing quantisation while remaining below the 1.5 s
# original budget gate.
FORENSIC_RULE = {
    'calibration_and_H4_max_abs_dwell_error_s': 0.5,
    'failed_block_min_max_abs_dwell_error_s': 1.0,
    'failed_block_min_rotation_demand_shift_rad': 0.25,
    'H4_max_rotation_demand_shift_rad': 0.15,
    'timing_decomposition_residual_max_s': 0.2,
}

DECISION_LABELS = (
    'DIAGNOSTIC_SUPPORTS_ONE_PROSPECTIVE_RETRY',
    'DIAGNOSTIC_MIXED_REDESIGN_BEFORE_RETRY',
    'DIAGNOSTIC_ARGUES_AGAINST_PROSPECTIVE_RETRY',
)


def load_json(path):
    return json.loads(Path(path).read_text())


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_json_sha(payload):
    encoded = json.dumps(
        payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def git_head():
    return subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=str(ROOT), text=True).strip()


def source_block_dir(block_id):
    return SOURCE_ROOT / 'target_B' / str(BLOCK_NUMBERS[block_id])


def source_capture_dir(block_id, arm):
    return source_block_dir(block_id) / arm / 'raw_attempt_01'


def source_capture_files(block_id, arm):
    directory = source_capture_dir(block_id, arm)
    return [directory / name for name in (
        'capture_result.json', 'capture_spec.json',
        'probe_gt_trajectory.txt', 'probe_stream_raw.jsonl')]


def source_immutability_manifest():
    paths = [SOURCE_ROOT / 'COLLECTION_LOCKED.json',
             SOURCE_ROOT / 'preregistration/v13C_preregistration.json',
             SOURCE_ROOT / 'collection/collection_state.json',
             SOURCE_ROOT / 'decision/final_gate.json']
    for block_id in BLOCKS:
        block = source_block_dir(block_id)
        paths.extend([block / 'action_specs.json', block / 'frozen_target.json',
                      block / 'prefix_reference.json'])
        for arm in ARMS:
            paths.extend(source_capture_files(block_id, arm))
    records = {str(path.relative_to(ROOT)): sha256(path) for path in paths}
    return {'files': records, 'bundle_sha256': canonical_json_sha(records)}


def verify_source_immutable(expected):
    observed = source_immutability_manifest()
    return {
        'passed': observed == expected,
        'expected_bundle_sha256': expected['bundle_sha256'],
        'observed_bundle_sha256': observed['bundle_sha256'],
        'mismatched_files': sorted(
            path for path, digest in expected['files'].items()
            if observed['files'].get(path) != digest),
    }


def frozen_blocks():
    manifest = load_json(
        SOURCE_ROOT / 'preregistration/v13C_frozen_history_manifest.json')
    rows = manifest['selected_blocks']['target_B']
    if len(rows) != 4:
        raise RuntimeError('expected four frozen Target-B histories')
    output = []
    for index, row in enumerate(rows, 1):
        expected = 'target_B_H{}'.format(index)
        if row['block_id'] != expected:
            raise RuntimeError('unexpected source block order')
        output.append({
            'block_id': 'B-H{}'.format(index),
            'source_block_id': row['block_id'],
            'seed': int(row['seed']),
            'local_five_target_state_ids': list(
                row['selected_five_state_ids']),
            'action_anchor_state_id': int(row['action_anchor_state_id']),
        })
    return output


def prefix_reference(block_id):
    record = load_json(source_block_dir(block_id) / 'prefix_reference.json')
    return {
        'canonical_prefix_path': record['canonical_prefix_path'],
        'canonical_prefix_sha256': record['canonical_prefix_sha256'],
        'canonical_prefix_record_count': record[
            'canonical_prefix_record_count'],
        'mapper_params_path': record['mapper_params_path'],
        'mapper_params_file_sha256': record['mapper_params_file_sha256'],
        'mapper_params_normalized_sha256': record[
            'mapper_params_normalized_sha256'],
        'mapper_binary_path': record['mapper_binary_path'],
        'mapper_binary_sha256': record['mapper_binary_sha256'],
        'prefix_reference_graph_path': record[
            'prefix_reference_graph_path'],
        'prefix_reference_graph_sha256': record[
            'prefix_reference_graph_sha256'],
        'prefix_structural_signature_sha256': record[
            'prefix_structural_signature_sha256'],
        'local_five_target_state_ids': record[
            'local_five_target_state_ids'],
        'numerical_tolerance': record['numerical_tolerance'],
    }


def relevant_code_files():
    names = [
        'tools/realizability_pilot/v13c_posthoc_b_protocol.py',
        'tools/realizability_pilot/v13c_posthoc_b_replay.py',
        'tools/realizability_pilot/v13c_posthoc_b_analysis.py',
        'tools/realizability_pilot/test_v13c_posthoc_b.py',
        'tools/realizability_pilot/v13_unified_replay.py',
        'tools/realizability_pilot/v13_prefix_equivalence.py',
        'tools/realizability_pilot/v13_replay_publisher.py',
        'tools/realizability_pilot/stitch_probe_stream.py',
        'tools/realizability_pilot/controlled_probe_capture.py',
        'tools/realizability_pilot/confirmatory_v12_protocol.py',
        'tools/realizability_pilot/confirmatory_v13c_analysis.py',
        'tools/realizability_pilot/se2_information.py',
        'tools/realizability_pilot/edge_analytics.py',
        'tools/realizability_pilot/common_prefix_analysis.py',
        'dependencies/navigation_2d/nav2d_karto/src/MultiMapper.cpp',
        'dependencies/navigation_2d/nav2d_karto/include/nav2d_karto/MultiMapper.h',
    ]
    return [ROOT / name for name in names]


def preregistration_payload():
    if git_head() != BASE_COMMIT:
        raise RuntimeError('post-hoc diagnostic source commit changed')
    original_protocol = SOURCE_ROOT / 'preregistration/v13C_preregistration.json'
    code_hashes = {str(path.relative_to(ROOT)): sha256(path)
                   for path in relevant_code_files()}
    blocks = frozen_blocks()
    source_manifest = source_immutability_manifest()
    return {
        'protocol_id': PROTOCOL_ID,
        'label': 'POSTHOC_NONCONFIRMATORY_TARGET_B_DIAGNOSTIC',
        'confirmatory': False,
        'source_commit': BASE_COMMIT,
        'B_H4_ENDPOINT_PREVIOUSLY_OBSERVED': True,
        'new_unobserved_backend_endpoints_at_freeze': [
            'B-H1', 'B-H2', 'B-H3'],
        'original_v13C_root': str(SOURCE_ROOT.relative_to(ROOT)),
        'original_v13C_protocol_sha256': sha256(original_protocol),
        'original_v13C_final_gate':
            'CONFIRMATORY_EXPERIMENT_TECHNICALLY_INCOMPLETE',
        'original_v13C_root_immutable': True,
        'source_capture_hashes': source_manifest,
        'code_hashes': code_hashes,
        'code_bundle_sha256': canonical_json_sha(code_hashes),
        'analysis_sha256': code_hashes[
            'tools/realizability_pilot/v13c_posthoc_b_analysis.py'],
        'blocks': [{**row, 'prefix_reference': prefix_reference(row['block_id'])}
                   for row in blocks],
        'planned_full_replays': 12,
        'planned_matched_replays': 12,
        'full_replay_definition': {
            'input': 'unaltered existing v13-C raw capture stream',
            'arms': list(ARMS),
            'blocks': list(BLOCKS),
            'rate_hz': RATE_HZ,
            'fresh_ros_master_and_mapper_per_branch': True,
            'processed_callback_count_barrier': True,
            'synchronous_graph_dump': True,
            'fixed_sleep_drain_forbidden': True,
            'background_graph_dump_forbidden': True,
            'zero_tolerance_prefix_reference_gate': True,
        },
        'exposure_matched_definition': {
            'N_match': 'minimum original raw scan count within each block',
            'operation': 'TAIL_TRUNCATION_ONLY',
            'record_order_preserved': True,
            'removed_scan_condition':
                'stamp >= frozen final_static_hold_start',
            'A1_final_static_hold_start': 'dwell.end_time',
            'A3_final_static_hold_start': 'dwell.end_time',
            'A2_final_static_hold_start': 'sweep_+30deg.end_time',
            'removed_tail_translation_tolerance_m':
                TAIL_TRANSLATION_TOLERANCE_M,
            'removed_tail_yaw_tolerance_rad': TAIL_YAW_TOLERANCE_RAD,
            'invalid_label': 'EXPOSURE_MATCH_NOT_IDENTIFIABLE',
            'interpretation':
                'post-hoc equal-scan sensitivity, not a physical counterfactual',
        },
        'budget_geometry_forensic': {
            'backend_outcomes_forbidden': True,
            'treatment_start': 'probe_arrival.start_time',
            'motion_duration':
                'final arm-specific move end minus treatment start',
            'required_A1_dwell': 'T_motion_A2 - T_motion_A1',
            'required_A3_dwell': 'T_motion_A2 - T_motion_A3',
            'frozen_target_B_dwell_s': {
                'A1_DWELL': 11.4, 'A3_MIN_TRIGGER': 7.0,
                'A2_SWEEP90': 0.0},
            'decision_rule': FORENSIC_RULE,
            'allowed_labels': [
                'GEOMETRY_DEPENDENT_CALIBRATION_SUPPORTED',
                'GEOMETRY_DEPENDENT_CALIBRATION_NOT_SUPPORTED',
                'FORENSIC_INCONCLUSIVE'],
        },
        'estimand': {
            'state_subset': 'original frozen five local historical states',
            'dimension': 15,
            'estimator': ('fixed-first-pose fixed-linearisation local '
                          'linear-Gaussian joint marginal covariance'),
            'J_T': '-logdet(Sigma_T)/15',
            'primary': 'D_sweep = J_T(A2_SWEEP90)-J_T(A3_MIN_TRIGGER)',
            'secondary': [
                'D_trigger = J_T(A3_MIN_TRIGGER)-J_T(A1_DWELL)',
                'D_total = J_T(A2_SWEEP90)-J_T(A1_DWELL)'],
        },
        'mechanism_metrics': [
            'accepted keyscan count', 'E_T', 'E_N', 'local edges',
            'all new edges', 'creation provenance', 'matcher type',
            'match response', 'edge covariance eigenvalues',
            'information eigenvalues', 'insertion-time graph geodesic',
            'insertion-time hop count', 'cycle size',
            'exact target-edge endpoint identity'],
        'explicit_loop_rule':
            'only matcher/provenance records containing TRY_CLOSE_LOOP',
        'decision_gate': {
            'support': {
                'label': DECISION_LABELS[0],
                'FULL_H1_H3_positive_min': 2,
                'FULL_H1_H3_mean_gt': 0.0,
                'FULL_H1_H4_positive_min': 3,
                'MATCHED_H1_H3_positive_min': 2,
                'MATCHED_H1_H3_mean_gt': 0.0,
                'MATCHED_H1_H4_positive_min': 3,
                'FULL_and_MATCHED_target_B_means_positive_same_sign': True,
                'not_driven_only_by_B_H4': True,
                'all_exposure_matching_technical_gates_valid': True,
            },
            'against': {
                'label': DECISION_LABELS[2],
                'both_modes_H1_H3_positive_max': 1,
                'both_modes_H1_H3_mean_le': 0.0,
                'both_modes_all_B_positive_max': 2,
                'both_modes_all_B_mean_le': 0.0,
            },
            'otherwise': DECISION_LABELS[1],
        },
        'posthoc_descriptive_only': True,
        'v12_v12b_pooling_allowed': False,
        'v13C_confirmatory_sample_membership_changed': False,
        'new_stage_or_physical_capture_allowed': False,
        'automatic_next_phase_allowed': False,
    }


def write_preregistration(path=PREREGISTRATION_PATH):
    path = Path(path)
    payload = preregistration_payload()
    if path.exists():
        if load_json(path) != payload:
            raise RuntimeError('refusing to alter frozen post-hoc preregistration')
        return payload
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(path, payload)
    return payload

