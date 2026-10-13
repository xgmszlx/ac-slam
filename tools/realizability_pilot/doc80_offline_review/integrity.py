#!/usr/bin/python3
"""Doc-80 stage 1: attempt-ledger and local-only-file integrity.

Answers Doc 80 section 3.1/3.2 with explicit gaps instead of silent skips.
"""

import csv
import hashlib
import json
from pathlib import Path

from . import common

PLANNED_EPISODES = [
    'D79_B_Lplus_1', 'D79_B_Lminus_1', 'D79_C_Lminus_1', 'D79_C_Lplus_1',
    'D79_B_Lminus_2', 'D79_B_Lplus_2', 'D79_C_Lplus_2', 'D79_C_Lminus_2',
]
BUDGET = 8
PHYSICAL_FAILURE = ('D79_B_Lplus_1', 'attempt_01')


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def ledger_audit(doc79_root=common.DOC79):
    state = common.load_json(Path(doc79_root) / 'suite_state.json', {}) or {}
    attempts = common.discover_attempts(doc79_root)
    by_episode = {}
    for run in attempts:
        by_episode.setdefault(run['episode_id'], []).append(run)
    findings = []
    ok = True

    # budget / coverage
    if state.get('attempts_used') != BUDGET:
        ok = False
        findings.append('suite attempts_used={} != budget {}'.format(
            state.get('attempts_used'), BUDGET))
    planned = [episode['episode_id'] for episode in state.get('episodes', [])]
    if planned != PLANNED_EPISODES:
        ok = False
        findings.append('planned episode order differs from the frozen plan')

    status_counts = {}
    for episode in state.get('episodes', []):
        status_counts[episode['status']] = status_counts.get(episode['status'], 0) + 1
    if status_counts.get('SUCCEEDED') != 7 or status_counts.get('PENDING') != 1:
        ok = False
        findings.append('unexpected suite status counts: {}'.format(status_counts))

    # attempt numbering / overwrite check
    for episode_id, runs in sorted(by_episode.items()):
        numbers = sorted(int(run['attempt'].split('_')[-1]) for run in runs)
        expected = list(range(1, len(numbers) + 1))
        if numbers != expected:
            ok = False
            findings.append('{} attempt numbering gap: {}'.format(episode_id, numbers))
        for run in runs:
            if run['attempt'] == 'attempt_01' and episode_id == PHYSICAL_FAILURE[0]:
                if run['result'].get('status') != 'FAILED':
                    ok = False
                    findings.append('expected FAILED attempt_01 for {}, got {}'.format(
                        episode_id, run['result'].get('status')))
                else:
                    reason = run['result'].get('reason', '')
                    if 'GT 0.771' not in reason:
                        findings.append('physical failure reason changed: {}'.format(reason))

    unexpected = sorted(set(by_episode) - set(PLANNED_EPISODES))
    if unexpected:
        ok = False
        findings.append('episodes present but not planned: {}'.format(unexpected))

    # hidden reruns: any attempt beyond the recorded suite bookkeeping
    recorded = 0
    for episode in state.get('episodes', []):
        recorded += len(episode.get('attempts', []))
    actual = sum(len(runs) for runs in by_episode.values())
    if recorded != actual:
        ok = False
        findings.append('attempt dirs ({}) != suite bookkeeping ({})'.format(
            actual, recorded))

    # no selective deletion: every failed/physical attempt has its raw evidence
    failure_dir = Path(doc79_root) / 'runs' / PHYSICAL_FAILURE[0] / PHYSICAL_FAILURE[1]
    evidence = ['scan_stream.jsonl', 'episode_result.json', 'keyscan_stream.jsonl']
    missing = [name for name in evidence if not (failure_dir / name).is_file()]
    if missing:
        ok = False
        findings.append('failed-attempt evidence missing: {}'.format(missing))

    return {
        'ok': ok,
        'findings': findings,
        'suite_status': state.get('status'),
        'suite_halt_reason': state.get('halt_reason'),
        'attempts_used': state.get('attempts_used'),
        'budget': BUDGET,
        'episode_status_counts': status_counts,
        'attempts_on_disk': actual,
        'attempts_recorded': recorded,
        'physical_failure': '{} {}'.format(*PHYSICAL_FAILURE),
        'independent_unit': 'episode (cross differences are not independent trials)',
    }


def local_only_audit(doc79_root=common.DOC79):
    registry = Path(doc79_root) / 'analysis' / 'local_only_files.csv'
    rows = []
    missing = []
    mismatched = []
    verified = 0
    total_bytes = 0
    if not registry.is_file():
        return {'ok': False, 'findings': ['local_only_files.csv missing'],
                'rows': 0, 'verified': 0, 'missing': [], 'mismatched': []}
    with open(registry) as handle:
        for row in csv.DictReader(handle):
            path = Path(row['path'])
            if not path.is_absolute():
                path = common.REPO / path
            expected = row['sha256']
            if not path.is_file():
                missing.append(row['path'])
                rows.append({'path': row['path'], 'status': 'MISSING'})
                continue
            actual = sha256(path)
            total_bytes += path.stat().st_size
            if actual != expected:
                mismatched.append(row['path'])
                rows.append({'path': row['path'], 'status': 'SHA256_MISMATCH',
                             'expected': expected, 'actual': actual})
            else:
                verified += 1
                rows.append({'path': row['path'], 'status': 'VERIFIED'})
    ok = not missing and not mismatched
    findings = []
    if missing:
        findings.append('local-only files missing: {}'.format(len(missing)))
    if mismatched:
        findings.append('local-only files with SHA256 mismatch: {}'.format(
            len(mismatched)))
    return {'ok': ok, 'findings': findings, 'rows': len(rows),
            'verified': verified, 'missing': missing, 'mismatched': mismatched,
            'total_bytes': total_bytes, 'detail': rows}


def run(doc80_root=common.DOC80, doc79_root=common.DOC79):
    ledger = ledger_audit(doc79_root)
    files = local_only_audit(doc79_root)
    payload = {
        'doc': '80',
        'role': 'input integrity: attempt ledger + local-only raw files',
        'git_head_baseline': '4f290fc0691324e13158d72fa77c18278e28b71e',
        'ledger': ledger,
        'local_only_files': {key: value for key, value in files.items()
                             if key != 'detail'},
        'ok': ledger['ok'] and files['ok'],
    }
    common.write_json(Path(doc80_root) / 'audit' / 'input_integrity.json', payload)
    common.write_csv(Path(doc80_root) / 'audit' / 'local_only_file_verification.csv',
                     files.get('detail', []))
    return payload
