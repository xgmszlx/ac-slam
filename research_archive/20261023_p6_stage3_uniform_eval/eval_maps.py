#!/usr/bin/env python3
"""P6-B: ONE uniform renderer for all methods, with per-held-out-frame metrics.

Rendering is identical for every method: a z-buffered surface projection of the method's
own map into each held-out camera with a fixed splat radius. Open3D 0.13 exposes no
raycast for ScalableTSDFVolume, so the "z-buffered surface projection" option from the
directive is used, and that choice is recorded in the output.

Reported per held-out frame and pooled:
  coverage      valid observed pixels that received a rendered depth
  resid_med/p90 |z_render - z_obs| over covered pixels
  inlier_5cm    covered pixels within 5 cm
  fsv           free-space violation rate: covered pixels where the map surface is more
                than `fsv_margin` IN FRONT of the observed surface (map occupies space the
                sensor saw as empty)
  common-domain metrics restricted to pixels covered by EVERY method, so no method can win
                by covering fewer or easier pixels.

Usage: python3 eval_maps.py <rundir> <dataset_dir> <sequence> --methods A,B,C,D
"""
import argparse, csv, json, os
import numpy as np, cv2, open3d as o3d

INTRINSICS = {'freiburg1': dict(fx=517.306504, fy=516.469215, cx=318.643040, cy=255.313989),
              'freiburg2': dict(fx=520.908620, fy=521.007327, cx=325.141442, cy=249.701764),
              'freiburg3': dict(fx=535.4, fy=539.2, cx=320.1, cy=247.6)}
DEPTH_SCALE = 5000.0


def parse_depth_index(p):
    ts, fs = [], []
    for line in open(p):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        s = line.split(); ts.append(float(s[0])); fs.append(s[1])
    return ts, fs


def render(points, Twc, K, H, W, radius):
    """Uniform renderer: project, splat with a fixed radius, keep the NEAREST z."""
    if len(points) == 0:
        return np.full((H, W), np.nan), np.zeros((H, W), bool)
    Tcw = np.linalg.inv(Twc)
    Pc = (Tcw[:3, :3] @ points.T).T + Tcw[:3, 3]
    keep = Pc[:, 2] > 1e-3
    if not keep.any():
        return np.full((H, W), np.nan), np.zeros((H, W), bool)
    P = Pc[keep]; z = P[:, 2]
    u = K['fx']*P[:, 0]/z + K['cx']
    v = K['fy']*P[:, 1]/z + K['cy']
    inside = (u >= -radius) & (u < W + radius) & (v >= -radius) & (v < H + radius)
    u, v, z = u[inside], v[inside], z[inside]
    zbuf = np.full((H, W), np.inf)
    for du in range(-radius, radius + 1):
        for dv in range(-radius, radius + 1):
            ui = np.rint(u + du).astype(int); vi = np.rint(v + dv).astype(int)
            ok = (ui >= 0) & (ui < W) & (vi >= 0) & (vi < H)
            np.minimum.at(zbuf, (vi[ok], ui[ok]), z[ok])
    hit = np.isfinite(zbuf)
    zbuf[~hit] = np.nan
    return zbuf, hit


