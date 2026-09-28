#!/usr/bin/python3
"""Frozen definitions for the v14 prospective confirmatory validation."""

import copy
import hashlib
import json
import subprocess
from pathlib import Path

import confirmatory_v12_protocol as v12
from controlled_branch_suite import atomic_json
from protocol import TARGETS as PILOT_TARGETS


PROTOCOL_ID = 'p1_v14_confirmatory_20260928'
BASE_COMMIT = 'e112208bac21341a4b60a992dfa7434659af405d'
ROOT = Path(__file__).resolve().parents[2]
RESULT_ROOT = ROOT / 'results/realizability_pilot' / PROTOCOL_ID
PREREGISTRATION_PATH = (RESULT_ROOT / 'preregistration' /
                        'v14_confirmatory_preregistration.json')
V14T_ROOT = (ROOT / 'results/realizability_pilot' /
             'p1_v14t_fixed_scan_technical_20260922')
TARGET_IDS = {'target_A': 'map3_grid_anchor_01',
              'target_B': 'map3_grid_anchor_03'}
TARGETS = ('target_A', 'target_B')
ARMS = ('A1_DWELL', 'A3_MIN_TRIGGER', 'A2_SWEEP90')
CANDIDATE_SEEDS = {
    'target_A': list(range(91001, 91017)),
    'target_B': list(range(92001, 92017)),
}
ARM_ORDERS = {
    'target_A': [
        ['A1_DWELL', 'A3_MIN_TRIGGER', 'A2_SWEEP90'],
        ['A3_MIN_TRIGGER', 'A2_SWEEP90', 'A1_DWELL'],
        ['A2_SWEEP90', 'A1_DWELL', 'A3_MIN_TRIGGER'],
        ['A1_DWELL', 'A2_SWEEP90', 'A3_MIN_TRIGGER'],
    ],
    'target_B': [
        ['A3_MIN_TRIGGER', 'A1_DWELL', 'A2_SWEEP90'],
        ['A2_SWEEP90', 'A3_MIN_TRIGGER', 'A1_DWELL'],
        ['A1_DWELL', 'A3_MIN_TRIGGER', 'A2_SWEEP90'],
        ['A3_MIN_TRIGGER', 'A2_SWEEP90', 'A1_DWELL'],
    ],
}
N_SCANS = 347
PREFIX_REPEAT_COUNT = 3
PREFIX_RATE_HZ = 20.0
MAX_CAPTURE_ATTEMPTS = 2
MAX_REPLAY_ATTEMPTS = 2
BOOTSTRAP_SEED = 140928
BOOTSTRAP_REPETITIONS = 10000
J_T_NONTRIVIAL_FLOOR = 1e-4
START_POSITION_TOLERANCE_M = v12.START_POSITION_TOLERANCE_M
START_HEADING_TOLERANCE_RAD = v12.START_HEADING_TOLERANCE_RAD
EXPECTED_MAPPER_BINARY_SHA256 = (
    '7ab54496b4572e831d7f10d615ad3d700bec3a0b89c5abdb9c562616a67d92f6')
EXPECTED_NORMALIZED_MAPPER_CONFIG_SHA256 = (
    '511dcacb4ff58a99d0f434cbfd604198c95f453e2bd18e35c0b5e0533437825c')
FROZEN_ZERO_TOLERANCE = {
    'node_translation_max_m': 0.0,
    'node_heading_max_rad': 0.0,
    'edge_translation_measurement_max_m': 0.0,
    'edge_heading_measurement_max_rad': 0.0,
    'edge_covariance_max_abs': 0.0,
}
HISTORY_MANIFEST_PATH = RESULT_ROOT / 'qualification/frozen_history_manifest.json'
ARM_ORDER_MANIFEST_PATH = RESULT_ROOT / 'collection/frozen_arm_order_manifest.json'


def load_json(path):
    return json.loads(Path(path).read_text())


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git_head():
    return subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=str(ROOT), text=True).strip()


def write_frozen_json(path, payload):
    path = Path(path)
    if path.exists():
        if load_json(path) != payload:
            raise RuntimeError('refusing to modify frozen {}'.format(path))
        return payload
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(path, payload)
    return payload


