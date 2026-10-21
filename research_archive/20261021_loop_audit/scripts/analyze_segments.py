import os, math
import numpy as np

BASE = r"D:\py\_audit\ac-slam\research_archive\20261021_ngd_region_prototype\results"

def load(path):
    d = np.loadtxt(path)
    return d[:, 0], d[:, 1:4], d[:, 4:8]

def R(q):
    x, y, z, w = q/np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                     [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                     [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])

def ang(A, B):
    c = (np.trace(A.T @ B)-1)/2
    return math.degrees(math.acos(max(-1, min(1, c))))

for tag in ("M0", "M2"):
    ts, p, q = load(os.path.join(BASE, tag, "CameraTrajectory.txt"))
    print(f"\n===== {tag} EXPORTED adjacent jumps =====")
    rows = []
    for i in range(1, len(ts)):
        rows.append((i, np.linalg.norm(p[i]-p[i-1]), ang(R(q[i-1]), R(q[i]))))
    rows = np.array(rows)
    for k in np.argsort(-rows[:, 1])[:10]:
        i = int(rows[k, 0])
        print(f"  frame {i:>3}: dpos={rows[k,1]:.4f} m  drot={rows[k,2]:.2f} deg")
    print("  median dpos=%.4f m" % np.median(rows[:, 1]))

print("\n================ ATE per segment (from per-frame ate.csv) ================")
for tag in ("M0", "M2"):
    for mode in ("online", "exported"):
        d = np.loadtxt(os.path.join(BASE, tag, "evaluation", mode, "ate.csv"), delimiter=",", skiprows=1)
        ts = d[:, 0]
        err = d[:, 1]
        segs = {"pre [0,490]": (0, 490), "trans [491,500]": (491, 500), "post [501,588]": (501, 588)}
        out = []
        for name, (a, b) in segs.items():
            m = (err >= 0) & (np.arange(len(err)) >= a) & (np.arange(len(err)) <= b)
            x = err[m]
            out.append(f"{name}: n={len(x)} rmse={np.sqrt(np.mean(x**2)):.4f} max={x.max():.3f}")
        print(f"{tag:>3} {mode:<9} | " + " | ".join(out))

print("\n================ RPE windows (exported) ================")
for tag in ("M0", "M2"):
    ts, _, _ = load(os.path.join(BASE, tag, "OnlineTrajectory.txt"))
    d = np.loadtxt(os.path.join(BASE, tag, "evaluation", "exported", "rpe.csv"), delimiter=",", skiprows=1)
    s, e, tm, rd = d[:,0], d[:,1], d[:,2], d[:,3]
    m = ((s < ts[493]) & (e >= ts[493])) | ((s < ts[500]) & (e >= ts[500]))
    rm = lambda x: float(np.sqrt(np.mean(x**2)))
    print(f"{tag}: ALL n={len(tm)} RPEt={rm(tm):.4f} RPEr={rm(rd):.3f} | CROSS n={m.sum()} RPEt={rm(tm[m]):.4f} | NONCROSS n={(~m).sum()} RPEt={rm(tm[~m]):.4f}")
    # worst 10 windows by translation
    idx = np.argsort(-tm)[:10]
    print("   worst windows: " + ", ".join(f"{s[k]:.2f}->{e[k]:.2f}={tm[k]:.3f}" for k in idx))
