#!/usr/bin/python3

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

import common_prefix_signature  # noqa: E402
import common_prefix_analysis  # noqa: E402
import normalize_replay_timestamps  # noqa: E402
import stitch_probe_stream  # noqa: E402


class CommonPrefixTest(unittest.TestCase):
    def test_signature_excludes_run_id_and_is_order_stable_for_nodes(self):
        node0 = {'state_id': 0, 'unique_id': 10, 'x': 0, 'y': 0, 'theta': 0}
        node1 = {'state_id': 1, 'unique_id': 11, 'x': 1, 'y': 0, 'theta': 0}
        edge = {'index': 0, 'source_state_id': 0, 'target_state_id': 1,
                'source_unique_id': 10, 'target_unique_id': 11,
                'measurement': {'dx': 1, 'dy': 0, 'dtheta': 0},
                'covariance_3x3': [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}
        left = {'run_id': 'a', 'nodes': [node1, node0], 'edges': [edge]}
        right = {'run_id': 'b', 'nodes': [node0, node1], 'edges': [edge]}
        self.assertEqual(common_prefix_signature.build_signature(left, [1]),
                         common_prefix_signature.build_signature(right, [1]))

    def test_stitch_preserves_prefix_bytes_and_is_strictly_increasing(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            prefix = directory / 'prefix.jsonl'
            probe = directory / 'probe.jsonl'
            out = directory / 'combined.jsonl'
            base = {'frame_id': 'laser', 'robot_id': 1, 'laser_type': 0,
                    'angle_min': -1, 'angle_max': 1, 'angle_increment': 1,
                    'range_min': 0, 'range_max': 10, 'ranges': [1, 2]}
            with open(prefix, 'w') as stream:
                for stamp, x in ((1.0, 0.0), (1.1, 1.0)):
                    stream.write(json.dumps(dict(base, stamp=stamp, x=x, y=0, yaw=0),
                                            separators=(',', ':')) + '\n')
            with open(probe, 'w') as stream:
                for stamp, x in ((10.0, 5.0), (10.1, 6.0)):
                    stream.write(json.dumps(dict(base, stamp=stamp, x=x, y=2, yaw=0.2),
                                            separators=(',', ':')) + '\n')
            report = stitch_probe_stream.stitch(prefix, probe, out)
            self.assertTrue(report['prefix_byte_identical'])
            records = stitch_probe_stream.load_records(out)
            self.assertTrue(all(b['stamp'] > a['stamp']
                                for a, b in zip(records, records[1:])))
            self.assertAlmostEqual(records[2]['x'], 1.0)
            self.assertAlmostEqual(records[2]['y'], 0.0)
            self.assertAlmostEqual(records[2]['yaw'], 0.0)

    def test_alignment_uses_one_rigid_transform(self):
        aligned = stitch_probe_stream.align_pose(
            [2, 0, math.pi / 2], [1, 0, 0], [5, 5, math.pi / 2])
        self.assertAlmostEqual(aligned[0], 5.0)
        self.assertAlmostEqual(aligned[1], 6.0)
        self.assertAlmostEqual(aligned[2], math.pi)

    def test_zero_stamp_prefix_is_normalized_in_original_order(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / 'source.jsonl'
            output = directory / 'output.jsonl'
            rows = [{'stamp': 0.0, 'x': value} for value in (3, 1, 2)]
            source.write_text(''.join(json.dumps(row) + '\n' for row in rows))
            report = normalize_replay_timestamps.normalize(
                source, output, period_s=0.1, start_s=2.0)
            normalized = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual([row['x'] for row in normalized], [3, 1, 2])
            self.assertEqual([row['stamp'] for row in normalized], [2.0, 2.1, 2.2])
            self.assertEqual(report['source_nonincreasing_adjacent_count'], 2)
            self.assertEqual(report['fields_changed'], ['stamp'])

    def test_branch_attribution_and_disconnected_history_ablation(self):
        covariance = [[0.1, 0, 0], [0, 0.1, 0], [0, 0, 0.01]]
        nodes = {
            index: {'id': index, 'unique_id': index, 'x': float(index),
                    'y': 0.0, 'theta': 0.0}
            for index in range(3)
        }
        def edge(index, start, end):
            return {'index': index, 'start': start, 'end': end,
                    'source_pose': [float(start), 0.0, 0.0],
                    'target_pose': [float(end), 0.0, 0.0],
                    'covariance_upper_triangle': '0.1 0 0 0.1 0 0.01',
                    'covariance_3x3': covariance,
                    'measurement': {'dx': end - start, 'dy': 0, 'dtheta': 0}}
        before = [edge(0, 0, 1)]
        final = before + [edge(1, 1, 2), edge(2, 0, 2)]
        new = common_prefix_analysis.classify_new_edges(
            before, final, target_ids={1}, history_ids={0, 1})
        self.assertEqual([row['attribution'] for row in new], [
            common_prefix_analysis.TARGET_LABEL,
            common_prefix_analysis.NONTARGET_LABEL])
        _node_ids, builds = common_prefix_analysis.information_variants(
            nodes, final, new)
        self.assertEqual(builds['all_constraints']['nullity'], 3)
        self.assertEqual(builds['target_removed']['nullity'], 3)
        self.assertEqual(builds['history_removed']['nullity'], 6)
        utilities = common_prefix_analysis.paper_graph_utilities(nodes, final, new)
        self.assertFalse(utilities['all_disconnected'])
        self.assertFalse(utilities['target_removed_disconnects_graph'])
        self.assertTrue(utilities['history_removed_disconnects_graph'])


if __name__ == '__main__':
    unittest.main()
