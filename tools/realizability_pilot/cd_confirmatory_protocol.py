#!/usr/bin/python3
"""Frozen protocol definitions for the prospective context-dose experiment."""

import copy
import hashlib
import json
import math
import subprocess
from pathlib import Path

import confirmatory_v12_protocol as v12
from context_disentangle_protocol import dose_motion
from controlled_branch_suite import atomic_json
from protocol import TARGETS as PILOT_TARGETS


PROTOCOL_ID = 'p1_context_disentangle_confirmatory_20260930'
LABEL = 'CD_PROSPECTIVE_CONTEXT_DOSE_EXPERIMENT'
BASE_COMMIT = '40f1aee3b1e5bff6bb62594373d7124e19e22da8'
ROOT = Path(__file__).resolve().parents[2]
RESULT_ROOT = ROOT / 'results/realizability_pilot' / PROTOCOL_ID
PREREGISTRATION_PATH = (
    RESULT_ROOT / 'preregistration/CD_confirmatory_preregistration.json')
HISTORY_MANIFEST_PATH = (
    RESULT_ROOT / 'qualification/frozen_history_manifest.json')
ARM_ORDER_MANIFEST_PATH = (
    RESULT_ROOT / 'collection/frozen_arm_order_manifest.json')

TARGET_IDS = {
    'target_A': 'map3_grid_anchor_01',
    'target_B': 'map3_grid_anchor_03',
}
TARGETS = ('target_A', 'target_B')
ARMS = ('D0_ZERO', 'D1_THRESHOLD', 'D2_HIGH')
DOSES = {
    'D0_ZERO': 0.0,
    'D1_THRESHOLD': 1.087946562824985,
    'D2_HIGH': math.pi,
}
CANDIDATE_SEEDS = {
    'target_A': list(range(101001, 101017)),
    'target_B': list(range(102001, 102017)),
}
ARM_ORDERS = {
    'target_A': [
        ['D0_ZERO', 'D1_THRESHOLD', 'D2_HIGH'],
        ['D1_THRESHOLD', 'D2_HIGH', 'D0_ZERO'],
        ['D2_HIGH', 'D0_ZERO', 'D1_THRESHOLD'],
        ['D0_ZERO', 'D2_HIGH', 'D1_THRESHOLD'],
        ['D1_THRESHOLD', 'D0_ZERO', 'D2_HIGH'],
        ['D2_HIGH', 'D1_THRESHOLD', 'D0_ZERO'],
        ['D0_ZERO', 'D1_THRESHOLD', 'D2_HIGH'],
        ['D1_THRESHOLD', 'D2_HIGH', 'D0_ZERO'],
    ],
    'target_B': [
        ['D1_THRESHOLD', 'D0_ZERO', 'D2_HIGH'],
        ['D2_HIGH', 'D1_THRESHOLD', 'D0_ZERO'],
        ['D0_ZERO', 'D2_HIGH', 'D1_THRESHOLD'],
        ['D1_THRESHOLD', 'D2_HIGH', 'D0_ZERO'],
        ['D2_HIGH', 'D0_ZERO', 'D1_THRESHOLD'],
        ['D0_ZERO', 'D1_THRESHOLD', 'D2_HIGH'],
        ['D1_THRESHOLD', 'D0_ZERO', 'D2_HIGH'],
        ['D2_HIGH', 'D1_THRESHOLD', 'D0_ZERO'],
    ],
}

