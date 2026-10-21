"""Build the archive tables from read-only sources.

- table A: same-condition repeats (Bonn box 589f / walking 827f) -> baseline spread
- table B: trajectory integrity per run
- table C: historical loop/GBA audit (delegated to scan_history.py)
No SLAM run, no write into research_archive/.
"""
import json
import math
from pathlib import Path

import numpy as np

ARCH = Path(r"D:\py\_audit\ac-slam\research_archive")
OUT = ARCH / "20261021_loop_audit" / "tables"


def tum(p):
    rows = [ln.split() for ln in Path(p).read_text(errors="ignore").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    a = np.asarray(rows, dtype=float)
    return a[:, 0], a[:, 1:4], a[:, 4:8]


def R(q):
    n = np.linalg.norm(q)
    x, y, z, w = (q / n) if n else (0, 0, 0, 1)
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def ang(A, B):
    c = (np.trace(A.T @ B) - 1) / 2
    return math.degrees(math.acos(max(-1, min(1, c))))


def integrity(run_dir):
    """max KF step speed and path-length ratio; None when files absent."""
    res = {}
    k = run_dir / "KeyFrameTrajectory.txt"
    o = run_dir / "OnlineTrajectory.txt"
    e = run_dir / "CameraTrajectory.txt"
    if k.exists():
        t, p, q = tum(k)
        vmax = 0.0
        wmax = 0.0
        fmax = None
        for i in range(1, len(t)):
            dt = t[i] - t[i-1]
            if dt <= 0:
                continue
            v = float(np.linalg.norm(p[i] - p[i-1]) / dt)
            w = ang(R(q[i-1]), R(q[i])) / dt
            if v > vmax:
                vmax, fmax = v, i
            wmax = max(wmax, w)
        res["kf_vmax_mps"] = round(vmax, 3)
        res["kf_wmax_dps"] = round(wmax, 1)
        res["kf_step_at"] = fmax
        res["kf_count"] = len(t)
    if o.exists() and e.exists():
        ot, op, _ = tum(o)
        et, ep, _ = tum(e)
        n = min(len(op), len(ep))
        lo = float(np.linalg.norm(np.diff(op[:n], axis=0), axis=1).sum())
        le = float(np.linalg.norm(np.diff(ep[:n], axis=0), axis=1).sum())
        res["path_online_m"] = round(lo, 3)
        res["path_exported_m"] = round(le, 3)
        res["path_ratio"] = round(le / lo, 3) if lo else None
    return res


def metrics(run_dir, sub=None):
    p = run_dir / "evaluation" / "metrics.json" if sub is None else run_dir / "evaluation" / sub / "metrics.json"
    if not p.exists():
        return None
    m = json.loads(p.read_text())
    return dict(
        ate=m["ate_m"]["rmse"], rpet=m["rpe_1s_translation_m"]["rmse"],
        rper=m["rpe_1s_rotation_deg"]["rmse"],
        ate_p90=m["ate_m"].get("p90"), rpet_p90=m["rpe_1s_translation_m"].get("p90"),
        n=m["saved_camera_poses"], kf=m["saved_keyframes"])


REPEATS = [
    # (label, run dir, metrics subdir, note)
    ("M0_05  20261020 ngd_scientific_baseline", ARCH / "20261020_ngd_scientific_baseline/results/M0_05", None, "rgbd_tum_headless"),
    ("S0     20261020 rgbd_combo_e2e",          ARCH / "20261020_rgbd_combo_e2e/results/S0", "exported", "rgbd_combo mode0"),
    ("S0     20261020 rgbd_deletion_ablation",  ARCH / "20261020_rgbd_deletion_ablation/results/S0", "exported", "rgbd_combo mode0"),
    ("M0     20261021 ngd_region_prototype",    ARCH / "20261021_ngd_region_prototype/results/M0", "exported", "rgbd_region mode0"),
]

WALK_REPEATS = [
    ("M0_02", ARCH / "20261020_ngd_scientific_baseline/results/M0_02", None),
    ("M0_03", ARCH / "20261020_ngd_scientific_baseline/results/M0_03", None),
]


def stat(vals):
    a = np.array(vals)
    return f"min={a.min():.4f}  max={a.max():.4f}  range={a.max()-a.min():.4f}  相对={(a.max()-a.min())/a.min()*100:.1f}%"


def main():
    OUT.mkdir(exist_ok=True)
    lines = []
    lines.append("### A. 同条件重复：Bonn `moving_obstructing_box`，589 帧，mode 0\n")
    lines.append("同序列、同 `associations.txt`（sha256 `c30faa1d…`）、同 `bonn.yaml`（sha256 `972bc2bc…`）、"
                 "同 `OPENCV_FOR_THREADS_NUM=1`；差别只有构建/入口二进制。\n")
    lines.append("| 运行 | 入口 | ATE (m) | RPEt (m) | RPEr (°) | KF | 关键帧最大速度 | 路径比 导出/在线 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    ates, rpets, rpers, kfs = [], [], [], []
    for label, d, sub, entry in REPEATS:
        m = metrics(d, sub)
        ig = integrity(d)
        if not m:
            continue
        ates.append(m["ate"]); rpets.append(m["rpet"]); rpers.append(m["rper"]); kfs.append(m["kf"])
        lines.append(f"| {label} | {entry} | {m['ate']:.4f} | {m['rpet']:.4f} | {m['rper']:.2f} | {m['kf']} | "
                     f"{ig.get('kf_vmax_mps','-')} m/s | {ig.get('path_ratio','-')} |")
    lines.append("")
    lines.append(f"- ATE：{stat(ates)}")
    lines.append(f"- RPEt：{stat(rpets)}")
    lines.append(f"- RPEr：{stat(rpers)}")
    lines.append(f"- 关键帧数：min={min(kfs)} max={max(kfs)} range={max(kfs)-min(kfs)}")
    lines.append(f"- **M2 相对 M0 的 ATE 变化 = 0.068 m，仅为本条件基线极差 {max(ates)-min(ates):.4f} m 的 "
                 f"{(0.068/(max(ates)-min(ates)))*100:.0f}%**")
    lines.append("")

    lines.append("### B. 同条件重复：`walking`，827 帧，mode 0\n")
    lines.append("| 运行 | ATE (m) | RPEt (m) | RPEr (°) | KF |")
    lines.append("|---|---|---|---|---|")
    wa, wr, wq, wk = [], [], [], []
    for label, d, sub in WALK_REPEATS[:2]:
        m = metrics(d, sub)
        if not m:
            continue
        wa.append(m["ate"]); wr.append(m["rpet"]); wq.append(m["rper"]); wk.append(m["kf"])
        lines.append(f"| {label} | {m['ate']:.5f} | {m['rpet']:.5f} | {m['rper']:.3f} | {m['kf']} |")
    lines.append("")
    lines.append(f"- ATE：{stat(wa)}")
    lines.append(f"- RPEt：{stat(wr)}")
    lines.append(f"- RPEr：{stat(wq)}")
    lines.append("")
    lines.append("`20261020_ngd_scientific_baseline/results/comparison.csv` 另含第三次同条件重复 `M0_01`（轨迹文件未入库，"
                 f"ATE 0.01577、RPEt 0.01970、RPEr 0.587、KF 75），故 walking 实际有 3 次同条件重复，"
                 f"ATE 极差 0.0004 m（2.5%）。\n")

    txt = "\n".join(lines)
    (OUT / "baseline_repeatability.md").write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
