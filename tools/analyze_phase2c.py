#!/usr/bin/python3
"""Phase 2C analysis: align Karto loop diagnostics to active-loop events.

For each Phase 2C run (results/phase2c/map3/seed_XXXXX) this script:

  1. parses the Karto loop-diagnostics JSONL,
  2. parses rosout for PHASE2_LOOP_* events, PHASE2C_KEYSCAN_ACCEPTED anchors and
     accepted "Add one Loop closure" callbacks,
  3. aligns each active loop to the keyscans / loop-search records generated inside
     its execution interval (via the sim-time anchors),
  4. classifies every loop into the Phase 2C taxonomy (C1-C4 / D1-D5 / S / U) with an
     evidence level (Confirmed only when direct Karto internal evidence exists),
  5. compares against the old Phase 2B labels to build a transition matrix, and
  6. writes aggregate CSV/JSON summaries plus a few descriptive plots.

This is descriptive analysis only; no ML, no regression score, no probability model,
no threshold optimization.
"""

import argparse
import csv
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
PHASE2C_ROOT = ROOT / 'results' / 'phase2c' / 'map3'
PHASE2B_TAXONOMY = ROOT / 'results' / 'phase2b' / 'diagnosis' / 'failure_taxonomy.csv'
AGG_DIR = PHASE2C_ROOT / 'aggregate'

LOOP_SEARCH_MAX_M = 4.0
CHAIN_MIN = 4
RESP_COARSE = 0.6
RESP_FINE = 0.7
VAR_COARSE = 0.16
SCAN_BUFFER = 70

TAXONOMY_ORDER = ['C1', 'C2', 'C3', 'C4', 'D1', 'D2', 'D3', 'D4', 'D5', 'S', 'U']


def wrap_angle(value):
    while value > math.pi:
        value -= 2.0 * math.pi
    while value < -math.pi:
        value += 2.0 * math.pi
    return value


def euclidean(left, right):
    return math.hypot(left[0] - right[0], left[1] - right[1])


def parse_diagnostics(path):
    records = []
    for line in path.read_text(errors='replace').splitlines():
        line = line.strip()
        if not line:
            continue
        records.append(json.loads(line))
    return records


def parse_rosout(path):
    """Returns (loop_events, keyscan_anchors, accepted_callbacks)."""
    loop_events = []
    keyscan_anchors = []  # (state_id, sim_time)
    accepted_callbacks = []  # sim_time
    for line in path.read_text(errors='replace').splitlines():
        sim_match = re.match(r'^([0-9.]+)\s+', line)
        sim_time = float(sim_match.group(1)) if sim_match else None
        if 'PHASE2_LOOP_PLANNED' in line:
            m = re.search(r'PHASE2_LOOP_PLANNED vertex=(\d+) source=(\S+) waypoints=(\d+) path=(.+)$', line)
            if m:
                waypoints = []
                for token in m.group(4).split(';'):
                    x, y = token.split(',')
                    waypoints.append((float(x), float(y)))
                loop_events.append({
                    'type': 'planned', 'sim_time': sim_time, 'vertex': int(m.group(1)),
                    'source': m.group(2), 'waypoints_planned': int(m.group(3)),
                    'history_waypoints': waypoints,
                })
        elif 'PHASE2_LOOP_EXECUTION_STARTED' in line:
            m = re.search(r'PHASE2_LOOP_EXECUTION_STARTED vertex=(\d+) waypoints=(\d+)', line)
            if m:
                loop_events.append({'type': 'start', 'sim_time': sim_time,
                                    'vertex': int(m.group(1)), 'waypoints': int(m.group(2))})
        elif 'PHASE2_LOOP_EXECUTION_FINISHED' in line:
            m = re.search(r'PHASE2_LOOP_EXECUTION_FINISHED vertex=(\d+) waypoints=(\d+)', line)
            if m:
                loop_events.append({'type': 'finish', 'sim_time': sim_time,
                                    'vertex': int(m.group(1)), 'waypoints': int(m.group(2))})
        elif 'PHASE2_LOOP_WAYPOINT_REACHED' in line:
            m = re.search(r'PHASE2_LOOP_WAYPOINT_REACHED vertex=(\d+) waypoint=(\d+)', line)
            if m:
                loop_events.append({'type': 'waypoint', 'sim_time': sim_time,
                                    'vertex': int(m.group(1)), 'waypoint': int(m.group(2))})
        elif 'PHASE2C_KEYSCAN_ACCEPTED' in line:
            m = re.search(r'PHASE2C_KEYSCAN_ACCEPTED unique_id=(\d+) state_id=(\d+) sim_time=([0-9.]+)', line)
            if m:
                keyscan_anchors.append((int(m.group(2)), float(m.group(3))))
        elif 'Add one Loop closure' in line:
            accepted_callbacks.append(sim_time)
    return loop_events, keyscan_anchors, accepted_callbacks


