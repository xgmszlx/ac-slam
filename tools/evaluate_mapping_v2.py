#!/usr/bin/env python3
"""Phase 4C offline occupancy-grid boundary and local-revisit evaluation."""

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import distance_transform_edt

from evaluate_mapping import (
    boundary_scores,
    evaluate_maps,
    load_map,
    occupied_boundary,
    sample_source_on_target,
)


def directional_distances(source_boundary, target_boundary, resolution):
    if int(source_boundary.sum()) == 0 or int(target_boundary.sum()) == 0:
        return None
    distance = distance_transform_edt(~target_boundary, sampling=resolution)
    return distance[source_boundary]


def symmetric_boundary_distance(gt_boundary, est_boundary, resolution):
    gt_count = int(gt_boundary.sum())
    est_count = int(est_boundary.sum())
    if gt_count == 0 and est_count == 0:
        return {
            "mean_m": 0.0, "median_m": 0.0,
            "estimated_to_gt_mean_m": 0.0, "gt_to_est_mean_m": 0.0,
            "estimated_boundary_cells": 0, "gt_boundary_cells": 0,
            "status": "BOTH_EMPTY",
        }
    if gt_count == 0 or est_count == 0:
        return {
            "mean_m": None, "median_m": None,
            "estimated_to_gt_mean_m": None, "gt_to_est_mean_m": None,
            "estimated_boundary_cells": est_count, "gt_boundary_cells": gt_count,
            "status": "ONE_EMPTY_DISTANCE_UNDEFINED",
        }
    est_to_gt = directional_distances(est_boundary, gt_boundary, resolution)
    gt_to_est = directional_distances(gt_boundary, est_boundary, resolution)
    return {
        "mean_m": float(0.5 * (np.mean(est_to_gt) + np.mean(gt_to_est))),
        "median_m": float(0.5 * (np.median(est_to_gt) + np.median(gt_to_est))),
        "estimated_to_gt_mean_m": float(np.mean(est_to_gt)),
        "gt_to_est_mean_m": float(np.mean(gt_to_est)),
        "estimated_to_gt_median_m": float(np.median(est_to_gt)),
        "gt_to_est_median_m": float(np.median(gt_to_est)),
        "estimated_boundary_cells": int(est_boundary.sum()),
        "gt_boundary_cells": int(gt_boundary.sum()),
        "status": "AVAILABLE",
    }


def target_mask(grid, target_xy, radius_m):
    rows, cols = np.indices((grid.height, grid.width), dtype=np.float64)
    grid_y = grid.height - 1.0 - rows
    local_x = (cols + 0.5) * grid.resolution
    local_y = (grid_y + 0.5) * grid.resolution
    cosine = np.cos(grid.origin_yaw)
    sine = np.sin(grid.origin_yaw)
    world_x = grid.origin_x + cosine * local_x - sine * local_y
    world_y = grid.origin_y + sine * local_x + cosine * local_y
    return (world_x - target_xy[0]) ** 2 + (world_y - target_xy[1]) ** 2 <= radius_m ** 2


def local_boundary_scores(gt_boundary, est_boundary, mask, resolution, tolerance_m):
    local_gt = gt_boundary & mask
    local_est = est_boundary & mask
    gt_count, est_count = int(local_gt.sum()), int(local_est.sum())
    if gt_count == 0 and est_count == 0:
        return {
            "precision": None, "recall": None, "f1": None,
            "gt_boundary_cells": 0, "estimated_boundary_cells": 0,
            "estimated_matched_cells": 0, "gt_matched_cells": 0,
            "status": "NOT_APPLICABLE_NO_GT_BOUNDARY",
        }
    if gt_count == 0 or est_count == 0:
        return {
            "precision": 0.0, "recall": 0.0, "f1": 0.0,
            "gt_boundary_cells": gt_count, "estimated_boundary_cells": est_count,
            "estimated_matched_cells": 0, "gt_matched_cells": 0,
            "status": (
                "NO_ESTIMATED_BOUNDARY" if gt_count > 0 else "ESTIMATED_BOUNDARY_WITHOUT_GT"
            ),
        }
    distance_to_gt = distance_transform_edt(~gt_boundary, sampling=resolution)
    distance_to_est = distance_transform_edt(~est_boundary, sampling=resolution)
    est_matched = int((local_est & (distance_to_gt <= tolerance_m + 1e-12)).sum())
    gt_matched = int((local_gt & (distance_to_est <= tolerance_m + 1e-12)).sum())
    precision = est_matched / float(est_count)
    recall = gt_matched / float(gt_count)
    f1 = 0.0 if precision + recall == 0 else 2.0 * precision * recall / (precision + recall)
    return {
        "precision": precision, "recall": recall, "f1": f1,
        "gt_boundary_cells": gt_count, "estimated_boundary_cells": est_count,
        "estimated_matched_cells": est_matched, "gt_matched_cells": gt_matched,
        "status": "AVAILABLE",
    }


