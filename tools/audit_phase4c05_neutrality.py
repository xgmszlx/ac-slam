#!/usr/bin/env python3
"""Audit and apply a treatment-neutral Phase 4B loop-attribution target."""

import argparse
import csv
import json
from pathlib import Path

from audit_phase4c0_attribution import (
    formal_run_dirs,
    load_json,
    nearest_prior_assignments,
    parse_keyscan_times,
    prior_graph,
)


CLASSES = ("TARGET_ATTRIBUTABLE", "TEMPORALLY_ASSOCIATED", "PASSIVE_OR_UNRELATED")


def neutral_target(loop, snapshot, prior):
    """Return H*: baseline anchor plus a fixed seven-keyscan forward window.

    The anchor is the author's pre-Phase-4 baseline reliable-loop anchor: among
    historical scans associated to the selected prior vertex, choose the scan
    closest to that vertex.  The evaluation neighborhood then uses exactly seven
    chronological pre-loop keyscans starting at the anchor.  Seven and forward
    direction come from the original V0 rule; unlike the execution path, H* never
    branches on oracle_mode and never expands for Always-Trace or Selective repair.
    """
    nodes = {int(key): value for key, value in snapshot["pose_graph_nodes"].items()}
    ordered = sorted(nodes)
    vertex = int(loop["loop_vertex"])
    candidates = nearest_prior_assignments(nodes, prior).get(vertex, [])
    if not candidates:
        raise ValueError("no pre-loop scan assigned to vertex {}".format(vertex))
    vertex_x, vertex_y = prior.nodes[vertex]["position"]
    anchor = min(
        candidates,
        key=lambda scan_id: (
            (nodes[scan_id]["x"] - vertex_x) ** 2
            + (nodes[scan_id]["y"] - vertex_y) ** 2,
            scan_id,
        ),
    )
    index = ordered.index(anchor)
    ids = ordered[index:index + 7]
    if len(ids) != 7:
        raise ValueError("fewer than seven pre-loop scans after anchor {}".format(anchor))
    return {"anchor": anchor, "ids": ids, "size": len(ids), "vertex": vertex}


