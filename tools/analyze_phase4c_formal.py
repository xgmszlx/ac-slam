#!/usr/bin/env python3
"""Frozen offline aggregation for Phase 4C formal cross-environment runs."""

import csv
import hashlib
import json
import math
import pickle
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from audit_phase4c0_attribution import parse_keyscan_times
from audit_phase4c05_neutrality import neutral_target
from evaluate_mapping import load_map
from evaluate_mapping_v2 import evaluate_maps_v2
from phase4c_formal_common import FORMAL_ROOT, MAPS, ROOT


AGGREGATE = ROOT / 'results' / 'phase4c' / 'aggregate'
WRITE_RUN_ARTIFACTS = True
METHOD_DIRS = {'A': 'A_original', 'B': 'B_always_trace', 'C': 'C_selective'}
METHOD_NAMES = {'A': 'Original', 'B': 'Always-Trace', 'C': 'Selective'}
CONTRASTS = (('C', 'A', 'C-A'), ('B', 'A', 'B-A'), ('C', 'B', 'C-B'))
POSE_FIELDS = (
    'map', 'seed', 'condition', 'method', 'loop_id', 'event_seq',
    'historical_pose_count', 'mean_historical_pose_correction_m',
    'median_historical_pose_correction_m', 'max_historical_pose_correction_m',
    'status', 'reason',
)


def load_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text()) if path.is_file() else default


def write_csv(path, rows, fields=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0]) if rows else []
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def canonical_hash(value):
    raw = json.dumps(value, separators=(',', ':'), ensure_ascii=True).encode('ascii')
    return hashlib.sha256(raw).hexdigest()


def result_path(path):
    """Use a repository-relative path when possible, else a stable absolute path."""
    try:
        return str(Path(path).relative_to(ROOT))
    except ValueError:
        return str(Path(path))


def selected_formal_run(map_id, seed, label):
    method_dir = FORMAL_ROOT / map_id / 'seed_{}'.format(seed) / METHOD_DIRS[label]
    selected = load_json(method_dir / 'selected_attempt.json')
    if not selected:
        return None
    return ROOT / selected['run_dir']


def run_inventory():
    runs = []
    map3_root = ROOT / 'results' / 'phase4b' / 'map3'
    for seed in range(21001, 21006):
        for label, directory in METHOD_DIRS.items():
            path = map3_root / 'seed_{}'.format(seed) / directory
            if path.is_dir():
                runs.append(('map3', seed, label, path))
    for map_id in MAPS:
        for seed in range(21001, 21006):
            for label in 'ABC':
                path = selected_formal_run(map_id, seed, label)
                if path:
                    runs.append((map_id, seed, label, path))
    return runs


def load_prior(run_dir):
    paths = sorted((run_dir / 'author_outputs').glob('prior_map_*.pickle'))
    if len(paths) != 1:
        raise RuntimeError('expected one prior pickle in {}'.format(run_dir))
    with paths[0].open('rb') as stream:
        return pickle.load(stream)


