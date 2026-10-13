#!/usr/bin/python3
"""Doc-80 sections 3.4 + 5.2: frame identity, extrinsics and pre-action state.

Outputs
- audit/state_identity_and_frame_audit.csv
- analysis/pre_action_state_audit.csv
"""

import json
import math
import statistics
from pathlib import Path

import sys

from . import common

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'continuous_revisit'))
import geometry as ge  # noqa: E402
import analysis as frozen_analysis  # noqa: E402


def sample_accept_residuals(run, stage='final'):
    """Model check: node_laser o T_LASER_BASE vs recorded map->base at accept."""
    scans = common.jsonl(run['attempt_dir'] / 'scan_stream.jsonl')
    accepts = common.accepts(run)
    graph = common.sync_graph(run, stage)
    if graph is None or not scans or not accepts:
        return []
    nodes = {node['state_id']: node for node in graph['nodes']}
    residuals = []
    for item in accepts:
        node = nodes.get(item['state_id'])
        if node is None:
            continue
        scan = common.scan_at(scans, item['sim_time'], tolerance=0.05)
        if scan is None or scan.get('map_base') is None:
            continue
        estimate = common.compose((node['x'], node['y'], node['theta']),
                                  common.T_LASER_BASE)
        residuals.append({
            'state_id': item['state_id'],
            'position_m': common.translation_error(estimate, scan['map_base']),
            'heading_rad': common.rotation_error(estimate, scan['map_base']),
            'map_base_age_s': scan.get('map_base_age_s'),
        })
    return residuals


def extrinsics(run):
    scans = common.jsonl(run['attempt_dir'] / 'scan_stream.jsonl')
    samples = []
    for record in scans[::25]:
        odom_laser = record.get('odom_laser')
        odom_base = record.get('odom_base')
        if odom_laser is None or odom_base is None:
            continue
        samples.append(common.compose(common.inverse(tuple(odom_laser)),
                                      tuple(odom_base)))
    if not samples:
        return None
    x = [value[0] for value in samples]
    y = [value[1] for value in samples]
    yaw = [value[2] for value in samples]
    return {
        'n': len(samples),
        'base_in_laser_x_mean': statistics.mean(x),
        'base_in_laser_x_sd': statistics.pstdev(x),
        'base_in_laser_y_mean': statistics.mean(y),
        'base_in_laser_y_sd': statistics.pstdev(y),
        'base_in_laser_yaw_mean': statistics.mean(yaw),
        'base_in_laser_yaw_sd': statistics.pstdev(yaw),
        'max_sd': max(statistics.pstdev(x), statistics.pstdev(y),
                      statistics.pstdev(yaw)),
    }


def extrinsics_stable(stats, tolerance=0.02):
    """True when the recovered base-in-laser transform is time-stable."""
    if stats is None:
        return False
    return (stats['base_in_laser_x_sd'] <= tolerance
            and stats['base_in_laser_y_sd'] <= tolerance)


def frame_audit(doc80_root=common.DOC80):
    rows = []
    for run in common.valid_runs():
        scans = common.jsonl(run['attempt_dir'] / 'scan_stream.jsonl')
        accepts = common.accepts(run)
        graphs = {stem: common.sync_graph(run, stem) for stem in common.STAGES}
        index_ok = True
        contiguous = True
        unique_ok = True
        for stem, graph in graphs.items():
            if graph is None:
                index_ok = False
                continue
            payload = common.load_json(
                run['attempt_dir'] / 'graph_{}_sync.json'.format(stem))
            ids = sorted(node['state_id'] for node in payload['nodes'])
            if ids != list(range(len(ids))):
                contiguous = False
            # unique id <-> state id stability across stages
        unique_maps = []
        for stem, graph in graphs.items():
            if graph is None:
                continue
            unique_maps.append({node['unique_id']: node['state_id']
                                for node in graph['nodes']})
        for other in unique_maps[1:]:
            shared = set(unique_maps[0]) & set(other)
            if any(unique_maps[0][key] != other[key] for key in shared):
                unique_ok = False
        extr = extrinsics(run)
        residuals = sample_accept_residuals(run)
        residual_positions = [item['position_m'] for item in residuals]
        residual_headings = [item['heading_rad'] for item in residuals]
        ages = [item['map_base_age_s'] for item in residuals
                if item.get('map_base_age_s') is not None]
        first = scans[0] if scans else {}
        rows.append({
            'episode_id': run['episode_id'], 'attempt': run['attempt'],
            'scan_frame_id': first.get('frame_id'),
            'angle_min': first.get('angle_min'), 'angle_max': first.get('angle_max'),
            'angle_increment': first.get('angle_increment'),
            'range_min': first.get('range_min'), 'range_max': first.get('range_max'),
            'fov_deg': (math.degrees(first.get('angle_max', 0.0)
                                     - first.get('angle_min', 0.0))
                        if first else None),
            'beam_count_est': (int(round((first.get('angle_max', 0.0)
                                          - first.get('angle_min', 0.0))
                                         / first.get('angle_increment', 1.0))) + 1
                               if first else None),
            'dump_index_equals_state_id': index_ok,
            'state_ids_contiguous': contiguous,
            'unique_id_mapping_stable': unique_ok,
            'base_in_laser_x_mean': extr['base_in_laser_x_mean'] if extr else None,
            'base_in_laser_x_sd': extr['base_in_laser_x_sd'] if extr else None,
            'base_in_laser_y_mean': extr['base_in_laser_y_mean'] if extr else None,
            'base_in_laser_yaw_mean': extr['base_in_laser_yaw_mean'] if extr else None,
            'extrinsics_max_sd': extr['max_sd'] if extr else None,
            'geometry_py_LASER_OFFSET_X': ge.LASER_OFFSET_X,
            'laser_offset_matches_geometry_py': (
                extr is not None and abs(extr['base_in_laser_x_mean']
                                         + ge.LASER_OFFSET_X) <= 0.01),
            'model_residual_samples': len(residuals),
            'model_residual_position_mean_m': (statistics.mean(residual_positions)
                                               if residual_positions else None),
            'model_residual_position_max_m': (max(residual_positions)
                                              if residual_positions else None),
            'model_residual_heading_mean_rad': (statistics.mean(residual_headings)
                                                if residual_headings else None),
            'model_residual_heading_max_rad': (max(residual_headings)
                                               if residual_headings else None),
            'map_base_age_max_s': max(ages) if ages else None,
            'accept_states': len(accepts),
        })
    common.write_csv(Path(doc80_root) / 'audit' / 'state_identity_and_frame_audit.csv',
                     rows)
    return rows


