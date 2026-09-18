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
COMMON_PREFIX_PROTOCOL_VERSION = 'p1_common_prefix_v9'


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

# Additional historical regions on the same frozen route.  They exist so the
# N1-A offline screen has a candidate set with more than one local geometry; the
# route itself, the map and every tolerance stay frozen.  The index selects the
# history waypoint whose neighbourhood becomes the historical region.
_TARGET_EXTRA_WAYPOINTS = {
    'map3_grid_anchor_02': 2,
    'map3_grid_anchor_03': 1,
    'map3_grid_anchor_04': 3,
}
for _extra_id, _waypoint_index in _TARGET_EXTRA_WAYPOINTS.items():
    _extra = copy.deepcopy(TARGETS['map3_grid_anchor_01'])
    _extra['target_history_waypoint_index'] = _waypoint_index
    _extra['candidate_region_waypoint_index'] = _waypoint_index
    TARGETS[_extra_id] = _extra
TARGETS['map3_grid_anchor_01']['candidate_region_waypoint_index'] = 0

# The frozen preflight/screening profiles must keep their original size: the
# additional historical regions exist only for the explicit direction-decision
# profiles, which pass their target ids in from the frozen preregistration.
DEFAULT_TARGET_IDS = ['map3_grid_anchor_01']


def _condition(condition_id, delta_yaw_deg, offset_m, maneuver, diagnostics):
    return {
        'condition_id': condition_id,
        'delta_yaw_deg': float(delta_yaw_deg),
        'lateral_offset_m': float(offset_m),
        'maneuver_type': maneuver,
        'diagnostics_enabled': bool(diagnostics),
        'provenance_enabled': True,
        'neutral_offset_m': 0.0,
    }


PREFLIGHT_CONDITIONS = [
    _condition('baseline_diag_off', 0, 0.0, 'pass', False),
    _condition('baseline_diag_on', 0, 0.0, 'pass', True),
    _condition('align60_diag_on', 60, 0.0, 'align', True),
    _condition('sweep90_diag_on', 90, 0.0, 'sweep', True),
]

# ---------------------------------------------------------------------------
# 2026-09-16 direction-decision experiment (N0 instrumentation validity and
# N1-B budget-matched action intervention).  The frozen preflight above is
# untouched; these are additive profiles with explicit per-episode seeds so a
# matched block shares one TSP seed (the defect of the earlier OFF/ON pair was
# seed confounding: 31000 + sequence).
# ---------------------------------------------------------------------------

N0_INSTRUMENT_ARMS = [
    # (condition_id, diagnostics, provenance, neutral_offset_m)
    ('n0_instr_off', False, False, 0.0),
    ('n0_prov_on', False, True, 0.0),
    ('n0_prov_diag_on', True, True, 0.0),
]

N0_SEEDS = [41001, 41002, 41003]
# Latin-square arm order per seed: every arm occupies every position once.
N0_ARM_ORDERS = [
    ['n0_instr_off', 'n0_prov_on', 'n0_prov_diag_on'],
    ['n0_prov_diag_on', 'n0_instr_off', 'n0_prov_on'],
    ['n0_prov_on', 'n0_prov_diag_on', 'n0_instr_off'],
]

# N1-B action conditions at a fixed sensing/motion budget target.
#   A0 baseline  : the frozen Graph-Based active revisit execution
#   A1 neutral   : budget-matched neutral translation (away-and-back along the
#                  arrival heading) - same scan-addition opportunity as A2's
#                  three 30 deg rotations, but no deliberate yaw sweep
#   A2 sweep90   : the frozen 90 deg sensing sweep (±30 deg at the anchor)
N1_ACTIONS = [
    ('n1_a0_baseline', 0.0, 'pass', False, True, 0.0),
    ('n1_a1_neutral', 0.0, 'neutral', False, True, 1.5),
    ('n1_a2_sweep90', 90.0, 'sweep', False, True, 0.0),
]

N1_TARGET_SEEDS = {
    # two matched blocks per target, each with its own shared seed
    0: [42001, 42002],
    1: [42003, 42004],
}

# Balanced action order per block position (4 blocks x 3 actions).
N1_BLOCK_ORDERS = [
    ['n1_a0_baseline', 'n1_a1_neutral', 'n1_a2_sweep90'],
    ['n1_a2_sweep90', 'n1_a0_baseline', 'n1_a1_neutral'],
    ['n1_a1_neutral', 'n1_a2_sweep90', 'n1_a0_baseline'],
    ['n1_a0_baseline', 'n1_a2_sweep90', 'n1_a1_neutral'],
]


