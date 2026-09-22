#!/usr/bin/python3
"""Definitions and outcome-blind preregistration for v14-T certification."""

import hashlib
import json
import math
import subprocess
from pathlib import Path

from controlled_branch_suite import atomic_json


PROTOCOL_ID = 'p1_v14t_fixed_scan_technical_20260922'
BASE_COMMIT = '49cfff904954219f5be9425c714d6571c4cdd783'
ROOT = Path(__file__).resolve().parents[2]
RESULT_ROOT = ROOT / 'results/realizability_pilot' / PROTOCOL_ID
V13C_ROOT = ROOT / 'results/realizability_pilot/p1_confirmatory_v13c_20260921'
POSTHOC_ROOT = ROOT / 'results/realizability_pilot/p1_v13c_posthoc_targetB_20260921'
V12B_ROOT = ROOT / 'results/realizability_pilot/p1_confirmatory_v12b_20260918'
ARMS = ('A1_DWELL', 'A3_MIN_TRIGGER', 'A2_SWEEP90')
TARGETS = ('target_A', 'target_B')
BLOCKS = tuple('{}-H{}'.format(target[-1], index)
               for target in TARGETS for index in range(1, 5))
MANEUVER_COMPLETION_LABEL = {
    'A1_DWELL': 'probe_arrival',
    'A3_MIN_TRIGGER': 'min_trigger_return',
    'A2_SWEEP90': 'sweep_+30deg',
}
FRESH_CANDIDATE_SEEDS = {
    'target_A': list(range(91001, 91017)),
    'target_B': list(range(92001, 92017)),
}
TIMESTAMP_INCLUSION = 'treatment_start <= scan.stamp <= maneuver_completion'
STATIC_TAIL_INCLUSION = 'final_static_start <= scan.stamp <= probe_end_time'
START_POSITION_TOLERANCE_M = 0.08
START_HEADING_TOLERANCE_RAD = 0.04


def load_json(path):
    return json.loads(Path(path).read_text())


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git_head():
    return subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=str(ROOT), text=True).strip()


def v13c_capture_path(target, block_index, arm):
    return (V13C_ROOT / target / str(block_index) / arm /
            'raw_attempt_01/capture_result.json')


def compatible_budget_capture_paths():
    paths = []
    for target in TARGETS:
        for index in range(1, 5):
            for arm in ARMS:
                paths.append(v13c_capture_path(target, index, arm))
        for repeat in range(1, 4):
            for arm in ARMS:
                paths.append(V12B_ROOT / 'calibration' / target /
                             'repeat_{:02d}'.format(repeat) / arm /
                             'capture_result.json')
    return paths


def _moves(result):
    return {row['label']: row for row in result['moves']}


def read_jsonl(path):
    with open(path) as stream:
        return [json.loads(line) for line in stream if line.strip()]


def fixed_scan_stream_diagnostics(records, treatment_start, completion, budget):
    """Apply the frozen timestamp and exact-first-N treatment semantics.

    Records stamped before the treatment reset are raw/debug observations, not
    treatment scans.  The completion interval is closed at both boundaries.
    """
    budget = int(budget)
    if budget <= 0:
        raise ValueError('fixed scan budget must be positive')
    treatment = [row for row in records
                 if float(row['stamp']) >= float(treatment_start)]
    scientific = treatment[:budget]
    stamps = [float(row['stamp']) for row in scientific]
    completion_index = sum(
        float(treatment_start) <= float(row['stamp']) <= float(completion)
        for row in treatment)
    duplicate_count = len(stamps) - len(set(stamps))
    nonmonotonic_count = sum(
        right <= left for left, right in zip(stamps, stamps[1:]))
    status = 'SUCCEEDED'
    if completion_index > budget:
        status = 'TECHNICAL_INVALID_MANEUVER_EXCEEDS_SCAN_BUDGET'
    elif len(scientific) != budget:
        status = 'TECHNICAL_INVALID_SCIENTIFIC_SCAN_COUNT'
    elif duplicate_count:
        status = 'TECHNICAL_INVALID_DUPLICATE_TIMESTAMP'
    elif nonmonotonic_count:
        status = 'TECHNICAL_INVALID_NONMONOTONIC_TIMESTAMP'
    return {
        'status': status,
        'treatment_records': treatment,
        'scientific_records': scientific,
        'completion_scan_index': completion_index,
        'completion_margin': budget - completion_index,
        'duplicate_timestamp_count': duplicate_count,
        'nonmonotonic_timestamp_count': nonmonotonic_count,
    }


