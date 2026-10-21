import numpy as np, sys, json
from scanmatch import load_gt, gt_at, scans_to_pts, normals_from_scan

NPZ = sys.argv[1]; GT = sys.argv[2]
NFRAME = int(sys.argv[3]) if len(sys.argv)>3 else 120
NPERT  = int(sys.argv[4]) if len(sys.argv)>4 else 5
STEP   = int(sys.argv[5]) if len(sys.argv)>5 else 40
SIGMA  = 0.02
rng = np.random.default_rng(0)

d = np.load(NPZ)
ts = d["ts"]; R = d["ranges"]; meta = d["meta"]
gt_t, gt_p = load_gt(GT)
gp = gt_at(gt_t, gt_p, ts)
pts = scans_to_pts(R, meta, rmax=8.0)
print(f"scans {len(pts)}, gt poses {len(gt_p)}")

def build_grid(Q, cell):
    key = np.floor(Q/cell).astype(np.int64)
    g = {}
    for i,k in enumerate(map(tuple,key)): g.setdefault(k,[]).append(i)
    return {k:np.asarray(v) for k,v in g.items()}, cell

def nn_query(g, cell, Q, P):
    idx = np.full(len(P),-1); dist=np.full(len(P),1e9)
    ck = np.floor(P/cell).astype(np.int64)
    for i,k in enumerate(map(tuple,ck)):
        best=-1; bd=1e9
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                c = g.get((k[0]+dx,k[1]+dy))
                if c is None: continue
                dd = np.sum((Q[c]-P[i])**2,axis=1)
                j = dd.argmin()
                if dd[j]<bd: bd=dd[j]; best=c[j]
        idx[i]=best; dist[i]=np.sqrt(bd) if best>=0 else 1e9
    return idx,dist

rows=[]
frame_ids = list(range(1, len(pts), STEP))[:NFRAME]
for fi in frame_ids:
    P0 = pts[fi-1]
    if len(P0)<50: continue
    N0,k = normals_from_scan(P0)
    good = np.any(N0!=0,axis=1)
    P0g, N0g = P0[good], N0[good]
    if len(P0g)<40: continue
    # 目标：上一帧点，按 GT 相对位姿变换到当前帧的初始位姿参考
    gait = gp[fi-1]; gnow = gp[fi]
    dth = np.arctan2(np.sin(gnow[2]-gait[2]), np.cos(gnow[2]-gait[2]))
    c,s = np.cos(gait[2]), np.sin(gait[2])
    dx = c*(gnow[0]-gait[0]) + s*(gnow[1]-gait[1])
    dy = -s*(gnow[0]-gait[0]) + c*(gnow[1]-gait[1])
    true = np.array([dx,dy,dth])
    # 目标集：当前帧坐标系下的上一帧点
    Qw = P0g @ np.array([[np.cos(dth),np.sin(dth)],[-np.sin(dth),np.cos(dth)]]) + np.array([dx,dy])
    g, cell = build_grid(Qw, 0.3)
    nees=[]; lam=[]
    for pi in range(NPERT):
        init = true + rng.normal(0,[0.08,0.08,0.02])
        x,y,th = init; H=None
        for it in range(15):
            c,s = np.cos(th), np.sin(th)
            Rm = np.array([[c,-s],[s,c]])
            P = P0g @ Rm.T + np.array([x,y])
            Nn = N0g @ Rm.T
            idx,dist = nn_query(g, cell, Qw, P)
            ok = dist<0.4
            if ok.sum()<10: break
            Pp,Np,Qq = P[ok],Nn[ok],Qw[idx[ok]]
            r = np.sum(Np*(Pp-Qq),axis=1)
            J = np.stack([Np[:,0],Np[:,1],-Pp[:,1]*Np[:,0]+Pp[:,0]*Np[:,1]],1)
            w = 1.0/(SIGMA*SIGMA)
            a=np.abs(r); hub=np.where(a<=0.10,1.0,0.10/np.maximum(a,1e-9))
            wj = w*hub
            JtJ=(J*wj[:,None]).T@J; Jtr=(J*wj[:,None]).T@r
            H=JtJ
            try: ddx = np.linalg.solve(JtJ+1e-9*np.eye(3), -Jtr)
            except: break
            x+=ddx[0]; y+=ddx[1]; th+=ddx[2]
            if np.max(np.abs(ddx))<1e-7: break
        if H is None: continue
        ev = np.linalg.eigvalsh(H)
        ev = np.maximum(ev, 1e-12)
        e = np.array([x,y,th]) - true
        e[2] = np.arctan2(np.sin(e[2]),np.cos(e[2]))
        nees.append(float(e @ (H @ e)))
        lam.append(ev)
    if nees:
        lam = np.array(lam).mean(0)
        rows.append(dict(frame=int(fi), nees=float(np.mean(nees)),
                         lmin=float(lam[0]), lmax=float(lam[2]),
                         gamma=float(lam[0]/lam[2]), n=int(ok.sum())))
print(f"frames analysed: {len(rows)}")
ne = np.array([r['nees'] for r in rows])
ga = np.array([r['gamma'] for r in rows])
print(f"NEES mean {ne.mean():.2f} median {np.median(ne):.2f} p95 {np.percentile(ne,95):.2f} max {ne.max():.2f}")
print(f"gamma  median {np.median(ga):.4f}  p05 {np.percentile(ga,5):.4f}  min {ga.min():.5f}")
# 按退化程度分组
thr = np.percentile(ga, 25)
grpA = ne[ga<=thr]; grpB = ne[ga>thr]
print(f"\n最退化的 25% 帧 (gamma<={thr:.4f}): NEES mean {grpA.mean():.2f} median {np.median(grpA):.2f}")
print(f"较正常的 75% 帧            : NEES mean {grpB.mean():.2f} median {np.median(grpB):.2f}")
json.dump(rows, open('consistency_'+NPZ.replace('.npz','')+'.json','w'))
