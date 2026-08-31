#!/usr/bin/env python3
"""Offline-only active-loop opportunity gate for Phase 4C-1 candidates."""

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import types
from pathlib import Path

import networkx as nx
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "baseline/Graph-Based_SLAM-Aware_Exploration/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.append(str(ROOT / "catkin_ws/python"))

# offline_tsp_evaluation imports rospy only for two logerr calls.  Keep the
# author's implementation untouched and avoid mixing ROS Python 3.8 packages
# into the Python 3.12 scientific environment.
sys.modules.setdefault("rospy", types.SimpleNamespace(logerr=lambda message: print(message, file=sys.stderr)))

from offline_tsp_evaluation import (
    concorde_tsp_solver,
    connect_tsp_path,
    get_distance_matrix_for_new_tsp_solver,
    get_distance_matrix_for_tsp,
    offline_evaluate_tsp_path,
)
from read_drawio_to_nx import build_prior_map_from_drawio
from utils import add_edge_information_matrix, add_graph_weights_as_dopt


SEEDS = tuple(range(21001, 21006))
MIN_PER_SEED = 2
MIN_TOTAL = 10

# Frozen before opportunity outputs.  The shorter-side/free-area rule prevents a
# tiny point-navigation layout or a single narrow corridor from becoming primary M3.
SCALE_GATE = {
    "minimum_width_m": 45.0,
    "minimum_height_m": 30.0,
    "minimum_free_area_m2": 500.0,
}

ORDER = {
    21001: ["A", "B", "C"],
    21002: ["B", "C", "A"],
    21003: ["C", "A", "B"],
    21004: ["A", "C", "B"],
    21005: ["B", "A", "C"],
}


