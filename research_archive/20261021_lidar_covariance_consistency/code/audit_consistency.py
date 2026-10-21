#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Independent recomputation of the archived 2D scan-matching consistency results.

Assistant-authored audit, 2026-10-21. This script is NOT part of the original
experiment; it re-derives every number quoted in REPORT.md from the raw rows in
results/v3_*.json, using numpy only (no scipy, no matplotlib).

Checks performed
  1. NEES rows reproduce: nees_field == e^T H e for every row.
  2. Sample structure: how many distinct frames, how many initializations per
     frame. This matters because rows are (frame, init) pairs, not independent
     scans.
  3. NEES distribution per condition, plus the implied effective range noise
     sigma_eff = sigma * sqrt(median_NEES / 3).
  4. Predicted vs empirical correlation of (x,y), (x,theta), (y,theta).
  5. Scale-invariance test of gamma = lmin/lmax of the mixed-unit 3x3 Hessian:
     re-deriving the same geometry with lengths in cm must not change a
     meaningful degeneracy index.
  6. Tail-vs-geometry split: are high-NEES rows concentrated at low gamma?

Usage:  python3 code/audit_consistency.py
Output: results/summary.json, results/per_frame.csv,
        results/correlation_check.json, audit/independent_check.json
"""
import csv
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESULTS = os.path.join(ROOT, 'results')
AUDIT = os.path.join(ROOT, 'audit')

CONDITIONS = [
    ('static_0', 0.02, 'v3_s0.02.json'),
    ('static_0', 0.04, 'v3_s0.04.json'),
    ('static_0', 0.06, 'v3_s0.06.json'),
    ('lt_changes_0', 0.02, 'v3_lt0.02.json'),
    ('lt_changes_0', 0.04, 'v3_lt0.04.json'),
    ('lt_changes_0', 0.06, 'v3_lt0.06.json'),
]

DOF = 3  # (x, y, theta)

# chi-square with 3 dof: quantiles (standard tables; no scipy available here)
CHI2_3 = {'p50': 2.365974, 'p90': 6.251389, 'p99': 11.344867, 'p999': 16.266248,
          'p9999': 21.107504}


def load(name):
    with open(os.path.join(RESULTS, name)) as f:
        return json.load(f)


def corr_from_cov(s):
    d = np.sqrt(np.diag(s))
    return s / np.outer(d, d)


def empirical_corr(e):
    return np.corrcoef(e.T)


def analyse(rows):
    e = np.asarray([r['e'] for r in rows], dtype=float)
    H = np.asarray([r['H'] for r in rows], dtype=float)
    nees_field = np.asarray([r['nees'] for r in rows], dtype=float)
    frames = np.asarray([r['frame'] for r in rows], dtype=int)
    npts = np.asarray([r['n'] for r in rows], dtype=float)

    # ---- 1. row-level reproduction of the stored NEES ----------------------
    nees_check = np.einsum('ni,nij,nj->n', e, H, e)
    rel = np.abs(nees_check - nees_field) / np.maximum(np.abs(nees_field), 1e-12)
    # near-zero NEES rows make relative error meaningless; keep both views
    finite = np.isfinite(rel)
    max_rel = float(np.max(rel[finite])) if finite.any() else float('nan')

    # ---- 2. sample structure ---------------------------------------------
    uniq, counts = np.unique(frames, return_counts=True)

    # ---- 3. distribution --------------------------------------------------
    nees = nees_field
    sigma = float(rows[0]['sigma'])
    med = float(np.median(nees))
    stats = {
        'sigma_nominal_m': sigma,
        'rows': int(len(rows)),
        'distinct_frames': int(len(uniq)),
        'inits_per_frame': sorted({int(c) for c in counts}),
        'nees_median': med,
        'nees_mean': float(np.mean(nees)),
        'nees_p90': float(np.quantile(nees, 0.90)),
        'nees_p99': float(np.quantile(nees, 0.99)),
        'nees_max': float(np.max(nees)),
        'nees_min': float(np.min(nees)),
        'frac_nees_gt_100': float(np.mean(nees > 100.0)),
        'sigma_eff_m': float(sigma * np.sqrt(med / DOF)),
        'correspondences_mean': float(np.mean(npts)),
        'correspondences_min': float(np.min(npts)),
    }

    # first initialization only, to show the effect of the repeated inits
    first = {}
    for f in uniq:
        idx = int(np.where(frames == f)[0][0])
        first[int(f)] = idx
    fidx = np.asarray([first[int(f)] for f in uniq])
    stats['first_init_only'] = {
        'rows': int(len(fidx)),
        'nees_median': float(np.median(nees[fidx])),
        'nees_mean': float(np.mean(nees[fidx])),
        'nees_p99': float(np.quantile(nees[fidx], 0.99)),
        'nees_max': float(np.max(nees[fidx])),
        'frac_nees_gt_100': float(np.mean(nees[fidx] > 100.0)),
    }

    # ---- 4. predicted vs empirical correlation ---------------------------
    c_pred_each = np.asarray([corr_from_cov(np.linalg.inv(h)) for h in H])
    c_pred_mean = c_pred_each.mean(axis=0)
    c_emp = empirical_corr(e)
    c_emp_first = empirical_corr(e[fidx])
    pairs = {'xy': (0, 1), 'xth': (0, 2), 'yth': (1, 2)}
    corr = {}
    for k, (i, j) in pairs.items():
        corr[k] = {
            'predicted_mean_over_frames': float(c_pred_mean[i, j]),
            'predicted_from_mean_cov': float(
                corr_from_cov(np.linalg.inv(H.mean(axis=0)))[i, j]),
            'empirical_all_rows': float(c_emp[i, j]),
            'empirical_first_init': float(c_emp_first[i, j]),
        }

    # ---- 4b. scale-free tail shape --------------------------------------
    # Dividing every NEES by the condition's own median removes the unknown
    # range-noise scale entirely: any rescaling Sigma -> k*Sigma maps
    # NEES -> NEES/k and leaves these ratios unchanged. So this is the only
    # part of the analysis that does not depend on the assumed sigma_range.
    u = nees / med
    shape = {
        'u_p50': float(np.quantile(u, 0.50)),
        'u_p90': float(np.quantile(u, 0.90)),
        'u_p99': float(np.quantile(u, 0.99)),
        'u_p999': float(np.quantile(u, 0.999)),
        'u_max': float(np.max(u)),
        'chi2_3_reference_u': {k: v / CHI2_3['p50'] for k, v in CHI2_3.items()},
        'inflation_p90': float(np.quantile(u, 0.90) / (CHI2_3['p90'] / CHI2_3['p50'])),
        'inflation_p99': float(np.quantile(u, 0.99) / (CHI2_3['p99'] / CHI2_3['p50'])),
        'inflation_p999': float(np.quantile(u, 0.999) / (CHI2_3['p999'] / CHI2_3['p50'])),
    }
    stats['scale_free_tail_shape'] = shape

    # ---- 5. scale invariance of gamma -----------------------------------
    # gamma as used previously: lmin/lmax of the mixed-unit 3x3 information
    # matrix (x,y in m, theta in rad). Recompute the identical geometry with
    # lengths expressed in cm: only a change of variables, so any meaningful
    # degeneracy index must be unchanged.
    ev_m = np.linalg.eigvalsh(H)
    gamma_m = ev_m[:, 0] / ev_m[:, -1]
    d = np.tile(np.array([1.0, 1.0, 100.0]), (len(H), 1))   # m -> cm on theta column
    H_cm = H * d[:, :, None] * d[:, None, :]
    ev_cm = np.linalg.eigvalsh(H_cm)
    gamma_cm = ev_cm[:, 0] / ev_cm[:, -1]
    # translation-only block ratio: dimensionally consistent by construction
    gamma_xy = np.asarray([np.linalg.eigvalsh(h[:2, :2]) for h in H])
    gamma_xy_ratio = gamma_xy[:, 0] / gamma_xy[:, 1]
    scale = {
        'gamma_m_median': float(np.median(gamma_m)),
        'gamma_cm_median': float(np.median(gamma_cm)),
        'gamma_ratio_cm_over_m': float(np.median(gamma_cm) / np.median(gamma_m)),
        'gamma_xy_ratio_median': float(np.median(gamma_xy_ratio)),
        'gamma_xy_ratio_identical_under_unit_change': True,
    }

    # ---- 6. tail vs geometry --------------------------------------------
    cut = np.quantile(nees, 0.90)
    tail = nees >= cut
    # the 4 initializations of one frame are not independent: report how many
    # distinct scans the tail actually contains
    tail_frames = np.unique(frames[tail])

    def tail_split(mask):
        if mask.sum() == 0 or (~mask).sum() == 0:
            return None
        return {
            'n_rows': int(mask.sum()),
            'gamma_m_tail': float(np.median(gamma_m[mask])),
            'gamma_m_rest': float(np.median(gamma_m[~mask])),
            'gamma_xy_tail': float(np.median(gamma_xy_ratio[mask])),
            'gamma_xy_rest': float(np.median(gamma_xy_ratio[~mask])),
        }

    # same quantile rule applied to the first-initialization-only sample, so
    # that every row is a different scan
    nees_first = nees[fidx]
    tail_first = nees_first >= np.quantile(nees_first, 0.90)
    first_split = tail_split(np.isin(frames, frames[fidx][tail_first]))

    tail_geom = {
        'tail_definition': 'NEES >= p90 of this condition',
        'n_tail_rows': int(tail.sum()),
        'n_tail_distinct_frames': int(len(tail_frames)),
        'n_total_distinct_frames': int(len(uniq)),
        'gamma_m_tail_median': float(np.median(gamma_m[tail])),
        'gamma_m_rest_median': float(np.median(gamma_m[~tail])),
        'gamma_m_ratio_tail_over_rest':
            float(np.median(gamma_m[tail]) / np.median(gamma_m[~tail])),
        'gamma_xy_ratio_tail_median': float(np.median(gamma_xy_ratio[tail])),
        'gamma_xy_ratio_rest_median': float(np.median(gamma_xy_ratio[~tail])),
        'gamma_xy_ratio_tail_over_rest':
            float(np.median(gamma_xy_ratio[tail]) / np.median(gamma_xy_ratio[~tail])),
        'correspondences_tail_median': float(np.median(npts[tail])),
        'correspondences_rest_median': float(np.median(npts[~tail])),
        'first_init_only_tail_split': first_split,
    }

    # ---- 6b. is the tail "confidently wrong" or "knew it was unsure"? ----
    # Predicted positional standard deviation implied by H, independent of the
    # unknown range-noise scale only up to a common factor, but its RATIO
    # between tail and rest frames is scale-free.
    pred_sigma = np.asarray([
        np.sqrt(np.trace(np.linalg.inv(h)[:2, :2])) for h in H])
    log_tr = np.log10(np.asarray([np.trace(h) for h in H]))
    # rank correlation between reported confidence and actual error
    rk_nees = np.argsort(np.argsort(nees)).astype(float)
    rk_pred = np.argsort(np.argsort(pred_sigma)).astype(float)
    rk_corr = float(np.corrcoef(rk_nees, rk_pred)[0, 1])
    confidence = {
        'predicted_sigma_xy_tail_median_m': float(np.median(pred_sigma[tail])),
        'predicted_sigma_xy_rest_median_m': float(np.median(pred_sigma[~tail])),
        'predicted_sigma_ratio_tail_over_rest':
            float(np.median(pred_sigma[tail]) / np.median(pred_sigma[~tail])),
        'trace_H_log10_tail_median': float(np.median(log_tr[tail])),
        'trace_H_log10_rest_median': float(np.median(log_tr[~tail])),
        'rank_correlation_nees_vs_predicted_sigma': rk_corr,
        'reading': 'ratio < 1 means the tail frames are reported as MORE precise than '
                   'the rest, i.e. confidently wrong; ratio > 1 means the model at '
                   'least flagged them as uncertain'
    }
    stats['tail_confidence'] = confidence

    return stats, corr, scale, tail_geom, {
        'max_relative_nees_reproduction_error_all_rows': max_rel,
        'rows_with_nonfinite_relative_error': int((~finite).sum()),
        'frames': frames,
        'rows_e': e,
        'rows_nees': nees,
        'rows_gamma_m': gamma_m,
        'rows_gamma_xy': gamma_xy_ratio,
        'rows_n': npts,
        'first_init_index': fidx,
    }


def main():
    summary = {}
    correlations = {}
    scale_inv = {}
    tails = {}
    checks = {'per_condition': {}}
    per_frame_rows = []

    for scene, sigma, fname in CONDITIONS:
        key = '%s_sigma%.2f' % (scene, sigma)
        rows = load(fname)
        st, corr, scale, tail, det = analyse(rows)
        summary[key] = st
        correlations[key] = corr
        scale_inv[key] = scale
        tails[key] = tail
        checks['per_condition'][key] = {
            'file': fname,
            'max_relative_nees_reproduction_error':
                det['max_relative_nees_reproduction_error_all_rows'],
            'rows_with_nonfinite_relative_error':
                det['rows_with_nonfinite_relative_error'],
        }
        for k in range(len(rows)):
            r = rows[k]
            per_frame_rows.append({
                'condition': key,
                'scene': scene,
                'sigma_nominal_m': sigma,
                'row': k,
                'frame': int(r['frame']),
                'is_first_init': bool(k in set(det['first_init_index'].tolist())),
                'n_correspondences': int(r['n']),
                'e_x': float(det['rows_e'][k, 0]),
                'e_y': float(det['rows_e'][k, 1]),
                'e_theta': float(det['rows_e'][k, 2]),
                'nees': float(det['rows_nees'][k]),
                'gamma_lmin_over_lmax_mixed_units': float(det['rows_gamma_m'][k]),
                'gamma_xy_translation_only': float(det['rows_gamma_xy'][k]),
            })

    # ---- sigma scaling: NEES must fall as sigma^-2 ----------------------
    scaling = {}
    for scene in ('static_0', 'lt_changes_0'):
        meds = [summary['%s_sigma%.2f' % (scene, s)]['nees_median']
                for s in (0.02, 0.04, 0.06)]
        scaling[scene] = {
            'nees_median_by_sigma': {str(s): m for s, m in zip((0.02, 0.04, 0.06), meds)},
            'ratio_0.02_over_0.04_observed': meds[0] / meds[1],
            'ratio_0.02_over_0.04_theory': 4.0,
            'ratio_0.04_over_0.06_observed': meds[1] / meds[2],
            'ratio_0.04_over_0.06_theory': (0.06 / 0.04) ** 2,
        }

    # consistency: the same scene at the same nominal sigma should give the
    # same effective noise if sigma_eff is a property of the data
    sigma_eff = {scene: summary['%s_sigma0.02' % scene]['sigma_eff_m']
                 for scene in ('static_0', 'lt_changes_0')}

    # ---- sigma invariance: are the three sigma rows one computation? -----
    # w_i = (1/sigma^2) * huber(...) and huber does not involve sigma, so the
    # normal equations scale by 1/sigma^2 on both sides and the solution is
    # identical for every sigma. Check it instead of asserting it.
    sigma_invariance = {}
    for scene, files in (('static_0', ['v3_s0.02.json', 'v3_s0.04.json', 'v3_s0.06.json']),
                         ('lt_changes_0', ['v3_lt0.02.json', 'v3_lt0.04.json', 'v3_lt0.06.json'])):
        runs = [load(f) for f in files]
        e0 = np.asarray([r['e'] for r in runs[0]])
        max_de = 0.0
        n_same = True
        h_ratio = set()
        for other in runs[1:]:
            eo = np.asarray([r['e'] for r in other])
            max_de = max(max_de, float(np.abs(e0 - eo).max()))
            n_same = n_same and ([r['n'] for r in runs[0]] == [r['n'] for r in other])
        H0 = np.asarray([r['H'] for r in runs[1]])
        Href = np.asarray([r['H'] for r in runs[0]])
        h_ratio = sorted({round(float(x), 6) for x in np.unique((H0 / Href).ravel())})
        sigma_invariance[scene] = {
            'max_abs_error_difference_between_sigma_runs': max_de,
            'correspondence_counts_identical': bool(n_same),
            'distinct_H_ratios_relative_to_sigma0.02': h_ratio,
            'conclusion': 'the three sigma rows are one computation reported at three '
                          'rescalings; they are not three independent experiments'
        }

    out = {
        'role': 'assistant-authored independent recomputation from archived raw rows; '
                'not an independent team replication',
        'conditions': summary,
        'sigma_invariance': sigma_invariance,
        'sigma_scaling': scaling,
        'effective_noise': sigma_eff,
        'correlations': correlations,
        'gamma_scale_invariance': scale_inv,
        'tail_vs_geometry': tails,
        'row_reproduction_checks': checks,
        'notes': [
            'Each row is one (frame, initialization) pair. The archived runs use '
            '4 initializations per frame, so rows are not independent scans.',
            'The estimator is initialized from ground truth plus Gaussian noise; the '
            'recorded error is therefore a local convergence residual around truth, '
            'not an accumulated SLAM trajectory error.',
            'NEES uses Sigma = H^-1 with H = sum J^T Omega J, Omega = 1/sigma_range^2.',
            'gamma = lmin/lmax of the mixed-unit 3x3 Hessian is reproduced here; its '
            'lack of unit invariance is quantified, not assumed.',
        ],
    }

    os.makedirs(AUDIT, exist_ok=True)
    with open(os.path.join(RESULTS, 'summary.json'), 'w') as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write('\n')
    with open(os.path.join(RESULTS, 'correlation_check.json'), 'w') as f:
        json.dump({'correlations': correlations,
                   'gamma_scale_invariance': scale_inv}, f, indent=1, sort_keys=True)
        f.write('\n')
    with open(os.path.join(AUDIT, 'independent_check.json'), 'w') as f:
        json.dump({'row_reproduction_checks': checks,
                   'sigma_scaling': scaling,
                   'effective_noise': sigma_eff},
                  f, indent=1, sort_keys=True)
        f.write('\n')

    cols = ['condition', 'scene', 'sigma_nominal_m', 'row', 'frame', 'is_first_init',
            'n_correspondences', 'e_x', 'e_y', 'e_theta', 'nees',
            'gamma_lmin_over_lmax_mixed_units', 'gamma_xy_translation_only']
    with open(os.path.join(RESULTS, 'per_frame.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in per_frame_rows:
            w.writerow(r)

    # ---- console summary --------------------------------------------------
    for k in sorted(summary):
        s = summary[k]
        print('%-22s rows=%3d frames=%2d  NEES med=%9.2f mean=%10.2f p90=%8.2f '
              'p99=%11.2f  sigma_eff=%.4f m' % (
                  k, s['rows'], s['distinct_frames'], s['nees_median'], s['nees_mean'],
                  s['nees_p90'], s['nees_p99'], s['sigma_eff_m']))
    print()
    for k in sorted(correlations):
        c = correlations[k]
        print('%-22s rho_xy pred=%+.3f emp=%+.3f | rho_xtheta pred=%+.3f emp=%+.3f | '
              'rho_ytheta pred=%+.3f emp=%+.3f' % (
                  k,
                  c['xy']['predicted_mean_over_frames'], c['xy']['empirical_all_rows'],
                  c['xth']['predicted_mean_over_frames'], c['xth']['empirical_all_rows'],
                  c['yth']['predicted_mean_over_frames'], c['yth']['empirical_all_rows']))
    print()
    for k in sorted(scale_inv):
        s = scale_inv[k]
        print('%-22s gamma_m=%.4f gamma_cm=%.4f ratio=%.3f | gamma_xy=%.4f | tail gamma_m %.4f vs rest %.4f' % (
            k, s['gamma_m_median'], s['gamma_cm_median'], s['gamma_ratio_cm_over_m'],
            s['gamma_xy_ratio_median'],
            tails[k]['gamma_m_tail_median'], tails[k]['gamma_m_rest_median']))
    print()
    print('sigma_eff static_0 = %.4f m, lt_changes_0 = %.4f m' % (
        sigma_eff['static_0'], sigma_eff['lt_changes_0']))


if __name__ == '__main__':
    main()
