#!/usr/bin/python3
"""Synthetic validation for the frozen Phase 4B map evaluator."""

import tempfile
import unittest
from pathlib import Path
import sys

import numpy as np
import yaml
from PIL import Image
from scipy.ndimage import binary_dilation

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_mapping import evaluate_maps, load_map


def write_map(root, name, state, resolution=0.1, origin=(0.0, 0.0, 0.0)):
    root = Path(root)
    image_path = root / (name + '.png')
    yaml_path = root / (name + '.yaml')
    image = np.full(state.shape, 205, dtype=np.uint8)
    image[state == 0] = 254
    image[state == 1] = 0
    Image.fromarray(image, mode='L').save(str(image_path))
    metadata = {
        'image': image_path.name,
        'resolution': float(resolution),
        'origin': list(origin),
        'occupied_thresh': 0.65,
        'free_thresh': 0.196,
        'negate': 0,
    }
    yaml_path.write_text(yaml.safe_dump(metadata, sort_keys=True), encoding='utf-8')
    return yaml_path


def base_state(size=64):
    state = np.zeros((size, size), dtype=np.int8)
    state[12:52, 20] = 1
    state[12:52, 43] = 1
    state[12, 20:44] = 1
    state[51, 20:44] = 1
    return state


class MappingEvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='phase4b_map_test_')
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def evaluate(self, gt_state, est_state, gt_resolution=0.1, est_resolution=0.1,
                 gt_origin=(0.0, 0.0, 0.0), est_origin=(0.0, 0.0, 0.0)):
        gt = load_map(write_map(
            self.root, 'gt', gt_state, gt_resolution, gt_origin
        ))
        est = load_map(write_map(
            self.root, 'est', est_state, est_resolution, est_origin
        ))
        return evaluate_maps(gt, est, boundary_tolerance_m=0.20)

    def test_identity_is_one(self):
        state = base_state()
        result = self.evaluate(state, state.copy())
        self.assertAlmostEqual(result['occupied_iou']['value'], 1.0, places=12)
        self.assertAlmostEqual(result['occupied_boundary_f1']['f1'], 1.0, places=12)

    def test_translation_lowers_scores(self):
        gt = base_state()
        shifted = np.zeros_like(gt)
        shifted[:, 4:] = gt[:, :-4]
        result = self.evaluate(gt, shifted)
        self.assertLess(result['occupied_iou']['value'], 0.8)
        self.assertLess(result['occupied_boundary_f1']['f1'], 0.95)

    def test_wall_thickening_lowers_boundary_f1(self):
        gt = base_state()
        thick = binary_dilation(gt == 1, iterations=3).astype(np.int8)
        result = self.evaluate(gt, thick)
        self.assertLess(result['occupied_boundary_f1']['f1'], 0.95)

    def test_unknown_masking_is_fixed(self):
        gt = base_state()
        gt[0:8, :] = -1
        est = gt.copy()
        est[0:8, :] = 1  # differences in GT-unknown domain must be excluded
        same = self.evaluate(gt, est)
        self.assertAlmostEqual(same['occupied_iou']['value'], 1.0, places=12)
        est = gt.copy()
        est[12:30, 20] = -1  # unknown over a known GT wall is a false negative
        missing = self.evaluate(gt, est)
        self.assertLess(missing['occupied_iou']['value'], 1.0)
        self.assertGreater(missing['supporting']['estimated_unknown_ratio'], 0.0)

    def test_equivalent_different_resolutions(self):
        # Same world-coordinate rectangle at 0.1 m and 0.05 m resolution.
        gt = np.zeros((40, 40), dtype=np.int8)
        est = np.zeros((80, 80), dtype=np.int8)
        gt[10:30, 10:20] = 1
        est[20:60, 20:40] = 1
        result = self.evaluate(gt, est, gt_resolution=0.1, est_resolution=0.05)
        self.assertAlmostEqual(result['occupied_iou']['value'], 1.0, places=12)
        self.assertAlmostEqual(result['occupied_boundary_f1']['f1'], 1.0, places=12)


if __name__ == '__main__':
    unittest.main(verbosity=2)
