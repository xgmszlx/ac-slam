#!/usr/bin/python3
"""Post-confirmatory exploratory heterogeneity audit for frozen v14 data.

The script is read-only with respect to the v14 confirmatory result root.  It
does not launch ROS, Stage, Karto, a planner, or a new data collection.  Its
outputs live under a separate heterogeneity result root.
"""

import argparse
import csv
import hashlib
import json
import math
import subprocess
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

import edge_analytics
from common_prefix_analysis import edges_from_graph, nodes_from_graph
from controlled_branch_suite import atomic_json
from v14_confirmatory_analysis import target_information


ROOT = Path(__file__).resolve().parents[2]
V14_ROOT = ROOT / 'results/realizability_pilot/p1_v14_confirmatory_20260928'
RESULT_ROOT = ROOT / 'results/realizability_pilot/p1_v14_heterogeneity_20260928'
IMMUTABLE_MANIFEST = RESULT_ROOT / 'provenance/v14_immutable_manifest.json'
ARMS = ('A1_DWELL', 'A3_MIN_TRIGGER', 'A2_SWEEP90')
TARGETS = ('target_A', 'target_B')
HISTORICAL_LABELS = {'E_T_target', 'E_N_nontarget_history'}
AUDIT_LABEL = 'EXPLORATORY_HETEROGENEITY_ONLY'


def load_json(path):
    return json.loads(Path(path).read_text())


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv(path):
    with open(path, newline='') as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    rows = list(rows)
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='') as stream:
        if fields:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)


def wrap_angle(value):
    return math.atan2(math.sin(value), math.cos(value))


def verify_v14_immutable(manifest_path=IMMUTABLE_MANIFEST):
    manifest = load_json(manifest_path)
    failures = []
    for relative, expected in manifest['critical_sha256'].items():
        path = V14_ROOT / relative
        actual = sha256(path) if path.is_file() else None
        if actual != expected:
            failures.append({'path': relative, 'expected': expected,
                             'actual': actual})
    relative_root = V14_ROOT.relative_to(ROOT).as_posix()
    committed_tree_oid = subprocess.check_output(
        ['git', 'rev-parse', 'HEAD:' + relative_root],
        cwd=ROOT, text=True).strip()
    worktree_status = subprocess.check_output(
        ['git', 'status', '--porcelain', '--untracked-files=all', '--',
         relative_root], cwd=ROOT, text=True).strip()
    if committed_tree_oid != manifest['v14_git_tree_oid']:
        failures.append({'path': relative_root, 'expected':
                         manifest['v14_git_tree_oid'],
                         'actual': committed_tree_oid})
    if worktree_status:
        failures.append({'path': relative_root, 'expected':
                         'clean against HEAD', 'actual': worktree_status})
    return {'passed': not failures, 'checked': len(
        manifest['critical_sha256']), 'failures': failures,
        'expected_v14_git_tree_oid': manifest['v14_git_tree_oid'],
        'actual_v14_git_tree_oid': committed_tree_oid,
        'v14_worktree_clean': not bool(worktree_status)}


def _node_adjacency(nodes, edges):
    adjacency = {}
    for edge in edges:
        left, right = edge['start'], edge['end']
        distance = math.hypot(nodes[right]['x'] - nodes[left]['x'],
                              nodes[right]['y'] - nodes[left]['y'])
        adjacency.setdefault(left, []).append((right, distance))
        adjacency.setdefault(right, []).append((left, distance))
    return adjacency


def _graph_components(node_ids, edges):
    parent = {node: node for node in node_ids}

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for edge in edges:
        left, right = find(edge['start']), find(edge['end'])
        if left != right:
            parent[right] = left
    return len({find(node) for node in node_ids}) if node_ids else 0


def _target_spatial_metrics(segment):
    points = np.asarray([[row['x'], row['y']] for row in segment], dtype=float)
    arc = sum(float(np.linalg.norm(right - left))
              for left, right in zip(points, points[1:]))
    pairwise = [float(np.linalg.norm(points[right] - points[left]))
                for left in range(len(points))
                for right in range(left + 1, len(points))]
    center = points.mean(axis=0)
    rms = math.sqrt(float(np.mean(np.sum((points - center) ** 2, axis=1))))
    return arc, max(pairwise), rms


def _pretreatment_contract():
    true_fields = [
        'block_id', 'target_label', 'target_B_indicator', 'seed',
        'target_anchor_state', 'five_target_state_ids', 'pre_nodes',
        'pre_edges', 'pre_cycle_rank', 'pre_connected_components',
        'pre_edge_node_ratio', 'target_degree_min', 'target_degree_mean',
        'target_degree_max', 'target_internal_pre_edges',
        'target_incident_pre_edges', 'J_pre', 'pre_target_trace',
        'pre_target_logdet', 'pre_cov_eigen_min', 'pre_cov_eigen_median',
        'pre_cov_eigen_max', 'target_segment_arc_length_m',
        'target_spatial_spread_max_m', 'target_spatial_spread_rms_m',
        'current_to_anchor_euclidean_m', 'current_to_anchor_geodesic_m',
        'current_to_anchor_hops', 'anchor_yaw_map_rad',
        'anchor_yaw_world_rad', 'arrival_bearing_world_rad',
        'bearing_minus_anchor_yaw_rad', 'planned_arrival_rotation_A3_rad',
        'local_graph_density',
    ]
    false_fields = ['local_scan_geometry_descriptor',
                    'local_occupancy_geometry_descriptor']
    return {field: True for field in true_fields} | {
        field: False for field in false_fields}


