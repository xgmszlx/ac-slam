#!/usr/bin/python3
"""Phase 4A: offline validation of the ONLINE G2 cue.

Online G2 (SLAM-only, computable at loop start) =
    |wrap( robot SLAM heading at loop start - history tangent at closest pose )|

Here 'history tangent' is estimated two ways from online data:
  (a) direction of the V0 reliable-loop path (first -> last waypoint),
  (b) local tangent of the pre-loop SLAM trajectory at the closest historical pose.

We compare the online G2 against the offline (GT-based) yaw_diff_median_rad used in
Phase 3B, and check whether the binary decision (G2>0.78) is stable between them and
whether online G2 separates the S reference from the D1/C3 failures.
"""

import csv
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FEAT = ROOT / 'results' / 'phase3a' / 'analysis' / 'loop_realization_features.csv'
OUT = ROOT / 'results' / 'phase4a' / 'gate_audit'


def wrap(a):
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return a


def load_tum(path):
    out = []
    for line in Path(path).read_text(errors='replace').splitlines():
        p = line.split()
        if len(p) < 8:
            continue
        try:
            t, x, y = float(p[0]), float(p[1]), float(p[2])
            qz, qw = float(p[6]), float(p[7])
        except ValueError:
            continue
        yaw = math.atan2(2.0 * (qw * qz), 1.0 - 2.0 * qz * qz)
        out.append((t, x, y, yaw))
    return out


def loop_events(seed):
    rosout = ROOT / 'results' / 'phase2c' / 'map3' / 'seed_{}'.format(seed) / 'rosout.log'
    starts, ends = [], []
    paths = {}
    for line in rosout.read_text(errors='replace').splitlines():
        m = re.match(r'^([0-9.]+) INFO .*PHASE2_LOOP_EXECUTION_(STARTED|FINISHED) vertex=(\d+)', line)
        if m:
            (starts if m.group(2) == 'STARTED' else ends).append(
                (float(m.group(1)), int(m.group(3))))
        m = re.search(r'PHASE2_LOOP_PLANNED vertex=(\d+) source=\S+ waypoints=\d+ path=(.*)', line)
        if m:
            paths[int(m.group(1))] = [tuple(map(float, tok.split(',')))
                                      for tok in m.group(2).split(';')]
    return starts, ends, paths


def local_tangent(slam, t_ref, x_ref, y_ref):
    """Local tangent of the SLAM trajectory at the pose nearest to (x_ref,y_ref)."""
    best = min(range(len(slam)), key=lambda i: (slam[i][1] - x_ref) ** 2 + (slam[i][2] - y_ref) ** 2)
    lo = max(0, best - 3)
    hi = min(len(slam) - 1, best + 3)
    if hi - lo < 2:
        return None
    xs = [slam[i][1] for i in range(lo, hi + 1)]
    ys = [slam[i][2] for i in range(lo, hi + 1)]
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    den = sum((xs[i] - mx) ** 2 for i in range(n))
    if den < 1e-6:
        return None
    slope = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / den
    return math.atan2(slope, 1.0)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(open(FEAT)))
    out_rows = []
    for r in rows:
        seed = r['seed']
        lid = int(r['loop_id'])
        starts, ends, paths = loop_events(seed)
        if lid - 1 >= len(starts):
            continue
        ss, sv = starts[lid - 1]
        path = paths.get(sv)
        slam = load_tum(ROOT / 'results' / 'phase2c' / 'map3' / 'seed_{}'.format(seed) /
                        'trajectory_slam.txt')
        near_start = min(slam, key=lambda s: abs(s[0] - ss))
        robot_heading = near_start[3]
        g2_path = None
        if path and len(path) >= 2:
            dx = path[-1][0] - path[0][0]
            dy = path[-1][1] - path[0][1]
            htan = math.atan2(dy, dx)
            g2_path = abs(wrap(robot_heading - htan))
        # closest historical pose (pre-loop) = pose nearest to the loop vertex position
        # use path[-1] as the vertex-side reference when available
        ref_x, ref_y = (path[-1] if path else (near_start[1], near_start[2]))
        htan2 = local_tangent(slam, ss, ref_x, ref_y)
        g2_traj = abs(wrap(robot_heading - htan2)) if htan2 is not None else None
        off = float(r['yaw_diff_median_rad'])
        out_rows.append({
            'seed': seed, 'loop_id': lid, 'vertex': sv, 'subclass': r['failure_subclass'],
            'v0_span_m': r['history_path_length_m'],
            'yaw_med_offline_rad': round(off, 3),
            'online_g2_pathdir_rad': round(g2_path, 3) if g2_path is not None else None,
            'online_g2_trajtangent_rad': round(g2_traj, 3) if g2_traj is not None else None,
            'offline_gt_0_78': off > 0.78,
            'online_pathdir_gt_0_78': (g2_path or 9.9) > 0.78,
            'online_trajtangent_gt_0_78': (g2_traj or 9.9) > 0.78,
        })
    with (OUT / 'online_g2_validation.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    print('%-13s %-4s %-8s %-9s %-9s %-9s %-6s %-6s' % (
        'loop', 'sub', 'offline', 'g2_path', 'g2_traj', 'off>0.78', 'p>0.78', 't>0.78'))
    for r in out_rows:
        print('s{} l{} v{:<4} {:<8} {:<9} {:<9} {:<9} {:<6} {:<6} {:<6}'.format(
            r['seed'], r['loop_id'], r['vertex'], r['subclass'],
            r['yaw_med_offline_rad'], r['online_g2_pathdir_rad'], r['online_g2_trajtangent_rad'],
            str(r['offline_gt_0_78']), str(r['online_pathdir_gt_0_78']),
            str(r['online_trajtangent_gt_0_78'])))
    # agreement with offline (binary)
    agree_path = sum(1 for r in out_rows if r['offline_gt_0_78'] == r['online_pathdir_gt_0_78'])
    agree_traj = sum(1 for r in out_rows if r['offline_gt_0_78'] == r['online_trajtangent_gt_0_78'])
    print('\nagreement offline-vs-online(pathdir) = {}/{}'.format(agree_path, len(out_rows)))
    print('agreement offline-vs-online(trajtang) = {}/{}'.format(agree_traj, len(out_rows)))


if __name__ == '__main__':
    main()
