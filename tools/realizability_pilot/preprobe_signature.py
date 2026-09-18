#!/usr/bin/python3
"""Pre-probe graph signature: one deterministic description of the graph state
that a matched episode block must share before its probe/action phase opens.

The signature is produced by the live driver (written while the probe phase is
still closed, so it cannot contain a probe outcome) and can be re-derived from
the recorded ``pose_graph_before.json`` snapshot by the offline analyses.  The
two paths must agree, which is asserted by the unit tests.
"""

import hashlib
import json
import math


def path_length(samples):
    return sum(
        math.hypot(right[1] - left[1], right[2] - left[2])
        for left, right in zip(samples, samples[1:]))


def _upper_triangle_values(edge):
    upper = edge.get('covariance_upper_triangle')
    if not upper:
        return None
    values = [float(value) for value in str(upper).split()]
    if len(values) != 6:
        return None
    return values


def build_signature(before, frozen_target, spec, run_id, wall_time=None,
                    gt_pose=None):
    """Build the signature dict from a before-probe snapshot."""
    nodes = sorted(before['full_pose_nodes'], key=lambda node: node['id'])
    edges = sorted(before['full_pose_edges'], key=lambda edge: edge['index'])
    path_nodes = sorted(before['nodes'], key=lambda node: node['id'])
    endpoint_pairs = sorted(
        (min(int(edge['start']), int(edge['end'])),
         max(int(edge['start']), int(edge['end']))) for edge in edges)
    endpoint_set_hash = hashlib.sha256(json.dumps(
        endpoint_pairs, separators=(',', ':')).encode()).hexdigest()
    node_set_hash = hashlib.sha256(json.dumps(
        [int(node['id']) for node in nodes],
        separators=(',', ':')).encode()).hexdigest()
    covariances = [values for values in (
        _upper_triangle_values(edge) for edge in edges) if values is not None]
    traces = sorted(values[0] + values[3] + values[5] for values in covariances)
    determinants = sorted(
        values[0] * (values[3] * values[5] - values[4] * values[4])
        - values[1] * (values[1] * values[5] - values[4] * values[2])
        + values[2] * (values[1] * values[4] - values[3] * values[2])
        for values in covariances)
    return {
        'signature_version': 1,
        'run_id': run_id,
        'episode_id': spec.get('episode_id'),
        'protocol_version': spec.get('protocol_version'),
        'target_id': spec.get('target_id'),
        'condition_id': spec.get('condition_id'),
        'maneuver_type': spec.get('maneuver_type'),
        'tsp_seed': spec.get('tsp_seed'),
        'diagnostics_enabled': bool(spec.get('diagnostics_enabled')),
        'provenance_enabled': bool(spec.get('provenance_enabled', True)),
        'block_id': spec.get('block_id'),
        'block_position': spec.get('block_position'),
        'wall_time': wall_time,
        'sim_time': before.get('sim_time'),
        'snapshot_phase': before.get('phase'),
        'node_count': len(nodes),
        'keyscan_count': len(path_nodes),
        'node_id_set_hash': node_set_hash,
        'node_ids': [int(node['id']) for node in nodes],
        'node_unique_ids': [int(node.get('unique_id', -1)) for node in nodes],
        'edge_count': len(edges),
        'edge_endpoint_set_hash': endpoint_set_hash,
        'edge_endpoints': [[int(start), int(end)] for start, end in endpoint_pairs],
        'corrected_path_length_m': path_length(
            [[0.0, float(node['x']), float(node['y'])] for node in path_nodes]),
        'first_corrected_pose': (
            None if not path_nodes else [float(path_nodes[0]['x']),
                                         float(path_nodes[0]['y']),
                                         float(path_nodes[0]['theta'])]),
        'last_corrected_pose': (
            None if not path_nodes else [float(path_nodes[-1]['x']),
                                         float(path_nodes[-1]['y']),
                                         float(path_nodes[-1]['theta'])]),
        'edge_covariance_count': len(covariances),
        'edge_covariance_trace_median': (
            None if not traces else float(traces[len(traces) // 2])),
        'edge_covariance_trace_max': None if not traces else float(traces[-1]),
        'edge_covariance_logdet_median': (
            None if not determinants else float(
                math.log(max(determinants[len(determinants) // 2], 1e-300)))),
        'robot_gt_pose_before_probe': None if gt_pose is None else list(gt_pose),
        'robot_gt_pose_before_probe_format': 'stamp,x,y,theta',
        'route_start_node_count': frozen_target['route_start_node_count'],
        'target_historical_scan_ids': list(frozen_target['historical_scan_ids']),
        'target_historical_unique_ids': list(frozen_target['historical_unique_ids']),
        'target_segment_size': len(frozen_target['historical_scan_ids']),
        'target_anchor': dict(frozen_target['anchor_scan']),
        'target_reference': list(frozen_target['target_reference']),
        'target_identity_gate': frozen_target['target_identity_gate'],
        'before_probe': True,
    }