def extract_pretreatment_features(block_id, seed, target_label, block_dir):
    """Use graph_pre/frozen target/planned geometry only."""
    graph_paths = [block_dir / arm / 'attempt_01/graph_pre.json'
                   for arm in ('A1_DWELL', 'A3_MIN_TRIGGER', 'A2_SWEEP90')]
    graph_hashes = {sha256(path) for path in graph_paths}
    if len(graph_hashes) != 1:
        raise RuntimeError('{} pre-graph differs by arm'.format(block_id))
    graph = load_json(graph_paths[0])
    nodes = nodes_from_graph(graph)
    edges = edges_from_graph(graph, nodes)
    frozen = load_json(V14_ROOT / 'collection/captures' / target_label /
                       block_id / 'frozen_target.json')
    specs = load_json(V14_ROOT / 'collection/captures' / target_label /
                      block_id / 'action_specs.json')
    target_ids = [int(value) for value in frozen['historical_scan_ids']]
    target_set = set(target_ids)
    degrees = {state: 0 for state in target_ids}
    incident = internal = 0
    for edge in edges:
        pair = {edge['start'], edge['end']}
        touched = pair & target_set
        if touched:
            incident += 1
            for state in touched:
                degrees[state] += 1
        if edge['start'] in target_set and edge['end'] in target_set:
            internal += 1
    components = _graph_components(sorted(nodes), edges)
    posterior = target_information(nodes, edges, target_ids)
    eigenvalues = [float(value) for value in posterior['eigenvalues']]
    segment = frozen['segment_nodes']
    arc, spread_max, spread_rms = _target_spatial_metrics(segment)
    current = max(nodes)
    anchor = int(frozen['anchor_scan']['id'])
    adjacency = _node_adjacency(nodes, edges)
    euclidean = math.hypot(nodes[current]['x'] - nodes[anchor]['x'],
                           nodes[current]['y'] - nodes[anchor]['y'])
    geodesic = edge_analytics.dijkstra(adjacency, current, anchor)
    hops = edge_analytics.hop_count(adjacency, current, anchor)
    a3 = specs['actions']['A3_MIN_TRIGGER']
    core = int(a3['core_action_start_index'])
    before = a3['action_waypoints'][core - 1]
    arrival = a3['action_waypoints'][core]
    bearing = math.atan2(arrival[1] - before[1], arrival[0] - before[0])
    planned_rotation = abs(wrap_angle(arrival[2] - before[2]))
    row = {
        'block_id': block_id, 'target_label': target_label,
        'target_B_indicator': int(target_label == 'target_B'),
        'seed': int(seed), 'target_anchor_state': anchor,
        'five_target_state_ids': json.dumps(target_ids),
        'pre_nodes': len(nodes), 'pre_edges': len(edges),
        'pre_cycle_rank': len(edges) - len(nodes) + components,
        'pre_connected_components': components,
        'pre_edge_node_ratio': len(edges) / float(len(nodes)),
        'target_degree_min': min(degrees.values()),
        'target_degree_mean': float(np.mean(list(degrees.values()))),
        'target_degree_max': max(degrees.values()),
        'target_internal_pre_edges': internal,
        'target_incident_pre_edges': incident,
        'J_pre': posterior['J_T'],
        'pre_target_trace': posterior['trace'],
        'pre_target_logdet': posterior['logdet'],
        'pre_cov_eigen_min': min(eigenvalues),
        'pre_cov_eigen_median': float(np.median(eigenvalues)),
        'pre_cov_eigen_max': max(eigenvalues),
        'target_segment_arc_length_m': arc,
        'target_spatial_spread_max_m': spread_max,
        'target_spatial_spread_rms_m': spread_rms,
        'current_to_anchor_euclidean_m': euclidean,
        'current_to_anchor_geodesic_m': geodesic,
        'current_to_anchor_hops': hops,
        'anchor_yaw_map_rad': float(frozen['anchor_scan']['theta']),
        'anchor_yaw_world_rad': float(arrival[2]),
        'arrival_bearing_world_rad': bearing,
        'bearing_minus_anchor_yaw_rad': wrap_angle(bearing - arrival[2]),
        'planned_arrival_rotation_A3_rad': planned_rotation,
        'local_graph_density': incident / float(len(nodes)),
        'local_scan_geometry_descriptor': None,
        'local_occupancy_geometry_descriptor': None,
        'source_graph_pre_sha256': next(iter(graph_hashes)),
        'audit_label': AUDIT_LABEL,
    }
    contract = _pretreatment_contract()
    for field, available in contract.items():
        row[field + '__PRETREATMENT_AVAILABLE'] = available
    return row, contract


def load_gt(path):
    rows = []
    with open(path) as stream:
        for line in stream:
            if line.strip():
                rows.append([float(value) for value in line.split()])
    return rows


def path_length(rows):
    return sum(math.hypot(right[1] - left[1], right[2] - left[2])
               for left, right in zip(rows, rows[1:]))


def yaw_excursion(rows):
    return sum(abs(wrap_angle(right[3] - left[3]))
               for left, right in zip(rows, rows[1:]))


def _angular_rates(rows):
    rates = [abs(wrap_angle(right[3] - left[3])) /
             (right[0] - left[0])
             for left, right in zip(rows, rows[1:])
             if right[0] > left[0]]
    return (float(np.mean(rates)) if rates else None,
            float(np.median(rates)) if rates else None,
            max(rates) if rates else None)


def arm_dose(capture_dir, specs, arm):
    result = load_json(capture_dir / 'capture_result.json')
    gt = load_gt(capture_dir / 'probe_gt_trajectory.txt')
    start = float(result['treatment_start_time'])
    completion = float(result['maneuver_completion_time'])
    end = float(result['treatment_end_timestamp'])
    treatment = [row for row in gt if start <= row[0] <= end]
    moving = [row for row in gt if start <= row[0] <= completion]
    if len(treatment) < 2 or len(moving) < 2:
        raise RuntimeError('{} lacks GT samples for dose extraction'.format(arm))
    spec = specs['actions'][arm]
    core = int(spec['core_action_start_index'])
    planned = spec['action_waypoints'][core - 1:]
    planned_yaw = sum(abs(wrap_angle(right[2] - left[2]))
                      for left, right in zip(planned, planned[1:]))
    post_arrival = spec['action_waypoints'][core:]
    planned_post_arrival_yaw = sum(
        abs(wrap_angle(right[2] - left[2]))
        for left, right in zip(post_arrival, post_arrival[1:]))
    moves = {row['label']: row for row in result['moves']}
    arrival = moves['probe_arrival']
    initial_rotation = abs(wrap_angle(
        float(arrival['target'][2]) - float(arrival['before'][2])))
    mean_rate, median_rate, max_rate = _angular_rates(moving)
    return {
        'yaw_excursion_full_treatment_rad': yaw_excursion(treatment),
        'yaw_excursion_moving_rad': yaw_excursion(moving),
        'planned_cumulative_angular_path_rad': planned_yaw,
        'planned_post_arrival_angular_path_rad': planned_post_arrival_yaw,
        'actual_cumulative_angular_path_rad': yaw_excursion(moving),
        'completion_scan_index': int(result['completion_scan_index']),
        'completion_time_from_treatment_s': completion - start,
        'moving_scan_count': int(result['completion_scan_index']),
        'post_maneuver_static_scan_count': int(result['static_tail_scan_count']),
        'treatment_distance_m': path_length(treatment),
        'moving_distance_m': path_length(moving),
        'final_heading_rad': float(moving[-1][3]),
        'initial_arrival_rotation_demand_rad': initial_rotation,
        'mean_abs_angular_velocity_rad_s': mean_rate,
        'median_abs_angular_velocity_rad_s': median_rate,
        'max_abs_angular_velocity_rad_s': max_rate,
        'result_reported_yaw_excursion_rad': float(
            result['treatment_yaw_excursion_rad']),
        'raw_gt_recomputed': True,
    }


