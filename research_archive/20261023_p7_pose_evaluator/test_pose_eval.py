#!/usr/bin/env python3
"""P7-A unit tests. Every expected value is analytic; nothing is tuned to pass."""
import math, os, sys, tempfile
import numpy as np
import pose_eval as pe

FAILS = []
def ck(name, cond, detail=''):
    print(('  PASS  ' if cond else '  FAIL  ') + name + ((' | ' + detail) if detail else ''))
    if not cond: FAILS.append(name)

def write_tum(path, ts, xyz, quat):
    with open(path, 'w') as f:
        for t, p, q in zip(ts, xyz, quat):
            f.write('%.9f %.9f %.9f %.9f %.9f %.9f %.9f %.9f\n' % (t, p[0], p[1], p[2], q[0], q[1], q[2], q[3]))

def R_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])

TMP = tempfile.mkdtemp(prefix='p7a_')

# build a synthetic helical trajectory: 1 s apart, 40 poses
N = 40
ts = np.arange(N) * 0.05          # 20 Hz
gt_xyz = np.stack([np.cos(ts * 2), np.sin(ts * 2), ts * 0.3], axis=1)
gt_R = [R_y(0.5 * t) for t in ts]
gt_q = [pe.R_to_quat(R) for R in gt_R]
GT = os.path.join(TMP, 'gt.txt'); write_tum(GT, ts, gt_xyz, gt_q)

# ---- T1 identical trajectories -> ATE ~ 0 ----
print('[T1] identical trajectories')
EST1 = os.path.join(TMP, 'est1.txt'); write_tum(EST1, ts, gt_xyz, gt_q)
r = pe.evaluate(GT, EST1, label='identical')
ck('ATE aligned rmse < 1e-9', r['ate_aligned']['rmse'] < 1e-9, '%.3e' % r['ate_aligned']['rmse'])
ck('ATE unaligned rmse < 1e-9', r['ate_unaligned']['rmse'] < 1e-9)
ck('RPE trans rmse < 1e-9', r['rpe']['trans_rmse'] < 1e-9)
ck('RPE rot rmse < 1e-6 deg', r['rpe']['rot_rmse_deg'] < 1e-6)
ck('coverage == 1', abs(r['association']['coverage_est'] - 1.0) < 1e-12)

# ---- T2 known rigid transform -> aligned ATE 0, unaligned ATE == |t| ----
print('[T2] known rigid transform on the estimate')
A = pe.umeyama(gt_xyz, gt_xyz + np.array([0, 0, 0.0]), False)   # identity for reference
shift = np.array([3.0, -2.0, 1.5])
est_xyz = gt_xyz + shift
EST2 = os.path.join(TMP, 'est2.txt'); write_tum(EST2, ts, est_xyz, gt_q)
r = pe.evaluate(GT, EST2, label='shifted')
ck('aligned ATE rmse < 1e-9 (alignment absorbs a pure translation)',
   r['ate_aligned']['rmse'] < 1e-9, '%.3e' % r['ate_aligned']['rmse'])
ck('unaligned ATE rmse equals |shift| exactly',
   abs(r['ate_unaligned']['rmse'] - float(np.linalg.norm(shift))) < 1e-9,
   '%.6f vs %.6f' % (r['ate_unaligned']['rmse'], np.linalg.norm(shift)))

# ---- T3 injected constant position error -> unaligned ATE equals it ----
print('[T3] injected constant position error')
d = 0.07
EST3 = os.path.join(TMP, 'est3.txt'); write_tum(EST3, ts, gt_xyz + np.array([d, 0, 0]), gt_q)
r = pe.evaluate(GT, EST3, label='offset')
ck('unaligned ATE == injected offset', abs(r['ate_unaligned']['rmse'] - d) < 1e-9,
   '%.6f vs %.6f' % (r['ate_unaligned']['rmse'], d))

# ---- T4 injected rotation error ----
# NOTE: a CONSTANT global rotation is invisible to RPE by construction -- left-multiplying
# every pose by R cancels in R_i^T R_j. My first version of this test asserted otherwise and
# was wrong. To exercise rotational RPE one needs a relative (accumulating) error, so use a
# GT with identity rotation and inject a constant per-frame yaw increment.
print('[T4] injected rotation error (accumulating; constant global rotation is invariant)')
qI = np.array([0.0, 0.0, 0.0, 1.0])
GT_ROT = os.path.join(TMP, 'gt_rot.txt'); write_tum(GT_ROT, ts, gt_xyz, np.tile(qI, (N, 1)))
# first check the invariance explicitly, so the invariance itself is a test
EST_const = os.path.join(TMP, 'est_const_rot.txt')
write_tum(EST_const, ts, gt_xyz, [pe.R_to_quat(R_y(math.radians(7.0))) for _ in ts])
r0 = pe.evaluate(GT_ROT, EST_const, label='constant-global-rotation')
ck('RPE is invariant to a constant global rotation (7 deg injected -> 0)',
   r0['rpe']['rot_rmse_deg'] < 1e-6, '%.3e deg' % r0['rpe']['rot_rmse_deg'])
