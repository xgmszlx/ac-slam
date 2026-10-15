"""Verify publication integrity and retained conclusions; no SLAM execution."""
import ast
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAP = ROOT / "snapshots"


def load(relative):
    return json.loads((SNAP / relative).read_text())


def main():
    inventory = json.loads((ROOT / "publication/source_inventory.json").read_text())
    selected = [x for x in inventory["records"] if x["included"]]
    for item in selected:
        p = SNAP / item["source_root"] / item["path"]
        assert hashlib.sha256(p.read_bytes()).hexdigest() == item["sha256"], p
    assert len(selected) == inventory["included_files"]
    actual = [p for p in SNAP.rglob("*") if p.is_file()]
    assert len(actual) == len(selected)

    ab = "active_slam_ab_decision_20261014/data/A_run01/"
    rows = list(csv.DictReader((SNAP / ab / "results.csv").open()))
    assert len(rows) == 150
    counts = Counter(r["policy"] for r in rows)
    successes = Counter(r["policy"] for r in rows if r["decision_correct"] == "True")
    summary = load(ab + "summary.json")
    for policy, data in summary.items():
        assert counts[policy] == data["n"] == 30
        assert successes[policy] == data["correct"]
        assert sum(int(r["false_update_cells"]) for r in rows if r["policy"] == policy) == data["false_update_cells"]

    b = "active_slam_b_final_qualification/"
    event_rows = list(csv.DictReader((SNAP / b / "results/old_283/scan_events.csv").open()))
    s = load(b + "results/old_283/summary.json")
    assert len(event_rows) == s["inputs"] == 283
    assert sum(r["strict_pair"] == "True" for r in event_rows) == s["strict_pairs"] == 199
    assert s["no_OdomInfo"] == 66 and len(s["map_TF_missing_with_output"]) == 18
    assert all(r["ICP_enter"] == "UNKNOWN" for r in event_rows)
    assert load(b + "results/final_core_regression/result.json")["pass_gate"] is False
    budget = load(b + "protocol/budget.json")
    assert budget["used"] == 0 and budget["attempts"] == []

    a = "active_map_author_validation/results/"
    assert load(a + "scientific_02_S1/evaluation.json")["map_final"]["false_update_cells"] == 1251
    assert load(a + "scientific_06_B1_S3/evaluation.json")["map_final"]["false_update_cells"] == 92
    assert load(a + "scientific_06_B1_S3/evaluation.json")["map_final"]["map_error_cells"] == 830

    baseline = load("active_slam_incremental_screen_20261014/audit/author_stop_baselines.json")
    assert [x["stop_false"] for x in baseline["results"]] == [23, 8, 5]
    assert all(x["stop_true"] + x["stop_false"] + x["no_stop"] == baseline["groups"] for x in baseline["results"])
    python_files = list(ROOT.rglob("*.py"))
    for p in python_files:
        ast.parse(p.read_text())
    result = {"status": "PASS", "byte_exact_snapshots": len(selected), "python_ast_files": len(python_files),
              "checks": ["150 toy outcomes match frozen summary", "283 scan table matches strict 199/283",
                         "Unknown internal ICP events remain unknown", "Core numerical regression remains FAIL",
                         "Unused final ROS budget remains zero", "Author-map and passive residual counts preserved",
                         "Strong simple stopping baseline retained"],
              "scope": "Archive integrity and evidence consistency only; no ROS, model inference, or scientific reproduction."}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
