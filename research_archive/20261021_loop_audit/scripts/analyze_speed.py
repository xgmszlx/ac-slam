import numpy as np, math
B=r"D:\py\_audit\ac-slam\research_archive\20261021_ngd_region_prototype\results"
def load(p):
    d=np.loadtxt(p); return d[:,0],d[:,1:4],d[:,4:8]
def R(q):
    x,y,z,w=q/np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
def ang(A,Bm):
    c=(np.trace(A.T@Bm)-1)/2; return math.degrees(math.acos(max(-1,min(1,c))))
for tag in ("M0","M2"):
    kt,kp,kq=load(rf"{B}\{tag}\KeyFrameTrajectory.txt")
    ft,fp,fq=load(rf"{B}\{tag}\OnlineTrajectory.txt")
    et,ep,eq=load(rf"{B}\{tag}\CameraTrajectory.txt")
    fidx=[int(np.argmin(np.abs(ft-t))) for t in kt]
    spd=[]; rspd=[]
    for i in range(1,len(kt)):
        dt=kt[i]-kt[i-1]
        if dt<=0: continue
        spd.append((np.linalg.norm(kp[i]-kp[i-1])/dt, fidx[i]))
        rspd.append((ang(R(kq[i-1]),R(kq[i]))/dt, fidx[i]))
    spd=np.array(spd); rspd=np.array(rspd)
    print(f"\n== {tag}: KF-chain speed over {len(spd)} intervals ==")
    print(f"   linear  m/s : median={np.median(spd[:,0]):.3f} p95={np.percentile(spd[:,0],95):.3f} max={spd[:,0].max():.3f} @frame {int(spd[np.argmax(spd[:,0]),1])}")
    print(f"   angular deg/s: median={np.median(rspd[:,0]):.1f} p95={np.percentile(rspd[:,0],95):.1f} max={rspd[:,0].max():.1f} @frame {int(rspd[np.argmax(rspd[:,0]),1])}")
    print(f"   path length (KF chain) = {np.linalg.norm(np.diff(kp,axis=0),axis=1).sum():.3f} m ; duration = {kt[-1]-kt[0]:.2f} s")
    # online vs exported displacement over the same intervals as the big KF steps
    for f0,f1 in ((250,265),(299,316),(165,168)):
        i0=int(np.argmin(np.abs(ft-ft[f0]))); 
        d_online=np.linalg.norm(fp[f1]-fp[f0]); r_online=ang(R(fq[f0]),R(fq[f1]))
        d_exp=np.linalg.norm(ep[f1]-ep[f0]); r_exp=ang(R(eq[f0]),R(eq[f1]))
        print(f"   frames {f0}->{f1} ({(ft[f1]-ft[f0])*1000:.0f} ms): online {d_online:.3f} m / {r_online:.1f} deg | exported {d_exp:.3f} m / {r_exp:.1f} deg")
