#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Standalone reproduction of the L1 post-hoc diagnostics.  [v2, 2026-10-23]

Fixes three defects found by independent review in v1 (kept as
l1_posthoc_diagnostics_v1_BUGGY.py.bak):

  D1  Hessian pairing.  v1 indexed the Hessian dict by the RAW
      /hector_debug_info message counter, while per_frame.csv's `frame`
      column is the POST-PAIRING per_scan index.  Those differ
      (8979 -> 8911 and 6537 -> 6501).  v2 rebuilds the pairing exactly as
      l1_g1_analysis.py does (a pose immediately followed by the next debug
      message) and audits every skipped message.

  D2  A spurious factor of two.  trace_Ssum already is trace(Sigma_k +
      Sigma_{k-1}); v1 multiplied it by 2 again.  The cross-covariance line
      also summed only one of the two off-diagonal blocks.  Both fixed. The v1
      numbers (1238x / 1336x, ratio 7.3% / 3.9%) are kept only as historical
      records in ERRATA.md and are NOT reproduced here.

  D3  v1 printed JSON and never wrote the files it claimed to produce.
      v2 writes them and takes an explicit output directory.

STILL NOT a valid consistency test: the empirical cross covariance of the
measured error and an uncalibrated H^-1 are not the same statistical object.
Nothing here may be read as "the covariance is off by N x".

Usage:
    python3 l1_posthoc_diagnostics.py <run_dir> <sequence> [--out DIR]
