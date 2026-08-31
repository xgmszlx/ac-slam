#!/usr/bin/python3
"""Frozen Phase 4C formal map, method, ordering and environment helpers."""

import hashlib
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / 'baseline' / 'Graph-Based_SLAM-Aware_Exploration'
FORMAL_ROOT = ROOT / 'results' / 'phase4c' / 'formal'
SCIENTIFIC_BASE_COMMIT = '3ffaa2672816d5f5f20e0d8019054bdd47f2961b'

CONDITIONS = {
    'A': {'directory': 'A_original', 'name': 'Original', 'oracle_mode': 0},
    'B': {'directory': 'B_always_trace', 'name': 'Always-Trace', 'oracle_mode': 1},
    'C': {'directory': 'C_selective', 'name': 'Selective', 'oracle_mode': 2},
}
ORDERS = {
    21001: ('A', 'B', 'C'),
    21002: ('B', 'C', 'A'),
    21003: ('C', 'A', 'B'),
    21004: ('A', 'C', 'B'),
    21005: ('B', 'A', 'C'),
}

COMMON_INC_HASHES = {
    'floorplan.inc': '9087664e52773d63ea7e0546b10eadfe2e224a242b5b31dacb5cd756f6347059',
    'hokuyo.inc': '63187469b0c9173f2ab1e5086723283d8e920007e1a77030a64d583cdf19dc32',
    'p3at.inc': 'a619126df1a551ba06f552a3f981e00fdfd12c8daf779cf35d4d79f98579c2b1',
}

MAPS = {
    'map8': {
        'id': 'map8', 'map_name': 'map8/map8',
        'robot_position': '0.0 0.0 0', 'start_pose': [0.0, 0.0, 0.0],
        'map_width': 86.8,
        'source_dir': BASELINE / 'world' / 'map8',
        'runtime_dir': BASELINE / 'world' / 'map8',
        'gt_yaml': str(BASELINE / 'world' / 'map8' / 'map8.yaml'),
        'frozen_sha256': {
            **COMMON_INC_HASHES,
            'map8.png': '22a27847ccef060409e63ed6bea949265c52f8ca4f35545a4756697de0ed1046',
            'map8.world': '6beefe415afd84c587f5c31b81a1d09fa176230e146685ed11ad25836e663cb5',
            'map8.xml': 'ec78c76cfb3747f99e744e8efb166f07df580ef1a5aedce5653bdaf37ae4d9a3',
            'map8.yaml': 'b4380d64c3d1508fcdf4f24af5593203c5cef896707b65975f3e3c784a1f6544',
        },
    },
    'radish_mexico': {
        'id': 'radish_mexico', 'map_name': 'radish_mexico/radish_mexico',
        'robot_position': '-6.25 -1.6 0', 'start_pose': [-6.25, -1.6, 0.0],
        'map_width': 101.55,
        'source_dir': ROOT / 'results' / 'phase4c1' / 'environments' / 'radish_mexico',
        'runtime_dir': BASELINE / 'world' / 'radish_mexico',
        'gt_yaml': str(BASELINE / 'world' / 'radish_mexico' / 'radish_mexico.yaml'),
        'frozen_sha256': {
            **COMMON_INC_HASHES,
            'radish_mexico.png': 'b58741fbe042261c43d1f6b8500ad40612e4d6c8178f6a96ecbbb300c822ac2e',
            'radish_mexico.world': 'd17f1bc50ec33c7e1ab7ce528fce450a2f86341c7376aec1338d0115d89959c4',
            'radish_mexico.xml': '1efee1830bd9b29462a948d3dd67bf5338b7fc2658ec85962421ea665f33c75b',
            'radish_mexico.yaml': '1e84884a09665f6b3ddd85fb2cc1d9b22403a7e38d8fac238f89c4eed328e886',
        },
    },
}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify_environment(config, directory_key='source_dir'):
    directory = Path(config[directory_key])
    actual = {}
    for name, expected in config['frozen_sha256'].items():
        path = directory / name
        if not path.is_file():
            raise RuntimeError('frozen environment file missing: {}'.format(path))
        actual[name] = sha256(path)
        if actual[name] != expected:
            raise RuntimeError('frozen environment hash mismatch: {}'.format(path))
    return actual


def materialize_runtime_environment(config):
    verify_environment(config, 'source_dir')
    source = Path(config['source_dir'])
    runtime = Path(config['runtime_dir'])
    if source.resolve() != runtime.resolve():
        runtime.mkdir(parents=True, exist_ok=True)
        for name in sorted(config['frozen_sha256']):
            target = runtime / name
            if target.exists() and sha256(target) != config['frozen_sha256'][name]:
                raise RuntimeError('refusing to overwrite mismatched runtime file: {}'.format(target))
            if not target.exists():
                shutil.copy2(source / name, target)
    return verify_environment(config, 'runtime_dir')
