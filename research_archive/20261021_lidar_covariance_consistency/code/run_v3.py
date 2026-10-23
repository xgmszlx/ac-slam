import numpy as np, sys, json
from scanmatch import load_gt, gt_at, scans_to_pts, normals_from_scan
NPZ=sys.argv[1]; GT=sys.argv[2]; SIG=float(sys.argv[3]); TAG=sys.argv[4]
NFRAME=int(sys.argv[5]) if len(sys.argv)>5 else 60
rng=np.random.default_rng(1)
d=np.load(NPZ); ts=d["ts"]; R=d["ranges"]; meta=d["meta"]
gt_t,gt_p=load_gt(GT); gp=gt_at(gt_t,gt_p,ts); pts=scans_to_pts(R,meta,rmax=8.0)
CELL=0.3
def build_grid(Q):
    key=np.floor(Q/CELL).astype(np.int64); g={}
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
for fi in list(range(1,len(pts),40))[:NFRAME]:
    P0=pts[fi][::4]; Q0=pts[fi-1][::4]
    if len(P0)<60 or len(Q0)<60: continue
    N0,_=normals_from_scan(P0); good=np.any(N0!=0,axis=1); P0,N0=P0[good],N0[good]
    if len(P0)<50: continue
    a=gp[fi-1]; b=gp[fi]
    dth=np.arctan2(np.sin(b[2]-a[2]),np.cos(b[2]-a[2]))
    ca,sa=np.cos(-a[2]),np.sin(-a[2]); dxw,dyw=b[0]-a[0],b[1]-a[1]
    true=np.array([ca*dxw-sa*dyw, sa*dxw+ca*dyw, dth])
    g=build_grid(Q0)
    for pi in range(4):
        init=true+rng.normal(0,[0.05,0.05,0.01]); x,y,th=init; H=None; okn=0
        for it in range(20):
            c,s=np.cos(th),np.sin(th); Rm=np.array([[c,-s],[s,c]])
            P=P0@Rm.T+np.array([x,y]); Nn=N0@Rm.T
            idx,dist=nn_query(g,Q0,P); ok=dist<0.35; okn=int(ok.sum())
            if okn<12: break
            Pp,Np,Qq=P[ok],Nn[ok],Q0[idx[ok]]
            r=np.sum(Np*(Pp-Qq),axis=1)
            J=np.stack([Np[:,0],Np[:,1],-Pp[:,1]*Np[:,0]+Pp[:,0]*Np[:,1]],1)
            aa=np.abs(r); hub=np.where(aa<=0.10,1.0,0.10/np.maximum(aa,1e-9))
            wj=(1.0/(SIG*SIG))*hub
            H=(J*wj[:,None]).T@J; Jtr=(J*wj[:,None]).T@r
            try: ddx=np.linalg.solve(H+1e-12*np.eye(3),-Jtr)
            except: break
            x+=ddx[0];y+=ddx[1];th+=ddx[2]
            if np.max(np.abs(ddx))<1e-8: break
        if H is None: continue
        e=np.array([x,y,th])-true; e[2]=np.arctan2(np.sin(e[2]),np.cos(e[2]))
        rows.append(dict(frame=int(fi),sigma=SIG,e=e.tolist(),H=H.tolist(),
                         n=okn,nees=float(e@(H@e))))
json.dump(rows,open('v3_%s.json'%TAG,'w'))
ne=np.array([r['nees'] for r in rows])
print(f"σ={SIG}  n={len(rows)}  NEES 均 {ne.mean():.2f} 中位 {np.median(ne):.2f}")
