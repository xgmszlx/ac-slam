#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cov_consistency.py — Day 3–5 的一致性分析（纯 Python，零依赖）

判断：2D 扫描匹配输出的协方差，在退化几何下是否系统性偏乐观？
以及：现成的修正方法（标量膨胀 / 方向抑制 / 场景自适应）够不够？

输入：逐帧 CSV，每行一次扫描匹配
必需列（列名匹配即可，大小写不敏感）：
    sid                 帧标识
    sigma_along         预测的沿走廊方向标准差 (m)
    sigma_lat           预测的横向标准差 (m)
    err_along           真实的沿走廊方向误差 (m)
    err_lat             真实的横向误差 (m)
可选列：
    sigma_theta, err_theta      转角（rad）
    lambda_min, lambda_max      现有退化判据
    group               场景标签（如 A_normal / B_corridor）
    sigma_along_c2 ...  C2(方向抑制) 方案给出的对应 σ
    sigma_along_c3 ...  C3(场景自适应) 方案给出的对应 σ
    sigma_along_c1_k1 / _k2 ...  标量膨胀方案（每次一个 k）

输出：分场景、分方案的 NEES 与结论。

用法：
  python3 cov_consistency.py frames.csv
  python3 cov_consistency.py frames.csv --group-col group
  python3 cov_consistency.py frames.csv --bootstrap 2000
