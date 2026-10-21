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

def ang(A,B):
    c=(np.trace(A.T@B)-1)/2
    return math.degrees(math.acos(max(-1,min(1,c))))

for tag in ("M0","M2"):
    kt, kp, kq = load(os.path.join(BASE, tag, "KeyFrameTrajectory.txt"))
    ft, fp, fq = load(os.path.join(BASE, tag, "OnlineTrajectory.txt"))
    print(f"\n===== {tag}: KeyFrameTrajectory n={len(kt)} =====")
    # map KF timestamps to frame index
    fidx = [int(np.argmin(np.abs(ft-t))) for t in kt]
    jumps=[]
    for i in range(1,len(kt)):
        jumps.append((fidx[i], np.linalg.norm(kp[i]-kp[i-1]), ang(R(kq[i-1]),R(kq[i]))))
    jumps=np.array(jumps)
    top=np.argsort(-jumps[:,1])[:8]
    print("  top KF-pose steps (frame idx of KF, dpos, drot):")
    for k in np.sort(top):
        print(f"    KF@frame {int(jumps[k,0]):>3}: dpos={jumps[k,1]:.4f} m  drot={jumps[k,2]:.2f} deg")
    for f in (168,265,316,491,493,500):
        near=[int(x) for x in fidx if abs(x-f)<=3]
        print(f"  frames near {f}: KF frame indices {near}")

# also test whether M2 exported pose = (relative motion of online) * (KF transform) locally:
# check if exported preserves online *relative* motion away from the steps
for tag in ("M0","M2"):
    et,ep,eq = load(os.path.join(BASE,tag,"CameraTrajectory.txt"))
    ot,op,oq = load(os.path.join(BASE,tag,"OnlineTrajectory.txt"))
    n=min(len(et),len(ot))
    # relative motion between consecutive frames, compare
    dE=[];dO=[]
    for i in range(1,n):
        dE.append(np.linalg.norm(ep[i]-ep[i-1])); dO.append(np.linalg.norm(op[i]-op[i-1]))
    dE=np.array(dE);dO=np.array(dO)
    ratio=dE/(dO+1e-9)
    print(f"\n{tag}: consecutive-motion ratio exported/online  median={np.median(ratio):.3f}  p95={np.percentile(ratio,95):.3f}  max={ratio.max():.2f}")
    big=np.where(np.abs(dE-dO)>0.15)[0]+1
    print(f"   frames where |motion difference|>0.15 m: {big[:20]}")