def frame_metrics(zbuf, hit, zobs, fsv_margin, domain_mask=None):
    valid_obs = zobs > 0
    if domain_mask is None:
        dom = np.ones(zobs.shape, bool)
    else:
        dom = domain_mask
    cov = hit & valid_obs & dom
    n_valid = int((valid_obs & dom).sum())
    out = {'n_valid_obs': n_valid, 'n_covered': int(cov.sum()),
           'coverage': (float(cov.sum())/n_valid) if n_valid else None}
    if cov.sum() == 0:
        out.update(resid_med=None, resid_p90=None, inlier_5cm=None, fsv=None); return out
    d = np.abs(zbuf[cov] - zobs[cov])
    out['resid_med'] = float(np.median(d))
    out['resid_p90'] = float(np.quantile(d, 0.9))
    out['inlier_5cm'] = float((d <= 0.05).mean())
    out['fsv'] = float((zbuf[cov] < zobs[cov] - fsv_margin).mean())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rundir'); ap.add_argument('dataset_dir'); ap.add_argument('sequence')
    ap.add_argument('--methods', default='A_Raw,B_MaskHOG,C_GeomPrev,D_MapConfirm')
    ap.add_argument('--radius', type=int, default=2)
    ap.add_argument('--fsv-margin', type=float, default=0.10)
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    outdir = a.out or a.rundir
    D = a.dataset_dir
    fam = next(k for k in INTRINSICS if k in a.sequence); K = INTRINSICS[fam]
    methods = a.methods.split(',')
    dep_ts, dep_f = parse_depth_index(os.path.join(D, 'depth.txt'))

    maps, meta0, builds = {}, None, {}
    for m in methods:
        d = os.path.join(a.rundir, m)
        builds[m] = json.load(open(os.path.join(d, 'build_report.json')))
        pcd = o3d.io.read_point_cloud(os.path.join(d, 'map.ply'))
        maps[m] = np.asarray(pcd.points)
        hm = builds[m]['held_out_meta']
        if meta0 is None: meta0 = hm
        assert hm == meta0, 'held-out frames differ between methods'

    per_frame_rows = []
    agg = {m: {k: [] for k in ('coverage','resid_med','resid_p90','inlier_5cm','fsv')} for m in methods}
    agg_common = {m: {k: [] for k in ('resid_med','resid_p90','inlier_5cm','fsv')} for m in methods}

    for k, meta in enumerate(meta0):
        zobs = cv2.imread(os.path.join(D, dep_f[meta['dep_j']]), cv2.IMREAD_UNCHANGED)
        zobs = zobs.astype(np.float64)/DEPTH_SCALE
        zobs[zobs > 4.0] = 0.0
        Twc = np.array(meta['Twc'])
        rend = {m: render(maps[m], Twc, K, 480, 640, a.radius) for m in methods}
        # common pixel domain: covered by EVERY method
        common = None
        for m in methods:
            h = rend[m][1]
            common = h if common is None else (common & h)
        for m in methods:
            fm = frame_metrics(rend[m][0], rend[m][1], zobs, a.fsv_margin)
            fmc = frame_metrics(rend[m][0], rend[m][1], zobs, a.fsv_margin, common)
            row = {'frame': k, 'method': m, **{k2: fm[k2] for k2 in fm}}
            for k2 in ('resid_med','resid_p90','inlier_5cm','fsv'):
                row['common_'+k2] = fmc[k2]
            per_frame_rows.append(row)
            for k2 in agg[m]:
                if fm[k2] is not None: agg[m][k2].append(fm[k2])
                if k2 != 'coverage' and fmc[k2] is not None: agg_common[m][k2].append(fmc[k2])

    with open(os.path.join(outdir, 'per_frame.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(per_frame_rows[0].keys()))
        w.writeheader(); w.writerows(per_frame_rows)

    summary = {'sequence': a.sequence, 'renderer': 'z-buffered surface projection (splat radius %d)' % a.radius,
               'radius': a.radius, 'fsv_margin_m': a.fsv_margin,
               'held_out_frames': len(meta0), 'methods': {}}
    for m in methods:
        e = {k2: (float(np.median(v)) if v else None) for k2, v in agg[m].items()}
        e['resid_med_mean'] = float(np.mean(agg[m]['resid_med'])) if agg[m]['resid_med'] else None
        e['fsv_mean'] = float(np.mean(agg[m]['fsv'])) if agg[m]['fsv'] else None
        c = {k2: (float(np.median(v)) if v else None) for k2, v in agg_common[m].items()}
        summary['methods'][m] = {
            'build': {k2: builds[m][k2] for k2 in
                      ('n_points','pixels_kept_frac','peak_rss_mib','timing_s','per_frame_ms','hog_boxes')},
            'all_pixels': e, 'common_domain': c}
    json.dump(summary, open(os.path.join(outdir, 'eval_summary.json'), 'w'), indent=2)

    print("%-14s %7s %6s %8s %8s %8s %8s %8s" %
          ('method','pts','kept','cover','residMed','inlier5','fsv','RSS_MiB'))
    for m in methods:
        s = summary['methods'][m]
        print("%-14s %7d %6.3f %8s %8s %8s %8s %8.0f" % (
            m, s['build']['n_points'], s['build']['pixels_kept_frac'] or 0,
            '%.3f' % s['all_pixels']['coverage'] if s['all_pixels']['coverage'] is not None else 'n/a',
            '%.4f' % s['all_pixels']['resid_med'] if s['all_pixels']['resid_med'] is not None else 'n/a',
            '%.3f' % s['all_pixels']['inlier_5cm'] if s['all_pixels']['inlier_5cm'] is not None else 'n/a',
            '%.3f' % s['all_pixels']['fsv_mean'] if s['all_pixels']['fsv_mean'] is not None else 'n/a',
            s['build']['peak_rss_mib']))
    print("\ncommon pixel domain (pixels covered by ALL methods):")
    print("%-14s %8s %8s %8s %8s" % ('method','residMed','inlier5','fsv',''))
    for m in methods:
        c = summary['methods'][m]['common_domain']
        print("%-14s %8s %8s %8s" % (m,
            '%.4f' % c['resid_med'] if c['resid_med'] is not None else 'n/a',
            '%.3f' % c['inlier_5cm'] if c['inlier_5cm'] is not None else 'n/a',
            '%.3f' % c['fsv'] if c['fsv'] is not None else 'n/a'))


if __name__ == '__main__':
    main()
