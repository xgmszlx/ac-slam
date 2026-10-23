#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L1 G1 analysis: does a real 2D scan-matching system's own Hessian describe its error?

Frozen protocol: ../../protocol/PREREG.md (thresholds inherited verbatim from
research_archive/20261021_lidar_covariance_consistency/NEXT_MINIMAL_ACTION.md §3).

Usage:  python3 l1_g1_analysis.py <run_dir> <sequence>
Output: <run_dir>/summary.json, per_frame.csv, dropped_frames.csv, decision.json

Only numpy + rosbag are used. No scipy (not installed on this machine).
"""
import csv
import json
import math
import os
import sys

import numpy as np
import rosbag

# ---- frozen constants (PREREG §4) -------------------------------------------
DOF = 3
CHI2_3_P50 = 2.365974
CHI2_3_P99 = 11.344867
TAIL_REF = CHI2_3_P99 / CHI2_3_P50          # = 4.7959...  "R" denominator
N_ALIGN = 50                                 # PREREG §3.3
MAX_DT = 0.100  # SENSITIVITY ONLY
MIN_FRAMES = 200                             # PREREG §4
R_STRONG = 5.0                               # gate ① threshold
R_WEAK = 1.5                                 # gate 🔴 threshold
RHO_MIN = 0.3                                # gate ②(a)
QUINTILE_RATIO = 2.0                         # gate ②(b)
GT_PATH = '/home/wcqw/lilocbench_amcl_validation_20261016/data/gt/{seq}/gt_poses.txt'


# ---- geometry helpers ------------------------------------------------------
def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def q_to_yaw(x, y, z, w):
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def se2(theta, t):
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, -s, t[0]], [s, c, t[1]], [0.0, 0.0, 1.0]])


def compose(A, B):
    return A.dot(B)


def load_gt(path):
    ts, xs, ys, yaws = [], [], [], []
    with open(path) as f:
        for line in f:
            p = line.split()
            if len(p) < 8:
                continue
            ts.append(float(p[0]))
            xs.append(float(p[1]))
            ys.append(float(p[2]))
            yaws.append(q_to_yaw(float(p[4]), float(p[5]), float(p[6]), float(p[7])))
    return np.array(ts), np.array(xs), np.array(ys), np.array(yaws)


def gt_at(gt, t):
    """Nearest GT sample; return (x, y, yaw, |dt|) or None."""
    ts = gt[0]
    i = int(np.searchsorted(ts, t))
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(ts):
            dt = abs(ts[j] - t)
            if best is None or dt < best[3]:
                best = (gt[1][j], gt[2][j], gt[3][j], dt)
    return best


def umeyama_se2(gt_xy, h_xy):
    """Rigid SE(2) (no scale) mapping gt_xy -> h_xy, least squares."""
    mu_g = gt_xy.mean(axis=0)
    mu_h = h_xy.mean(axis=0)
    G = gt_xy - mu_g
    H = h_xy - mu_h
    C = H.T.dot(G) / len(gt_xy)
    U, S, Vt = np.linalg.svd(C)
    D = np.eye(2)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        D[1, 1] = -1.0
    R = U.dot(D).dot(Vt)
    t = mu_h - R.dot(mu_g)
    return R, t


def spearman(a, b):
    def rank(v):
        order = np.argsort(v, kind='mergesort')
        r = np.empty(len(v), dtype=float)
        r[order] = np.arange(len(v), dtype=float)
        # average ties
        sv = v[order]
        i = 0
        while i < len(sv):
            j = i
            while j + 1 < len(sv) and sv[j + 1] == sv[i]:
                j += 1
            if j > i:
                r[order[i:j + 1]] = (i + j) / 2.0
            i = j + 1
        return r
    ra, rb = rank(a), rank(b)
    ra = ra - ra.mean()
    rb = rb - rb.mean()
    den = math.sqrt(float((ra * ra).sum()) * float((rb * rb).sum()))
    return float((ra * rb).sum() / den) if den > 0 else float('nan')


# ---- main ------------------------------------------------------------------
def main():
    run_dir, seq = sys.argv[1], sys.argv[2]
    bag_path = os.path.join(run_dir, 'measure.bag')
    gt = load_gt(GT_PATH.format(seq=seq))

    poses, hess, dropped = [], [], []
    with rosbag.Bag(bag_path) as bag:
        per_scan = []  # kept in arrival order; poses and debug come from the same callback
        cur_pose = None
        n_pose = n_dbg = 0
        for topic, msg, _ in bag.read_messages(
                topics=['/slam_out_pose', '/hector_debug_info']):
            if topic == '/slam_out_pose':
                n_pose += 1
                cur_pose = (msg.header.stamp.to_sec(),
                            msg.pose.position.x, msg.pose.position.y,
                            q_to_yaw(msg.pose.orientation.x, msg.pose.orientation.y,
                                     msg.pose.orientation.z, msg.pose.orientation.w))
            else:
                n_dbg += 1
                if cur_pose is None or not msg.iterData:
                    dropped.append((n_dbg, 'no_pose_or_no_iter', ''))
                    continue
                H = np.array(msg.iterData[-1].hessian, dtype=float).reshape(3, 3)
                per_scan.append((cur_pose, H, n_dbg))
                cur_pose = None

    # ---- frame validity (PREREG §3.5) --------------------------------------
    valid = []
    for idx, (p, H, dbg_n) in enumerate(per_scan):
        if not np.all(np.isfinite(H)):
            dropped.append((idx, 'H_nonfinite', '')); continue
        if np.abs(H - H.T).max() > 1e-6:
            dropped.append((idx, 'H_asymmetric', '%.3g' % np.abs(H - H.T).max())); continue
        Hsym = 0.5 * (H + H.T)
        ev = np.linalg.eigvalsh(Hsym)
        if ev.min() <= 0:
            dropped.append((idx, 'H_not_PD', 'lmin=%.3g' % ev.min())); continue
        g = gt_at(gt, p[0])
        if g is None:
            dropped.append((idx, 'no_gt', '')); continue
        if g[3] > MAX_DT:
            dropped.append((idx, 'gt_dt', '%.4f' % g[3])); continue
        valid.append({'i': idx, 'stamp': p[0], 'hx': p[1], 'hy': p[2], 'hyaw': p[3],
                      'gx': g[0], 'gy': g[1], 'gyaw': g[2], 'dt': g[3], 'H': Hsym})

    if len(valid) < N_ALIGN + 10:
        json.dump({'status': 'INSUFFICIENT_FRAMES', 'valid': len(valid)},
                  open(os.path.join(run_dir, 'sensitivity_dt100_summary.json'), 'w'), indent=2)
        print('INSUFFICIENT_FRAMES', len(valid)); return

    # ---- frozen SE(2) alignment on first N_ALIGN valid frames (§3.3) -------
    al = valid[:N_ALIGN]
    gt_xy = np.array([[v['gx'], v['gy']] for v in al])
    h_xy = np.array([[v['hx'], v['hy']] for v in al])
    R, t = umeyama_se2(gt_xy, h_xy)

    rows, nees_all, sig_xy, err_xy = [], [], [], []
    for v in valid:
        alive = se2(v['gyaw'], (v['gx'], v['gy']))
        T = np.eye(3); T[:2, :2] = R; T[:2, 2] = t
        al_pose = compose(T, alive)
        ex = v['hx'] - al_pose[0, 2]
        ey = v['hy'] - al_pose[1, 2]
        eth = wrap(v['hyaw'] - math.atan2(al_pose[1, 0], al_pose[0, 0]))
        e = np.array([ex, ey, eth])
        H = v['H']
        nees = float(e.dot(H).dot(e))
        try:
            S = np.linalg.inv(H)
            s = math.sqrt(max(float(np.trace(S[:2, :2])), 0.0))
        except np.linalg.LinAlgError:
            S = None; s = float('nan')
        rows.append({'frame': v['i'], 'stamp': '%.6f' % v['stamp'],
                     'gt_dt': '%.6f' % v['dt'],
                     'ex': '%.8g' % ex, 'ey': '%.8g' % ey, 'eth': '%.8g' % eth,
                     'nees': '%.8g' % nees, 'sigma_xy': '%.8g' % s,
                     'err_xy': '%.8g' % math.hypot(ex, ey),
                     'cond': '%.6g' % float(np.linalg.cond(H))})
        if np.isfinite(nees) and np.isfinite(s):
            nees_all.append(nees); sig_xy.append(s); err_xy.append(math.hypot(ex, ey))

    nees = np.array(nees_all); sig = np.array(sig_xy); err = np.array(err_xy)
    n = len(nees)
    med = float(np.median(nees))
    p99 = float(np.quantile(nees, 0.99))
    R_tail = (p99 / med) / TAIL_REF if med > 0 else float('nan')

    # gate ②(a) rank correlation, ②(b) quintile ratio
    rho = spearman(sig, err)
    order = np.argsort(sig)
    k = max(1, n // 5)
    lo_err = float(err[order[:k]].mean())
    hi_err = float(err[order[-k:]].mean())
    ratio = hi_err / lo_err if lo_err > 0 else float('inf')

    g1 = bool(R_tail >= R_STRONG)
    g2a = bool(rho >= RHO_MIN)
    g2b = bool(ratio >= QUINTILE_RATIO)
    g2 = g1 and False  # placeholder, replaced below
    g2 = bool(g2a and g2b)

    if n < MIN_FRAMES:
        verdict = 'INCONCLUSIVE_TOO_FEW_FRAMES'
    elif g1 and g2:
        verdict = 'COVARIANCE_CANNOT_DESCRIBE_NOR_WARN'
    elif R_tail < R_WEAK and not g2:
        verdict = 'SIMPLIFIED_ICP_ARTIFACT'
    else:
        verdict = 'PARTIAL'

    summary = {
        'sequence': seq,
        'run_dir': run_dir,
        'system': 'hector_mapping (native Hessian from /hector_debug_info iterData[-1])',
        'n_valid_frames': n,
        'n_dropped': len(dropped),
        'gt_dt_median': float(np.median([v['dt'] for v in valid])),
        'alignment': {'n_align': N_ALIGN,
                      'yaw_deg': math.degrees(math.atan2(R[1, 0], R[0, 0])),
                      't': [float(t[0]), float(t[1])], 'scale_fitted': False},
        'nees_median': med, 'nees_p99': p99,
        'nees_mean': float(nees.mean()), 'nees_max': float(nees.max()),
        'nees_min': float(nees.min()),
        'tail_ratio_R': R_tail,
        'tail_ratio_ref': TAIL_REF,
        'u_p99': p99 / med if med > 0 else float('nan'),
        'spearman_sigma_vs_err': rho,
        'quintile_lo_err': lo_err, 'quintile_hi_err': hi_err,
        'quintile_ratio': ratio,
        'err_xy_median_m': float(np.median(err)),
        'err_xy_p99_m': float(np.quantile(err, 0.99)),
        'sigma_xy_median_m': float(np.median(sig)),
        'gate_1_tail': g1, 'gate_2a_rankcorr': g2a, 'gate_2b_quintile': g2b,
        'gate_2': g2,
        'verdict': verdict,
        'thresholds': {'R_strong': R_STRONG, 'R_weak': R_WEAK,
                       'rho_min': RHO_MIN, 'quintile_ratio': QUINTILE_RATIO,
                       'min_frames': MIN_FRAMES},
    }
    json.dump(summary, open(os.path.join(run_dir, 'sensitivity_dt100_summary.json'), 'w'), indent=2)

    with open(os.path.join(run_dir, 'sensitivity_dt100_per_frame.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    with open(os.path.join(run_dir, 'sensitivity_dt100_dropped_frames.csv'), 'w', newline='') as f:
        c = csv.writer(f); c.writerow(['frame_or_index', 'reason', 'detail']); c.writerows(dropped)

    print(json.dumps(summary, indent=2))
    print('\nverdict:', verdict)


if __name__ == '__main__':
    main()