def build_loops(loop_events):
    """Pair planned/start/finish events into loop records (sequential execution)."""
    planned = [e for e in loop_events if e['type'] == 'planned']
    starts = [e for e in loop_events if e['type'] == 'start']
    finishes = [e for e in loop_events if e['type'] == 'finish']
    waypoints = [e for e in loop_events if e['type'] == 'waypoint']
    loops = []
    for index, plan in enumerate(planned):
        start = starts[index] if index < len(starts) else None
        finish = finishes[index] if index < len(finishes) else None
        loop_waypoints = [w for w in waypoints
                          if w['vertex'] == plan['vertex']]
        loop = {
            'loop_id': index + 1,
            'loop_vertex': plan['vertex'],
            'planned_sim_time': plan['sim_time'],
            'start_sim_time': start['sim_time'] if start else None,
            'finish_sim_time': finish['sim_time'] if finish else None,
            'waypoints_planned': plan['waypoints_planned'],
            'waypoints_reached': len(loop_waypoints),
            'history_waypoints': plan['history_waypoints'],
            'reliable_source': plan['source'],
        }
        loops.append(loop)
    return loops


def load_tum(path):
    samples = []
    for line in path.read_text(errors='replace').splitlines():
        parts = line.split()
        if len(parts) < 8:
            continue
        try:
            stamp = float(parts[0])
            x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
            qx, qy, qz, qw = float(parts[4]), float(parts[5]), float(parts[6]), float(parts[7])
        except ValueError:
            continue
        yaw = math.atan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))
        samples.append((stamp, x, y, yaw))
    return samples


def loop_geometry(loop, gt_samples, slam_pre_loop):
    """Compute A-H min distance, delta yaw and overlap ratio for one loop.

    - A-H min distance: min over actual loop GT samples of distance to any
      service-selected history waypoint (from PHASE2_LOOP_PLANNED path).
    - delta yaw: yaw of the closest actual GT sample minus the yaw of the nearest
      pre-loop Karto pose (has a heading; the service waypoints carry x,y only).
    - overlap ratio: fraction of actual loop GT samples within 1 m of any pre-loop
      Karto pose (same definition as Phase 2B).
    """
    history = loop['history_waypoints']
    start = loop['start_sim_time']
    end = loop['finish_sim_time']
    if start is None or end is None:
        return {'interval_valid': False}
    actual = [s for s in gt_samples if start <= s[0] <= end]
    if not actual:
        return {'interval_valid': False, 'actual_samples': 0}
    pre_loop = [s for s in slam_pre_loop if s[0] <= start]

    min_dist = float('inf')
    min_sample = None
    for sample in actual:
        for hx, hy in history:
            dist = euclidean((sample[1], sample[2]), (hx, hy))
            if dist < min_dist:
                min_dist = dist
                min_sample = sample

    delta_yaw = None
    if min_sample is not None and pre_loop:
        nearest = min(pre_loop, key=lambda s: euclidean(
            (min_sample[1], min_sample[2]), (s[1], s[2])))
        delta_yaw = wrap_angle(min_sample[3] - nearest[3])

    overlap = None
    if pre_loop:
        within = sum(
            1 for sample in actual
            if any(euclidean((sample[1], sample[2]), (px, py)) <= 1.0
                   for _, px, py, _ in pre_loop)
        )
        overlap = within / len(actual)

    return {
        'interval_valid': True,
        'actual_samples': len(actual),
        'actual_to_history_min_distance_m': min_dist,
        'delta_yaw_at_closest_rad': delta_yaw,
        'overlap_ratio_1m': overlap,
        'history_pose_count': len(history),
        'history_poses': json.dumps([[round(h[0], 3), round(h[1], 3)] for h in history]),
    }