def extract_action_dose(block_id, target_label):
    base = V14_ROOT / 'collection/captures' / target_label / block_id
    specs = load_json(base / 'action_specs.json')
    doses = {}
    for arm in ('A3_MIN_TRIGGER', 'A2_SWEEP90'):
        doses[arm] = arm_dose(base / arm / 'attempt_01', specs, arm)
    row = {'block_id': block_id, 'target_label': target_label,
           'audit_label': AUDIT_LABEL}
    aliases = {'A3_MIN_TRIGGER': 'A3', 'A2_SWEEP90': 'A2'}
    for arm, values in doses.items():
        for field, value in values.items():
            row['{}_{}'.format(aliases[arm], field)] = value
    difference_fields = [
        'yaw_excursion_full_treatment_rad', 'yaw_excursion_moving_rad',
        'planned_cumulative_angular_path_rad',
        'planned_post_arrival_angular_path_rad',
        'actual_cumulative_angular_path_rad', 'completion_scan_index',
        'completion_time_from_treatment_s', 'moving_scan_count',
        'post_maneuver_static_scan_count', 'treatment_distance_m',
        'moving_distance_m', 'initial_arrival_rotation_demand_rad',
        'mean_abs_angular_velocity_rad_s',
        'median_abs_angular_velocity_rad_s',
        'max_abs_angular_velocity_rad_s']
    for field in difference_fields:
        left, right = doses['A2_SWEEP90'][field], doses['A3_MIN_TRIGGER'][field]
        row['Delta_' + field] = (None if left is None or right is None
                                 else left - right)
    row['A2_minus_A3_final_heading_rad'] = wrap_angle(
        doses['A2_SWEEP90']['final_heading_rad'] -
        doses['A3_MIN_TRIGGER']['final_heading_rad'])
    return row


def extract_realized_differences(metrics):
    by_block = defaultdict(dict)
    for row in metrics:
        by_block[row['block_id']][row['arm']] = row
    fields = {
        'accepted_keyscans': 'accepted_keyscans',
        'total_factors': 'total_new_factors',
        'local_factors': 'local_factors', 'E_T': 'E_T', 'E_N': 'E_N',
        'PREVIOUS_SCAN': 'PREVIOUS_SCAN',
        'RUNNING_SCAN_CHAIN': 'RUNNING_SCAN_CHAIN',
        'NEAR_CHAIN': 'NEAR_CHAIN',
        'TRY_CLOSE_LOOP': 'TRY_CLOSE_LOOP',
    }
    output = []
    for block_id, arms in sorted(by_block.items()):
        a2, a3 = arms['A2_SWEEP90'], arms['A3_MIN_TRIGGER']
        row = {'block_id': block_id, 'target_label': a2['target'],
               'audit_label': AUDIT_LABEL}
        for label, field in fields.items():
            row['A2_' + label] = int(float(a2[field]))
            row['A3_' + label] = int(float(a3[field]))
            row['Delta_' + label] = int(float(a2[field]) - float(a3[field]))
        row['A2_historical_factors'] = row['A2_E_T'] + row['A2_E_N']
        row['A3_historical_factors'] = row['A3_E_T'] + row['A3_E_N']
        row['Delta_historical_factors'] = (
            row['A2_historical_factors'] - row['A3_historical_factors'])
        output.append(row)
    return output


def canonical_endpoint(row):
    return tuple(sorted((int(row['source_state_id']),
                         int(row['target_state_id']))))


def endpoint_set_summary(a2_rows, a3_rows):
    a2 = {canonical_endpoint(row) for row in a2_rows}
    a3 = {canonical_endpoint(row) for row in a3_rows}
    intersection = a2 & a3
    union = a2 | a3
    a2_only, a3_only = a2 - a3, a3 - a2
    nonlocal_a2 = sum(_int_or_none(row.get('hops_at_insertion')) not in
                      (None, 0, 1) for row in a2_rows)
    nonlocal_a3 = sum(_int_or_none(row.get('hops_at_insertion')) not in
                      (None, 0, 1) for row in a3_rows)
    return {
        'A2_endpoint_pairs': json.dumps(sorted(a2)),
        'A3_endpoint_pairs': json.dumps(sorted(a3)),
        'intersection_pairs': json.dumps(sorted(intersection)),
        'A2_only_pairs': json.dumps(sorted(a2_only)),
        'A3_only_pairs': json.dumps(sorted(a3_only)),
        'A2_endpoint_count': len(a2), 'A3_endpoint_count': len(a3),
        'retained_historical_endpoint_count': len(intersection),
        'newly_realized_historical_endpoint_count': len(a2_only),
        'lost_historical_endpoint_count': len(a3_only),
        'historical_endpoint_novelty': len(a2_only),
        'historical_endpoint_loss': len(a3_only),
        'endpoint_jaccard_similarity': (
            len(intersection) / float(len(union)) if union else 1.0),
        'A2_nonlocal_historical_factor_count': nonlocal_a2,
        'A3_nonlocal_historical_factor_count': nonlocal_a3,
        'nonlocal_historical_gain': nonlocal_a2 - nonlocal_a3,
    }


def _int_or_none(value):
    if value in (None, '', 'None', 'null'):
        return None
    return int(float(value))


