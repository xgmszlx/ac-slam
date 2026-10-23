#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P6 Stage 2: GT-pose dynamic RGB-D TSDF, A/B/C/D comparison with HELD-OUT evaluation.

Fixes the two Stage-1 defects flagged in review:
  F1  the report conflated RGB-Depth and RGB-GT residuals; they are now computed and
      reported separately, and neither is called "under 2 ms" as a whole.
  F2  the 1.7 cm residual was measured on the frames that built the map. Fusion and
      evaluation frames are now DISJOINT (even indices fuse, odd indices evaluate).

Method groups (same input, poses, intrinsics, voxel, truncation, environment):
  A  Raw            accept every valid depth pixel
  B  MaskHOG        reject pixels inside OpenCV HOG person detections
  C  GeomPrev       reject pixels inconsistent with the PREVIOUS frame's depth warped
                    into this camera using the GT relative pose (causal, no future frames)
  D  MapConfirm     reject pixels whose world voxel is not already occupied by past
                    accepted frames (repeated-observation requirement; warm-up K frames)

Evaluation on held-out frames only:
  * depth agreement: |z_map - z_obs| median / inlier fraction (NOT an absolute map
    accuracy claim; no independent reference cloud exists here)
  * coverage: fraction of valid observed pixels the map covers
  * FREE-SPACE VIOLATION rate: fraction of map points that land in front of the surface
    a held-out frame observed, i.e. in space that is observed empty. This is a
    reference-free dynamic-residue indicator. It is NOT an absolute ghost rate.

No dynamic ground-truth labels are used anywhere. C and D use only causal information.

Usage:
  python3 tsdf_stage2_ab.py <dataset_dir> <sequence> --fuse 300 --eval 60 --voxel 0.02
