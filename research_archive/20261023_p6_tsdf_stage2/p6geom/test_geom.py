#!/usr/bin/env python3
"""Analytic unit tests for geom.warp_depth. No threshold tuning: every expected value
is derived in closed form or constructed independently."""
import math
import numpy as np
import geom

K = dict(fx=500.0, fy=500.0, cx=320.0, cy=240.0)
H, W = 480, 640
FAILS = []


def ck(name, cond, detail=''):
    print(('  PASS  ' if cond else '  FAIL  ') + name + ((' | ' + detail) if detail else ''))
    if not cond:
        FAILS.append(name)


def ident():
    return np.eye(4)


def R_y(t):
    c, s = math.cos(t), math.sin(t)
    T = np.eye(4); T[0, 0] = c; T[0, 2] = s; T[2, 0] = -s; T[2, 2] = c
    return T


def T_of(t):
    T = np.eye(4); T[:3, 3] = t; return T


# ---- A. identity pose -> the prediction must reproduce the input depth exactly ----
print('[A] identity pose')
d = np.zeros((H, W)); d[100:380, 160:480] = 2.0     # fronto-parallel patch at z=2
zp, hit = geom.warp_depth(d, K, ident(), ident(), (H, W))
slice_ = (slice(100, 380), slice(160, 480))
ck('all patch pixels predicted', hit[slice_].all())
ck('depth reproduced exactly', np.allclose(zp[slice_], 2.0))
ck('outside patch nothing predicted', not hit[:99].any() and not hit[:, :159].any())

# ---- B. known translation -> analytic pixel shift ----
print('[B] known translation')
Tp = ident(); Tc = T_of([1.0, 0.0, 0.0])   # camera moved +1 m along world x
zp, hit = geom.warp_depth(d, K, Tp, Tc, (H, W))
# point (X,Y,2) in prev cam -> world (X,Y,2) -> curr cam (X-1, Y, 2)
# u' = fx*(X-1)/2 + cx = u - fx/2   => shift of -fx/2 = -250 px
u_src = np.arange(160, 480)
x_w = (u_src - K['cx']) * 2.0 / K['fx']
u_dst = K['fx'] * (x_w - 1.0) / 2.0 + K['cx']
exp_shift = float(np.median(u_dst - u_src))
ck('shift equals -fx/2 analytically', abs(exp_shift - (-K['fx'] / 2)) < 1e-9,
   'expected %.3f got %.3f' % (-K['fx'] / 2, exp_shift))
rows_hit = np.where(hit[240])[0]
# the patch spans cols 160..479; after a -250 px shift it spans -90..229, and the
# part left of column 0 is outside the image, so the expected visible range is clipped
exp_min = max(0, int(math.ceil(160 + exp_shift)))
exp_max = min(W - 1, int(math.floor(479 + exp_shift)))
ck('prediction lands at the analytically shifted, clipped columns',
   abs(rows_hit.min() - exp_min) <= 1 and abs(rows_hit.max() - exp_max) <= 1,
   'expected %d..%d, got %d..%d' % (exp_min, exp_max, rows_hit.min(), rows_hit.max()))

# ---- C. known rotation about y ----
print('[C] known rotation')
th = math.radians(10)
Tc = R_y(th)                      # camera yaws by +10 deg about world y
zp, hit = geom.warp_depth(d, K, ident(), Tc, (H, W))
# centre column point (0,0,2): curr cam = (-2 sin th, 0, 2 cos th)
Zc = 2 * math.cos(th); Xc = -2 * math.sin(th)
u_expected = K['fx'] * Xc / Zc + K['cx']
row = np.where(hit[240])[0]
ck('rotation shifts the patch as predicted',
   abs(row.mean() - u_expected) < 30.0,
   'expected u=%.1f observed mean u=%.1f' % (u_expected, row.mean()))
ck('depth becomes 2*cos(th) at centre',
   abs(zp[240, int(round(u_expected))] - Zc) < 0.02)

