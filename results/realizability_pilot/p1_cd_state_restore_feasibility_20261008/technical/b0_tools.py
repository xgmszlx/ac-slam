#!/usr/bin/python3
"""Scoped CD-B0 manifests, input audit, freeze and graph comparisons."""
import argparse
import hashlib
import itertools
import json
import math
import subprocess
import time
from pathlib import Path

OUT = Path(__file__).resolve().parents[1]
ROOT = OUT.parents[2]
WS = Path('/home/wcqw/ac-slam_cd_b0_ws')
BASELINE = '6a0a5b89227d560c5bda2a2b2ef6b58ca96b2ff3'
SOURCE = ROOT / 'results/realizability_pilot/p1_v13_technical_20260920/histories/target_A/seed_81001/canonical_prefix.jsonl'
PROTECTED = [
    'p1_v14_confirmatory_20260928', 'p1_v14_heterogeneity_20260928',
    'p1_context_disentangle_t_20260928',
    'p1_context_disentangle_confirmatory_20260930',
    'p1_context_disentangle_confirmatory_amendment1_20260930',
    'p1_cd_prefix_forensic_f2_20261008',
    'p1_cd_serial_backend_screening_20261008',
]
PRODUCTION = [ROOT / 'catkin_ws/devel/lib/nav2d_karto/mapper',
              ROOT / 'catkin_ws/devel/lib/libMultiMapper.so',
              ROOT / 'catkin_ws/devel/lib/libOpenKarto.so']

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + '\n')

def read(path):
    return json.loads(Path(path).read_text())

def command(args):
    return subprocess.check_output(args, text=True, cwd=str(ROOT)).strip()

def aggregate(directory):
    files = sorted(p for p in Path(directory).rglob('*') if p.is_file())
    h = hashlib.sha256()
    for p in files:
        h.update(str(p.relative_to(directory)).encode() + b'\0' + sha(p).encode() + b'\n')
    return {'file_count': len(files), 'aggregate_sha256': h.hexdigest()}

def integrity(stage):
    data = {'hash_only_no_endpoint_parsing': True,
            'trees': {name: aggregate(ROOT / 'results/realizability_pilot' / name)
                      for name in PROTECTED},
            'production': {str(p.relative_to(ROOT)): sha(p) for p in PRODUCTION}}
    if stage == 'after':
        before = read(OUT / 'audit/integrity_before.json')
        data['all_exact'] = (data['trees'] == before['trees'] and
                             data['production'] == before['production'])
    write(OUT / ('audit/integrity_' + stage + '.json'), data)
    return data

def base_pose(row):
    return [row['x'] - 0.2 * math.cos(row['yaw']),
            row['y'] - 0.2 * math.sin(row['yaw']), row['yaw']]

def compose(a, b):
    c, s = math.cos(a[2]), math.sin(a[2])
    return [a[0] + c * b[0] - s * b[1], a[1] + s * b[0] + c * b[1], a[2] + b[2]]

def inverse(a):
    c, s = math.cos(a[2]), math.sin(a[2])
    return [-c * a[0] - s * a[1], s * a[0] - c * a[1], -a[2]]

