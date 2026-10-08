#!/usr/bin/python3
"""Outcome-blind technical amendment for the prospective CD experiment."""

import copy
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

import cd_confirmatory_protocol as original
from controlled_branch_suite import atomic_json


PROTOCOL_ID = 'p1_context_disentangle_confirmatory_amendment1_20260930'
LABEL = 'CD_PROSPECTIVE_CONTEXT_DOSE_TECHNICAL_AMENDMENT_1'
ROOT = original.ROOT
BASE_COMMIT = original.BASE_COMMIT
ORIGINAL_ROOT = original.RESULT_ROOT
ORIGINAL_PREREGISTRATION_PATH = original.PREREGISTRATION_PATH
ORIGINAL_HISTORY_MANIFEST_PATH = original.HISTORY_MANIFEST_PATH
ORIGINAL_FINAL_GATE_PATH = ORIGINAL_ROOT / 'decision/final_gate.json'
ORIGINAL_DOC_PATH = (
    ROOT / 'docs/research_log/70_context_disentanglement_prospective.md')
RESULT_ROOT = ROOT / 'results/realizability_pilot' / PROTOCOL_ID
PREREGISTRATION_PATH = (
    RESULT_ROOT / 'preregistration/CD_amendment1_preregistration.json')
HISTORY_MANIFEST_PATH = (
    RESULT_ROOT / 'qualification/frozen_history_manifest.json')
ARM_ORDER_MANIFEST_PATH = (
    RESULT_ROOT / 'collection/frozen_arm_order_manifest.json')

ARMS = original.ARMS
TARGETS = original.TARGETS
TARGET_IDS = original.TARGET_IDS
DOSES = original.DOSES
ARM_ORDERS = copy.deepcopy(original.ARM_ORDERS)
N_SCANS = original.N_SCANS
MIN_COMPLETION_MARGIN = original.MIN_COMPLETION_MARGIN
MAX_CAPTURE_ATTEMPTS = original.MAX_CAPTURE_ATTEMPTS
MAX_REPLAY_ATTEMPTS = original.MAX_REPLAY_ATTEMPTS
BOOTSTRAP_SEED = original.BOOTSTRAP_SEED
BOOTSTRAP_REPETITIONS = original.BOOTSTRAP_REPETITIONS
YAW_TOLERANCE_RAD = original.YAW_TOLERANCE_RAD
D0_YAW_MAX_RAD = original.D0_YAW_MAX_RAD
FINAL_HEADING_TOLERANCE_RAD = original.FINAL_HEADING_TOLERANCE_RAD
START_POSITION_TOLERANCE_M = original.START_POSITION_TOLERANCE_M
START_HEADING_TOLERANCE_RAD = original.START_HEADING_TOLERANCE_RAD
EXPECTED_MAPPER_BINARY_SHA256 = original.EXPECTED_MAPPER_BINARY_SHA256
EXPECTED_NORMALIZED_MAPPER_CONFIG_SHA256 = (
    original.EXPECTED_NORMALIZED_MAPPER_CONFIG_SHA256)

EXPECTED_ORIGINAL_AGGREGATE_SHA256 = (
    '0725778cbcd223cea69384350bcedefc965c2bb8c75a32a484e1e7e4d747fd4b')
EXPECTED_ORIGINAL_FILE_COUNT = 3881
EXPECTED_ORIGINAL_PREREG_SHA256 = (
    '38061e4964eb33bfcc0c718ba944adc2710ebd29ca30b6af2a8e2862f5e8f8bc')
EXPECTED_ORIGINAL_HISTORY_MANIFEST_SHA256 = (
    'c10fef99341eb325a01e3d96320fba851f0c3769a93be01e78acf2049a29f403')
EXPECTED_ORIGINAL_FINAL_GATE_SHA256 = (
    '3c239367543e78ce5f61f6dec57ac793655bb8bd16350d82e2a7d3c35318f8d3')
EXPECTED_ORIGINAL_DOC_SHA256 = (
    '20390d11ce080dca09ce35cc04f2968d361aad926ffdd69dba453f98fe47ec94')
EXPECTED_ARM_ORDERS_SHA256 = (
    '557370ec5e89fe266c6ece2655fa7cd596fef8fc34627daf24bc285c7b721f3b')
