#!/usr/bin/python3
"""Phase 4A Stage B: gate sanity + sensitivity audit (descriptive, NO threshold search).

Outputs under results/phase4a/gate_audit/:
- gate_decision_matrix.csv : per-loop decision across a small threshold grid
- threshold_stability.csv  : per-loop stability summary + S-reference decision
- leave_one_seed_out.csv   : per held-out seed, decisions + support check
- gate_formulations.csv    : A span+yaw vs B history-continuity(support) vs C span vs D yaw
- gate_stability.png

The audit ONLY checks whether small, mechanism-reasonable variations keep decisions
stable and whether the current G1/G2 thresholds remain interpretable without the
single S case. It does NOT optimize thresholds to maximize accuracy.
"""

import csv
import itertools
import statistics
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
FEAT = ROOT / 'results' / 'phase3a' / 'analysis' / 'loop_realization_features.csv'
OUT = ROOT / 'results' / 'phase4a' / 'gate_audit'

# Current Phase 3B gates
G1_KEY = 'history_path_length_m'     # contiguous history span (V0 path length), m
G2_KEY = 'yaw_diff_median_rad'       # heading consistency (offline GT-based metric)
T_SPAN_CUR = 4.5
T_YAW_CUR = 0.78

# small descriptive grids (mechanism-reasonable ranges)
SPAN_GRID = [3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0]
YAW_GRID = [0.5, 0.6, 0.78, 0.9, 1.0, 1.2]