def classify_loop(loop, loop_records, keyscan_ids):
    """Phase 2C taxonomy classification using direct Karto diagnostics.

    Classification rule:
    - accepted anywhere -> S (Confirmed).
    - otherwise classify by the DOMINANT mechanism across the loop's records:
      each no-chain record votes C1/C2/C3 by its reject reason; each chain record
      votes D1/D2/D3/D4/D5 by its reject stage/reason. The most frequent vote wins
      (ties resolved toward the deeper stage). A separate `deepest_stage_reached`
      is reported so mixed loops are not misrepresented.
    """
    if not loop_records:
        return {
            'failure_class': 'U', 'failure_subclass': 'U',
            'evidence_level': 'Unknown',
            'direct_evidence': 'no diagnostics record aligned to this loop',
            'deepest_stage_reached': 'NONE',
        }
    accepted_records = [r for r in loop_records if r.get('accepted') is True]
    if accepted_records:
        best = max(accepted_records, key=lambda r: r.get('coarse_response') or 0.0)
        return {
            'failure_class': 'S', 'failure_subclass': 'S',
            'evidence_level': 'Confirmed',
            'deepest_stage_reached': 'ACCEPTED',
            'direct_evidence': (
                'accepted: scan_id={} chain_size={} coarse_response={:.4f} fine_response={:.4f} '
                'min_gap={}'.format(
                    best['scan_id'], best['chain_size'],
                    best.get('coarse_response'), best.get('fine_response'),
                    best.get('min_scan_index_gap'))),
        }

    chain_records = [r for r in loop_records if r.get('event') == 'loop_search_chain']
    no_chain_records = [r for r in loop_records if r.get('event') == 'loop_search_no_chain']

    # deepest stage across the loop
    deepest = 'CANDIDATE'
    if chain_records:
        deepest = 'COARSE'
        if any(r.get('reject_stage') == 'FINE' for r in chain_records):
            deepest = 'FINE'
        if any(r.get('accepted') for r in chain_records):
            deepest = 'ACCEPTED'

    # per-record votes
    votes = []

    def vote_no_chain(record):
        if (record.get('historical_scans_in_distance') or 0) == 0:
            return 'C1'
        if ((record.get('historical_scans_in_distance') or 0)
                <= (record.get('historical_scans_filtered_near_linked') or 0)):
            return 'C2'
        return 'C3'

    for r in no_chain_records:
        votes.append(vote_no_chain(r))

    def vote_chain(record):
        if record.get('reject_stage') == 'FINE':
            return 'D4'
        reason = record.get('reject_reason')
        return {'COARSE_LOW_RESPONSE': 'D1',
                'COARSE_HIGH_VARIANCE': 'D2',
                'COARSE_ALT_REJECT': 'D3'}.get(reason, 'D5')

    for r in chain_records:
        votes.append(vote_chain(r))

    if not votes:
        return {
            'failure_class': 'U', 'failure_subclass': 'U',
            'evidence_level': 'Unknown',
            'direct_evidence': 'records present but none classified',
            'deepest_stage_reached': deepest,
        }

    # dominant vote; tie-break toward the deeper stage
    tally = Counter(votes)
    max_count = max(tally.values())
    candidates = [code for code, count in tally.items() if count == max_count]
    depth_order = ['C1', 'C2', 'C3', 'D1', 'D2', 'D3', 'D4', 'D5']
    dominant = max(candidates, key=lambda code: depth_order.index(code))

    evidence = classify_direct_evidence(dominant, chain_records, no_chain_records)
    return {
        'failure_class': dominant[0],
        'failure_subclass': dominant,
        'evidence_level': 'Confirmed',
        'deepest_stage_reached': deepest,
        'direct_evidence': evidence,
        'record_vote_tally': json.dumps(dict(tally), sort_keys=True),
    }


