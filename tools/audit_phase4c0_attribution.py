#!/usr/bin/env python3
"""Offline measurement-level attribution audit for Phase 4B accepted loops.

This script never contacts ROS.  It reconstructs the exact history scan ids used by
the frozen reliable-loop implementation from the pre-loop pose graph and prior graph,
then combines them with the Karto keyscan acquisition timestamps already present in
rosout.  Existing Phase 4B artifacts are read-only.
"""

import argparse
import csv
import glob
import json
import math
import pickle
import re
from pathlib import Path


KEYSCAN_RE = re.compile(
    r"PHASE2C_KEYSCAN_ACCEPTED unique_id=(\d+) state_id=(\d+) sim_time=([0-9.]+)"
)
METHOD_DIRS = ("A_original", "B_always_trace", "C_selective")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def path_length(ids, nodes):
    return sum(
        math.hypot(nodes[b]["x"] - nodes[a]["x"], nodes[b]["y"] - nodes[a]["y"])
        for a, b in zip(ids, ids[1:])
    )


def densify(points, spacing_m):
    if len(points) < 2:
        return list(points)
    out = [points[0]]
    for a, b in zip(points, points[1:]):
        distance = math.hypot(b[0] - a[0], b[1] - a[1])
        count = max(1, int(round(distance / spacing_m)))
        for index in range(1, count + 1):
            fraction = index / float(count)
            out.append((
                a[0] + fraction * (b[0] - a[0]),
                a[1] + fraction * (b[1] - a[1]),
            ))
    return out


def nearest_prior_assignments(nodes, prior):
    vertices = sorted(prior.nodes())
    by_vertex = {vertex: [] for vertex in vertices}
    for scan_id, pose in sorted(nodes.items()):
        vertex = min(
            vertices,
            key=lambda item: (
                (prior.nodes[item]["position"][0] - pose["x"]) ** 2
                + (prior.nodes[item]["position"][1] - pose["y"]) ** 2
            ),
        )
        by_vertex[vertex].append(scan_id)
    return by_vertex


def reconstruct_intended_history(run_dir, loop, snapshot, prior, manifest):
    """Mirror frozen path_planner.py selection without changing its behavior."""
    nodes = {int(key): value for key, value in snapshot["pose_graph_nodes"].items()}
    ordered = sorted(nodes)
    vertex = int(loop["loop_vertex"])
    by_vertex = nearest_prior_assignments(nodes, prior)
    candidates = by_vertex.get(vertex, [])
    if not candidates:
        raise ValueError("no pre-loop scan assigned to prior vertex {}".format(vertex))
    vertex_x, vertex_y = prior.nodes[vertex]["position"]
    closest = min(
        candidates,
        key=lambda scan_id: (
            (nodes[scan_id]["x"] - vertex_x) ** 2
            + (nodes[scan_id]["y"] - vertex_y) ** 2
        ),
    )
    mode = int(manifest["oracle_mode"])
    args = manifest["launch_arguments"]
    policy = loop.get("phase4b_execution_policy") or loop.get("execution_policy")

    if mode == 1:
        index = ordered.index(closest)
        before = int(args["oracle_before"])
        after = int(args["oracle_after"])
        intended = ordered[max(0, index - before):min(len(ordered), index + after + 1)]
        points = [(nodes[item]["x"], nodes[item]["y"]) for item in intended]
        expected = densify(points, float(args["oracle_densify_m"]))
    elif mode == 2 and policy == "SELECTIVE_REPAIR":
        index = ordered.index(closest)
        lo, hi = index, index + 1
        intended = [closest]
        max_waypoints = int(args["oracle_repair_max_wp"])
        nominal_budget = float(args["oracle_repair_max_len"])
        while True:
            if lo > 0 and (hi - lo) < len(ordered) and len(intended) < max_waypoints:
                lo -= 1
                intended.insert(0, ordered[lo])
            if path_length(intended, nodes) >= nominal_budget:
                break
            if hi < len(ordered) and (hi - lo) < len(ordered) and len(intended) < max_waypoints:
                intended.append(ordered[hi])
                hi += 1
            if path_length(intended, nodes) >= nominal_budget:
                break
            if (lo == 0 and hi == len(ordered)) or len(intended) >= max_waypoints:
                break
        robot = nodes[ordered[-1]]
        first, last = nodes[intended[0]], nodes[intended[-1]]

        def wrap(angle):
            while angle > math.pi:
                angle -= 2.0 * math.pi
            while angle < -math.pi:
                angle += 2.0 * math.pi
            return angle

        direction_lambda = float(args["oracle_dir_lambda"])

        def direction_score(pose):
            return (
                math.hypot(pose["x"] - robot["x"], pose["y"] - robot["y"])
                + direction_lambda * abs(wrap(pose["theta"] - robot["theta"]))
            )

        direction = "reverse" if direction_score(last) < direction_score(first) else "forward"
        directed = list(reversed(intended)) if direction == "reverse" else list(intended)
        points = [(nodes[item]["x"], nodes[item]["y"]) for item in directed]
        expected = densify(points, float(args["oracle_repair_densify"]))
        if len(expected) > max_waypoints:
            step = (len(expected) - 1) / float(max_waypoints - 1)
            expected = [expected[int(round(i * step))] for i in range(max_waypoints)]
    else:
        index = candidates.index(closest)
        intended = candidates[index:min(index + 7, len(candidates))]
        expected = [(nodes[item]["x"], nodes[item]["y"]) for item in intended]

    observed = [tuple(point) for point in loop["planned_loop_path"]]
    same_length = len(expected) == len(observed)
    forward_error = max(
        (math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(expected, observed)),
        default=0.0,
    ) if same_length else None
    reverse_error = max(
        (math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(reversed(expected), observed)),
        default=0.0,
    ) if same_length else None
    errors = [value for value in (forward_error, reverse_error) if value is not None]
    validation_error = min(errors) if errors else None
    return {
        "ids": intended,
        "closest_pose": closest,
        "path_reconstruction_error_m": validation_error,
        "path_reconstruction_pass": validation_error is not None and validation_error <= 1e-4,
        "policy": policy or ("ORIGINAL" if mode == 0 else "NO_REPAIR"),
    }