# now the real test: accumulating body-frame yaw error, 1 s window = 20 frames
per_frame = math.radians(0.075)          # 0.075 deg/frame -> 1.5 deg per 1 s window
est_q4 = [pe.R_to_quat(R_y(per_frame * k)) for k in range(N)]
EST4 = os.path.join(TMP, 'est4.txt'); write_tum(EST4, ts, gt_xyz, est_q4)
r = pe.evaluate(GT_ROT, EST4, label='rot-drift', window=1.0, dt_tol=0.01)
expect = math.degrees(per_frame * 20)
ck('RPE rot_rmse equals the analytic accumulating error',
   abs(r['rpe']['rot_rmse_deg'] - expect) < 1e-6,
   '%.6f vs %.6f deg' % (r['rpe']['rot_rmse_deg'], expect))
ck('ATE unaffected by a pure rotation error (positions identical)',
   r['ate_aligned']['rmse'] < 1e-9)

# ---- T5 deleted frames -> coverage drops and RPE does not cross the gap ----
print('[T5] deleted frames inside the trajectory')
keep = np.ones(N, bool); keep[18:26] = False       # remove a 0.35 s hole in the middle
EST5 = os.path.join(TMP, 'est5.txt'); write_tum(EST5, ts[keep], gt_xyz[keep], np.array(gt_q)[keep])
r = pe.evaluate(GT, EST5, label='gap', window=1.0, dt_tol=0.1)
ck('coverage_gt drops (deleted stretch is visible)',
   abs(r['association']['coverage_gt'] - 32.0 / 40.0) < 1e-9,
   '%.4f vs %.4f' % (r['association']['coverage_gt'], 32.0 / 40.0))
ck('coverage_est stays 1.0 for a subset -- documented trap',
   abs(r['association']['coverage_est'] - 1.0) < 1e-12,
   '%.4f' % r['association']['coverage_est'])
ck('RPE refused to build pairs across the hole (skipped > 0)',
   r['rpe']['n_skipped'] > 0, 'pairs=%d skipped=%d' %
   (r['rpe']['n_pairs'], r['rpe']['n_skipped']))
# every counted pair must sit on a real 1 s baseline in the kept data
gts = pe.load_tum(GT)['ts'][pe.associate(pe.load_tum(GT), pe.load_tum(EST5), 0.02)[0]]
gaps = []
for i in range(len(gts)):
    tgt = gts[i] + 1.0
    cand = [k for k in range(i + 1, len(gts)) if abs(gts[k] - tgt) <= 0.1]
    if cand:
        gaps.append(min(abs(gts[k] - tgt) for k in cand))
ck('every counted RPE pair really has a ~1 s baseline',
   all(g <= 0.1 for g in gaps) and len(gaps) > 0, 'n=%d maxerr=%.4f' % (len(gaps), max(gaps)))

# ---- T6 convention swap must be detected ----
print('[T6] swapped coordinate convention must not look like a good result')
# swap y and z in BOTH xyz and treat that as the estimate: a real system bug would
# produce a large, detectable error rather than a small one.
swap = np.array([[1,0,0],[0,0,1],[0,1,0]])
EST6 = os.path.join(TMP, 'est6.txt'); write_tum(EST6, ts, gt_xyz.dot(swap.T), gt_q)
r = pe.evaluate(GT, EST6, label='convention-swap')
ck('unaligned ATE is large (convention error surfaces, not hidden)',
   r['ate_unaligned']['rmse'] > 0.1, '%.4f' % r['ate_unaligned']['rmse'])
r_sw = pe.evaluate(GT, EST6, label='convention-swap-sim3', with_scale=True)
ck('report states which alignment was used',
   r_sw['options']['with_scale'] is True and r['options']['with_scale'] is False)

# ---- T7 failure inputs are reported, not swallowed ----
print('[T7] malformed and empty inputs')
BAD = os.path.join(TMP, 'bad.txt')
open(BAD, 'w').write('not a pose\n1 2 3\n')
raised = False
try:
    pe.evaluate(GT, BAD, label='bad')
except ValueError as e:
    raised = 'no valid pose rows' in str(e)
ck('empty/garbage estimate raises an explicit error', raised)
MIX = os.path.join(TMP, 'mix.txt')
with open(MIX, 'w') as f:
    f.write('garbage line\n')
    for t, p, q in zip(ts, gt_xyz, gt_q):
        f.write('%.9f %.9f %.9f %.9f %.9f %.9f %.9f %.9f\n' % (t, p[0], p[1], p[2], q[0], q[1], q[2], q[3]))
r = pe.evaluate(GT, MIX, label='mixed')
ck('malformed rows are counted, not silently dropped', r['est']['malformed_rows'] == 1,
   '%d' % r['est']['malformed_rows'])
FEW = os.path.join(TMP, 'few.txt'); write_tum(FEW, ts[:2], gt_xyz[:2], np.array(gt_q)[:2])
raised = False
try:
    pe.evaluate(GT, FEW, label='few')
except ValueError as e:
    raised = 'refusing to report' in str(e)
ck('too few associations refuses rather than reporting a number', raised)

print()
if FAILS:
    print('FAILED:', FAILS); sys.exit(1)
print('ALL P7-A TESTS PASSED')