def _n0_specs(target_id):
    episodes = []
    arm_by_id = {arm[0]: arm for arm in N0_INSTRUMENT_ARMS}
    for block_index, seed in enumerate(N0_SEEDS):
        order = N0_ARM_ORDERS[block_index]
        for position, arm_id in enumerate(order):
            condition_id, diagnostics, provenance, neutral = arm_by_id[arm_id]
            spec = copy.deepcopy(TARGETS[target_id])
            spec.update({
                'protocol_version': PROTOCOL_VERSION,
                'target_id': target_id,
                'condition_id': condition_id,
                'delta_yaw_deg': 0.0,
                'lateral_offset_m': 0.0,
                'maneuver_type': 'pass',
                'neutral_offset_m': neutral,
                'diagnostics_enabled': diagnostics,
                'provenance_enabled': provenance,
                'tsp_seed': seed,
                'block_id': 'n0_seed{}'.format(seed),
                'block_position': position,
                'repeat': path_position_repeat(position),
                'sequence': len(episodes) + 1,
                'episode_id': '{:04d}_{}_s{}'.format(
                    len(episodes) + 1, condition_id, seed),
            })
            episodes.append(spec)
    return episodes


def _n1_specs(target_ids):
    episodes = []
    action_by_id = {action[0]: action for action in N1_ACTIONS}
    target_by_id = {target_id: TARGETS[target_id] for target_id in target_ids}
    for target_index, target_id in enumerate(target_ids):
        for block_offset, seed in enumerate(N1_TARGET_SEEDS.get(target_index, [])):
            block_order_index = target_index * 2 + block_offset
            order = N1_BLOCK_ORDERS[block_order_index % len(N1_BLOCK_ORDERS)]
            for position, action_id in enumerate(order):
                condition_id, yaw, maneuver, diagnostics, provenance, neutral = \
                    action_by_id[action_id]
                spec = copy.deepcopy(target_by_id[target_id])
                spec.update({
                    'protocol_version': PROTOCOL_VERSION,
                    'target_id': target_id,
                    'condition_id': condition_id,
                    'action_id': action_id,
                    'delta_yaw_deg': yaw,
                    'lateral_offset_m': 0.0,
                    'maneuver_type': maneuver,
                    'neutral_offset_m': neutral,
                    'diagnostics_enabled': diagnostics,
                    'provenance_enabled': provenance,
                    'tsp_seed': seed,
                    'block_id': 'n1_{}_seed{}'.format(target_id, seed),
                    'block_position': position,
                    'repeat': path_position_repeat(position),
                    'sequence': len(episodes) + 1,
                    'episode_id': '{:04d}_{}_{}'.format(
                        len(episodes) + 1, condition_id, target_id[-2:]),
                })
                episodes.append(spec)
    return episodes


def _common_prefix_v9_specs(target_id):
    """One canonical history capture; no probe is executed in this profile."""
    spec = copy.deepcopy(TARGETS[target_id])
    spec.update({
        'protocol_version': COMMON_PREFIX_PROTOCOL_VERSION,
        'target_id': target_id,
        'condition_id': 'v9_canonical_history',
        'action_id': 'history_only',
        'delta_yaw_deg': 0.0,
        'lateral_offset_m': 0.0,
        'maneuver_type': 'pass',
        'neutral_offset_m': 0.0,
        'diagnostics_enabled': False,
        'provenance_enabled': True,
        'observer_enabled': True,
        'instrumentation_flush_period_s': 0.0,
        'tsp_seed': 43001,
        'block_id': 'v9_common_prefix_map3_grid_anchor_01',
        'block_position': 0,
        'repeat': 1,
        'sequence': 1,
        'episode_id': '0001_v9_canonical_history_anchor_01',
        'record_replay_stream': True,
        'stop_after_history': True,
    })
    return [spec]


def path_position_repeat(position):
    """Bookkeeping only: block position is the balanced-order slot, not a repeat."""
    return int(position) + 1


# ---------------------------------------------------------------------------
# 2026-09-17 instrumentation repair (N0-R).
#
# The first N0 round could not certify the instrument: the instrumented arms
# produced a small but sign-consistent offset in graph-size and local-constraint
# counts.  The repair removes every serialization and file-write operation from
# the constraint-creation path; this profile is the small online sanity check
# that must pass before the same-input replay certification.
#
# Two conditions, alternating order per seed, same seed inside a block:
#   n0r_observer_off_provenance_off  - graph observer ON, provenance OFF
#   n0r_buffered_provenance_on       - graph observer ON, buffered provenance ON
# The graph observer stays enabled in both arms because the measurement of the
# pre-probe graph (and therefore the target freeze gate) depends on it; the
# observer's own effect is therefore outside this profile and is documented as
# such.
# ---------------------------------------------------------------------------

N0R_INSTRUMENT_ARMS = [
    # (condition_id, diagnostics, provenance, observer)
    ('n0r_provenance_off', False, False, True),
    ('n0r_buffered_provenance_on', False, True, True),
]

N0R_SEEDS = [41001, 41002]

N0R_ARM_ORDERS = [
    ['n0r_provenance_off', 'n0r_buffered_provenance_on'],
    ['n0r_buffered_provenance_on', 'n0r_provenance_off'],
]

# A third configuration the mapper supports but this profile does not run: with
# the graph observer disabled there is no pose graph to freeze a target against,
# so no scientific episode can be executed.  It is recorded here so the
# limitation is explicit rather than implicit.
N0R_UNRUNNABLE_CONFIGURATION = {
    'observer': False,
    'provenance': False,
    'reason': 'without the graph observer the driver cannot freeze a target or '
              'measure the pre-probe graph, so no episode outcome exists',
}


