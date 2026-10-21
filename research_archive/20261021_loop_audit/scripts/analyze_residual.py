import os, math, json
import numpy as np

BASE = r"D:\py\_audit\ac-slam\research_archive\20261021_ngd_region_prototype\results"

def load(path):
    d = np.loadtxt(path)
    return d[:, 0], d[:, 1:4], d[:, 4:8]

def R(q):
    x, y, z, w = q / np.linalg.norm(q)
    return np.array([
        [1-2*(y*y+z*z), 2*(x*y-z*w),   2*(x*z+y*w)],
        [2*(x*y+z*w),   1-2*(x*x+z*z), 2*(y*z-x*w)],
        [2*(x*z-y*w),   2*(y*z+x*w),   1-2*(x*x+y*y)]])

def T(p, q):
    M = np.eye(4); M[:3, :3] = R(q); M[:3, 3] = p
    return M

def ang(M):
    c = (np.trace(M[:3, :3]) - 1)/2
    return math.degrees(math.acos(max(-1, min(1, c))))

for tag in ("M0", "M2"):
    ts_o, p_o, q_o = load(os.path.join(BASE, tag, "OnlineTrajectory.txt"))
    ts_e, p_e, q_e = load(os.path.join(BASE, tag, "CameraTrajectory.txt"))
    n = min(len(ts_o), len(ts_e))
    # D_i = T_exported_i * T_online_i^-1  (left residual: how history was transformed)
    Dt, Dr = [], []
    for i in range(n):
        D = T(p_e[i], q_e[i]) @ np.linalg.inv(T(p_o[i], q_o[i]))
        Dt.append(D[:3, 3]); Dr.append(D[:3, :3])
    Dt = np.array(Dt); Dr = np.array(Dr)
    print(f"\n========== {tag}: online->exported residual D_i ==========")
    for lo, hi, name in ((0, 489, "pre-loop [0,489]"), (490, 500, "transition [490,500]"), (501, n-1, f"post [501,{n-1}]")):
        sub_t = Dt[lo:hi+1]; 
        # rotation spread: angle between each Dr and the segment-mean rotation
        Msum = np.zeros((3, 3))
        for k in range(lo, hi+1): Msum += Dr[k]
        U, _, Vt = np.linalg.svd(Msum); Rmean = U @ Vt
        dev = np.array([ang(M=np.linalg.inv(Rmean) @ Dr[k]) for k in range(lo, hi+1)])
        print(f"{name:>18}: |t| mean={np.linalg.norm(sub_t,axis=1).mean():.4f} m  "
              f"t-spread(std per axis)={sub_t.std(axis=0).round(4)}  max|t|={np.linalg.norm(sub_t,axis=1).max():.4f}")
        print(f"{'':>18}  rot deviation from segment mean: mean={dev.mean():.3f} deg  p95={np.percentile(dev,95):.3f}  max={dev.max():.3f}")
    # step detection on |t|
    mag = np.linalg.norm(Dt, axis=1)
    d = np.abs(np.diff(mag))
    idx = np.argsort(-d)[:8]
    print("largest |t| steps (frame -> delta):")
    for k in sorted(idx):
        print(f"   frame {k+1:>3}: |D| {mag[k]:.4f} -> {mag[k+1]:.4f}   (delta {d[k]:.4f} m, rot {ang(np.linalg.inv(Dr[k])@Dr[k+1]):.2f} deg)")