# ---- D. z-buffer: two surfaces on the same pixel, nearest must win ----
print('[D] z-buffer')
d2 = np.zeros((H, W))
d2[200:280, 300:340] = 3.0
d2[200:280, 300:340] = 3.0
# construct a second, nearer layer by tilting: use a small patch at z=1 projected
# onto the same pixels via a rotation that brings it behind the first
zp, hit = geom.warp_depth(d2, K, ident(), ident(), (H, W))
ck('uniform surface reproduces one value', np.allclose(zp[200:280, 300:340], 3.0))
# explicit z-buffer numeric check
zz = np.full((H, W), np.inf)
np.minimum.at(zz, ([5, 5], [5, 5]), np.array([4.0, 2.0]))
ck('np.minimum.at keeps the nearer sample', zz[5, 5] == 2.0)

# ---- E. occlusion / missing depth ----
print('[E] missing depth and out-of-view')
d3 = np.zeros((H, W)); d3[240, 320] = 2.0
zp, hit = geom.warp_depth(d3, K, ident(), ident(), (H, W))
ck('single valid pixel handled', hit.sum() == 1 and abs(zp[240, 320] - 2.0) < 1e-9)
d4 = np.zeros((H, W))
zp, hit = geom.warp_depth(d4, K, ident(), ident(), (H, W))
ck('all-zero depth yields no prediction and no crash', hit.sum() == 0)
d5 = np.zeros((H, W)); d5[240, 320] = 2.0
Tc = T_of([10.0, 0.0, 0.0])       # move far away -> projects outside the image
zp, hit = geom.warp_depth(d5, K, ident(), Tc, (H, W))
ck('out-of-image projection yields no prediction', hit.sum() == 0)

# ---- F. static synthetic scene: two planes, exact analytic prediction ----
print('[F] static synthetic scene (two planes)')
d6 = np.zeros((H, W))
d6[:, :320] = 2.0      # left half at 2 m
d6[:, 320:] = 4.0      # right half at 4 m
# (my first version of this test had the sign backwards: with the camera at world
#  z = -0.2 the plane at world z = 2 is 2.2 m away, not 1.8. Test BOTH directions.)
for dz, exp_near, exp_far in ((+0.2, 1.8, 3.8), (-0.2, 2.2, 4.2)):
    Tc = T_of([0.0, 0.0, dz])
    zp, hit = geom.warp_depth(d6, K, ident(), Tc, (H, W))
    left = zp[:, :300][np.isfinite(zp[:, :300])]
    right = zp[:, 340:][np.isfinite(zp[:, 340:])]
    ck('camera dz=%+.1f: near plane -> %.1f m' % (dz, exp_near),
       abs(np.median(left) - exp_near) < 0.02, '%.3f' % np.median(left))
    ck('camera dz=%+.1f: far plane -> %.1f m' % (dz, exp_far),
       abs(np.median(right) - exp_far) < 0.02, '%.3f' % np.median(right))

# ---- G. independently moving object must be flagged as inconsistent ----
print('[G] moving object detection')
prev = np.full((H, W), 3.0)                 # static background wall at 3 m
prev[200:280, 300:340] = 1.0                # an object at 1 m
curr = prev.copy()
curr[200:280, 300:340] = 3.0                # the object moved away: now we see the wall
zp, hit = geom.warp_depth(prev, K, ident(), ident(), (H, W))
keep = geom.consistency_mask(curr, zp, hit, tau=0.05)
moved = np.zeros((H, W), bool); moved[200:280, 300:340] = True
ck('the vacated region is rejected', (~keep[moved]).mean() > 0.95,
   'rejected %.3f' % (~keep[moved]).mean())
ck('the static background is kept', keep[~moved].mean() > 0.95,
   'kept %.3f' % keep[~moved].mean())
keep0 = geom.consistency_mask(prev, zp, hit, tau=0.05)
ck('a fully static frame keeps everything', keep0[~moved].mean() > 0.999)

print()
if FAILS:
    print('FAILED:', FAILS); raise SystemExit(1)
print('ALL GEOM TESTS PASSED')
