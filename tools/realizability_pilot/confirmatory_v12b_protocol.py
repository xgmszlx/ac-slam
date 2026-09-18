#!/usr/bin/python3
"""Frozen definitions for the fresh v12b confirmatory experiment."""

import hashlib
import json
import subprocess
from pathlib import Path

import confirmatory_v12_protocol as v12
from controlled_branch_suite import atomic_json


PROTOCOL_ID = 'p1_confirmatory_v12b_20260918'
ROOT = Path(__file__).resolve().parents[2]
RESULT_ROOT = ROOT / 'results/realizability_pilot' / PROTOCOL_ID
V12_ROOT = (ROOT / 'results/realizability_pilot' /
            'p1_confirmatory_v12_20260917')
ARMS = v12.ARMS
PRIMARY_SEEDS = {
    'target_A': [71001, 71002, 71003, 71004],
    'target_B': [72001, 72002, 72003, 72004],
}
RESERVE_SEEDS = {
    'target_A': [71005, 71006],
    'target_B': [72005, 72006],
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
TARGET_IDS = v12.TARGET_IDS
START_POSITION_TOLERANCE_M = v12.START_POSITION_TOLERANCE_M
START_HEADING_TOLERANCE_RAD = v12.START_HEADING_TOLERANCE_RAD
BUDGET_GATES = v12.BUDGET_GATES
MAX_HISTORY_ATTEMPTS_PER_SEED = 2
MAX_BRANCH_ATTEMPTS = 2
A3_ANGLE_RAD = v12.A3_ANGLE_RAD
J_T_NONTRIVIAL_FLOOR = 1e-4
BOOTSTRAP_SEED = 120918
TECHNICAL_AMENDMENT_PATH = (
    RESULT_ROOT / 'preregistration' /
    'technical_amendment_01_pose_graph_dump_polling.json')

freeze_target = v12.freeze_target
target_references = v12.target_references


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def git_head():
    result = subprocess.run(
        ['git', 'rev-parse', 'HEAD'], cwd=str(ROOT), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return result.stdout.strip() if result.returncode == 0 else None


def calibration_record(root=RESULT_ROOT):
    path = Path(root) / 'preregistration/target_specific_budget_preregistration.json'
    payload = json.loads(path.read_text())
    if payload['status'] != 'TARGET_SPECIFIC_BUDGET_FROZEN':
        raise RuntimeError('target-specific budget is not frozen')
    return payload


def phase_r_record(root=RESULT_ROOT):
    path = Path(root) / 'decision/phase_r_gate.json'
    payload = json.loads(path.read_text())
    if payload['status'] != 'TARGET_B_TECHNICAL_READY':
        raise RuntimeError('Phase R has not authorized Phase C')
    return payload


def history_spec(target_label, seed, episode_id):
    payload = v12.history_spec(target_label, seed, episode_id)
    payload['protocol_version'] = PROTOCOL_ID
    payload['condition_id'] = 'v12b_fresh_canonical_history'
    payload['tsp_seed'] = int(seed)
    return payload


def action_specs(attempt_dir, frozen_target, dwell_by_target):
    target = frozen_target['target_label']
    dwell = dwell_by_target[target]
    payload = v12.action_specs(
        attempt_dir, frozen_target, dwell['A3_MIN_TRIGGER'])
    payload['actions']['A1_DWELL']['dwell_s'] = dwell['A1_DWELL']
    payload['actions']['A2_SWEEP90']['dwell_s'] = dwell['A2_SWEEP90']
    payload['common']['v12b_target_label'] = target
    payload['common']['target_specific_budget_calibration'] = {
        arm: dwell[arm] for arm in ARMS}
    return payload


def relevant_code_files():
    return [
        Path(__file__).resolve(),
        Path(__file__).with_name('confirmatory_v12b_collection.py'),
        Path(__file__).with_name('confirmatory_v12b_analysis.py'),
        Path(__file__).with_name('confirmatory_v12_analysis.py'),
        Path(__file__).with_name('common_prefix_replay.py'),
        Path(__file__).with_name('branch_replay.py'),
        Path(__file__).with_name('controlled_probe_capture.py'),
        ROOT / 'dependencies/navigation_2d/nav2d_karto/src/MultiMapper.cpp',
        ROOT / ('dependencies/navigation_2d/nav2d_karto/include/'
                'nav2d_karto/MultiMapper.h'),
    ]


def preregistration_payload(root=RESULT_ROOT):
    root = Path(root)
    phase_r = phase_r_record(root)
    calibration = calibration_record(root)
    code_hashes = {str(path.relative_to(ROOT)): sha256(path)
                   for path in relevant_code_files()}
    worktree_content_hash = hashlib.sha256(json.dumps(
        code_hashes, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    amendment_path = (root / 'preregistration' /
                      TECHNICAL_AMENDMENT_PATH.name)
    if not amendment_path.exists():
        raise RuntimeError('technical amendment record is missing')
    return {
        'protocol_id': PROTOCOL_ID,
        'created_before_fresh_scientific_collection': True,
        'predecessor_v12_final_gate':
            'CONFIRMATORY_EXPERIMENT_TECHNICALLY_INCOMPLETE',
        'v12_target_A_role': 'DESCRIPTIVE_PRIOR_EVIDENCE_NOT_POOLED',
        'phase_r_gate': phase_r,
        'phase_r_gate_sha256': sha256(root / 'decision/phase_r_gate.json'),
        'git_head': git_head(),
        'code_worktree_content_hash': worktree_content_hash,
        'code_hashes': code_hashes,
        'technical_amendments': [{
            'path': str(amendment_path),
            'sha256': sha256(amendment_path),
            'scope': 'COLLECTION_INSTRUMENTATION_ONLY',
            'requires_fresh_restart': True,
        }],
        'technical_calibration_files': {
            'budget_preregistration': {
                'path': str(root / 'preregistration/target_specific_budget_preregistration.json'),
                'sha256': sha256(root / 'preregistration/target_specific_budget_preregistration.json'),
            },
            'timing_audit': {
                'path': str(root / 'technical_repair/a2_phase_timing_summary.json'),
                'sha256': sha256(root / 'technical_repair/a2_phase_timing_summary.json'),
            },
            'prefix_audit': {
                'path': str(root / 'technical_repair/prefix_determinism_summary.json'),
                'sha256': sha256(root / 'technical_repair/prefix_determinism_summary.json'),
            },
        },
        'targets': target_references(),
        'primary_history_seeds': PRIMARY_SEEDS,
        'reserve_history_seeds': RESERVE_SEEDS,
        'reserve_rule': ('consume in listed target-level order only after '
                         'history, target-match, or prefix technical failure; '
                         'never replace budget or scientific outcome'),
        'fresh_history_rule': ('No v12 canonical history is eligible for the '
                               'v12b primary sample.'),
        'arm_orders': ARM_ORDERS,
        'arms': {
            'A1_DWELL': {
                'geometry': 'static at anchor theta0',
                'target_specific_dwell_s': {
                    target: calibration['dwell_durations_s'][target]['A1_DWELL']
                    for target in ('target_A', 'target_B')},
            },
            'A3_MIN_TRIGGER': {
                'geometry': 'theta0 -> theta0+0.5439732814 -> theta0 then dwell',
                'angle_rad': A3_ANGLE_RAD,
                'target_specific_residual_dwell_s': {
                    target: calibration['dwell_durations_s'][target]['A3_MIN_TRIGGER']
                    for target in ('target_A', 'target_B')},
                'keyscan_count_is_mediator_not_validity_gate': True,
            },
            'A2_SWEEP90': {
                'geometry': ('same relative +90 -> -30 -> 0 -> +30 degree '
                             'definition as v12'),
                'target_specific_residual_dwell_s': {
                    target: calibration['dwell_durations_s'][target]['A2_SWEEP90']
                    for target in ('target_A', 'target_B')},
            },
        },
        'budget_gates': BUDGET_GATES,
        'branch_start_gates': {
            'position_m_max': START_POSITION_TOLERANCE_M,
            'heading_rad_max': START_HEADING_TOLERANCE_RAD},
        'common_prefix': {
            'minimum_fresh_replays': 2,
            'instrumentation_flush_period_s': 0.0,
            'requires_exact_nodes_poses_edge_order_measurements_covariances_target_mapping': True,
        },
        'primary_outcome': {
            'fixed_state_subset': 'five matched prefix SE(2) states',
            'dimension': 15,
            'J_T': '-logdet(Sigma_T)/15',
            'primary_contrast': 'J_T(A2_SWEEP90)-J_T(A3_MIN_TRIGGER)',
            'key_mechanism_contrast': 'J_T(A3_MIN_TRIGGER)-J_T(A1_DWELL)',
            'secondary_total_contrast': 'J_T(A2_SWEEP90)-J_T(A1_DWELL)',
            'local_linear_Gaussian_not_exact_nonlinear': True,
        },
        'secondary_outcomes': [
            'target trace/logdet', 'prefix-terminal trace/logdet',
            'keyscan count and trigger', 'E_T/E_N/local factors',
            'creation provenance', 'factor identity/covariance',
            'insertion geodesic/cycle', 'Delta U_T',
            'history connectivity', 'v12 Target-A replication direction'],
        'analysis_plan': {
            'statistical_unit': 'canonical-history block',
            'planned_blocks': 8, 'planned_branches': 24,
            'strong_support': {
                'overall_positive_min': 6,
                'target_A_positive_min': 3,
                'target_B_positive_min': 3,
                'mean_effect_min': J_T_NONTRIVIAL_FLOOR,
                'target_stratified_block_bootstrap_mean_95pct_CI_lower_gt': 0.0,
            },
            'J_T_nontrivial_numerical_floor': J_T_NONTRIVIAL_FLOOR,
            'bootstrap_seed': BOOTSTRAP_SEED,
            'bootstrap_repetitions': 10000,
            'report': ['all eight effects', 'mean', 'median',
                       'target means/medians', 'target-stratified bootstrap CI',
                       'one-sided exact sign test'],
            'target_heterogeneity': ('one target >=3/4 positive and the other '
                                     '<=2/4, or target means have opposite signs'),
            'no_branch_level_pseudoreplication': True,
        },
        'technical_exclusions': {
            'history_attempts_per_seed': MAX_HISTORY_ATTEMPTS_PER_SEED,
            'branch_replay_attempts': MAX_BRANCH_ATTEMPTS,
            'budget_mismatch': ('invalidate block; no outcome-driven retry or '
                                'reserve substitution'),
            'scientific_outcome_never_authorizes_retry': True,
        },
        'no_peeking': {
            'collection_allowed': ['technical validity', 'hashes', 'branch start',
                                   'action execution', 'GT distance', 'duration',
                                   'raw scan count'],
            'forbidden_until_COLLECTION_LOCKED': [
                'J_T', 'posterior contrasts', 'E_T', 'E_N', 'Delta U',
                'factor provenance outcomes', 'A2-A3', 'A3-A1'],
        },
        'v12_descriptive_reference': {
            'D_view_target_A': {'positive': 4, 'total': 4,
                                'mean': 0.07086829572408293},
            'D_trigger_target_A': {'positive': 3, 'total': 4,
                                   'mean': 0.05766937777245884},
            'D_total_target_A': {'positive': 4, 'total': 4,
                                 'mean': 0.12853767349654177},
            'pool_with_v12b': False,
        },
    }


def write_preregistration(path, root=RESULT_ROOT):
    path = Path(path)
    payload = preregistration_payload(root)
    if path.exists():
        existing = json.loads(path.read_text())
        if existing != payload:
            raise RuntimeError('refusing to change frozen v12b preregistration')
        return existing
    atomic_json(path, payload)
    return payload
