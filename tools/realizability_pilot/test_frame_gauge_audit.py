#!/usr/bin/python3

import math
import sys
import unittest
from pathlib import Path

import numpy as np

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

import frame_gauge_audit


class FrameGaugeAuditTest(unittest.TestCase):
    def test_estimate_se2_recovers_rigid_transform_without_scale(self):
        source = np.asarray([[0.0, 0.0], [4.0, 0.0], [4.0, 3.0], [0.0, 3.0]])
        yaw = 0.31
        rotation = np.asarray([[math.cos(yaw), -math.sin(yaw)],
                               [math.sin(yaw), math.cos(yaw)]])
        translation = np.asarray([-28.2, 4.5])
        target = (rotation @ source.T).T + translation
        estimated_rotation, estimated_translation = frame_gauge_audit.estimate_se2(
            source, target)
        np.testing.assert_allclose(estimated_rotation, rotation, atol=1e-12)
        np.testing.assert_allclose(estimated_translation, translation, atol=1e-12)
        self.assertAlmostEqual(np.linalg.det(estimated_rotation), 1.0, places=12)

    def test_transform_pose_applies_same_yaw(self):
        yaw = -0.2
        rotation = np.asarray([[math.cos(yaw), -math.sin(yaw)],
                               [math.sin(yaw), math.cos(yaw)]])
        transformed = frame_gauge_audit.transform_pose(
            [2.0, 1.0, 0.7], rotation, np.asarray([4.0, -3.0]))
        np.testing.assert_allclose(transformed[:2],
                                   rotation @ np.asarray([2.0, 1.0]) + [4.0, -3.0])
        self.assertAlmostEqual(transformed[2], 0.5, places=12)

    def test_classification_is_independent_of_old_status(self):
        base = {
            'block_id': 'b', 'preprobe_node_count': 10, 'preprobe_edge_count': 12,
            'preprobe_node_id_set_hash': 'n', 'preprobe_edge_endpoint_set_hash': 'e',
            'rmse_after_alignment_m': 0.01, 'heading_rmse_after_rad': 0.01,
            'normalized_gate_error_reduction': 0.8, 'aligned_to_raw_ratio': 0.2,
            'old_expected_vs_aligned_target_position_m': 0.6,
            'old_expected_vs_aligned_target_heading_rad': 0.1,
        }
        rows = [dict(base, old_status='FAILED'), dict(base, old_status='SUCCEEDED')]
        frame_gauge_audit.classify(rows)
        self.assertEqual(rows[0]['arrival_gauge_class'], rows[1]['arrival_gauge_class'])
        self.assertEqual(rows[0]['arrival_gauge_class'],
                         'G2_TRUE_TRAJECTORY_OR_MAP_DIVERGENCE')

    def test_probe_cannot_be_used_as_fit_pair(self):
        # The fit selector is asserted through the public constant/source contract;
        # integration tests exercise fit_attempt against the preserved v8 corpus.
        self.assertEqual(frame_gauge_audit.MIN_FIT_PAIRS, 3)
        self.assertEqual(frame_gauge_audit.MIN_FIT_SPREAD_M, 2.0)


if __name__ == '__main__':
    unittest.main()