def derive_capture_budget_row(capture_path):
    capture_path = Path(capture_path)
    result = load_json(capture_path)
    spec = load_json(capture_path.with_name('capture_spec.json'))
    raw_path = capture_path.with_name('probe_stream_raw.jsonl')
    raw = read_jsonl(raw_path)
    stamps = [float(row['stamp']) for row in raw]
    arm = result['action_id']
    moves = _moves(result)
    treatment_start = float(moves['probe_arrival']['start_time'])
    completion = float(moves[MANEUVER_COMPLETION_LABEL[arm]]['end_time'])
    static_start = (float(result['dwell']['end_time'])
                    if result.get('dwell') else completion)
    completion_index = sum(
        treatment_start <= stamp <= completion for stamp in stamps)
    static_tail = sum(
        static_start <= stamp <= float(result['probe_end_time'])
        for stamp in stamps)
    relative = capture_path.relative_to(ROOT)
    parts = relative.parts
    target = next(part for part in parts if part in TARGETS)
    source_kind = 'V13C' if V13C_ROOT in capture_path.parents else 'V12B_CALIBRATION'
    if source_kind == 'V13C':
        block = '{}-H{}'.format(target[-1], parts[parts.index(target) + 1])
    else:
        block = parts[parts.index(target) + 1]
    return {
        'source_path': str(relative),
        'source_sha256': sha256(capture_path),
        'raw_stream_path': str(raw_path.relative_to(ROOT)),
        'raw_stream_sha256': sha256(raw_path),
        'source_kind': source_kind,
        'target': target,
        'block_or_history': block,
        'arm': arm,
        'treatment_start_s': treatment_start,
        'maneuver_completion_s': completion,
        'completion_scan_index': completion_index,
        'final_static_start_s': static_start,
        'probe_end_time_s': float(result['probe_end_time']),
        'static_tail_scan_count': static_tail,
        'raw_scan_count': len(raw),
        'duplicate_timestamp_count': len(stamps) - len(set(stamps)),
        'nonmonotonic_timestamp_count': sum(
            right <= left for left, right in zip(stamps, stamps[1:])),
        'timestamp_inclusion': TIMESTAMP_INCLUSION,
        'static_tail_inclusion': STATIC_TAIL_INCLUSION,
        'controller_semantics_compatible': bool(
            spec.get('core_action_start_index') is not None and
            MANEUVER_COMPLETION_LABEL[arm] in result['action_labels']),
    }


def derive_scan_budget():
    rows = [derive_capture_budget_row(path)
            for path in compatible_budget_capture_paths()]
    if len(rows) != 42:
        raise RuntimeError('fixed-scan budget requires exactly 42 captures')
    if not all(row['controller_semantics_compatible'] for row in rows):
        raise RuntimeError('incompatible controller semantics in budget source')
    if any(row['duplicate_timestamp_count'] or
           row['nonmonotonic_timestamp_count'] for row in rows):
        raise RuntimeError('budget source has ambiguous scan timestamps')
    m_value = max(row['completion_scan_index'] for row in rows)
    s_value = min(row['static_tail_scan_count'] for row in rows)
    return {
        'protocol_id': PROTOCOL_ID,
        'status': 'FIXED_SCAN_BUDGET_DERIVED_OUTCOME_BLIND',
        'scientific_backend_endpoints_read': [],
        'timestamp_boundary_convention': {
            'completion': TIMESTAMP_INCLUSION,
            'static_tail': STATIC_TAIL_INCLUSION,
            'scan_index_base': 1,
            'completion_scan_index_definition': (
                'number of treatment scans in the closed start/completion interval'),
        },
        'included_source_groups': [
            'v13-C Target-A H1-H4', 'v13-C Target-B H1-H4',
            'v12b compatible Target-A and Target-B calibration repeats 1-3'],
        'source_capture_count': len(rows),
        'rows': rows,
        'M': m_value,
        'S': s_value,
        'N': m_value + s_value,
        'minimum_acceptable_completion_margin': s_value,
        'rule': 'N = M + S',
    }


