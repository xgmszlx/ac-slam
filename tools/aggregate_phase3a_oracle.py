#!/usr/bin/python3
"""Phase 3A oracle-result aggregation.

For each V1 oracle run under results/phase3a/oracle/, extract the target loop's Karto
evidence from its own diagnostics/rosout, then compare against the Phase 2C V0 baseline
(same seed + same loop vertex). Outputs oracle_results.csv and phase3a_summary.json.
Descriptive only.
"""

import csv
import json
import re
from collections import Counter
from pathlib import Path

from analyze_phase3a import keyscan_anchors, load_taxonomy

ROOT = Path(__file__).resolve().parents[1]
ORACLE_ROOT = ROOT / 'results' / 'phase3a' / 'oracle'
AGG = ROOT / 'results' / 'phase3a' / 'aggregate'
P2C_TAXONOMY = ROOT / 'results' / 'phase2c' / 'map3' / 'aggregate' / 'active_loop_confirmed_taxonomy.csv'
P3A_FEATURES = ROOT / 'results' / 'phase3a' / 'analysis' / 'loop_realization_features.csv'

REASON_TO_STAGE = {
    'NO_CANDIDATES': 'C1',
    'ALL_CANDIDATES_NEAR_LINKED': 'C2',
    'CHAIN_TOO_SHORT': 'C3',
    'COARSE_LOW_RESPONSE': 'D1',
    'COARSE_HIGH_VARIANCE': 'D2',
    'COARSE_ALT_REJECT': 'D3',
    'FINE_LOW_RESPONSE': 'D4',
}

# target loop per oracle run (seed -> list of (loop vertex, V0 subclass))
TARGETS = {
    'seed_21001_S-reference-v26': [(26, 'S')],
    'seed_21003_D1-v15': [(15, 'D1')],
    'seed_21004_C3-v26+D1-v22': [(26, 'C3'), (22, 'D1')],
    'seed_21005_C3-v26+D1-v22': [(26, 'C3'), (22, 'D1')],
}


def loop_windows(rosout):
    """Returns list of (start_sim, end_sim, vertex) in order."""
    starts, finishes = [], []
    for line in rosout.read_text(errors='replace').splitlines():
        m = re.match(r'^([0-9.]+) .*PHASE2_LOOP_EXECUTION_STARTED vertex=(\d+)', line)
        if m:
            starts.append((float(m.group(1)), int(m.group(2))))
        m = re.match(r'^([0-9.]+) .*PHASE2_LOOP_EXECUTION_FINISHED vertex=(\d+)', line)
        if m:
            finishes.append((float(m.group(1)), int(m.group(2))))
    return [(s[0], f[0], s[1]) for s, f in zip(starts, finishes)]


def planned_paths(rosout):
    out = []
    for line in rosout.read_text(errors='replace').splitlines():
        m = re.search(r'PHASE2_LOOP_PLANNED vertex=(\d+) source=(\S+) waypoints=(\d+) path=(.*)', line)
        if m:
            out.append((int(m.group(1)), m.group(2), int(m.group(3)), m.group(4)))
    return out