def history_spec(target_label, seed):
    if int(seed) not in CANDIDATE_SEEDS[target_label]:
        raise ValueError('seed is outside the frozen v14 pool')
    target_id = TARGET_IDS[target_label]
    spec = copy.deepcopy(PILOT_TARGETS[target_id])
    episode_id = 'v14_{}_s{}'.format(target_label, int(seed))
    spec.update({
        'protocol_version': PROTOCOL_ID,
        'target_id': target_id,
        'condition_id': 'v14_history_qualification_only',
        'action_id': 'history_only',
        'delta_yaw_deg': 0.0,
        'lateral_offset_m': 0.0,
        'maneuver_type': 'pass',
        'neutral_offset_m': 0.0,
        'diagnostics_enabled': False,
        'provenance_enabled': True,
        'observer_enabled': True,
        'instrumentation_flush_period_s': 0.0,
        'tsp_seed': int(seed),
        'block_id': episode_id,
        'block_position': 0,
        'repeat': 1,
        'sequence': 1,
        'episode_id': episode_id,
        'record_replay_stream': True,
        'stop_after_history': True,
    })
    return spec


def candidate_dir(target_label, seed):
    return (RESULT_ROOT / 'qualification/candidates' / target_label /
            'seed_{}'.format(int(seed)))


def source_attempt(target_label, seed):
    return candidate_dir(target_label, seed) / 'attempt_01'


def frozen_history_manifest():
    manifest = load_json(HISTORY_MANIFEST_PATH)
    if not manifest.get('pool_complete'):
        raise RuntimeError('v14 history pool is not complete')
    if manifest.get('technical_gate') != 'V14_HISTORY_QUALIFICATION_PASS':
        raise RuntimeError('v14 history qualification did not pass')
    return manifest


def frozen_blocks():
    manifest = frozen_history_manifest()
    return [row for target in TARGETS
            for row in manifest['selected_blocks'][target]]


def frozen_target_payload(block):
    attempt = source_attempt(block['target_label'], block['seed'])
    snapshot = load_json(attempt / 'pose_graph_before.json')
    nodes = {int(row['id']): row for row in snapshot['nodes']}
    unique = {int(row['id']): int(row['unique_id'])
              for row in snapshot['full_pose_nodes']}
    segment = []
    for state_id in block['target_state_ids']:
        row = nodes[int(state_id)]
        segment.append({
            'id': int(state_id), 'unique_id': unique[int(state_id)],
            'x': float(row['x']), 'y': float(row['y']),
            'theta': float(row['theta']),
            'observed_time': row.get('observed_time'),
        })
    anchor_row = nodes[int(block['anchor_state_id'])]
    route = load_json(attempt / 'resolved_history_route.json')
    return {
        'protocol': 'v14 frozen block-local target subset',
        'target_label': block['target_label'],
        'target_id': block['target_id'],
        'historical_scan_ids': list(block['target_state_ids']),
        'historical_unique_ids': list(block['target_unique_ids']),
        'exact_state_count': 5,
        'segment_nodes': segment,
        'anchor_scan': {
            'id': int(block['anchor_state_id']),
            'unique_id': unique[int(block['anchor_state_id'])],
            'x': float(anchor_row['x']), 'y': float(anchor_row['y']),
            'theta': float(anchor_row['theta']),
            'observed_time': anchor_row.get('observed_time'),
        },
        'route_start_node_count': int(route['route_start_node_count']),
        'frozen_before_action_collection': True,
        'selection_source': str(HISTORY_MANIFEST_PATH.relative_to(ROOT)),
    }


def action_specs(block):
    attempt = source_attempt(block['target_label'], block['seed'])
    frozen = frozen_target_payload(block)
    payload = v12.action_specs(attempt, frozen, 0.0)
    payload['common'].update({
        'protocol_id': PROTOCOL_ID,
        'source_v14_history': str(attempt.relative_to(ROOT)),
        'hold_s': 0.0,
    })
    for arm in ARMS:
        payload['actions'][arm]['dwell_s'] = 0.0
    return payload, frozen


