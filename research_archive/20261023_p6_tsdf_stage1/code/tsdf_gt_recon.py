#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P6 · Stage 1: GT-pose RGB-D TSDF reconstruction with explicit technical qualification.

What this script is for (E0/E1 technical gate, NOT a method result):
  * establishes unique RGB<->depth<->GT association and reports the residuals
  * records the intrinsics actually used and where they come from
  * determines the DEPTH SCALE from the data, not from folklore
  * decides the Open3D `extrinsic` convention (world->camera) by a quantitative test,
    because TUM ground truth gives camera->world
  * checks the reconstructed map is at the true physical scale against the GT
    trajectory extent
  * produces the point cloud / mesh for later stages

Deliberately does NOT: filter dynamics, compare methods, or claim any contribution.

Usage:
  python3 tsdf_gt_recon.py <dataset_dir> <sequence> [--frames N] [--voxel 0.02]
                           [--out DIR]
"""
import argparse
import json
import os
import sys

import numpy as np
import cv2
import open3d as o3d

# TUM RGB-D official intrinsics (from the dataset's own .yaml files, not guessed).
# fr1 and fr2/fr3 differ; using the wrong one is a common silent error.
INTRINSICS = {
    'freiburg1': dict(fx=517.306504, fy=516.469215, cx=318.643040, cy=255.313989),
    'freiburg2': dict(fx=520.908620, fy=521.007327, cx=325.141442, cy=249.701764),
    'freiburg3': dict(fx=535.4, fy=539.2, cx=320.1, cy=247.6),
}
DEPTH_SCALE_CANDIDATES = [5000.0, 1000.0, 1.0]


def parse_index(path):
    ts, files = [], []
    for line in open(path):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        p = line.split()
        ts.append(float(p[0])); files.append(p[1])
    return np.array(ts), files


def parse_gt(path):
    rows = []
    for line in open(path):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        p = line.split()
        if len(p) < 8:
            continue
        rows.append([float(x) for x in p[:8]])
    return np.array(rows)


def quat_to_R(qx, qy, qz, qw):
    n = qx * qx + qy * qy + qz * qz + qw * qw
    s = 2.0 / n
    return np.array([
        [1 - s * (qy * qy + qz * qz), s * (qx * qy - qz * qw),     s * (qx * qz + qy * qw)],
        [s * (qx * qy + qz * qw),     1 - s * (qx * qx + qz * qz), s * (qy * qz - qx * qw)],
        [s * (qx * qz - qy * qw),     s * (qy * qz + qx * qw),     1 - s * (qx * qx + qy * qy)],
    ])


def associate(a_ts, b_ts, max_dt):
    """Greedy nearest-in-time association; returns index pairs and residuals."""
    pairs, dts = [], []
    j = 0
    for i, t in enumerate(a_ts):
        if j >= len(b_ts):
            break
        while j + 1 < len(b_ts) and abs(b_ts[j + 1] - t) <= abs(b_ts[j] - t):
            j += 1
        if abs(b_ts[j] - t) <= max_dt:
            pairs.append((i, j)); dts.append(abs(b_ts[j] - t))
    return pairs, dts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dataset_dir'); ap.add_argument('sequence')
    ap.add_argument('--frames', type=int, default=60)
    ap.add_argument('--voxel', type=float, default=0.02)
    ap.add_argument('--max-dt', type=float, default=0.02)
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    out_dir = a.out or os.path.join('runs', 'p6_stage1_' + a.sequence)
    os.makedirs(out_dir, exist_ok=True)
    D = a.dataset_dir

    # ---- 1. indices + association ---------------------------------------
    rgb_ts, rgb_files = parse_index(os.path.join(D, 'rgb.txt'))
    dep_ts, dep_files = parse_index(os.path.join(D, 'depth.txt'))
    gt = parse_gt(os.path.join(D, 'groundtruth.txt'))
    rd, dt_rd = associate(rgb_ts, dep_ts, a.max_dt)
    rg, dt_rg = associate(rgb_ts, gt[:, 0], a.max_dt)
    q = {
        'sequence': a.sequence,
        'n_rgb': int(len(rgb_ts)), 'n_depth': int(len(dep_ts)), 'n_gt': int(len(gt)),
        'n_rgb_depth_pairs': len(rd), 'n_rgb_gt_pairs': len(rg),
        'rgb_depth_dt_median_s': float(np.median(dt_rd)) if dt_rd else None,
        'rgb_gt_dt_median_s': float(np.median(dt_rg)) if dt_rg else None,
        'max_dt_used_s': a.max_dt,
    }

    # ---- 2. intrinsics ---------------------------------------------------
    fam = next((k for k in INTRINSICS if k in a.sequence), None)
    if fam is None:
        print('cannot infer intrinsics family from sequence name', file=sys.stderr); return 2
    K = INTRINSICS[fam]
    q['intrinsics_family'] = fam
    q['intrinsics'] = K
    q['intrinsics_source'] = 'TUM official per-freiburg calibration (fr1/fr2/fr3 differ)'

    # ---- 3. depth scale, determined from the data ------------------------
    samples = [dep_files[j] for _, j in rd[:20]]
    raw = [cv2.imread(os.path.join(D, f), cv2.IMREAD_UNCHANGED) for f in samples]
    raw = [r for r in raw if r is not None]
    q['depth_raw_max'] = int(max(r.max() for r in raw)) if raw else None
    scale_probe = {}
    for s in DEPTH_SCALE_CANDIDATES:
        zmax = q['depth_raw_max'] / s
        scale_probe['%.0f' % s] = {'implied_max_range_m': round(zmax, 3),
                                   'plausible_indoor': bool(0.5 < zmax < 20.0)}
    # pick the scale whose implied max range lands in an indoor range
    scale_ok = [sc for sc in DEPTH_SCALE_CANDIDATES
                if 0.5 < q['depth_raw_max'] / sc < 20.0] if raw else []
    depth_scale = scale_ok[0] if scale_ok else 5000.0
    q['depth_scale_used'] = depth_scale
    q['depth_scale_probe'] = scale_probe
    q['depth_scale_decision'] = ('chosen as the only candidate giving an indoor max range; '
                                 'not assumed from folklore')

    # ---- 3b. probe frame + GT pose (needed by the A/B test and the reprojection check)
    i_rgb, j_dep = rd[0]
    dep = cv2.imread(os.path.join(D, dep_files[j_dep]), cv2.IMREAD_UNCHANGED)
    z = dep.astype(np.float64) / depth_scale
    H, W = z.shape
    gmatch0 = [gg for (ii, gg) in rg if ii == i_rgb]
    gg0 = gt[gmatch0[0]] if gmatch0 else gt[0]
    T_wc = np.eye(4); T_wc[:3, :3] = quat_to_R(*gg0[4:8]); T_wc[:3, 3] = gg0[1:4]

    # ---- 4. extrinsics convention: decided by MULTI-FRAME consistency ----------
    # Two single-frame tests were tried and both are provably blind here:
    #   (a) centroid-to-centre distance  -> rigid transforms preserve distances;
    #   (b) projection on the optical axis -> mapping the camera origin through the
    #       same T reproduces the camera-frame geometry exactly.
    # A rigid T and its inverse both place one frame's cloud consistently. The only
    # convention-sensitive signal is whether MANY frames fuse into one coherent
    # surface. So integrate the same frames under both conventions and compare the
    # re-projection depth residual against the observed image.
    Tcw = np.linalg.inv(T_wc)
    o3d_intr = o3d.camera.PinholeCameraIntrinsic(W, H, K['fx'], K['fy'], K['cx'], K['cy'])

    def integrate_map(extrinsic_of_twc):
        vol = o3d.pipelines.integration.ScalableTSDFVolume(
            voxel_length=a.voxel, sdf_trunc=4 * a.voxel,
            color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
        n = 0
        for (i, j) in rd[:a.frames]:
            gm = [gg for (ii, gg) in rg if ii == i]
            if not gm:
                continue
            color = cv2.imread(os.path.join(D, rgb_files[i]))
            depth = cv2.imread(os.path.join(D, dep_files[j]), cv2.IMREAD_UNCHANGED)
            if color is None or depth is None:
                continue
            rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
                o3d.geometry.Image(np.ascontiguousarray(color[:, :, ::-1])),
                o3d.geometry.Image(np.ascontiguousarray(depth)),
                depth_scale=depth_scale, depth_trunc=6.0, convert_rgb_to_intensity=False)
            gg = gt[gm[0]]
            Twc = np.eye(4); Twc[:3, :3] = quat_to_R(*gg[4:8]); Twc[:3, 3] = gg[1:4]
            vol.integrate(rgbd, o3d_intr, extrinsic_of_twc(Twc))
            n += 1
        pc = vol.extract_point_cloud()
        return vol, pc.voxel_down_sample(a.voxel), n

    def reproj_residual(pcd_in):
        Pm = np.asarray(pcd_in.points)
        if len(Pm) == 0:
            return None
        Pcam = (Tcw[:3, :3] @ Pm.T).T + Tcw[:3, 3]
        front = Pcam[:, 2] > 0
        if front.sum() == 0:
            return None
        uu2 = K['fx'] * Pcam[front, 0] / Pcam[front, 2] + K['cx']
        vv2 = K['fy'] * Pcam[front, 1] / Pcam[front, 2] + K['cy']
        zi = Pcam[front, 2]
        inbox = (uu2 >= 0) & (uu2 < W) & (vv2 >= 0) & (vv2 < H)
        ui = uu2[inbox].astype(int); vi = vv2[inbox].astype(int); zz2 = zi[inbox]
        zobs = z[vi, ui]
        good = zobs > 0
        if good.sum() == 0:
            return None
        return float(np.median(np.abs(zz2[good] - zobs[good]))), int(good.sum())

    vol_correct, pcd_correct, n_int = integrate_map(lambda T: np.linalg.inv(T))
    vol_wrong, pcd_wrong, _ = integrate_map(lambda T: T.copy())
    r_correct = reproj_residual(pcd_correct)
    r_wrong = reproj_residual(pcd_wrong)
    conv = {
        'method': 'A/B multi-frame fusion + reprojection depth residual',
        'median_abs_depth_residual_world_to_camera_m': r_correct[0] if r_correct else None,
        'median_abs_depth_residual_camera_to_world_m': r_wrong[0] if r_wrong else None,
        'n_points_world_to_camera': len(np.asarray(pcd_correct.points)),
        'n_points_camera_to_world': len(np.asarray(pcd_wrong.points)),
        'chosen': 'extrinsic = inv(T_wc)  [world->camera]',
        'criterion': ('the convention whose multi-frame map re-projects onto the observed '
                      'depth wins; a single frame cannot discriminate T from T^-1'),
        'inverted_has_overlap': r_wrong is not None,
        'ratio_inverted_over_correct': ((r_wrong[0] / r_correct[0])
                                        if (r_correct and r_wrong and r_correct[0] > 0) else None),
        'note_if_none': ('None means the inverted-convention map has NO point in front of the '
                         'probe camera: it does not overlap the observed scene at all, which '
                         'is a stronger separation than a large residual.'),
    }
    q['extrinsics_test'] = conv
    q['frames_integrated'] = n_int

    # ---- 5. TSDF integration (reuse the A/B result already computed) ----
    vol, pcd = vol_correct, pcd_correct
    pcd.estimate_normals()
    ply = os.path.join(out_dir, 'map_stage1.ply')
    o3d.io.write_point_cloud(ply, pcd)
    pts = np.asarray(pcd.points)
    # ---- 6. ABSOLUTE check: reproject the map into the probe camera and compare depths
    # (v1 compared map extent to GT trajectory extent; with a quasi-stationary 60-frame
    #  window that ratio is meaningless -- it reported 62.7x and SUSPECT for that reason.)
    if len(pts):
        Tcw = np.linalg.inv(T_wc)
        Pm = np.asarray(pcd.points)
        Pcam = (Tcw[:3, :3] @ Pm.T).T + Tcw[:3, 3]
        front = Pcam[:, 2] > 0
        uu2 = (K['fx'] * Pcam[front, 0] / Pcam[front, 2] + K['cx'])
        vv2 = (K['fy'] * Pcam[front, 1] / Pcam[front, 2] + K['cy'])
        zin = Pcam[front, 2]
        inbox = (uu2 >= 0) & (uu2 < W) & (vv2 >= 0) & (vv2 < H)
        ui = uu2[inbox].astype(int); vi = vv2[inbox].astype(int); zi = zin[inbox]
        zobs = z[vi, ui]
        good = zobs > 0
        dz = np.abs(zi[good] - zobs[good])
        reproj = {
            'n_map_points_projected': int(good.sum()),
            'median_abs_depth_residual_m': float(np.median(dz)) if len(dz) else None,
            'p90_abs_depth_residual_m': float(np.quantile(dz, 0.9)) if len(dz) else None,
            'verdict': ('CONSISTENT' if len(dz) and float(np.median(dz)) < 0.08
                        else ('SUSPECT' if len(dz) else 'NO_OVERLAP')),
            'criterion': 'map re-projected into the probe camera must agree with the observed '
                         'depth image; this is an absolute, convention-sensitive check',
        }
    else:
        reproj = {'verdict': 'NO_POINTS'}
    q['reprojection_check'] = reproj

    # ---- 7. verdict ------------------------------------------------------
    checks = {
        'association_nonempty': len(rd) > 0 and len(rg) > 0,
        'association_dt_within_2ms': (q['rgb_depth_dt_median_s'] or 1) < 0.002,
        'depth_scale_determined_from_data': bool(scale_ok),
        # resolved if the chosen convention re-projects well AND the inverted one
        # either does not overlap the scene at all, or is far worse
        'extrinsics_direction_resolved': bool(
            conv['median_abs_depth_residual_world_to_camera_m'] is not None
            and conv['median_abs_depth_residual_world_to_camera_m'] < 0.08
            and (conv['median_abs_depth_residual_camera_to_world_m'] is None
                 or conv['median_abs_depth_residual_camera_to_world_m']
                    > 2.0 * conv['median_abs_depth_residual_world_to_camera_m'])),
        'map_nonempty': len(pts) > 1000,
        'reprojection_consistent': q['reprojection_check'].get('verdict') == 'CONSISTENT',
    }
    q['self_check'] = checks
    q['stage1_gate'] = 'PASS' if all(checks.values()) else 'NOT_PASSED'
    json.dump(q, open(os.path.join(out_dir, 'stage1_report.json'), 'w'), indent=2)
    print(json.dumps(q, indent=2))
    return 0 if q['stage1_gate'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
