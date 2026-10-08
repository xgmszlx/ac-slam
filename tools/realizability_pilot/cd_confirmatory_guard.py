#!/usr/bin/python3
"""Fail-closed no-peeking and lock guards for the CD experiment."""

from pathlib import Path

from cd_confirmatory_protocol import (
    PREREGISTRATION_PATH, RESULT_ROOT, load_json, sha256,
)


PHYSICAL_LOCK = RESULT_ROOT / 'collection/PHYSICAL_COLLECTION_LOCK.json'
BACKEND_LOCK = RESULT_ROOT / 'collection/BACKEND_REPLAY_LOCK.json'
ANALYSIS_ROOT = RESULT_ROOT / 'analysis'
DECISION_ROOT = RESULT_ROOT / 'decision'


def assert_prelock_no_scientific_outputs(analysis_root=ANALYSIS_ROOT,
                                         decision_root=DECISION_ROOT):
    forbidden = []
    for root in (Path(analysis_root), Path(decision_root)):
        if root.exists():
            forbidden.extend(str(path) for path in root.rglob('*')
                             if path.is_file())
    if forbidden:
        raise RuntimeError(
            'scientific output exists before backend lock: {}'.format(
                forbidden))
    return True


def assert_backend_lock_allows_analysis(
        preregistration_path=PREREGISTRATION_PATH,
        physical_lock=PHYSICAL_LOCK, backend_lock=BACKEND_LOCK):
    preregistration_path = Path(preregistration_path)
    physical_lock = Path(physical_lock)
    backend_lock = Path(backend_lock)
    if not preregistration_path.is_file():
        raise RuntimeError('scientific analysis requires preregistration')
    if not physical_lock.is_file() or not backend_lock.is_file():
        raise RuntimeError('scientific analysis requires both locks')
    physical = load_json(physical_lock)
    backend = load_json(backend_lock)
    if not physical.get('complete'):
        raise RuntimeError('physical lock is technically incomplete')
    if not backend.get('complete'):
        raise RuntimeError('backend lock is technically incomplete')
    if backend.get('preregistration_sha256') != sha256(
            preregistration_path):
        raise RuntimeError('backend lock preregistration hash mismatch')
    if backend.get('physical_collection_lock_sha256') != sha256(
            physical_lock):
        raise RuntimeError('backend lock physical hash mismatch')
    return physical, backend