def attribute_run(map_id, seed, label, run_dir):
    manifest = load_json(run_dir / 'manifest.json')
    loops = load_json(run_dir / 'loops.json', {'loops': []})['loops']
    events = load_json(run_dir / 'closure_events.json', {'events': []})['events']
    prior = load_prior(run_dir)
    keyscan_times = parse_keyscan_times(run_dir / 'rosout.log')
    targets = {}
    target_rows = []
    for order, loop in enumerate(loops, start=1):
        snapshot = load_json(run_dir / loop['snapshot_before'])
        target = neutral_target(loop, snapshot, prior)
        targets[int(loop['loop_id'])] = target
        target_rows.append({
            'map': map_id, 'seed': seed, 'condition': label,
            'method': METHOD_NAMES[label], 'selection_order': order,
            'loop_id': loop['loop_id'], 'loop_vertex': loop['loop_vertex'],
            'baseline_anchor_scan': target['anchor'],
            'h_star_ids': json.dumps(target['ids']), 'h_star_size': target['size'],
            'local_roi_center_x': prior.nodes[int(loop['loop_vertex'])]['position'][0],
            'local_roi_center_y': prior.nodes[int(loop['loop_vertex'])]['position'][1],
            'local_roi_radius_m': 5.0,
        })
    event_rows = []
    target_loop_ids = set()
    temporal_loop_ids = set()
    for event in events:
        current = int(event['current_scan'])
        scan_time = keyscan_times.get(current)
        matching = [
            loop for loop in loops
            if scan_time is not None and loop.get('actual_start_time') is not None
            and loop.get('actual_end_time') is not None
            and float(loop['actual_start_time']) <= scan_time <= float(loop['actual_end_time'])
        ]
        loop = matching[0] if len(matching) == 1 else None
        target = targets.get(int(loop['loop_id'])) if loop else None
        overlap = []
        attribution = 'PASSIVE_OR_UNRELATED'
        if loop is not None:
            chain = set(range(int(event['chain_start']), int(event['chain_end']) + 1))
            overlap = sorted(chain.intersection(target['ids']))
            if overlap:
                attribution = 'TARGET_ATTRIBUTABLE'
                target_loop_ids.add(int(loop['loop_id']))
            else:
                attribution = 'TEMPORALLY_ASSOCIATED'
                temporal_loop_ids.add(int(loop['loop_id']))
        event_rows.append({
            'map': map_id, 'seed': seed, 'condition': label,
            'method': METHOD_NAMES[label],
            'loop_id': loop.get('loop_id') if loop else '',
            'vertex': loop.get('loop_vertex') if loop else '',
            'event_seq': event.get('seq'), 'current_scan': current,
            'current_scan_time': scan_time if scan_time is not None else '',
            'chain_start': event['chain_start'], 'chain_end': event['chain_end'],
            'active_start': loop.get('actual_start_time') if loop else '',
            'active_end': loop.get('actual_end_time') if loop else '',
            'baseline_anchor_scan': target['anchor'] if target else '',
            'h_star_ids': json.dumps(target['ids']) if target else '',
            'matched_h_star_ids': json.dumps(overlap),
            'attribution_class': attribution, 'run_dir': str(run_dir.relative_to(ROOT)),
        })
    loop_rows = []
    for loop in loops:
        loop_id = int(loop['loop_id'])
        policy = loop.get('phase4b_execution_policy') or loop.get('execution_policy')
        generated = (loop.get('repair_plan') or {}).get('planned_length_m')
        loop_rows.append({
            'map': map_id, 'seed': seed, 'condition': label,
            'method': METHOD_NAMES[label], 'loop_id': loop_id,
            'loop_vertex': int(loop['loop_vertex']),
            'planned': True, 'executed': loop.get('actual_start_time') is not None,
            'execution_finished': bool(loop.get('execution_finished')),
            'target_attributable': loop_id in target_loop_ids,
            'temporally_associated': loop_id in temporal_loop_ids,
            'execution_policy': policy, 'active_loop_distance_m': loop.get('extra_distance'),
            'active_loop_time_s': loop.get('phase4b_active_loop_time_s'),
            'actual_generated_repair_length_m': generated,
            'actual_executed_repair_length_m': (
                loop.get('extra_distance') if policy in ('ALWAYS_TRACE', 'SELECTIVE_REPAIR') else 0.0
            ),
            'early_stopped': bool(loop.get('early_stopped')),
            'avoided_nominal_repair_path_length_lower_bound_m': loop.get(
                'early_stop_saved_remaining_polyline_m_lower_bound'
            ),
            'run_dir': str(run_dir.relative_to(ROOT)),
        })
    payload = {
        'frozen_rule': 'unique active interval AND accepted historical chain overlaps fixed 7-scan H*',
        'target_attributable_loop_ids': sorted(target_loop_ids),
        'temporally_associated_loop_ids': sorted(temporal_loop_ids),
        'passive_or_unrelated_events': sum(
            row['attribution_class'] == 'PASSIVE_OR_UNRELATED' for row in event_rows
        ),
        'events': event_rows,
    }
    output = AGGREGATE / 'per_run' / map_id / str(seed) / label / 'target_attribution.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
    return target_rows, event_rows, loop_rows, prior