N_SCANS = 347
MIN_COMPLETION_MARGIN = 60
PREFIX_REPEAT_COUNT = 3
PREFIX_RATE_HZ = 20.0
MAX_CAPTURE_ATTEMPTS = 2
MAX_REPLAY_ATTEMPTS = 2
BOOTSTRAP_SEED = 300930
BOOTSTRAP_REPETITIONS = 20000
YAW_TOLERANCE_RAD = 0.06
D0_YAW_MAX_RAD = 0.03
FINAL_HEADING_TOLERANCE_RAD = 0.04
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
FROZEN_ROOTS = {
    'v14': 'results/realizability_pilot/p1_v14_confirmatory_20260928',
    'v14_heterogeneity': (
        'results/realizability_pilot/p1_v14_heterogeneity_20260928'),
    'cd_technical': (
        'results/realizability_pilot/p1_context_disentangle_t_20260928'),
}
EXPECTED_FROZEN_TREE_OIDS = {
    'v14': '82c934201e75dc42c9718455c860fa1cc4f2630e',
    'v14_heterogeneity': '720779e2eb2efb1bf253df051207e675ae26e31b',
}
EXPECTED_CDT_PROTOCOL_SHA256 = (
    '416596725551d4e2eb7da61284850b665cbc2ad894d30e823a85dcc8c8fc6289')


def load_json(path):
    return json.loads(Path(path).read_text())


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git_head():
    return subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=str(ROOT), text=True).strip()


def git_branch():
    return subprocess.check_output(
        ['git', 'branch', '--show-current'], cwd=str(ROOT), text=True).strip()


def git_tree_oid(relative):
    return subprocess.check_output(
        ['git', 'rev-parse', 'HEAD:{}'.format(relative)],
        cwd=str(ROOT), text=True).strip()


def write_frozen_json(path, payload):
    path = Path(path)
    if path.exists():
        if load_json(path) != payload:
            raise RuntimeError('refusing to modify frozen {}'.format(path))
        return payload
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(path, payload)
    return payload


def frozen_source_provenance():
    if git_head() != BASE_COMMIT:
        raise RuntimeError('CD experiment must freeze from authorized HEAD')
    if git_branch() != 'research/phase4c-formal':
        raise RuntimeError('unexpected source branch')
    failures = []
    trees = {}
    for label in ('v14', 'v14_heterogeneity'):
        actual = git_tree_oid(FROZEN_ROOTS[label])
        trees[label] = actual
        if actual != EXPECTED_FROZEN_TREE_OIDS[label]:
            failures.append('{} tree changed'.format(label))
    cdt = ROOT / FROZEN_ROOTS['cd_technical'] / \
        'preregistration/CDT_protocol.json'
    cdt_hash = sha256(cdt)
    if cdt_hash != EXPECTED_CDT_PROTOCOL_SHA256:
        failures.append('CD-T protocol changed')
    return {
        'source_branch': git_branch(),
        'source_head': git_head(),
        'frozen_tree_oids': trees,
        'cdt_protocol_sha256': cdt_hash,
        'failures': failures,
        'passed': not failures,
    }


def history_spec(target_label, seed):
    if int(seed) not in CANDIDATE_SEEDS[target_label]:
        raise ValueError('seed is outside frozen CD candidate pool')
    target_id = TARGET_IDS[target_label]
    spec = copy.deepcopy(PILOT_TARGETS[target_id])
    episode_id = 'cd_{}_s{}'.format(target_label, int(seed))
    spec.update({
        'protocol_version': PROTOCOL_ID,
        'target_id': target_id,
        'condition_id': 'cd_history_qualification_only',
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
        raise RuntimeError('CD history pool is not complete')
    if manifest.get('technical_gate') != 'CD_HISTORY_QUALIFICATION_PASS':
        raise RuntimeError('CD history qualification did not pass')
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
            'id': int(state_id),
            'unique_id': unique[int(state_id)],
            'x': float(row['x']),
            'y': float(row['y']),
            'theta': float(row['theta']),
            'observed_time': row.get('observed_time'),
        })
    anchor = nodes[int(block['anchor_state_id'])]
    route = load_json(attempt / 'resolved_history_route.json')
    return {
        'protocol': 'CD frozen block-local target subset',
        'target_label': block['target_label'],
        'target_id': block['target_id'],
        'historical_scan_ids': list(block['target_state_ids']),
        'historical_unique_ids': list(block['target_unique_ids']),
        'exact_state_count': 5,
        'segment_nodes': segment,
        'anchor_scan': {
            'id': int(block['anchor_state_id']),
            'unique_id': unique[int(block['anchor_state_id'])],
            'x': float(anchor['x']),
            'y': float(anchor['y']),
            'theta': float(anchor['theta']),
            'observed_time': anchor.get('observed_time'),
        },
        'route_start_node_count': int(route['route_start_node_count']),
        'canonical_prefix_sha256': block['canonical_prefix_sha256'],
        'pre_treatment_descriptor_sha256': block[
            'pre_treatment_descriptor_sha256'],
        'frozen_before_action_collection': True,
        'selection_source': str(HISTORY_MANIFEST_PATH.relative_to(ROOT)),
    }