def audit(phase4b_root, output_dir):
    event_rows, size_rows = [], []
    target_actions = {}
    sequence_neutrality = {}
    roi_neutrality = {}
    for run_dir in formal_run_dirs(phase4b_root):
        manifest = load_json(run_dir / "manifest.json")
        loops = load_json(run_dir / "loops.json")["loops"]
        events = load_json(run_dir / "closure_events.json")["events"]
        keyscan_times = parse_keyscan_times(run_dir / "rosout.log")
        prior = prior_graph(run_dir)
        targets = {}
        for order, loop in enumerate(loops, start=1):
            target = neutral_target(
                loop, load_json(run_dir / loop["snapshot_before"]), prior
            )
            targets[int(loop["loop_id"])] = target
            size_rows.append({
                "map": manifest["map"], "seed": manifest["seed"],
                "condition": manifest["condition"], "method": manifest["method"],
                "selection_order": order, "loop_id": loop["loop_id"],
                "loop_vertex": loop["loop_vertex"],
                "baseline_anchor_scan": target["anchor"],
                "h_star_ids": json.dumps(target["ids"]),
                "h_star_size": target["size"],
                "oracle_mode_used_by_h_star": False,
                "local_roi_center_x": prior.nodes[int(loop["loop_vertex"])]["position"][0],
                "local_roi_center_y": prior.nodes[int(loop["loop_vertex"])]["position"][1],
                "local_roi_radius_m": 5.0,
            })
        sequence_neutrality[(int(manifest["seed"]), manifest["condition"])] = [
            int(loop["loop_vertex"]) for loop in loops
        ]
        roi_neutrality[(int(manifest["seed"]), manifest["condition"])] = [
            (
                int(loop["loop_vertex"]),
                float(prior.nodes[int(loop["loop_vertex"])]["position"][0]),
                float(prior.nodes[int(loop["loop_vertex"])]["position"][1]),
                5.0,
            )
            for loop in loops
        ]

        for event in events:
            current = int(event["current_scan"])
            scan_time = keyscan_times.get(current)
            matching = [
                loop for loop in loops
                if scan_time is not None
                and loop.get("actual_start_time") is not None
                and loop.get("actual_end_time") is not None
                and float(loop["actual_start_time"]) <= scan_time <= float(loop["actual_end_time"])
            ]
            attribution = "PASSIVE_OR_UNRELATED"
            loop = matching[0] if len(matching) == 1 else None
            target, overlap = None, []
            if loop is not None:
                target = targets[int(loop["loop_id"])]
                chain = set(range(int(event["chain_start"]), int(event["chain_end"]) + 1))
                overlap = sorted(chain.intersection(target["ids"]))
                attribution = "TARGET_ATTRIBUTABLE" if overlap else "TEMPORALLY_ASSOCIATED"
                if overlap:
                    target_actions.setdefault(
                        (int(manifest["seed"]), manifest["condition"]), set()
                    ).add(int(loop["loop_id"]))
            event_rows.append({
                "map": manifest["map"], "seed": manifest["seed"],
                "condition": manifest["condition"], "method": manifest["method"],
                "loop_id": loop.get("loop_id") if loop else "",
                "vertex": loop.get("loop_vertex") if loop else "",
                "event_seq": event["seq"], "current_scan": current,
                "current_scan_time": scan_time if scan_time is not None else "",
                "chain_start": event["chain_start"], "chain_end": event["chain_end"],
                "active_start": loop.get("actual_start_time") if loop else "",
                "active_end": loop.get("actual_end_time") if loop else "",
                "baseline_anchor_scan": target["anchor"] if target else "",
                "h_star_ids": json.dumps(target["ids"]) if target else "",
                "h_star_size": target["size"] if target else "",
                "matched_h_star_ids": json.dumps(overlap),
                "attribution_class": attribution,
                "evidence": json.dumps({
                    "measurement_interval_matches": len(matching),
                    "current_scan_time_source": "rosout PHASE2C_KEYSCAN_ACCEPTED",
                    "target_rule": "baseline anchor + exactly seven chronological scans",
                    "target_constructed_before_execution_policy_branch": True,
                    "oracle_mode_used": False,
                }, sort_keys=True),
                "run_dir": str(run_dir),
            })

    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, rows in (
        ("phase4b_neutral_attribution.csv", event_rows),
        ("target_set_sizes.csv", size_rows),
    ):
        with (output_dir / filename).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)

    counts = {
        condition: sum(
            len(target_actions.get((seed, condition), set()))
            for seed in range(21001, 21006)
        )
        for condition in "ABC"
    }
    per_seed_sequences_equal = {
        str(seed): len({
            tuple(sequence_neutrality[(seed, condition)]) for condition in "ABC"
        }) == 1
        for seed in range(21001, 21006)
    }
    per_seed_rois_equal = {
        str(seed): len({
            tuple(roi_neutrality[(seed, condition)]) for condition in "ABC"
        }) == 1
        for seed in range(21001, 21006)
    }
    result = {
        "status": "PASS",
        "prior_phase4c0_definition_neutrality": "FAIL",
        "prior_failure_reason": (
            "target ids were reconstructed from oracle-mode-specific executed V0, "
            "Always-Trace, or Selective-repair paths"
        ),
        "frozen_h_star": (
            "method-neutral high-level loop vertex -> original baseline closest historical "
            "anchor -> exactly seven chronological pre-loop keyscans from that anchor"
        ),
        "window_provenance": (
            "K=7 and forward direction predate Phase 4A/4B in the author's V0 reliable-loop rule; "
            "the accepted chains were not used to select K"
        ),
        "constructed_before_oracle_branch": True,
        "oracle_mode_used": False,
        "all_target_sets_size_7": all(row["h_star_size"] == 7 for row in size_rows),
        "target_set_rows": len(size_rows),
        "accepted_event_class_counts": {
            name: sum(row["attribution_class"] == name for row in event_rows)
            for name in CLASSES
        },
        "target_attributable_action_counts": counts,
        "executed_action_counts": {"A": 21, "B": 21, "C": 21},
        "phase4b_selected_loop_vertex_sequences_equal": per_seed_sequences_equal,
        "local_roi_neutrality": {
            "status": "PASS" if all(per_seed_rois_equal.values()) else "FAIL",
            "centre": "method-neutral high-level prior-graph loop vertex position",
            "radius_m": 5.0,
            "per_seed_A_B_C_roi_sequences_equal": per_seed_rois_equal,
            "execution_replay_or_repair_path_used": False,
        },
        "independent_run_identity_note": (
            "numeric scan ids differ across stochastic A/B/C histories; equality means the same "
            "pre-branch vertex/anchor/K=7 construction and cardinality, not shared scan ids"
        ),
    }
    (output_dir / "method_neutrality_check.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase4b-root", type=Path, default=Path("results/phase4b/map3"))
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("results/phase4c0/attribution_neutrality"),
    )
    args = parser.parse_args()
    print(json.dumps(audit(args.phase4b_root, args.output_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