def classify_direct_evidence(subclass, chain_records, no_chain_records):
    """Builds a one-line direct-evidence string for the dominant subclass."""
    if subclass.startswith('D') and chain_records:
        best = max(chain_records, key=lambda r: r.get('coarse_response') or 0.0)
        reason = best.get('reject_reason')
        return (
            'coarse/fine rejected: scan_id={} chain_size={} coarse_response={:.4f} '
            'required={:.2f} cov_x={:.4f} cov_y={:.4f} required_var={:.2f} reason={}'.format(
                best['scan_id'], best['chain_size'], best.get('coarse_response'),
                RESP_COARSE, best.get('coarse_variance_x'), best.get('coarse_variance_y'),
                VAR_COARSE, reason))
    if subclass.startswith('C') and no_chain_records:
        best = max(no_chain_records, key=lambda r: (r.get('historical_scans_in_distance') or 0))
        return (
            'no valid chain: scan_id={} in_distance={} near_linked={} '
            'required_chain_size={} reason={}'.format(
                best['scan_id'], best.get('historical_scans_in_distance'),
                best.get('historical_scans_filtered_near_linked'), CHAIN_MIN,
                best.get('reject_reason')))
    return 'no direct record for {}'.format(subclass)


def per_loop_matcher_stats(loop_records):
    """Best/aggregate matcher statistics across all records aligned to the loop."""
    stats = {
        'candidate_count_max': None,
        'near_linked_filtered_max': None,
        'chain_count_total': 0,
        'max_chain_size': 0,
        'best_coarse_response': None,
        'min_coarse_variance_x': None,
        'min_coarse_variance_y': None,
        'best_fine_response': None,
        'coarse_attempted_count': 0,
        'fine_attempted_count': 0,
    }
    for r in loop_records:
        stats['candidate_count_max'] = max(
            stats['candidate_count_max'] if stats['candidate_count_max'] is not None else 0,
            r.get('historical_scans_in_distance') or 0)
        stats['near_linked_filtered_max'] = max(
            stats['near_linked_filtered_max'] if stats['near_linked_filtered_max'] is not None else 0,
            r.get('historical_scans_filtered_near_linked') or 0)
        stats['chain_count_total'] += int(r.get('candidate_chain_count') or 0)
        if r.get('event') == 'loop_search_chain':
            stats['max_chain_size'] = max(stats['max_chain_size'], int(r.get('chain_size') or 0))
            if r.get('coarse_response') is not None:
                stats['coarse_attempted_count'] += 1
                stats['best_coarse_response'] = max(
                    stats['best_coarse_response'] if stats['best_coarse_response'] is not None else -1.0,
                    float(r['coarse_response']))
                if r.get('coarse_variance_x') is not None:
                    stats['min_coarse_variance_x'] = min(
                        stats['min_coarse_variance_x'] if stats['min_coarse_variance_x'] is not None else float('inf'),
                        float(r['coarse_variance_x']))
                    stats['min_coarse_variance_y'] = min(
                        stats['min_coarse_variance_y'] if stats['min_coarse_variance_y'] is not None else float('inf'),
                        float(r['coarse_variance_y']))
            if r.get('fine_response') is not None:
                stats['fine_attempted_count'] += 1
                stats['best_fine_response'] = max(
                    stats['best_fine_response'] if stats['best_fine_response'] is not None else -1.0,
                    float(r['fine_response']))
    return stats