def canonical_hash(value):
    payload = json.dumps(value, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def parse_world(path):
    text = Path(path).read_text(encoding="utf-8")
    sizes = re.findall(r"size\s*\[([^]]+)\]", text)
    poses = re.findall(r"pose\s*\[([^]]+)\]", text)
    if not sizes or not poses:
        raise ValueError("missing Stage size/start pose in {}".format(path))
    return (
        [float(value) for value in sizes[-1].split()[:2]],
        [float(value) for value in poses[-1].split()[:3]],
    )


def load_graph(candidate_dir):
    candidate = candidate_dir.name
    size, start = parse_world(candidate_dir / (candidate + ".world"))
    graph = build_prior_map_from_drawio(
        str(candidate_dir / (candidate + ".xml")), actual_map_width=size[0],
        need_normalize=False, need_noise=False, variance=0,
    )
    for node in graph:
        x, y = graph.nodes[node]["position"]
        graph.nodes[node]["position"] = (x - start[0], y - start[1])
    covariance = np.diag([0.1, 0.1, 0.001])
    add_edge_information_matrix(graph, np.linalg.inv(covariance))
    add_graph_weights_as_dopt(graph, key="d_opt")
    return graph, size, start


def plan(graph, seed):
    _, node_list = get_distance_matrix_for_tsp(graph)
    start_index = min(
        range(len(node_list)),
        key=lambda index: (
            sum(value * value for value in graph.nodes[node_list[index]]["position"]),
            int(node_list[index]),
        ),
    )
    concorde_nodes = [node_list[start_index]] + [
        node for index, node in enumerate(node_list) if index != start_index
    ]
    matrix = get_distance_matrix_for_new_tsp_solver(graph, node_list=concorde_nodes)
    initial, predicted = concorde_tsp_solver(matrix, concorde_nodes, seed=seed)
    full = connect_tsp_path(graph, initial)
    result = offline_evaluate_tsp_path(graph, full)
    optimized, modified, loop_indices = result[0], result[1], result[2]
    if optimized:
        selected_path = [int(node) for node in modified]
        loop_indices = sorted(int(index) for index in loop_indices)
    else:
        selected_path, loop_indices = [int(node) for node in initial], []
    loop_vertices = [selected_path[index] for index in loop_indices]
    return {
        "solver": "concorde", "seed": seed,
        "initial_tsp_path": [int(node) for node in initial],
        "full_tsp_path": [int(node) for node in full],
        "initial_tsp_hash": canonical_hash([int(node) for node in initial]),
        "full_tsp_hash": canonical_hash([int(node) for node in full]),
        "predicted_tsp_length": float(predicted),
        "modified_high_level_path": selected_path,
        "selected_loop_indices": loop_indices,
        "selected_loop_vertex_sequence": loop_vertices,
        "planned_active_loop_actions": len(loop_vertices),
    }


def topology_distance_selection(inventory, topology, eligible):
    author_rows = {
        row["map_name"]: row
        for row in csv.DictReader((ROOT / "results/phase4c0/maps/map_inventory.csv").open())
    }
    rows = []
    for name in ("map3", "map8"):
        row = author_rows[name]
        width, height, free = map(float, (row["width_m"], row["height_m"], row["free_area_m2"]))
        skeleton_length = float(row["free_space_skeleton_length_m"])
        rows.append({
            "name": name, "aspect_ratio": width / height,
            "free_fraction": free / (width * height),
            "skeleton_length_per_free_area": skeleton_length / free,
            "junction_density_per_100m": float(row["skeleton_junction_density_per_100m"]),
            "log1p_skeleton_cycles": math.log1p(float(row["skeleton_cycle_count"])),
            "median_corridor_width_m": float(row["median_corridor_width_m"]),
            "log1p_prior_cycle_rank": math.log1p(float(row["prior_graph_cycle_rank"])),
        })
    inventory_by_name = {row["candidate"]: row for row in inventory}
    topology_by_name = {row["candidate"]: row for row in topology}
    for name in sorted(topology_by_name):
        inv, topo = inventory_by_name[name], topology_by_name[name]
        width, height, free = map(float, (inv["width_m"], inv["height_m"], inv["free_area_m2"]))
        skeleton_length = float(topo["skeleton_length_m"])
        rows.append({
            "name": name, "aspect_ratio": width / height,
            "free_fraction": free / (width * height),
            "skeleton_length_per_free_area": skeleton_length / free,
            "junction_density_per_100m": float(topo["junction_density_per_100m"]),
            "log1p_skeleton_cycles": math.log1p(float(topo["skeleton_cycle_count"])),
            "median_corridor_width_m": float(topo["median_corridor_width_m"]),
            "log1p_prior_cycle_rank": math.log1p(float(topo["prior_cycle_rank"])),
        })
    features = [key for key in rows[0] if key != "name"]
    values = np.asarray([[row[key] for key in features] for row in rows], dtype=float)
    scale = values.std(axis=0)
    scale[scale == 0] = 1.0
    standardized = (values - values.mean(axis=0)) / scale
    index = {row["name"]: i for i, row in enumerate(rows)}
    distances = {}
    for name in eligible:
        distance_map3 = float(np.linalg.norm(standardized[index[name]] - standardized[index["map3"]]))
        distance_map8 = float(np.linalg.norm(standardized[index[name]] - standardized[index["map8"]]))
        distances[name] = {
            "distance_to_map3": distance_map3,
            "distance_to_map8": distance_map8,
            "minimum_distance_to_frozen_maps": min(distance_map3, distance_map8),
        }
    selected = max(
        eligible,
        key=lambda name: (distances[name]["minimum_distance_to_frozen_maps"], name),
    ) if eligible else None
    return selected, distances, features


def audit(output_root):
    environment_root = output_root / "environments"
    inventory = list(csv.DictReader((output_root / "candidate_inventory.csv").open()))
    topology = list(csv.DictReader((output_root / "topology_metrics.csv").open()))
    validation = json.loads((output_root / "prior_builder_validation.json").read_text())
    rows, details, summaries = [], {}, {}
    for candidate_dir in sorted(path for path in environment_root.iterdir() if path.is_dir()):
        candidate = candidate_dir.name
        graph, size, start = load_graph(candidate_dir)
        details[candidate] = {}
        for seed in SEEDS:
            item = plan(graph.copy(), seed)
            details[candidate][str(seed)] = item
            rows.append({
                "candidate": candidate, "seed": seed,
                "planned_active_loop_actions": item["planned_active_loop_actions"],
                "selected_loop_vertex_sequence": json.dumps(item["selected_loop_vertex_sequence"]),
                "initial_tsp_hash": item["initial_tsp_hash"], "full_tsp_hash": item["full_tsp_hash"],
                "initial_tsp_path": json.dumps(item["initial_tsp_path"]),
                "full_tsp_path": json.dumps(item["full_tsp_path"]),
                "predicted_tsp_length": item["predicted_tsp_length"],
                "performance_exploration_run": False,
            })
        counts = [details[candidate][str(seed)]["planned_active_loop_actions"] for seed in SEEDS]
        inv = next(row for row in inventory if row["candidate"] == candidate)
        scale_pass = (
            float(inv["width_m"]) >= SCALE_GATE["minimum_width_m"]
            and float(inv["height_m"]) >= SCALE_GATE["minimum_height_m"]
            and float(inv["free_area_m2"]) >= SCALE_GATE["minimum_free_area_m2"]
        )
        opportunity_pass = all(count >= MIN_PER_SEED for count in counts) and sum(counts) >= MIN_TOTAL
        prior_pass = validation["candidates"][candidate]["status"] == "PASS"
        summaries[candidate] = {
            "per_seed_counts": {str(seed): count for seed, count in zip(SEEDS, counts)},
            "total": sum(counts), "each_seed_at_least_2": all(count >= MIN_PER_SEED for count in counts),
            "total_at_least_10": sum(counts) >= MIN_TOTAL,
            "opportunity_adequacy": "PASS" if opportunity_pass else "FAIL",
            "scale_adequacy": "PASS" if scale_pass else "FAIL",
            "prior_validation": "PASS" if prior_pass else "FAIL",
            "primary_m3_eligible": bool(opportunity_pass and scale_pass and prior_pass),
        }
    eligible = sorted(name for name, item in summaries.items() if item["primary_m3_eligible"])
    selected, distances, features = topology_distance_selection(inventory, topology, eligible)
    for name in summaries:
        summaries[name]["topology_distance"] = distances.get(name)
    with (output_root / "opportunity_counts.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    (output_root / "high_level_plans.json").write_text(
        json.dumps(details, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    selection = {
        "status": "READY_FOR_PHASE4C_FORMAL" if selected else "NO_EXTERNAL_MAP_MEETS_ADEQUACY",
        "M1": "map3", "M2": "map8", "M3": selected,
        "M2_frozen": True, "M2_opportunities": [3, 3, 3, 3, 3],
        "candidate_results": summaries, "opportunity_criterion": {
            "minimum_per_seed": MIN_PER_SEED, "minimum_five_seed_total": MIN_TOTAL,
        },
        "scale_gate": SCALE_GATE,
        "selection_rule": "among prior/scale/opportunity PASS candidates, maximize minimum standardized topology distance to map3 and map8",
        "topology_features": features, "performance_results_consulted": False,
        "formal_performance_runs_started": False,
    }
    (output_root / "selected_environment.json").write_text(
        json.dumps(selection, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    protocol = {
        "status": selection["status"],
        "generation_base_checkpoint": "cbd86bb29524d4ad3cbaaff37314addb8e0f4704",
        "formal_performance_runs_started": False,
        "environments": {"M1": "map3", "M2": "map8", "M3": selected},
        "future_order": {str(seed): order for seed, order in ORDER.items()},
        "future_new_runs": 30 if selected else 0,
        "map3_policy": "reuse Phase4B raw runs with neutral attribution and unified offline evaluator",
        "primary_unit": "map-seed", "individual_loop_use": "descriptive only",
        "frozen_attribution": "unique active interval AND accepted historical chain overlaps fixed 7-scan H_star",
        "frozen_local_roi": "5.0 m circle centered on method-neutral high-level loop vertex",
        "frozen_mapping_metrics": {
            "primary": {
                "boundary_f1_tolerance_m": 0.20,
                "symmetric_boundary_distance": True,
            },
            "secondary": ["occupied_iou"],
            "local": [
                "local_boundary_f1", "local_symmetric_boundary_distance",
                "local_observed_coverage",
            ],
        },
        "frozen_online_settings": {
            "active_loop_proxy_m": 4.0,
            "neutral_attribution_history_scans": 7,
            "nominal_repair_budget_m": 12.0,
            "repair_waypoint_cap": 24,
            "repair_densification_m": 0.5,
            "early_stop_changed": False,
            "direction_cue_changed": False,
            "karto_changed": False,
            "d_opt_changed": False,
            "tsp_objective_changed": False,
            "frontier_logic_changed": False,
            "navigation_parameters_changed": False,
        },
        "selection_sequence_fields": [
            "selected_loop_vertex_sequence", "selection_order", "selection_timestamp",
            "initial_tsp_hash", "full_tsp_hash",
        ],
        "method_parameters_changed": False,
    }
    (output_root / "protocol_manifest.json").write_text(
        json.dumps(protocol, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return selection


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=Path("results/phase4c1"))
    args = parser.parse_args()
    print(json.dumps(audit(args.output_root.resolve()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