def num(v):
    if v is None or v == '' or v == 'None':
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(open(FEAT)))
    loops = [r for r in rows]
    for r in loops:
        r['_span'] = num(r.get(G1_KEY))
        r['_yaw'] = num(r.get(G2_KEY))
        r['_wp'] = num(r.get('history_waypoint_count'))
        r['_sub'] = r['failure_subclass']

    # ---------------- decision matrix across grid ----------------
    combo_fields = []
    for ts in SPAN_GRID:
        for ty in YAW_GRID:
            dec = {}
            for r in loops:
                g1 = r['_span'] is not None and r['_span'] < ts
                g2 = r['_yaw'] is not None and r['_yaw'] > ty
                dec[r['seed'] + '_l' + r['loop_id']] = 'REPAIR' if (g1 or g2) else 'NO_REPAIR'
            combo_fields.append((ts, ty, dec))

    with (OUT / 'gate_decision_matrix.csv').open('w', newline='') as f:
        w = csv.writer(f)
        header = ['seed', 'loop_id', 'vertex', 'subclass'] + [
            'span<{:.1f},yaw>{:.2f}'.format(ts, ty) for ts, ty, _ in combo_fields]
        w.writerow(header)
        for r in loops:
            lid = r['seed'] + '_l' + r['loop_id']
            w.writerow([r['seed'], r['loop_id'], r['loop_vertex'], r['_sub']] +
                       [d[lid] for _, _, d in combo_fields])

    # ---------------- stability per loop ----------------
    stab_rows = []
    for r in loops:
        lid = r['seed'] + '_l' + r['loop_id']
        decisions = [d[lid] for _, _, d in combo_fields]
        repair_frac = decisions.count('REPAIR') / len(decisions)
        stab_rows.append({
            'seed': r['seed'], 'loop_id': r['loop_id'], 'vertex': r['loop_vertex'],
            'subclass': r['_sub'], 'span_m': r['_span'], 'yaw_med_rad': r['_yaw'],
            'waypoints': r['_wp'],
            'repair_frac_across_grid': round(repair_frac, 3),
            'current_decision': ('REPAIR' if (r['_span'] is not None and r['_span'] < T_SPAN_CUR)
                                 or (r['_yaw'] is not None and r['_yaw'] > T_YAW_CUR)
                                 else 'NO_REPAIR'),
            'current_reasons': ';'.join(x for x in (
                'span<4.5' if r['_span'] is not None and r['_span'] < T_SPAN_CUR else '',
                'yaw>0.78' if r['_yaw'] is not None and r['_yaw'] > T_YAW_CUR else '') if x),
        })
    with (OUT / 'threshold_stability.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(stab_rows[0].keys()))
        w.writeheader()
        w.writerows(stab_rows)

    # S-reference decision across the grid
    s = next(r for r in loops if r['_sub'] == 'S')
    sid = s['seed'] + '_l' + s['loop_id']
    print('=== S-reference (s21001 l4 v26) decision across grid ===')
    for ts, ty, d in combo_fields:
        print('  span<{:.1f} yaw>{:.2f}: {}  (span={} yaw={})'.format(
            ts, ty, d[sid], s['_span'], s['_yaw']))

    # ---------------- leave-one-seed-out ----------------
    seeds = sorted({r['seed'] for r in loops})
    loso = []
    for held in seeds:
        train = [r for r in loops if r['seed'] != held]
        # mechanism support: without the held seed, what span separates C3/D1 from S?
        # We do NOT fit; we only report the observed span/yaw ranges and whether the
        # S-protection (max span among NO_REPAIR-worthy successes) still exists.
        subs = {}
        for r in train:
            subs.setdefault(r['_sub'], []).append((r['_span'], r['_yaw']))
        def rng(vals, idx):
            v = [x[idx] for x in vals if x[idx] is not None]
            return (round(min(v), 2), round(max(v), 2)) if v else None
        # S in training?
        s_train = [r for r in train if r['_sub'] == 'S']
        span_support = None
        if s_train:
            span_support = rng([(r['_span'], r['_yaw']) for r in s_train], 0)
        # how many training failures would be caught by current gates
        caught = sum(1 for r in train
                     if (r['_span'] is not None and r['_span'] < T_SPAN_CUR)
                     or (r['_yaw'] is not None and r['_yaw'] > T_YAW_CUR))
        total_fail = sum(1 for r in train if r['_sub'] != 'S')
        loso.append({
            'held_out_seed': held,
            'n_train_loops': len(train),
            's_cases_in_train': len(s_train),
            's_span_range': str(span_support),
            'c3_span_range': str(rng(subs.get('C3', []), 0)),
            'd1_span_range': str(rng(subs.get('D1', []), 0)),
            'c3_yaw_range': str(rng(subs.get('C3', []), 1)),
            'd1_yaw_range': str(rng(subs.get('D1', []), 1)),
            'failed_loops_caught_by_current_gates': '{}/{}'.format(caught, total_fail),
        })
    with (OUT / 'leave_one_seed_out.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(loso[0].keys()))
        w.writeheader()
        w.writerows(loso)
    for row in loso:
        print('LOSO held={}: s_train={} s_span={} c3_span={} d1_span={} caught={}'.format(
            row['held_out_seed'], row['s_cases_in_train'], row['s_span_range'],
            row['c3_span_range'], row['d1_span_range'], row['failed_loops_caught_by_current_gates']))

    # ---------------- gate formulations ----------------
    # A: span+yaw (current); B: history-continuity support (waypoint count < min chain 4)
    #    OR span < min_chain*min_travel (4*1.0=4.0) — fixed SLAM config, not data-tuned;
    # C: span-only (4.5); D: yaw-only (0.78)
    fmt_rows = []
    for r in loops:
        gA = (r['_span'] is not None and r['_span'] < 4.5) or (r['_yaw'] is not None and r['_yaw'] > 0.78)
        # B: fixed Karto config: LoopMatchMinimumChainSize=4, MinimumTravelDistance=1.0
        gB = (r['_wp'] is not None and r['_wp'] < 4) or (r['_span'] is not None and r['_span'] < 4.0)
        gC = r['_span'] is not None and r['_span'] < 4.5
        gD = r['_yaw'] is not None and r['_yaw'] > 0.78
        fmt_rows.append({
            'seed': r['seed'], 'loop_id': r['loop_id'], 'vertex': r['loop_vertex'],
            'subclass': r['_sub'],
            'A_span_plus_yaw': 'REPAIR' if gA else 'NO_REPAIR',
            'B_history_support': 'REPAIR' if gB else 'NO_REPAIR',
            'C_span_only': 'REPAIR' if gC else 'NO_REPAIR',
            'D_yaw_only': 'REPAIR' if gD else 'NO_REPAIR',
        })
    with (OUT / 'gate_formulations.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(fmt_rows[0].keys()))
        w.writeheader()
        w.writerows(fmt_rows)
    print('\n=== gate formulations (A/B/C/D) on 21 loops ===')
    for row in fmt_rows:
        print('  s{} l{} v{:<3} {}: A={} B={} C={} D={}'.format(
            row['seed'], row['loop_id'], row['vertex'], row['subclass'],
            row['A_span_plus_yaw'], row['B_history_support'], row['C_span_only'], row['D_yaw_only']))

    # ---------------- plot ----------------
    fig, ax = plt.subplots(figsize=(7, 5))
    for r in loops:
        color = {'C3': '#d1495b', 'D1': '#2e86ab', 'S': '#1b9e77'}.get(r['_sub'], '#888')
        marker = 'o'
        ax.scatter(r['_span'], r['_yaw'], c=color, s=70, alpha=0.85,
                   edgecolor='k', linewidth=0.4, marker=marker)
        ax.annotate('s{}l{}'.format(r['seed'], r['loop_id']),
                    (r['_span'], r['_yaw']), fontsize=7, alpha=0.8,
                    textcoords='offset points', xytext=(4, 4))
    ax.axvline(T_SPAN_CUR, color='k', ls='--', alpha=0.5, label='G1 span=4.5')
    ax.axhline(T_YAW_CUR, color='k', ls=':', alpha=0.5, label='G2 yaw=0.78')
    from matplotlib.lines import Line2D
    handles = [Line2D([0], [0], marker='o', color='w', markerfacecolor=c, label=s, markersize=8)
               for s, c in [('C3', '#d1495b'), ('D1', '#2e86ab'), ('S', '#1b9e77')]]
    ax.legend(handles=handles, loc='upper right')
    ax.set_xlabel('history span (m)')
    ax.set_ylabel('yaw median diff (rad)')
    ax.set_title('Gate G1/G2 decisions (repair = left of line OR above dotted line)')
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / 'gate_stability.png', dpi=130)
    plt.close(fig)
    print('\nwrote:', sorted(p.name for p in OUT.iterdir()))


if __name__ == '__main__':
    main()
