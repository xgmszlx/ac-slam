#!/usr/bin/python3
"""Frozen protocol for the continuous revisit action experiment (round 2026-10-10).

Design decisions locked before any episode of this round was executed:

* **One route, four places.**  A single frozen route through the map3 pillar grid
  is executed in every episode.  It passes four corners ``A``/``B``/``C``/``D``
  in order, then finishes at a point that is at least 8.5 m away from all four
  corners, so every place is reached once early ("first pass"), left, and then
  returned to by the probe phase of the same physical run.  The four places were
  chosen by measured geometry only (nearest-obstacle distance and angular
  obstacle coverage computed from ``map3.png``), never by action outcome.

* **Four actions** at the arrival pose theta0: ``S0`` (static hold), ``S1``
  (theta0 -> theta0 + dose/2 -> theta0 with dose = 1.087946562824985 rad,
  the historical D1 dose), ``L+`` (theta0 -> theta0 + pi/2 -> theta0) and ``L-``
  (theta0 -> theta0 - pi/2 -> theta0).  ``L+`` and ``L-`` have the same
  cumulative rotation budget and the same speed limits; they differ only in the
  sign of the rotation.

* **Matched conditions.**  All four actions of a group use the same route, the
  same arrival waypoint and the same frozen target identity rule.  The arm order
  inside a group rotates deterministically so that each action occupies each
  order position equally often across the twelve groups.

* **Budget.**  The action phase retains the first ``ACTION_FRAMES`` valid scans;
  the robot keeps sampling after the motion ends until that count is reached.

Nothing in this module reads an action outcome.
"""

import copy
import math

PROTOCOL_VERSION = 'p1_continuous_revisit_v1'

#: Stage world of the frozen map.  ``robot_position`` is the Stage initial pose.
MAP_ID = 'map3'
MAP_NAME = 'map3/map3'
MAP_WIDTH = 74.0
ROBOT_POSITION = '-28.0 -28.0 0'
START_POSE = [-28.0, -28.0, 0.0]
ROUTE_AXIS_HEADING_RAD = 0.0

#: Frozen route expressed in the episode mapper frame (origin = robot start,
#: x forward at heading 0).  Waypoint tuples are ``(dx, dy, heading)`` where the
#: heading is the direction of the leg leaving that waypoint.
ROUTE_OFFSETS = [
    (-2.50, 10.00, 0.0),               # A  (-30.50, -18.00)
    (22.05, 10.00, -math.pi / 2.0),    # B  ( -5.95, -18.00)
    (22.05, -2.00, math.pi),           # C  ( -5.95, -30.00)
    (-2.50, -2.00, 0.0),               # D  (-30.50, -30.00)
    (6.00, -2.00, 0.0),                # finish (-22.00, -30.00)
]

#: The four experimental places are route waypoint 0..3; waypoint 4 is only a
#: finish point so that every place has a genuine return leg.
PLACES = {
    'place_A': {'waypoint_index': 0, 'world_position': [-30.5, -18.0]},
    'place_B': {'waypoint_index': 1, 'world_position': [-5.95, -18.0]},
    'place_C': {'waypoint_index': 2, 'world_position': [-5.95, -30.0]},
    'place_D': {'waypoint_index': 3, 'world_position': [-30.5, -30.0]},
}
PLACE_IDS = ['place_A', 'place_B', 'place_C', 'place_D']

#: Action definitions.  ``max_abs_yaw_rad`` is the magnitude of the single
#: excursion away from theta0; the robot returns to theta0 at the end.
#: Four frozen actions (handoff section 4, table).  ``waypoints`` holds the
#: yaw-goal fractions of the action: the first goal deflects the probe by
#: ``fraction * max_abs_yaw_rad`` and the last goal returns it to theta0, so
#: ``planned_cumulative_rotation_rad`` is the out-and-back total.  ``L-`` keeps
#: a *signed* peak (the sign is the rotation direction); the field name is kept
#: so that every arm carries the same key.
ACTIONS = {
    'S0': {
        'action_id': 'S0',
        'label': 'static_hold',
        'max_abs_yaw_rad': 0.0,
        'planned_cumulative_rotation_rad': 0.0,
        'waypoints': [],
    },
    'S1': {
        'action_id': 'S1',
        'label': 'half_dose_rotation',
        'max_abs_yaw_rad': 1.087946562824985 / 2.0,
        'planned_cumulative_rotation_rad': 1.087946562824985,
        'waypoints': [1.0, 0.0],
    },
    'L+': {
        'action_id': 'L+',
        'label': 'positive_quarter_turn',
        'max_abs_yaw_rad': math.pi / 2.0,
        'planned_cumulative_rotation_rad': math.pi,
        'waypoints': [1.0, 0.0],
    },
    'L-': {
        'action_id': 'L-',
        'label': 'negative_quarter_turn',
        'max_abs_yaw_rad': -math.pi / 2.0,
        'planned_cumulative_rotation_rad': math.pi,
        'waypoints': [1.0, 0.0],
    },
}
ACTION_IDS = ['S0', 'S1', 'L+', 'L-']