def load_phase2b_labels():
    """seed -> {loop_id: (old_class, old_subclass, old_evidence)} from Phase 2B."""
    mapping = {}
    if not PHASE2B_TAXONOMY.is_file():
        return mapping
    with PHASE2B_TAXONOMY.open() as handle:
        for row in csv.DictReader(handle):
            pair = int(row['pair'])
            loop_id = int(row['loop_id'])
            seed = 21000 + pair
            mapping.setdefault(seed, {})[loop_id] = {
                'old_class': row['primary_failure_category'],
                'old_evidence': row['evidence_level'],
                'old_rationale': row['rationale'],
            }
    return mapping


def run_analysis(seed_dirs):
    rows = []
    run_manifests = []
    keyscan_alignment = []
    for seed_dir in sorted(seed_dirs, key=lambda p: p.name):
        seed = int(seed_dir.name.split('_')[1])
        diag_path = seed_dir / 'karto_loop_diagnostics.jsonl'
        rosout_path = seed_dir / 'rosout.log'
        gt_path = seed_dir / 'trajectory_gt.txt'
        slam_path = seed_dir / 'trajectory_slam.txt'
        if not (diag_path.is_file() and rosout_path.is_file()):
            print('SKIP {}: missing diagnostics or rosout'.format(seed_dir.name))
            continue
        diagnostics = parse_diagnostics(diag_path)
        loop_events, anchors, callbacks = parse_rosout(rosout_path)
        loops = build_loops(loop_events)
        gt_samples = load_tum(gt_path) if gt_path.is_file() else []
        slam_samples = load_tum(slam_path) if slam_path.is_file() else []
        anchor_map = {state_id: sim for state_id, sim in anchors}

        for loop in loops:
            start = loop['start_sim_time']
            end = loop['finish_sim_time']
            geometry = loop_geometry(loop, gt_samples, slam_samples)
            if start is None or end is None:
                loop['aligned_keyscan_ids'] = []
                loop_records = []
                alignment = 'no_loop_interval'
            else:
                loop_keyscans = [sid for sid, sim in anchors if start - 1.0 <= sim <= end + 1.0]
                loop['aligned_keyscan_ids'] = loop_keyscans
                loop_records = [r for r in diagnostics if r.get('scan_id') in set(loop_keyscans)]
                alignment = ('aligned' if loop_keyscans else 'ambiguous_no_keyscan_in_interval')
            keyscan_alignment.append({'seed': seed, 'loop_id': loop['loop_id'],
                                     'alignment': alignment,
                                     'aligned_keyscan_count': len(loop.get('aligned_keyscan_ids', []))})

            classification = classify_loop(loop, loop_records, loop.get('aligned_keyscan_ids', []))
            matcher = per_loop_matcher_stats(loop_records)

            row = {
                'run': 'seed_{}'.format(seed),
                'seed': seed,
                'loop_id': loop['loop_id'],
                'loop_vertex': loop['loop_vertex'],
                'reliable_source': loop['reliable_source'],
                'history_pose_count': geometry.get('history_pose_count'),
                'history_poses': geometry.get('history_poses'),
                'actual_to_history_min_distance_m': geometry.get('actual_to_history_min_distance_m'),
                'delta_yaw_at_closest_rad': geometry.get('delta_yaw_at_closest_rad'),
                'overlap_ratio_1m': geometry.get('overlap_ratio_1m'),
                'interval_valid': geometry.get('interval_valid'),
                'aligned_keyscan_ids': json.dumps(loop.get('aligned_keyscan_ids', [])),
                'current_scan': loop.get('aligned_keyscan_ids', [])[-1] if loop.get('aligned_keyscan_ids') else None,
                'scan_gap_min': None,
                'scan_gap_max': None,
                'candidate_count_max': matcher['candidate_count_max'],
                'near_linked_filtered_max': matcher['near_linked_filtered_max'],
                'candidate_chain_count_total': matcher['chain_count_total'],
                'max_chain_size': matcher['max_chain_size'],
                'best_coarse_response': matcher['best_coarse_response'],
                'min_coarse_variance_x': matcher['min_coarse_variance_x'],
                'min_coarse_variance_y': matcher['min_coarse_variance_y'],
                'best_fine_response': matcher['best_fine_response'],
                'coarse_attempted_count': matcher['coarse_attempted_count'],
                'fine_attempted_count': matcher['fine_attempted_count'],
                'karto_accepted_callbacks_in_run': len(callbacks),
                'accepted': classification['failure_subclass'] == 'S',
                'failure_class': classification['failure_class'],
                'failure_subclass': classification['failure_subclass'],
                'evidence_level': classification['evidence_level'],
                'deepest_stage_reached': classification.get('deepest_stage_reached', 'NONE'),
                'record_vote_tally': classification.get('record_vote_tally'),
                'direct_evidence': classification['direct_evidence'],
            }
            chain_records = [r for r in loop_records if r.get('event') == 'loop_search_chain']
            if chain_records:
                gaps = []
                for r in chain_records:
                    if r.get('min_scan_index_gap') is not None:
                        gaps.append(int(r['min_scan_index_gap']))
                        gaps.append(int(r['max_scan_index_gap']))
                if gaps:
                    row['scan_gap_min'] = min(gaps)
                    row['scan_gap_max'] = max(gaps)
            rows.append(row)

        run_manifests.append({
            'run': 'seed_{}'.format(seed), 'seed': seed,
            'diagnostics_records': len(diagnostics),
            'keyscan_anchors': len(anchors),
            'accepted_callbacks': len(callbacks),
            'planned_loops': len(loops),
        })

    return rows, run_manifests, keyscan_alignment


