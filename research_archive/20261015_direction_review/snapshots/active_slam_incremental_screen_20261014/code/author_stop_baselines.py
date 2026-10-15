"""Reorganize existing author predictions; no new inference or robot experiment."""
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources/completeness/Results/predictions_labelled_KTH+MIT_08.csv"


def summarize(groups, threshold, required):
    counts = {"stop_true": 0, "stop_false": 0, "no_stop": 0}
    for snapshots in groups.values():
        streak = 0
        outcome = "no_stop"
        for _, row in sorted(snapshots, key=lambda item: item[0]):
            streak = streak + 1 if float(row["prediction_EX"]) >= threshold else 0
            if streak >= required:
                # class_id is the prediction, not the ground-truth label.
                outcome = "stop_true" if row["type"] in ("TP", "FN") else "stop_false"
                break
        counts[outcome] += 1
    assert sum(counts.values()) == len(groups)
    return counts


def main():
    groups = defaultdict(list)
    rows = list(csv.DictReader(SOURCE.open()))
    identities = set()
    for row in rows:
        env, run, suffix = row["image_name"].rsplit("@", 2)
        assert suffix.endswith("Map.png"), suffix
        ordinal = float(suffix[:-len("Map.png")])
        identity = (env, run, ordinal)
        assert identity not in identities, identity
        identities.add(identity)
        assert row["type"] in ("TP", "TN", "FP", "FN")
        groups[(env, run)].append((ordinal, row))
    # A minimal parsing/control check, not a new model or full policy test.
    control = {("test", "run"): [(0, {"prediction_EX": ".9", "type": "FP"}),
                                   (1, {"prediction_EX": ".96", "type": "TP"})]}
    assert summarize(control, .8, 1)["stop_false"] == 1
    assert summarize(control, .8, 2)["stop_true"] == 1
    assert summarize(control, .99, 1)["no_stop"] == 1
    output = {
        "status": "PUBLIC_AUTHOR_OUTPUT_OFFLINE_AUDIT_ONLY",
        "source": str(SOURCE.relative_to(ROOT)), "rows": len(rows), "groups": len(groups),
        "results": [dict(threshold=t, adjacent_saved_snapshots=k, **summarize(groups, t, k))
                    for t, k in ((.8, 1), (.95, 1), (.8, 2))],
        "limitations": ["No model inference, simulator, or action counterfactual",
                        "Numeric filename order; actual timestamp units and intervening snapshots unknown",
                        "Ground truth inferred only from original TP/TN/FP/FN audit labels",
                        "Release cohort not certified identical to final paper evaluation",
                        "No runtime or movement cost established; no generalization conclusion"]}
    (ROOT / "audit/author_stop_baselines.json").write_text(json.dumps(output, indent=2))
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
