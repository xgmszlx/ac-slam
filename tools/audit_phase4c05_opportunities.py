#!/usr/bin/python3
"""Offline-only initial high-level opportunity audit for author map/prior pairs."""

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "baseline/Graph-Based_SLAM-Aware_Exploration/scripts"
sys.path.insert(0, str(SCRIPTS))

from offline_tsp_evaluation import (
    concorde_tsp_solver,
    connect_tsp_path,
    get_distance_matrix_for_new_tsp_solver,
    get_distance_matrix_for_tsp,
    offline_evaluate_tsp_path,
)
from read_drawio_to_nx import build_prior_map_from_drawio
from utils import add_edge_information_matrix, add_graph_weights_as_dopt


MAPS = {
    "map4": {"width": 39.8, "robot": (-17.9, -26.35)},
    "map7": {"width": 138.2, "robot": (-55.0, -20.0)},
    "map8": {"width": 86.8, "robot": (0.0, 0.0)},
}
SEEDS = tuple(range(21001, 21006))


def canonical_hash(value):
    payload = json.dumps(value, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def prior_graph(map_name, config):
    path = ROOT / "baseline/Graph-Based_SLAM-Aware_Exploration/world" / map_name / (map_name + ".xml")
    graph = build_prior_map_from_drawio(
        str(path), actual_map_width=config["width"],
        need_normalize=False, need_noise=False, variance=0,
    )
    for node in graph:
        x, y = graph.nodes[node]["position"]
        graph.nodes[node]["position"] = (x - config["robot"][0], y - config["robot"][1])
    covariance = np.diag([0.1, 0.1, 0.001])
    add_edge_information_matrix(graph, np.linalg.inv(covariance))
    add_graph_weights_as_dopt(graph, key="d_opt")
    return graph


def plan(graph, seed):
    _, node_list = get_distance_matrix_for_tsp(graph)
    start_index = min(
        range(len(node_list)),
        key=lambda index: sum(value * value for value in graph.nodes[node_list[index]]["position"]),
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


def audit(output_dir):
    rows, details = [], {}
    for map_name, config in MAPS.items():
        graph = prior_graph(map_name, config)
        details[map_name] = {}
        for seed in SEEDS:
            item = plan(graph.copy(), seed)
            details[map_name][str(seed)] = item
            rows.append({
                "map": map_name, "seed": seed,
                "planned_active_loop_actions": item["planned_active_loop_actions"],
                "selected_loop_vertex_sequence": json.dumps(item["selected_loop_vertex_sequence"]),
                "initial_tsp_hash": item["initial_tsp_hash"],
                "full_tsp_hash": item["full_tsp_hash"],
                "initial_tsp_path": json.dumps(item["initial_tsp_path"]),
                "full_tsp_path": json.dumps(item["full_tsp_path"]),
                "performance_exploration_run": False,
            })

    smoke_validation = {}
    smoke_root = ROOT / "results/phase4c0/maps/technical_smoke_20260831T100425"
    for map_name in ("map4", "map7"):
        smoke = json.loads((smoke_root / map_name / "tsp_record.json").read_text())
        item = details[map_name]["21001"]
        smoke_validation[map_name] = {
            "initial_tsp_equal": item["initial_tsp_path"] == smoke["initial_tsp_path"],
            "full_tsp_equal": item["full_tsp_path"] == smoke["full_tsp_path"],
        }

    map_summary = {}
    for map_name in MAPS:
        counts = [details[map_name][str(seed)]["planned_active_loop_actions"] for seed in SEEDS]
        map_summary[map_name] = {
            "per_seed_counts": {str(seed): count for seed, count in zip(SEEDS, counts)},
            "total_planned_active_loop_opportunities": sum(counts),
            "each_seed_at_least_2": all(count >= 2 for count in counts),
            "total_at_least_10": sum(counts) >= 10,
            "opportunity_adequacy": (
                "PASS" if all(count >= 2 for count in counts) and sum(counts) >= 10 else "FAIL"
            ),
        }
    selected = {name: map_summary[name]["opportunity_adequacy"] for name in ("map4", "map7")}
    replacement = [
        name for name in ("map8",)
        if map_summary[name]["opportunity_adequacy"] == "PASS"
    ]
    summary = {
        "status": "PASS",
        "audit_scope": "offline initial high-level planning only; no robot exploration",
        "formal_performance_runs_started": False,
        "criterion": "each seed >=2 planned active loops AND five-seed total >=10",
        "maps": map_summary,
        "selected_map_status": selected,
        "next_ranked_author_candidates_passing": replacement,
        "seed21001_offline_vs_startup_smoke": smoke_validation,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "opportunity_by_seed.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    (output_dir / "high_level_plans.json").write_text(
        json.dumps(details, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "opportunity_adequacy.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("results/phase4c0/opportunity_adequacy"),
    )
    args = parser.parse_args()
    print(json.dumps(audit(args.output_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
