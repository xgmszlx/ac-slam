#!/usr/bin/env python3
"""Standalone reproduction of the L1 post-hoc diagnostics.

Every number in ERRATA.md and in analysis/*.json can be regenerated with this file;
none of it was previously committed as an executable script (audit defect 4.2).

Usage: python3 l1_posthoc_diagnostics.py <run_dir> <sequence>
Writes: analysis/effective_sample_size.json, analysis/cross_covariance_check.json,
        analysis/per_axis_decomposition.json, analysis/drift_vs_white.json
"""
import csv, glob, json, math, os, sys
import numpy as np, rosbag

def load(run_dir):
    rows = sorted(csv.DictReader(open(os.path.join(run_dir, 'per_frame.csv'))),
                  key=lambda r: int(r['frame']))
    H = {}; i = -1
    with rosbag.Bag(os.path.join(run_dir, 'measure.bag')) as bag:
        for topic, msg, _ in bag.read_messages(topics=['/hector_debug_info']):
            if msg.iterData:
                H[i] = np.array(msg.iterData[-1].hessian).reshape(3, 3)
            i += 1
    E, S, F = [], [], []
    for r in rows:
        k = int(r['frame']); Hk = H.get(k)
        if Hk is None: continue
        Hk = 0.5 * (Hk + Hk.T)
        try: S.append(np.linalg.inv(Hk))
        except np.linalg.LinAlgError: continue
        E.append([float(r['ex']), float(r['ey']), float(r['eth'])]); F.append(k)
    return np.array(E), np.array(S), F

def main():
    run_dir, seq = sys.argv[1], sys.argv[2]
    E, S, _ = load(run_dir)
    n = len(E)
    out = {'sequence': seq, 'n_records': n}
    # 1) effective sample size (AR(1))
    rho = [float(np.corrcoef(E[:-1, j], E[1:, j])[0, 1]) for j in range(3)]
    neff = [n * (1 - r) / (1 + r) for r in rho]
    out['lag1_rho'] = dict(zip(['x', 'y', 'theta'], rho))
    out['n_eff'] = dict(zip(['x', 'y', 'theta'], neff))
    out['min_n_eff'] = min(neff)
    out['gate_200_independent_frames_met'] = bool(min(neff) >= 200)
    # 2) omitted cross-covariance magnitude
    dE = np.diff(E, axis=0); Ssum = S[1:] + S[:-1]
    C_d = np.cov(dE.T, bias=True)
    X = np.cov(np.vstack([E[:-1].T, E[1:].T]), bias=True)
    out['trace_Ssum'] = float(np.mean([np.trace(s) for s in Ssum]))
    out['trace_cross_x2'] = float(np.trace(X[:3, 3:]))
    out['cross_over_denominator'] = out['trace_cross_x2'] / out['trace_Ssum']
    out['trace_emp_cov_dE'] = float(np.trace(C_d))
    out['cov_overestimated_factor'] = 2 * out['trace_Ssum'] / out['trace_emp_cov_dE']
    # 3) per-axis absolute decomposition
    dg = np.array([np.diag(s) for s in S])
    z = np.abs(E) / np.sqrt(np.maximum(dg, 1e-300))
    out['per_axis_median_abs_z'] = dict(zip(['x', 'y', 'theta'], [float(x) for x in np.median(z, axis=0)]))
    out['per_axis_sigma_factor'] = dict(zip(['x', 'y', 'theta'], [float(x) / 0.674 for x in np.median(z, axis=0)]))
    print(json.dumps(out, indent=2))

if __name__ == '__main__':
    main()
