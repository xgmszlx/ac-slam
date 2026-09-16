#!/usr/bin/python3
"""Frozen action and target definitions for the controlled pilot.

The first target is deliberately a single infrastructure target in map3.  It is
not labelled as a corridor/room semantic class: map3 is a synthetic open grid and
does not support that interpretation.  More targets are admitted only after this
route completes reproducibly.
"""

import copy
import math


PROTOCOL_VERSION = 'p1_preflight_v7'


def wrap_angle(value):
    return math.atan2(math.sin(value), math.cos(value))


def resolve_local_waypoints(origin, offsets):
    """Resolve start-local SE(2) offsets into the episode mapper frame."""
    x0, y0, theta0 = (float(value) for value in origin)
    cosine = math.cos(theta0)
    sine = math.sin(theta0)
    resolved = []
    for dx, dy, dtheta in offsets:
        resolved.append([
            x0 + cosine * float(dx) - sine * float(dy),
            y0 + sine * float(dx) + cosine * float(dy),
            wrap_angle(theta0 + float(dtheta)),
        ])
    return resolved


def goal_errors(observed_pose, goal):
    """Return independent mapper-pose position and heading errors."""
    return (
        math.hypot(float(observed_pose[0]) - float(goal[0]),
                   float(observed_pose[1]) - float(goal[1])),
        abs(wrap_angle(float(observed_pose[2]) - float(goal[2]))),
    )


def target_freeze_checks(node_count, anchor_id, anchor_distance_m,
                         segment_count, route_start_node_count, spec):
    """Evaluate the frozen, outcome-blind target-identity gates.

    These checks only establish that the selected historical scan belongs to
    the newly executed history route and is geometrically close to its first
    waypoint.  They do not inspect or predict the later loop-closure outcome.
    """
    checks = {
        'minimum_history_node_count': (
            int(node_count) >= int(spec['minimum_history_node_count'])),
        'anchor_within_reference_radius': (
            float(anchor_distance_m) <= float(spec['target_anchor_max_distance_m'])),
        'anchor_acquired_after_route_start': (
            int(anchor_id) >= int(route_start_node_count)),
        'minimum_target_segment_scans': (
            int(segment_count) >= int(spec['minimum_target_segment_scans'])),
    }
    return {
        'passed': all(checks.values()),
        'checks': checks,
        'observed': {
            'node_count': int(node_count),
            'anchor_id': int(anchor_id),
            'anchor_distance_m': float(anchor_distance_m),
            'segment_count': int(segment_count),
            'route_start_node_count': int(route_start_node_count),
        },
        'thresholds': {
            'minimum_history_node_count': int(spec['minimum_history_node_count']),
            'target_anchor_max_distance_m': float(
                spec['target_anchor_max_distance_m']),
            'minimum_target_segment_scans': int(
                spec['minimum_target_segment_scans']),
        },
    }


def resolve_marker_edges(marker_edges, nodes):
    """Resolve Karto marker endpoints to full-path state IDs.

    `/Mapper/closure_edges` contains explicit loop edges and ordinary near-chain
    links. Resolution is geometric evidence only; it does not assign edge kind.
    """
    if not nodes:
        return []
    resolved = []
    for edge in marker_edges:
        endpoints = []
        for point in edge:
            node = min(nodes, key=lambda candidate: math.hypot(
                float(candidate['x']) - float(point[0]),
                float(candidate['y']) - float(point[1])))
            endpoints.append({
                'node_id': int(node['id']),
                'match_error_m': math.hypot(
                    float(node['x']) - float(point[0]),
                    float(node['y']) - float(point[1])),
            })
        resolved.append({
            'source': endpoints[0]['node_id'],
            'target': endpoints[1]['node_id'],
            'scan_index_gap': abs(
                endpoints[0]['node_id'] - endpoints[1]['node_id']),
            'endpoint_match_error_max_m': max(
                endpoints[0]['match_error_m'], endpoints[1]['match_error_m']),
            'raw_points': edge,
        })
    return resolved

