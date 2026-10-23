import numpy as np
from scanmatch import load_gt, gt_at, scans_to_pts, normals_from_scan
d=np.load('static_0.npz'); ts=d["ts"]; R=d["ranges"]; meta=d["meta"]
gt_t,gt_p=load_gt('/home/wcqw/lilocbench_amcl_validation_20261016/data/gt/static_0/gt_poses.txt')
gp=gt_at(gt_t,gt_p,ts); pts=scans_to_pts(R,meta,rmax=8.0)
CELL=0.3; SIG=0.02
def build_grid(Q):
    key=np.floor(Q/CELL).astype(np.int64); g={}
    for i,k in enumerate(map(tuple,key)): g.setdefault(k,[]).append(i)
    return {k:np.asarray(v) for k,v in g.items()}
def nn(g,Q,P):
    idx=np.full(len(P),-1); dist=np.full(len(P),1e9)
    ck=np.floor(P/CELL).astype(np.int64)
    for i,k in enumerate(map(tuple,ck)):
        b=-1;bd=1e9
        for dx in(-1,0,1):
            for dy in(-1,0,1):
                c=g.get((k[0]+dx,k[1]+dy))
                if c is None: continue
                dd=np.sum((Q[c]-P[i])**2,axis=1); j=dd.argmin()
                if dd[j]<bd: bd=dd[j]; b=c[j]
        idx[i]=b; dist[i]=np.sqrt(bd) if b>=0 else 1e9
    return idx,dist

for OFF in (-3,-2,-1,0,1,2,3):
    errs=[]
    for fi in list(range(6,len(pts)-6,200))[:40]:
        P0=pts[fi][::4]; Q0=pts[fi-1][::4]
        N0,_=normals_from_scan(P0); good=np.any(N0!=0,axis=1); P0,N0=P0[good],N0[good]
        if len(P0)<50: continue
        a=gp[fi-1]; b=gp[fi-1+OFF] if OFF!=0 else gp[fi]
        # 真值：用 (fi-1) -> (fi-1+OFF) 的相对运动，但匹配仍是 fi vs fi-1
        # 更公平：保持匹配对不变，改变 GT 的取值帧
        g2=gp[fi]
        dth=np.arctan2(np.sin(g2[2]-a[2]),np.cos(g2[2]-a[2]))
        ca,sa=np.cos(-a[2]),np.sin(-a[2]); dxw,dyw=g2[0]-a[0],g2[1]-a[1]
        # 若 OFF!=0，用偏移帧的位姿作为“当前”
        gc=gp[min(max(fi+OFF,0),len(gp)-1)]
        dth=np.arctan2(np.sin(gc[2]-a[2]),np.cos(gc[2]-a[2]))
        dxw,dyw=gc[0]-a[0],gc[1]-a[1]
        true=np.array([ca*dxw-sa*dyw, sa*dxw+ca*dyw, dth])
        grid=build_grid(Q0); x,y,th=true[0]+0.03,true[1]+0.03,true[2]+0.01
        for it in range(20):
            c,s=np.cos(th),np.sin(th); Rm=np.array([[c,-s],[s,c]])
            P=P0@Rm.T+np.array([x,y]); Nn=N0@Rm.T
            idx,dist=nn(grid,Q0,P); ok=dist<0.35
            if ok.sum()<12: break
            Pp,Np,Qq=P[ok],Nn[ok],Q0[idx[ok]]
            r=np.sum(Np*(Pp-Qq),axis=1)
            J=np.stack([Np[:,0],Np[:,1],-Pp[:,1]*Np[:,0]+Pp[:,0]*Np[:,1]],1)
            aa=np.abs(r); hub=np.where(aa<=0.10,1.0,0.10/np.maximum(aa,1e-9))
            wj=(1/(SIG*SIG))*hub
            H=(J*wj[:,None]).T@J; Jtr=(J*wj[:,None]).T@r
            try: ddx=np.linalg.solve(H+1e-12*np.eye(3),-Jtr)
            except: break
            x+=ddx[0];y+=ddx[1];th+=ddx[2]
            if np.max(np.abs(ddx))<1e-8: break
        errs.append(np.hypot(x-true[0],y-true[1]))
    if errs:
        e=np.array(errs)
        print(f"GT 偏移 {OFF:+d} 帧: 位移误差 均 {e.mean()*100:6.2f} cm  中位 {np.median(e)*100:6.2f} cm")