def endpoint_analysis(constraints):
    historical = [row for row in constraints
                  if row['attribution'] in HISTORICAL_LABELS]
    grouped = defaultdict(list)
    for row in historical:
        grouped[(row['block_id'], row['arm'])].append(row)
    comparisons, details = [], []
    for block_id in sorted({row['block_id'] for row in historical}):
        a2 = grouped[(block_id, 'A2_SWEEP90')]
        a3 = grouped[(block_id, 'A3_MIN_TRIGGER')]
        summary = endpoint_set_summary(a2, a3)
        target = (a2 or a3)[0]['target']
        comparisons.append({'block_id': block_id, 'target_label': target,
                            **summary, 'audit_label': AUDIT_LABEL,
                            'causal_effect_claimed': False})
        for arm, rows in (('A2_SWEEP90', a2), ('A3_MIN_TRIGGER', a3)):
            graph_path = (V14_ROOT / 'collection/replays' / target / block_id /
                          arm / 'attempt_01/graph_final.json')
            graph_edges = {int(edge['index']): edge
                           for edge in load_json(graph_path)['edges']}
            for row in rows:
                edge_index = int(row['edge_index'])
                covariance = graph_edges[edge_index]['covariance_3x3']
                details.append({
                    'block_id': block_id, 'target_label': target, 'arm': arm,
                    'canonical_endpoint_pair': json.dumps(canonical_endpoint(row)),
                    'attribution': row['attribution'],
                    'source_state_id': row['source_state_id'],
                    'target_state_id': row['target_state_id'],
                    'constraint_family': row['constraint_family'],
                    'creation_provenance': row['creation_provenance'],
                    'creation_stage': row['creation_stage'],
                    'matcher_type': row['matcher_type'],
                    'match_response': row['match_response'],
                    'match_threshold': row['match_threshold'],
                    'measurement_dx': row['measurement_dx'],
                    'measurement_dy': row['measurement_dy'],
                    'measurement_dtheta': row['measurement_dtheta'],
                    'covariance_3x3': json.dumps(covariance),
                    'covariance_eigenvalues': row['covariance_eigenvalues'],
                    'information_eigenvalues': row['information_eigenvalues'],
                    'constraint_d_opt': row['constraint_d_opt'],
                    'geodesic_at_insertion_m': row['geodesic_at_insertion_m'],
                    'hops_at_insertion': row['hops_at_insertion'],
                    'cycle_size_edges': row['cycle_size_edges'],
                    'audit_label': AUDIT_LABEL,
                })
    return comparisons, details


def _float(value):
    if value in (None, '', 'None', 'null'):
        return float('nan')
    return float(value)


def correlation_matrix(rows, fields):
    output = []
    for left in fields:
        for right in fields:
            x = np.asarray([_float(row.get(left)) for row in rows], dtype=float)
            y = np.asarray([_float(row.get(right)) for row in rows], dtype=float)
            valid = np.isfinite(x) & np.isfinite(y)
            xv, yv = x[valid], y[valid]
            if len(xv) < 3 or len(set(xv)) < 2 or len(set(yv)) < 2:
                pearson = spearman = None
            else:
                pearson = float(stats.pearsonr(xv, yv).statistic)
                spearman = float(stats.spearmanr(xv, yv).statistic)
            output.append({'feature_x': left, 'feature_y': right,
                           'n': int(valid.sum()), 'pearson_r': pearson,
                           'spearman_rho': spearman,
                           'audit_label': AUDIT_LABEL})
    return output


def target_confounding(rows, fields, rho_threshold=0.75):
    """Flag features whose A/B ranges separate and ranks follow target."""
    output = []
    target = np.asarray([int(row['target_B_indicator']) for row in rows])
    for field in fields:
        values = np.asarray([_float(row.get(field)) for row in rows], dtype=float)
        valid = np.isfinite(values)
        a = values[(target == 0) & valid]
        b = values[(target == 1) & valid]
        rho = (float(stats.spearmanr(target[valid], values[valid]).statistic)
               if valid.sum() >= 3 and len(set(values[valid])) > 1 else None)
        separated = bool(len(a) and len(b) and
                         (max(a) < min(b) or max(b) < min(a)))
        confounded = bool(separated and rho is not None and
                          abs(rho) >= rho_threshold)
        output.append({
            'feature': field, 'target_spearman_rho': rho,
            'target_A_min': min(a) if len(a) else None,
            'target_A_max': max(a) if len(a) else None,
            'target_B_min': min(b) if len(b) else None,
            'target_B_max': max(b) if len(b) else None,
            'target_ranges_nonoverlapping': separated,
            'status': ('TARGET_FEATURE_CONFOUNDING_NOT_IDENTIFIABLE'
                       if confounded else 'TARGET_FEATURE_SEPARATION_NOT_COMPLETE'),
            'rho_threshold': rho_threshold, 'audit_label': AUDIT_LABEL,
        })
    return output


def leave_one_out(rows, predictors):
    output = []
    for predictor in predictors:
        for omitted in rows:
            subset = [row for row in rows
                      if row['block_id'] != omitted['block_id']]
            x = np.asarray([_float(row[predictor]) for row in subset])
            y = np.asarray([_float(row['D_sweep']) for row in subset])
            rho = (float(stats.spearmanr(x, y).statistic)
                   if len(set(x)) > 1 else None)
            output.append({'predictor': predictor,
                           'omitted_block': omitted['block_id'],
                           'spearman_rho': rho, 'n': len(subset),
                           'audit_label': AUDIT_LABEL})
    return output


def sign(value):
    return 1 if value > 0 else -1 if value < 0 else 0


def sign_alignment(rows, fields):
    output = {}
    for field in fields:
        evaluable = [row for row in rows
                     if sign(float(row[field])) and sign(float(row['D_sweep']))]
        matches = sum(sign(float(row[field])) == sign(float(row['D_sweep']))
                      for row in evaluable)
        output[field] = {
            'aligned': matches, 'evaluable': len(evaluable),
            'exact_all_aligned_probability_one_sided': (
                0.5 ** len(evaluable) if matches == len(evaluable) else None),
        }
    return output


def trigger_realization(metrics, primary):
    by_block = defaultdict(dict)
    for row in metrics:
        by_block[row['block_id']][row['arm']] = row
    primary_by_block = {row['block_id']: row for row in primary}
    output = []
    fields = ['accepted_keyscans', 'total_new_factors', 'local_factors',
              'E_T', 'E_N', 'PREVIOUS_SCAN', 'RUNNING_SCAN_CHAIN',
              'NEAR_CHAIN', 'TRY_CLOSE_LOOP']
    for block_id, arms in sorted(by_block.items()):
        a3, a1 = arms['A3_MIN_TRIGGER'], arms['A1_DWELL']
        row = {'block_id': block_id, 'target_label': a3['target'],
               'D_trigger': float(primary_by_block[block_id]['D_trigger']),
               'audit_label': AUDIT_LABEL}
        for field in fields:
            row['Delta_' + field] = int(float(a3[field]) - float(a1[field]))
        row['Delta_historical_factors'] = row['Delta_E_T'] + row['Delta_E_N']
        output.append(row)
    return output


