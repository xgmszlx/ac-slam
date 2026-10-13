#!/usr/bin/python3
"""Offline qualification forensics only; never import ROS or run the sealed suite.

Without --write this command is read-only. With --write it creates/refreshes only
three post-hoc audit files, never protocols, attempts, metrics or original gates.
The local-only raw captures are needed to reproduce counts and manifests.
"""
import argparse
import csv
import hashlib
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'results/research_direction/localization_recovery_phase0'
ASSETS = Path('/home/wcqw/ac-slam')


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def metadata(path):
    return {'path': str(path.relative_to(OUT)), 'bytes': path.stat().st_size,
            'sha256': sha(path)}


def stream_stats(path, check_map_base=False):
    stamps, count, missing = [], 0, 0
    with path.open() as stream:
        for line in stream:
            row = json.loads(line)
            count += 1
            if row.get('stamp') is not None:
                stamps.append(float(row['stamp']))
            if check_map_base and row.get('map_base') is None:
                missing += 1
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    return {'rows': count, 'map_base_missing': missing if check_map_base else None,
            'span_sim_s': max(stamps) - min(stamps) if stamps else None,
            'median_consecutive_gap_sim_s': statistics.median(gaps) if gaps else None,
            'max_consecutive_gap_sim_s': max(gaps) if gaps else None}


def audit():
    checks = []

    def check(path, expected, group):
        actual = sha(path) if path.is_file() else None
        checks.append({'path': str(path), 'group': group, 'expected': expected,
                       'actual': actual, 'equal': actual == expected})

    prereg = read_json(OUT / 'protocol/preregistration.json')
    for name in ('preregistration', 'technical_amendment1', 'technical_amendment2'):
        protocol = OUT / ('protocol/' + name + '.json')
        check(protocol, read_json(protocol.with_name(name + '_hash.json'))['sha256'],
              'protocol_hash')
    for path, digest in prereg['frozen_code_sha256'].items():
        check(ROOT / path, digest, 'frozen_original_source')
    for name, key in (('technical_amendment1', 'amendment_code_sha256'),
                      ('technical_amendment2', 'amendment2_code_sha256')):
        data = read_json(OUT / ('protocol/' + name + '.json'))
        check(Path(__file__).with_name(name + '.py'), data[key], 'amendment_source')
        for path, digest in data['immutable_R0_sha256'].items():
            check(OUT / path, digest, name + '_protected_attempts')
    for path, digest in read_json(OUT / 'audit/protected_input_hashes.json').items():
        check(ASSETS / path, digest, 'old_worktree_and_binaries')
    for row in read_json(OUT / 'audit/local_only_capture_manifest.json')['files']:
        check(OUT / row['path'], row['sha256'], 'sealed_local_capture')
    mismatches = [r for r in checks if not r['equal']]
    if mismatches:
        raise RuntimeError('Immutable input mismatch: ' + json.dumps(mismatches))

    ledger = read_json(OUT / 'protocol/budget_ledger.json')
    expected = ['NORMAL_GEOMETRY_271001', 'NORMAL_GEOMETRY_271001_A1',
                'NORMAL_GEOMETRY_271001_A2']
    if [r['episode_id'] for r in ledger['attempts']] != expected:
        raise RuntimeError('Not the sealed three-attempt ledger')
    rows, details = [], []
    for attempt in ledger['attempts']:
        directory = OUT / attempt['kind'] / attempt['episode_id']
        state = read_json(directory / 'run_state.json')
        stream = {n: stream_stats(directory / (n + '.jsonl'), n == 'scan_stream')
                  for n in ('scan_stream', 'gt_stream', 'odom_stream', 'tf_stream',
                            'control_stream', 'keyscan_stream')}
        task = (directory / 'phase_markers.json').exists()
        endpoint = (directory / 'episode_result.json').exists()
        if task or endpoint or (directory / 'metrics.json').exists():
            raise RuntimeError('Unexpected scientific artifact: review before interpreting')
        if state['status'] != 'TECHNICAL_FAILURE' or attempt['status'] != state['status']:
            raise RuntimeError('Not a sealed failed qualification')
        row = {'episode_id': attempt['episode_id'], 'seed': attempt['spec']['seed'],
               'status': state['status'], 'reason': state['reason'],
               'wall_duration_s': state['wall_duration_s'],
               'scientific_task_started': task, 'scientific_endpoint': endpoint}
        row.update({n: s['rows'] for n, s in stream.items()})
        rows.append(row)
        details.append({'episode_id': attempt['episode_id'], 'streams': stream,
                        'metrics_computed': False})

    snapshots = []
    for path in sorted((OUT / 'baseline').glob('*/loaded_mapper_libraries.json')):
        relevant = set()
        for capture in read_json(path).values():
            for line in capture['maps'].splitlines():
                p = line.split()[-1]
                if p.startswith('/') and any(n in p for n in ('nav2d_karto/mapper',
                        'libMultiMapper', 'libOpenKarto', 'libSelfLocalizer', 'libtbb',
                        'libcholmod', 'libceres', 'libCSparse', 'libcxsparse')):
                    relevant.add(p)
        snapshots.append({'local_only_snapshot': metadata(path),
                          'relevant_loaded_files': [
                              {'path': p, 'sha256_at_postcheck': sha(p)}
                              for p in sorted(relevant)]})
    return rows, {'all_immutable_checks_equal': True, 'checks': len(checks),
                  'total_attempts': len(rows), 'valid_scientific_episodes': 0,
                  'stream_forensics': details, 'scientific_metrics_computed': False}, snapshots


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='write only post-hoc audit outputs')
    args = parser.parse_args()
    rows, summary, snapshots = audit()
    if args.write:
        for name, obj in (('postmortem_verification.json', summary),
                          ('runtime_library_manifest.json', snapshots)):
            path = OUT / 'audit' / name
            path.write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + '\n')
        with (OUT / 'audit/qualification_attempts.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    print(json.dumps({k: v for k, v in summary.items() if k != 'stream_forensics'}, indent=2))


if __name__ == '__main__':
    main()