def prefix_reference_record(block):
    candidate = candidate_dir(block['target_label'], block['seed'])
    attempt = source_attempt(block['target_label'], block['seed'])
    prefix = candidate / 'canonical_prefix.jsonl'
    graph = candidate / 'prefix_replays/repeat_01/graph_pre.json'
    replay = load_json(candidate /
                       'prefix_replays/repeat_01/unified_replay_result.json')
    binary = ROOT / 'catkin_ws/devel/lib/nav2d_karto/mapper'
    return {
        'block_id': block['block_id'],
        'target_label': block['target_label'],
        'seed': block['seed'],
        'canonical_prefix_path': str(prefix.relative_to(ROOT)),
        'canonical_prefix_sha256': sha256(prefix),
        'canonical_prefix_record_count': replay['prefix_record_count'],
        'mapper_params_path': str((attempt / 'mapper_params.yaml').relative_to(ROOT)),
        'mapper_params_file_sha256': sha256(attempt / 'mapper_params.yaml'),
        'mapper_params_normalized_sha256': replay['mapper_params_sha256'],
        'mapper_binary_path': str(binary.relative_to(ROOT)),
        'mapper_binary_sha256': sha256(binary),
        'prefix_reference_graph_path': str(graph.relative_to(ROOT)),
        'prefix_reference_graph_sha256': sha256(graph),
        'prefix_structural_signature_sha256': replay[
            'prefix_structural_signature']['structural_signature_sha256'],
        'local_five_target_state_ids': list(block['target_state_ids']),
        'action_anchor_state_id': block['anchor_state_id'],
        'numerical_tolerance': FROZEN_ZERO_TOLERANCE,
    }


def code_files():
    names = [
        'tools/realizability_pilot/v14_confirmatory_protocol.py',
        'tools/realizability_pilot/v14_history_qualification.py',
        'tools/realizability_pilot/v14_confirmatory_collection.py',
        'tools/realizability_pilot/v14_confirmatory_replay.py',
        'tools/realizability_pilot/v14_confirmatory_analysis.py',
        'tools/realizability_pilot/test_v14_confirmatory.py',
        'tools/realizability_pilot/fixed_scan_capture.py',
        'tools/realizability_pilot/v14t_fixed_scan_protocol.py',
        'tools/realizability_pilot/controlled_probe_capture.py',
        'tools/realizability_pilot/mechanism_classifier.py',
        'tools/realizability_pilot/v14_estimator_sanity.py',
        'tools/realizability_pilot/v13_unified_replay.py',
        'tools/realizability_pilot/v13_replay_publisher.py',
        'tools/realizability_pilot/v13_prefix_equivalence.py',
        'tools/realizability_pilot/v13_target_selector.py',
        'tools/realizability_pilot/normalize_replay_timestamps.py',
        'tools/realizability_pilot/common_prefix_signature.py',
        'tools/realizability_pilot/common_prefix_analysis.py',
        'tools/realizability_pilot/edge_analytics.py',
        'tools/realizability_pilot/same_input_replay.py',
        'tools/realizability_pilot/run_pilot.py',
        'tools/realizability_pilot/se2_information.py',
        'tools/realizability_pilot/stitch_probe_stream.py',
        'tools/realizability_pilot/controlled_branch_suite.py',
        'tools/realizability_pilot/confirmatory_v12_protocol.py',
        'dependencies/navigation_2d/nav2d_karto/src/MultiMapper.cpp',
        'dependencies/navigation_2d/nav2d_karto/include/nav2d_karto/MultiMapper.h',
        'dependencies/navigation_2d/nav2d_karto/CMakeLists.txt',
        'dependencies/navigation_2d/nav2d_karto/package.xml',
    ]
    return [ROOT / name for name in names]


