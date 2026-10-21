import numpy as np, sys, json

def load_gt(path):
    d = np.loadtxt(path)
    t = d[:,0]; x = d[:,1]; y = d[:,2]
    qx,qy,qz,qw = d[:,4],d[:,5],d[:,6],d[:,7]
    yaw = np.arctan2(2*(qw*qz+qx*qy), 1-2*(qy*qy+qz*qz))
    return t, np.stack([x,y,yaw],1)

def gt_at(gt_t, gt_p, ts):
    out = np.empty((len(ts),3))
    for i,t in enumerate(ts):
        j = np.searchsorted(gt_t, t)
        j = min(max(j,1), len(gt_t)-1)
        a = (t-gt_t[j-1])/max(gt_t[j]-gt_t[j-1],1e-9)
        out[i] = gt_p[j-1]*(1-a) + gt_p[j]*a
        # wrap yaw
        d = out[i,2]-gt_p[j-1,2]
        out[i,2] = gt_p[j-1,2] + np.arctan2(np.sin(d),np.cos(d))*a
    return out

def scans_to_pts(R, meta, rmax=8.0):
    amin, inc, rmin, _ = meta
    n = R.shape[1]
    ang = amin + np.arange(n)*inc
    ca, sa = np.cos(ang), np.sin(ang)
    pts=[]
    for r in R:
        m = np.isfinite(r) & (r>=rmin) & (r<=rmax)
        pts.append(np.stack([r[m]*ca[m], r[m]*sa[m]],1).astype(np.float64))
    return pts

def normals_from_scan(P, k=3):
    """用扫描相邻点估法向。P 已按角度排序。返回单位法向。"""
    n = len(P)
    if n < 2*k+1: return np.zeros((0,2))
    d = P[2*k:] - P[:-2*k]           # 跨越 2k 个点
    L = np.linalg.norm(d,axis=1); good = L>1e-6
    N = np.zeros_like(P)
    t = np.zeros_like(P)
    t[k:n-k][good] = d[good]/L[good,None]
    # 法向 = 切线转90°
    N[:,0] = -t[:,1]; N[:,1] = t[:,0]
    return N, k

def T(theta, p):
    c,s = np.cos(theta), np.sin(theta)
    return np.array([[c,-s,p[0]],[s,c,p[1]],[0,0,1]])

def icp_pl(Pw, Nw, Q, pose, sigma=0.02, iters=20, cell=0.3, huber=0.1):
    """Pw/Nw: 扫描点及其法向(传感器系); Q: 目标点集(世界系); pose=(x,y,th)"""
    x,y,th = pose
    H = None
    for it in range(iters):
        c,s = np.cos(th), np.sin(th)
        Rm = np.array([[c,-s],[s,c]])
        P = Pw @ Rm.T + np.array([x,y])
        Nn = Nw @ Rm.T
        # 网格近邻
        idx, dist = nn_grid(Q, P, cell)
        ok = dist < 0.5
        if ok.sum() < 10: break
        Pp, Np, Qq = P[ok], Nn[ok], Q[idx[ok]]
        r = np.sum(Np*(Pp-Qq), axis=1)
        w = 1.0/(sigma*sigma)
        # Huber
        a = np.abs(r)
        hub = np.where(a<=huber, 1.0, huber/np.maximum(a,1e-9))
        wj = w*hub
        # J = [nx, ny, -pwy*nx + pwx*ny]
        J = np.stack([Np[:,0], Np[:,1], -Pp[:,1]*Np[:,0]+Pp[:,0]*Np[:,1]],1)
        JtJ = (J*wj[:,None]).T @ J
        Jtr = (J*wj[:,None]).T @ r
        H = JtJ
        try:
            dx = np.linalg.solve(JtJ + 1e-9*np.eye(3), -Jtr)
        except np.linalg.LinAlgError:
            break
        x += dx[0]; y += dx[1]; th += dx[2]
        if np.max(np.abs(dx)) < 1e-6: break
    return np.array([x,y,th]), H, it+1

def nn_grid(Q, P, cell):
    """返回每个 P 点在 Q 中的最近点索引与距离（体素哈希）。"""
    key = np.floor(Q/cell).astype(np.int64)
    d = {}
    for i,k in enumerate(map(tuple,key)):
        d.setdefault(k,[]).append(i)
    idx = np.full(len(P), -1); dist = np.full(len(P), 1e9)
    cellQ = np.floor(P/cell).astype(np.int64)
    for i,k in enumerate(map(tuple,cellQ)):
        best=-1; bd=1e9
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                cand = d.get((k[0]+dx, k[1]+dy))
                if not cand: continue
                cand = np.asarray(cand)
                dd = np.sum((Q[cand]-P[i])**2, axis=1)
                j = np.argmin(dd)
                if dd[j] < bd: bd=dd[j]; best=cand[j]
        idx[i]=best; dist[i]=np.sqrt(bd) if best>=0 else 1e9
    return idx, dist
