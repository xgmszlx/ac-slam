#!/usr/bin/env python3
"""P6: build ONE method's TSDF map in its own process, with per-phase timing.

Why a separate process per method (directive §7): resource.RUSAGE_SELF.ru_maxrss is a
process-lifetime peak, so running A/B/C/D in one process makes their memory numbers
meaningless. One process per method gives an independent peak RSS per method.

Phases timed separately: image load, mask/geometry pre-processing, TSDF integration,
map extraction. Thread counts are pinned from the environment so methods are comparable.

Usage: python3 build_map.py <method> <dataset> <sequence> --fuse 200 --voxel 0.02 --out DIR
  method in {A_Raw, B_MaskHOG, C_GeomPrev, D_MapConfirm}
"""
import argparse, json, os, resource, sys, time
import numpy as np, cv2, open3d as o3d
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'p6geom'))
import geom as p6geom

INTRINSICS = {'freiburg1': dict(fx=517.306504, fy=516.469215, cx=318.643040, cy=255.313989),
              'freiburg2': dict(fx=520.908620, fy=521.007327, cx=325.141442, cy=249.701764),
              'freiburg3': dict(fx=535.4, fy=539.2, cx=320.1, cy=247.6)}
DEPTH_SCALE = 5000.0


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
        if len(s) >= 8: rows.append([float(x) for x in s[:8]])
    return np.array(rows)


def quat_to_R(qx, qy, qz, qw):
    n = qx*qx+qy*qy+qz*qz+qw*qw; s = 2.0/n
    return np.array([[1-s*(qy*qy+qz*qz), s*(qx*qy-qz*qw), s*(qx*qz+qy*qw)],
                     [s*(qx*qy+qz*qw), 1-s*(qx*qx+qz*qz), s*(qy*qz-qx*qw)],
                     [s*(qx*qz-qy*qw), s*(qy*qz+qx*qw), 1-s*(qx*qx+qy*qy)]])


def pose_of(r):
    T = np.eye(4); T[:3, :3] = quat_to_R(*r[4:8]); T[:3, 3] = r[1:4]; return T