#: The action phase retains this many valid scans (historical CD/v14 budget).
ACTION_FRAMES = 347

#: Frozen tolerances and timings.  ``goal_*`` are the navigator's own acceptance
#: tolerances; ``gt_*`` are the independent ground-truth checks.
GOAL_POSITION_TOLERANCE_M = 0.75
GOAL_HEADING_TOLERANCE_RAD = 0.35
GT_POSITION_TOLERANCE_M = 0.75
GT_HEADING_TOLERANCE_RAD = 0.35
GOAL_SETTLE_S = 1.0
HISTORY_HOLD_S = 2.0
ARRIVAL_HOLD_S = 2.0
ACTION_FINISH_HOLD_S = 2.0
MOVE_TIMEOUT_S = 360.0
ACTION_PHASE_TIMEOUT_S = 240.0

#: Target identity rule: the anchor is the graph node closest to the place
#: reference, the segment is the contiguous run of nodes within the radius, and
#: the five target states are the arc-length quantiles of that segment.
TARGET_SEGMENT_RADIUS_M = 2.5
TARGET_STATE_COUNT = 5
TARGET_ANCHOR_MAX_DISTANCE_M = 1.0
#: The anchor must also match the historical observation heading; the window is
#: wider than the navigator's own 0.1 rad acceptance because the mapper only
#: creates a state after 0.52 rad of turning, so the closest state to the stop
#: pose can legitimately lag the final heading by that much.
TARGET_ANCHOR_HEADING_TOLERANCE_RAD = 0.6
#: Fixed position/heading trade-off (metres per radian) in the anchor match.
TARGET_ANCHOR_HEADING_WEIGHT = 0.5
MINIMUM_HISTORY_NODE_COUNT = 40
TARGET_REACHED_RADIUS_M = 1.0

#: Deterministic arm order per group (rotating through all four positions).
GROUP_COUNT = 12
REPEATS = 3


def rotate(values, offset):
    return list(values[offset:]) + list(values[:offset])


def group_id(place_id, repeat):
    return '{}_r{}'.format(place_id, repeat)


def episode_specs():
    """The 48 planned episodes of the main matrix."""
    episodes = []
    sequence = 0
    for place_index, place_id in enumerate(PLACE_IDS):
        for repeat in range(1, REPEATS + 1):
            group = place_index * REPEATS + (repeat - 1)
            order = rotate(ACTION_IDS, group % len(ACTION_IDS))
            for position, action_id in enumerate(order):
                sequence += 1
                spec = build_spec(place_id, repeat, action_id, sequence, group,
                                  position)
                episodes.append(spec)
    return episodes


