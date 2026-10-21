#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_laser_info.py — 把 2DLIW-SLAM 的激光信息矩阵导出，变成一致性检验表

输入：
  1) laser_info.csv   —— PATCH_laser_info.md 导出的逐帧文件
     列：index, n_lines, p0,p1,p2, q0,q1,q2, Hp(9 行优先), Hq(9 行优先)
  2) GT 轨迹（TUM 格式：timestamp tx ty tz qx qy qz qw），可选
     —— 不给 GT 也能跑，只做"信息矩阵结构分析"（秩、方向性）

输出：
  frames.csv —— 直接喂给 cov_consistency.py
     列：group, sigma_along, sigma_lat, err_along, err_lat, sigma_theta, err_theta

用法：
  python3 analyze_laser_info.py laser_info.csv
  python3 analyze_laser_info.py laser_info.csv --gt groundtruth.txt
  python3 analyze_laser_info.py laser_info.csv --gt gt.txt --corridor-axis x
"""

import argparse
import csv
import math
import sys


def parse_dump(path):
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for ln, raw in enumerate(f, 1):
            s = raw.strip()
            if not s or s.startswith("#"):
                continue
            p = s.split(",")
            if len(p) < 26:
                continue
            try:
                d = dict(
                    idx=int(float(p[0])), n=int(float(p[1])),
                    px=float(p[2]), py=float(p[3]), pz=float(p[4]),
                    qx=float(p[5]), qy=float(p[6]), qz=float(p[7]),
                )
                v = [float(x) for x in p[8:26]]
                d["Hp"] = [v[0:3], v[3:6], v[6:9]]
                d["Hq"] = [v[9:12], v[12:15], v[15:18]]
                rows.append(d)
            except ValueError:
                continue
    return rows


def log_to_yaw(qx, qy, qz):
    """SO(3) log 向量 → yaw（绕 z）。"""
    th = math.sqrt(qx * qx + qy * qy + qz * qz)
    if th < 1e-12:
        return 0.0
    # 旋转矩阵里 yaw 的提取
    kx, ky, kz = qx / th, qy / th, qz / th
    c, s = math.cos(th), math.sin(th)
    v = 1 - c
    # R[1][0] = kx*ky*v + kz*s ; yaw = atan2(R10, R00)
    R00 = kx * kx * v + c
    R10 = kx * ky * v + kz * s
    return math.atan2(R10, R00)


def read_tum(path):
    out = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            s = raw.strip()
            if not s or s.startswith("#"):
                continue
            p = s.replace(",", " ").split()
            if len(p) < 8:
                continue
            try:
                t = float(p[0]); x = float(p[1]); y = float(p[2])
                qx, qy, qz, qw = map(float, p[4:8])
                yaw = math.atan2(2 * (qw * qz + qx * qy), 1 - 2 * (qy * qy + qz * qz))
                out.append((t, x, y, yaw))
            except ValueError:
                continue
    out.sort()
    return out


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def structure_report(rows, axis):
    """不给 GT 也能做：信息矩阵的秩与方向性。"""
    print("=" * 70)
    print("信息矩阵结构分析（不需要 GT）")
    print(f"{'idx':>5}{'n_ln':>6}{'Hp_xx':>12}{'Hp_yy':>12}{'Hp_xy':>12}"
          f"{'rank?':>8}{'σ_x(cm)':>10}{'σ_y(cm)':>10}{'dir_ratio':>11}")
    nan = float("nan")
    for d in rows[: min(len(rows), 400)]:
        Hx, Hy, Hxy = d["Hp"][0][0], d["Hp"][1][1], d["Hp"][0][1]
        det = Hx * Hy - Hxy * Hxy
        sx = 1 / math.sqrt(Hx) if Hx > 1e-18 else nan
        sy = 1 / math.sqrt(Hy) if Hy > 1e-18 else nan
        ratio = math.sqrt(Hx / Hy) if Hy > 1e-18 and Hx > 1e-18 else nan
        r = "full" if det > 1e-18 else ("rank1" if (Hx > 1e-18 or Hy > 1e-18) else "rank0")
        print(f"{d['idx']:>5}{d['n']:>6}{Hx:>12.4g}{Hy:>12.4g}{Hxy:>12.4g}"
              f"{r:>8}{sx*100 if sx==sx else nan:>10.3f}{sy*100 if sy==sy else nan:>10.3f}"
              f"{ratio:>11.3f}")

    # 汇总
    full = sum(1 for d in rows if d["Hp"][0][0] * d["Hp"][1][1] - d["Hp"][0][1] ** 2 > 1e-18)
    print(f"\n样本 {len(rows)} 帧；Hp 满秩(2x2) {full} 帧，"
          f"秩亏 {len(rows)-full} 帧 ({100*(len(rows)-full)/max(len(rows),1):.1f}%)")
    hy = [d["Hp"][1][1] for d in rows if d["Hp"][1][1] > 1e-18]
    hx = [d["Hp"][0][0] for d in rows if d["Hp"][0][0] > 1e-18]
    if hx and hy:
        import statistics as st
        print(f"Hp_xx 中位 {st.median(hx):.4g}  → σ_x 中位 {100/math.sqrt(st.median(hx)):.3f} cm")
        print(f"Hp_yy 中位 {st.median(hy):.4g}  → σ_y 中位 {100/math.sqrt(st.median(hy)):.3f} cm")
    print("\n判读：")
    print("  · 若大量帧 Hp 秩亏，且亏的是同一方向 → 那个方向就是退化的方向（实测，不靠阈值）")
    print("  · σ_x 与 σ_y 相差一个数量级以上 → 各向异性极强，任何各向同性协方差都会错")


def build_frames(rows, gt, axis):
    """把逐帧信息 + GT 的相对误差拼成 cov_consistency.py 要的表。"""
    # 按位置把估计帧对齐到 GT（用最近点）
    out = []
    for a, b in zip(rows[:-1], rows[1:]):
        # 估计的相对位姿
        dx = b["px"] - a["px"]; dy = b["py"] - a["py"]
        ya, yb = log_to_yaw(a["qx"], a["qy"], a["qz"]), log_to_yaw(b["qx"], b["qy"], b["qz"])
        dth = wrap(yb - ya)
        # 旋转到帧 a 的朝向（局部系）
        c, s = math.cos(-ya), math.sin(-ya)
        ex = c * dx - s * dy
        ey = s * dx + c * dy
        # 预测 σ（取 b 帧的信息，投影到同样的局部系）
        Hb = b["Hp"]
        # 局部系下的信息：R^T H R
        Hxx = c * c * Hb[0][0] - 2 * c * s * Hb[0][1] + s * s * Hb[1][1]
        Hyy = s * s * Hb[0][0] + 2 * c * s * Hb[0][1] + c * c * Hb[1][1]
        sx = 1 / math.sqrt(Hxx) if Hxx > 1e-18 else 1e3
        sy = 1 / math.sqrt(Hyy) if Hyy > 1e-18 else 1e3
        st = 1 / math.sqrt(b["Hq"][2][2]) if b["Hq"][2][2] > 1e-18 else 1e3

        rec = dict(sigma_along=sx, sigma_lat=sy, sigma_theta=st,
                   est_x=ex, est_y=ey, est_th=dth)
        if gt:
            # 找到 a、b 在 GT 里的最近点
            ia = min(range(len(gt)), key=lambda k: (gt[k][1]-a["px"])**2 + (gt[k][2]-a["py"])**2)
            ib = min(range(len(gt)), key=lambda k: (gt[k][1]-b["px"])**2 + (gt[k][2]-b["py"])**2)
            if ib > ia:
                gx = gt[ib][1] - gt[ia][1]; gy = gt[ib][2] - gt[ia][2]
                gth = wrap(gt[ib][3] - gt[ia][3])
                cg, sg = math.cos(-gt[ia][3]), math.sin(-gt[ia][3])
                gex = cg*gx - sg*gy; gey = sg*gx + cg*gy
                rec["err_along"] = ex - gex
                rec["err_lat"] = ey - gey
                rec["err_theta"] = wrap(dth - gth)
        out.append(rec)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("--gt", default=None)
    ap.add_argument("--corridor-axis", default="x", choices=["x", "y"])
    ap.add_argument("--out", default="frames.csv")
    a = ap.parse_args()

    rows = parse_dump(a.dump)
    if not rows:
        print("❌ 没读到数据。检查格式：index,n_lines,px,py,pz,qx,qy,qz,Hp*9,Hq*9")
        return 1
    print(f"读到 {len(rows)} 帧\n")

    structure_report(rows, a.corridor_axis)

    gt = read_tum(a.gt) if a.gt else None
    if not gt:
        print("\n（未给 GT，跳过 NEES。加 --gt groundtruth.txt 可得一致性检验）")
        return 0

    fr = build_frames(rows, gt, a.corridor_axis)
    fr = [x for x in fr if "err_along" in x]
    if not fr:
        print("❌ 无法与 GT 配对")
        return 1

    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["group", "sigma_along", "sigma_lat",
                                          "sigma_theta", "err_along", "err_lat", "err_theta"])
        w.writeheader()
        for x in fr:
            w.writerow(dict(group="all", sigma_along=x["sigma_along"], sigma_lat=x["sigma_lat"],
                            sigma_theta=x["sigma_theta"], err_along=x["err_along"],
                            err_lat=x["err_lat"], err_theta=x["err_theta"]))
    print(f"\n✅ 写出 {a.out}（{len(fr)} 行）→ 现在跑：")
    print(f"   python3 cov_consistency.py {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
