#!/usr/bin/python3
"""Hash-only verification of protected old experiments; no endpoint parsing."""

import hashlib
import json
import subprocess
from pathlib import Path

SCREEN = Path(__file__).resolve().parents[1]
ROOT = SCREEN.parents[2]
BASE = ROOT / 'results/realizability_pilot'
ORIGINAL = BASE / 'p1_context_disentangle_confirmatory_20260930'
EXPECTED_AGGREGATE = '0725778cbcd223cea69384350bcedefc965c2bb8c75a32a484e1e7e4d747fd4b'
PROTECTED = [
    'p1_v14_confirmatory_20260928',
    'p1_v14_heterogeneity_20260928',
    'p1_context_disentangle_t_20260928',
    'p1_context_disentangle_confirmatory_20260930',
    'p1_context_disentangle_confirmatory_amendment1_20260930',
    'p1_cd_prefix_forensic_f2_20261008',
]
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def aggregate_tree(root):
    paths = sorted(p for p in root.rglob('*') if p.is_file())
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b'\0')
        digest.update(sha(path).encode())
        digest.update(b'\n')
    return len(paths), digest.hexdigest()


def main():
    count, aggregate = aggregate_tree(ORIGINAL)
    v14 = BASE / 'p1_v14_confirmatory_20260928'
    v14_manifest = json.loads((BASE / 'p1_v14_heterogeneity_20260928/provenance/v14_immutable_manifest.json').read_text())
    critical = {}
    for relative, expected in v14_manifest['critical_sha256'].items():
        path = v14 / relative
        critical[relative] = {'expected': expected,
                              'actual': sha(path) if path.is_file() else None}
    diff = subprocess.run(['git', '-C', str(ROOT), 'diff', '--exit-code', 'HEAD', '--'] +
                          [str((BASE / name).relative_to(ROOT)) for name in PROTECTED],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    staged = subprocess.run(['git', '-C', str(ROOT), 'diff', '--cached', '--exit-code',
                             'HEAD', '--'] +
                            [str((BASE / name).relative_to(ROOT)) for name in PROTECTED],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    result = {
        'original_cd': {'file_count': count, 'expected_count': 3881,
                        'aggregate_sha256': aggregate,
                        'expected_aggregate_sha256': EXPECTED_AGGREGATE,
                        'exact': count == 3881 and aggregate == EXPECTED_AGGREGATE,
                        'coverage': 'all currently present regular files under original CD root only'},
        'v14_critical': {'files': critical,
                         'all_exact': all(x['actual'] == x['expected'] for x in critical.values())},
        'protected_tracked_dirs': PROTECTED,
        'tracked_diff_clean': diff.returncode == 0 and staged.returncode == 0,
        'tracked_diff_output': (diff.stdout + staged.stdout)[:2000],
        'coverage_limitation': ('No claim that ignored raw files in Amendment 1, v14, '
                                'v14-H, CD-T, or CD-F2 have an independent full-tree hash; '
                                'tracked files checked against HEAD and specific v14 critical hashes.'),
    }
    path = SCREEN / 'audit/protected_frozen_integrity.json'
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'original_exact': result['original_cd']['exact'],
                      'v14_critical_exact': result['v14_critical']['all_exact'],
                      'protected_tracked_clean': result['tracked_diff_clean']}))
    if not (result['original_cd']['exact'] and result['v14_critical']['all_exact'] and
            result['tracked_diff_clean']):
        raise SystemExit('protected frozen integrity FAILED')


if __name__ == '__main__':
    main()
