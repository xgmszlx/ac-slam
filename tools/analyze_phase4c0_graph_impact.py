#!/usr/bin/env python3
"""Offline pose-graph impact audit using the baseline D-opt spanning-tree metric."""

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
from scipy.linalg import eigvalsh
from scipy.sparse import csc_matrix
from scipy.sparse.linalg import splu


EIG_TH = 1e-6


def covariance_from_upper(values):
    vals = [float(value) for value in values]
    if len(vals) != 6:
        raise ValueError("expected six covariance terms")
    return np.array([
        [vals[0], vals[1], vals[2]],
        [vals[1], vals[3], vals[4]],
        [vals[2], vals[4], vals[5]],
    ], dtype=float)


def edge_dopt_from_covariance(covariance):
    information = np.linalg.inv(covariance)
    eigenvalues = eigvalsh(information)
    selected = eigenvalues[eigenvalues > EIG_TH]
    if selected.size != 3 or not np.all(np.isfinite(selected)):
        raise ValueError("edge information is not finite positive definite")
    # Exact baseline utils.get_d_opt normalization for a 3 x 3 edge matrix.
    return float(np.exp(np.sum(np.log(selected)) / 3.0))


def normalized_weighted_spanning_tree_metric(nodes, edges):
    """Matrix-tree D-opt metric used by the baseline, evaluated in log space."""
    ordered = sorted(set(nodes))
    if len(ordered) < 2:
        return None
    anchor = ordered[0]
    free_nodes = ordered[1:]
    index = {node: idx for idx, node in enumerate(free_nodes)}
    size = len(free_nodes)
    matrix = np.zeros((size, size), dtype=float)
    for (start, end), covariance in edges.items():
        weight = edge_dopt_from_covariance(covariance)
        if start != anchor:
            matrix[index[start], index[start]] += weight
        if end != anchor:
            matrix[index[end], index[end]] += weight
        if start != anchor and end != anchor:
            matrix[index[start], index[end]] -= weight
            matrix[index[end], index[start]] -= weight
    factor = splu(csc_matrix(matrix))
    diagonal = np.abs(factor.U.diagonal())
    if np.any(diagonal <= 0) or not np.all(np.isfinite(diagonal)):
        raise ValueError("reduced weighted Laplacian is singular")
    log_determinant = float(np.sum(np.log(diagonal)))
    return float(np.exp(log_determinant / size))


def snapshot_graph(snapshot):
    nodes = [int(key) for key in snapshot["pose_graph_nodes"]]
    # nx.Graph in the baseline keeps one value for duplicate undirected endpoints.
    edges = {}
    for edge in snapshot["pose_graph_edges"]:
        key = tuple(sorted((int(edge["start"]), int(edge["end"]))))
        edges[key] = covariance_from_upper(edge["covariance_upper_triangle"].split())
    return nodes, edges