def evaluate_map_run(map_id, seed, label, run_dir, prior, loops):
    yaml_path = run_dir / 'final_map.yaml'
    if not yaml_path.is_file():
        return None, []
    if map_id == 'map3':
        gt_yaml = ROOT / 'baseline/Graph-Based_SLAM-Aware_Exploration/world/map3/map3.yaml'
    else:
        gt_yaml = Path(MAPS[map_id]['gt_yaml'])
    targets = [{
        'target_id': 'loop_{}'.format(loop['loop_id']),
        'loop_id': loop['loop_id'], 'vertex': loop['loop_vertex'],
        'xy': list(prior.nodes[int(loop['loop_vertex'])]['position']),
    } for loop in loops]
    result = evaluate_maps_v2(
        load_map(gt_yaml), load_map(yaml_path), boundary_tolerance_m=0.20,
        local_targets=targets, local_radius_m=5.0,
    )
    detail = AGGREGATE / 'per_run' / map_id / str(seed) / label / 'mapping_metrics_v2.json'
    detail.parent.mkdir(parents=True, exist_ok=True)
    detail.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    global_row = {
        'map': map_id, 'seed': seed, 'condition': label, 'method': METHOD_NAMES[label],
        'boundary_f1': result['occupied_boundary_f1']['f1'],
        'symmetric_boundary_distance_mean_m': result['symmetric_boundary_distance']['mean_m'],
        'symmetric_boundary_distance_median_m': result['symmetric_boundary_distance']['median_m'],
        'symmetric_boundary_distance_p95_m': result['symmetric_boundary_distance']['p95_m'],
        'occupied_iou': result['occupied_iou']['value'],
        'observed_coverage_global': 1.0 - result['supporting']['estimated_unknown_ratio'],
        'detail': result_path(detail),
    }
    local_rows = [{
        'map': map_id, 'seed': seed, 'condition': label, 'method': METHOD_NAMES[label],
        'loop_id': local['loop_id'], 'loop_vertex': local['vertex'],
        'local_boundary_f1': local['boundary_f1']['f1'],
        'local_boundary_status': local['boundary_f1']['status'],
        'local_symmetric_boundary_distance_mean_m': local['symmetric_boundary_distance']['mean_m'],
        'local_distance_status': local['symmetric_boundary_distance']['status'],
        'local_observed_coverage': local['observed_coverage'],
    } for local in result['local_revisit']]
    return global_row, local_rows


def correction_rows(event_rows, loop_rows_by_key):
    rows = []
    for event in event_rows:
        if event['attribution_class'] != 'TARGET_ATTRIBUTABLE':
            continue
        key = (event['map'], int(event['seed']), event['condition'], int(event['loop_id']))
        base = {
            'map': event['map'], 'seed': event['seed'], 'condition': event['condition'],
            'method': event['method'], 'loop_id': event['loop_id'],
            'event_seq': event['event_seq'],
        }
        loop_record = loop_rows_by_key.get(key)
        if not loop_record:
            rows.append({**base, 'historical_pose_count': 0,
                         'mean_historical_pose_correction_m': None,
                         'median_historical_pose_correction_m': None,
                         'max_historical_pose_correction_m': None,
                         'status': 'N/A', 'reason': 'loop record unavailable'})
            continue
        loop = loop_record['raw_loop']
        run_dir = ROOT / event['run_dir']
        before_path = loop.get('snapshot_before')
        after_path = loop.get('snapshot_after')
        before = load_json(run_dir / before_path) if before_path else None
        after = load_json(run_dir / after_path) if after_path else None
        if not before or not after:
            rows.append({**base, 'historical_pose_count': 0,
                         'mean_historical_pose_correction_m': None,
                         'median_historical_pose_correction_m': None,
                         'max_historical_pose_correction_m': None,
                         'status': 'N/A', 'reason': 'before/after pose graph unavailable'})
            continue
        first = {int(k): v for k, v in before['pose_graph_nodes'].items()}
        second = {int(k): v for k, v in after['pose_graph_nodes'].items()}
        historical_max = int(event['chain_end'])
        common = sorted(set(first).intersection(second).intersection(range(historical_max + 1)))
        values = [math.hypot(second[i]['x'] - first[i]['x'], second[i]['y'] - first[i]['y']) for i in common]
        rows.append({
            **base, 'historical_pose_count': len(values),
            'mean_historical_pose_correction_m': float(np.mean(values)) if values else None,
            'median_historical_pose_correction_m': float(np.median(values)) if values else None,
            'max_historical_pose_correction_m': float(np.max(values)) if values else None,
            'status': 'AVAILABLE' if values else 'N/A',
            'reason': '' if values else 'no common historical pose IDs',
        })
    return rows


