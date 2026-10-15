"""One-time, read-only export of local research records. Never starts ROS."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = [
    "active_slam_topic_audit_20261014", "active_slam_ab_decision_20261014",
    "active_map_author_validation", "active_slam_feedback_probe_20261014",
    "active_slam_next_direction_20261014", "active_slam_b_final_qualification",
    "active_slam_anchor_selection_20261014", "active_slam_incremental_screen_20261014",
]


def select(path):
    parts = path.parts
    name = path.name.lower()
    if "__pycache__" in parts or ".git" in parts:
        return "cache_or_git_metadata"
    if parts[0] in ("sources", "code_snapshots", "catkin_ws", "frontier_build_ws"):
        return "third_party_cache_or_build_workspace"
    if path.suffix in (".bag", ".db", ".pdf", ".txt", ".html", ".response", ".jsonl",
                       ".pyc", ".so", ".o", ".npz", ".pgm", ".pickle", ".gz", ".zip"):
        return "raw_stream_binary_or_download_cache"
    if any(key in name for key in ("protection_before", "protected_before", "protected_pre", "workspace_before",
                                  "workspace_after", "manifest", "legacy_hashes", "receipts")):
        return "local_inventory_or_receipt_dump"
    if len(parts) == 1 and path.suffix in (".md", ".json"):
        return None
    if parts[0] in ("code", "scripts", "tests", "patches", "failures"):
        return None if path.suffix in (".py", ".cpp", ".h", ".sh", ".patch", ".md", ".json") else "not_selected_code_artifact"
    if parts[0] in ("protocol", "config"):
        return None if path.suffix in (".json", ".md", ".yaml", ".yml", ".world", ".png") else "not_selected_protocol_artifact"
    if parts[0] == "literature":
        return None if path.suffix in (".md", ".json", ".csv") else "literature_download_cache"
    if parts[0] == "audit":
        return None if path.suffix in (".json", ".md", ".csv") else "machine_log_or_command_dump"
    if parts[0] in ("results", "data", "analysis"):
        if name in ("trajectory.csv", "passive_estimates.json", "owned_processes.json", "collector.json", "decisions.json"):
            return "per_frame_or_process_detail"
        return None if path.suffix in (".json", ".csv", ".md", ".tsv") else "raw_or_unselected_result"
    if parts[0] == "figures" and path.suffix == ".png":
        return None
    return "outside_compact_archive_scope"


def main():
    target = ROOT / "snapshots"
    target.mkdir(exist_ok=False)
    records = []
    for name in NAMES:
        source = Path("/home/wcqw") / name
        assert source.is_dir(), source
        for item in sorted(source.rglob("*")):
            if not item.is_file() or item.is_symlink():
                continue
            rel = item.relative_to(source)
            payload = item.read_bytes()
            reason = select(rel)
            if reason is None and len(payload) > 262144:
                reason = "above_256KiB_compact_file_limit"
            row = {"source_root": name, "path": str(rel), "bytes": len(payload),
                   "sha256": hashlib.sha256(payload).hexdigest(), "included": reason is None}
            if reason:
                row["reason"] = reason
            else:
                dest = target / name / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(item, dest)
            records.append(row)
    included = [x for x in records if x["included"]]
    result = {"status": "BYTE_EXACT_SELECTED_SNAPSHOTS", "records": records,
              "included_files": len(included), "included_bytes": sum(x["bytes"] for x in included),
              "excluded_files": len(records) - len(included),
              "note": "Excluded originals remain local; this is not a standalone full experiment environment."}
    (ROOT / "publication/source_inventory.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != "records"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
