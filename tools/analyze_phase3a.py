#!/usr/bin/python3
"""Phase 3A natural-experiment analysis: per-loop revisit-realization features.

For the 21 Phase 2C active loops, this computes transparent realization features:
planned history-path geometry, actual execution fidelity, actual-to-history polyline
distance distributions, spatial/continuous overlap, trajectory-derived orientation
consistency, Karto opportunity persistence, and matcher persistence. All orientation
features use trajectory-derived yaw (GT/SLAM TUM), never the invalid diagnostics
`scan_yaw`. Descriptive only; no ML, no threshold optimization.
"""

import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
P2C = ROOT / 'results' / 'phase2c' / 'map3'
P3A = ROOT / 'results' / 'phase3a' / 'analysis'
P3A_AGG = ROOT / 'results' / 'phase3a' / 'aggregate'

TAXONOMY_CSV = P2C / 'aggregate' / 'active_loop_confirmed_taxonomy.csv'


def wrap_angle(v):
    while v > math.pi:
        v -= 2 * math.pi
    while v < -math.pi:
        v += 2 * math.pi
    return v


def dist_pt_seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def dist_to_polyline(px, py, poly):
    return min(dist_pt_seg(px, py, poly[i][0], poly[i][1],
                           poly[i + 1][0], poly[i + 1][1])
               for i in range(len(poly) - 1))


def load_tum(path):
    samples = []
    for line in path.read_text(errors='replace').splitlines():
        parts = line.split()
        if len(parts) < 8:
            continue
        try:
            stamp = float(parts[0])
            x, y = float(parts[1]), float(parts[2])
            qx, qy, qz, qw = float(parts[4]), float(parts[5]), float(parts[6]), float(parts[7])
        except ValueError:
            continue
        yaw = math.atan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))
        samples.append((stamp, x, y, yaw))
    return samples


def parse_loop_events(rosout_path):
    """Returns (planned list, start/finish by loop order) from a rosout.log."""
    plans = []  # (vertex, waypoints, history_waypoints)
    starts = []  # (sim, vertex)
    finishes = []
    for line in rosout_path.read_text(errors='replace').splitlines():
        t = re.match(r'^([0-9.]+) ', line)
        if not t:
            continue
        sim = float(t.group(1))
        m = re.search(r'PHASE2_LOOP_PLANNED vertex=(\d+) source=\S+ waypoints=(\d+) path=(.*)', line)
        if m:
            waypoints = []
            for token in m.group(3).split(';'):
                x, y = token.split(',')
                waypoints.append((float(x), float(y)))
            plans.append((int(m.group(1)), int(m.group(2)), waypoints))
            continue
        m = re.search(r'PHASE2_LOOP_EXECUTION_STARTED vertex=(\d+)', line)
        if m:
            starts.append((sim, int(m.group(1))))
            continue
        m = re.search(r'PHASE2_LOOP_EXECUTION_FINISHED vertex=(\d+)', line)
        if m:
            finishes.append((sim, int(m.group(1))))
    return plans, starts, finishes


def keyscan_anchors(rosout_path):
    anchors = []
    for line in rosout_path.read_text(errors='replace').splitlines():
        m = re.search(r'PHASE2C_KEYSCAN_ACCEPTED unique_id=\d+ state_id=(\d+) sim_time=([0-9.]+)', line)
        if m:
            anchors.append((int(m.group(1)), float(m.group(2))))
    return anchors


def load_diagnostics(seed):
    recs = []
    path = P2C / 'seed_{}'.format(seed) / 'karto_loop_diagnostics.jsonl'
    for line in path.read_text(errors='replace').splitlines():
        if line.strip():
            recs.append(json.loads(line))
    return recs