def _legacy_context_rows(protocol, estimand, exposure, contrast_path,
                         metrics_path, contrast_name='D_sweep'):
    if not Path(contrast_path).is_file() or not Path(metrics_path).is_file():
        return []
    contrasts = read_csv(contrast_path)
    metrics = read_csv(metrics_path)
    by_block = defaultdict(dict)
    for row in metrics:
        by_block[row['block_id']][row['arm']] = row
    output = []
    if 'contrast' in contrasts[0]:
        selected = [row for row in contrasts if row['contrast'] == contrast_name]
    else:
        selected = contrasts
    for contrast in selected:
        block = contrast['block_id']
        arms = by_block.get(block, {})
        if not all(arm in arms for arm in ('A2_SWEEP90', 'A3_MIN_TRIGGER')):
            continue
        a2, a3 = arms['A2_SWEEP90'], arms['A3_MIN_TRIGGER']
        difference = contrast.get('difference', contrast.get('D_sweep'))
        a2_yaw, a3_yaw = (_float(a2.get('yaw_excursion_rad')),
                          _float(a3.get('yaw_excursion_rad')))
        yaw_difference = (float(a2_yaw - a3_yaw)
                          if np.isfinite(a2_yaw) and np.isfinite(a3_yaw)
                          else None)
        output.append({
            'protocol': protocol, 'estimand_version': estimand,
            'exposure_rule': exposure, 'target': contrast.get(
                'target', a2.get('target')), 'seed_or_history': a2.get(
                    'seed', block), 'block_id': block,
            'source_contrast_name': contrast.get('contrast', 'D_sweep'),
            'D_sweep_context_field': _float(difference),
            'Delta_yaw_excursion_rad': yaw_difference,
            'Delta_accepted_keyscans': int(float(a2['accepted_keyscan_count']) -
                                           float(a3['accepted_keyscan_count'])),
            'Delta_historical_factors': int(
                float(a2['E_T_count']) + float(a2['E_N_count']) -
                float(a3['E_T_count']) - float(a3['E_N_count'])),
            'comparability_to_v14': 'NOT_DIRECTLY_COMPARABLE',
            'pooled_with_v14': False, 'audit_label': AUDIT_LABEL,
        })
    return output


def cross_protocol_context():
    rows = []
    v13 = ROOT / 'results/realizability_pilot/p1_confirmatory_v13c_20260921'
    rows += _legacy_context_rows(
        'v13-C', 'block-local J_T D_sweep', 'variable raw capture budget',
        v13 / 'analysis/paired_contrasts.csv',
        v13 / 'analysis/branch_metrics.csv')
    post = ROOT / 'results/realizability_pilot/p1_v13c_posthoc_targetB_20260921'
    rows += _legacy_context_rows(
        'v13-C-posthoc-B-FULL', 'block-local J_T D_sweep',
        'FULL variable raw capture replay',
        post / 'analysis/FULL/paired_contrasts.csv',
        post / 'analysis/FULL/branch_metrics.csv')
    v12 = ROOT / 'results/realizability_pilot/p1_confirmatory_v12_20260917'
    rows += _legacy_context_rows(
        'v12', 'D_view predecessor estimand', 'variable raw capture budget',
        v12 / 'analysis/paired_contrasts.csv',
        v12 / 'analysis/branch_metrics.csv', contrast_name='D_view')
    rows.append({
        'protocol': 'v12b', 'estimand_version': 'no complete scientific sample',
        'exposure_rule': 'target-specific budget attempt', 'target': None,
        'seed_or_history': None, 'block_id': None,
        'source_contrast_name': None, 'D_sweep_context_field': None,
        'Delta_yaw_excursion_rad': None, 'Delta_accepted_keyscans': None,
        'Delta_historical_factors': None,
        'comparability_to_v14': 'NOT_DIRECTLY_COMPARABLE',
        'pooled_with_v14': False, 'audit_label': AUDIT_LABEL,
        'status': 'TECHNICALLY_INCOMPLETE_NO_PRIMARY_POOLING',
    })
    return rows


def _save_figure(fig, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches='tight', metadata={
        'Creator': 'v14_heterogeneity_audit.py',
        'Description': AUDIT_LABEL})
    plt.close(fig)


