#!/usr/bin/python3
"""Frozen definitions and preregistration for v13-C."""

import hashlib
import json
import subprocess
from pathlib import Path

import confirmatory_v12_protocol as v12
from controlled_branch_suite import atomic_json
from v13c_local_estimand_amendment import (BASE_COMMIT, FROZEN_MANIFEST_PATH,
                                           PROTOCOL_ID, RESULT_ROOT,
                                           V13T_ROOT)


ARMS = ('A1_DWELL', 'A3_MIN_TRIGGER', 'A2_SWEEP90')
TARGETS = ('target_A', 'target_B')
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
BUDGET_GATES = {
    'pairwise_distance_range_m_max': 0.10,
    'pairwise_time_range_s_max': 1.5,
    'raw_scan_relative_range_max': 0.03,
}
START_POSITION_TOLERANCE_M = v12.START_POSITION_TOLERANCE_M
START_HEADING_TOLERANCE_RAD = v12.START_HEADING_TOLERANCE_RAD
A3_ANGLE_RAD = v12.A3_ANGLE_RAD
MAX_CAPTURE_ATTEMPTS = 2
MAX_PREFIX_ATTEMPTS = 2
BOOTSTRAP_SEED = 130921
BOOTSTRAP_REPETITIONS = 10000
J_T_NONTRIVIAL_FLOOR = 1e-4
ROOT = Path(__file__).resolve().parents[2]
BUDGET_SOURCE = (ROOT / 'results/realizability_pilot' /
                 'p1_confirmatory_v12b_20260918/preregistration/'
                 'target_specific_budget_preregistration.json')
PREREGISTRATION_PATH = RESULT_ROOT / 'preregistration/v13C_preregistration.json'


def load_json(path):
    return json.loads(Path(path).read_text())


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git_head():
    return subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=str(ROOT), text=True).strip()


def frozen_manifest():
    payload = load_json(FROZEN_MANIFEST_PATH)
    if payload['stage0_gate'] != 'LOCAL_ESTIMAND_AMENDMENT_PASS':
        raise RuntimeError('Stage 0 has not authorized v13-C')
    if payload['planned_block_count'] != 8:
        raise RuntimeError('v13-C requires exactly eight frozen blocks')
    return payload


def budget_record():
    payload = load_json(BUDGET_SOURCE)
    if payload['status'] != 'TARGET_SPECIFIC_BUDGET_FROZEN':
        raise RuntimeError('frozen target-specific budget is unavailable')
    return payload


def source_attempt(target_label, seed):
    return (V13T_ROOT / 'histories' / target_label /
            'seed_{}'.format(int(seed)) / 'attempt_01')


def source_candidate_dir(target_label, seed):
    return source_attempt(target_label, seed).parent


def frozen_block_rows():
    manifest = frozen_manifest()
    return [row for target in TARGETS
            for row in manifest['selected_blocks'][target]]


def frozen_target_payload(block):
    attempt = source_attempt(block['block_id'].split('_H')[0], block['seed'])
    snapshot = load_json(attempt / 'pose_graph_before.json')
    nodes = {int(row['id']): row for row in snapshot['nodes']}
    unique = {int(row['id']): int(row['unique_id'])
              for row in snapshot['full_pose_nodes']}
    selected = []
    for state_id in block['selected_five_state_ids']:
        row = nodes[int(state_id)]
        selected.append({
            'id': int(state_id), 'unique_id': unique[int(state_id)],
            'x': float(row['x']), 'y': float(row['y']),
            'theta': float(row['theta']),
            'observed_time': row.get('observed_time'),
        })
    anchor_row = nodes[int(block['action_anchor_state_id'])]
    anchor = {
        'id': int(block['action_anchor_state_id']),
        'unique_id': unique[int(block['action_anchor_state_id'])],
        'x': float(anchor_row['x']), 'y': float(anchor_row['y']),
        'theta': float(anchor_row['theta']),
        'observed_time': anchor_row.get('observed_time'),
    }
    route = load_json(attempt / 'resolved_history_route.json')
    return {
        'protocol': 'v13-C Stage-0 local target subset',
        'target_label': block['block_id'].split('_H')[0],
        'target_id': block['target_id'],
        'historical_scan_ids': list(block['selected_five_state_ids']),
        'historical_unique_ids': list(block['selected_five_unique_ids']),
        'exact_state_count': 5,
        'segment_nodes': selected,
        'anchor_scan': anchor,
        'route_start_node_count': int(route['route_start_node_count']),
        'frozen_before_action_collection': True,
        'selection_source': str(FROZEN_MANIFEST_PATH.relative_to(ROOT)),
    }