def parse_keyscan_times(path):
    result = {}
    for match in KEYSCAN_RE.finditer(Path(path).read_text(encoding="utf-8", errors="replace")):
        result[int(match.group(2))] = float(match.group(3))
    return result


def prior_graph(run_dir):
    matches = sorted((run_dir / "author_outputs").glob("prior_map_*.pickle"))
    if len(matches) != 1:
        raise ValueError("expected one prior map in {}".format(run_dir))
    with matches[0].open("rb") as stream:
        return pickle.load(stream)


def formal_run_dirs(root):
    for seed_dir in sorted(root.glob("seed_*")):
        for method_dir in METHOD_DIRS:
            run_dir = seed_dir / method_dir
            if run_dir.is_dir():
                yield run_dir


def run_audit(phase4b_root, output_dir):
    rows = []
    total_events = 0
    path_checks = []
    active_events = 0
    for run_dir in formal_run_dirs(phase4b_root):
        manifest = load_json(run_dir / "manifest.json")
        loops = load_json(run_dir / "loops.json")["loops"]
        closures = load_json(run_dir / "closure_events.json")["events"]
        keyscan_times = parse_keyscan_times(run_dir / "rosout.log")
        prior = prior_graph(run_dir)
        reconstruction = {}
        for loop in loops:
            snapshot = load_json(run_dir / loop["snapshot_before"])
            item = reconstruct_intended_history(run_dir, loop, snapshot, prior, manifest)
            reconstruction[int(loop["loop_id"])] = item
            path_checks.append(item["path_reconstruction_pass"])

        for event in closures:
            total_events += 1
            current_scan = int(event["current_scan"])
            scan_time = keyscan_times.get(current_scan)
            matching = []
            if scan_time is not None:
                matching = [
                    loop for loop in loops
                    if loop.get("actual_start_time") is not None
                    and loop.get("actual_end_time") is not None
                    and float(loop["actual_start_time"]) <= scan_time <= float(loop["actual_end_time"])
                ]
            attribution = "PASSIVE_OR_UNRELATED"
            loop = matching[0] if len(matching) == 1 else None
            intended = None
            evidence = {
                "current_scan_time_source": "rosout PHASE2C_KEYSCAN_ACCEPTED",
                "callback_stamp": event.get("stamp"),
                "measurement_interval_matches": len(matching),
            }
            if loop is not None:
                active_events += 1
                item = reconstruction[int(loop["loop_id"])]
                intended = item["ids"]
                chain = set(range(int(event["chain_start"]), int(event["chain_end"]) + 1))
                overlap = sorted(chain.intersection(intended))
                evidence.update({
                    "intended_history_reconstruction": "frozen reliable-loop code replay",
                    "closest_pose": item["closest_pose"],
                    "execution_policy": item["policy"],
                    "matched_intended_ids": overlap,
                    "path_reconstruction_error_m": item["path_reconstruction_error_m"],
                    "path_reconstruction_pass": item["path_reconstruction_pass"],
                })
                if overlap and item["path_reconstruction_pass"]:
                    attribution = "TARGET_ATTRIBUTABLE"
                else:
                    attribution = "TEMPORALLY_ASSOCIATED"
            rows.append({
                "map": manifest["map"],
                "seed": manifest["seed"],
                "method": manifest["method"],
                "condition": manifest["condition"],
                "loop_id": loop.get("loop_id") if loop else "",
                "vertex": loop.get("loop_vertex") if loop else "",
                "event_seq": event["seq"],
                "current_scan": current_scan,
                "current_scan_time": scan_time if scan_time is not None else "",
                "chain_start": event["chain_start"],
                "chain_end": event["chain_end"],
                "active_start": loop.get("actual_start_time") if loop else "",
                "active_end": loop.get("actual_end_time") if loop else "",
                "intended_history_ids_or_region": json.dumps(intended) if intended is not None else "",
                "attribution_class": attribution,
                "evidence": json.dumps(evidence, sort_keys=True),
                "run_dir": str(run_dir),
            })

    output_dir.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with (output_dir / "phase4b_event_attribution.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    counts = {name: sum(row["attribution_class"] == name for row in rows) for name in (
        "TARGET_ATTRIBUTABLE", "TEMPORALLY_ASSOCIATED", "PASSIVE_OR_UNRELATED"
    )}
    coverage = {
        "formal_runs": 15,
        "accepted_events": total_events,
        "events_with_current_scan_acquisition_time": sum(row["current_scan_time"] != "" for row in rows),
        "events_measurement_timed_inside_exactly_one_active_interval": active_events,
        "active_events_with_reconstructed_intended_history": sum(
            bool(row["intended_history_ids_or_region"]) for row in rows
        ),
        "planned_path_reconstruction_checks": len(path_checks),
        "planned_path_reconstruction_passes": sum(path_checks),
        "classification_counts": counts,
        "phase4b_strong_attribution_compatible": (
            total_events > 0
            and all(row["current_scan_time"] != "" for row in rows)
            and all(path_checks)
        ),
    }
    (output_dir / "attribution_coverage.json").write_text(
        json.dumps(coverage, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    definition = {
        "version": "phase4c0-v1",
        "primary": "TARGET_ATTRIBUTABLE",
        "TARGET_ATTRIBUTABLE": (
            "current Karto keyscan acquisition timestamp lies in exactly one active-loop execution "
            "interval AND the accepted historical chain has at least one exact scan-id overlap with "
            "the history ids reconstructed from the frozen reliable-loop selection"
        ),
        "TEMPORALLY_ASSOCIATED": (
            "current Karto keyscan acquisition timestamp lies in exactly one active-loop interval, "
            "but exact intended-history overlap is absent or cannot be established"
        ),
        "PASSIVE_OR_UNRELATED": (
            "current Karto keyscan acquisition timestamp does not lie in exactly one active-loop interval"
        ),
        "callback_grace_period_s": None,
        "spatial_threshold_m": None,
        "notes": [
            "Classification follows scan acquisition and history identity, not callback arrival alone.",
            "The intended-id replay mirrors oracle modes 0/1/2 at the frozen Phase 4B parameters.",
            "The 4.0 m gate remains a configuration-inspired lightweight prototype proxy.",
        ],
    }
    (output_dir / "attribution_definition.json").write_text(
        json.dumps(definition, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return coverage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase4b-root", type=Path, default=Path("results/phase4b/map3"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/phase4c0/attribution"))
    args = parser.parse_args()
    print(json.dumps(run_audit(args.phase4b_root, args.output_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