def make_figures(rows, endpoint_rows, output_dir):
    output_dir = Path(output_dir)
    colors = {'target_A': '#2166ac', 'target_B': '#b2182b'}
    labels = [row['block_id'].replace('target_', '') for row in rows]

    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    ax.bar(labels, [row['D_sweep'] for row in rows],
           color=[colors[row['target_label']] for row in rows])
    ax.axhline(0, color='black', linewidth=0.8)
    ax.set_ylabel(r'$D_{sweep}=J_T(A2)-J_T(A3)$')
    ax.set_title('V14 block-level broad-package effect (exploratory context audit)')
    ax.tick_params(axis='x', rotation=35)
    _save_figure(fig, output_dir / '01_D_sweep_by_target_block.svg')

    for number, field, xlabel in (
            ('02', 'Delta_yaw_excursion_full_treatment_rad',
             r'$\Delta$ full-treatment yaw excursion [rad]'),
            ('03', 'Delta_historical_factors',
             r'$\Delta$ historical-factor count (A2-A3)')):
        fig, ax = plt.subplots(figsize=(6.4, 4.8))
        for row in rows:
            ax.scatter(row[field], row['D_sweep'], s=55,
                       color=colors[row['target_label']])
            ax.annotate(row['block_id'].split('_')[-1],
                        (row[field], row['D_sweep']), xytext=(4, 4),
                        textcoords='offset points', fontsize=8)
        ax.axhline(0, color='black', linewidth=0.7)
        ax.axvline(0, color='black', linewidth=0.7)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(r'$D_{sweep}$')
        ax.set_title('Exploratory association; n=8 blocks')
        _save_figure(fig, output_dir / '{}_D_sweep_vs_{}.svg'.format(
            number, field.replace('Delta_', 'delta_')))

    fig, axes = plt.subplots(1, 3, figsize=(13.0, 4.2))
    layer_fields = ['Delta_accepted_keyscans',
                    'Delta_historical_factors', 'D_sweep']
    layer_values = np.asarray([[float(row[field]) for field in layer_fields]
                               for row in rows], dtype=float)
    layer_means = layer_values.mean(axis=0)
    layer_stds = layer_values.std(axis=0)
    layer_stds[layer_stds == 0] = 1.0
    standardized = (layer_values - layer_means) / layer_stds
    for row_index, row in enumerate(rows):
        color = colors[row['target_label']]
        axes[0].scatter(row['Delta_accepted_keyscans'],
                        row['Delta_historical_factors'], color=color)
        axes[1].scatter(row['Delta_historical_factors'], row['D_sweep'],
                        color=color)
        axes[2].plot([0, 1, 2], standardized[row_index],
                    color=color, alpha=0.75, marker='o')
    axes[0].set(xlabel=r'$\Delta$ keyscans',
                ylabel=r'$\Delta$ historical factors')
    axes[1].set(xlabel=r'$\Delta$ historical factors', ylabel=r'$D_{sweep}$')
    axes[2].set_xticks([0, 1, 2], ['keyscans', 'historical', 'D_sweep'])
    axes[2].set_ylabel('Within-variable standardized value')
    axes[2].set_title('Standardized paths identify blocks')
    fig.suptitle('Keyscan realization → historical realization → information effect')
    _save_figure(fig, output_dir / '04_three_layer_realization.svg')

    fig, ax = plt.subplots(figsize=(8.0, 5.0))
    for row in rows:
        ax.plot(['A1', 'A3', 'A2'], [row['J_A1'], row['J_A3'], row['J_A2']],
                marker='o', color=colors[row['target_label']], alpha=0.8,
                label=row['block_id'])
    handles, names = ax.get_legend_handles_labels()
    ax.legend(handles, names, ncol=2, fontsize=7, frameon=False)
    ax.set_ylabel(r'$J_T$')
    ax.set_title('A1/A3/A2 target-information trajectory by canonical block')
    _save_figure(fig, output_dir / '05_J_T_trajectory_per_block.svg')

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.4))
    for row in rows:
        for ax, field, title in (
                (axes[0], 'pre_cycle_rank', 'Pre-graph cycle rank'),
                (axes[1], 'J_pre', r'Pre-treatment $J_T$')):
            ax.scatter(row[field], row['D_sweep'], s=50,
                       color=colors[row['target_label']])
            ax.annotate(row['block_id'].split('_')[-1],
                        (row[field], row['D_sweep']), xytext=(3, 3),
                        textcoords='offset points', fontsize=7)
            ax.set_xlabel(title)
            ax.set_ylabel(r'$D_{sweep}$')
    fig.suptitle('Pre-graph context versus broad-package effect (n=8)')
    _save_figure(fig, output_dir / '06_pregraph_metric_vs_D_sweep.svg')

    endpoint_by_block = {row['block_id']: row for row in endpoint_rows}
    heat_fields = ['endpoint_jaccard_similarity',
                   'historical_endpoint_novelty',
                   'historical_endpoint_loss', 'nonlocal_historical_gain']
    matrix = np.asarray([[float(endpoint_by_block[row['block_id']][field])
                          for field in heat_fields] for row in rows])
    normalized = matrix.copy()
    for column in range(matrix.shape[1]):
        low, high = matrix[:, column].min(), matrix[:, column].max()
        normalized[:, column] = ((matrix[:, column] - low) / (high - low)
                                 if high > low else 0.5)
    fig, ax = plt.subplots(figsize=(8.0, 5.3))
    image = ax.imshow(normalized, cmap='viridis', aspect='auto', vmin=0, vmax=1)
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            ax.text(j, i, '{:.2f}'.format(matrix[i, j]), ha='center',
                    va='center', color='white' if normalized[i, j] < 0.45 else 'black')
    ax.set_xticks(range(len(heat_fields)),
                  ['Jaccard', 'A2-only', 'A3-only', 'nonlocal gain'])
    ax.set_yticks(range(len(rows)), labels)
    ax.set_title('Historical endpoint overlap and novelty (raw values annotated)')
    fig.colorbar(image, ax=ax, label='within-column normalized for display')
    _save_figure(fig, output_dir / '07_endpoint_overlap_novelty_heatmap.svg')


def causal_relationship_summary():
    return {
        'label': 'EXPLORATORY_NONIDENTIFIED_DAG',
        'nodes': [
            {'id': 'pregraph_scene_context', 'measurement': 'MEASURED'},
            {'id': 'effective_action_dose', 'measurement': 'MEASURED'},
            {'id': 'accepted_keyscan_realization', 'measurement': 'MEASURED'},
            {'id': 'historical_factor_realization', 'measurement': 'MEASURED'},
            {'id': 'posterior_information_effect', 'measurement': 'MEASURED'},
        ],
        'edges': [
            {'source': 'pregraph_scene_context', 'target': 'effective_action_dose',
             'status': 'INFERRED', 'causal_identified': False,
             'interpretation': 'protocol and realized geometry can couple context to dose'},
            {'source': 'effective_action_dose',
             'target': 'accepted_keyscan_realization', 'status': 'MEASURED',
             'interpretation': 'association only', 'causal_identified': False},
            {'source': 'accepted_keyscan_realization',
             'target': 'historical_factor_realization', 'status': 'MEASURED',
             'interpretation': 'association only', 'causal_identified': False},
            {'source': 'historical_factor_realization',
             'target': 'posterior_information_effect', 'status': 'MEASURED',
             'interpretation': '8/8 sign alignment; association only',
             'causal_identified': False},
            {'source': 'pregraph_scene_context',
             'target': 'accepted_keyscan_realization', 'status': 'UNIDENTIFIED',
             'role': 'candidate effect modification'},
            {'source': 'pregraph_scene_context',
             'target': 'posterior_information_effect', 'status': 'UNIDENTIFIED',
             'role': 'candidate factor-utility modification'},
        ],
        'warning': 'The DAG is a hypothesis map, not an identified causal graph.',
    }


def competing_hypotheses_summary(rows, correlations, confounding, alignment):
    corr_to_outcome = {row['feature_x']: row for row in correlations
                       if row['feature_y'] == 'D_sweep'}
    confounded = {row['feature'] for row in confounding
                  if row['status'] ==
                  'TARGET_FEATURE_CONFOUNDING_NOT_IDENTIFIABLE'}
    return {
        'audit_label': AUDIT_LABEL,
        'causal_identification': False,
        'H1_ACTION_DOSE': {
            'status': 'MEASURED_ASSOCIATION_TARGET_CONFOUNDED',
            'pearson_r_with_D_sweep': corr_to_outcome[
                'Delta_yaw_excursion_full_treatment_rad']['pearson_r'],
            'spearman_rho_with_D_sweep': corr_to_outcome[
                'Delta_yaw_excursion_full_treatment_rad']['spearman_rho'],
            'target_confounding': (
                'Delta_yaw_excursion_full_treatment_rad' in confounded),
        },
        'H2_MEASUREMENT_REALIZATION': {
            'status': 'STRONGEST_MEASURED_SIGN_ASSOCIATION_NOT_CAUSAL',
            'historical_factor_sign_alignment': alignment[
                'Delta_historical_factors'],
            'total_factor_sign_alignment': alignment['Delta_total_factors'],
            'local_factor_sign_alignment': alignment['Delta_local_factors'],
            'keyscan_sign_alignment': alignment['Delta_accepted_keyscans'],
            'historical_realization_target_confounding': (
                'Delta_historical_factors' in confounded),
        },
        'H3_PREGRAPH_CONTEXT': {
            'status': 'NOT_RESOLVED',
            'pre_cycle_rank_spearman_rho': corr_to_outcome[
                'pre_cycle_rank']['spearman_rho'],
            'J_pre_spearman_rho': corr_to_outcome['J_pre']['spearman_rho'],
            'note': 'weak simple associations at n=8 do not rule out effect modification',
        },
        'H4_SCENE_ASSOCIATION_GEOMETRY': {
            'status': 'UNIDENTIFIED',
            'local_scan_descriptor_available': False,
            'local_occupancy_descriptor_available': False,
            'note': 'target geometry and realized dose are not experimentally separated',
        },
        'ranked_direction': 'MULTIFACTOR_INTERACTION_CANDIDATE',
    }


