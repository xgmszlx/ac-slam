import os, math, json
import numpy as np

BASE = r"D:\py\_audit\ac-slam\research_archive\20261021_ngd_region_prototype\results"

def load_tum(path):
    d = np.loadtxt(path, delimiter=None, ndmin=2)
    return d[:, 0], d[:, 1:4], d[:, 4:8]

def quat_to_R(q):
    x, y, z, w = q
    n = math.sqrt(x*x+y*y+z*z+w*w)
    if n == 0: n = 1.0
    x, y, z, w = x/n, y/n, z/n, w/n
    return np.array([
        [1-2*(y*y+z*z), 2*(x*y-z*w),   2*(x*z+y*w)],
        [2*(x*y+z*w),   1-2*(x*x+z*z), 2*(y*z-x*w)],
        [2*(x*z-y*w),   2*(y*z+x*w),   1-2*(x*x+y*y)]
    ])

def rot_angle_deg(R):
    c = (np.trace(R)-1.0)/2.0
    c = max(-1.0, min(1.0, c))
    return math.degrees(math.acos(c))

def rect4(name):
    pass

def analyze(tag):
    ts_on, p_on, q_on = load_tum(os.path.join(BASE, tag, "OnlineTrajectory.txt"))
    ts_cam, p_cam, q_cam = load_tum(os.path.join(BASE, tag, "CameraTrajectory.txt"))
    print(f"\n===== {tag} =====")
    print(f"online rows={len(ts_on)}  exported rows={len(ts_cam)}")
    n = min(len(ts_on), len(ts_cam))
    rows = []
    for i in range(1, n):
        d = np.linalg.norm(p_on[i]-p_on[i-1])
        R = quat_to_R(q_on[i-1]).T @ quat_to_R(q_on[i])
        rows.append((i, ts_on[i], d, rot_angle_deg(R)))
    rows = np.array(rows)
    print("\n-- top 12 adjacent jumps (online) --")
    order = np.argsort(-rows[:, 2])[:12]
    print(f"{'frame':>6} {'dt(ms)':>8} {'dpos(m)':>9} {'drot(deg)':>10}")
    for k in sorted(order):
        i = int(rows[k, 0])
        print(f"{i:>6} {(ts_on[i]-ts_on[i-1])*1000:>8.1f} {rows[k,2]:>9.4f} {rows[k,3]:>10.2f}")
    # top by rotation
    order2 = np.argsort(-rows[:, 3])[:8]
    print("-- top 8 rotation jumps --")
    for k in sorted(order2):
        i = int(rows[k, 0])
        print(f"  frame {i:>4}  dpos={rows[k,2]:.4f} m  drot={rows[k,3]:.2f} deg")

    dpos = np.linalg.norm(p_cam[:n]-p_on[:n], axis=1)
    drot = np.array([rot_angle_deg(quat_to_R(q_on[i]).T @ quat_to_R(q_cam[i])) for i in range(n)])
    print(f"\n-- online vs exported (n={n}) --")
    print(f"position diff: median={np.median(dpos):.4f} mean={dpos.mean():.4f} p95={np.percentile(dpos,95):.4f} max={dpos.max():.4f}")
    print(f"rotation diff: median={np.median(drot):.3f} mean={drot.mean():.3f} p95={np.percentile(drot,95):.3f} max={drot.max():.3f}")
    print("\n-- window 486..506 --")
    print(f"{'frame':>6} {'dpos_on':>8} {'drot_on':>8} {'on_vs_exp_p':>11} {'on_vs_exp_r':>11}")
    for i in range(486, 507):
        if i < n and i >= 1:
            print(f"{i:>6} {rows[i-1,2]:>8.4f} {rows[i-1,3]:>8.2f} {dpos[i]:>11.4f} {drot[i]:>11.2f}")
    return ts_on, rows, dpos, drot

def rpe_windows(tag, jumps, labels):
    ts_on, _p, _q = load_tum(os.path.join(BASE, tag, "OnlineTrajectory.txt"))
    path = os.path.join(BASE, tag, "evaluation", "online", "rpe.csv")
    d = np.loadtxt(path, delimiter=",", skiprows=1)
    s, e, tm, rd = d[:,0], d[:,1], d[:,2], d[:,3]
    masks = []
    for jf, jt in jumps:
        m = (s < jt) & (e >= jt)
        masks.append(m)
    anym = np.zeros(len(s), dtype=bool)
    for m in masks: anym |= m
    def rmse(x): return float(np.sqrt(np.mean(np.square(x)))) if len(x) else float('nan')
    print(f"\n===== RPE windows: {tag} =====")
    print(f"total windows={len(s)}")
    print(f"ALL              : n={len(tm):>3} RPEt={rmse(tm):.4f} m  RPEr={rmse(rd):.3f} deg")
    print(f"CROSS jump       : n={anym.sum():>3} RPEt={rmse(tm[anym]):.4f} m  RPEr={rmse(rd[anym]):.3f} deg")
    print(f"NO-CROSS         : n={(~anym).sum():>3} RPEt={rmse(tm[~anym]):.4f} m  RPEr={rmse(rd[~anym]):.3f} deg")
    for (jf, jt), m in zip(jumps, masks):
        print(f"  crossing frame {jf:>3} (t={jt:.3f}): n={m.sum():>2} RPEt={rmse(tm[m]):.4f} RPEr={rmse(rd[m]):.3f}")
    return anym.sum()

ts, rows, dpos, drot = analyze("M0")
m0 = {"jump493": ts[493], "jump500": ts[500]}
ts2, rows2, dpos2, drot2 = analyze("M2")
m2 = {"jump493": ts2[493], "jump500": ts2[500]}
print("\nM2 frame timestamps: 493=%.3f  500=%.3f" % (ts2[493], ts2[500]))
print("M0 same-frame adjacent deltas: 493=(%.4f m, %.2f deg) 500=(%.4f m, %.2f deg)" % (rows[492,2], rows[492,3], rows[499,2], rows[499,3]))

rpe_windows("M0", [(493, ts[493]), (500, ts[500])], None)
rpe_windows("M2", [(493, ts2[493]), (500, ts2[500])], None)
