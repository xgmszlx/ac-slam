import numpy as np, math
B=r"D:\py\_audit\ac-slam\research_archive\20261021_ngd_region_prototype\results"
def load(p):
    d=np.loadtxt(p); return d[:,0],d[:,1:4]
def rigid(src,dst):
    a,b=src.mean(0),dst.mean(0)
    u,_,vt=np.linalg.svd((src-a).T@(dst-b)); d=np.eye(3); d[-1,-1]=np.linalg.det(vt.T@u.T)
    R=vt.T@d@u.T
    return R, b-R@a
def relang(R1,R2):
    c=(np.trace(R1.T@R2)-1)/2; return math.degrees(math.acos(max(-1,min(1,c))))
for tag in ("M0","M2"):
    _,op=load(rf"{B}\{tag}\OnlineTrajectory.txt")
    _,ep=load(rf"{B}\{tag}\CameraTrajectory.txt")
    n=min(len(op),len(ep))
    segs={"pre[10:480]":slice(10,481),"post[501:588]":slice(501,589),"all":slice(0,n)}
    res={}
    for name,s in segs.items():
        R,t=rigid(op[s],ep[s])
        p=(op[s]@R.T)+t
        rms=np.sqrt(np.mean(np.sum((p-ep[s])**2,axis=1)))
        res[name]=(R,t,rms)
        print(f"{tag} {name:>15}: residual rms={rms:.4f} m")
    Rp,tp,_=res["pre[10:480]"]; Rq,tq,_=res["post[501:588]"]
    print(f"{tag}  implied frame discrepancy pre vs post: rotation={relang(Rp,Rq):.2f} deg, translation={np.linalg.norm(tp-tq):.4f} m")