def _replay_source_specs(target_id):
    """One recording episode whose only product is the mapper input stream.

    Its outcomes are not used in any comparison: the same-input replay compares
    two replays of this stream against each other.  The graph observer and the
    provenance instrument are irrelevant here, so the instrument is disabled to
    keep the recording run as plain as possible.
    """
    spec = copy.deepcopy(TARGETS[target_id])
    spec.update({
        'protocol_version': PROTOCOL_VERSION,
        'target_id': target_id,
        'condition_id': 'replay_source',
        'delta_yaw_deg': 0.0,
        'lateral_offset_m': 0.0,
        'maneuver_type': 'pass',
        'neutral_offset_m': 0.0,
        'diagnostics_enabled': False,
        'provenance_enabled': False,
        'observer_enabled': True,
        'record_replay_stream': True,
        'tsp_seed': 43001,
        'block_id': 'replay_source',
        'block_position': 0,
        'repeat': 1,
        'sequence': 1,
        'episode_id': '0001_replay_source',
    })
    return [spec]


#: Seeds added by the pre-registered extension of the N0-R block.  No target,
#: maneuver, instrument configuration, outcome or threshold changes; only the
#: number of seed pairs grows, so a same-direction shift either persists or it
#: does not.
N0R_EXTENSION_SEEDS = [41003, 41004]


def _n0r_specs(target_id, seeds=None):
    episodes = []
    seeds = list(seeds) if seeds else list(N0R_SEEDS)
    arm_by_id = {arm[0]: arm for arm in N0R_INSTRUMENT_ARMS}
    for block_index, seed in enumerate(seeds):
        for position, arm_id in enumerate(
                N0R_ARM_ORDERS[block_index % len(N0R_ARM_ORDERS)]):
            condition_id, diagnostics, provenance, observer = arm_by_id[arm_id]
            spec = copy.deepcopy(TARGETS[target_id])
            spec.update({
                'protocol_version': PROTOCOL_VERSION,
                'target_id': target_id,
                'condition_id': condition_id,
                'delta_yaw_deg': 0.0,
                'lateral_offset_m': 0.0,
                'maneuver_type': 'pass',
                'neutral_offset_m': 0.0,
                'diagnostics_enabled': diagnostics,
                'provenance_enabled': provenance,
                'observer_enabled': observer,
                # Zero I/O during the run: records are buffered on the
                # constraint-creation path and serialized only at shutdown.
                'instrumentation_flush_period_s': 0.0,
                'tsp_seed': seed,
                'block_id': 'n0r_seed{}'.format(seed),
                'block_position': position,
                'repeat': path_position_repeat(position),
                'sequence': len(episodes) + 1,
                'episode_id': '{:04d}_{}_s{}'.format(
                    len(episodes) + 1, condition_id, seed),
            })
            episodes.append(spec)
    return episodes


def episode_specs(profile='preflight', repeats=1, target_ids=None):
    if profile in ('preflight', 'screening'):
        return episode_specs_legacy(profile, repeats, target_ids)
    if profile == 'n0_matched':
        selected = list(target_ids) if target_ids else list(DEFAULT_TARGET_IDS)
        return _n0_specs(selected[0])
    if profile == 'n0r_sanity':
        selected = list(target_ids) if target_ids else list(DEFAULT_TARGET_IDS)
        return _n0r_specs(selected[0])
    if profile == 'n0r_extension':
        selected = list(target_ids) if target_ids else list(DEFAULT_TARGET_IDS)
        return _n0r_specs(selected[0], seeds=N0R_EXTENSION_SEEDS)
    if profile == 'replay_source':
        selected = list(target_ids) if target_ids else list(DEFAULT_TARGET_IDS)
        return _replay_source_specs(selected[0])
    if profile == 'n1_blocks':
        selected = list(target_ids) if target_ids else sorted(TARGETS)[:2]
        if len(selected) != 2:
            raise ValueError('n1_blocks needs exactly two target ids')
        return _n1_specs(list(selected))
    if profile == 'common_prefix_v9':
        selected = target_ids or DEFAULT_TARGET_IDS
        if list(selected) != ['map3_grid_anchor_01']:
            raise ValueError('common_prefix_v9 is frozen to map3_grid_anchor_01')
        return _common_prefix_v9_specs('map3_grid_anchor_01')
    raise ValueError('unknown profile: {}'.format(profile))


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


def episode_specs_legacy(profile='preflight', repeats=1, target_ids=None):
    """Legacy generator retained for the frozen preflight profiles."""
    conditions = PREFLIGHT_CONDITIONS if profile == 'preflight' else screening_conditions()
    selected = list(target_ids) if target_ids else list(DEFAULT_TARGET_IDS)
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
                    'tsp_seed': 31000 + sequence,
                    'episode_id': '{:04d}_{}_r{:02d}'.format(
                        sequence, condition['condition_id'], repeat),
                })
                episodes.append(spec)
    return episodes
