"""Historical loop/GBA + trajectory-integrity audit over every archived run.

Read-only. Scans research_archive/**/results/<run>/stdout.log and trajectories.
Emits CSV + markdown rows; no SLAM run, no file writes into archives.
"""
import csv
import json
import math
import os
import re
from pathlib import Path

import numpy as np

ROOT = Path(r"D:\py\_audit\ac-slam")
ARCH = ROOT / "research_archive"


def read_tum(p):
    if not p.exists():
        return None
    rows = [ln.split() for ln in p.read_text(errors="ignore").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    arr = np.asarray(rows, dtype=float)
    return arr[:, 0], arr[:, 1:4], arr[:, 4:8]


def quat_to_R(q):
    n = np.linalg.norm(q)
    x, y, z, w = (q / n) if n else (0, 0, 0, 1)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def ang(A, B):
    c = (np.trace(A.T @ B) - 1) / 2
    return math.degrees(math.acos(max(-1, min(1, c))))


def path_len(p):
    return float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum()) if len(p) > 1 else float("nan")


def scan():
    out = []
    for log in sorted(ARCH.rglob("results/*/stdout.log")):
        run_dir = log.parent
        text = log.read_text(errors="ignore")
        name = str(run_dir.relative_to(ARCH))
        frames = [int(m) for m in re.findall(r"^Frame (\d+) end", text, re.M)]
        loops = text.count("*Loop detected")
        merges = text.count("*Merge detected")
        stops = text.count("Local Mapping STOP")
        rels = text.count("Local Mapping RELEASE")
        gba_start = text.count("Starting Global Bundle Adjustment")
        gba_done = text.count("Global Bundle Adjustment finished")
        map_upd = text.count("Map updated!")
        shutdown = "Shutdown" in text
        # config: nearest ancestor config dir
        cfg_txt, loop_cfg = None, "UNKNOWN"
        for cand in run_dir.parents:
            cfg_dir = cand / "config"
            if cfg_dir.is_dir():
                hits = sorted(cfg_dir.glob("*.yaml"))
                if hits:
                    cfg_txt = "\n".join(h.read_text(errors="ignore") for h in hits)
                    m = re.search(r"^loopClosing:\s*(\S+)", cfg_txt, re.M)
                    loop_cfg = m.group(1) if m else "UNSET(default=1)"
                break
        o = read_tum(run_dir / "OnlineTrajectory.txt")
        e = read_tum(run_dir / "CameraTrajectory.txt")
        k = read_tum(run_dir / "KeyFrameTrajectory.txt")
        row = dict(run=name, frames=len(frames), last_frame=frames[-1] if frames else None,
                   loop_detected=loops, merge_detected=merges,
                   lm_stop=stops, lm_release=rels,
                   gba_started_log=gba_start, gba_finished_log=gba_done, map_updated_log=map_upd,
                   shutdown_logged=shutdown, loopClosing=loop_cfg,
                   has_online=o is not None, has_exported=e is not None, has_kf=k is not None)
        if o is not None and e is not None:
            n = min(len(o[0]), len(e[0]))
            dp = np.linalg.norm(e[1][:n] - o[1][:n], axis=1)
            dr = np.array([ang(quat_to_R(o[2][i]), quat_to_R(e[2][i])) for i in range(n)])
            row["on_exp_med_m"] = round(float(np.median(dp)), 4)
            row["on_exp_med_deg"] = round(float(np.median(dr)), 3)
            row["on_exp_max_m"] = round(float(dp.max()), 4)
            lo, le = path_len(o[1][:n]), path_len(e[1][:n])
            row["path_online_m"] = round(lo, 3)
            row["path_exported_m"] = round(le, 3)
            row["path_ratio"] = round(le / lo, 3) if lo else None
        else:
            for kk in ("on_exp_med_m", "on_exp_med_deg", "on_exp_max_m",
                       "path_online_m", "path_exported_m", "path_ratio"):
                row[kk] = None
        out.append(row)
    return out


if __name__ == "__main__":
    rows = scan()
    keys = list(rows[0].keys())
    csv_path = ARCH / "20261021_loop_audit" / "tables" / "historical_loop_gba_audit.csv"
    csv_path.parent.mkdir(exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(f"runs={len(rows)}  -> {csv_path}\n")
    hdr = f"{'run':<52}{'fr':>5}{'loop':>5}{'stp':>5}{'gba':>5}{'shut':>6}{'med_m':>8}{'med_deg':>8}{'ratio':>7}  loopClosing"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['run'][:52]:<52}{r['frames']:>5}{r['loop_detected']:>5}{r['lm_stop']:>5}"
              f"{r['gba_finished_log']:>5}{('Y' if r['shutdown_logged'] else 'N'):>6}"
              f"{(r['on_exp_med_m'] if r['on_exp_med_m'] is not None else -1):>8.4f}"
              f"{(r['on_exp_med_deg'] if r['on_exp_med_deg'] is not None else -1):>8.3f}"
              f"{(r['path_ratio'] if r['path_ratio'] is not None else -1):>7.3f}  {r['loopClosing']}")
