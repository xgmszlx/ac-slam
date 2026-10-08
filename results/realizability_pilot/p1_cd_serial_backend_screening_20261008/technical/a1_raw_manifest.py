#!/usr/bin/python3
"""Inventory local ignored A1 raw evidence without uploading its bytes."""

import hashlib
import json
from pathlib import Path

SCREEN = Path(__file__).resolve().parents[1]
RUNS = SCREEN / 'technical/runs'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    entries = []
    for path in sorted(RUNS.rglob('*')):
        if path.is_file():
            entries.append({'path': str(path.relative_to(SCREEN)),
                            'size_bytes': path.stat().st_size,
                            'sha256': sha(path)})
    payload = {'root': str(SCREEN), 'run_count': len(list(RUNS.glob('run_*'))),
               'file_count': len(entries), 'files': entries,
               'scope_note': 'Only new A1 technical/runs raw artifacts; old ignored raw not covered'}
    output = SCREEN / 'analysis/raw_artifact_manifest.json'
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'run_count': payload['run_count'], 'file_count': payload['file_count']}))


if __name__ == '__main__':
    main()
