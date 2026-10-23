#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P7-A  ·  Pose evaluator (freezeable component A of the shared evaluator).

Scope: TUM/Bonn ground truth and estimated trajectories, time association, SE(3) or
Sim(3) alignment, ATE, windowed RPE (translational + rotational), coverage, and the
online-vs-final trajectory distinction.

Non-goals: map/dense evaluation (that is P7-B), and any notion of "better" -- this
module computes numbers under an explicitly declared convention and refuses to guess.

Conventions that are FROZEN here (changing any of them invalidates comparisons):
  * files are TUM format: "timestamp tx ty tz qx qy qz qw", seconds since epoch;
  * a row's pose is camera-to-world, i.e. p_world = R * p_cam + t;
  * alignment is applied to the ESTIMATE and never to the GT;
  * alignment scale is OFF by default (SE(3)). RGB-D/stereo must use SE(3);
    Sim(3) is opt-in and the report always states which was used;
  * RPE uses a TIME window (default 1.0 s), never a frame count, and never crosses a
    gap: if no pose is within `dt_tol` of t_i + window, that pair is skipped;
  * ATE is reported both with and without alignment, because "aligned ATE" can hide a
    constant offset that matters for a localisation system.

Bonn errata (from research_archive/20261021_ngd_bonn_frame_audit/ERRATA.md): Bonn raw
ground truth needs a camera-frame treatment that TUM does not. This module exposes
`bonn_camera_frame=True` which applies the documented rotation; it is NEVER applied to
TUM, and the report records which branch ran. The physical origin of the Bonn scale
factor remains UNKNOWN in the upstream archive and is not resolved here.
"""
import math

import numpy as np

BONN_CAM_FRAME = np.array([[0.0, -1.0, 0.0],
                           [0.0, 0.0, -1.0],
                           [1.0, 0.0, 0.0]])


# ---------------------------------------------------------------- io ----------
def load_tum(path):
    """Return dict(ts, xyz Nx3, quat Nx4 as xyzw). Empty rows are reported, not hidden."""
    ts, xyz, quat, bad = [], [], [], 0
    with open(path) as f:
        for ln, line in enumerate(f, 1):
            s = line.split()
            if not s or s[0].startswith('#'):
                continue
            if len(s) < 8:
                bad += 1
                continue
            try:
                ts.append(float(s[0]))
                xyz.append([float(s[1]), float(s[2]), float(s[3])])
                quat.append([float(s[4]), float(s[5]), float(s[6]), float(s[7])])
            except ValueError:
                bad += 1
    if not ts:
        raise ValueError('%s: no valid pose rows (malformed=%d)' % (path, bad))
    ts = np.asarray(ts); xyz = np.asarray(xyz); quat = np.asarray(quat)
    order = np.argsort(ts, kind='mergesort')
    return {'ts': ts[order], 'xyz': xyz[order], 'quat': quat[order],
            'malformed_rows': bad, 'path': path}


def quat_to_R(q):
    q = np.asarray(q, float)
    n = np.linalg.norm(q)
    if n == 0:
        raise ValueError('zero quaternion')
    x, y, z, w = q / n
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def R_to_quat(R):
    t = np.trace(R)
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        w = 0.25 * s; x = (R[2, 1] - R[1, 2]) / s; y = (R[0, 2] - R[2, 0]) / s; z = (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        w = (R[2, 1] - R[1, 2]) / s; x = 0.25 * s; y = (R[0, 1] + R[1, 0]) / s; z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        w = (R[0, 2] - R[2, 0]) / s; x = (R[0, 1] + R[1, 0]) / s; y = 0.25 * s; z = (R[1, 2] + R[2, 1]) / s
    else:
        s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        w = (R[1, 0] - R[0, 1]) / s; x = (R[0, 2] + R[2, 0]) / s; y = (R[1, 2] + R[2, 1]) / s; z = 0.25 * s
    return np.array([x, y, z, w])


def rot_angle(R):
    c = (np.trace(R) - 1.0) / 2.0
    return float(math.acos(max(-1.0, min(1.0, c))))


# ------------------------------------------------------- association ----------
def associate(gt, est, max_dt):
    """Nearest-in-time association est->gt. Returns index arrays and residuals."""
    gi, ei, dts = [], [], []
    j = 0
    for i, t in enumerate(est['ts']):
        if j >= len(gt['ts']):
            break
        while j + 1 < len(gt['ts']) and abs(gt['ts'][j + 1] - t) <= abs(gt['ts'][j] - t):
            j += 1
        dt = abs(gt['ts'][j] - t)
        if dt <= max_dt:
            gi.append(j); ei.append(i); dts.append(dt)
    return np.asarray(gi, int), np.asarray(ei, int), np.asarray(dts, float)


# ----------------------------------------------------------- alignment --------
def umeyama(src, dst, with_scale):
    """Least-squares R,t(,s) mapping src -> dst. Returns dict."""
    mu_s = src.mean(axis=0); mu_d = dst.mean(axis=0)
    S = src - mu_s; D = dst - mu_d
    C = D.T.dot(S) / len(src)
    U, sv, Vt = np.linalg.svd(C)
    Dm = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        Dm[2, 2] = -1.0
    R = U.dot(Dm).dot(Vt)
    if with_scale:
        var_s = (S * S).sum() / len(src)
        s = float(np.trace(np.diag(sv).dot(Dm)) / var_s) if var_s > 0 else 1.0
    else:
        s = 1.0
    t = mu_d - s * R.dot(mu_s)
    return {'R': R, 't': t, 's': s}


def apply_sim3(P, align):
    return align['s'] * P.dot(align['R'].T) + align['t']


# ---------------------------------------------------------------- metrics -----
def ate(gt_xyz, est_xyz, align_on, with_scale):
    if align_on:
        A = umeyama(est_xyz, gt_xyz, with_scale)
        E = apply_sim3(est_xyz, A)
    else:
        A = {'R': np.eye(3), 't': np.zeros(3), 's': 1.0}
        E = est_xyz.copy()
    e = np.linalg.norm(E - gt_xyz, axis=1)
    return {'rmse': float(np.sqrt((e ** 2).mean())),
            'mean': float(e.mean()), 'median': float(np.median(e)),
            'max': float(e.max()), 'align': A, 'errors': e}


def rpe(gt_ts, gt_R, gt_t, est_R, est_t, window, dt_tol):
    """Windowed relative pose error. Pairs are (i, j) with t_j - t_i ~ window.

    Pairs whose time gap is not within dt_tol are SKIPPED and counted, so a deletion
    in the middle of a trajectory cannot silently produce a long-baseline RPE.
    """
    te, re = [], []
    n = len(gt_ts)
    used = 0; skipped = 0
    for i in range(n):
        target = gt_ts[i] + window
        # nearest j >= i+1 to the target time
        js = np.searchsorted(gt_ts, target)
        cands = [k for k in (js - 1, js, js + 1) if i + 1 <= k < n]
        if not cands:
            continue
        j = min(cands, key=lambda k: abs(gt_ts[k] - target))
        gap = gt_ts[j] - gt_ts[i]
        if abs(gap - window) > dt_tol:
            skipped += 1
            continue
        dR_gt = gt_R[i].T.dot(gt_R[j]);  dt_gt = gt_R[i].T.dot(gt_t[j] - gt_t[i])
        dR_es = est_R[i].T.dot(est_R[j]); dt_es = est_R[i].T.dot(est_t[j] - est_t[i])
        te.append(float(np.linalg.norm(dt_es - dt_gt)))
        re.append(rot_angle(dR_es.T.dot(dR_gt)))
        used += 1
    te = np.asarray(te); re = np.asarray(re)
    return {'window_s': window, 'dt_tol_s': dt_tol, 'n_pairs': int(used), 'n_skipped': int(skipped),
            'trans_rmse': float(np.sqrt((te ** 2).mean())) if used else None,
            'trans_median': float(np.median(te)) if used else None,
            'rot_rmse_deg': float(np.degrees(np.sqrt((re ** 2).mean()))) if used else None,
            'rot_median_deg': float(np.degrees(np.median(re))) if used else None}


def evaluate(gt_path, est_path, *, max_dt=0.02, window=1.0, dt_tol=0.1,
             with_scale=False, bonn_camera_frame=False, label=''):
    gt = load_tum(gt_path)
    est = load_tum(est_path)
    if bonn_camera_frame:
        for k in range(len(gt['quat'])):
            R = quat_to_R(gt['quat'][k]).dot(BONN_CAM_FRAME)
            gt['quat'][k] = R_to_quat(R)
    gi, ei, dts = associate(gt, est, max_dt)
    if len(gi) < 3:
        raise ValueError('%s: only %d associations within %.3fs -- refusing to report'
                         % (label or est_path, len(gi), max_dt))
    gR = np.array([quat_to_R(q) for q in gt['quat'][gi]])
    eR = np.array([quat_to_R(q) for q in est['quat'][ei]])
    gT = gt['xyz'][gi]; eT = est['xyz'][ei]
    a_al = ate(gT, eT, True, with_scale)
    a_raw = ate(gT, eT, False, with_scale)
    rep = {
        'label': label,
        'gt': {'path': gt_path, 'n': len(gt['ts']), 'span_s': float(gt['ts'][-1] - gt['ts'][0]),
               'malformed_rows': gt['malformed_rows']},
        'est': {'path': est_path, 'n': len(est['ts']), 'span_s': float(est['ts'][-1] - est['ts'][0]),
                'malformed_rows': est['malformed_rows']},
        'association': {'max_dt_s': max_dt, 'n_pairs': int(len(gi)),
                        # coverage_est: how much of the ESTIMATE found GT
                        'coverage_est': float(len(gi) / len(est['ts'])),
                        # coverage_gt: how much of the GT the estimate covers. A deleted
                        # stretch shows up here, not in coverage_est (a subset of GT times
                        # matches perfectly, so coverage_est stays 1.0 -- that trap is why
                        # both directions are reported).
                        'coverage_gt': float(len(gi) / len(gt['ts'])),
                        'dt_median_s': float(np.median(dts)), 'dt_max_s': float(dts.max()),
                        'est_span_covered_s': float(est['ts'][-1] - est['ts'][0])},
        'ate_aligned': {'rmse': a_al['rmse'], 'median': a_al['median'], 'max': a_al['max'],
                        'scale_used': a_al['align']['s'], 'with_scale': with_scale},
        'ate_unaligned': {'rmse': a_raw['rmse'], 'median': a_raw['median'], 'max': a_raw['max']},
        'rpe': rpe(gt['ts'][gi], gR, gT, eR, eT, window, dt_tol),
        'options': {'with_scale': with_scale, 'bonn_camera_frame': bonn_camera_frame,
                    'window_s': window, 'align_applied_to': 'estimate only'},
    }
    return rep


def format_report(rep):
    L = []
    L.append('== %s ==' % (rep['label'] or '(unlabelled)'))
    L.append('  gt   n=%d span=%.1fs  est n=%d span=%.1fs' %
             (rep['gt']['n'], rep['gt']['span_s'], rep['est']['n'], rep['est']['span_s']))
    A = rep['association']
    L.append('  assoc n=%d coverage(est)=%.3f coverage(gt)=%.3f dt_med=%.1fms dt_max=%.1fms' %
             (A['n_pairs'], A['coverage_est'], A['coverage_gt'],
              A['dt_median_s'] * 1e3, A['dt_max_s'] * 1e3))
    L.append('  ATE aligned   rmse=%.4f median=%.4f max=%.4f m (scale=%.4f)' %
             (rep['ate_aligned']['rmse'], rep['ate_aligned']['median'],
              rep['ate_aligned']['max'], rep['ate_aligned']['scale_used']))
    L.append('  ATE unaligned rmse=%.4f median=%.4f max=%.4f m' %
             (rep['ate_unaligned']['rmse'], rep['ate_unaligned']['median'],
              rep['ate_unaligned']['max']))
    R = rep['rpe']
    L.append('  RPE(%gs) pairs=%d skipped=%d  trans_rmse=%s m  rot_rmse=%s deg' %
             (R['window_s'], R['n_pairs'], R['n_skipped'],
              'n/a' if R['trans_rmse'] is None else '%.4f' % R['trans_rmse'],
              'n/a' if R['rot_rmse_deg'] is None else '%.4f' % R['rot_rmse_deg']))
    return '\n'.join(L)
