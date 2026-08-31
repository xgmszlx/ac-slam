#!/usr/bin/env python3
"""Offline Phase 4B reanalysis with frozen Phase 4C boundary metrics."""

import argparse
import csv
import json
import pickle
from pathlib import Path

import numpy as np

from evaluate_mapping import load_map
from evaluate_mapping_v2 import evaluate_maps_v2


METHOD_DIRS = ("A_original", "B_always_trace", "C_selective")


def stats(values):
    values = [value for value in values if value is not None and np.isfinite(value)]
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        return {"mean": None, "median": None, "min": None, "max": None, "n": 0}
    return {
        "mean": float(np.mean(array)), "median": float(np.median(array)),
        "min": float(np.min(array)), "max": float(np.max(array)), "n": int(array.size),
    }


def run_dirs(root):
    for seed_dir in sorted(root.glob("seed_*")):
        for method_dir in METHOD_DIRS:
            path = seed_dir / method_dir
            if path.is_dir():
                yield path


def load_prior(run_dir):
    paths = list((run_dir / "author_outputs").glob("prior_map_*.pickle"))
    with paths[0].open("rb") as stream:
        return pickle.load(stream)


def reanalyze(root, gt_yaml, output_dir, detail_dir):
    gt = load_map(gt_yaml)
    global_rows, local_rows = [], []
    for run_dir in run_dirs(root):
        manifest = json.loads((run_dir / "manifest.json").read_text())
        loops = json.loads((run_dir / "loops.json").read_text())["loops"]
        prior = load_prior(run_dir)
        targets = [{
            "target_id": "loop_{}".format(loop["loop_id"]),
            "loop_id": loop["loop_id"], "vertex": loop["loop_vertex"],
            "xy": list(prior.nodes[int(loop["loop_vertex"])]["position"]),
        } for loop in loops]
        result = evaluate_maps_v2(
            gt, load_map(run_dir / "final_map.yaml"), boundary_tolerance_m=0.20,
            local_targets=targets, local_radius_m=5.0,
        )
        relative = run_dir.relative_to(root)
        detail_path = detail_dir / relative / "mapping_metrics_v2.json"
        detail_path.parent.mkdir(parents=True, exist_ok=True)
        detail_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        global_rows.append({
            "map": manifest["map"], "seed": manifest["seed"],
            "condition": manifest["condition"], "method": manifest["method"],
            "occupied_boundary_f1": result["occupied_boundary_f1"]["f1"],
            "symmetric_boundary_distance_mean_m": result["symmetric_boundary_distance"]["mean_m"],
            "symmetric_boundary_distance_median_m": result["symmetric_boundary_distance"]["median_m"],
            "symmetric_boundary_distance_p95_m": result["symmetric_boundary_distance"]["p95_m"],
            "occupied_iou_secondary": result["occupied_iou"]["value"],
            "observed_coverage_global": 1.0 - result["supporting"]["estimated_unknown_ratio"],
            "detail": str(detail_path),
        })
        for local in result["local_revisit"]:
            local_rows.append({
                "map": manifest["map"], "seed": manifest["seed"],
                "condition": manifest["condition"], "method": manifest["method"],
                "loop_id": local["loop_id"], "vertex": local["vertex"],
                "target_x": local["xy"][0], "target_y": local["xy"][1],
                "radius_m": local["radius_m"],
                "local_boundary_f1": local["boundary_f1"]["f1"],
                "local_boundary_status": local["boundary_f1"]["status"],
                "local_boundary_precision": local["boundary_f1"]["precision"],
                "local_boundary_recall": local["boundary_f1"]["recall"],
                "local_symmetric_boundary_distance_mean_m": local["symmetric_boundary_distance"]["mean_m"],
                "local_symmetric_boundary_distance_median_m": local["symmetric_boundary_distance"]["median_m"],
                "local_symmetric_boundary_distance_p95_m": local["symmetric_boundary_distance"]["p95_m"],
                "local_distance_status": local["symmetric_boundary_distance"]["status"],
                "local_observed_coverage": local["observed_coverage"],
                "local_domain_cells": local["domain_cells"],
                "local_gt_boundary_cells": local["gt_boundary_cells"],
            })

    output_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in (("mapping_boundary_metrics.csv", global_rows),
                       ("local_revisit_metrics.csv", local_rows)):
        with (output_dir / name).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)

    by_block = {(row["map"], row["seed"], row["condition"]): row for row in global_rows}
    paired_rows = []
    for map_name, seed in sorted({(row["map"], row["seed"]) for row in global_rows}):
        for left, right in (("B", "A"), ("C", "A"), ("C", "B")):
            lhs, rhs = by_block[(map_name, seed, left)], by_block[(map_name, seed, right)]
            paired_rows.append({
                "map": map_name, "seed": seed, "contrast": "{}-{}".format(left, right),
                "boundary_f1_delta": lhs["occupied_boundary_f1"] - rhs["occupied_boundary_f1"],
                "symmetric_distance_delta_m": (
                    lhs["symmetric_boundary_distance_mean_m"]
                    - rhs["symmetric_boundary_distance_mean_m"]
                ),
                "occupied_iou_delta_secondary": (
                    lhs["occupied_iou_secondary"] - rhs["occupied_iou_secondary"]
                ),
            })
    with (output_dir / "paired_seed_mapping_v2.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(paired_rows[0]))
        writer.writeheader(); writer.writerows(paired_rows)

    method_stats = {}
    for condition in ("A", "B", "C"):
        selected = [row for row in global_rows if row["condition"] == condition]
        local_selected = [row for row in local_rows if row["condition"] == condition]
        method_stats[condition] = {
            "global_boundary_f1": stats([row["occupied_boundary_f1"] for row in selected]),
            "global_symmetric_distance_m": stats([
                row["symmetric_boundary_distance_mean_m"] for row in selected
            ]),
            "occupied_iou_secondary": stats([row["occupied_iou_secondary"] for row in selected]),
            "local_boundary_f1_loop_descriptive": stats([
                row["local_boundary_f1"] for row in local_selected
            ]),
            "local_symmetric_distance_m_loop_descriptive": stats([
                row["local_symmetric_boundary_distance_mean_m"] for row in local_selected
            ]),
            "local_observed_coverage_loop_descriptive": stats([
                row["local_observed_coverage"] for row in local_selected
            ]),
        }
    summary = {
        "status": "OFFLINE_REANALYSIS_COMPLETED",
        "formal_runs": len(global_rows), "local_loop_rows": len(local_rows),
        "global_primary_metrics": ["occupied_boundary_f1", "symmetric_boundary_distance_mean_m"],
        "local_secondary_metrics": [
            "local_boundary_f1", "local_symmetric_boundary_distance_mean_m", "local_observed_coverage"
        ],
        "occupied_iou_role": "secondary construct-limited metric",
        "inference_warning": "loop rows are descriptive; the formal paired unit remains map-seed",
        "local_target_comparability": {
            "same_loop_vertex_sequence_across_A_B_C_for_each_seed": all(
                len({
                    tuple(int(row["vertex"]) for row in local_rows
                          if row["seed"] == seed and row["condition"] == condition)
                    for condition in ("A", "B", "C")
                }) == 1
                for seed in sorted({row["seed"] for row in local_rows})
            ),
            "coordinate_frame": "prior-map and map frame share the recorded start-relative coordinates",
        },
        "local_availability": {
            key: sum(row["local_boundary_status"] == key for row in local_rows)
            for key in sorted({row["local_boundary_status"] for row in local_rows})
        },
        "method_stats": method_stats,
    }
    (output_dir / "phase4b_mapping_reanalysis.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase4b-root", type=Path, default=Path("results/phase4b/map3"))
    parser.add_argument("--gt-yaml", type=Path,
                        default=Path("baseline/Graph-Based_SLAM-Aware_Exploration/world/map3/map3.yaml"))
    parser.add_argument("--output-dir", type=Path,
                        default=Path("results/phase4b/map3/aggregate_v2"))
    parser.add_argument("--detail-dir", type=Path,
                        default=Path("results/phase4c0/map_evaluation/phase4b_map3"))
    args = parser.parse_args()
    print(json.dumps(reanalyze(args.phase4b_root, args.gt_yaml, args.output_dir, args.detail_dir),
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
