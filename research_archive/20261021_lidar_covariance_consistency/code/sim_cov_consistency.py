#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sim_cov_consistency.py — 纯 Python 仿真：2D 扫描匹配的 Hessian 协方差是否过度自信？

回答 Day 3–4 的核心问题，但用**仿真**而非真实数据：
  Q: 在近退化几何（长走廊）下，H⁻¹ 给出的预测协方差，会不会系统性小于真实误差？

更重要的一层：**把失配的来源拆开**
  S0 理想条件（精确对应 + 正确噪声 + 精确地图）→ NEES 应 ≈ 2（若无偏且线性）
  S1 加地图误差（匹配器用的地图偏了 2 cm）
  S2 加对应模糊（近邻关联，点可能连错面）
  S3 特征稀少（走廊里只有 2 个门框）

如果 S0 的 NEES ≈ 2 而 S1/S2 远大于 2，那说明：
  **问题不在 Hessian 公式本身，而在对应关系与地图——那是完全不同的论文。**

用法：python3 sim_cov_consistency.py
"""

import math
import random


# ---------------------------------------------------------------- 几何
class Seg:
    """二维线段 + 单位法向。"""
    __slots__ = ("a", "b", "n", "tag")

    def __init__(self, a, b, tag=""):
        self.a, self.b, self.tag = a, b, tag
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        # 法向：线段方向左转 90°
        self.n = (-dy / L, dx / L)

    def ray(self, o, d):
        """射线 o + t d 与线段求交，返回 t>0 或 None。"""
        ax, ay = self.a
        bx, by = self.b
        ex, ey = bx - ax, by - ay
        den = d[0] * ey - d[1] * ex
        if abs(den) < 1e-12:
            return None
        t = ((ax - o[0]) * ey - (ay - o[1]) * ex) / den
        if t <= 1e-6:
            return None
        u = ((ax - o[0]) * d[1] - (ay - o[1]) * d[0]) / den
        if -1e-9 <= u <= 1 + 1e-9:
            return t
        return None

    def nearest(self, p):
        """点到线段的最近点与距离。"""
        ax, ay = self.a
        bx, by = self.b
        ex, ey = bx - ax, by - ay
        L2 = ex * ex + ey * ey
        t = ((p[0] - ax) * ex + (p[1] - ay) * ey) / L2
        t = max(0.0, min(1.0, t))
        q = (ax + t * ex, ay + t * ey)
        return q, math.hypot(p[0] - q[0], p[1] - q[1])


def build_corridor(n_features=8, half_width=1.2, length=40.0, feat_depth=0.25,
                   feat_w=0.5, seed=1, shift=(0.0, 0.0)):
    """走廊：两侧墙 + 若干净 FEATURE 个门框状凸起。shift 用来模拟地图误差。"""
    rng = random.Random(seed)
    sx, sy = shift
    segs = []
    W, L = half_width, length
    # 两侧墙（分段，为了有法向朝向内部）
    segs.append(Seg((sx + 0.0, sy + W), (sx + L, sy + W), "wall_up"))
    segs.append(Seg((sx + L, sy - W), (sx + 0.0, sy - W), "wall_dn"))
    xs = sorted(rng.uniform(3.0, L - 3.0) for _ in range(n_features))
    for i, xc in enumerate(xs):
        side = 1.0 if i % 2 == 0 else -1.0
        yw = side * W
        yf = side * (W - feat_depth)
        x0, x1 = xc - feat_w / 2, xc + feat_w / 2
        # 面向走廊的凸起面（法向沿 y）
        if side > 0:
            segs.append(Seg((sx + x0, sy + yf), (sx + x1, sy + yf), "feat_f"))
            segs.append(Seg((sx + x0, sy + yf), (sx + x0, sy + yw), "feat_s"))
            segs.append(Seg((sx + x1, sy + yw), (sx + x1, sy + yf), "feat_s"))
        else:
            segs.append(Seg((sx + x1, sy + yf), (sx + x0, sy + yf), "feat_f"))
            segs.append(Seg((sx + x1, sy + yf), (sx + x1, sy + yw), "feat_s"))
            segs.append(Seg((sx + x0, sy + yw), (sx + x0, sy + yf), "feat_s"))
    return segs


def scan(segs, pose, n_beams=360, rmax=20.0, sigma=0.02, rng=None):
    """从 pose 出发做一次扫描，返回 [(世界坐标点, 击中线段)]。"""
    px, py, th = pose
    out = []
    for k in range(n_beams):
        ang = -math.pi + 2 * math.pi * k / n_beams
        d = (math.cos(ang), math.sin(ang))
        o = (px, py)
        best_t, best_s = None, None
        for s in segs:
            t = s.ray(o, d)
            if t is not None and t <= rmax and (best_t is None or t < best_t):
                best_t, best_s = t, s
        if best_s is None:
            continue
        r = best_t + (rng.gauss(0, sigma) if rng else 0.0)
        p = (px + r * d[0], py + r * d[1])
        out.append((p, best_s))
    return out


# ---------------------------------------------------------------- 匹配
def transform(p, t):
    c, s = math.cos(t[2]), math.sin(t[2])
    return (c * p[0] - s * p[1] + t[0], s * p[0] + c * p[1] + t[1])


def icp(scan_pts, world_pts, init, sigma=0.02, iters=25, near_pool=None):
    """
    点-线 ICP（Gauss-Newton）。
    scan_pts: 传感器系下的点；world_pts: 它们在真值世界系下的落点（用于最近邻关联）
    near_pool: 若给，则按"世界系里最近的点"重新关联（模拟对应模糊）
    """
    t = list(init)
    H = None
    for _ in range(iters):
        JtJ = [[0.0] * 3 for _ in range(3)]
        Jtb = [0.0, 0.0, 0.0]
        for i, p in enumerate(scan_pts):
            pw = transform(p, t)
            # 关联
            if near_pool is not None and i < len(near_pool):
                q, nrm = near_pool[i]
            else:
                q, nrm = None, None
            if q is None:
                continue
            r = nrm[0] * (pw[0] - q[0]) + nrm[1] * (pw[1] - q[1])
            # 法向 n；J = [nx, ny, -pwy*nx + pwx*ny]
            j = (nrm[0], nrm[1], -pw[1] * nrm[0] + pw[0] * nrm[1])
            w = 1.0 / (sigma * sigma)
            for a in range(3):
                Jtb[a] += w * j[a] * r
                for b in range(3):
                    JtJ[a][b] += w * j[a] * j[b]
        H = JtJ
        dx = solve3(JtJ, [-x for x in Jtb])
        if dx is None:
            break
        t[0] += dx[0]; t[1] += dx[1]; t[2] += dx[2]
        if max(abs(dx[0]), abs(dx[1]), abs(dx[2])) < 1e-6:
            break
    return t, H


def solve3(A, b):
    import copy
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    n = 3
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[piv][c]) < 1e-18:
            return None
        M[c], M[piv] = M[piv], M[c]
        for r in range(n):
            if r == c:
                continue
            f = M[r][c] / M[c][c]
            for k in range(c, n + 1):
                M[r][k] -= f * M[c][k]
    return [M[i][n] / M[i][i] for i in range(n)]


def inv3_pinv(M):
    """对称半正定 3x3 伪逆（用于退化情况）。"""
    # 用特征分解不必要；这里用简单的 SVD-free 方法：加小正则后求逆
    tr = M[0][0] + M[1][1] + M[2][2]
    eps = max(tr, 1e-12) * 1e-9
    A = [[M[i][j] + (eps if i == j else 0.0) for j in range(3)] for i in range(3)]
    # 高斯-约当求逆
    M2 = [row[:] + [1.0 if i == j else 0.0 for j in range(3)] for i, row in enumerate(A)]
    n = 3
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M2[r][c]))
        if abs(M2[piv][c]) < 1e-18:
            return None
        M2[c], M2[piv] = M2[piv], M2[c]
        pv = M2[c][c]
        M2[c] = [x / pv for x in M2[c]]
        for r in range(n):
            if r == c:
                continue
            f = M2[r][c]
            M2[r] = [M2[r][k] - f * M2[c][k] for k in range(2 * n)]
    return [[M2[i][3 + j] for j in range(3)] for i in range(3)]


# ---------------------------------------------------------------- 单次试验
def trial(seed, n_features, map_error, ambiguous, n_beams=360, sigma=0.02,
          true_delta=(0.30, 0.06, 0.02)):
    """
    估计 pose1 相对 pose0 的相对运动 δ（在 pose0 坐标系下表达）。
    真实 δ = true_delta；用 scan1（在 pose1 系下）与真值几何的对应点做点-线 ICP。
    """
    rng = random.Random(seed)
    segs_true = build_corridor(n_features=n_features, seed=seed % 97)
    segs_map = build_corridor(n_features=n_features, seed=seed % 97, shift=(map_error, 0.0))

    pose0 = (2.0, 0.0, 0.0)
    # pose1 = pose0 复合 true_delta（在 pose0 系下）
    c0, s0 = math.cos(pose0[2]), math.sin(pose0[2])
    pose1 = (pose0[0] + c0 * true_delta[0] - s0 * true_delta[1],
             pose0[1] + s0 * true_delta[0] + c0 * true_delta[1],
             pose0[2] + true_delta[2])

    sc1 = scan(segs_true, pose1, n_beams=n_beams, sigma=sigma, rng=rng)
    if len(sc1) < 30:
        return None

    # scan1 点转到 pose1 传感器系
    c, s_ = math.cos(-pose1[2]), math.sin(-pose1[2])
    pts = [(c * (p[0] - pose1[0]) - s_ * (p[1] - pose1[1]),
            s_ * (p[0] - pose1[0]) + c * (p[1] - pose1[1])) for p, _ in sc1]

    # 对应点 & 法向，全部表达在 pose0 系下
    cc, ss = math.cos(-pose0[2]), math.sin(-pose0[2])
    def to0(pw):
        dx, dy = pw[0] - pose0[0], pw[1] - pose0[1]
        return (cc * dx - ss * dy, ss * dx + cc * dy)
    def n0(nw):
        return (cc * nw[0] - ss * nw[1], ss * nw[0] + cc * nw[1])

    near_pool = []
    for pwt, sg in sc1:
        if ambiguous:
            # 用"匹配器地图"上的最近点（可能与真值面不同 → 对应错误）
            cand = segs_map
        else:
            cand = [x for x in segs_map if x.tag == sg.tag] or segs_map
        best = None
        for x in cand:
            q, d = x.nearest(pwt)
            if best is None or d < best[0]:
                best = (d, q, x.n)
        if best is None or best[0] > 0.35:
            near_pool.append((None, None))
        else:
            near_pool.append((to0(best[1]), n0(best[2])))

    est, H = icp(pts, None, (0.0, 0.0, 0.0), sigma=sigma, near_pool=near_pool)
    if H is None:
        return None

    e = (est[0] - true_delta[0], est[1] - true_delta[1], est[2] - true_delta[2])

    # NEES（二维位置）= e^T Σ^{-1} e，Σ = H^{-1}(2x2 位置块) → 等价于 e^T H e
    Hp = [[H[0][0], H[0][1]], [H[1][0], H[1][1]]]
    nees2 = (e[0] * (Hp[0][0] * e[0] + Hp[0][1] * e[1]) +
             e[1] * (Hp[1][0] * e[0] + Hp[1][1] * e[1]))
    Sig = inv3_pinv(H)
    if Sig is None:
        return None
    return dict(e_along=e[0], e_lat=e[1], e_th=e[2],
                s_along=math.sqrt(max(Sig[0][0], 0.0)),
                s_lat=math.sqrt(max(Sig[1][1], 0.0)),
                nees2=max(nees2, 0.0))


def safe_inv(x):
    return 1.0 / x if abs(x) > 1e-30 else 0.0


def run(name, **kw):
    res = []
    for k in range(240):
        r = trial(seed=k * 7 + 13, **kw)
        if r:
            res.append(r)
    if not res:
        print(f"{name:<34} 无有效样本"); return None
    ne = sorted(x["nees2"] for x in res)
    mean_nees = sum(ne) / len(ne)
    med = ne[len(ne) // 2]
    ea = sum(abs(x["e_along"]) for x in res) / len(res)
    el = sum(abs(x["e_lat"]) for x in res) / len(res)
    sa = sum(x["s_along"] for x in res) / len(res)
    sl = sum(x["s_lat"] for x in res) / len(res)
    print(f"{name:<34} NEES均 {mean_nees:8.2f}  中位 {med:8.2f}   "
          f"|沿走廊误差| {ea*100:6.2f}cm  预测σ {sa*100:6.2f}cm   "
          f"|横| {el*100:5.2f}cm  σ {sl*100:5.2f}cm")
    return dict(nees=mean_nees, ea=ea, sa=sa, el=el, sl=sl, n=len(res))


def main():
    print("仿真：走廊内扫描匹配，真实位移 (0.30, 0.06, 0.02) m/rad，测距噪声 2 cm")
    print("NEES 期望值 ≈ 2（二维位置）。远大于 2 = 协方差过度自信。\n")
    print(f"{'配置':<34}{'':<4}")
    print("-" * 118)
    base = dict(n_features=8, map_error=0.0, ambiguous=False)
    run("S0 理想（精确对应 + 精确地图）", **base)
    run("S1 地图偏移 2 cm", **dict(base, map_error=0.02))
    run("S2 对应模糊（近邻关联）", **dict(base, ambiguous=True))
    run("S3 特征稀少（只有 2 个）", **dict(base, n_features=2))
    run("S4 特征稀少 + 对应模糊", **dict(base, n_features=2, ambiguous=True))
    run("S5 极稀疏（0 个特征）", **dict(base, n_features=0))
    print("-" * 118)
    print("\n判读：")
    print("  · S0 ≈ 2  → Hessian 公式本身没错，问题来自别处")
    print("  · S1/S2 >> 2 → 失配来自**地图误差 / 对应关系**，不是几何退化")
    print("  · S3/S5 >> 2 → 失配确实与**几何退化**相关")
    print("  · 『|沿走廊误差|』远大于『预测σ』→ 方向性过度自信（这才是 B#1 想要的）")


if __name__ == "__main__":
    main()