def action_specs(block):
    target_label = block['block_id'].split('_H')[0]
    attempt = source_attempt(target_label, block['seed'])
    frozen = frozen_target_payload(block)
    dwell = budget_record()['dwell_durations_s'][target_label]
    payload = v12.action_specs(attempt, frozen, dwell['A3_MIN_TRIGGER'])
    payload['actions']['A1_DWELL']['dwell_s'] = dwell['A1_DWELL']
    payload['actions']['A2_SWEEP90']['dwell_s'] = dwell['A2_SWEEP90']
    payload['common']['protocol_id'] = PROTOCOL_ID
    payload['common']['source_v13T_history'] = str(attempt.relative_to(ROOT))
    payload['common']['target_specific_budget_s'] = {
        arm: dwell[arm] for arm in ARMS}
    return payload, frozen


def prefix_reference_record(block):
    target_label = block['block_id'].split('_H')[0]
    seed = block['seed']
    candidate = source_candidate_dir(target_label, seed)
    attempt = source_attempt(target_label, seed)
    prefix = candidate / 'canonical_prefix.jsonl'
    graph = candidate / 'prefix_replays/repeat_01/graph_pre.json'
    replay = load_json(candidate /
                       'prefix_replays/repeat_01/unified_replay_result.json')
    binary = ROOT / 'catkin_ws/devel/lib/nav2d_karto/mapper'
    return {
        'block_id': block['block_id'],
        'target_label': target_label,
        'seed': seed,
        'canonical_prefix_path': str(prefix.relative_to(ROOT)),
        'canonical_prefix_sha256': sha256(prefix),
        'canonical_prefix_record_count':
            replay['prefix_record_count'],
        'mapper_params_path': str((attempt / 'mapper_params.yaml').relative_to(ROOT)),
        'mapper_params_file_sha256': sha256(attempt / 'mapper_params.yaml'),
        'mapper_params_normalized_sha256': replay['mapper_params_sha256'],
        'mapper_binary_path': str(binary.relative_to(ROOT)),
        'mapper_binary_sha256': sha256(binary),
        'prefix_reference_graph_path': str(graph.relative_to(ROOT)),
        'prefix_reference_graph_sha256': sha256(graph),
        'prefix_structural_signature_sha256': replay[
            'prefix_structural_signature']['structural_signature_sha256'],
        'local_five_target_state_ids': block['selected_five_state_ids'],
        'action_anchor_state_id': block['action_anchor_state_id'],
        'numerical_tolerance': {
            'node_translation_max_m': 0.0,
            'node_heading_max_rad': 0.0,
            'edge_translation_measurement_max_m': 0.0,
            'edge_heading_measurement_max_rad': 0.0,
            'edge_covariance_max_abs': 0.0,
        },
    }


def relevant_code_files():
    names = [
        'tools/realizability_pilot/confirmatory_v13c_protocol.py',
        'tools/realizability_pilot/confirmatory_v13c_collection.py',
        'tools/realizability_pilot/confirmatory_v13c_analysis.py',
        'tools/realizability_pilot/v13c_local_estimand_amendment.py',
        'tools/realizability_pilot/v13_unified_replay.py',
        'tools/realizability_pilot/v13_replay_publisher.py',
        'tools/realizability_pilot/v13_prefix_equivalence.py',
        'tools/realizability_pilot/v13_target_selector.py',
        'tools/realizability_pilot/se2_information.py',
        'tools/realizability_pilot/controlled_branch_suite.py',
        'tools/realizability_pilot/controlled_probe_capture.py',
        'tools/realizability_pilot/stitch_probe_stream.py',
        'tools/realizability_pilot/confirmatory_v12_protocol.py',
        'dependencies/navigation_2d/nav2d_karto/src/MultiMapper.cpp',
        'dependencies/navigation_2d/nav2d_karto/include/nav2d_karto/MultiMapper.h',
    ]
    return [ROOT / name for name in names]