def local_symmetric_distance(gt_boundary, est_boundary, mask, resolution):
    result = symmetric_boundary_distance(gt_boundary & mask, est_boundary & mask, resolution)
    if result["status"] == "BOTH_EMPTY":
        result["mean_m"] = None
        result["median_m"] = None
        result["status"] = "NOT_APPLICABLE_NO_GT_BOUNDARY"
    return result


def evaluate_maps_v2(gt, estimated, boundary_tolerance_m=0.20, local_targets=None, local_radius_m=5.0):
    base = evaluate_maps(gt, estimated, boundary_tolerance_m=boundary_tolerance_m)
    estimated_on_gt = sample_source_on_target(estimated, gt)
    domain = gt.state >= 0
    gt_boundary = occupied_boundary((gt.state == 1) & domain)
    est_boundary = occupied_boundary((estimated_on_gt == 1) & domain)
    base["symmetric_boundary_distance"] = symmetric_boundary_distance(
        gt_boundary, est_boundary, gt.resolution
    )
    base["protocol"].update({
        "symmetric_boundary_distance": (
            "0.5 * (mean estimated-boundary to nearest GT-boundary distance + "
            "mean GT-boundary to nearest estimated-boundary distance)"
        ),
        "local_radius_m": float(local_radius_m),
        "local_boundary_policy": (
            "score boundary points whose centres lie inside the frozen circular ROI; "
            "nearest-neighbour search uses the full opposite boundary to avoid crop-edge artifacts"
        ),
        "local_coverage_policy": (
            "all GT-known cells in the circular ROI form the denominator; estimated unknown/out-of-bounds "
            "cells are unobserved, and unobserved GT boundary remains in local recall"
        ),
    })
    local = []
    for target in local_targets or []:
        mask = target_mask(gt, target["xy"], local_radius_m) & domain
        local_gt = gt_boundary & mask
        local_est = est_boundary & mask
        known = (estimated_on_gt >= 0) & mask
        entry = dict(target)
        entry.update({
            "radius_m": float(local_radius_m),
            "domain_cells": int(mask.sum()),
            "observed_cells": int(known.sum()),
            "observed_coverage": float(known.sum() / mask.sum()) if mask.any() else None,
            "boundary_f1": local_boundary_scores(
                gt_boundary, est_boundary, mask, gt.resolution, boundary_tolerance_m
            ),
            "symmetric_boundary_distance": local_symmetric_distance(
                gt_boundary, est_boundary, mask, gt.resolution
            ),
            "gt_boundary_cells": int(local_gt.sum()),
            "estimated_boundary_cells": int(local_est.sum()),
        })
        local.append(entry)
    base["local_revisit"] = local
    return base


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gt-yaml", required=True, type=Path)
    parser.add_argument("--estimated-yaml", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--boundary-tolerance-m", type=float, default=0.20)
    parser.add_argument("--local-radius-m", type=float, default=5.0)
    parser.add_argument("--targets-json", type=Path)
    args = parser.parse_args()
    targets = json.loads(args.targets_json.read_text()) if args.targets_json else []
    result = evaluate_maps_v2(
        load_map(args.gt_yaml), load_map(args.estimated_yaml),
        boundary_tolerance_m=args.boundary_tolerance_m,
        local_targets=targets, local_radius_m=args.local_radius_m,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "boundary_f1": result["occupied_boundary_f1"]["f1"],
        "symmetric_boundary_distance_m": result["symmetric_boundary_distance"]["mean_m"],
        "local_targets": len(result["local_revisit"]),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
