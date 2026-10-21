import numpy as np, sys, json
from scanmatch import load_gt, gt_at, scans_to_pts, normals_from_scan

NPZ=sys.argv[1]; GT=sys.argv[2]
NFRAME=int(sys.argv[3]); NPERT=int(sys.argv[4]); STEP=int(sys.argv[5])
SIGMA=float(sys.argv[6]) if len(sys.argv)>6 else 0.02
rng=np.random.default_rng(1)
d=np.load(NPZ); ts=d["ts"]; R=d["ranges"]; meta=d["meta"]
gt_t,gt_p=load_gt(GT); gp=gt_at(gt_t,gt_p,ts)
pts=scans_to_pts(R,meta,rmax=8.0)
CELL=0.3

def build_grid(Q):
    key=np.floor(Q/CELL).astype(np.int64)
    g={}
    for i,k in enumerate(map(tuple,key)): g.setdefault(k,[]).append(i)
    return {k:np.asarray(v) for k,v in g.items()}

def nn_query(g,Q,P):
    idx=np.full(len(P),-1); dist=np.full(len(P),1e9)
    ck=np.floor(P/CELL).astype(np.int64)
    for i,k in enumerate(map(tuple,ck)):
        best=-1;bd=1e9
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                c=g.get((k[0]+dx,k[1]+dy))
                if c is None: continue
                dd=np.sum((Q[c]-P[i])**2,axis=1); j=dd.argmin()
                if dd[j]<bd: bd=dd[j]; best=c[j]
        idx[i]=best; dist[i]=np.sqrt(bd) if best>=0 else 1e9
    return idx,dist

rows=[]
for fi in list(range(1,len(pts),STEP))[:NFRAME]:
    P0=pts[fi][::4]; Q0=pts[fi-1][::4]          # 降采样到约 200 点
    if len(P0)<80 or len(Q0)<80: continue
    N0,k=normals_from_scan(P0); good=np.any(N0!=0,axis=1)
    P0,N0=P0[good],N0[good]
    if len(P0)<60: continue
    a=gp[fi-1]; b=gp[fi]
    dth=np.arctan2(np.sin(b[2]-a[2]),np.cos(b[2]-a[2]))
    dxw,dyw=b[0]-a[0],b[1]-a[1]
    ca,sa=np.cos(-a[2]),np.sin(-a[2])
    dx=ca*dxw-sa*dyw; dy=sa*dxw+ca*dyw
    true=np.array([dx,dy,dth])                  # 当前帧 -> 上一帧 的真值
    g=build_grid(Q0)
    for pi in range(NPERT):
        init=true+rng.normal(0,[0.05,0.05,0.01])
        x,y,th=init; H=None; ok=None
        for it in range(20):
            c,s=np.cos(th),np.sin(th)
            Rm=np.array([[c,-s],[s,c]])
            P=P0@Rm.T+np.array([x,y]); Nn=N0@Rm.T
            idx,dist=nn_query(g,Q0,P); ok=dist<0.35
            if ok.sum()<12: break
            Pp,Np,Qq=P[ok],Nn[ok],Q0[idx[ok]]
            r=np.sum(Np*(Pp-Qq),axis=1)
            J=np.stack([Np[:,0],Np[:,1],-Pp[:,1]*Np[:,0]+Pp[:,0]*Np[:,1]],1)
            w=1.0/(SIGMA*SIGMA); aa=np.abs(r)
            hub=np.where(aa<=0.10,1.0,0.10/np.maximum(aa,1e-9)); wj=w*hub
            JtJ=(J*wj[:,None]).T@J; Jtr=(J*wj[:,None]).T@r; H=JtJ
            try: ddx=np.linalg.solve(JtJ+1e-12*np.eye(3),-Jtr)
            except: break
            x+=ddx[0];y+=ddx[1];th+=ddx[2]
            if np.max(np.abs(ddx))<1e-8: break
        if H is None: continue
        ev=np.maximum(np.linalg.eigvalsh(H),1e-12)
        e=np.array([x,y,th])-true; e[2]=np.arctan2(np.sin(e[2]),np.cos(e[2]))
        nees=float(e@(H@e))
        rows.append(dict(frame=int(fi),nees=nees,e_along=float(e[0]),e_lat=float(e[1]),
                         lmin=float(ev[0]),lmax=float(ev[2]),gamma=float(ev[0]/ev[2]),
                         n=int(ok.sum()) if ok is not None else 0))
# 汇总
import collections
by=collections.defaultdict(list)
for r in rows: by[r['frame']].append(r['nees'])
frames=sorted(by)
ne=np.array([np.mean(by[f]) for f in frames])
ga=np.array([next(r['gamma'] for r in rows if r['frame']==f) for f in frames])
print(f"帧数 {len(frames)}  (每帧 {NPERT} 次扰动)  σ_range={SIGMA}")
print(f"NEES  均 {ne.mean():.2f}  中位 {np.median(ne):.2f}  P95 {np.percentile(ne,95):.2f}")
print(f"γ_min 中位 {np.median(ga):.5f}  P05 {np.percentile(ga,5):.5f}  min {ga.min():.6f}")
for q in (10,25,50,75,90):
    t=np.percentile(ga,q)
    m=ga<=t
    print(f"  γ<={t:.5f} (n={m.sum():3d}): NEES 均 {ne[m].mean():7.2f} 中位 {np.median(ne[m]):7.2f}")
json.dump(rows,open('res_'+NPZ.replace('.npz','')+'.json','w'))