def write_outputs(rows, run_manifests, keyscan_alignment, phase2b_labels):
    AGG_DIR.mkdir(parents=True, exist_ok=True)

    with (AGG_DIR / 'active_loop_confirmed_taxonomy.csv').open('w', newline='') as handle:
        fieldnames = [
            'run', 'seed', 'loop_id', 'loop_vertex', 'reliable_source',
            'history_pose_count', 'history_poses',
            'actual_to_history_min_distance_m', 'delta_yaw_at_closest_rad',
            'overlap_ratio_1m', 'interval_valid', 'aligned_keyscan_ids',
            'current_scan', 'scan_gap_min', 'scan_gap_max',
            'candidate_count_max', 'near_linked_filtered_max',
            'candidate_chain_count_total', 'max_chain_size',
            'best_coarse_response', 'min_coarse_variance_x', 'min_coarse_variance_y',
            'best_fine_response', 'coarse_attempted_count', 'fine_attempted_count',
            'karto_accepted_callbacks_in_run', 'accepted',
            'failure_class', 'failure_subclass', 'evidence_level', 'deepest_stage_reached',
            'record_vote_tally', 'direct_evidence',
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    with (AGG_DIR / 'run_manifest.csv').open('w', newline='') as handle:
        fieldnames = ['run', 'seed', 'diagnostics_records', 'keyscan_anchors',
                      'accepted_callbacks', 'planned_loops']
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for row in run_manifests:
            writer.writerow(row)

    with (AGG_DIR / 'keyscan_alignment.csv').open('w', newline='') as handle:
        fieldnames = ['seed', 'loop_id', 'alignment', 'aligned_keyscan_count']
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(keyscan_alignment)

    # failure subtype counts
    subtype_counts = Counter(row['failure_subclass'] for row in rows)
    class_counts = Counter(row['failure_class'] for row in rows)
    evidence_counts = Counter(row['evidence_level'] for row in rows)
    with (AGG_DIR / 'failure_subtype_counts.csv').open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['taxonomy', 'class', 'count'])
        for code in TAXONOMY_ORDER:
            count = subtype_counts.get(code, 0)
            if count:
                writer.writerow([code, code[0], count])
        writer.writerow([])
        writer.writerow(['class', '', 'count'])
        for cls in sorted(class_counts):
            writer.writerow([cls, '', class_counts[cls]])
        writer.writerow([])
        writer.writerow(['evidence_level', '', 'count'])
        for ev in sorted(evidence_counts):
            writer.writerow([ev, '', evidence_counts[ev]])

    # failure transition matrix (old Phase 2B -> new Phase 2C), per-seed by loop index
    transition = []
    for seed, labels in sorted(phase2b_labels.items()):
        new_rows = [r for r in rows if r['seed'] == seed]
        for loop_id, old in sorted(labels.items()):
            new_row = next((r for r in new_rows if r['loop_id'] == loop_id), None)
            if new_row is None:
                continue
            old_class = old['old_class']
            new_label = new_row['failure_subclass']
            transition.append({
                'seed': seed, 'loop_id': loop_id,
                'old_phase2b_class': old_class,
                'old_phase2b_evidence': old['old_evidence'],
                'new_phase2c_subclass': new_label,
                'new_evidence_level': new_row['evidence_level'],
                'match_by': 'loop_index_and_seed',
                'note': (
                    'Phase 2C is an independent run with the same seed; loop matching '
                    'is by loop index within the run, not by shared loop identity.'
                ),
            })
    with (AGG_DIR / 'failure_transition_matrix.csv').open('w', newline='') as handle:
        fieldnames = ['seed', 'loop_id', 'old_phase2b_class', 'old_phase2b_evidence',
                      'new_phase2c_subclass', 'new_evidence_level', 'match_by', 'note']
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(transition)

    # matcher statistics
    with (AGG_DIR / 'matcher_statistics.csv').open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['metric', 'mean', 'median', 'min', 'max', 'count'])
        numeric = {
            'candidate_count_max': 'candidate_count_max',
            'near_linked_filtered_max': 'near_linked_filtered_max',
            'max_chain_size': 'max_chain_size',
            'best_coarse_response': 'best_coarse_response',
            'min_coarse_variance_x': 'min_coarse_variance_x',
            'min_coarse_variance_y': 'min_coarse_variance_y',
            'best_fine_response': 'best_fine_response',
            'actual_to_history_min_distance_m': 'actual_to_history_min_distance_m',
            'overlap_ratio_1m': 'overlap_ratio_1m',
        }
        for label, key in numeric.items():
            values = [r[key] for r in rows if r.get(key) is not None]
            if values:
                writer.writerow([label,
                                 round(statistics.mean(values), 6),
                                 round(statistics.median(values), 6),
                                 round(min(values), 6),
                                 round(max(values), 6),
                                 len(values)])
            else:
                writer.writerow([label, 'NA', 'NA', 'NA', 'NA', 0])

    summary = {
        'runs': len(run_manifests),
        'total_loops': len(rows),
        'accepted_loops': sum(1 for r in rows if r['accepted']),
        'failure_class_counts': dict(class_counts),
        'failure_subtype_counts': dict(subtype_counts),
        'evidence_counts': dict(evidence_counts),
        'confirmed_count': evidence_counts.get('Confirmed', 0),
        'alignment': Counter(k['alignment'] for k in keyscan_alignment),
        'taxonomy_definitions': {
            'C1': 'No spatial historical candidate (0 scans within LoopSearchMaximumDistance)',
            'C2': 'Candidates exist but all removed as near-linked',
            'C3': 'Candidate scans exist but valid chain insufficient (below 4 or broken)',
            'C4': 'Other opportunity failure',
            'D1': 'Coarse response rejection',
            'D2': 'Coarse variance rejection',
            'D3': 'Alternate coarse branch rejection',
            'D4': 'Fine response rejection',
            'D5': 'Other matcher rejection',
            'S': 'Accepted successful loop',
            'U': 'Unknown',
        },
    }
    (AGG_DIR / 'phase2c_summary.json').write_text(
        json.dumps(summary, indent=2, sort_keys=True) + '\n')
    return summary