"""
import argparse
import csv
import json
import os
import sys

import numpy as np
import rosbag


def load_pairing(run_dir):
    """Rebuild the pose -> debug pairing exactly as l1_g1_analysis.py does."""
    per_scan = []
    audit = {'n_pose': 0, 'n_debug': 0, 'skipped': []}
    cur_pose = False
    dbg_ordinal = 0
    with rosbag.Bag(os.path.join(run_dir, 'measure.bag')) as bag:
        for topic, msg, _ in bag.read_messages(
                topics=['/slam_out_pose', '/hector_debug_info']):
            if topic == '/slam_out_pose':
                audit['n_pose'] += 1
                cur_pose = True
            else:
                audit['n_debug'] += 1
                dbg_ordinal += 1
                if (not cur_pose) or (not msg.iterData):
                    audit['skipped'].append({
                        'debug_ordinal': dbg_ordinal,
                        'reason': 'no_preceding_unconsumed_pose' if not cur_pose
                                  else 'empty_iterData',
                        'per_scan_index_at_skip': len(per_scan),
                    })
                    cur_pose = False
                    continue
                H = np.array(msg.iterData[-1].hessian, dtype=float).reshape(3, 3)
                per_scan.append(0.5 * (H + H.T))
                cur_pose = False
    audit['n_per_scan'] = len(per_scan)
    return per_scan, audit


def load_errors(run_dir):
    rows = sorted(csv.DictReader(open(os.path.join(run_dir, 'per_frame.csv'))),
                  key=lambda r: int(r['frame']))
    idx = np.array([int(r['frame']) for r in rows])
    E = np.array([[float(r['ex']), float(r['ey']), float(r['eth'])] for r in rows])
    return idx, E


def trace_mean(A):
    return float(np.mean([np.trace(a) for a in A]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('run_dir')
    ap.add_argument('sequence')
    ap.add_argument('--out', default=None,
                    help='output directory (default: <run_dir>/posthoc_v2)')
    a = ap.parse_args()
    out_dir = a.out or os.path.join(a.run_dir, 'posthoc_v2')
    os.makedirs(out_dir, exist_ok=True)

    per_scan, audit = load_pairing(a.run_dir)
    idx, E = load_errors(a.run_dir)

    pairing = {
        'n_pose': audit['n_pose'], 'n_debug': audit['n_debug'],
        'n_per_scan': audit['n_per_scan'],
        'pose_equals_debug': audit['n_pose'] == audit['n_debug'],
        'n_per_frame_rows': int(len(idx)),
        'max_frame_index': int(idx.max()) if len(idx) else None,
        'frame_index_within_per_scan': bool(len(idx) and idx.max() < audit['n_per_scan']),
        'n_skipped_debug': len(audit['skipped']),
        'skipped_head': audit['skipped'][:50],
        'note': ('v1 indexed Hessians by raw debug ordinal; the per_frame `frame` column is '
                 'the post-pairing per_scan index. v2 indexes by per_scan position.'),
    }

    S_all, keep = [], []
    for k in idx:
        try:
            S_all.append(np.linalg.inv(per_scan[int(k)]))
            keep.append(True)
        except (np.linalg.LinAlgError, IndexError):
            keep.append(False)
    keep = np.array(keep, dtype=bool)
    S = np.array(S_all)
    E = E[keep]
    n = len(E)
    out = {'sequence': a.sequence, 'n_records': int(n)}

    # 1. effective sample size (uses errors only -> unaffected by D1)
    rho = [float(np.corrcoef(E[:-1, j], E[1:, j])[0, 1]) for j in range(3)]
    neff = [n * (1 - r) / (1 + r) for r in rho]
    out['lag1_rho'] = dict(zip(['x', 'y', 'theta'], rho))
    out['n_eff_ar1'] = dict(zip(['x', 'y', 'theta'], neff))
    out['n_eff_min_axis'] = float(min(neff))
    out['gate_200_independent_frames_met'] = bool(min(neff) >= 200)
    out['n_eff_caveat'] = ('AR(1) approximation applies to the MEAN of a stationary series, '
                           'not to every statistic; see CONTROL/STATISTICAL_UNITS.md')

    # 2. cross-covariance magnitude (D2 fixed: no extra x2 on Ssum, both blocks)
    dE = np.diff(E, axis=0)
    Ssum = S[1:] + S[:-1]
    C_d = np.cov(dE.T, bias=True)
    X = np.cov(np.vstack([E[:-1].T, E[1:].T]), bias=True)
    cross_one = X[:3, 3:]
    out['trace_Ssum'] = trace_mean(Ssum)
    out['trace_cross_one_block'] = float(np.trace(cross_one))
    out['trace_cross_both_blocks'] = float(2.0 * np.trace(cross_one))
    out['cross_over_denominator'] = out['trace_cross_both_blocks'] / out['trace_Ssum']
    out['trace_emp_cov_dE'] = float(np.trace(C_d))
    out['denominator_over_empirical'] = out['trace_Ssum'] / out['trace_emp_cov_dE']
    out['interpretation'] = ('denominator_over_empirical compares TWO DIFFERENT OBJECTS '
                             '(uncalibrated H^-1 sum vs empirical error-difference covariance). '
                             'It is NOT a covariance-mismatch factor.')

    # 3. per-axis absolute decomposition
    dg = np.array([np.diag(s) for s in S])
    z = np.abs(E) / np.sqrt(np.maximum(dg, 1e-300))
    med = np.median(z, axis=0)
    out['per_axis_median_abs_z'] = {k: float(v) for k, v in zip(['x', 'y', 'theta'], med)}
    out['per_axis_sigma_factor'] = {k: float(v) / 0.674
                                    for k, v in out['per_axis_median_abs_z'].items()}

    # 4. drift vs white
    q = max(1, n // 4)
    out['abs_theta_median_by_quarter_mrad'] = [
        float(np.median(np.abs(E[j * q:(j + 1) * q, 2])) * 1000.0) for j in range(4)]

    files = {}
    for name in ('effective_sample_size', 'cross_covariance_check',
                 'per_axis_decomposition', 'drift_vs_white'):
        p = os.path.join(out_dir, name + '.json')
        json.dump(out, open(p, 'w'), indent=2)
        files[name] = p
    json.dump(pairing, open(os.path.join(out_dir, 'pairing_audit.json'), 'w'), indent=2)
    files['pairing_audit'] = os.path.join(out_dir, 'pairing_audit.json')

    checks = {
        'pose_debug_counts_match': pairing['pose_equals_debug'],
        'frame_index_within_per_scan': pairing['frame_index_within_per_scan'],
        'n_per_scan_equals_pose_minus_skipped':
            pairing['n_per_scan'] == pairing['n_pose'] - pairing['n_skipped_debug'],
        'n_records_positive': n > 0,
        'all_outputs_written': all(os.path.isfile(p) for p in files.values()),
    }
    json.dump(checks, open(os.path.join(out_dir, 'self_check.json'), 'w'), indent=2)
    out['self_check'] = checks
    out['files'] = files

    keys = ('sequence', 'n_records', 'n_eff_ar1', 'n_eff_min_axis',
            'gate_200_independent_frames_met', 'trace_Ssum',
            'trace_cross_both_blocks', 'cross_over_denominator',
            'trace_emp_cov_dE', 'denominator_over_empirical',
            'per_axis_sigma_factor', 'self_check')
    print(json.dumps({k: out[k] for k in keys}, indent=2))
    if not all(checks.values()):
        print('SELF-CHECK FAILED', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
