#!/usr/bin/env python3
"""Write deterministic construct-validation evidence for Phase 4C map metrics."""

import argparse
import json
import tempfile
from pathlib import Path
import sys

import numpy as np
from scipy.ndimage import binary_dilation

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_mapping import load_map
from evaluate_mapping_v2 import evaluate_maps_v2
from test_phase4b_mapping import base_state, write_map


def evaluate(root, gt, est, gt_resolution=0.1, est_resolution=0.1, targets=None):
    gt_grid = load_map(write_map(root, "gt", gt, gt_resolution, (0.0, 0.0, 0.0)))
    est_grid = load_map(write_map(root, "est", est, est_resolution, (0.0, 0.0, 0.0)))
    return evaluate_maps_v2(
        gt_grid, est_grid, boundary_tolerance_m=0.20,
        local_targets=targets or [], local_radius_m=5.0,
    )


def compact(result):
    return {
        "boundary_f1": result["occupied_boundary_f1"]["f1"],
        "symmetric_boundary_distance_mean_m": result["symmetric_boundary_distance"]["mean_m"],
        "symmetric_boundary_distance_median_m": result["symmetric_boundary_distance"]["median_m"],
        "symmetric_boundary_distance_p95_m": result["symmetric_boundary_distance"]["p95_m"],
    }


def validate():
    with tempfile.TemporaryDirectory(prefix="phase4c0_map_validation_") as tmp:
        root = Path(tmp)
        gt = base_state()
        identity = compact(evaluate(root, gt, gt.copy()))
        translations = []
        for cells in (1, 2, 4):
            shifted = np.zeros_like(gt)
            shifted[:, cells:] = gt[:, :-cells]
            translations.append({"cells": cells, **compact(evaluate(root, gt, shifted))})
        double = gt.copy()
        double[:, 24] = np.maximum(double[:, 24], gt[:, 20])
        thick = binary_dilation(gt == 1, iterations=3).astype(np.int8)
        double_result = compact(evaluate(root, gt, double))
        thick_result = compact(evaluate(root, gt, thick))
        unknown = gt.copy()
        unknown[10:54, 18:46] = -1
        unknown_result = evaluate(
            root, gt, unknown, targets=[{"target_id": "centre", "xy": [3.2, 3.2]}]
        )
        coarse = np.zeros((40, 40), dtype=np.int8)
        fine = np.zeros((80, 80), dtype=np.int8)
        coarse[10:30, 10:20] = 1
        fine[20:60, 20:40] = 1
        resolution = compact(evaluate(root, coarse, fine, 0.1, 0.05))
        empty = np.zeros((128, 128), dtype=np.int8)
        empty_result = evaluate(
            root, empty, empty.copy(),
            targets=[{"target_id": "empty", "xy": [6.4, 6.4]}],
        )["local_revisit"][0]

    checks = {
        "identity": identity["boundary_f1"] == 1.0
                    and identity["symmetric_boundary_distance_mean_m"] == 0.0,
        "translation_1_2_4_monotonic": all(
            translations[i]["symmetric_boundary_distance_mean_m"]
            < translations[i + 1]["symmetric_boundary_distance_mean_m"]
            for i in range(2)
        ) and all(translations[i]["boundary_f1"] >= translations[i + 1]["boundary_f1"]
                  for i in range(2)),
        "double_wall_worse": double_result["boundary_f1"] < 1.0,
        "boundary_thickening_worse": thick_result["boundary_f1"] < 1.0,
        "unknown_masking_penalizes_recall_and_coverage": (
            unknown_result["local_revisit"][0]["observed_coverage"] < 1.0
            and unknown_result["local_revisit"][0]["boundary_f1"]["recall"] < 1.0
        ),
        "resolution_conversion": resolution["boundary_f1"] == 1.0
                                 and resolution["symmetric_boundary_distance_mean_m"] == 0.0,
        "empty_local_roi_not_false_perfect": (
            empty_result["boundary_f1"]["f1"] is None
            and empty_result["boundary_f1"]["status"] == "NOT_APPLICABLE_NO_GT_BOUNDARY"
        ),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "passed": sum(checks.values()), "total": len(checks), "checks": checks,
        "frozen_boundary_tolerance_m": 0.20, "frozen_local_radius_m": 5.0,
        "identity": identity, "translations": translations,
        "double_wall": double_result,
        "boundary_thickening": thick_result,
        "unknown_masking": {
            "local_observed_coverage": unknown_result["local_revisit"][0]["observed_coverage"],
            "local_boundary_recall": unknown_result["local_revisit"][0]["boundary_f1"]["recall"],
        },
        "resolution_conversion": resolution,
        "empty_local_roi_status": empty_result["boundary_f1"]["status"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path,
        default=Path("results/phase4c0/map_evaluation/evaluator_validation.json"),
    )
    args = parser.parse_args()
    result = validate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