def load_taxonomy():
    rows = []
    with TAXONOMY_CSV.open() as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def polyline_heading_change(poly):
    if len(poly) < 3:
        return 0.0
    total = 0.0
    prev = math.atan2(poly[1][1] - poly[0][1], poly[1][0] - poly[0][0])
    for i in range(1, len(poly) - 1):
        cur = math.atan2(poly[i + 1][1] - poly[i][1], poly[i + 1][0] - poly[i][0])
        total += abs(wrap_angle(cur - prev))
        prev = cur
    return total


def polyline_length(poly):
    return sum(math.hypot(poly[i + 1][0] - poly[i][0], poly[i + 1][1] - poly[i][1])
               for i in range(len(poly) - 1))


def consecutive_runs(flags):
    best = 0
    run = 0
    for flag in flags:
        run = run + 1 if flag else 0
        best = max(best, run)
    return best


def analyze_loop(seed, loop_row, plans, starts, finishes, anchors, gt, slam):
    """Compute realization features for one active loop."""
    loop_id = int(loop_row['loop_id'])
    idx = loop_id - 1
    if idx >= len(plans):
        return None
    vertex, wp_count, history = plans[idx]
    start_sim = starts[idx][0] if idx < len(starts) else None
    end_sim = finishes[idx][0] if idx < len(finishes) else None

    # --- planned history path ---
    history_len = polyline_length(history) if history else 0.0
    spacing = [math.hypot(history[i + 1][0] - history[i][0], history[i + 1][1] - history[i][1])
               for i in range(len(history) - 1)] if len(history) > 1 else []
    heading_change = polyline_heading_change(history) if history else 0.0

    # --- actual execution ---
    actual = [s for s in gt if start_sim is not None and end_sim is not None and start_sim <= s[0] <= end_sim]
    actual_len = sum(math.hypot(actual[i + 1][1] - actual[i][1], actual[i + 1][2] - actual[i][2])
                     for i in range(len(actual) - 1)) if len(actual) > 1 else 0.0
    exec_time = (end_sim - start_sim) if (start_sim is not None and end_sim is not None) else None
    loop_keyscans = [sid for sid, sim in anchors if start_sim is not None and start_sim - 1 <= sim <= end_sim + 1]

    # --- actual-to-history polyline distance distribution ---
    if history and actual:
        dists = [dist_to_polyline(s[1], s[2], history) for s in actual]
        dists.sort()
        n = len(dists)
        ah = {
            'ah_mean_m': sum(dists) / n,
            'ah_median_m': dists[n // 2],
            'ah_p90_m': dists[min(n - 1, int(0.90 * n))],
            'ah_max_m': dists[-1],
        }
        # spatial overlap fraction within 0.5/1.0/2.0 m of history polyline
        overlap = {key: sum(1 for d in dists if d <= th) / n
                   for key, th in (('overlap_0_5m', 0.5), ('overlap_1_0m', 1.0), ('overlap_2_0m', 2.0))}
        # continuous overlap (longest consecutive actual samples within threshold)
        for key, th in (('cont_overlap_0_5m', 0.5), ('cont_overlap_1_0m', 1.0)):
            overlap[key] = consecutive_runs([d <= th for d in
                                             [dist_to_polyline(s[1], s[2], history) for s in actual]])
    else:
        ah = {'ah_mean_m': None, 'ah_median_m': None, 'ah_p90_m': None, 'ah_max_m': None}
        overlap = {'overlap_0_5m': None, 'overlap_1_0m': None, 'overlap_2_0m': None,
                   'cont_overlap_0_5m': None, 'cont_overlap_1_0m': None}

    # --- orientation consistency vs nearest pre-loop slam pose ---
    pre_loop = [s for s in slam if start_sim is not None and s[0] <= start_sim]
    yaw_diffs = []
    if pre_loop and actual:
        for s in actual:
            nearest = min(pre_loop, key=lambda p: math.hypot(s[1] - p[1], s[2] - p[2]))
            yaw_diffs.append(abs(wrap_angle(s[3] - nearest[3])))
        yaw_diffs.sort()
        yn = len(yaw_diffs)
        yaw = {
            'yaw_diff_mean_rad': sum(yaw_diffs) / yn,
            'yaw_diff_median_rad': yaw_diffs[yn // 2],
            'yaw_diff_p90_rad': yaw_diffs[min(yn - 1, int(0.90 * yn))],
            'yaw_frac_lt_0_26': sum(1 for y in yaw_diffs if y < 0.26) / yn,
            'yaw_frac_lt_0_52': sum(1 for y in yaw_diffs if y < 0.52) / yn,
            'yaw_frac_lt_0_78': sum(1 for y in yaw_diffs if y < 0.78) / yn,
        }
    else:
        yaw = {k: None for k in ('yaw_diff_mean_rad', 'yaw_diff_median_rad', 'yaw_diff_p90_rad',
                                 'yaw_frac_lt_0_26', 'yaw_frac_lt_0_52', 'yaw_frac_lt_0_78')}

    # --- Karto opportunity persistence ---
    recs = [r for r in load_diagnostics(seed) if r.get('scan_id') in set(loop_keyscans)]
    chain_recs = [r for r in recs if r.get('event') == 'loop_search_chain']
    by_scan = {}
    for r in recs:
        by_scan.setdefault(r['scan_id'], []).append(r)
    scans_with_chain = [sid for sid in loop_keyscans if any(x.get('event') == 'loop_search_chain' for x in by_scan.get(sid, []))]
    scans_with_valid_chain = [sid for sid in scans_with_chain
                              if any(x.get('chain_size', 0) >= 4 for x in by_scan[sid])]
    # best coarse response per keyscan
    best_coarse = {}
    for sid in scans_with_chain:
        best_coarse[sid] = max(x.get('coarse_response') or 0.0 for x in by_scan[sid])
    opp = {
        'keyscans_in_loop': len(loop_keyscans),
        'keyscans_with_chain': len(scans_with_chain),
        'keyscans_with_valid_chain': len(scans_with_valid_chain),
        'fraction_keyscans_valid_chain': (len(scans_with_valid_chain) / len(loop_keyscans)
                                          if loop_keyscans else None),
        'longest_consec_valid_chain_keyscans': consecutive_runs(
            [sid in scans_with_valid_chain for sid in sorted(loop_keyscans)]),
    }

    # --- matcher persistence ---
    ordered = sorted(loop_keyscans)
    frac = {key: (sum(1 for sid in scans_with_chain if best_coarse.get(sid, -1) >= th) / len(loop_keyscans)
                  if loop_keyscans else None)
            for key, th in (('frac_coarse_ge_0_4', 0.4), ('frac_coarse_ge_0_5', 0.5), ('frac_coarse_ge_0_6', 0.6))}
    match = {
        'best_coarse_response': max(best_coarse.values()) if best_coarse else None,
        'longest_consec_coarse_ge_0_5': consecutive_runs(
            [best_coarse.get(sid, -1) >= 0.5 for sid in ordered]),
    }
    match.update(frac)

    # --- record vote counts (direct reject_reason mapping, as in analyze_phase2c) ---
    REASON_TO_STAGE = {
        'NO_CANDIDATES': 'C1',
        'ALL_CANDIDATES_NEAR_LINKED': 'C2',
        'CHAIN_TOO_SHORT': 'C3',
        'COARSE_LOW_RESPONSE': 'D1',
        'COARSE_HIGH_VARIANCE': 'D2',
        'COARSE_ALT_REJECT': 'D3',
        'FINE_LOW_RESPONSE': 'D4',
    }
    votes = Counter()
    for r in recs:
        if r.get('accepted'):
            votes['ACCEPTED'] += 1
        else:
            votes[REASON_TO_STAGE.get(r.get('reject_reason'), r.get('reject_reason') or 'UNKNOWN')] += 1
    deepest = 'CANDIDATE'
    if any(r.get('event') == 'loop_search_chain' for r in recs):
        deepest = 'FINE' if any(r.get('reject_stage') == 'FINE' for r in recs) else 'COARSE'
    if any(r.get('accepted') for r in recs):
        deepest = 'ACCEPTED'

    row = {
        'seed': seed,
        'loop_id': loop_id,
        'loop_vertex': vertex,
        'failure_subclass': loop_row['failure_subclass'],
        'evidence_level': loop_row['evidence_level'],
        'accepted': loop_row['accepted'],
        # planned history path
        'history_waypoint_count': wp_count,
        'history_path_length_m': round(history_len, 3),
        'mean_waypoint_spacing_m': round(sum(spacing) / len(spacing), 3) if spacing else None,
        'max_waypoint_spacing_m': round(max(spacing), 3) if spacing else None,
        'history_start_x': round(history[0][0], 3) if history else None,
        'history_start_y': round(history[0][1], 3) if history else None,
        'history_end_x': round(history[-1][0], 3) if history else None,
        'history_end_y': round(history[-1][1], 3) if history else None,
        'history_path_heading_change_rad': round(heading_change, 3),
        # actual execution
        'actual_path_length_m': round(actual_len, 3),
        'execution_time_sim': round(exec_time, 2) if exec_time is not None else None,
        'keyscan_count_inside_loop': len(loop_keyscans),
        'actual_to_history_mean_m': round(ah['ah_mean_m'], 3) if ah['ah_mean_m'] is not None else None,
        'actual_to_history_median_m': round(ah['ah_median_m'], 3) if ah['ah_median_m'] is not None else None,
        'actual_to_history_p90_m': round(ah['ah_p90_m'], 3) if ah['ah_p90_m'] is not None else None,
        'actual_to_history_max_m': round(ah['ah_max_m'], 3) if ah['ah_max_m'] is not None else None,
        # overlap
        'overlap_0_5m': round(overlap['overlap_0_5m'], 3) if overlap['overlap_0_5m'] is not None else None,
        'overlap_1_0m': round(overlap['overlap_1_0m'], 3) if overlap['overlap_1_0m'] is not None else None,
        'overlap_2_0m': round(overlap['overlap_2_0m'], 3) if overlap['overlap_2_0m'] is not None else None,
        'cont_overlap_0_5m_samples': overlap['cont_overlap_0_5m'],
        'cont_overlap_1_0m_samples': overlap['cont_overlap_1_0m'],
        # orientation
        'yaw_diff_mean_rad': round(yaw['yaw_diff_mean_rad'], 3) if yaw['yaw_diff_mean_rad'] is not None else None,
        'yaw_diff_median_rad': round(yaw['yaw_diff_median_rad'], 3) if yaw['yaw_diff_median_rad'] is not None else None,
        'yaw_diff_p90_rad': round(yaw['yaw_diff_p90_rad'], 3) if yaw['yaw_diff_p90_rad'] is not None else None,
        'yaw_frac_lt_0_26': round(yaw['yaw_frac_lt_0_26'], 3) if yaw['yaw_frac_lt_0_26'] is not None else None,
        'yaw_frac_lt_0_52': round(yaw['yaw_frac_lt_0_52'], 3) if yaw['yaw_frac_lt_0_52'] is not None else None,
        'yaw_frac_lt_0_78': round(yaw['yaw_frac_lt_0_78'], 3) if yaw['yaw_frac_lt_0_78'] is not None else None,
        # Karto opportunity persistence
        'fraction_keyscans_valid_chain': round(opp['fraction_keyscans_valid_chain'], 3) if opp['fraction_keyscans_valid_chain'] is not None else None,
        'longest_consec_valid_chain_keyscans': opp['longest_consec_valid_chain_keyscans'],
        'max_chain_size': max((x.get('chain_size', 0) for x in chain_recs), default=0),
        # matcher persistence
        'best_coarse_response': round(match['best_coarse_response'], 3) if match['best_coarse_response'] is not None else None,
        'longest_consec_coarse_ge_0_5': match['longest_consec_coarse_ge_0_5'],
        'frac_coarse_ge_0_4': round(match['frac_coarse_ge_0_4'], 3) if match['frac_coarse_ge_0_4'] is not None else None,
        'frac_coarse_ge_0_5': round(match['frac_coarse_ge_0_5'], 3) if match['frac_coarse_ge_0_5'] is not None else None,
        'frac_coarse_ge_0_6': round(match['frac_coarse_ge_0_6'], 3) if match['frac_coarse_ge_0_6'] is not None else None,
        # vote counts
        'num_C1': votes.get('C1', 0),
        'num_C2': votes.get('C2', 0),
        'num_C3': votes.get('C3', 0),
        'num_D1': votes.get('COARSE_LOW_RESPONSE', 0),
        'num_D2': votes.get('COARSE_HIGH_VARIANCE', 0),
        'num_D3': votes.get('COARSE_ALT_REJECT', 0),
        'num_D4': votes.get('FINE_LOW_RESPONSE', 0),
        'num_ACCEPTED': votes.get('ACCEPTED', 0),
        'deepest_stage_reached': deepest,
        'dominant_stage': loop_row['failure_subclass'][0],
    }
    return row


def main():
    P3A.mkdir(parents=True, exist_ok=True)
    P3A_AGG.mkdir(parents=True, exist_ok=True)
    taxonomy = load_taxonomy()
    rows = []
    for seed in (21001, 21002, 21003, 21004, 21005):
        rosout = P2C / 'seed_{}'.format(seed) / 'rosout.log'
        gt = P2C / 'seed_{}'.format(seed) / 'trajectory_gt.txt'
        slam = P2C / 'seed_{}'.format(seed) / 'trajectory_slam.txt'
        plans, starts, finishes = parse_loop_events(rosout)
        anchors = keyscan_anchors(rosout)
        gt_s = load_tum(gt)
        slam_s = load_tum(slam)
        seed_rows = [r for r in taxonomy if int(r['seed']) == seed]
        for loop_row in seed_rows:
            row = analyze_loop(seed, loop_row, plans, starts, finishes, anchors, gt_s, slam_s)
            if row:
                rows.append(row)

    fieldnames = list(rows[0].keys())
    with (P3A / 'loop_realization_features.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)

    # same-vertex comparison
    by_vertex = defaultdict(list)
    for r in rows:
        by_vertex[r['loop_vertex']].append(r)
    with (P3A / 'same_vertex_comparison.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for vertex in sorted(by_vertex):
            if len(by_vertex[vertex]) > 1:
                for r in sorted(by_vertex[vertex], key=lambda x: (x['seed'], x['loop_id'])):
                    writer.writerow(r)

    # matched-case comparison vs the single success (seed 21001 loop 4)
    success = next(r for r in rows if r['accepted'] == 'True')
    with (P3A / 'matched_case_comparison.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerow(success)
        # same vertex, then similar waypoint count / AH / gap
        candidates = [r for r in rows if r is not success]
        candidates.sort(key=lambda r: (
            0 if r['loop_vertex'] == success['loop_vertex'] else 1,
            abs((r['history_waypoint_count'] or 0) - (success['history_waypoint_count'] or 0)),
            abs((r['actual_to_history_median_m'] or 9) - (success['actual_to_history_median_m'] or 9)),
        ))
        for r in candidates[:5]:
            writer.writerow(r)

    print('wrote {} loops to loop_realization_features.csv'.format(len(rows)))
    for r in sorted(rows, key=lambda x: (x['seed'], x['loop_id'])):
        print('s{} l{} v{:<3} {}  ov1m={} cont1m={} yawmed={} vcfrac={} maxchain={} bestcoarse={}'.format(
            r['seed'], r['loop_id'], r['loop_vertex'], r['failure_subclass'],
            r['overlap_1_0m'], r['cont_overlap_1_0m_samples'], r['yaw_diff_median_rad'],
            r['fraction_keyscans_valid_chain'], r['max_chain_size'], r['best_coarse_response']))


if __name__ == '__main__':
    main()