def finite(value):
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def mean_or_none(values):
    values = [float(v) for v in values if finite(v)]
    return float(np.mean(values)) if values else None


def plot_by_map(rows, key, ylabel, filename):
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), sharey=False)
    for ax, map_id in zip(axes, ('map3', 'map8', 'radish_mexico')):
        for index, label in enumerate('ABC'):
            values = [float(row[key]) for row in rows if row['map'] == map_id and row['condition'] == label and finite(row.get(key))]
            if values:
                jitter = np.linspace(-0.08, 0.08, len(values))
                ax.scatter(np.full(len(values), index) + jitter, values, color='black', s=18)
                ax.plot([index - 0.15, index + 0.15], [np.mean(values)] * 2, color='tab:blue', lw=3)
        ax.set_title(map_id)
        ax.set_xticks(range(3)); ax.set_xticklabels(['A', 'B', 'C'])
        ax.grid(axis='y', alpha=0.25)
    axes[0].set_ylabel(ylabel)
    fig.tight_layout(); fig.savefig(AGGREGATE / filename, dpi=180); plt.close(fig)


def paired_effects(run_rows):
    lookup = {(r['map'], int(r['seed']), r['condition']): r for r in run_rows}
    metrics = [
        'target_realization_rate', 'active_loop_distance_m', 'active_loop_time_s',
        'ape_rmse_m', 'rpe_translation_rmse_m', 'rpe_rotation_rmse_deg',
        'boundary_f1', 'symmetric_boundary_distance_mean_m',
        'local_boundary_f1_mean', 'local_symmetric_boundary_distance_mean_m',
        'local_observed_coverage_mean',
    ]
    rows = []
    for map_id in ('map3', 'map8', 'radish_mexico'):
        for seed in range(21001, 21006):
            for left, right, name in CONTRASTS:
                lhs, rhs = lookup.get((map_id, seed, left)), lookup.get((map_id, seed, right))
                for metric in metrics:
                    lv = lhs.get(metric) if lhs else None
                    rv = rhs.get(metric) if rhs else None
                    rows.append({
                        'map': map_id, 'seed': seed, 'contrast': name, 'metric': metric,
                        'left_value': lv, 'right_value': rv,
                        'difference': float(lv) - float(rv) if finite(lv) and finite(rv) else None,
                    })
    return rows


def summarize_paired_effects(rows):
    grouped = defaultdict(list)
    for row in rows:
        if finite(row.get('difference')):
            grouped[(row['contrast'], row['metric'])].append(float(row['difference']))
    summary = []
    for contrast in ('C-A', 'B-A', 'C-B'):
        metrics = sorted({row['metric'] for row in rows if row['contrast'] == contrast})
        for metric in metrics:
            values = grouped[(contrast, metric)]
            tolerance = 1e-12
            summary.append({
                'contrast': contrast, 'metric': metric, 'paired_block_n': len(values),
                'mean_difference': float(np.mean(values)) if values else None,
                'median_difference': float(np.median(values)) if values else None,
                'minimum_difference': float(np.min(values)) if values else None,
                'maximum_difference': float(np.max(values)) if values else None,
                'positive_count': sum(value > tolerance for value in values),
                'tie_count': sum(abs(value) <= tolerance for value in values),
                'negative_count': sum(value < -tolerance for value in values),
                'sign_note': 'raw left-minus-right difference; metric direction is not normalized',
            })
    return summary