def main():
    AGG.mkdir(parents=True, exist_ok=True)
    taxonomy = load_taxonomy()
    features = {f"{r['seed']}_{r['loop_id']}": r for r in
                csv.DictReader(open(P3A_FEATURES))}

    rows = []
    for run_name, targets in TARGETS.items():
        seed = int(run_name.split('_')[1])
        run_dir = ORACLE_ROOT / run_name
        rosout = run_dir / 'rosout.log'
        diag_path = run_dir / 'karto_loop_diagnostics.jsonl'
        if not rosout.is_file() or not diag_path.is_file():
            rows.append({
                'run': run_name, 'seed': seed, 'status': 'MISSING',
                'loop_vertex': '', 'target_v0_subclass': '',
            })
            continue
        windows = loop_windows(rosout)
        paths = planned_paths(rosout)
        anchors = keyscan_anchors(rosout)
        recs = _load_diag(diag_path)

        for vertex, v0_sub in targets:
            # find the loop window(s) for this vertex
            hits = [w for w in windows if w[2] == vertex]
            if not hits:
                rows.append({'run': run_name, 'seed': seed, 'status': 'NO_LOOP',
                             'loop_vertex': vertex, 'target_v0_subclass': v0_sub})
                continue
            # take the first hit (the active loop at this vertex)
            start_sim, end_sim, v = hits[0]
            loop_id = windows.index(hits[0]) + 1
            # planned path
            path_info = next((p for p in paths if p[0] == vertex), None)
            # keyscans in loop
            loop_keyscans = [sid for sid, sim in anchors if start_sim - 1 <= sim <= end_sim + 1]
            loop_recs = [r for r in recs if r.get('scan_id') in set(loop_keyscans)]
            by_scan = {}
            for r in loop_recs:
                by_scan.setdefault(r['scan_id'], []).append(r)
            scans_with_chain = [sid for sid in loop_keyscans
                                if any(x.get('event') == 'loop_search_chain' for x in by_scan.get(sid, []))]
            scans_with_valid = [sid for sid in scans_with_chain
                                if any(x.get('chain_size', 0) >= 4 for x in by_scan[sid])]
            best_coarse = {}
            for sid in scans_with_chain:
                best_coarse[sid] = max(x.get('coarse_response') or 0.0 for x in by_scan[sid])
            best_fine = None
            accepted_any = False
            for r in loop_recs:
                if r.get('accepted'):
                    accepted_any = True
                fr = r.get('fine_response')
                if fr is not None:
                    best_fine = max(best_fine or 0.0, fr)
            votes = Counter()
            for r in loop_recs:
                if r.get('accepted'):
                    votes['ACCEPTED'] += 1
                else:
                    votes[REASON_TO_STAGE.get(r.get('reject_reason'), r.get('reject_reason') or '?')] += 1

            # extra distance/time vs V0 (from V0 planned path length)
            v0_row = features.get(f"{seed}_{loop_id}")
            trace_len_m = None
            if path_info:
                pts = [tuple(map(float, tok.split(','))) for tok in path_info[3].split(';')]
                trace_len_m = sum(( (pts[i+1][0]-pts[i][0])**2 + (pts[i+1][1]-pts[i][1])**2 )**0.5
                                  for i in range(len(pts)-1))
            extra_waypoints = (path_info[2] - int(v0_row['history_waypoint_count'])) if (path_info and v0_row) else None
            extra_distance_m = (round(trace_len_m - float(v0_row['history_path_length_m']), 2)
                                if (trace_len_m is not None and v0_row) else None)

            rows.append({
                'run': run_name, 'seed': seed, 'status': 'OK',
                'loop_vertex': vertex, 'loop_id': loop_id,
                'target_v0_subclass': v0_sub,
                'v1_waypoints': path_info[2] if path_info else None,
                'v1_trace_len_m': round(trace_len_m, 2) if trace_len_m else None,
                'v0_waypoints': v0_row['history_waypoint_count'] if v0_row else None,
                'extra_waypoints': extra_waypoints,
                'extra_distance_m': extra_distance_m,
                'execution_time_sim': round(end_sim - start_sim, 1),
                'keyscans_in_loop': len(loop_keyscans),
                'fraction_valid_chain': round(len(scans_with_valid) / len(loop_keyscans), 3) if loop_keyscans else None,
                'longest_consec_valid_chain': _consec([sid in scans_with_valid for sid in sorted(loop_keyscans)]),
                'max_chain_size': max((x.get('chain_size', 0) for x in loop_recs), default=0),
                'best_coarse': round(max(best_coarse.values()), 3) if best_coarse else None,
                'best_fine': round(best_fine, 3) if best_fine is not None else None,
                'accepted': accepted_any,
                'votes': json.dumps(dict(votes)),
                # V0 baseline (Phase 2C)
                'v0_subclass': v0_row['failure_subclass'] if v0_row else None,
                'v0_fraction_valid_chain': v0_row['fraction_keyscans_valid_chain'] if v0_row else None,
                'v0_best_coarse': v0_row['best_coarse_response'] if v0_row else None,
                'v0_max_chain': v0_row['max_chain_size'] if v0_row else None,
                'v0_accepted': v0_row['accepted'] if v0_row else None,
            })

    fieldnames = list(rows[0].keys())
    with (AGG / 'oracle_results.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        'cases': len(rows),
        'accepted_v1': sum(1 for r in rows if r.get('accepted')),
        'coarse_ge_0_6_v1': sum(1 for r in rows if (r.get('best_coarse') or 0) >= 0.6),
        'improved_valid_chain_v1': sum(
            1 for r in rows
            if r.get('v0_fraction_valid_chain') is not None and r.get('fraction_valid_chain') is not None
            and r['fraction_valid_chain'] > float(r['v0_fraction_valid_chain']) + 0.05),
        'improved_best_coarse_v1': sum(
            1 for r in rows
            if r.get('v0_best_coarse') is not None and r.get('best_coarse') is not None
            and r['best_coarse'] > float(r['v0_best_coarse']) + 0.02),
    }
    (AGG / 'phase3a_summary.json').write_text(json.dumps(summary, indent=2) + '\n')

    print('aggregated {} target loops'.format(len(rows)))
    for r in rows:
        print('{run} v{loop_vertex} [{target_v0_subclass}->v1] vc={fraction_valid_chain} (v0 {v0_fraction_valid_chain}) '
              'coarse={best_coarse} (v0 {v0_best_coarse}) chain={max_chain_size} acc={accepted} extra_wp={extra_waypoints}'.format(**r))


def _consec(flags):
    best = run = 0
    for f in flags:
        run = run + 1 if f else 0
        best = max(best, run)
    return best


def _load_diag(path):
    recs = []
    for line in path.read_text(errors='replace').splitlines():
        if line.strip():
            recs.append(json.loads(line))
    return recs


if __name__ == '__main__':
    main()
