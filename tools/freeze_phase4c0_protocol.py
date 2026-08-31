#!/usr/bin/env python3
"""Generate the machine-readable Phase 4C protocol and statistics freeze."""

import csv
import hashlib
import json
import platform
import subprocess
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
PHASE4B = ROOT / "results/phase4b/map3"
ATTRIBUTION = ROOT / "results/phase4c0/attribution_neutrality/phase4b_neutral_attribution.csv"
STATS_DIR = ROOT / "results/phase4c0/statistics"
PROTOCOL_DIR = ROOT / "results/phase4c0/protocol"
METHODS = {
    "A": {"name": "Original", "oracle_mode": 0},
    "B": {"name": "Always-Trace", "oracle_mode": 1},
    "C": {"name": "Selective", "oracle_mode": 2},
}
ORDERS = {
    21001: ("A", "B", "C"), 21002: ("B", "C", "A"),
    21003: ("C", "A", "B"), 21004: ("A", "C", "B"),
    21005: ("B", "A", "C"),
}
MAPS = {
    "map3": {
        "role": "M1_existing_Phase4B", "map_name": "map3/map3",
        "stage_start_pose": [-28.0, -28.0, 0.0], "map_width_m": 74.0,
    },
    "map4": {
        "role": "M2_new", "map_name": "map4/map4",
        "stage_start_pose": [-17.9, -26.35, 0.0], "map_width_m": 39.8,
    },
    "map7": {
        "role": "M3_new", "map_name": "map7/map7",
        "stage_start_pose": [-55.0, -20.0, 0.0], "map_width_m": 138.2,
    },
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def stats(values):
    values = np.asarray(values, dtype=float)
    return {
        "n": int(values.size), "mean": float(np.mean(values)),
        "median": float(np.median(values)), "min": float(np.min(values)),
        "max": float(np.max(values)),
    }


def strong_attribution_table():
    with ATTRIBUTION.open(newline="", encoding="utf-8") as stream:
        events = list(csv.DictReader(stream))
    targets = {}
    for event in events:
        if event["attribution_class"] == "TARGET_ATTRIBUTABLE":
            key = (int(event["seed"]), event["condition"])
            targets.setdefault(key, set()).add(int(event["loop_id"]))
    with (PHASE4B / "aggregate/run_table.csv").open(newline="", encoding="utf-8") as stream:
        runs = list(csv.DictReader(stream))
    rows = []
    for run in runs:
        seed, condition = int(run["seed"]), run["condition"]
        executed = int(run["executed_active_loops"])
        accepted = len(targets.get((seed, condition), set()))
        rows.append({
            "map": "map3", "seed": seed, "condition": condition,
            "method": run["method"], "executed_active_loops": executed,
            "target_attributable_active_loops": accepted,
            "target_attributable_acceptance_rate": accepted / executed if executed else None,
        })
    path = STATS_DIR / "phase4b_strong_attribution_by_seed.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    return rows


def attribution_summary(rows):
    per_method = {}
    for condition in METHODS:
        selected = [row for row in rows if row["condition"] == condition]
        numerator = sum(row["target_attributable_active_loops"] for row in selected)
        denominator = sum(row["executed_active_loops"] for row in selected)
        per_method[condition] = {
            "target_loops": numerator, "executed_loops": denominator,
            "pooled_rate_descriptive": numerator / denominator,
            "seed_rate": stats([row["target_attributable_acceptance_rate"] for row in selected]),
        }
    lookup = {(row["seed"], row["condition"]): row for row in rows}
    contrasts = {}
    for left, right in (("C", "A"), ("B", "A"), ("C", "B")):
        values = [
            lookup[(seed, left)]["target_attributable_acceptance_rate"]
            - lookup[(seed, right)]["target_attributable_acceptance_rate"]
            for seed in ORDERS
        ]
        contrasts["{}-{}".format(left, right)] = {
            **stats(values),
            "direction_count": {
                "positive": sum(value > 0 for value in values),
                "tie": sum(value == 0 for value in values),
                "negative": sum(value < 0 for value in values),
            },
        }
    return {"per_method": per_method, "paired_seed_contrasts": contrasts}


def run_matrix():
    rows = []
    for map_name in ("map4", "map7"):
        for seed, order in ORDERS.items():
            for order_index, condition in enumerate(order, start=1):
                rows.append({
                    "map": map_name, "seed": seed, "order_index": order_index,
                    "condition": condition, "method": METHODS[condition]["name"],
                    "oracle_mode": METHODS[condition]["oracle_mode"],
                    "tsp_seed": seed, "status": "NOT_STARTED",
                })
    path = PROTOCOL_DIR / "phase4c_run_matrix.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    return rows


def main():
    STATS_DIR.mkdir(parents=True, exist_ok=True)
    PROTOCOL_DIR.mkdir(parents=True, exist_ok=True)
    strong_rows = strong_attribution_table()
    strong_summary = attribution_summary(strong_rows)
    matrix = run_matrix()

    statistics = {
        "status": "FROZEN_BEFORE_M2_M3_PERFORMANCE_RUNS",
        "primary_paired_unit": "map-seed",
        "planned_paired_blocks": 15,
        "individual_loops_are_independent_inference_units": False,
        "strong_acceptance_rate": (
            "number of executed active-loop actions with at least one TARGET_ATTRIBUTABLE "
            "accepted constraint divided by executed active-loop actions"
        ),
        "rare_event_reporting": [
            "per-map raw numerator/denominator", "per-seed rates",
            "pooled rates as descriptive only", "paired map-seed differences",
            "mean median range and positive/tie/negative direction count",
        ],
        "optional_inference": [
            "paired exact randomization/permutation over map-seed blocks",
            "map-seed cluster bootstrap",
        ],
        "pooled_interval_warning": (
            "Wilson/Jeffreys intervals, if shown, are descriptive and do not account "
            "for within-seed dependence"
        ),
        "multiple_outcome_policy": (
            "outcome groups are reported separately; no post-hoc primary switching and "
            "no individual-loop pseudo-replication"
        ),
        "phase4b_strong_attribution_descriptive": strong_summary,
    }
    (STATS_DIR / "statistics_protocol.json").write_text(
        json.dumps(statistics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    tracked_sources = [
        "tools/audit_phase4c0_attribution.py", "tools/audit_phase4c05_neutrality.py",
        "tools/audit_phase4c05_opportunities.py", "tools/analyze_phase4c0_graph_impact.py",
        "tools/evaluate_mapping_v2.py", "tools/reanalyze_phase4b_mapping_v2.py",
        "tools/inventory_phase4c_maps.py", "tools/validate_phase4c0_mapping.py",
        "baseline/Graph-Based_SLAM-Aware_Exploration/scripts/path_planner.py",
        "dependencies/navigation_2d/nav2d_karto/OpenKarto/source/OpenMapper.cpp",
    ]
    protocol = {
        "phase": "4C", "status": "BLOCKED_OPPORTUNITY_ADEQUACY_NOT_STARTED",
        "scope": "2D LiDAR active SLAM for planar indoor ground robots",
        "selection_frozen_before_new_map_performance": True,
        "maps": MAPS, "new_formal_run_count": len(matrix),
        "publication_target_run_count_including_phase4b": 45,
        "conditions": METHODS, "only_scientific_variable": "oracle_mode",
        "formal_seeds": list(ORDERS),
        "counterbalanced_order": {str(seed): list(order) for seed, order in ORDERS.items()},
        "online_method": {
            "frozen_baseline_commit": git(ROOT / "baseline/Graph-Based_SLAM-Aware_Exploration", "rev-parse", "HEAD"),
            "navigation_commit": git(ROOT / "dependencies/navigation_2d", "rev-parse", "HEAD"),
            "configuration_inspired_proxy_m": 4.0,
            "repair_extension_budget": (
                "nominal 12m repair-extension budget with possible terminal-segment overshoot"
            ),
            "repair_waypoint_cap": 24, "repair_densification_m": 0.5,
            "diagnostics_enabled": False,
            "unchanged_components": [
                "repair decision", "direction selection", "early-stop logic", "prior graph",
                "TSP", "D-opt", "frontier logic", "Karto thresholds", "navigation settings",
            ],
        },
        "pairing": {
            "solver": "Concorde", "seed": "same as map-seed formal seed",
            "required_equal_fields_across_A_B_C": [
                "solver", "seed", "initial_tsp_path", "full_tsp_path",
                "predicted_tsp_length", "predicted_full_tsp_length",
            ],
            "mismatch_policy": "mark paired seed TECHNICAL_INVALID and stop; no automatic retry",
        },
        "attribution": {
            "primary": "TARGET_ATTRIBUTABLE",
            "current_measurement_rule": "current keyscan acquisition time lies in exactly one active interval",
            "history_identity_rule": (
                "accepted historical chain has non-empty overlap with H*: original baseline closest "
                "historical anchor plus exactly seven chronological pre-loop keyscans"
            ),
            "target_constructed_before_oracle_branch": True,
            "oracle_mode_used_to_construct_target": False,
            "target_cardinality": 7,
            "grace_period_s": None, "spatial_threshold_m": None,
        },
        "local_revisit_roi": {
            "centre": "method-neutral high-level prior-graph loop vertex position",
            "radius_m": 5.0,
            "execution_replay_or_repair_path_used": False,
        },
        "selection_sequence_protocol": {
            "required_fields_per_run": [
                "selected_loop_vertex_sequence", "selection_order", "selection_timestamp",
                "initial_tsp_hash", "full_tsp_hash",
            ],
            "paper_wording_if_sequences_equal": "loop targets matched",
            "paper_wording_if_sequences_differ": (
                "high-level selection algorithm/objective held fixed; do not claim all selected loops held fixed"
            ),
            "secondary_analysis_if_sequences_differ": "common selected-loop subset",
            "primary_analysis_unit": "map-seed",
        },
        "opportunity_adequacy": {
            "criterion": "each seed >=2 initial planned active loops and five-seed total >=10",
            "map4": {"counts": [1, 1, 1, 1, 1], "total": 5, "status": "FAIL"},
            "map7": {"counts": [1, 1, 1, 1, 1], "total": 5, "status": "FAIL"},
            "map8_next_candidate": {"counts": [3, 3, 3, 3, 3], "total": 15, "status": "PASS"},
            "formal_run_authorized": False,
            "blocking_reason": "only one remaining author map passes, but two adequate new maps are required",
        },
        "outcome_groups": {
            "loop_realization": ["target-attributable active-loop acceptance rate"],
            "execution_efficiency": ["active-loop distance_m", "active-loop time_s", "C-vs-B"],
            "pose_graph_impact_exploratory": [
                "accepted-edge final-graph ablation when edge is present",
                "continuous historical pose correction when compatible snapshots exist",
            ],
            "trajectory": ["SE2 APE RMSE m", "translational RPE RMSE m", "rotational RPE RMSE deg"],
            "mapping_primary": ["occupied boundary F1 at 0.20m", "symmetric boundary distance mean m"],
            "mapping_bridge_secondary": [
                "5m local boundary F1", "5m local symmetric boundary distance",
                "5m local observed coverage",
            ],
            "mapping_secondary": ["occupied IoU", "boundary distance median and p95"],
        },
        "repair_length_recording": [
            "nominal_budget", "actual_generated_length", "actual_executed_length"
        ],
        "validity_policy": {
            "technical_fault": "TECHNICAL_INVALID; preserve raw attempt and stop, no automatic retry",
            "navigation_or_exploration_failure": "retain as experimental outcome",
        },
        "source_freeze": {
            "generation_base_root_commit": git(ROOT, "rev-parse", "HEAD"),
            "branch": git(ROOT, "branch", "--show-current"),
            "file_sha256": {path: sha256(ROOT / path) for path in tracked_sources},
            "formal_preflight_requirement": "record clean final Phase4C-0 root HEAD and verify these file hashes",
            "offline_python": {
                "executable": "/home/wcqw/anaconda3/bin/python",
                "version": platform.python_version(),
                "invocation": (
                    "run in a clean shell or with PYTHONPATH unset; never inherit the catkin "
                    "Python 3.8 package path into Python 3.12"
                ),
            },
            "ros_python": "/usr/bin/python3 3.8",
        },
        "decision_rule": {
            "minimum_support": [
                "C has cross-map positive or non-inferior realization trend versus A",
                "C reduces blind revisit cost versus B on most or all maps",
                "no systematic pose-graph trajectory or map degradation",
            ],
            "case_1": "GENERALIZATION_SUPPORTED",
            "case_2": "REDESIGN_REALIZABILITY_GATE",
            "case_3": "REOPEN_EXECUTION_HYPOTHESIS",
            "case_4": "REASSESS_LOOP_UTILITY",
        },
        "formal_hypotheses": {
            "H1_realization_gap": "Original planner-selected loops often fail to become target-attributable constraints",
            "H2_execution_leverage": "blind stronger revisit can alter realization",
            "H3_selective_efficiency": "selective execution retains realization benefit while reducing revisit cost",
            "H4_supporting_non_degradation": "SLAM trajectory and local-map outcomes show no systematic degradation",
        },
        "efficiency_presentation": (
            "two-dimensional Pareto-style realization rate versus active-loop distance/time; "
            "no single closure-per-meter score"
        ),
    }
    (PROTOCOL_DIR / "phase4c_protocol.json").write_text(
        json.dumps(protocol, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": "BLOCKED_OPPORTUNITY_ADEQUACY_NOT_STARTED",
        "new_formal_runs": len(matrix),
        "maps": ["map4", "map7"], "primary_unit": "map-seed",
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