def g2o_graph(path):
    nodes, edges = [], {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        values = line.split()
        if not values:
            continue
        if values[0] == "VERTEX_SE2":
            nodes.append(int(values[1]))
        elif values[0] == "EDGE_SE2":
            key = tuple(sorted((int(values[1]), int(values[2]))))
            edges[key] = covariance_from_upper(values[3:9])
    return nodes, edges


def pose_correction(before, after):
    old = before.get("trajectory_estimate", [])
    new = after.get("trajectory_estimate", [])
    count = min(len(old), len(new))
    if count == 0:
        return None
    distances = [
        math.hypot(new[i]["x"] - old[i]["x"], new[i]["y"] - old[i]["y"])
        for i in range(count)
    ]
    return {
        "common_nodes": count,
        "mean_m": float(np.mean(distances)),
        "max_m": float(np.max(distances)),
        "median_m": float(np.median(distances)),
    }


def validate_metric():
    covariance = np.diag([0.1, 0.1, 0.001])
    nodes = [0, 1, 2, 3]
    edges = {
        (0, 1): covariance, (1, 2): covariance,
        (2, 3): covariance, (0, 3): covariance,
    }
    sparse_value = normalized_weighted_spanning_tree_metric(nodes, edges)
    weights = {edge: edge_dopt_from_covariance(cov) for edge, cov in edges.items()}
    laplacian = np.zeros((4, 4), dtype=float)
    for (start, end), weight in weights.items():
        laplacian[start, start] += weight
        laplacian[end, end] += weight
        laplacian[start, end] -= weight
        laplacian[end, start] -= weight
    eigenvalues = eigvalsh(laplacian[1:, 1:])
    baseline_dense = float(np.exp(np.sum(np.log(eigenvalues[eigenvalues > EIG_TH])) / 3.0))
    return {
        "toy_sparse_value": sparse_value,
        "toy_baseline_dense_value": baseline_dense,
        "absolute_error": abs(sparse_value - baseline_dense),
        "pass": abs(sparse_value - baseline_dense) <= 1e-9,
    }


def analyze(attribution_csv, output_dir):
    with Path(attribution_csv).open(newline="", encoding="utf-8") as stream:
        attribution = list(csv.DictReader(stream))
    rows = []
    marginal_available = 0
    correction_available = 0
    prepost_available = 0
    for event in attribution:
        run_dir = Path(event["run_dir"])
        loops = json.loads((run_dir / "loops.json").read_text())["loops"]
        loop = None
        if event["loop_id"]:
            loop = next(item for item in loops if int(item["loop_id"]) == int(event["loop_id"]))
        before_metric = after_metric = delta_metric = None
        correction = None
        if loop is not None:
            before = json.loads((run_dir / loop["snapshot_before"]).read_text())
            after = json.loads((run_dir / loop["snapshot_after"]).read_text())
            before_metric = normalized_weighted_spanning_tree_metric(*snapshot_graph(before))
            after_metric = normalized_weighted_spanning_tree_metric(*snapshot_graph(after))
            delta_metric = after_metric - before_metric
            prepost_available += 1
            correction = pose_correction(before, after)
            if correction is not None:
                correction_available += 1

        final_nodes, final_edges = g2o_graph(run_dir / "pose_graph.g2o")
        current = int(event["current_scan"])
        chain = range(int(event["chain_start"]), int(event["chain_end"]) + 1)
        closure_edges = [tuple(sorted((current, scan))) for scan in chain]
        closure_edges = [edge for edge in closure_edges if edge in final_edges]
        full_metric = without_metric = marginal_gain = None
        marginal_status = "NOT_AVAILABLE_CLOSURE_EDGE_MISSING_FROM_SAVED_GRAPH"
        if len(closure_edges) == 1:
            full_metric = normalized_weighted_spanning_tree_metric(final_nodes, final_edges)
            without = dict(final_edges)
            without.pop(closure_edges[0])
            without_metric = normalized_weighted_spanning_tree_metric(final_nodes, without)
            marginal_gain = full_metric - without_metric
            marginal_status = "AVAILABLE_FINAL_GRAPH_EDGE_ABLATION"
            marginal_available += 1
        elif len(closure_edges) > 1:
            marginal_status = "NOT_AVAILABLE_AMBIGUOUS_MULTIPLE_CLOSURE_EDGES"

        rows.append({
            "map": event["map"], "seed": event["seed"], "method": event["method"],
            "condition": event["condition"], "loop_id": event["loop_id"],
            "vertex": event["vertex"], "event_seq": event["event_seq"],
            "attribution_class": event["attribution_class"],
            "current_scan": current, "chain_start": event["chain_start"], "chain_end": event["chain_end"],
            "R_before_interval": before_metric, "R_after_interval": after_metric,
            "Delta_R_interval_observed": delta_metric,
            "Delta_R_interval_causal_status": (
                "NON_CAUSAL_INTERVAL_WIDE_INCLUDES_NEW_ODOMETRY" if loop is not None else "NOT_AVAILABLE"
            ),
            "closure_edge": json.dumps(closure_edges[0]) if len(closure_edges) == 1 else "",
            "R_final_with_edge": full_metric, "R_final_without_edge": without_metric,
            "Delta_R_actual_marginal": marginal_gain, "marginal_status": marginal_status,
            "pose_correction_common_nodes": correction["common_nodes"] if correction else "",
            "pose_correction_mean_m": correction["mean_m"] if correction else "",
            "pose_correction_median_m": correction["median_m"] if correction else "",
            "pose_correction_max_m": correction["max_m"] if correction else "",
            "materially_corrected_nodes": "",
            "material_threshold_status": "NOT_DEFINED_CONTINUOUS_VALUES_ONLY",
        })

    output_dir.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with (output_dir / "phase4b_closure_impact.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    predicted_fields = [
        "map", "seed", "method", "condition", "loop_id", "vertex", "event_seq",
        "attribution_class", "Delta_R_predicted", "Delta_R_actual_marginal", "eta_real", "status",
    ]
    with (output_dir / "predicted_vs_realized_gain.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=predicted_fields)
        writer.writeheader()
        for row in rows:
            if row["attribution_class"] != "TARGET_ATTRIBUTABLE":
                continue
            writer.writerow({
                **{key: row[key] for key in predicted_fields if key in row},
                "Delta_R_predicted": "", "eta_real": "",
                "status": "NOT_AVAILABLE_PREDICTED_GAIN_NOT_LOGGED",
            })
    validation = {
        "baseline_metric": (
            "normalized weighted spanning-tree D-opt: exp(log(det(reduced weighted Laplacian))/(N-1)); "
            "edge weight is the D-opt geometric mean of the inverse 3x3 edge covariance"
        ),
        "implementation_validation": validate_metric(),
        "accepted_events": len(rows),
        "interval_pre_post_available": prepost_available,
        "interval_pre_post_causal_interpretation": "not valid; node/odometry growth occurs during intervals",
        "final_graph_closure_edge_ablation_available": marginal_available,
        "pose_correction_available": correction_available,
        "pose_correction_definition": (
            "index-aligned /slam_path historical positions common to before/after snapshots; continuous mean/median/max only"
        ),
        "predicted_gain_available": False,
        "eta_real_available": False,
    }
    (output_dir / "graph_metric_validation.json").write_text(
        json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return validation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--attribution-csv", type=Path,
                        default=Path("results/phase4c0/attribution/phase4b_event_attribution.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/phase4c0/graph_impact"))
    args = parser.parse_args()
    print(json.dumps(analyze(args.attribution_csv, args.output_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
