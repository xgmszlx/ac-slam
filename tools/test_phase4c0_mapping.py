#!/usr/bin/env python3
"""Synthetic construct validation for Phase 4C boundary metrics."""

import tempfile
import unittest
from pathlib import Path
import sys

import numpy as np
from scipy.ndimage import binary_dilation

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_mapping import load_map
from evaluate_mapping_v2 import evaluate_maps_v2
from test_phase4b_mapping import base_state, write_map


class Phase4CMappingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="phase4c0_map_test_")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def evaluate(self, gt, est, gt_resolution=0.1, est_resolution=0.1,
                 gt_origin=(0.0, 0.0, 0.0), est_origin=(0.0, 0.0, 0.0), targets=None):
        gt_grid = load_map(write_map(self.root, "gt", gt, gt_resolution, gt_origin))
        est_grid = load_map(write_map(self.root, "est", est, est_resolution, est_origin))
        return evaluate_maps_v2(
            gt_grid, est_grid, boundary_tolerance_m=0.20,
            local_targets=targets or [], local_radius_m=5.0,
        )

    def test_identity(self):
        state = base_state()
        result = self.evaluate(state, state.copy())
        self.assertAlmostEqual(result["occupied_boundary_f1"]["f1"], 1.0, places=12)
        self.assertAlmostEqual(result["symmetric_boundary_distance"]["mean_m"], 0.0, places=12)

    def test_translation_1_2_4_cells_is_monotonic(self):
        gt = base_state()
        results = []
        for cells in (1, 2, 4):
            shifted = np.zeros_like(gt)
            shifted[:, cells:] = gt[:, :-cells]
            results.append(self.evaluate(gt, shifted))
        distances = [item["symmetric_boundary_distance"]["mean_m"] for item in results]
        f1 = [item["occupied_boundary_f1"]["f1"] for item in results]
        self.assertLess(distances[0], distances[1])
        self.assertLess(distances[1], distances[2])
        self.assertGreaterEqual(f1[0], f1[1])
        self.assertGreaterEqual(f1[1], f1[2])

    def test_double_wall_is_worse(self):
        gt = base_state()
        double = gt.copy()
        # Put the duplicate beyond the frozen 0.20 m matching tolerance.  The
        # corruption, not the evaluator tolerance, is the controlled variable.
        double[:, 24] = np.maximum(double[:, 24], gt[:, 20])
        result = self.evaluate(gt, double)
        self.assertLess(result["occupied_boundary_f1"]["f1"], 1.0)
        self.assertGreater(result["symmetric_boundary_distance"]["mean_m"], 0.0)

    def test_boundary_thickening_is_worse(self):
        gt = base_state()
        thick = binary_dilation(gt == 1, iterations=3).astype(np.int8)
        result = self.evaluate(gt, thick)
        self.assertLess(result["occupied_boundary_f1"]["f1"], 1.0)
        self.assertGreater(result["symmetric_boundary_distance"]["mean_m"], 0.0)

    def test_unknown_masking_penalizes_recall_and_coverage(self):
        gt = base_state()
        est = gt.copy()
        est[10:54, 18:46] = -1
        target = [{"target_id": "centre", "xy": [3.2, 3.2]}]
        result = self.evaluate(gt, est, targets=target)
        local = result["local_revisit"][0]
        self.assertLess(local["observed_coverage"], 1.0)
        self.assertLess(local["boundary_f1"]["recall"], 1.0)

    def test_local_roi_without_gt_boundary_is_not_scored_as_perfect(self):
        state = np.zeros((128, 128), dtype=np.int8)
        target = [{"target_id": "empty", "xy": [6.4, 6.4]}]
        result = self.evaluate(state, state.copy(), targets=target)
        local = result["local_revisit"][0]
        self.assertIsNone(local["boundary_f1"]["f1"])
        self.assertEqual(
            local["boundary_f1"]["status"], "NOT_APPLICABLE_NO_GT_BOUNDARY"
        )
        self.assertIsNone(local["symmetric_boundary_distance"]["mean_m"])

    def test_resolution_conversion(self):
        gt = np.zeros((40, 40), dtype=np.int8)
        est = np.zeros((80, 80), dtype=np.int8)
        gt[10:30, 10:20] = 1
        est[20:60, 20:40] = 1
        result = self.evaluate(gt, est, gt_resolution=0.1, est_resolution=0.05)
        self.assertAlmostEqual(result["occupied_boundary_f1"]["f1"], 1.0, places=12)
        self.assertAlmostEqual(result["symmetric_boundary_distance"]["mean_m"], 0.0, places=12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