"""
import argparse
import json
import os
import resource
import sys
import time

import numpy as np
import cv2
import open3d as o3d

INTRINSICS = {
    'freiburg1': dict(fx=517.306504, fy=516.469215, cx=318.643040, cy=255.313989),
    'freiburg2': dict(fx=520.908620, fy=521.007327, cx=325.141442, cy=249.701764),
    'freiburg3': dict(fx=535.4, fy=539.2, cx=320.1, cy=247.6),
}
DEPTH_SCALE = 5000.0  # TUM RGB-D official: depth PNG is uint16 in 1/5000 m


def parse_index(p):
    ts, fs = [], []
    for line in open(p):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        s = line.split(); ts.append(float(s[0])); fs.append(s[1])
    return np.array(ts), fs


def parse_gt(p):
    rows = []
    for line in open(p):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        s = line.split()
        if len(s) >= 8:
            rows.append([float(x) for x in s[:8]])
    return np.array(rows)


def quat_to_R(qx, qy, qz, qw):
    n = qx * qx + qy * qy + qz * qz + qw * qw; s = 2.0 / n
    return np.array([
        [1 - s * (qy * qy + qz * qz), s * (qx * qy - qz * qw), s * (qx * qz + qy * qw)],
        [s * (qx * qy + qz * qw), 1 - s * (qx * qx + qz * qz), s * (qy * qz - qx * qw)],
        [s * (qx * qz - qy * qw), s * (qy * qz + qx * qw), 1 - s * (qx * qx + qy * qy)]])


def associate(a_ts, b_ts, max_dt):
    pairs, dts = [], []; j = 0
    for i, t in enumerate(a_ts):
        if j >= len(b_ts):
            break
        while j + 1 < len(b_ts) and abs(b_ts[j + 1] - t) <= abs(b_ts[j] - t):
            j += 1
        if abs(b_ts[j] - t) <= max_dt:
            pairs.append((i, j)); dts.append(abs(b_ts[j] - t))
    return pairs, dts


def pose_of(gt_row):
    T = np.eye(4); T[:3, :3] = quat_to_R(*gt_row[4:8]); T[:3, 3] = gt_row[1:4]
    return T


def backproject(depth_m, K):
    H, W = depth_m.shape
    uu, vv = np.meshgrid(np.arange(W), np.arange(H))
    z = depth_m; v = z > 0
    x = (uu[v] - K['cx']) * z[v] / K['fx']
    y = (vv[v] - K['cy']) * z[v] / K['fy']
    return np.stack([x, y, z[v]], axis=1), v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dataset_dir'); ap.add_argument('sequence')
    ap.add_argument('--fuse', type=int, default=300)
    ap.add_argument('--eval', type=int, default=60)
    ap.add_argument('--voxel', type=float, default=0.02)
    ap.add_argument('--trunc', type=float, default=4.0)
    ap.add_argument('--tau', type=float, default=0.05, help='geometric consistency threshold [m]')
    ap.add_argument('--warmup', type=int, default=5, help='frames accepted unconditionally by D')
    ap.add_argument('--hog-margin', type=float, default=0.25, help='fractional box expansion for B')
    ap.add_argument('--max-dt', type=float, default=0.02)
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    out = a.out or os.path.join('runs', 'p6_stage2_' + a.sequence)
    os.makedirs(out, exist_ok=True)
    D = a.dataset_dir

    rgb_ts, rgb_f = parse_index(os.path.join(D, 'rgb.txt'))
    dep_ts, dep_f = parse_index(os.path.join(D, 'depth.txt'))
    gt = parse_gt(os.path.join(D, 'groundtruth.txt'))
    rd, dt_rd = associate(rgb_ts, dep_ts, a.max_dt)      # rgb <-> depth
    rg, dt_rg = associate(rgb_ts, gt[:, 0], a.max_dt)    # rgb <-> gt
    gtmap = {}
    for i, j in rg:
        gtmap[i] = gt[j]

    fam = next((k for k in INTRINSICS if k in a.sequence), None)
    K = INTRINSICS[fam]
    probe = cv2.imread(os.path.join(D, dep_f[rd[0][1]]), cv2.IMREAD_UNCHANGED)
    H, W = probe.shape
    intr = o3d.camera.PinholeCameraIntrinsic(W, H, K['fx'], K['fy'], K['cx'], K['cy'])

    fused_pairs = [pr for pr in rd if (pr[0] % 2 == 0) and pr[0] in gtmap][:a.fuse]
    eval_pairs = [pr for pr in rd if (pr[0] % 2 == 1) and pr[0] in gtmap][:a.eval]

    # ---------------- HOG people detector (a real, traceable, independent mask source)
    hog = cv2.HOGDescriptor()
    hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def hog_mask(color_bgr):
        small = cv2.resize(color_bgr, (W // 2, H // 2))
        rects, weights = hog.detectMultiScale(small, winStride=(8, 8), padding=(8, 8), scale=1.05)
        m = np.zeros((H, W), np.uint8)
        for (x, y, w, h), wt in zip(rects, weights):
            if wt < 0.3:
                continue
            dx = int(w * a.hog_margin); dy = int(h * a.hog_margin)
            x0 = max(0, (x - dx) * 2); y0 = max(0, (y - dy) * 2)
            x1 = min(W, (x + w + dx) * 2); y1 = min(H, (y + h + dy) * 2)
            m[y0:y1, x0:x1] = 1
        return m, int(len(rects))

    def run_method(name):
        vol = o3d.pipelines.integration.ScalableTSDFVolume(
            voxel_length=a.voxel, sdf_trunc=4 * a.voxel,
            color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
        occupied = set()
        times, n_pix_kept, n_pix_total = [], 0, 0
        prev = None   # (depth_m, T_wc)
        hog_calls, hog_boxes = 0, 0
        for (i, j) in fused_pairs:
            t0 = time.time()
            color = cv2.imread(os.path.join(D, rgb_f[i]))
            dep = cv2.imread(os.path.join(D, dep_f[j]), cv2.IMREAD_UNCHANGED)
            if color is None or dep is None:
                continue
            z = dep.astype(np.float64) / DEPTH_SCALE
            z[z > a.trunc] = 0.0
            Twc = pose_of(gtmap[i])
            keep = z > 0
            n_pix_total += int(keep.sum())
            if name == 'B_MaskHOG':
                m, nb = hog_mask(color); hog_calls += 1; hog_boxes += nb
                keep &= (m == 0)
            elif name == 'C_GeomPrev' and prev is not None:
                pdepth, pTwc = prev
                T_rel = np.linalg.inv(pTwc) @ Twc                  # this <- prev
                Pc, _ = backproject(pdepth, K)
                Pw = (pTwc[:3, :3] @ Pc.T).T + pTwc[:3, 3]
                Pn = (T_rel[:3, :3] @ Pw.T).T + T_rel[:3, 3]
                uu = (K['fx'] * Pn[:, 0] / Pn[:, 2] + K['cx'])
                vv = (K['fy'] * Pn[:, 1] / Pn[:, 2] + K['cy'])
                zp = Pn[:, 2]
                ok = (zp > 0) & (uu >= 0) & (uu < W) & (vv >= 0) & (vv < H)
                zpred = np.full((H, W), np.nan)
                zpred[vv[ok].astype(int), uu[ok].astype(int)] = zp[ok]
                has = np.isfinite(zpred)
                inconsistent = has & (np.abs(z - np.nan_to_num(zpred)) > a.tau)
                keep &= ~inconsistent
            elif name == 'D_MapConfirm' and len(times) >= a.warmup:
                Pc, _ = backproject(np.where(keep, z, 0.0), K)
                Pw = (Twc[:3, :3] @ Pc.T).T + Twc[:3, 3]
                keys = np.floor(Pw / a.voxel).astype(np.int64)
                kk = set(map(tuple, keys.tolist()))
                # accept only if the pixel's voxel was already occupied
                idx_world = np.zeros((H, W), bool)
                uv, _ = backproject(np.where(keep, z, 0.0), K)
                idx_world[backproject(np.where(keep, z, 0.0), K)[1]] = [
                    (tuple(int(c) for c in np.floor(p / a.voxel))) in occupied for p in Pw]
                keep &= idx_world
            n_pix_kept += int(keep.sum())
            zmasked = np.where(keep, z, 0.0)
            rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
                o3d.geometry.Image(np.ascontiguousarray(color[:, :, ::-1])),
                o3d.geometry.Image(np.ascontiguousarray((zmasked * DEPTH_SCALE).astype(np.uint16))),
                depth_scale=DEPTH_SCALE, depth_trunc=a.trunc, convert_rgb_to_intensity=False)
            vol.integrate(rgbd, intr, np.linalg.inv(Twc))
            if name == 'D_MapConfirm':
                Pc2, _ = backproject(zmasked, K)
                Pw2 = (Twc[:3, :3] @ Pc2.T).T + Twc[:3, 3]
                occupied.update(map(tuple, np.floor(Pw2 / a.voxel).astype(np.int64).tolist()))
            prev = (z, Twc)
            times.append(time.time() - t0)
        pcd = vol.extract_point_cloud().voxel_down_sample(a.voxel)
        return pcd, times, n_pix_kept, n_pix_total, {'hog_calls': hog_calls, 'hog_boxes': hog_boxes}

    def evaluate(pcd):
        Pm = np.asarray(pcd.points)
        dz_all, cover_num, cover_den, viol_num, viol_den = [], 0, 0, 0, 0
        for (i, j) in eval_pairs:
            dep = cv2.imread(os.path.join(D, dep_f[j]), cv2.IMREAD_UNCHANGED)
            zobs = dep.astype(np.float64) / DEPTH_SCALE
            zobs[zobs > a.trunc] = 0.0
            Twc = pose_of(gtmap[i]); Tcw = np.linalg.inv(Twc)
            Pc = (Tcw[:3, :3] @ Pm.T).T + Tcw[:3, 3]
            front = Pc[:, 2] > 0.05
            if front.sum() == 0:
                continue
            uu = (K['fx'] * Pc[front, 0] / Pc[front, 2] + K['cx'])
            vv = (K['fy'] * Pc[front, 1] / Pc[front, 2] + K['cy'])
            zm = Pc[front, 2]
            inbox = (uu >= 0) & (uu < W) & (vv >= 0) & (vv < H)
            ui = uu[inbox].astype(int); vi = vv[inbox].astype(int); zi = zm[inbox]
            zo = zobs[vi, ui]
            seen = zo > 0
            if seen.sum():
                dz_all.append(np.abs(zi[seen] - zo[seen]))
            valid_px = zobs > 0
            proj = np.zeros((H, W), bool); proj[vi, ui] = True
            cover_num += int((valid_px & proj).sum()); cover_den += int(valid_px.sum())
            # free-space violation: map point clearly IN FRONT of observed surface
            vmask = seen & (zi < zo - 0.10)
            viol_num += int(vmask.sum()); viol_den += int(seen.sum())
        dz = np.concatenate(dz_all) if dz_all else np.array([])
        return {
            'n_eval_frames': len(eval_pairs),
            'depth_abs_residual_median_m': float(np.median(dz)) if len(dz) else None,
            'depth_abs_residual_p90_m': float(np.quantile(dz, 0.9)) if len(dz) else None,
            'depth_inlier_frac_5cm': float(np.mean(dz <= 0.05)) if len(dz) else None,
            'coverage_frac': (cover_num / cover_den) if cover_den else None,
            'free_space_violation_frac': (viol_num / viol_den) if viol_den else None,
            'note': ('free-space violation is a reference-free dynamic-residue indicator, '
                     'NOT an absolute ghost rate; no independent static reference cloud exists here'),
        }

    report = {'sequence': a.sequence, 'dataset_dir': D,
              'fusion_frames': len(fused_pairs), 'held_out_frames': len(eval_pairs),
              'disjoint_by_construction': 'even indices fuse, odd indices evaluate',
              'timing': {'rgb_depth_dt_median_ms': float(np.median(dt_rd) * 1000) if dt_rd else None,
                         'rgb_gt_dt_median_ms': float(np.median(dt_rg) * 1000) if dt_rg else None,
                         'rgb_gt_dt_p99_ms': float(np.quantile(dt_rg, 0.99) * 1000) if dt_rg else None,
                         'association_window_ms': a.max_dt * 1000,
                         'note': 'rgb-depth and rgb-gt are reported separately (Stage-1 defect F1)'},
              'params': {'voxel': a.voxel, 'sdf_trunc_voxels': 4, 'depth_trunc_m': a.trunc,
                         'geom_tau_m': a.tau, 'warmup_frames': a.warmup,
                         'depth_scale': DEPTH_SCALE,
                         'depth_scale_source': 'TUM RGB-D official format (uint16, 1/5000 m)'},
              'methods': {}}
    for name in ('A_Raw', 'B_MaskHOG', 'C_GeomPrev', 'D_MapConfirm'):
        t0 = time.time()
        pcd, times, kept, tot, extra = run_method(name)
        el = time.time() - t0
        ply = os.path.join(out, 'map_%s.ply' % name)
        o3d.io.write_point_cloud(ply, pcd)
        ev = evaluate(pcd)
        report['methods'][name] = {
            'n_points': int(len(np.asarray(pcd.points))),
            'pixels_kept_frac': (kept / tot) if tot else None,
            'fusion_time_median_ms': float(np.median(times) * 1000) if times else None,
            'fusion_time_p95_ms': float(np.quantile(times, 0.95) * 1000) if times else None,
            'wall_s': el,
            'peak_rss_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0,
            'eval': ev, 'extra': extra}
        print('%-12s pts=%6d kept=%.3f fuse_med=%6.1fms depth_resid=%s viol=%s' % (
            name, report['methods'][name]['n_points'],
            report['methods'][name]['pixels_kept_frac'] or 0,
            report['methods'][name]['fusion_time_median_ms'] or 0,
            None if ev['depth_abs_residual_median_m'] is None else round(ev['depth_abs_residual_median_m'], 4),
            None if ev['free_space_violation_frac'] is None else round(ev['free_space_violation_frac'], 4)),
            flush=True)
    json.dump(report, open(os.path.join(out, 'stage2_report.json'), 'w'), indent=2)
    print('\nwrote', os.path.join(out, 'stage2_report.json'))


if __name__ == '__main__':
    main()