def context_disentanglement_design(rows):
    a3_planned = [float(row['A3_planned_post_arrival_angular_path_rad'])
                  for row in rows]
    a2_planned = [float(row['A2_planned_post_arrival_angular_path_rad'])
                  for row in rows]
    trigger_total = float(np.median(a3_planned))
    high_total = float(np.median(a2_planned))
    return {
        'name': 'CONTEXT_DISENTANGLEMENT_EXPERIMENT',
        'status': 'DESIGN_ONLY_NOT_EXECUTED',
        'research_question': ('How do controlled cumulative angular dose and '
                              'target context interact to change realized '
                              'historical measurement utility?'),
        'factorial_structure': 'Target A/B x three identical dose packages',
        'dose_levels': [
            {'name': 'ZERO', 'cumulative_yaw_rad': 0.0,
             'derivation': 'static reference under the same N-scan budget'},
            {'name': 'THRESHOLD', 'cumulative_yaw_rad': trigger_total,
             'derivation': ('median v14 A3 planned post-arrival cumulative yaw; '
                            'tied to the certified near-threshold package')},
            {'name': 'HIGH', 'cumulative_yaw_rad': high_total,
             'derivation': ('median v14 A2 planned post-arrival cumulative yaw, '
                            're-expressed with common initial/final orientation')},
        ],
        'motion_template': ('start at anchor yaw; execute a symmetric scaled '
                            'rotation template; return to anchor yaw'),
        'controls': [
            'identical dose levels at both targets',
            'common initial orientation', 'same final orientation',
            'fixed N=347 sensing budget',
            'fresh preregistered histories',
            'full seed pool before outcome-blind selection',
            'no outcome-driven replacement',
        ],
        'primary_unit': 'canonical-history block',
        'primary_analysis': ('target x dose interaction on historical endpoint '
                             'realization and J_T; no branch pseudoreplication'),
        'purpose': ('identify action dose x context interaction, not re-prove '
                    'that broad sweep is universally effective'),
        'execution_authorized': False,
    }