def associate(a_ts, b_ts, max_dt):
    pairs, dts = [], []; j = 0
    for i, t in enumerate(a_ts):
        if j >= len(b_ts): break
        while j+1 < len(b_ts) and abs(b_ts[j+1]-t) <= abs(b_ts[j]-t): j += 1
        if abs(b_ts[j]-t) <= max_dt: pairs.append((i, j)); dts.append(abs(b_ts[j]-t))
    return pairs, dts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('method'); ap.add_argument('dataset_dir'); ap.add_argument('sequence')
    ap.add_argument('--fuse', type=int, default=200); ap.add_argument('--eval', type=int, default=40)
    ap.add_argument('--voxel', type=float, default=0.02); ap.add_argument('--trunc', type=float, default=4.0)
    ap.add_argument('--tau', type=float, default=0.05); ap.add_argument('--warmup', type=int, default=5)
    ap.add_argument('--max-dt', type=float, default=0.02); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    D = a.dataset_dir
    rgb_ts, rgb_f = parse_index(os.path.join(D, 'rgb.txt'))
    dep_ts, dep_f = parse_index(os.path.join(D, 'depth.txt'))
    gt = parse_gt(os.path.join(D, 'groundtruth.txt'))
    rd, dt_rd = associate(rgb_ts, dep_ts, a.max_dt)
    rg, dt_rg = associate(rgb_ts, gt[:, 0], a.max_dt)
    gtm = {i: gt[j] for i, j in rg}
    fam = next(k for k in INTRINSICS if k in a.sequence); K = INTRINSICS[fam]
    probe = cv2.imread(os.path.join(D, dep_f[rd[0][1]]), cv2.IMREAD_UNCHANGED)
    H, W = probe.shape
    intr = o3d.camera.PinholeCameraIntrinsic(W, H, K['fx'], K['fy'], K['cx'], K['cy'])
    fused = [pr for pr in rd if pr[0] % 2 == 0 and pr[0] in gtm][:a.fuse]
    evals = [pr for pr in rd if pr[0] % 2 == 1 and pr[0] in gtm][:a.eval]

    hog = cv2.HOGDescriptor(); hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
    vol = o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=a.voxel, sdf_trunc=4*a.voxel,
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
    t_img = t_pre = t_int = 0.0
    occupied = set(); prev = None; kept = tot = 0; hog_boxes = 0
    for (i, j) in fused:
        s = time.perf_counter()
        color = cv2.imread(os.path.join(D, rgb_f[i]))
        dep = cv2.imread(os.path.join(D, dep_f[j]), cv2.IMREAD_UNCHANGED)
        t_img += time.perf_counter() - s
        if color is None or dep is None: continue
        z = dep.astype(np.float64)/DEPTH_SCALE; z[z > a.trunc] = 0.0
        Twc = pose_of(gtm[i]); keep = z > 0; tot += int(keep.sum())
        s = time.perf_counter()
        if a.method == 'B_MaskHOG':
            small = cv2.resize(color, (W//2, H//2))
            rects, wts = hog.detectMultiScale(small, winStride=(8, 8), padding=(8, 8), scale=1.05)
            mm = np.zeros((H, W), np.uint8)
            for (x, y, w, h), wt in zip(rects, wts):
                if wt < 0.3: continue
                hog_boxes += 1
                dx = int(w*0.25); dy = int(h*0.25)
                mm[max(0,(y-dy)*2):min(H,(y+h+dy)*2), max(0,(x-dx)*2):min(W,(x+w+dx)*2)] = 1
            keep &= (mm == 0)
        elif a.method == 'C_GeomPrev' and prev is not None:
            pd, pTwc = prev
            zp, hit = p6geom.warp_depth(pd, K, pTwc, Twc, (H, W))
            keep &= p6geom.consistency_mask(z, zp, hit, a.tau)
        elif a.method == 'D_MapConfirm' and len(occupied) > 0:
            Pc, _ = p6geom.backproject(np.where(keep, z, 0.0), K)
            Pw = (Twc[:3, :3] @ Pc.T).T + Twc[:3, 3]
            keys = np.floor(Pw/a.voxel).astype(np.int64)
            m = np.zeros((H, W), bool)
            m[p6geom.backproject(np.where(keep, z, 0.0), K)[1]] = [
                tuple(int(c) for c in k) in occupied for k in keys]
            keep &= m
        t_pre += time.perf_counter() - s
        kept += int(keep.sum())
        s = time.perf_counter()
        zmasked = np.where(keep, z, 0.0)
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
            o3d.geometry.Image(np.ascontiguousarray(color[:, :, ::-1])),
            o3d.geometry.Image(np.ascontiguousarray((zmasked*DEPTH_SCALE).astype(np.uint16))),
            depth_scale=DEPTH_SCALE, depth_trunc=a.trunc, convert_rgb_to_intensity=False)
        vol.integrate(rgbd, intr, np.linalg.inv(Twc))
        if a.method == 'D_MapConfirm':
            Pc2, _ = p6geom.backproject(zmasked, K)
            Pw2 = (Twc[:3, :3] @ Pc2.T).T + Twc[:3, 3]
            occupied.update(map(tuple, np.floor(Pw2/a.voxel).astype(np.int64).tolist()))
        prev = (z, Twc)
        t_int += time.perf_counter() - s
    s = time.perf_counter()
    pcd = vol.extract_point_cloud().voxel_down_sample(a.voxel)
    t_ext = time.perf_counter() - s
    ply = os.path.join(a.out, 'map.ply'); o3d.io.write_point_cloud(ply, pcd)
    eval_meta = [{'rgb_i': int(i), 'dep_j': int(j), 'Twc': pose_of(gtm[i]).tolist()} for (i, j) in evals]
    rep = {'method': a.method, 'sequence': a.sequence, 'fusion_frames': len(fused),
           'held_out_frames': len(evals), 'n_points': int(len(np.asarray(pcd.points))),
           'pixels_kept_frac': kept/max(tot, 1), 'hog_boxes': hog_boxes,
           'timing_s': {'image_load': t_img, 'preprocess_mask_geom': t_pre,
                        'tsdf_integrate': t_int, 'map_extract': t_ext,
                        'total': t_img+t_pre+t_int+t_ext},
           'per_frame_ms': {'image_load': 1e3*t_img/max(len(fused),1),
                            'preprocess_mask_geom': 1e3*t_pre/max(len(fused),1),
                            'tsdf_integrate': 1e3*t_int/max(len(fused),1)},
           'peak_rss_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024.0,
           'params': {'voxel': a.voxel, 'trunc': a.trunc, 'tau': a.tau, 'warmup': a.warmup,
                      'max_dt': a.max_dt, 'threads': os.environ.get('OMP_NUM_THREADS')},
           'held_out_meta': eval_meta}
    json.dump(rep, open(os.path.join(a.out, 'build_report.json'), 'w'), indent=2)
    print(json.dumps({k: rep[k] for k in ('method','n_points','pixels_kept_frac','peak_rss_mib',
                                          'timing_s','per_frame_ms','hog_boxes')}, indent=2))


if __name__ == '__main__':
    main()