def input_audit():
    records = [json.loads(line) for line in SOURCE.open() if line.strip()]
    assert len(records) == 33
    assert sha(SOURCE) == '4eddfa84d601f04bf4b86f52dca819c4ccd83c5476fdb48cf1e48f0c76255bde'
    errors = []
    for i, row in enumerate(records):
        assert len(row['ranges']) == 901
        assert all(math.isfinite(row[k]) for k in ('x', 'y', 'yaw', 'stamp'))
        assert all(math.isfinite(x) for x in row['ranges'])
        assert i == 0 or row['stamp'] > records[i - 1]['stamp']
        reconstructed = compose(base_pose(row), [0.2, 0., 0.])
        errors.append(max(abs(a - b) for a, b in zip(reconstructed, [row['x'], row['y'], row['yaw']])))
    result = {'status': 'FEASIBLE_FOR_TECHNICAL_REPLAY', 'source': str(SOURCE.relative_to(ROOT)),
              'source_sha256': sha(SOURCE), 'records': len(records),
              'maximum_pose_roundtrip_error': max(errors),
              'original_timing_recoverable': False,
              'recorded_odometry': 'laser odom pose derived from most recent base odom sample; not GT',
              'adapted_odometry': 'algebraic inverse of documented 0.2m laser mounting at each recorded sample',
              'constructed_metadata': ['laser frame name cd_b0_laser', 'global scan sequence index',
                                       'timestamp +10s origin shift', 'scan_time/time_increment=0, unknown'],
              'not_claimed': ['original acquisition latency', 'original per-beam time', 'hardware timing fidelity'],
              'map_frame': 'mapper-owned map', 'odom_frame': 'odom', 'base_frame': 'base_footprint',
              'base_to_laser': [0.2, 0., -0.2, 0., 0., 0.],
              'cut': {'H': [0, 20], 'C': [20, 33], 'index_semantics': 'zero-based half-open; fixed before runs'}}
    write(OUT / 'audit/input_adapter_checks.json', result)
    for label, segment in [('H', records[:20]), ('C', records[20:])]:
        p = OUT / ('technical/input_' + label + '.jsonl')
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(''.join(json.dumps(row, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n'
                             for row in segment))
    return result

def build_manifest():
    paths = [WS / 'devel/lib/slam_toolbox/sync_slam_toolbox_node'] + sorted((WS / 'devel/lib').glob('*.so'))
    data = {'upstream_version': '1.5.7', 'upstream_tag_commit': '1b18cacfa6971bd9c3f8fdd965d7baeecffbedf0',
            'noetic_devel_head_audited': '8a754bb37485c598064dd1e5d00057ece4e3891d',
            'source_acquisition': 'ROS release source tar, compared with official tag raw source',
            'source_archive_sha256': sha(WS / 'packages/ros-noetic-slam-toolbox_1.5.7.orig.tar.gz'),
            'source_tree': aggregate(WS / 'src/slam_toolbox'),
            'compiler': command(['/usr/bin/c++', '--version']),
            'cmake_cache_sha256': sha(WS / 'build/CMakeCache.txt'),
            'packages': {p.name: sha(p) for p in sorted((WS / 'packages').glob('*.deb'))},
            'executables_libraries': {str(p): sha(p) for p in paths},
            'build_command': 'source technical/environment.sh; catkin_make -DPYTHON_EXECUTABLE=/usr/bin/python3 -DCMAKE_BUILD_TYPE=Release -Dgflags_DIR=/home/wcqw/ac-slam_cd_b0_ws/apt_root/usr/lib/x86_64-linux-gnu/cmake/gflags -j2 -l2',
            'system_install': False, 'production_overlay_used': False}
    assert paths[0].is_file()
    write(OUT / 'audit/isolated_build_manifest.json', data)
    return data

def freeze():
    assert command(['git', 'rev-parse', 'HEAD']) == BASELINE
    if (OUT / 'protocol/frozen_technical_experiment.json').exists():
        raise RuntimeError('refusing to replace frozen protocol')
    adapter = input_audit()
    build = build_manifest()
    config = WS / 'src/slam_toolbox/config/mapper_params_online_sync.yaml'
    (OUT / 'technical/parameters.yaml').write_bytes(config.read_bytes())
    tracked = [OUT / 'technical/b0_tools.py', OUT / 'technical/b0_run.py',
               OUT / 'technical/test_b0.py', OUT / 'technical/environment.sh',
               OUT / 'technical/parameters.yaml', OUT / 'audit/observation.patch',
               OUT / 'audit/isolation_dependency.patch']
    payload = {
        'task_id': 'CD_B0_STATE_RESTORE_BACKEND_FEASIBILITY', 'task_type': 'TECHNICAL_ARCHITECTURE_POC_ONLY',
        'baseline_commit': BASELINE, 'input': adapter,
        'frozen_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'H_sha256': sha(OUT / 'technical/input_H.jsonl'), 'C_sha256': sha(OUT / 'technical/input_C.jsonl'),
        'build_manifest_sha256': sha(OUT / 'audit/isolated_build_manifest.json'),
        'software_config_sha256': {str(p.relative_to(OUT)): sha(p) for p in tracked},
        'run_order': ['continuous', 'checkpoint', 'restore_1', 'restore_2', 'restore_3'],
        'fresh_master_and_process_each_run': True,
        'restore_count': 3, 'restore_mode': 'START_AT_GIVEN_POSE',
        'restore_initial_pose_rule': 'T_corrected_last_H * inverse(T_odom_last_H) * T_base_first_C; no fitted alignment',
        'metadata_scan_rule': 'first C published once after normal+waitForMessage subscribers connect; used both as metadata and first continuation scan',
        'header_sequence_rule': 'global input index on wire; restore C starts at seq20',
        'publisher_rate_hz': 5., 'drain_timeout_s': 40., 'per_run_timeout_s': 180.,
        'barrier': 'published complete; callbacks==expected; processed==accepted; queue0; no in_flight; synchronized graph dump; no more scan publication during save',
        'comparison': {'node_mapping': 'exact scan range vector to frozen source input index, unique match required',
                       'coordinate_gauge': 'common odom origin and base/laser mounting; require same first historical node anchor; no fitted rotation/translation',
                       'numeric_tolerance': 0., 'criteria': ['mapped node sequence', 'corrected pose', 'sensor pose', 'ordered edge endpoints', 'edge measurement', 'edge covariance'],
                       'diagnostics': ['internal ids', 'odometric pose after session transform', 'native scan time', 'scan acceptance', 'optimizer invocations'],
                       'nonlocality': 'raw original-input index gap; NOT a provenance label or proof of accepted closure'},
        'stop_rules': {'runtime_or_barrier_failure': 'stop remaining matrix; save failure; no automatic retry',
                       'numeric_or_structure_mismatch': 'complete frozen three restores; report failed equivalence without tuning',
                       'maximum_replays': 5, 'no_scientific_collection': True},
        'historical_measurement_requirement': 'accepted nonlocal historical constraint needs source provenance; optimizer execution alone is insufficient',
        'output_root': str(OUT), 'build': build['executables_libraries'],
    }
    write(OUT / 'protocol/frozen_technical_experiment.json', payload)
    write(OUT / 'protocol/frozen_hash.json', {'sha256': sha(OUT / 'protocol/frozen_technical_experiment.json')})
    return payload

def graph_identity(path):
    graph = read(path)
    source = [json.loads(x) for x in SOURCE.open() if x.strip()]
    lookup = {tuple(row['ranges']): i for i, row in enumerate(source)}
    assert len(lookup) == len(source), 'ambiguous source scan identity'
    ids = {}
    nodes = []
    for node in graph['nodes']:
        index = lookup[tuple(node['ranges'])]
        assert node['id'] not in ids
        ids[node['id']] = index
        nodes.append({'input_index': index, 'corrected': node['corrected'], 'sensor_pose': node['sensor_pose']})
    assert len({n['input_index'] for n in nodes}) == len(nodes), 'duplicated scan identity'
    edges = [{'source': ids[e['source']], 'target': ids[e['target']],
              'measurement': e['measurement'], 'covariance': e['covariance']} for e in graph['edges']]
    return {'nodes': nodes, 'edges': edges}

def max_difference(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b)
    if isinstance(a, list) and isinstance(b, list):
        return max([max_difference(x, y) for x, y in zip(a, b)] + [0.])
    return 0.

def compare(a, b):
    x, y = graph_identity(a), graph_identity(b)
    sequence_equal = [n['input_index'] for n in x['nodes']] == [n['input_index'] for n in y['nodes']]
    edge_endpoints_equal = [(e['source'], e['target']) for e in x['edges']] == [(e['source'], e['target']) for e in y['edges']]
    anchor_equal = x['nodes'][0] == y['nodes'][0] if x['nodes'] and y['nodes'] else False
    result = {'node_mapping_equal': sequence_equal, 'ordered_edge_endpoints_equal': edge_endpoints_equal,
              'anchor_equal': anchor_equal, 'exact': x == y,
              'counts': [[len(x['nodes']), len(x['edges'])], [len(y['nodes']), len(y['edges'])]],
              'numeric_differences_comparable': sequence_equal and edge_endpoints_equal}
    if sequence_equal and edge_endpoints_equal:
        for field in ('corrected', 'sensor_pose'):
            result['max_' + field + '_difference'] = max([max_difference(i[field], j[field]) for i, j in zip(x['nodes'], y['nodes'])] + [0.])
        for field in ('measurement', 'covariance'):
            result['max_' + field + '_difference'] = max([max_difference(i[field], j[field]) for i, j in zip(x['edges'], y['edges'])] + [0.])
    return result

def analyze():
    runs = OUT / 'technical/runs'
    pair_results = {}
    for a, b in itertools.combinations(['restore_1', 'restore_2', 'restore_3'], 2):
        if (runs / a / 'graph.json').exists() and (runs / b / 'graph.json').exists():
            pair_results[a + '__' + b] = compare(runs / a / 'graph.json', runs / b / 'graph.json')
    continuous = {}
    for label in ('restore_1', 'restore_2', 'restore_3'):
        if (runs / label / 'graph.json').exists() and (runs / 'continuous/graph.json').exists():
            continuous[label] = compare(runs / 'continuous/graph.json', runs / label / 'graph.json')
    inventory = {}
    for directory in sorted(runs.glob('*')):
        if not directory.is_dir(): continue
        info = {'status': read(directory / 'status.json') if (directory / 'status.json').exists() else 'missing'}
        if (directory / 'graph.json').exists():
            graph = graph_identity(directory / 'graph.json')
            info['accepted_input_indices'] = [n['input_index'] for n in graph['nodes']]
            info['edge_index_gaps'] = [abs(e['target'] - e['source']) for e in graph['edges']]
            info['edge_endpoints'] = [[e['source'], e['target']] for e in graph['edges']]
            info['node_count'] = len(graph['nodes']); info['edge_count'] = len(graph['edges'])
        log = directory / 'mapper.log'
        if log.exists():
            text = log.read_text(errors='replace')
            info['optimizer_compute_log_count'] = text.count('CD_B0_OPTIMIZER_COMPUTE')
            info['accepted_loop_log_count'] = text.count('CD_B0_ACCEPTED_LOOP')
            info['first_frame_processing'] = [s for s in text.splitlines() if 'CD_B0_PROCESS' in s][:1]
        inventory[directory.name] = info
    runtime_success = (len(inventory) == 5 and all(isinstance(i['status'], dict) and i['status'].get('completed') for i in inventory.values()))
    rr = len(pair_results) == 3 and all(p['exact'] for p in pair_results.values())
    rc = len(continuous) == 3 and all(p['exact'] for p in continuous.values())
    gate = ('RESTORE_FEASIBILITY_PASS' if runtime_success and rr and rc else
            'RESTORE_REPEATABLE_NOT_CONTINUOUS_EQUIVALENT' if runtime_success and rr else
            'STATE_RESTORE_UNVERIFIED' if runtime_success else 'TECHNICALLY_INCOMPLETE')
    result = {'main_gate': gate, 'restore_to_restore_exact': rr, 'restore_to_continuous_exact': rc,
              'all_runtime_barriers_complete': runtime_success,
              'restore_to_restore': pair_results, 'restore_to_continuous': continuous, 'runs': inventory,
              'historical_measurement_gate': 'HISTORICAL_MEASUREMENT_NOT_YET_VALIDATED',
              'scope': 'single technical input; no CD scientific endpoint',
              'plan_a_ready': False}
    write(OUT / 'analysis/technical_verdict.json', result)
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['integrity-before', 'integrity-after', 'input-audit', 'build-manifest', 'freeze', 'analyze'])
    a = parser.parse_args().action
    result = integrity(a.split('-')[1]) if a.startswith('integrity-') else {
        'input-audit': input_audit, 'build-manifest': build_manifest,
        'freeze': freeze, 'analyze': analyze}[a]()
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