def preregistration_payload():
    if git_head() != BASE_COMMIT:
        raise RuntimeError('v14 must freeze from the authorized base commit')
    hashes = {str(path.relative_to(ROOT)): sha256(path) for path in code_files()}
    mapper_binary = ROOT / 'catkin_ws/devel/lib/nav2d_karto/mapper'
    if sha256(mapper_binary) != EXPECTED_MAPPER_BINARY_SHA256:
        raise RuntimeError('certified mapper binary changed')
    return {
        'protocol_id': PROTOCOL_ID,
        'label': 'V14_PROSPECTIVE_CONFIRMATORY_VALIDATION',
        'created_before_any_fresh_candidate_or_action_collection': True,
        'base_git_commit': BASE_COMMIT,
        'code_hashes': hashes,
        'code_bundle_sha256': hashlib.sha256(json.dumps(
            hashes, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'mapper_backend': {
            'binary_path': str(mapper_binary.relative_to(ROOT)),
            'binary_sha256': EXPECTED_MAPPER_BINARY_SHA256,
            'normalized_config_sha256': EXPECTED_NORMALIZED_MAPPER_CONFIG_SHA256,
            'cpp_or_instrumentation_change_allowed': False,
            'blocked_label_if_change_required':
                'V14_BLOCKED_BY_BACKEND_CHANGE_REQUIREMENT',
        },
        'fixed_scan_controller': {
            'N': N_SCANS,
            'counter_reset': 'probe_arrival.start_time',
            'scientific_stream': 'exact first 347 treatment scans',
            'raw_debug_tail_allowed': True,
            'completion_after_N': 'technical failure',
            'target_specific_dwell': False,
            'A2_geometry': 'theta0 -> +90 -> -30 -> 0 -> +30',
            'effect_name': 'BROAD_SWEEP_ACTION_PACKAGE_EFFECT',
            'controller_sha256': hashes[
                'tools/realizability_pilot/fixed_scan_capture.py'],
        },
        'history_qualification': {
            'candidate_seeds_in_frozen_order': CANDIDATE_SEEDS,
            'one_attempt_per_candidate': True,
            'entire_pool_before_selection': True,
            'target_ids': TARGET_IDS,
            'selector': ('nearest legal post-route-start historical scan to '
                         'fixed target; +/-10 state segment; arc-length '
                         'quantiles 0.1/0.3/0.5/0.7/0.9'),
            'required_target_states': 5,
            'prefix_repeat_count': PREFIX_REPEAT_COUNT,
            'prefix_replay_rate_hz': PREFIX_RATE_HZ,
            'zero_structural_and_numerical_tolerance': FROZEN_ZERO_TOLERANCE,
            'first_four_eligible_rule': True,
            'reserve_or_substitution_allowed': False,
            'failure_gate': 'V14_PROSPECTIVE_TECHNICALLY_INCOMPLETE',
        },
        'arm_order_rule': {
            'deterministic_orders': ARM_ORDERS,
            'balanced_position_count_max_difference': 1,
            'history_property_used': False,
            'frozen_before_physical_collection': True,
        },
        'technical_retry_rule': {
            'MAX_CAPTURE_ATTEMPTS': MAX_CAPTURE_ATTEMPTS,
            'MAX_REPLAY_ATTEMPTS': MAX_REPLAY_ATTEMPTS,
            'technical_failures_only': [
                'Stage/ROS crash', 'controller exception',
                'branch-start gate fail', 'scientific scan count != 347',
                'maneuver completion after scan 347',
                'duplicate/nonmonotonic timestamp',
                'corrupt/missing required file'],
            'scientific_outcome_retry_forbidden': True,
            'reserve_history_substitution_forbidden': True,
        },
        'collection_and_replay_locks': {
            'physical': 'collection/PHYSICAL_COLLECTION_LOCK.json',
            'backend': 'collection/BACKEND_REPLAY_LOCK.json',
            'no_branch_after_physical_lock': True,
            'analysis_only_after_backend_lock': True,
        },
        'unified_backend_replay': {
            'fresh_ros_master_and_multimapper': True,
            'exact_canonical_prefix': True,
            'prefix_reference_zero_tolerance': True,
            'processed_count_barrier': True,
            'synchronous_graph_dump': True,
            'suffix': 'exact first-347 scientific treatment scans',
        },
        'estimands': {
            'J_T': '-logdet(Sigma_T)/15',
            'target_states': 'five frozen block-local history states',
            'statistical_unit': 'canonical-history block',
            'primary': 'D_sweep = J_T(A2_SWEEP90)-J_T(A3_MIN_TRIGGER)',
            'primary_effect_name': 'BROAD_SWEEP_ACTION_PACKAGE_EFFECT',
            'secondary': [
                'D_trigger = J_T(A3_MIN_TRIGGER)-J_T(A1_DWELL)',
                'D_total = J_T(A2_SWEEP90)-J_T(A1_DWELL)'],
            'v13_or_posthoc_pooled': False,
        },
        'gt_sanity_estimands': {
            'role': 'ESTIMATOR_EFFECT_SANITY_CHECK',
            'gauge': ('single SE(2) transform fitted from pre-treatment '
                      'canonical history and shared by all arms'),
            'arm_specific_alignment_forbidden': True,
            'metrics': [
                'translation RMSE before/after',
                'heading MAE/RMSE before/after',
                'delta translation RMSE', 'delta heading MAE/RMSE',
                'max/mean target-state correction',
                'GT_sweep_translation = DeltaRMSE_A2-DeltaRMSE_A3',
                'corresponding heading contrasts'],
            'warning': 'GT_SANITY_DIRECTIONAL_WARNING',
            'directional_warning_rule': (
                'warning iff at least 4 of 8 complete blocks have D_sweep > 0 '
                'and either GT_sweep_translation < 0 or '
                'GT_sweep_heading_RMSE < 0'),
            'no_warning': 'GT_SANITY_NO_DIRECTIONAL_WARNING',
            'unavailable': 'GT_SANITY_UNAVAILABLE',
            'affects_primary_gate': False,
        },
        'support_gate': {
            'requires_complete_blocks': 8,
            'overall_positive_min': 6,
            'target_A_positive_min': 3,
            'target_B_positive_min': 3,
            'mean_D_sweep_gt': J_T_NONTRIVIAL_FLOOR,
            'target_stratified_bootstrap_95pct_CI_lower_gt': 0.0,
            'bootstrap_seed': BOOTSTRAP_SEED,
            'bootstrap_repetitions': BOOTSTRAP_REPETITIONS,
        },
        'mechanism': {
            'families': ['PREVIOUS_SCAN', 'RUNNING_SCAN_CHAIN', 'NEAR_CHAIN',
                         'TRY_CLOSE_LOOP'],
            'exact_token_classifier': True,
            'zero_explicit_label': 'NO_EXPLICIT_TRY_CLOSE_LOOP_OBSERVED',
            'phase_attribution': 'PHASE_ATTRIBUTION_NOT_IDENTIFIABLE',
        },
        'no_peeking': {
            'allowed_before_physical_lock': [
                'branch-start gate', 'exact scan count', 'completion index',
                'completion margin', 'GT motion', 'timestamp integrity',
                'file/hash integrity', 'controller/ROS/Stage technical state'],
            'forbidden_before_backend_lock': [
                'accepted keyscan arm differences', 'E_T/E_N',
                'factor-count arm differences', 'J_T', 'posterior',
                'D_sweep', 'D_trigger', 'D_total'],
        },
        'final_three_state_decision': {
            'support': 'V14_PROSPECTIVE_SUPPORT',
            'no_support': 'V14_PROSPECTIVE_NO_SUPPORT',
            'incomplete': 'V14_PROSPECTIVE_TECHNICALLY_INCOMPLETE',
        },
        'hard_stop': {
            'V14_PROSPECTIVE_SUPPORT': 'PROCEED_TO_REALIZATION_MODELING_DESIGN',
            'V14_PROSPECTIVE_NO_SUPPORT':
                'STOP_CURRENT_CONFIRMATORY_INTERVENTION_AND_ANALYZE_HETEROGENEITY',
            'V14_PROSPECTIVE_TECHNICALLY_INCOMPLETE':
                'STOP_AND_DIAGNOSE_TECHNICAL_FAILURE',
            'automatic_next_experiment_allowed': False,
        },
    }


def write_preregistration(path=PREREGISTRATION_PATH):
    return write_frozen_json(path, preregistration_payload())