def audit(root=RESULT_ROOT):
    root = Path(root).resolve()
    if root != RESULT_ROOT.resolve():
        raise RuntimeError('audit output root is frozen by task scope')
    verification_before = verify_v14_immutable()
    if not verification_before['passed']:
        raise RuntimeError('frozen v14 hash verification failed')
    analysis = root / 'analysis'
    figures = root / 'figures'
    analysis.mkdir(parents=True, exist_ok=True)
    (root / 'design').mkdir(parents=True, exist_ok=True)
    (root / 'provenance').mkdir(parents=True, exist_ok=True)

    history = load_json(V14_ROOT /
                        'qualification/frozen_history_manifest.json')
    primary = read_csv(V14_ROOT / 'analysis/primary_block_table.csv')
    metrics = read_csv(V14_ROOT / 'analysis/branch_metrics.csv')
    constraints = read_csv(V14_ROOT / 'analysis/constraint_mechanism.csv')
    primary_by_block = {row['block_id']: row for row in primary}
    blocks = [row for target in TARGETS
              for row in history['selected_blocks'][target]]

    pretreatment, contract = [], None
    dose = []
    for block in blocks:
        replay_block = (V14_ROOT / 'collection/replays' /
                        block['target_label'] / block['block_id'])
        row, current_contract = extract_pretreatment_features(
            block['block_id'], block['seed'], block['target_label'], replay_block)
        if contract is not None and contract != current_contract:
            raise RuntimeError('pretreatment feature contract changed by block')
        contract = current_contract
        pretreatment.append(row)
        dose.append(extract_action_dose(block['block_id'],
                                        block['target_label']))
    write_csv(analysis / 'pretreatment_feature_table.csv', pretreatment)
    atomic_json(analysis / 'pretreatment_feature_contract.json', {
        'audit_label': AUDIT_LABEL, 'features': contract,
        'future_predictor_allowlist': sorted(
            field for field, available in contract.items() if available),
        'post_treatment_feature_leakage_allowed': False,
    })
    write_csv(analysis / 'action_dose_table.csv', dose)

    realized = extract_realized_differences(metrics)
    write_csv(analysis / 'realized_measurement_difference_table.csv', realized)
    endpoint_rows, factor_details = endpoint_analysis(constraints)
    write_csv(analysis / 'endpoint_set_comparison.csv', endpoint_rows)
    write_csv(analysis / 'historical_factor_details.csv', factor_details)

    pre_by = {row['block_id']: row for row in pretreatment}
    dose_by = {row['block_id']: row for row in dose}
    realized_by = {row['block_id']: row for row in realized}
    endpoint_by = {row['block_id']: row for row in endpoint_rows}
    merged = []
    for block in blocks:
        block_id = block['block_id']
        outcome = primary_by_block[block_id]
        merged.append({
            **pre_by[block_id], **dose_by[block_id], **realized_by[block_id],
            **endpoint_by[block_id],
            'J_A1': float(outcome['J_A1']),
            'J_A3': float(outcome['J_A3']),
            'J_A2': float(outcome['J_A2']),
            'D_trigger': float(outcome['D_trigger']),
            'D_sweep': float(outcome['D_sweep']),
            'D_total': float(outcome['D_total']),
            'outcome__PRETREATMENT_AVAILABLE': False,
            'audit_label': AUDIT_LABEL,
        })
    write_csv(analysis / 'block_heterogeneity_table.csv', merged)

    correlation_fields = [
        'target_B_indicator', 'Delta_yaw_excursion_full_treatment_rad',
        'Delta_completion_scan_index', 'Delta_treatment_distance_m',
        'J_pre', 'pre_cycle_rank', 'target_incident_pre_edges',
        'Delta_accepted_keyscans', 'Delta_total_factors',
        'Delta_local_factors', 'Delta_historical_factors',
        'historical_endpoint_novelty', 'historical_endpoint_loss',
        'nonlocal_historical_gain', 'D_trigger', 'D_sweep']
    correlations = correlation_matrix(merged, correlation_fields)
    write_csv(analysis / 'feature_correlation_matrix.csv', correlations)
    confounding_fields = [
        'Delta_yaw_excursion_full_treatment_rad',
        'Delta_completion_scan_index', 'Delta_treatment_distance_m',
        'J_pre', 'pre_cycle_rank', 'Delta_historical_factors',
        'historical_endpoint_novelty', 'nonlocal_historical_gain']
    confounding = target_confounding(merged, confounding_fields)
    write_csv(analysis / 'target_feature_confounding.csv', confounding)
    predictors = ['Delta_yaw_excursion_full_treatment_rad',
                  'Delta_historical_factors', 'Delta_accepted_keyscans',
                  'pre_cycle_rank', 'J_pre']
    write_csv(analysis / 'leave_one_block_sensitivity.csv',
              leave_one_out(merged, predictors))

    alignment = sign_alignment(merged, [
        'Delta_historical_factors', 'Delta_total_factors',
        'Delta_local_factors', 'Delta_accepted_keyscans'])
    historical_alignment = alignment['Delta_historical_factors']
    exact_historical_alignment = (
        historical_alignment['aligned'] == 8 and
        historical_alignment['evaluable'] == 8)
    alignment_label = ('HISTORICAL_REALIZATION_SIGN_ALIGNMENT = 8/8'
                       if exact_historical_alignment
                       else 'HISTORICAL_REALIZATION_SIGN_ALIGNMENT_NOT_8_OF_8')
    atomic_json(analysis / 'sign_alignment_audit.json', {
        'audit_label': AUDIT_LABEL, 'alignments': alignment,
        'historical_alignment_label': alignment_label,
        'interpretation': 'MEASURED ASSOCIATION NOT CAUSAL',
    })

    trigger_rows = trigger_realization(metrics, primary)
    write_csv(analysis / 'trigger_realization_table.csv', trigger_rows)
    trigger_by_target = {}
    for target in TARGETS:
        values = [float(row['D_trigger']) for row in trigger_rows
                  if row['target_label'] == target]
        trigger_by_target[target] = {
            'mean_D_trigger': float(np.mean(values)),
            'median_D_trigger': float(np.median(values)),
            'positive': sum(value > 0 for value in values),
            'n': len(values),
        }
    atomic_json(analysis / 'context_dependent_action_intensity.json', {
        'label': 'CONTEXT_DEPENDENT_ACTION_INTENSITY_HYPOTHESIS',
        'status': AUDIT_LABEL, 'target_summaries': trigger_by_target,
        'hypothesis': {
            'target_A': 'minimal trigger may be sufficient; broad package may be unnecessary or harmful',
            'target_B': 'minimal trigger may be insufficient; broader package may be needed',
        },
        'proved': False, 'target_confounding_unresolved': True,
    })

    cross_rows = cross_protocol_context()
    write_csv(analysis / 'cross_protocol_context.csv', cross_rows)
    atomic_json(analysis / 'cross_protocol_non_pooling_guard.json', {
        'pooled_analysis_allowed': False,
        'all_legacy_rows_marked_not_directly_comparable': all(
            row['comparability_to_v14'] == 'NOT_DIRECTLY_COMPARABLE'
            for row in cross_rows),
        'reason': 'estimand, exposure rule, history pool, and protocol differ',
        'audit_label': AUDIT_LABEL,
    })
    atomic_json(analysis / 'causal_relationship_summary.json',
                causal_relationship_summary())
    atomic_json(analysis / 'competing_hypotheses.json',
                competing_hypotheses_summary(
                    merged, correlations, confounding, alignment))

    confounded = [row['feature'] for row in confounding
                  if row['status'] ==
                  'TARGET_FEATURE_CONFOUNDING_NOT_IDENTIFIABLE']
    if historical_alignment['aligned'] == 8 and confounded:
        direction = 'MULTIFACTOR_INTERACTION_CANDIDATE'
    elif historical_alignment['aligned'] == 8:
        direction = 'MEASUREMENT_REALIZATION_DOMINANT_CANDIDATE'
    else:
        direction = 'HETEROGENEITY_NOT_RESOLVED'
    summary = {
        'audit_id': 'V14_H_CONTEXT_DEPENDENT_REALIZATION_AUDIT',
        'audit_label': AUDIT_LABEL,
        'scientific_role': 'POST_CONFIRMATORY_EXPLORATORY',
        'v14_prospective_gate_unchanged': 'V14_PROSPECTIVE_NO_SUPPORT',
        'universal_broad_sweep_hypothesis': 'STOPPED',
        'block_count': len(merged), 'target_A_positive_D_sweep': sum(
            row['target_label'] == 'target_A' and row['D_sweep'] > 0
            for row in merged),
        'target_B_positive_D_sweep': sum(
            row['target_label'] == 'target_B' and row['D_sweep'] > 0
            for row in merged),
        'sign_alignment': alignment,
        'historical_alignment_label': alignment_label,
        'target_confounded_features': confounded,
        'target_feature_confounding_label': (
            'TARGET_FEATURE_CONFOUNDING_NOT_IDENTIFIABLE'
            if confounded else 'TARGET_FEATURE_SEPARATION_NOT_COMPLETE'),
        'trigger_summary': trigger_by_target,
        'ranked_direction': direction,
        'causal_claim': False,
        'v14_data_modified': False,
        'new_experiment_executed': False,
    }
    atomic_json(analysis / 'heterogeneity_summary.json', summary)
    design = context_disentanglement_design(merged)
    atomic_json(root / 'design/CONTEXT_DISENTANGLEMENT_EXPERIMENT.json', design)
    make_figures(merged, endpoint_rows, figures)

    verification_after = verify_v14_immutable()
    if not verification_after['passed']:
        raise RuntimeError('v14 changed during heterogeneity audit')
    atomic_json(root / 'provenance/v14_post_audit_verification.json',
                verification_after)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=RESULT_ROOT)
    args = parser.parse_args()
    print(json.dumps(audit(args.root), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