"""

import argparse
import csv
import math
import random
import sys


def fnum(row, *names):
    for n in names:
        for k in row:
            if k.lower() == n.lower():
                try:
                    return float(row[k])
                except (TypeError, ValueError):
                    return None
    return None


def mean(v):
    return sum(v) / len(v) if v else float("nan")


def std(v):
    if len(v) < 2:
        return float("nan")
    m = mean(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))


def pct(v, q):
    if not v:
        return float("nan")
    s = sorted(v)
    return s[min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))]


def load(path, group_col):
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        rd = csv.DictReader(f)
        for r in rd:
            d = dict(r)
            for k in list(d):
                if k is None:
                    continue
            sa = fnum(r, "sigma_along")
            sl = fnum(r, "sigma_lat")
            ea = fnum(r, "err_along")
            el = fnum(r, "err_lat")
            if None in (sa, sl, ea, el):
                continue
            if sa <= 0 or sl <= 0:
                continue
            g = r.get(group_col) if group_col and group_col in r else (r.get("group") or "all")
            rec = dict(group=(g or "all").strip(), sa=sa, sl=sl, ea=ea, el=el,
                       st=fnum(r, "sigma_theta"), et=fnum(r, "err_theta"),
                       lmin=fnum(r, "lambda_min"), lmax=fnum(r, "lambda_max"),
                       raw=r)
            rows.append(rec)
    return rows


def nees_series(rows, sa_key="sa", sl_key="sl", st_key="st", et_key="et"):
    """按行计算 NEES。缺 theta 时只算位置（2 自由度）。"""
    out = {"nees2": [], "nees3": []}
    for r in rows:
        n2 = (r["ea"] / r[sa_key]) ** 2 + (r["el"] / r[sl_key]) ** 2
        out["nees2"].append(n2)
        if r[st_key] and r[et_key] is not None and r[st_key] > 0:
            out["nees3"].append(n2 + (r[et_key] / r[st_key]) ** 2)
    return out


def block_bootstrap_ci(vals, n=2000, frac=0.25, seed=0):
    """分块 bootstrap：相邻帧相关，不能当独立样本。返回 NEES 均值的 95% 区间。"""
    if len(vals) < 10:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    m = mean(vals)
    L = max(2, int(len(vals) * frac))
    boots = []
    for _ in range(n):
        acc = []
        while len(acc) < len(vals):
            s = rng.randrange(0, len(vals))
            acc.extend(vals[s:s + L])
        boots.append(mean(acc[:len(vals)]))
    boots.sort()
    return (boots[int(0.025 * n)], boots[int(0.975 * n)])


def verdict(vals, dof):
    """NEES 均值应≈dof。返回状态。"""
    m = mean(vals)
    if not vals:
        return "无数据", 0.0
    ratio = m / dof
    if 0.5 <= ratio <= 2.0:
        st = "🟢 一致（协方差可信）"
    elif 2.0 < ratio <= 10.0:
        st = "🟡 偏乐观（低估误差）"
    elif ratio > 10.0:
        st = "🔴 严重低估（过度自信）"
    elif ratio < 0.5:
        st = "🔵 偏保守（高估误差）"
    else:
        st = "?"
    return st, ratio


def report_group(name, rows, dof_key="nees2"):
    print(f"\n{'='*68}\n场景 [{name}]  样本 {len(rows)}")
    if not rows:
        print("  无有效样本"); return
    s = nees_series(rows)
    vals = s[dof_key]
    if not vals:
        print("  无法计算 NEES（缺 theta 时用 2 自由度）"); vals = s["nees2"]
    dof = 3 if dof_key == "nees3" else 2
    st, ratio = verdict(vals, dof)
    lo, hi = block_bootstrap_ci(vals)
    print(f"  NEES 均值 {mean(vals):8.2f}  中位 {pct(vals,0.5):8.2f}  P95 {pct(vals,0.95):8.2f}")
    print(f"  期望值 ≈ {dof}   →  比值 {ratio:.2f}")
    print(f"  分块 bootstrap 95% CI: [{lo:.2f}, {hi:.2f}]")
    print(f"  判定：{st}")
    # 方向分解
    ra = [r["ea"] / r["sa"] for r in rows]
    rl = [r["el"] / r["sl"] for r in rows]
    print(f"  沿走廊方向 err/σ: 均 {mean(ra):+.2f}  绝对均 {mean([abs(x) for x in ra]):.2f}"
          f"  P95|.| {pct([abs(x) for x in ra],0.95):.2f}")
    print(f"  横向    方向 err/σ: 均 {mean(rl):+.2f}  绝对均 {mean([abs(x) for x in rl]):.2f}"
          f"  P95|.| {pct([abs(x) for x in rl],0.95):.2f}")
    print("  ↑ 若沿走廊的 |err/σ| 显著大于横向 → 失配是**方向性的**（这才是你要的证据）")


def compare_plans(all_rows, groups):
    """Day5：把 C0 / C1(k) / C2 / C3 放在一起比。"""
    print(f"\n{'='*68}\nDay 5 · 修正方案对照")
    cands = []
    # C0 原始：用解析后的值，不从原始行查列
    cands.append(("C0 原始", None, None, None))
    # C1 标量膨胀：找所有 sigma_along_c1_k* 列
    keys = set()
    for r in all_rows:
        for k in r["raw"]:
            kl = k.lower()
            if kl.startswith("sigma_along_c1"):
                keys.add(k)
    def _knum(x):
        import re as _re
        m=_re.search(r"(\d+)$", x)
        return int(m.group(1)) if m else 0
    for k in sorted(keys, key=_knum):
        sl_key = k.lower().replace("sigma_along", "sigma_lat")
        st_key = k.lower().replace("sigma_along", "sigma_theta")
        cands.append((f"{k}", k, sl_key, st_key))
    # C2 / C3
    for tag in ("c2", "c3"):
        if any(f"sigma_along_{tag}" in {kk.lower() for kk in r["raw"]} for r in all_rows):
            cands.append((f"{tag.upper()} 方案", f"sigma_along_{tag}", f"sigma_lat_{tag}", f"sigma_theta_{tag}"))

    for gname, rows in groups.items():
        print(f"\n-- 场景 [{gname}] --")
        print(f"{'方案':<22}{'NEES均值':>10}{'比值(dof=2)':>13}{'判定':>26}")
        best = None
        for label, ka, kl, kt in cands:
            sub = []
            for r in rows:
                if ka is None:
                    sa, sl = r["sa"], r["sl"]
                else:
                    sa, sl = fnum(r["raw"], ka), fnum(r["raw"], kl)
                if not sa or not sl or sa <= 0 or sl <= 0:
                    continue
                sub.append(dict(r, sa=sa, sl=sl))
            if len(sub) < 10:
                print(f"{label:<22}{'样本不足':>10}")
                continue
            vals = nees_series(sub)["nees2"]
            st, ratio = verdict(vals, 2)
            print(f"{label:<22}{mean(vals):>10.2f}{ratio:>13.2f}{st:>26}")
            score = abs(math.log(max(ratio, 1e-9)))
            if best is None or score < best[0]:
                best = (score, label, ratio)
        if best:
            print(f"  → 最接近一致的是 **{best[1]}**（比值 {best[2]:.2f}）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--group-col", default="group")
    ap.add_argument("--bootstrap", type=int, default=2000)
    a = ap.parse_args()

    rows = load(a.csv, a.group_col)
    if not rows:
        print("❌ 没读到有效行。检查列名：sigma_along / sigma_lat / err_along / err_lat")
        return 1

    groups = {}
    for r in rows:
        groups.setdefault(r["group"], []).append(r)

    print(f"总样本 {len(rows)}；场景 {list(groups)}")
    for g, rs in groups.items():
        report_group(g, rs)

    # 跨场景对比：方向性失配是否只在退化场景出现
    if len(groups) >= 2:
        print(f"\n{'='*68}\n跨场景判据（这是关键）")
        print(f"{'场景':<18}{'沿走廊|err/σ|':>15}{'横向|err/σ|':>15}{'方向比':>10}")
        base = None
        for g, rs in groups.items():
            ra = mean([abs(r["ea"] / r["sa"]) for r in rs])
            rl = mean([abs(r["el"] / r["sl"]) for r in rs])
            ratio = ra / max(rl, 1e-9)
            print(f"{g:<18}{ra:>15.2f}{rl:>15.2f}{ratio:>10.2f}")
            if base is None:
                base = ra
        print("\n  判读：")
        print("  · 若退化场景的『沿走廊 |err/σ|』明显高于正常场景，且『方向比』也更高")
        print("    → 失配是**几何退化特异的**，B#1 的科学问题成立")
        print("  · 若两个场景差不多 → 是整体模型问题，不是退化特异 → 停")

    compare_plans(rows, groups)
    return 0


if __name__ == "__main__":
    sys.exit(main())
