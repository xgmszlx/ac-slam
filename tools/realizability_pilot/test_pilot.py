#!/usr/bin/python3
"""ROS-free unit tests for pilot protocol and aggregation semantics."""

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

from aggregate_episode_table import diagnostic_stages  # noqa: E402
from protocol import (episode_specs, goal_errors, resolve_local_waypoints,
                      resolve_marker_edges, target_freeze_checks)  # noqa: E402


class PilotProtocolTest(unittest.TestCase):
    def test_preflight_has_diagnostics_sentinel_pair(self):
        specs = episode_specs('preflight', 1)
        self.assertEqual(len(specs), 4)
        baseline = [spec for spec in specs if spec['maneuver_type'] == 'pass'
                    and spec['delta_yaw_deg'] == 0]
        self.assertEqual({spec['diagnostics_enabled'] for spec in baseline}, {False, True})
        self.assertTrue(all(spec['protocol_version'] == 'p1_preflight_v7'
                            for spec in specs))

    def test_screening_factorial_size(self):
        specs = episode_specs('screening', 2)
        self.assertEqual(len(specs), 4 * 2 * 3 * 2)
        self.assertEqual(len({spec['episode_id'] for spec in specs}), len(specs))

    def test_history_route_ends_away_from_target(self):
        spec = episode_specs('preflight', 1)[0]
        target = spec['history_offsets'][spec['target_history_waypoint_index']]
        staging = spec['history_offsets'][-1]
        self.assertGreaterEqual(math.hypot(staging[0] - target[0], staging[1] - target[1]), 6.0)

    def test_episode_local_route_transform(self):
        route = resolve_local_waypoints([1.0, 2.0, math.pi / 2.0], [[3.0, 0.0, 0.0]])
        self.assertAlmostEqual(route[0][0], 1.0)
        self.assertAlmostEqual(route[0][1], 5.0)
        self.assertAlmostEqual(route[0][2], math.pi / 2.0)

    def test_route_axis_is_canonical_across_initial_headings(self):
        spec = episode_specs('preflight', 1)[0]
        origin_a = [0.2, 0.0, spec['route_axis_heading_rad']]
        origin_b = [0.2, 0.0, spec['route_axis_heading_rad']]
        self.assertEqual(resolve_local_waypoints(origin_a, spec['history_offsets']),
                         resolve_local_waypoints(origin_b, spec['history_offsets']))
        self.assertEqual(spec['route_axis_heading_rad'], 0.0)

    def test_independent_goal_error(self):
        position, heading = goal_errors([1.3, 2.4, -math.pi + 0.05],
                                        [1.0, 2.0, math.pi - 0.05])
        self.assertAlmostEqual(position, 0.5)
        self.assertAlmostEqual(heading, 0.1)

    def test_target_freeze_gate_accepts_route_scan_near_reference(self):
        spec = episode_specs('preflight', 1)[0]
        result = target_freeze_checks(
            node_count=33, anchor_id=16, anchor_distance_m=0.39,
            segment_count=5, route_start_node_count=11, spec=spec)
        self.assertTrue(result['passed'])
        self.assertTrue(all(result['checks'].values()))

    def test_target_freeze_gate_rejects_initial_mapping_scan(self):
        spec = episode_specs('preflight', 1)[0]
        result = target_freeze_checks(
            node_count=33, anchor_id=1, anchor_distance_m=5.20,
            segment_count=8, route_start_node_count=11, spec=spec)
        self.assertFalse(result['passed'])
        self.assertFalse(result['checks']['anchor_within_reference_radius'])
        self.assertFalse(result['checks']['anchor_acquired_after_route_start'])

    def test_marker_edges_resolve_to_full_path_ids(self):
        nodes = [
            {'id': 14, 'x': 3.0, 'y': 4.0},
            {'id': 40, 'x': 8.0, 'y': 9.0},
        ]
        result = resolve_marker_edges(
            [[[3.01, 4.0], [8.0, 8.98]]], nodes)
        self.assertEqual(result[0]['source'], 14)
        self.assertEqual(result[0]['target'], 40)
        self.assertEqual(result[0]['scan_index_gap'], 26)
        self.assertAlmostEqual(result[0]['endpoint_match_error_max_m'], 0.02)

    def test_diagnostics_are_target_and_probe_bounded(self):
        records = [
            {'scan_id': 10, 'scan_ids': [2, 3], 'coarse_pass': True, 'fine_pass': True},
            {'scan_id': 21, 'scan_ids': [2, 3], 'coarse_pass': True, 'fine_pass': True},
            {'scan_id': 22, 'scan_ids': [7, 8], 'coarse_pass': False, 'fine_pass': False},
            {'scan_id': 40, 'scan_ids': [7, 8], 'coarse_pass': True, 'fine_pass': True},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'diag.jsonl'
            path.write_text('\n'.join(json.dumps(row) for row in records) + '\n')
            stages = diagnostic_stages(path, {7, 8}, 20, 30)
        self.assertEqual(stages, {'opportunity': True, 'coarse': False, 'fine': False})


if __name__ == '__main__':
    unittest.main()
