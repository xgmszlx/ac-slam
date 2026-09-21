#!/usr/bin/python3
"""Stage-0 and protocol-boundary tests for v13-C."""

import json
import tempfile
import unittest
from pathlib import Path

from confirmatory_v13c_analysis import analysis_preflight
from confirmatory_v13c_collection import budget_gate
from confirmatory_v13c_protocol import (ARMS, ARM_ORDERS,
                                        preregistration_payload)
from v13c_local_estimand_amendment import (build_amendment,
                                           select_local_target)
from v13_unified_replay import evaluate_prefix_reference


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload))


class LocalEstimandAmendmentTest(unittest.TestCase):
    def synthetic_attempt(self, root, node_x, route_start=10,
                          waypoint=(0.0, 0.0, 0.0)):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        nodes = [{'id': 10 + index, 'x': float(x), 'y': 0.0, 'theta': 0.0}
                 for index, x in enumerate(node_x)]
        write_json(root / 'pose_graph_before.json', {
            'nodes': nodes,
            'full_pose_nodes': [dict(row, unique_id=1000 + row['id'])
                                for row in nodes],
        })
        write_json(root / 'resolved_history_route.json', {
            'route_start_node_count': route_start,
            'resolved_history_waypoints': [list(waypoint), [10.0, 0.0, 0.0]],
        })
        write_json(root / 'episode_result.json', {
            'canonical_history_complete': True})
        return root

    def test_fixed_radius_contiguous_run_and_five_quantiles(self):
        with tempfile.TemporaryDirectory() as temporary:
            attempt = self.synthetic_attempt(
                temporary, [-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0])
            result = select_local_target(
                attempt, 'target_A', 'map3_grid_anchor_01')
            self.assertEqual(result['local_candidate_state_ids'],
                             [11, 12, 13, 14, 15])
            self.assertEqual(result['contiguous_local_run_state_ids'],
                             [11, 12, 13, 14, 15])
            self.assertTrue(result['selection_valid'])
            self.assertEqual(len(result['selected_five_state_ids']), 5)

    def test_quantile_ties_use_lower_state_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            attempt = self.synthetic_attempt(
                temporary, [-1.0, -0.6, -0.2, 0.2, 0.6, 1.0])
            result = select_local_target(
                attempt, 'target_A', 'map3_grid_anchor_01')
            self.assertTrue(result['selection_valid'])
            self.assertEqual(result['selected_five_state_ids'][0], 10)

    def test_fewer_than_five_local_states_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            attempt = self.synthetic_attempt(
                temporary, [-4.0, -1.0, 0.0, 1.0, 4.0])
            result = select_local_target(
                attempt, 'target_A', 'map3_grid_anchor_01')
            self.assertFalse(result['selection_valid'])
            self.assertIn('fewer than five', result['exclusion_reason'])

    def test_frozen_sixteen_history_amendment_passes_without_actions(self):
        amendment = build_amendment()
        self.assertEqual(len(amendment['records']), 16)
        self.assertEqual(amendment['stage0_gate'],
                         'LOCAL_ESTIMAND_AMENDMENT_PASS')
        self.assertEqual(amendment['targets']['target_A'][
            'frozen_first_four_seeds'], [81001, 81002, 81003, 81005])
        self.assertEqual(amendment['targets']['target_B'][
            'frozen_first_four_seeds'], [82001, 82002, 82003, 82005])
        self.assertFalse(amendment['action_launched'])
        self.assertEqual(amendment['scientific_endpoints_read'], [])


class V13CProtocolBoundaryTest(unittest.TestCase):
    @staticmethod
    def graph(offset=0.0):
        return {
            'nodes': [
                {'state_id': 0, 'unique_id': 0, 'x': 0.0, 'y': 0.0,
                 'theta': 0.0},
                {'state_id': 1, 'unique_id': 1, 'x': 1.0 + offset,
                 'y': 0.0, 'theta': 0.0}],
            'edges': [{
                'index': 0, 'source_state_id': 0, 'target_state_id': 1,
                'source_unique_id': 0, 'target_unique_id': 1,
                'measurement': {'dx': 1.0, 'dy': 0.0, 'dtheta': 0.0},
                'covariance_3x3': [[1.0, 0.0, 0.0],
                                   [0.0, 1.0, 0.0],
                                   [0.0, 0.0, 1.0]],
            }],
        }

    def test_pre_suffix_gate_requires_structural_and_numerical_exactness(self):
        exact = evaluate_prefix_reference(self.graph(), self.graph(), [1])
        changed = evaluate_prefix_reference(
            self.graph(), self.graph(offset=0.001), [1])
        self.assertTrue(exact['passed'])
        self.assertFalse(changed['passed'])
        self.assertTrue(changed['structural']['exact'])
        self.assertFalse(changed['numerical']['exact'])

    def test_budget_gate_reads_only_physical_fields(self):
        branches = {}
        for index, arm in enumerate(ARMS):
            branches[arm] = {
                'distance_m': 10.0 + 0.01 * index,
                'duration_s': 60.0 + 0.1 * index,
                'raw_scan_count': 600 + index,
                'J_T': 999.0 * index,
                'accepted_keyscan_count': 1000 * index,
            }
        result = budget_gate({'branches': branches})
        self.assertTrue(result['passed'])
        self.assertEqual(result['scientific_variables_used'], [])

    def test_analysis_fails_closed_before_collection_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(RuntimeError, 'COLLECTION_LOCKED'):
                analysis_preflight(temporary)

    def test_preregistration_has_eight_blocks_and_twenty_four_branches(self):
        payload = preregistration_payload()
        self.assertEqual(payload['planned_blocks'], 8)
        self.assertEqual(payload['planned_branches'], 24)
        self.assertEqual(len(payload['blocks']), 8)
        self.assertEqual(payload['arm_orders'], ARM_ORDERS)
        self.assertTrue(payload['no_peeking']['forbidden_until_collection_lock'])
        self.assertIn(
            'tools/realizability_pilot/confirmatory_v13c_analysis.py',
            payload['code_hashes'])


if __name__ == '__main__':
    unittest.main()
