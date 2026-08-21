#!/usr/bin/python3
"""Evaluate one planar SLAM trajectory with a pinned workspace-local evo.

The canonical evaluation intentionally applies no post-hoc trajectory alignment:
Stage ground truth and Karto estimates are already expressed in the same map
frame.  Association uses nearest timestamps with a fixed 0.05 s gate.
"""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVO_SITE = ROOT / "evaluation" / "evo-1.31.1-target" / "site-packages"
EVO_VERSION = "1.31.1"
RMSE_RE = re.compile(r"^\s*rmse\s+([0-9eE+.-]+)\s*$", re.MULTILINE)


def run_metric(module, relation, gt, slam, output_dir, stem, t_start=None, t_end=None):
    command = [
        "/usr/bin/python3", "-m", module, "tum", str(gt.resolve()), str(slam.resolve()),
        "-r", relation, "--project_to_plane", "xy",
        "--t_max_diff", "0.05", "--t_offset", "0", "--no_warnings",
    ]
    if module == "evo.main_rpe":
        command.extend(["-d", "1", "-u", "m", "--all_pairs", "--pairs_from_reference"])
    if t_start is not None:
        command.extend(["--t_start", "{:.9f}".format(float(t_start))])
    if t_end is not None:
        command.extend(["--t_end", "{:.9f}".format(float(t_end))])
    archive = output_dir / (stem + ".zip")
    command.extend(["--save_results", str(archive.resolve())])

    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(EVO_SITE) + ((":" + existing) if existing else "")
    reproducible_command = "env PYTHONPATH={} {}".format(
        shlex.quote(str(EVO_SITE)), shlex.join(command)
    )
    completed = subprocess.run(command, text=True, capture_output=True, env=env)
    text = completed.stdout + completed.stderr
    (output_dir / (stem + ".txt")).write_text(text, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError("metric command failed: {}\n{}".format(shlex.join(command), text))
    match = RMSE_RE.search(text)
    if not match:
        raise RuntimeError("could not parse RMSE from {}".format(stem))
    return {
        "rmse": float(match.group(1)),
        "command": reproducible_command,
        "stdout_stderr": stem + ".txt",
        "result_archive": stem + ".zip",
    }


def evaluate_set(gt, slam, output_dir, prefix="", t_start=None, t_end=None):
    stem_prefix = (prefix + "_") if prefix else ""
    return {
        "ape_se2_translation_m": run_metric(
            "evo.main_ape", "trans_part", gt, slam, output_dir,
            stem_prefix + "ape_se2_translation", t_start, t_end
        ),
        "rpe_translation_1m_m": run_metric(
            "evo.main_rpe", "trans_part", gt, slam, output_dir,
            stem_prefix + "rpe_translation_1m", t_start, t_end
        ),
        "rpe_rotation_1m_deg": run_metric(
            "evo.main_rpe", "angle_deg", gt, slam, output_dir,
            stem_prefix + "rpe_rotation_1m", t_start, t_end
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gt", required=True, type=Path)
    parser.add_argument("--slam", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--loops-json", type=Path,
        help="Optional JSON list/object containing actual_start_time and actual_end_time"
    )
    args = parser.parse_args()

    if not args.gt.is_file() or not args.slam.is_file():
        raise SystemExit("GT and SLAM trajectory files must exist")
    if not EVO_SITE.is_dir():
        raise SystemExit("pinned evo environment is missing: {}".format(EVO_SITE))
    args.output_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "protocol": {
            "evo_version": EVO_VERSION,
            "python": "/usr/bin/python3 (3.8)",
            "trajectory_format": "TUM",
            "timestamp_association": "nearest timestamp, max difference 0.05 s, offset 0 s",
            "alignment": "none (identity; GT and Karto share the map frame)",
            "projection": "xy plane before metric evaluation",
            "ape": "translation-part RMSE on planar SE(2) poses, metres",
            "rpe_translation": "translation-part RMSE, all reference pairs at 1 m delta, metres",
            "rpe_rotation": "rotation-angle RMSE, all reference pairs at 1 m delta, degrees",
            "scale_correction": False,
        },
        "inputs": {"gt": str(args.gt.resolve()), "slam": str(args.slam.resolve())},
        "whole_run": evaluate_set(args.gt, args.slam, args.output_dir),
        "loops": [],
    }

    if args.loops_json:
        loop_data = json.loads(args.loops_json.read_text(encoding="utf-8"))
        loops = loop_data.get("loops", []) if isinstance(loop_data, dict) else loop_data
        for index, loop in enumerate(loops):
            loop_id = str(loop.get("loop_id", index + 1))
            before_t = loop.get("actual_start_time")
            after_t = loop.get("actual_end_time")
            entry = {"loop_id": loop_id, "actual_start_time": before_t, "actual_end_time": after_t}
            try:
                if before_t is None or after_t is None:
                    raise ValueError("missing actual loop boundaries")
                entry["cumulative_before"] = evaluate_set(
                    args.gt, args.slam, args.output_dir, "loop_{}_before".format(loop_id), t_end=before_t
                )
                entry["cumulative_after"] = evaluate_set(
                    args.gt, args.slam, args.output_dir, "loop_{}_after".format(loop_id), t_end=after_t
                )
            except (RuntimeError, ValueError) as exc:
                entry["status"] = "INCONCLUSIVE"
                entry["reason"] = str(exc)
            else:
                entry["status"] = "COMPUTED"
            result["loops"].append(entry)

    (args.output_dir / "metrics.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    commands = []
    for metric in result["whole_run"].values():
        commands.append(metric["command"])
    (args.output_dir / "commands.txt").write_text("\n".join(commands) + "\n", encoding="utf-8")
    print(json.dumps(result["whole_run"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