def tsp_pairing_audit(inventory):
    by_block = defaultdict(dict)
    for map_id, seed, label, run_dir in inventory:
        record = load_json(run_dir / 'tsp_record.json')
        if not record:
            raise RuntimeError('missing TSP record: {}'.format(run_dir))
        by_block[(map_id, seed)][label] = record
    rows = []
    for (map_id, seed), records in sorted(by_block.items()):
        initial = {label: canonical_hash(record.get('initial_tsp_path'))
                   for label, record in records.items()}
        full = {label: canonical_hash(record.get('full_tsp_path'))
                for label, record in records.items()}
        initial_match = len(records) == 3 and len(set(initial.values())) == 1
        full_match = len(records) == 3 and len(set(full.values())) == 1
        rows.append({
            'map': map_id, 'seed': seed, 'conditions_present': ''.join(sorted(records)),
            'initial_tsp_A_hash': initial.get('A'), 'initial_tsp_B_hash': initial.get('B'),
            'initial_tsp_C_hash': initial.get('C'), 'initial_tsp_exact_match': initial_match,
            'full_tsp_A_hash': full.get('A'), 'full_tsp_B_hash': full.get('B'),
            'full_tsp_C_hash': full.get('C'), 'full_tsp_exact_match': full_match,
            'interpretation': ('initial-condition match; full-path divergence is retained as outcome'
                               if initial_match else 'BLOCKER: initial-condition mismatch'),
        })
        if len(records) == 3 and not initial_match:
            raise RuntimeError('BLOCKER: initial TSP mismatch for {} seed {}'.format(map_id, seed))
    return rows


