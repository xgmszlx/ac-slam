import numpy as np, math
def load(p):
    d=np.loadtxt(p); return d[:,0],d[:,1:4],d[:,4:8]
def R(q):
    x,y,z,w=q/np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
def ang(A,B):
    c=(np.trace(A.T@B)-1)/2; return math.degrees(math.acos(max(-1,min(1,c))))
for tag in ("M0","M2"):
    kt,kp,kq=load(rf"D:\py\_audit\ac-slam\research_archive\20261021_ngd_region_prototype\results\{tag}\KeyFrameTrajectory.txt")
    ft,_,_=load(rf"D:\py\_audit\ac-slam\research_archive\20261021_ngd_region_prototype\results\{tag}\OnlineTrajectory.txt")
    fidx=[int(np.argmin(np.abs(ft-t))) for t in kt]
    print(f"\n{tag}: KFs={len(kt)} unique frame idx={len(set(fidx))} monotone={all(b>a for a,b in zip(fidx,fidx[1:]))}")
    for i in range(1,len(kt)):
        dp=np.linalg.norm(kp[i]-kp[i-1]); dt=kt[i]-kt[i-1]; dr=ang(R(kq[i-1]),R(kq[i]))
        if dp>0.14 or dr>8:
            print(f"  KF#{i:>3} @frame {fidx[i]:>3}: dt={dt*1000:7.1f} ms  dpos={dp:.4f} m  drot={dr:6.2f} deg  (prev frame {fidx[i-1]})")
    dts=np.diff(kt)*1000
    print(f"  KF dt: median={np.median(dts):.1f} ms  max={dts.max():.1f} ms")