def original_artifact_manifest():
    paths = [
        V13C_ROOT / 'COLLECTION_LOCKED.json',
        V13C_ROOT / 'decision/final_gate.json',
        V13C_ROOT / 'preregistration/v13C_preregistration.json',
        POSTHOC_ROOT / 'REPLAY_COLLECTION_LOCKED.json',
        POSTHOC_ROOT / 'decision/posthoc_diagnostic_gate.json',
        POSTHOC_ROOT / 'preregistration/posthoc_diagnostic_preregistration.json',
    ]
    files = {str(path.relative_to(ROOT)): sha256(path) for path in paths}
    return {'files': files, 'bundle_sha256': hashlib.sha256(json.dumps(
        files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()}


def relevant_code_files():
    names = [
        'tools/realizability_pilot/mechanism_classifier.py',
        'tools/realizability_pilot/v14_estimator_sanity.py',
        'tools/realizability_pilot/v14t_fixed_scan_protocol.py',
        'tools/realizability_pilot/fixed_scan_capture.py',
        'tools/realizability_pilot/v14t_fixed_scan_technical.py',
        'tools/realizability_pilot/test_v14t_fixed_scan.py',
        'tools/realizability_pilot/controlled_probe_capture.py',
        'tools/realizability_pilot/controlled_branch_suite.py',
        'tools/realizability_pilot/confirmatory_v13c_protocol.py',
    ]
    return [ROOT / name for name in names]


def protocol_payload(budget):
    if git_head() != BASE_COMMIT:
        raise RuntimeError('v14-T must freeze from the declared base commit')
    hashes = {str(path.relative_to(ROOT)): sha256(path)
              for path in relevant_code_files()}
    original = original_artifact_manifest()
    return {
        'protocol_id': PROTOCOL_ID,
        'label': 'V14_T_FIXED_SCAN_TECHNICAL_CERTIFICATION',
        'scientific_confirmatory_experiment': False,
        'base_commit': BASE_COMMIT,
        'code_hashes': hashes,
        'code_bundle_sha256': hashlib.sha256(json.dumps(
            hashes, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'original_artifact_manifest': original,
        'original_v13C_gate': 'CONFIRMATORY_EXPERIMENT_TECHNICALLY_INCOMPLETE',
        'posthoc_decision': 'DIAGNOSTIC_SUPPORTS_ONE_PROSPECTIVE_RETRY',
        'scan_budget': {key: budget[key] for key in (
            'M', 'S', 'N', 'minimum_acceptable_completion_margin', 'rule')},
        'scan_budget_derivation_sha256': sha256(
            RESULT_ROOT / 'preregistration/v14T_scan_budget_derivation.json'),
        'planned_old_geometry_blocks': list(BLOCKS),
        'planned_technical_captures': 24,
        'arms': list(ARMS),
        'controller': {
            'treatment_counter_reset': 'probe_arrival.start_time',
            'scientific_stream': 'exact first N treatment scans',
            'raw_debug_stream_may_exceed_N': True,
            'maneuver_completion_labels': MANEUVER_COMPLETION_LABEL,
            'completion_after_N': 'TECHNICAL_INVALID_MANEUVER_EXCEEDS_SCAN_BUDGET',
            'target_specific_dwell_used': False,
            'A2_geometry_unchanged': True,
            'A2_final_heading': 'theta0+30deg',
            'effect_name': 'BROAD_SWEEP_ACTION_PACKAGE_EFFECT',
        },
        'technical_gate': {
            'required_valid_captures': 24,
            'exact_scientific_treatment_scans': budget['N'],
            'duplicates_allowed': 0,
            'nonmonotonic_allowed': 0,
            'minimum_completion_margin': budget['S'],
            'success': 'SCAN_BUDGET_TECHNICALLY_CERTIFIED',
            'failure': 'SCAN_BUDGET_ENVELOPE_INSUFFICIENT',
            'final_ready': 'V14_FIXED_SCAN_TECHNICALLY_READY',
            'final_redesign': 'V14_FIXED_SCAN_TECHNICAL_REDESIGN_REQUIRED',
        },
        'backend_started': False,
        'scientific_endpoint_access_during_collection': False,
        'future_scientific_estimands': {
            'primary': 'D_sweep = J_T(A2_SWEEP90)-J_T(A3_MIN_TRIGGER)',
            'primary_effect_name': 'BROAD_SWEEP_ACTION_PACKAGE_EFFECT',
            'secondary': [
                'D_trigger = J_T(A3_MIN_TRIGGER)-J_T(A1_DWELL)',
                'D_total = J_T(A2_SWEEP90)-J_T(A1_DWELL)'],
            'J_T': '-logdet(Sigma_T)/15',
            'support_structure': {
                'overall_positive_min': 6, 'target_A_positive_min': 3,
                'target_B_positive_min': 3, 'mean_D_sweep_gt': 1e-4,
                'target_stratified_bootstrap_95pct_CI_lower_gt': 0.0,
                'statistical_unit': 'canonical-history block'},
        },
        'estimator_effect_sanity_check': {
            'gauge': 'one transformation fitted from pre-treatment canonical history',
            'per_arm_realignment_forbidden': True,
            'metrics': [
                'translation RMSE before/after', 'heading MAE/RMSE before/after',
                'delta translation RMSE', 'delta heading error',
                'max historical target-state correction',
                'mean historical target-state correction'],
            'does_not_replace_primary': True,
            'NEES': 'NOT_PREREGISTERED_GAUGE_AND_COVARIANCE_INTERPRETATION_UNRESOLVED',
        },
        'fresh_history_plan_if_authorized': {
            'candidate_seeds_in_frozen_order': FRESH_CANDIDATE_SEEDS,
            'overlaps_v13_pool': False,
            'selection': ('large frozen pool -> outcome-blind qualification -> '
                          'first four eligible per target'),
            'replacement_after_endpoint': False,
            'freeze': ['seed order', 'target selector', 'five-state local estimand',
                       'prefix repeatability', 'eligibility', 'first-four rule'],
        },
        'no_peeking': {
            'allowed_before_collection_lock': [
                'controller status', 'branch start', 'exact N scan count',
                'action execution', 'GT motion', 'timestamp integrity',
                'input hashes', 'prefix equivalence'],
            'forbidden_before_collection_lock': [
                'J_T', 'E_T/E_N arm comparison', 'keyscan arm comparison',
                'factor-count arm comparison', 'posterior comparison',
                'D_sweep', 'D_trigger', 'D_total'],
        },
        'mechanism_language': {
            'exact_families': ['PREVIOUS_SCAN', 'RUNNING_SCAN_CHAIN',
                               'NEAR_CHAIN', 'TRY_CLOSE_LOOP'],
            'zero_explicit_label': 'NO_EXPLICIT_TRY_CLOSE_LOOP_OBSERVED',
            'preferred_terms': ['historical revisit association',
                                'historical pose-graph constraint',
                                'action-conditioned historical measurement realization'],
            '360_degree_lidar_warning': True,
        },
        'future_research_question': (
            'How does an active revisit action translate into the set and '
            'information utility of historical pose-graph constraints actually '
            'realized by a SLAM backend?'),
        'future_modeling_hypothesis': 'planned revisit value != realized backend information',
        'future_prediction_targets': [
            'E[Delta J_realized | G_pre, action]',
            'P(E_realized | G_pre, action)'],
        'automatic_v14_collection_allowed': False,
    }


def write_frozen_json(path, payload):
    path = Path(path)
    if path.exists():
        if load_json(path) != payload:
            raise RuntimeError('refusing to modify frozen {}'.format(path))
        return payload
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(path, payload)
    return payload


def verify_original_artifacts(manifest):
    mismatches = []
    for relative, expected in manifest['files'].items():
        observed = sha256(ROOT / relative)
        if observed != expected:
            mismatches.append({'path': relative, 'expected': expected,
                               'observed': observed})
    return {'passed': not mismatches, 'mismatches': mismatches}
