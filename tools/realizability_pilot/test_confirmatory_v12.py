#!/usr/bin/python3

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import confirmatory_v12_analysis as analysis
import confirmatory_v12_protocol as protocol


class ConfirmatoryV12Test(unittest.TestCase):
    def test_design_has_eight_blocks_and_twenty_four_assignments(self):
        self.assertEqual(sum(len(value) for value in protocol.PRIMARY_SEEDS.values()), 8)
        orders = [order for target in protocol.ARM_ORDERS.values() for order in target]
        self.assertEqual(len(orders), 8)
        self.assertTrue(all(sorted(order) == sorted(protocol.ARMS)
                            for order in orders))

    def test_target_references_are_exactly_five_and_preexisting(self):
        references = protocol.target_references()
        self.assertEqual(set(references), {'target_A', 'target_B'})
        self.assertTrue(all(len(row['q']) == 5 for row in references.values()))
        self.assertEqual(references['target_B']['source_state_ids'], [29, 30, 31, 32, 33])

    def test_monotonic_assignment_obeys_order_and_tolerance(self):
        references = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
                      [2.0, 0.0, 0.0], [3.0, 0.0, 0.0],
                      [4.0, 0.0, 0.0]]
        states = [{'state_id': index + 10, 'stamp': float(index),
                   'pose': [float(index), 0.0, 0.0]}
                  for index in range(5)]
        result = protocol.monotonic_target_assignment(references, states, 10)
        self.assertEqual(result['historical_scan_ids'], [10, 11, 12, 13, 14])
        bad = list(states); bad[2] = dict(bad[2], pose=[20.0, 0.0, 0.0])
        with self.assertRaisesRegex(ValueError, 'TARGET_REFERENCE_MATCH_INVALID'):
            protocol.monotonic_target_assignment(references, bad, 10)

    def test_a3_semantics_do_not_gate_on_keyscan_count(self):
        payload = protocol.preregistration_payload(a3_dwell_s=2.4)
        a3 = payload['arms']['A3_MIN_TRIGGER']
        self.assertTrue(a3['keyscan_count_is_mediator_not_validity_gate'])
        self.assertAlmostEqual(a3['angle_rad'], 0.5439732814124923)

    def test_fixed_root_covariance_and_joint_target_dimension(self):
        nodes = {0: {'x': 0.0, 'y': 0.0, 'theta': 0.0},
                 1: {'x': 1.0, 'y': 0.0, 'theta': 0.0}}
        covariance = np.eye(3).tolist()
        edges = [{'start': 0, 'end': 1, 'source_pose': [0.0, 0.0, 0.0],
                  'target_pose': [1.0, 0.0, 0.0],
                  'covariance_upper_triangle': '1 0 0 1 0 1',
                  'covariance_3x3': covariance}]
        full, diagnostic = analysis.fixed_root_covariance(nodes, edges)
        metrics = analysis.joint_metrics(full, [0, 1], [1])
        self.assertEqual(diagnostic['root_id'], 0)
        self.assertEqual(metrics['dimension'], 3)
        self.assertTrue(np.isfinite(metrics['J']))

    def test_analysis_fails_closed_without_collection_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, 'COLLECTION_COMPLETE'):
                analysis.analyze(Path(directory))

    def test_four_single_target_blocks_are_not_confirmatory_evaluable(self):
        rows = []
        for index in range(4):
            for arm, value in (('A1_DWELL', 1.0),
                               ('A3_MIN_TRIGGER', 2.0),
                               ('A2_SWEEP90', 3.0)):
                rows.append({'block_id': 'A{}'.format(index),
                             'target': 'target_A', 'arm': arm, 'J_T': value})
        _paired, summary = analysis.contrast_summary(
            rows, 'A2_SWEEP90', 'A3_MIN_TRIGGER', 'D_view')
        self.assertEqual(summary['positive_blocks'], 4)
        self.assertFalse(summary['confirmatory_evaluable'])
        self.assertFalse(summary['supported_by_preregistered_rule'])
        self.assertEqual(summary['confirmatory_verdict'],
                         'NOT_EVALUABLE_TECHNICAL_INCOMPLETENESS')


if __name__ == '__main__':
    unittest.main()