def pre_action_state_audit(doc80_root=common.DOC80):
    rows = []
    for run in common.valid_runs():
        result = run['result']
        stage_windows = common.windows(result)
        scans = common.jsonl(run['attempt_dir'] / 'scan_stream.jsonl')
        gt_stream = common.jsonl(run['attempt_dir'] / 'gt_stream.jsonl')
        graph = common.sync_graph(run, 'arrival')
        if stage_windows is None or graph is None:
            continue
        frozen = run['frozen']
        targets = [int(value) for value in frozen['target_state_ids']]
        anchor = int(frozen['anchor']['id'])
        nodes = {node['state_id']: node for node in graph['nodes']}
        edges = graph['edges']
        edge_keys = {(edge['source_state_id'], edge['target_state_id'])
                     for edge in edges}
        node_ids = set(nodes)
        chain_edges = sum(1 for a, b in edge_keys if a in node_ids and b in node_ids
                          and (b == a + 1 or a == b + 1))
        nonchain_edges = len(edge_keys) - chain_edges
        analysis_graph = common.graph_as_analysis(graph)
        try:
            j_arrival = frozen_analysis.target_score(analysis_graph, targets)['J_T']
        except Exception:  # noqa: BLE001
            j_arrival = None

        # robot pose at action start (last return scan) and its GT
        action_start = stage_windows['action'][0]
        start_scan = next((record for record in scans
                           if record['index'] == action_start - 1), None)
        robot_pose = start_scan.get('map_base') if start_scan else None
        robot_laser = (common.compose(tuple(robot_pose), (0.2, 0.0, 0.0))
                       if robot_pose else None)
        gt_pose = (common.gt_pose_at(gt_stream, start_scan['stamp'])
                   if start_scan else None)

        # target spatial distribution
        target_positions = [(nodes[state]['x'], nodes[state]['y'])
                            for state in targets if state in nodes]
        spread = None
        centroid_distance = None
        if target_positions and robot_laser:
            cx = sum(p[0] for p in target_positions) / len(target_positions)
            cy = sum(p[1] for p in target_positions) / len(target_positions)
            spread = statistics.mean(
                math.hypot(px - cx, py - cy) for px, py in target_positions)
            centroid_distance = math.hypot(cx - robot_laser[0],
                                           cy - robot_laser[1])
        anchor_node = nodes.get(anchor)
        anchor_pose = (anchor_node['x'], anchor_node['y'], anchor_node['theta']) \
            if anchor_node else None
        rows.append({
            'episode_id': run['episode_id'], 'attempt': run['attempt'],
            'place': run['spec'].get('place_id'),
            'action': run['spec'].get('action_id'),
            'seed': run['spec'].get('tsp_seed'),
            'nodes_arrival_sync': len(graph['nodes']),
            'edges_arrival_sync': len(graph['edges']),
            'chain_edges_arrival': chain_edges,
            'nonchain_edges_arrival': nonchain_edges,
            'J_arrival_sync': j_arrival,
            'delta_J_return_sync': None,  # filled from doc79 metrics below
            'anchor_state_id': anchor,
            'anchor_pose': json.dumps(anchor_pose),
            'robot_pose_at_action_start': json.dumps(robot_pose),
            'robot_laser_at_action_start': json.dumps(robot_laser),
            'gt_pose_at_action_start': json.dumps(
                None if gt_pose is None else [gt_pose['x'], gt_pose['y'],
                                              gt_pose['theta']]),
            'target_count_in_graph': len(target_positions),
            'target_spread_m': spread,
            'target_centroid_distance_m': centroid_distance,
            'last_accept_before_action': (
                max((item['sim_time'] for item in common.accepts(run)
                     if item['sim_time'] <= (start_scan['stamp']
                                             if start_scan else 0.0)),
                    default=None)),
            'scan_params_fov_deg': (math.degrees(
                scans[0]['angle_max'] - scans[0]['angle_min']) if scans else None),
        })

    # join Doc-79 recorded return-stage increment (read-only source)
    metrics_path = (common.DOC79 / 'analysis' / 'per_episode_metrics.csv')
    import csv
    if metrics_path.is_file():
        lookup = {}
        with open(metrics_path) as handle:
            for row in csv.DictReader(handle):
                lookup[(row['episode_id'], row['attempt'])] = row
        for row in rows:
            source = lookup.get((row['episode_id'], row['attempt']))
            if source and source.get('delta_J_return_sync'):
                row['delta_J_return_sync'] = float(source['delta_J_return_sync'])
    common.write_csv(Path(doc80_root) / 'analysis' / 'pre_action_state_audit.csv',
                     rows)
    return rows


if __name__ == '__main__':
    frame_audit()
    pre_action_state_audit()