def make_plots(rows):
    AGG_DIR.mkdir(parents=True, exist_ok=True)

    # failure subtype counts
    counts = Counter(row['failure_subclass'] for row in rows)
    codes = [c for c in TAXONOMY_ORDER if counts.get(c)]
    values = [counts[c] for c in codes]
    if codes:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(codes, values, color='#4C72B0')
        ax.set_title('Phase 2C failure subtype counts')
        ax.set_xlabel('subtype')
        ax.set_ylabel('loops')
        for i, v in enumerate(values):
            ax.text(i, v + 0.1, str(v), ha='center')
        fig.tight_layout()
        fig.savefig(AGG_DIR / 'failure_subtype_counts.png', dpi=150)
        plt.close(fig)

    # old vs new taxonomy (class-level)
    old_counts = Counter()
    new_counts = Counter(row['failure_class'] for row in rows)
    if (AGG_DIR / 'failure_transition_matrix.csv').is_file():
        with (AGG_DIR / 'failure_transition_matrix.csv').open() as handle:
            for row in csv.DictReader(handle):
                old_class = row['old_phase2b_class']
                old_counts[old_class[0]] += 1
    labels = sorted(set(old_counts) | set(new_counts))
    if labels:
        x = list(range(len(labels)))
        width = 0.38
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar([i - width / 2 for i in x], [old_counts.get(l, 0) for l in labels], width,
               label='Phase 2B (reconstructed)', color='#C44E52')
        ax.bar([i + width / 2 for i in x], [new_counts.get(l, 0) for l in labels], width,
               label='Phase 2C (direct diagnostics)', color='#55A868')
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_ylabel('loops')
        ax.set_title('Old (Phase 2B) vs new (Phase 2C) failure class counts')
        ax.legend()
        fig.tight_layout()
        fig.savefig(AGG_DIR / 'old_vs_new_taxonomy.png', dpi=150)
        plt.close(fig)

    def hist(values, name, title, xlabel):
        values = [v for v in values if v is not None]
        if not values:
            return
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.hist(values, bins=min(20, max(5, len(set(values)))), color='#4C72B0')
        ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.set_ylabel('loops')
        fig.tight_layout()
        fig.savefig(AGG_DIR / name, dpi=150)
        plt.close(fig)

    hist([r['best_coarse_response'] for r in rows if r['coarse_attempted_count']],
         'coarse_response_distribution.png',
         'Best coarse response per loop (threshold 0.60)', 'coarse response')
    hist([r['best_fine_response'] for r in rows if r['fine_attempted_count']],
         'fine_response_distribution.png',
         'Best fine response per loop (threshold 0.70)', 'fine response')
    hist([r['max_chain_size'] for r in rows],
         'chain_size_distribution.png',
         'Max candidate chain size per loop (minimum 4)', 'chain size')

    # overlap vs failure class
    classes = sorted(set(r['failure_class'] for r in rows))
    if classes:
        fig, ax = plt.subplots(figsize=(8, 4))
        data = [[r['overlap_ratio_1m'] for r in rows if r['failure_class'] == cls
                 and r['overlap_ratio_1m'] is not None] for cls in classes]
        ax.boxplot(data, labels=classes)
        ax.set_title('Trajectory overlap (1 m) by failure class')
        ax.set_ylabel('overlap ratio')
        fig.tight_layout()
        fig.savefig(AGG_DIR / 'overlap_vs_failure.png', dpi=150)
        plt.close(fig)

    # yaw vs failure class
    if classes:
        fig, ax = plt.subplots(figsize=(8, 4))
        data = [[r['delta_yaw_at_closest_rad'] for r in rows if r['failure_class'] == cls
                 and r['delta_yaw_at_closest_rad'] is not None] for cls in classes]
        ax.boxplot(data, labels=classes)
        ax.set_title('Delta yaw at closest approach by failure class')
        ax.set_ylabel('delta yaw (rad)')
        fig.tight_layout()
        fig.savefig(AGG_DIR / 'yaw_vs_failure.png', dpi=150)
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=PHASE2C_ROOT)
    args = parser.parse_args()
    if not args.root.is_dir():
        raise SystemExit('no Phase 2C root: {}'.format(args.root))
    seed_dirs = sorted(args.root.glob('seed_*'))
    if not seed_dirs:
        raise SystemExit('no seed_* run directories found')
    rows, run_manifests, keyscan_alignment = run_analysis(seed_dirs)
    phase2b_labels = load_phase2b_labels()
    summary = write_outputs(rows, run_manifests, keyscan_alignment, phase2b_labels)
    make_plots(rows)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