TARGETS = {
    'map3_grid_anchor_01': {
        'map_id': 'map3',
        'map_name': 'map3/map3',
        'map_width': 74.0,
        'robot_position': '-28.0 -28.0 0',
        'start_pose': [-28.0, -28.0, 0.0],
        # A non-self-intersecting, three-sided rectangle expressed in the
        # episode's mapper-start frame. The v1 Stage-world coordinates were
        # invalid MoveTo goals because Karto's map frame is local to the run.
        # The first goal is the target anchor; the final goal is 6 m away.
        'history_frame': 'episode_mapper_start',
        'history_origin_source': 'first_karto_path_pose_xy_with_fixed_map_axis',
        'route_axis_heading_rad': 0.0,
        'history_offsets': [
            [6.0, 0.0, 0.0],
            [10.0, 0.0, 0.0],
            [10.0, 6.0, math.pi / 2.0],
            [6.0, 6.0, math.pi],
        ],
        'target_history_waypoint_index': 0,
        'target_segment_radius_m': 2.5,
        'target_reached_radius_m': 1.0,
        # Freeze fails closed unless /slam_path supplies a complete historical
        # keyscan sequence and the selected scan is both close to the intended
        # waypoint and newer than the initial-mapping history.
        'minimum_history_node_count': 20,
        'minimum_target_segment_scans': 3,
        'target_anchor_max_distance_m': 1.0,
        'marker_endpoint_max_error_m': 0.05,
        'goal_position_tolerance_m': 0.75,
        'goal_heading_tolerance_rad': 0.35,
        'gt_position_tolerance_m': 0.75,
        'gt_heading_tolerance_rad': 0.35,
        'goal_settle_s': 1.0,
        'history_hold_s': 2.0,
        'probe_hold_s': 6.0,
        'move_timeout_s': 360.0,
    },
}


def _condition(condition_id, delta_yaw_deg, offset_m, maneuver, diagnostics):
    return {
        'condition_id': condition_id,
        'delta_yaw_deg': float(delta_yaw_deg),
        'lateral_offset_m': float(offset_m),
        'maneuver_type': maneuver,
        'diagnostics_enabled': bool(diagnostics),
    }


PREFLIGHT_CONDITIONS = [
    _condition('baseline_diag_off', 0, 0.0, 'pass', False),
    _condition('baseline_diag_on', 0, 0.0, 'pass', True),
    _condition('align60_diag_on', 60, 0.0, 'align', True),
    _condition('sweep90_diag_on', 90, 0.0, 'sweep', True),
]


def screening_conditions():
    conditions = []
    for yaw in (0, 30, 60, 90):
        for offset in (0.0, 0.5):
            for maneuver in ('pass', 'align', 'sweep'):
                conditions.append(_condition(
                    'yaw{:03d}_off{:02d}_{}'.format(yaw, int(round(offset * 10)), maneuver),
                    yaw, offset, maneuver, True,
                ))
    return conditions


def episode_specs(profile='preflight', repeats=1, target_ids=None):
    if profile == 'preflight':
        conditions = PREFLIGHT_CONDITIONS
    elif profile == 'screening':
        conditions = screening_conditions()
    else:
        raise ValueError('unknown profile: {}'.format(profile))
    selected = target_ids or sorted(TARGETS)
    unknown = sorted(set(selected) - set(TARGETS))
    if unknown:
        raise ValueError('unknown target ids: {}'.format(', '.join(unknown)))
    episodes = []
    sequence = 0
    for target_id in selected:
        for condition in conditions:
            for repeat in range(1, int(repeats) + 1):
                sequence += 1
                spec = copy.deepcopy(TARGETS[target_id])
                spec.update(copy.deepcopy(condition))
                spec.update({
                    'protocol_version': PROTOCOL_VERSION,
                    'target_id': target_id,
                    'repeat': repeat,
                    'sequence': sequence,
                    'episode_id': '{:04d}_{}_r{:02d}'.format(
                        sequence, condition['condition_id'], repeat),
                })
                episodes.append(spec)
    return episodes