def action_specs(block):
    attempt = source_attempt(block['target_label'], block['seed'])
    frozen = frozen_target_payload(block)
    legacy = v12.action_specs(attempt, frozen, 0.0)
    source = legacy['actions']['A1_DWELL']
    core = int(source['core_action_start_index'])
    prefix_waypoints = [list(row) for row in
                        source['action_waypoints'][:core + 1]]
    prefix_labels = list(source['action_labels'][:core + 1])
    anchor = prefix_waypoints[core]
    theta0 = float(anchor[2])
    actions = {}
    for arm in ARMS:
        motion = dose_motion(theta0, arm)
        waypoints = [list(row) for row in prefix_waypoints]
        labels = list(prefix_labels)
        for label, heading in zip(motion['post_start_labels'],
                                  motion['headings_rad'][1:]):
            labels.append(label)
            waypoints.append([float(anchor[0]), float(anchor[1]),
                              float(heading)])
        actions[arm] = {
            'action_id': arm,
            'action_labels': labels,
            'action_waypoints': waypoints,
            'core_action_start_index': core,
            'theta0_rad': theta0,
            'planned_cumulative_yaw_rad': DOSES[arm],
            'controller_properties': {
                'max_angular_velocity_rad_s': 0.65,
                'proportional_gain': 1.8,
                'heading_tolerance_rad': 0.018,
                'stable_cycles': 3,
                'control_period_s': 0.05,
                'zero_twist_hold': True,
            },
        }
    common = dict(legacy['common'])
    common.update({
        'protocol_id': PROTOCOL_ID,
        'source_cd_history': str(attempt.relative_to(ROOT)),
        'hold_s': 0.0,
        'scientific_treatment_scan_budget': N_SCANS,
        'dose_intervention': 'STANDARDIZED_ROTATIONAL_ACTION_DOSE',
        'pure_cumulative_yaw_causal_effect_claimed': False,
    })
    return {'common': common, 'actions': actions}, frozen


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
        'mapper_params_path': str(
            (attempt / 'mapper_params.yaml').relative_to(ROOT)),
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
        'tools/realizability_pilot/cd_confirmatory_protocol.py',
        'tools/realizability_pilot/cd_confirmatory_guard.py',
        'tools/realizability_pilot/cd_confirmatory_qualification.py',
        'tools/realizability_pilot/cd_confirmatory_capture.py',
        'tools/realizability_pilot/cd_confirmatory_collection.py',
        'tools/realizability_pilot/cd_confirmatory_replay.py',
        'tools/realizability_pilot/cd_confirmatory_analysis.py',
        'tools/realizability_pilot/cd_confirmatory_pipeline.py',
        'tools/realizability_pilot/test_cd_confirmatory.py',
        'tools/realizability_pilot/context_disentangle_protocol.py',
        'tools/realizability_pilot/controlled_probe_capture.py',
        'tools/realizability_pilot/fixed_scan_capture.py',
        'tools/realizability_pilot/v14t_fixed_scan_protocol.py',
        'tools/realizability_pilot/v14_confirmatory_collection.py',
        'tools/realizability_pilot/v14_confirmatory_replay.py',
        'tools/realizability_pilot/v14_confirmatory_analysis.py',
        'tools/realizability_pilot/v14_estimator_sanity.py',
        'tools/realizability_pilot/v13_unified_replay.py',
        'tools/realizability_pilot/v13_replay_publisher.py',
        'tools/realizability_pilot/v13_prefix_equivalence.py',
        'tools/realizability_pilot/v13_target_selector.py',
        'tools/realizability_pilot/normalize_replay_timestamps.py',
        'tools/realizability_pilot/common_prefix_signature.py',
        'tools/realizability_pilot/common_prefix_analysis.py',
        'tools/realizability_pilot/edge_analytics.py',
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
    provenance = frozen_source_provenance()
    if not provenance['passed']:
        raise RuntimeError('frozen source provenance failed')
    hashes = {str(path.relative_to(ROOT)): sha256(path)
              for path in code_files()}
    mapper = ROOT / 'catkin_ws/devel/lib/nav2d_karto/mapper'
    if sha256(mapper) != EXPECTED_MAPPER_BINARY_SHA256:
        raise RuntimeError('certified mapper binary changed')
    return {
        'protocol_id': PROTOCOL_ID,
        'label': LABEL,
        'created_before_any_fresh_history_generation': True,
        'base_git_commit': BASE_COMMIT,
        'source_provenance': provenance,
        'code_hashes': hashes,
        'code_bundle_sha256': hashlib.sha256(json.dumps(
            hashes, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'mapper_backend': {
            'binary_path': str(mapper.relative_to(ROOT)),
            'binary_sha256': EXPECTED_MAPPER_BINARY_SHA256,
            'normalized_config_sha256': EXPECTED_NORMALIZED_MAPPER_CONFIG_SHA256,
            'instrumentation_change_allowed': False,
        },
        'intervention': {
            'name': 'STANDARDIZED_ROTATIONAL_ACTION_DOSE',
            'arms': {arm: {'planned_cumulative_rotational_action_rad': dose}
                     for arm, dose in DOSES.items()},
            'template': 'theta0 -> theta0 + dose/2 -> theta0',
            'common_anchor_and_initial_final_heading': True,
            'N': N_SCANS,
            'pure_cumulative_yaw_causal_effect_claimed': False,
            'jointly_changes': ['maneuver duration', 'moving-scan composition'],
        },
        'history_qualification': {
            'candidate_seeds_in_frozen_order': CANDIDATE_SEEDS,
            'candidate_attempts_per_seed': 1,
            'entire_pool_before_selection': True,
            'target_ids': TARGET_IDS,
            'selector': ('nearest legal post-route-start historical scan to '
                         'fixed target; five block-local states'),
            'prefix_repeat_count': PREFIX_REPEAT_COUNT,
            'zero_structural_and_numerical_tolerance': FROZEN_ZERO_TOLERANCE,
            'first_eight_eligible_rule': True,
            'selected_blocks_per_target': 8,
            'reserve_or_substitution_allowed': False,
            'failure_gate': 'CD_PROSPECTIVE_TECHNICALLY_INCOMPLETE',
        },
        'arm_order_rule': {
            'deterministic_orders': ARM_ORDERS,
            'history_property_used': False,
            'frozen_before_physical_collection': True,
        },
        'technical_retry_rule': {
            'MAX_CAPTURE_ATTEMPTS': MAX_CAPTURE_ATTEMPTS,
            'MAX_REPLAY_ATTEMPTS': MAX_REPLAY_ATTEMPTS,
            'technical_failures_only': True,
            'scientific_outcome_retry_forbidden': True,
            'reserve_history_substitution_forbidden': True,
        },
        'manipulation_gate': {
            'N': N_SCANS,
            'minimum_completion_margin': MIN_COMPLETION_MARGIN,
            'D0_max_yaw_rad': D0_YAW_MAX_RAD,
            'D1_D2_error_tolerance_rad': YAW_TOLERANCE_RAD,
            'final_heading_tolerance_rad': FINAL_HEADING_TOLERANCE_RAD,
            'strict_D0_D1_D2_monotonicity': True,
            'target_actual_dose_ranges_must_overlap': True,
            'target_completion_scan_ranges_must_overlap': True,
        },
        'locks': {
            'physical': 'collection/PHYSICAL_COLLECTION_LOCK.json',
            'backend': 'collection/BACKEND_REPLAY_LOCK.json',
            'no_recollection_after_physical_lock': True,
            'analysis_only_after_complete_backend_lock': True,
        },
        'backend_replay': {
            'fresh_ros_master_and_multimapper': True,
            'exact_canonical_prefix': True,
            'zero_tolerance_prefix_gate': True,
            'processed_count_barrier': True,
            'synchronous_graph_dump': True,
            'suffix': 'exact first-347 scientific treatment scans',
        },
        'estimands': {
            'J_T': '-logdet(Sigma_T)/15',
            'statistical_unit': 'canonical-history block',
            'independent_units': 16,
            'branches_not_independent': 48,
            'C_HT_block': 'J_T(D2_HIGH)-J_T(D1_THRESHOLD)',
            'C_HT_A': 'mean Target-A C_HT',
            'C_HT_B': 'mean Target-B C_HT',
            'primary_I_HT': 'C_HT_B-C_HT_A',
            'co_primary_contrasts': [],
            'secondary': {
                'C_T0': 'J_T(D1_THRESHOLD)-J_T(D0_ZERO)',
                'C_H0': 'J_T(D2_HIGH)-J_T(D0_ZERO)',
                'I_T0': 'mean_B(C_T0)-mean_A(C_T0)',
                'I_H0': 'mean_B(C_H0)-mean_A(C_H0)',
            },
        },
        'primary_inference': {
            'procedure': 'target-stratified block bootstrap',
            'bootstrap_seed': BOOTSTRAP_SEED,
            'bootstrap_repetitions': BOOTSTRAP_REPETITIONS,
            'support': ('complete 8A+8B and two-sided 95% CI(I_HT) '
                        'excludes zero'),
        },
        'mechanism': {
            'H_HT': ('HistoricalFactors(D2_HIGH)-'
                     'HistoricalFactors(D1_THRESHOLD)'),
            'I_HIST_HT': 'mean_B(H_HT)-mean_A(H_HT)',
            'causal_mediation_claim_allowed': False,
            'direction_label_only': True,
        },
        'gt_sanity': {
            'shared_pre_treatment_gauge': True,
            'per_arm_after_realignment_forbidden': True,
            'strict_timestamp_pairing': True,
            'unavailable_label': 'GT_SANITY_UNAVAILABLE',
            'affects_primary_gate': False,
        },
        'no_peeking': {
            'analysis_requires_complete_backend_lock': True,
            'forbidden_before_backend_lock': [
                'J_T', 'historical factor arm comparison',
                'accepted-keyscan arm comparison', 'C_HT', 'I_HT',
                'secondary J contrasts', 'mechanism contrasts'],
            'pre_treatment_descriptors_not_used_for_selection': True,
        },
        'final_three_state_decision': {
            'support': 'CD_PROSPECTIVE_INTERACTION_SUPPORT',
            'no_support': 'CD_PROSPECTIVE_NO_INTERACTION_SUPPORT',
            'incomplete': 'CD_PROSPECTIVE_TECHNICALLY_INCOMPLETE',
        },
        'hard_stop': {
            'CD_PROSPECTIVE_INTERACTION_SUPPORT':
                'EXPAND_CONTEXT_SET_BEFORE_PREDICTOR',
            'CD_PROSPECTIVE_NO_INTERACTION_SUPPORT':
                'REASSESS_PLAN_A_MECHANISM_AFTER_DOSE_DECONFOUNDING',
            'CD_PROSPECTIVE_TECHNICALLY_INCOMPLETE':
                'STOP_AND_DIAGNOSE_CD_TECHNICAL_FAILURE',
            'automatic_followup_experiment_allowed': False,
        },
        'prior_scientific_state_preserved': {
            'v14': 'V14_PROSPECTIVE_NO_SUPPORT',
            'universal_broad_sweep_hypothesis': 'STOPPED',
        },
    }


def write_preregistration(path=PREREGISTRATION_PATH):
    return write_frozen_json(path, preregistration_payload())