def preregistration_payload():
    if git_head() != BASE_COMMIT:
        raise RuntimeError('v13-C base commit differs from certified v13-T')
    manifest = frozen_manifest()
    budget = budget_record()
    blocks = frozen_block_rows()
    hashes = {str(path.relative_to(ROOT)): sha256(path)
              for path in relevant_code_files()}
    prefix_references = [prefix_reference_record(block) for block in blocks]
    return {
        'protocol_id': PROTOCOL_ID,
        'created_before_action_collection': True,
        'base_git_commit': BASE_COMMIT,
        'code_hashes': hashes,
        'code_bundle_sha256': hashlib.sha256(json.dumps(
            hashes, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'stage0_gate': manifest['stage0_gate'],
        'local_estimand_amendment_path': str(
            FROZEN_MANIFEST_PATH.with_name(
                'v13T_amendment_01_local_estimand.json').relative_to(ROOT)),
        'local_estimand_amendment_sha256': manifest['amendment_sha256'],
        'frozen_history_manifest_path': str(FROZEN_MANIFEST_PATH.relative_to(ROOT)),
        'frozen_history_manifest_sha256': sha256(FROZEN_MANIFEST_PATH),
        'blocks': [{
            'block_id': block['block_id'],
            'target_label': block['block_id'].split('_H')[0],
            'seed': block['seed'],
            'arm_order': ARM_ORDERS[block['block_id'].split('_H')[0]][
                int(block['block_id'].split('_H')[1]) - 1],
            'local_five_target_state_ids': block['selected_five_state_ids'],
            'action_anchor_state_id': block['action_anchor_state_id'],
        } for block in blocks],
        'planned_blocks': 8,
        'planned_branches': 24,
        'runtime_reserve_allowed': False,
        'history_rerun_allowed': False,
        'seed_substitution_allowed': False,
        'arm_orders': ARM_ORDERS,
        'actions': {
            'A1_DWELL': {
                'geometry': 'static at theta0',
                'target_A_dwell_s': 7.1,
                'target_B_dwell_s': 11.4,
            },
            'A3_MIN_TRIGGER': {
                'geometry': 'theta0 -> theta0 + 0.5439732814124923 -> theta0',
                'angle_rad': A3_ANGLE_RAD,
                'target_A_residual_dwell_s': 2.6,
                'target_B_residual_dwell_s': 7.0,
            },
            'A2_SWEEP90': {
                'geometry': 'frozen relative Sweep90 package',
                'target_A_residual_dwell_s': 0.0,
                'target_B_residual_dwell_s': 0.0,
            },
        },
        'budget_source': str(BUDGET_SOURCE.relative_to(ROOT)),
        'budget_source_sha256': sha256(BUDGET_SOURCE),
        'budget_durations_s': budget['dwell_durations_s'],
        'budget_gates': BUDGET_GATES,
        'budget_gate_excludes': ['accepted keyscan count', 'constraint count'],
        'capture_before_backend_replay': True,
        'capture_technical_attempt_cap': MAX_CAPTURE_ATTEMPTS,
        'prefix_replay_attempt_cap': MAX_PREFIX_ATTEMPTS,
        'post_treatment_retry_allowed': False,
        'prefix_references': prefix_references,
        'unified_replay': {
            'fresh_master_and_mapper': True,
            'subscriber_connection_required': True,
            'processed_callback_count_barrier': True,
            'synchronous_snapshot': True,
            'fixed_drain_sleep_forbidden': True,
            'background_graph_dump_forbidden': True,
            'suffix_forbidden_until_prefix_reference_exact': True,
            'numerical_tolerance': 0.0,
        },
        'primary_estimand': {
            'state_subset': 'five Stage-0 frozen local historical states',
            'dimension': 15,
            'estimator': ('fixed-first-pose fixed-linearisation local '
                          'linear-Gaussian joint marginal covariance'),
            'J_T': '-logdet(Sigma_T)/15',
            'not_exact_nonlinear_posterior': True,
        },
        'contrasts': {
            'D_sweep': ('J_T(A2_SWEEP90)-J_T(A3_MIN_TRIGGER); incremental '
                        'broad-sweep package effect'),
            'D_trigger': ('J_T(A3_MIN_TRIGGER)-J_T(A1_DWELL); incremental '
                          'minimal threshold-crossing effect'),
            'D_total': 'J_T(A2_SWEEP90)-J_T(A1_DWELL); secondary',
        },
        'support_rule': {
            'overall_positive_min': 6,
            'target_A_positive_min': 3,
            'target_B_positive_min': 3,
            'mean_effect_gt': J_T_NONTRIVIAL_FLOOR,
            'target_stratified_bootstrap_95pct_CI_lower_gt': 0.0,
            'bootstrap_seed': BOOTSTRAP_SEED,
            'bootstrap_repetitions': BOOTSTRAP_REPETITIONS,
            'statistical_unit': 'canonical-history block',
        },
        'no_peeking': {
            'collection_allowed': [
                'technical status', 'input hashes', 'prefix equivalence',
                'branch start', 'physical action execution', 'GT distance',
                'duration', 'raw scan count', 'required artifact presence'],
            'forbidden_until_collection_lock': [
                'J_T', 'posterior', 'E_T', 'E_N', 'keyscan comparison',
                'factor provenance interpretation', 'Delta U', 'D_sweep',
                'D_trigger', 'D_total'],
        },
        'v12_target_A_role': 'EXTERNAL_DESCRIPTIVE_REPLICATION_NOT_POOLED',
    }


def write_preregistration(path=PREREGISTRATION_PATH):
    path = Path(path)
    payload = preregistration_payload()
    if path.exists():
        if load_json(path) != payload:
            raise RuntimeError('refusing to change frozen v13-C preregistration')
        return payload
    atomic_json(path, payload)
    return payload