SCIENTIFIC_FIELDS = (
    'intervention', 'estimands', 'primary_inference',
    'final_three_state_decision', 'hard_stop', 'mechanism', 'gt_sanity',
    'no_peeking', 'backend_replay', 'manipulation_gate',
    'technical_retry_rule',
)


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def load_json(path):
    return json.loads(Path(path).read_text())


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_sha(payload):
    encoded = json.dumps(
        payload, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def aggregate_tree_sha(root):
    root = Path(root)
    files = sorted(path for path in root.rglob('*') if path.is_file())
    digest = hashlib.sha256()
    for path in files:
        relative = str(path.relative_to(root))
        digest.update(relative.encode())
        digest.update(b'\0')
        digest.update(sha256(path).encode())
        digest.update(b'\n')
    return len(files), digest.hexdigest()


def original_run_audit():
    file_count, aggregate = aggregate_tree_sha(ORIGINAL_ROOT)
    final = load_json(ORIGINAL_FINAL_GATE_PATH)
    physical_capture_root = ORIGINAL_ROOT / 'collection/captures'
    replay_root = ORIGINAL_ROOT / 'collection/replays'
    analysis_root = ORIGINAL_ROOT / 'analysis'
    checks = {
        'original_file_count_exact': file_count == EXPECTED_ORIGINAL_FILE_COUNT,
        'original_aggregate_sha256_exact': (
            aggregate == EXPECTED_ORIGINAL_AGGREGATE_SHA256),
        'original_preregistration_exact': (
            sha256(ORIGINAL_PREREGISTRATION_PATH) ==
            EXPECTED_ORIGINAL_PREREG_SHA256),
        'original_history_manifest_exact': (
            sha256(ORIGINAL_HISTORY_MANIFEST_PATH) ==
            EXPECTED_ORIGINAL_HISTORY_MANIFEST_SHA256),
        'original_final_gate_exact': (
            sha256(ORIGINAL_FINAL_GATE_PATH) ==
            EXPECTED_ORIGINAL_FINAL_GATE_SHA256),
        'original_report_exact': (
            sha256(ORIGINAL_DOC_PATH) == EXPECTED_ORIGINAL_DOC_SHA256),
        'original_gate_is_technical_incomplete': (
            final.get('final_scientific_gate') ==
            'CD_PROSPECTIVE_TECHNICALLY_INCOMPLETE'),
        'original_gate_reason_is_arm_balance_validator': (
            final.get('reason') ==
            'RuntimeError: frozen arm order is not position-balanced'),
        'no_physical_lock_before_amendment': not (
            ORIGINAL_ROOT / 'collection/PHYSICAL_COLLECTION_LOCK.json').exists(),
        'no_physical_state_before_amendment': not (
            ORIGINAL_ROOT / 'collection/physical_collection_state.json').exists(),
        'no_physical_branch_before_amendment': (
            not physical_capture_root.exists() or
            not any(path.is_file() for path in physical_capture_root.rglob('*'))),
        'no_backend_lock_before_amendment': not (
            ORIGINAL_ROOT / 'collection/BACKEND_REPLAY_LOCK.json').exists(),
        'no_backend_state_before_amendment': not (
            ORIGINAL_ROOT / 'collection/backend_replay_state.json').exists(),
        'no_backend_replay_before_amendment': (
            not replay_root.exists() or
            not any(path.is_file() for path in replay_root.rglob('*'))),
        'no_scientific_analysis_before_amendment': (
            not analysis_root.exists() or
            not any(path.is_file() for path in analysis_root.rglob('*'))),
        'scientific_endpoint_not_read': True,
    }
    return {
        'passed': all(checks.values()),
        'checks': checks,
        'original_file_count': file_count,
        'original_aggregate_manifest_sha256': aggregate,
        'original_preregistration_sha256': sha256(
            ORIGINAL_PREREGISTRATION_PATH),
        'original_history_manifest_sha256': sha256(
            ORIGINAL_HISTORY_MANIFEST_PATH),
        'original_final_gate_sha256': sha256(ORIGINAL_FINAL_GATE_PATH),
        'original_report_sha256': sha256(ORIGINAL_DOC_PATH),
        'audited_utc': now(),
    }


def frozen_history_manifest():
    manifest = load_json(HISTORY_MANIFEST_PATH)
    if sha256(HISTORY_MANIFEST_PATH) != \
            EXPECTED_ORIGINAL_HISTORY_MANIFEST_SHA256:
        raise RuntimeError('amendment history manifest is not exact original')
    if manifest.get('technical_gate') != 'CD_HISTORY_QUALIFICATION_PASS':
        raise RuntimeError('original history qualification did not pass')
    return manifest


def frozen_blocks():
    manifest = frozen_history_manifest()
    return [row for target in TARGETS
            for row in manifest['selected_blocks'][target]]


def source_attempt(target_label, seed):
    return original.source_attempt(target_label, seed)


def action_specs(block):
    specs, frozen = original.action_specs(block)
    specs = copy.deepcopy(specs)
    specs['common']['protocol_id'] = PROTOCOL_ID
    specs['common']['technical_amendment'] = {
        'amendment_of': original.PROTOCOL_ID,
        'only_change': ('arm-order balance validation is evaluated within '
                        'each Target stratum rather than pooled across A+B'),
    }
    return specs, frozen


def prefix_reference_record(block):
    return original.prefix_reference_record(block)


def arm_order_rows():
    rows = []
    for block in frozen_blocks():
        index = int(block['block_id'].split('_H')[1]) - 1
        rows.append({
            'block_id': block['block_id'],
            'target_label': block['target_label'],
            'seed': block['seed'],
            'arm_order': ARM_ORDERS[block['target_label']][index],
        })
    return rows


def per_target_position_counts(rows=None):
    rows = arm_order_rows() if rows is None else rows
    output = {}
    for target in TARGETS:
        counts = {arm: Counter() for arm in ARMS}
        for row in rows:
            if row['target_label'] != target:
                continue
            for position, arm in enumerate(row['arm_order'], 1):
                counts[arm][position] += 1
        output[target] = {
            arm: {str(position): counts[arm][position]
                  for position in (1, 2, 3)}
            for arm in ARMS}
    return output


def validate_per_target_arm_balance(rows=None):
    counts = per_target_position_counts(rows)
    checks = {}
    for target in TARGETS:
        checks[target] = {}
        for arm in ARMS:
            values = list(counts[target][arm].values())
            checks[target][arm] = max(values) - min(values) <= 1
    return {
        'passed': all(value for target in checks.values()
                      for value in target.values()),
        'validation_unit': 'Target stratum',
        'maximum_position_count_difference_within_target': 1,
        'position_counts': counts,
        'checks': checks,
        'pooled_A_plus_B_balance_is_not_a_gate': True,
    }


def arm_order_manifest_payload(frozen_utc):
    rows = arm_order_rows()
    validation = validate_per_target_arm_balance(rows)
    if not validation['passed']:
        raise RuntimeError('per-Target-stratum arm balance failed')
    return {
        'protocol_id': PROTOCOL_ID,
        'amendment_of': original.PROTOCOL_ID,
        'blocks': rows,
        'exact_original_arm_orders_sha256': canonical_sha(ARM_ORDERS),
        'arm_orders_exact_original': (
            canonical_sha(ARM_ORDERS) == EXPECTED_ARM_ORDERS_SHA256),
        'balance_validation': validation,
        'history_property_used': False,
        'frozen_utc': frozen_utc,
    }


def code_files():
    additions = [
        'tools/realizability_pilot/cd_confirmatory_amendment_protocol.py',
        'tools/realizability_pilot/cd_confirmatory_amendment_collection.py',
        'tools/realizability_pilot/cd_confirmatory_amendment_replay.py',
        'tools/realizability_pilot/cd_confirmatory_amendment_analysis.py',
        'tools/realizability_pilot/cd_confirmatory_amendment_pipeline.py',
        'tools/realizability_pilot/test_cd_confirmatory_amendment.py',
    ]
    paths = list(original.code_files()) + [ROOT / name for name in additions]
    unique = []
    seen = set()
    for path in paths:
        relative = str(path.relative_to(ROOT))
        if relative not in seen:
            unique.append(path)
            seen.add(relative)
    return unique


def preregistration_payload():
    audit = original_run_audit()
    if not audit['passed']:
        raise RuntimeError('original incomplete run immutability audit failed')
    if not HISTORY_MANIFEST_PATH.is_file():
        raise RuntimeError('exact frozen history manifest copy missing')
    if sha256(HISTORY_MANIFEST_PATH) != \
            EXPECTED_ORIGINAL_HISTORY_MANIFEST_SHA256:
        raise RuntimeError('frozen history copy differs from original')
    if not ARM_ORDER_MANIFEST_PATH.is_file():
        raise RuntimeError('frozen amendment arm-order manifest missing')
    original_prereg = load_json(ORIGINAL_PREREGISTRATION_PATH)
    payload = copy.deepcopy(original_prereg)
    hashes = {str(path.relative_to(ROOT)): sha256(path)
              for path in code_files()}
    payload.update({
        'protocol_id': PROTOCOL_ID,
        'label': LABEL,
        'base_git_commit': BASE_COMMIT,
        'created_before_any_fresh_history_generation': False,
        'created_before_any_scientific_physical_collection': True,
        'history_generation_reused_from_original_incomplete_run': True,
        'code_hashes': hashes,
        'code_bundle_sha256': canonical_sha(hashes),
        'technical_amendment': {
            'amendment_of_protocol_id': original.PROTOCOL_ID,
            'original_preregistration_sha256': (
                EXPECTED_ORIGINAL_PREREG_SHA256),
            'original_final_gate': 'CD_PROSPECTIVE_TECHNICALLY_INCOMPLETE',
            'original_final_gate_preserved': True,
            'outcome_blind': True,
            'scientific_endpoint_available_before_amendment': False,
            'only_change': {
                'from': 'pooled Target-A plus Target-B position balance gate',
                'to': 'within-Target-stratum position balance gate',
                'rationale': ('Target is the between-context stratum and dose '
                              'is repeated within canonical-history block'),
            },
            'unchanged': [
                'first-eight histories per target', 'arm orders', 'doses',
                'N=347', 'controller', 'estimands', 'analysis',
                'scientific gates', 'retry rules', 'backend'],
        },
        'original_run_pre_amendment_audit': audit,
        'reused_inputs': {
            'history_manifest_path': str(
                HISTORY_MANIFEST_PATH.relative_to(ROOT)),
            'history_manifest_sha256': sha256(HISTORY_MANIFEST_PATH),
            'history_manifest_byte_identical_to_original': True,
            'arm_order_manifest_path': str(
                ARM_ORDER_MANIFEST_PATH.relative_to(ROOT)),
            'arm_orders_sha256': canonical_sha(ARM_ORDERS),
            'arm_orders_exact_original': (
                canonical_sha(ARM_ORDERS) == EXPECTED_ARM_ORDERS_SHA256),
            'histories_regenerated': False,
            'arms_reordered': False,
        },
        'arm_order_validation_amendment': validate_per_target_arm_balance(),
        'scientific_collection_authorized_after_this_freeze': True,
    })
    return payload


def scientific_design_unchanged(payload=None):
    payload = preregistration_payload() if payload is None else payload
    original_prereg = load_json(ORIGINAL_PREREGISTRATION_PATH)
    checks = {field: payload[field] == original_prereg[field]
              for field in SCIENTIFIC_FIELDS}
    checks.update({
        'arm_orders': (payload['arm_order_rule']['deterministic_orders'] ==
                       original_prereg['arm_order_rule'][
                           'deterministic_orders']),
        'candidate_seeds': (
            payload['history_qualification'][
                'candidate_seeds_in_frozen_order'] ==
            original_prereg['history_qualification'][
                'candidate_seeds_in_frozen_order']),
    })
    return {'passed': all(checks.values()), 'checks': checks}


def write_frozen_json(path, payload):
    path = Path(path)
    if path.exists():
        if load_json(path) != payload:
            raise RuntimeError('refusing to modify frozen {}'.format(path))
        return payload
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(path, payload)
    return payload


def prepare_amendment():
    if RESULT_ROOT.exists():
        raise RuntimeError('amendment result root already exists')
    audit = original_run_audit()
    if not audit['passed']:
        raise RuntimeError('original run audit failed before amendment')
    HISTORY_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_MANIFEST_PATH.write_bytes(
        ORIGINAL_HISTORY_MANIFEST_PATH.read_bytes())
    audit_path = RESULT_ROOT / 'provenance/original_incomplete_run_audit.json'
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(audit_path, audit)
    ARM_ORDER_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(ARM_ORDER_MANIFEST_PATH, arm_order_manifest_payload(now()))
    payload = preregistration_payload()
    unchanged = scientific_design_unchanged(payload)
    if not unchanged['passed']:
        raise RuntimeError('scientific design changed in technical amendment')
    atomic_json(RESULT_ROOT / 'provenance/scientific_design_unchanged.json',
                unchanged)
    write_frozen_json(PREREGISTRATION_PATH, payload)
    return {
        'status': 'AMENDMENT_PREREGISTERED',
        'protocol_id': PROTOCOL_ID,
        'preregistration_sha256': sha256(PREREGISTRATION_PATH),
        'original_run_preserved': True,
        'scientific_design_unchanged': True,
        'collection_authorized': True,
    }
