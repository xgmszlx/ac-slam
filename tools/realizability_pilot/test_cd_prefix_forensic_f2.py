"""Static, outcome-blind regression tests for the CD-F2 forensic toolchain."""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cd_prefix_forensic_f2 import F2, cluster_graphs, first_nonzero, normalized_launch
from cd_prefix_forensic_f2_run import (normalize_library_resolution, schedule,
                                       validate_schedule)


def toy_graph(dx):
    return {'nodes': [{'index': 0, 'state_id': 0, 'unique_id': 0,
                       'x': 0.0, 'y': 0.0, 'theta': 0.0}],
            'edges': [{'index': 0, 'source_state_id': 0, 'target_state_id': 0,
                       'source_unique_id': 0, 'target_unique_id': 0,
                       'measurement': {'dx': dx, 'dy': 0.0, 'dtheta': 0.0},
                       'covariance_3x3': [[1.0, 0.0, 0.0],
                                          [0.0, 1.0, 0.0],
                                          [0.0, 0.0, 1.0]]}]}


def test_cluster_uses_serialized_numerics_not_file_hash():
    graphs = {'A': (Path('a'), toy_graph(0.123456)),
              'B': (Path('b'), toy_graph(0.123456)),
              'C': (Path('c'), toy_graph(0.123457))}
    assert cluster_graphs(graphs) == [['A', 'B'], ['C']]


def test_first_divergence_preserves_order():
    rows = [{'index': 1, 'delta': 0}, {'index': 2, 'delta': 0.01}]
    assert first_nonzero(rows, ('delta',)) == rows[1]


def test_frozen_schedule_is_balanced_and_has_no_suffix():
    rows = schedule()
    assert validate_schedule(rows)
    assert len(rows) == 24
    assert all('suffix' not in key for row in rows for key in row)
    assert all(row['prefix_path'].endswith('canonical_prefix.jsonl') for row in rows)


def test_launch_normalization_ignores_only_output_destinations(tmp_path):
    launch = tmp_path / 'mapper.launch'
    launch.write_text('<launch><node name="MultiMapper" pkg="nav2d_karto" '
                      'type="mapper" output="log">'
                      '<param name="MinimumTravelDistance" value="1.0"/>'
                      '<param name="pose_graph_dump_path" value="/tmp/graph.json"/>'
                      '</node></launch>')
    normalized = normalized_launch(launch)
    assert normalized['semantic_params'] == {'MinimumTravelDistance': '1.0'}
    assert normalized['output_only_params']['pose_graph_dump_path'] == '/tmp/graph.json'


def test_library_fingerprint_ignores_aslr_addresses():
    left = 'libtbb.so.2 => /lib/libtbb.so.2 (0x001)\n'
    right = 'libtbb.so.2 => /lib/libtbb.so.2 (0x999)\n'
    assert normalize_library_resolution(left) == normalize_library_resolution(right)


def test_saved_prefix_only_protocol_never_published_suffix():
    root = F2 / 'technical/runs'
    records = [json.loads((root / ('run_%02d' % index) /
                           'forensic_result.json').read_text())
               for index in range(1, 25)]
    assert len(records) == 24
    assert all(row['suffix_published'] is False for row in records)
    assert all(row['actual_published_count'] == row['processed_callback_count']
               for row in records)
    assert all(row['structure_exact_vs_qualification'] for row in records)
    by_block = {block: [row for row in records if row['block'] == block]
                for block in ('target_A_H1', 'target_A_H2', 'target_B_H1')}
    assert all(len(rows) == 8 for rows in by_block.values())
    assert sum(row['numerical_exact_vs_qualification_6dp']
               for row in by_block['target_A_H1']) == 1
    assert all(row['numerical_exact_vs_qualification_6dp']
               for row in by_block['target_A_H2'] + by_block['target_B_H1'])
