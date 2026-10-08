#!/usr/bin/python3
"""Independent read-only postcheck of A1 runtime and no-suffix evidence."""

import hashlib
import json
from pathlib import Path

SCREEN = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    manifest = load(SCREEN / 'protocol/frozen_run_manifest.json')
    runtime_a0 = load(SCREEN / 'audit/runtime_library_provenance.json')
    a0_files = {row['path']: row['sha256'] for row in runtime_a0['proc_maps_mapped_files']}
    rows = []
    for row in manifest['rows']:
        directory = Path(row['output_path'])
        replay = load(directory / 'unified_replay_result.json')
        result = load(directory / 'a1_result.json')
        actual_files = set(replay['mapper_runtime']['mapped_paths'])
        actual_hashes = {path: sha(path) if Path(path).is_file() else None
                         for path in actual_files}
        expected = manifest['inputs'][row['block']]
        checks = {
            'same_loaded_file_set_as_A0': actual_files == set(a0_files),
            'same_loaded_file_hashes_as_A0': actual_hashes == a0_files,
            'input_byte_hash_exact': sha(directory / 'canonical_prefix.jsonl') == expected['prefix_byte_sha256'],
            'input_semantic_hash_exact': result['input_semantic_sha256'] == expected['prefix_semantic_sha256'],
            'expected_published_processed_equal': (row['expected_prefix_count'] ==
                                                    replay['prefix_publisher']['published'] ==
                                                    replay['processed_prefix_count']),
            'publisher_subscriber_connected': replay['prefix_publisher']['connection_confirmed'],
            'synchronous_barrier': (not replay['background_graph_dump_used'] and
                                    not replay['fixed_sleep_used_as_drain_barrier'] and
                                    'synchronous_G_pre_saved' in replay['timeline']),
            'no_suffix': (not replay['suffix_published'] and
                          replay['suffix_record_count'] == 0 and
                          not (directory / 'publisher_suffix_status.json').exists() and
                          not (directory / 'probe_suffix.jsonl').exists()),
            'edge_provenance_count': result['constraint_provenance_count'] == result['edges'],
            'B_gate_agrees_with_six_decimal_reference': (
                row['mode'] != 'B' or replay['prefix_gate_passed'] ==
                result['branch_style_would_pass']),
        }
        rows.append({'ordinal': row['ordinal'], 'block': row['block'],
                     'mode': row['mode'], 'checks': checks, 'all_checks_pass': all(checks.values())})
    output = {'planned': 24, 'checked': len(rows),
              'all_checks_pass': len(rows) == 24 and all(x['all_checks_pass'] for x in rows),
              'runs': rows,
              'meaning': 'runtime and prefix-only technical checks; no scientific endpoint read'}
    path = SCREEN / 'analysis/a1_postcheck.json'
    path.write_text(json.dumps(output, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'checked': output['checked'], 'all_checks_pass': output['all_checks_pass']}))
    if not output['all_checks_pass']:
        raise SystemExit('A1 postcheck failed')


if __name__ == '__main__':
    main()