def aggregate():
    AGGREGATE.mkdir(parents=True, exist_ok=True)
    inventory = run_inventory()
    target_rows, event_rows, loop_rows = [], [], []
    global_map_rows, local_rows = [], []
    raw_loop_lookup = {}
    run_meta = {}
    for map_id, seed, label, run_dir in inventory:
        targets, events, loops_flat, prior = attribute_run(map_id, seed, label, run_dir)
        target_rows.extend(targets); event_rows.extend(events); loop_rows.extend(loops_flat)
        raw_loops = load_json(run_dir / 'loops.json', {'loops': []})['loops']
        for loop in raw_loops:
            raw_loop_lookup[(map_id, seed, label, int(loop['loop_id']))] = {'raw_loop': loop}
        global_row, local = evaluate_map_run(map_id, seed, label, run_dir, prior, raw_loops)
        if global_row:
            global_map_rows.append(global_row)
        local_rows.extend(local)
        run_meta[(map_id, seed, label)] = {
            'run_dir': run_dir, 'summary': load_json(run_dir / 'run_summary.json', {}),
            'loops': loops_flat,
        }

    pose_rows = correction_rows(event_rows, raw_loop_lookup)
    local_by_run = defaultdict(list)
    for row in local_rows:
        local_by_run[(row['map'], int(row['seed']), row['condition'])].append(row)
    global_lookup = {(r['map'], int(r['seed']), r['condition']): r for r in global_map_rows}
    if WRITE_RUN_ARTIFACTS:
        for (map_id, seed, label), meta in run_meta.items():
            per_run_local = local_by_run[(map_id, seed, label)]
            (meta['run_dir'] / 'local_mapping_metrics.json').write_text(
                json.dumps({
                    'protocol': {'center': 'selected high-level loop vertex',
                                 'radius_m': 5.0, 'boundary_tolerance_m': 0.20},
                    'targets': per_run_local,
                }, indent=2, sort_keys=True) + '\n', encoding='utf-8'
            )
            per_run_pose = [
                row for row in pose_rows
                if row['map'] == map_id and int(row['seed']) == seed
                and row['condition'] == label
            ]
            (meta['run_dir'] / 'pose_correction.json').write_text(
                json.dumps({
                    'definition': 'historical pose displacement from loop before/after snapshots',
                    'material_correction_threshold': None,
                    'events': per_run_pose,
                }, indent=2, sort_keys=True) + '\n', encoding='utf-8'
            )
    run_rows = []
    for (map_id, seed, label), meta in sorted(run_meta.items()):
        summary, loops = meta['summary'], meta['loops']
        executed = [row for row in loops if row['executed']]
        target = [row for row in executed if row['target_attributable']]
        temporal_events = sum(row['attribution_class'] == 'TEMPORALLY_ASSOCIATED' for row in event_rows if row['map'] == map_id and int(row['seed']) == seed and row['condition'] == label)
        passive_events = sum(row['attribution_class'] == 'PASSIVE_OR_UNRELATED' for row in event_rows if row['map'] == map_id and int(row['seed']) == seed and row['condition'] == label)
        trajectory = summary.get('trajectory', {})
        exploration = summary.get('exploration', {})
        mapping = global_lookup.get((map_id, seed, label), {})
        local = local_by_run[(map_id, seed, label)]
        run_rows.append({
            'map': map_id, 'seed': seed, 'condition': label, 'method': METHOD_NAMES[label],
            'validity': summary.get('validity'), 'run_dir': str(meta['run_dir'].relative_to(ROOT)),
            'planned_active_loops': len(loops), 'executed_active_loops': len(executed),
            'target_attributable_loops': len(target),
            'target_realization_rate': float(len(target)) / len(executed) if executed else None,
            'temporally_associated_events': temporal_events,
            'passive_or_unrelated_events': passive_events,
            'active_loop_distance_m': sum(float(row['active_loop_distance_m'] or 0) for row in executed),
            'active_loop_time_s': sum(float(row['active_loop_time_s'] or 0) for row in executed),
            'total_exploration_distance_m': exploration.get('total_distance_m'),
            'total_exploration_sim_time_s': exploration.get('sim_time_s'),
            'total_exploration_wall_time_s': exploration.get('wall_time_s'),
            'wall_sim_ratio': exploration.get('wall_sim_ratio'),
            'repair_count': sum(row['execution_policy'] in ('ALWAYS_TRACE', 'SELECTIVE_REPAIR') for row in executed),
            'no_repair_count': sum(row['execution_policy'] == 'NO_REPAIR' for row in executed),
            'early_stop_count': sum(row['early_stopped'] for row in executed),
            'actual_generated_repair_length_m': sum(
                float(row['actual_generated_repair_length_m'] or 0) for row in executed
            ),
            'actual_executed_repair_length_m': sum(
                float(row['actual_executed_repair_length_m'] or 0) for row in executed
            ),
            'avoided_nominal_repair_path_length_lower_bound_m': sum(
                float(row['avoided_nominal_repair_path_length_lower_bound_m'] or 0)
                for row in executed
            ),
            'avoided_path_interpretation': 'geometric lower bound; not observed counterfactual travel',
            'ape_rmse_m': trajectory.get('ape_se2_translation_rmse_m'),
            'rpe_translation_rmse_m': trajectory.get('rpe_translation_1m_rmse_m'),
            'rpe_rotation_rmse_deg': trajectory.get('rpe_rotation_1m_rmse_deg'),
            'boundary_f1': mapping.get('boundary_f1'),
            'symmetric_boundary_distance_mean_m': mapping.get('symmetric_boundary_distance_mean_m'),
            'symmetric_boundary_distance_median_m': mapping.get('symmetric_boundary_distance_median_m'),
            'symmetric_boundary_distance_p95_m': mapping.get('symmetric_boundary_distance_p95_m'),
            'occupied_iou': mapping.get('occupied_iou'),
            'local_boundary_f1_mean': mean_or_none([r['local_boundary_f1'] for r in local]),
            'local_symmetric_boundary_distance_mean_m': mean_or_none([r['local_symmetric_boundary_distance_mean_m'] for r in local]),
            'local_observed_coverage_mean': mean_or_none([r['local_observed_coverage'] for r in local]),
        })

    sequences = []
    common_rows = []
    loops_by_block = defaultdict(dict)
    for row in loop_rows:
        loops_by_block[(row['map'], int(row['seed']))].setdefault(row['condition'], []).append(row)
    local_lookup = {(r['map'], int(r['seed']), r['condition'], int(r['loop_id'])): r for r in local_rows}
    for (map_id, seed), by_condition in sorted(loops_by_block.items()):
        seqs = {label: [r['loop_vertex'] for r in by_condition.get(label, [])] for label in 'ABC'}
        common = set(seqs['A']).intersection(seqs['B']).intersection(seqs['C'])
        tsp_hashes = {}
        for label in 'ABC':
            meta = run_meta.get((map_id, seed, label))
            tsp = load_json(meta['run_dir'] / 'tsp_record.json', {}) if meta else {}
            tsp_hashes[label] = {
                'initial': canonical_hash(tsp.get('initial_tsp_path')) if tsp else None,
                'full': canonical_hash(tsp.get('full_tsp_path')) if tsp else None,
            }
        sequences.append({
            'map': map_id, 'seed': seed,
            'A_sequence': json.dumps(seqs['A']), 'B_sequence': json.dumps(seqs['B']),
            'C_sequence': json.dumps(seqs['C']),
            'exact_sequence_match': len({tuple(v) for v in seqs.values()}) == 1,
            'common_target_vertices': json.dumps(sorted(common)),
            'common_target_count': len(common),
            'initial_tsp_A_hash': tsp_hashes['A']['initial'],
            'initial_tsp_B_hash': tsp_hashes['B']['initial'],
            'initial_tsp_C_hash': tsp_hashes['C']['initial'],
            'full_tsp_A_hash': tsp_hashes['A']['full'],
            'full_tsp_B_hash': tsp_hashes['B']['full'],
            'full_tsp_C_hash': tsp_hashes['C']['full'],
        })
        for vertex in sorted(common):
            for label in 'ABC':
                for row in by_condition[label]:
                    if row['loop_vertex'] == vertex:
                        local = local_lookup.get((map_id, seed, label, row['loop_id']), {})
                        common_rows.append({
                            **{key: row[key] for key in ('map', 'seed', 'condition', 'method', 'loop_id', 'loop_vertex', 'target_attributable', 'active_loop_distance_m', 'active_loop_time_s')},
                            'local_boundary_f1': local.get('local_boundary_f1'),
                            'local_symmetric_boundary_distance_mean_m': local.get('local_symmetric_boundary_distance_mean_m'),
                            'local_observed_coverage': local.get('local_observed_coverage'),
                        })

    tsp_rows = tsp_pairing_audit(inventory)
    paired = paired_effects(run_rows)
    paired_summary = summarize_paired_effects(paired)
    write_csv(AGGREGATE / 'run_table.csv', run_rows)
    write_csv(AGGREGATE / 'loop_table.csv', loop_rows)
    write_csv(AGGREGATE / 'target_attribution.csv', event_rows)
    write_csv(AGGREGATE / 'target_sets.csv', target_rows)
    write_csv(AGGREGATE / 'selection_sequence_comparison.csv', sequences)
    write_csv(AGGREGATE / 'common_target_loop_table.csv', common_rows)
    write_csv(AGGREGATE / 'execution_cost.csv', run_rows)
    write_csv(AGGREGATE / 'trajectory_accuracy.csv', run_rows)
    write_csv(AGGREGATE / 'pose_correction.csv', pose_rows, POSE_FIELDS)
    write_csv(AGGREGATE / 'global_mapping_quality.csv', global_map_rows)
    write_csv(AGGREGATE / 'local_revisit_quality.csv', local_rows)
    write_csv(AGGREGATE / 'map_seed_paired_effects.csv', paired)
    write_csv(AGGREGATE / 'map_seed_paired_effect_summary.csv', paired_summary)
    write_csv(AGGREGATE / 'tsp_pairing_audit.csv', tsp_rows)
    acceptance = []
    for map_id in ('map3', 'map8', 'radish_mexico'):
        for label in 'ABC':
            subset = [r for r in run_rows if r['map'] == map_id and r['condition'] == label]
            numerator = sum(int(r['target_attributable_loops']) for r in subset)
            denominator = sum(int(r['executed_active_loops']) for r in subset)
            acceptance.append({
                'map': map_id, 'condition': label, 'method': METHOD_NAMES[label],
                'target_attributable_numerator': numerator,
                'executed_loop_denominator': denominator,
                'descriptive_pooled_rate': float(numerator) / denominator if denominator else None,
                'ci_note': 'descriptive only; does not account for within-seed dependence',
            })
    write_csv(AGGREGATE / 'acceptance_by_map_method.csv', acceptance)

    plot_by_map(run_rows, 'target_realization_rate', 'TARGET_ATTRIBUTABLE / executed', 'target_realization_by_map.png')
    plot_by_map(run_rows, 'active_loop_distance_m', 'Active-loop distance (m)', 'active_loop_distance_by_map.png')
    plot_by_map(run_rows, 'active_loop_time_s', 'Active-loop sim time (s)', 'active_loop_time_by_map.png')
    plot_by_map(run_rows, 'ape_rmse_m', 'APE RMSE (m)', 'ape_by_map.png')
    plot_by_map(run_rows, 'rpe_translation_rmse_m', 'RPE translation RMSE (m)', 'rpe_translation_by_map.png')
    plot_by_map(run_rows, 'rpe_rotation_rmse_deg', 'RPE rotation RMSE (deg)', 'rpe_rotation_by_map.png')
    plot_by_map(run_rows, 'local_boundary_f1_mean', 'Mean local boundary F1', 'local_boundary_f1_by_map.png')
    plot_by_map(run_rows, 'local_symmetric_boundary_distance_mean_m', 'Mean local boundary distance (m)', 'local_boundary_distance_by_map.png')
    plot_by_map(pose_rows, 'mean_historical_pose_correction_m', 'Historical pose correction (m)', 'pose_correction_by_method.png')
    fig, ax = plt.subplots(figsize=(6.5, 5))
    for label, color in zip('ABC', ('tab:gray', 'tab:orange', 'tab:blue')):
        subset = [r for r in run_rows if r['condition'] == label and finite(r['active_loop_distance_m']) and finite(r['target_realization_rate'])]
        ax.scatter([r['active_loop_distance_m'] for r in subset], [r['target_realization_rate'] for r in subset], label=METHOD_NAMES[label], color=color)
    ax.set_xlabel('Active-loop distance (m)'); ax.set_ylabel('TARGET_ATTRIBUTABLE realization rate')
    ax.grid(alpha=0.25); ax.legend(); fig.tight_layout()
    fig.savefig(AGGREGATE / 'realization_cost_pareto.png', dpi=180); plt.close(fig)
    summary = {
        'status': 'COMPLETE' if len(run_rows) == 45 else 'INCOMPLETE',
        'formal_method_runs': len(run_rows), 'expected_method_runs': 45,
        'primary_unit': 'map-seed', 'paired_block_count_expected': 15,
        'individual_loops_inferential_samples': False,
        'acceptance_by_map_method': acceptance,
        'selection_exact_match_blocks': sum(r['exact_sequence_match'] for r in sequences),
        'selection_blocks': len(sequences),
        'target_event_count': sum(r['attribution_class'] == 'TARGET_ATTRIBUTABLE' for r in event_rows),
        'pose_correction_available_events': sum(r['status'] == 'AVAILABLE' for r in pose_rows),
        'initial_tsp_exact_match_blocks': sum(r['initial_tsp_exact_match'] for r in tsp_rows),
        'tsp_blocks_audited': len(tsp_rows),
        'paired_effect_summary': paired_summary,
        'p_values_reported': False,
    }
    (AGGREGATE / 'phase4c_summary.json').write_text(
        json.dumps(summary, indent=2, sort_keys=True) + '\n'
    )
    return summary


if __name__ == '__main__':
    print(json.dumps(aggregate(), indent=2, sort_keys=True))