def build_spec(place_id, repeat, action_id, sequence, group_index,
               order_position, smoke=False):
    place = PLACES[place_id]
    action = ACTIONS[action_id]
    spec = {
        'protocol_version': PROTOCOL_VERSION,
        'round': 'smoke' if smoke else 'main',
        'episode_id': '{:04d}_{}_{}_{}'.format(
            sequence, place_id, 'r{}'.format(repeat), action_id),
        'sequence': sequence,
        'map_id': MAP_ID,
        'map_name': MAP_NAME,
        'map_width': MAP_WIDTH,
        'robot_position': ROBOT_POSITION,
        'start_pose': list(START_POSE),
        'route_axis_heading_rad': ROUTE_AXIS_HEADING_RAD,
        'history_offsets': copy.deepcopy(ROUTE_OFFSETS),
        'target_history_waypoint_index': int(place['waypoint_index']),
        'place_id': place_id,
        'place_world_position': list(place['world_position']),
        'repeat': int(repeat),
        'group_id': group_id(place_id, repeat),
        'group_index': int(group_index),
        'order_position': int(order_position),
        'action_id': action_id,
        'action_label': action['label'],
        'max_abs_yaw_rad': action['max_abs_yaw_rad'],
        'planned_cumulative_rotation_rad': action[
            'planned_cumulative_rotation_rad'],
        'action_waypoints': list(action['waypoints']),
        'action_frames': ACTION_FRAMES,
        'target_segment_radius_m': TARGET_SEGMENT_RADIUS_M,
        'target_state_count': TARGET_STATE_COUNT,
        'target_anchor_max_distance_m': TARGET_ANCHOR_MAX_DISTANCE_M,
        'target_anchor_heading_tolerance_rad': TARGET_ANCHOR_HEADING_TOLERANCE_RAD,
        'target_anchor_heading_weight': TARGET_ANCHOR_HEADING_WEIGHT,
        'minimum_history_node_count': MINIMUM_HISTORY_NODE_COUNT,
        'target_reached_radius_m': TARGET_REACHED_RADIUS_M,
        'goal_position_tolerance_m': GOAL_POSITION_TOLERANCE_M,
        'goal_heading_tolerance_rad': GOAL_HEADING_TOLERANCE_RAD,
        'gt_position_tolerance_m': GT_POSITION_TOLERANCE_M,
        'gt_heading_tolerance_rad': GT_HEADING_TOLERANCE_RAD,
        'goal_settle_s': GOAL_SETTLE_S,
        'history_hold_s': HISTORY_HOLD_S,
        'arrival_hold_s': ARRIVAL_HOLD_S,
        'action_finish_hold_s': ACTION_FINISH_HOLD_S,
        'move_timeout_s': MOVE_TIMEOUT_S,
        'action_phase_timeout_s': ACTION_PHASE_TIMEOUT_S,
        # Observation-only instrumentation, identical in every arm.
        'provenance_enabled': True,
        'observer_enabled': True,
        'diagnostics_enabled': False,
        'instrumentation_flush_period_s': 0.0,
        'record_stream': True,
        'tsp_seed': 44000 + sequence,
    }
    return spec


def action_goals(spec, anchor_xy_theta, reference_gt_pose):
    """Ordered goals for the action phase.

    ``anchor_xy_theta`` is the arrival pose in the mapper frame, i.e. the pose
    the probe reached before the action begins; ``reference_gt_pose`` is the
    matching ground-truth pose.  Every goal keeps the position fixed and only
    changes the heading: this makes the action a pure observation-direction
    change, and the return leg of the last waypoint brings the robot back to
    ``theta0``.
    """
    x, y, theta0 = (float(value) for value in anchor_xy_theta)
    gx, gy, gt_theta0 = (float(value) for value in reference_gt_pose)
    goals = []
    for index, fraction in enumerate(spec['action_waypoints']):
        yaw = theta0 + float(fraction) * float(spec['max_abs_yaw_rad'])
        gt_yaw = gt_theta0 + float(fraction) * float(spec['max_abs_yaw_rad'])
        label = 'action_{}_wp{}'.format(spec['action_id'].replace('+', 'p')
                                        .replace('-', 'm'), index + 1)
        goals.append((x, y, wrap_angle(yaw), label,
                      [gx, gy, wrap_angle(gt_yaw)]))
    return goals


def wrap_angle(value):
    return math.atan2(math.sin(float(value)), math.cos(float(value)))


def select_target_states(segment, count=TARGET_STATE_COUNT):
    """Pick ``count`` target states from a contiguous segment by arc length.

    The rule is fixed and outcome-blind: walk the segment in state order,
    accumulate Euclidian arc length, and take the states closest to the
    quantiles ``i / (count - 1)``.  Returns the selected node records.
    """
    if len(segment) < count:
        return list(segment)
    positions = []
    for index, node in enumerate(segment):
        if index == 0:
            positions.append(0.0)
            continue
        previous = segment[index - 1]
        positions.append(positions[-1] + math.hypot(
            float(node['x']) - float(previous['x']),
            float(node['y']) - float(previous['y'])))
    total = positions[-1]
    if total <= 0.0:
        return list(segment[:count])
    selected = []
    used = set()
    for step in range(count):
        quantile = total * step / float(count - 1)
        best_index = min(range(len(segment)),
                         key=lambda i: abs(positions[i] - quantile))
        while best_index in used and best_index + 1 < len(segment):
            best_index += 1
        used.add(best_index)
        selected.append(segment[best_index])
    return selected
