#!/usr/bin/python3
"""Frozen definitions for the v12 confirmatory mechanism experiment.

This module is intentionally free of Karto outcome inspection.  It creates the
preregistration, resolves the five physical target references against a fresh
history, and constructs the three physical action specifications.
"""

import copy
import hashlib
import json
import math
from pathlib import Path

from controlled_branch_suite import atomic_json
from frame_gauge_audit import estimate_se2, transform_pose, wrap_angle
from protocol import TARGETS


PROTOCOL_ID = 'p1_confirmatory_v12_20260917'
ROOT = Path(__file__).resolve().parents[2]
RESULT_ROOT = ROOT / 'results/realizability_pilot' / PROTOCOL_ID
ARMS = ('A1_DWELL', 'A3_MIN_TRIGGER', 'A2_SWEEP90')
PRIMARY_SEEDS = {
    'target_A': [51001, 51002, 51003, 51004],
    'target_B': [52001, 52002, 52003, 52004],
}
RESERVE_SEEDS = {
    'target_A': [51005, 51006],
    'target_B': [52005, 52006],
}
ARM_ORDERS = {
    'target_A': [
        ['A1_DWELL', 'A3_MIN_TRIGGER', 'A2_SWEEP90'],
        ['A3_MIN_TRIGGER', 'A2_SWEEP90', 'A1_DWELL'],
        ['A2_SWEEP90', 'A1_DWELL', 'A3_MIN_TRIGGER'],
        ['A1_DWELL', 'A2_SWEEP90', 'A3_MIN_TRIGGER'],
    ],
    'target_B': [
        ['A3_MIN_TRIGGER', 'A1_DWELL', 'A2_SWEEP90'],
        ['A2_SWEEP90', 'A3_MIN_TRIGGER', 'A1_DWELL'],
        ['A1_DWELL', 'A3_MIN_TRIGGER', 'A2_SWEEP90'],
        ['A3_MIN_TRIGGER', 'A2_SWEEP90', 'A1_DWELL'],
    ],
}
TARGET_IDS = {'target_A': 'map3_grid_anchor_01',
              'target_B': 'map3_grid_anchor_03'}
ANCHOR_REFERENCE_INDEX = {'target_A': 2, 'target_B': 1}
POSITION_TOLERANCE_M = 0.60
HEADING_TOLERANCE_RAD = 0.25
START_POSITION_TOLERANCE_M = 0.08
START_HEADING_TOLERANCE_RAD = 0.04
A1_DWELL_S = 7.6
A3_ANGLE_RAD = 0.5439732814124923
BUDGET_GATES = {'pairwise_distance_range_m_max': 0.10,
                'pairwise_time_range_s_max': 1.5,
                'raw_scan_relative_range_max': 0.03}
MAX_HISTORY_ATTEMPTS_PER_SEED = 2
MAX_BRANCH_ATTEMPTS = 2


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_tum(path):
    rows = []
    with open(path) as stream:
        for line in stream:
            if line.strip():
                values = [float(value) for value in line.split()]
                rows.append(values)
    return rows


def tum_yaw(row):
    return 2.0 * math.atan2(float(row[6]), float(row[7]))


def stage_states(attempt_dir):
    """Join Karto state row order to Stage GT using the exact scan timestamp."""
    attempt_dir = Path(attempt_dir)
    slam = read_tum(attempt_dir / 'trajectory_slam.txt')
    gt = {round(row[0], 6): row for row in read_tum(
        attempt_dir / 'trajectory_gt.txt')}
    rows = []
    for state_id, state in enumerate(slam):
        truth = gt.get(round(state[0], 6))
        if truth is None:
            continue
        rows.append({'state_id': state_id, 'stamp': state[0],
                     'pose': [truth[1], truth[2], tum_yaw(truth)]})
    return rows


def target_references():
    source_a = (ROOT / 'results/realizability_pilot/'
                'p1_dwell_control_v10_20260917/target_physical_region.json')
    data_a = json.loads(source_a.read_text())
    refs_a = [row['stage_gt_base_pose'] for row in data_a['mappings']]

    source_b_dir = (ROOT / 'results/realizability_pilot/'
                    'p1_dir_dec_v8_20260916/n1_blocks/episodes/'
                    '0007_n1_a1_neutral_03/attempt_01')
    states_b = {row['state_id']: row for row in stage_states(source_b_dir)}
    selected_b = [29, 30, 31, 32, 33]
    refs_b = [states_b[state_id]['pose'] for state_id in selected_b]
    return {
        'target_A': {
            'target_id': TARGET_IDS['target_A'], 'q': refs_a,
            'source': str(source_a), 'source_sha256': sha256(source_a),
            'selection_rule': 'all five already verified v10 physical scans',
            'source_state_ids': data_a['target_scan_ids'],
        },
        'target_B': {
            'target_id': TARGET_IDS['target_B'], 'q': refs_b,
            'source': str(source_b_dir),
            'source_episode_result_sha256': sha256(
                source_b_dir / 'episode_result.json'),
            'selection_rule': ('five consecutive historical states 29--33: '
                               'the five nearest old pre-probe states to the '
                               'physical anchor, then restored to route order'),
            'source_state_ids': selected_b,
        },
    }


def preregistration_payload(a3_dwell_s=None, calibration=None):
    code_files = [Path(__file__).resolve(),
                  Path(__file__).with_name('confirmatory_v12_collection.py'),
                  Path(__file__).with_name('confirmatory_v12_analysis.py')]
    payload = {
        'protocol_id': PROTOCOL_ID,
        'created_before_formal_branch_collection': True,
        'targets': target_references(),
        'primary_history_seeds': PRIMARY_SEEDS,
        'reserve_history_seeds': RESERVE_SEEDS,
        'reserve_rule': ('consume in listed order only after '
                         'TECHNICAL_INVALID_HISTORY; never replace an outcome'),
        'arm_orders': ARM_ORDERS,
        'arms': {
            'A1_DWELL': {'dwell_s': A1_DWELL_S, 'geometry': 'static'},
            'A3_MIN_TRIGGER': {
                'angle_rad': A3_ANGLE_RAD, 'dwell_s': a3_dwell_s,
                'geometry': 'theta0 -> theta0+angle -> theta0 then dwell',
                'keyscan_count_is_mediator_not_validity_gate': True,
            },
            'A2_SWEEP90': {'geometry': 'frozen v9/v10 Sweep90'},
        },
        'target_match': {
            'algorithm': 'global minimum-cost strictly monotonic assignment',
            'cost': 'sum(position_m^2 + (0.5*heading_rad)^2)',
            'position_tolerance_m': POSITION_TOLERANCE_M,
            'heading_tolerance_rad': HEADING_TOLERANCE_RAD,
            'exact_state_count': 5,
            'allowed_inputs': ['Stage GT physical position', 'heading',
                               'Karto state order'],
        },
        'primary_estimand': {
            'subset': 'five fixed prefix SE(2) states', 'dimension': 15,
            'J_T': '-logdet(Sigma_T)/15',
            'primary_contrast': 'J_T(A2_SWEEP90)-J_T(A3_MIN_TRIGGER)',
            'secondary_contrasts': [
                'J_T(A3_MIN_TRIGGER)-J_T(A1_DWELL)',
                'J_T(A2_SWEEP90)-J_T(A1_DWELL)'],
        },
        'support_rule': ('at least 7/8 positive, target_A at least 3/4, '
                         'target_B at least 3/4'),
        'budget_gates': BUDGET_GATES,
        'start_gate': {'position_m_max': START_POSITION_TOLERANCE_M,
                       'heading_rad_max': START_HEADING_TOLERANCE_RAD},
        'technical_attempt_caps': {
            'history_per_seed': MAX_HISTORY_ATTEMPTS_PER_SEED,
            'branch_per_assignment': MAX_BRANCH_ATTEMPTS},
        'no_peeking': {
            'collection_allowed': ['technical status', 'start pose',
                                   'action execution', 'GT distance', 'time',
                                   'raw scan count', 'prefix hash'],
            'forbidden_until_collection_complete': [
                'accepted keyscans', 'constraints', 'utility', 'posterior',
                'arm contrasts'],
        },
        'calibration': calibration,
        'code_hashes': {str(path.relative_to(ROOT)): sha256(path)
                        for path in code_files if path.is_file()},
    }
    return payload


def history_spec(target_label, seed, episode_id):
    spec = copy.deepcopy(TARGETS[TARGET_IDS[target_label]])
    spec.update({
        'protocol_version': PROTOCOL_ID, 'target_id': TARGET_IDS[target_label],
        'condition_id': 'v12_canonical_history', 'action_id': 'history_only',
        'delta_yaw_deg': 0.0, 'lateral_offset_m': 0.0,
        'maneuver_type': 'pass', 'neutral_offset_m': 0.0,
        'diagnostics_enabled': False, 'provenance_enabled': True,
        'observer_enabled': True, 'instrumentation_flush_period_s': 0.0,
        'tsp_seed': int(seed), 'block_id': episode_id, 'block_position': 0,
        'repeat': 1, 'sequence': 1, 'episode_id': episode_id,
        'record_replay_stream': True, 'stop_after_history': True,
    })
    return spec


def angle_distance(left, right):
    return abs(wrap_angle(float(left) - float(right)))


def monotonic_target_assignment(references, states, route_start_node_count):
    candidates = [row for row in states
                  if int(row['state_id']) >= int(route_start_node_count)]
    if len(candidates) < len(references):
        raise ValueError('fewer candidate history states than references')
    # Dynamic programming gives the same global optimum as enumerating all
    # combinations while keeping the runtime linear in references*candidates.
    previous = {}
    for reference_index, q in enumerate(references):
        current = {}
        best_prefix = None
        for candidate_index, state in enumerate(candidates):
            if reference_index:
                prior = previous.get(candidate_index - 1)
                if prior is not None and (best_prefix is None or
                                          prior[0] < best_prefix[0]):
                    best_prefix = prior
                if best_prefix is None:
                    continue
            pose = state['pose']
            position = math.hypot(float(q[0]) - pose[0], float(q[1]) - pose[1])
            heading = angle_distance(q[2], pose[2])
            if (position > POSITION_TOLERANCE_M or
                    heading > HEADING_TOLERANCE_RAD):
                continue
            row = {'reference_index': reference_index, 'q': q,
                   'state_id': state['state_id'], 'stamp': state['stamp'],
                   'stage_gt_pose': pose, 'position_error_m': position,
                   'heading_error_rad': heading}
            base_cost, base_path = (best_prefix if reference_index else
                                    (0.0, []))
            current[candidate_index] = (
                base_cost + position ** 2 + (0.5 * heading) ** 2,
                base_path + [row])
        previous = current
    if not previous:
        raise ValueError('TARGET_REFERENCE_MATCH_INVALID')
    best = min(previous.values(), key=lambda item: item[0])
    return {'status': 'TARGET_REFERENCE_MATCH_VALID',
            'total_cost': best[0], 'matches': best[1],
            'historical_scan_ids': [row['state_id'] for row in best[1]],
            'historical_unique_ids': [row['state_id'] for row in best[1]],
            'exact_state_count': len(best[1]),
            'position_tolerance_m': POSITION_TOLERANCE_M,
            'heading_tolerance_rad': HEADING_TOLERANCE_RAD,
            'outcome_blind': True}


def freeze_target(attempt_dir, target_label, output_path):
    attempt_dir = Path(attempt_dir)
    result = json.loads((attempt_dir / 'episode_result.json').read_text())
    old_frozen = json.loads((attempt_dir / 'frozen_target.json').read_text())
    refs = target_references()[target_label]
    assignment = monotonic_target_assignment(
        refs['q'], stage_states(attempt_dir), old_frozen['route_start_node_count'])
    nodes = {int(row['id']): row for row in old_frozen.get('segment_nodes', [])}
    # The replay tools only need historical ids, but retaining the original
    # Karto poses makes the selected prefix subset independently auditable.
    slam_rows = read_tum(attempt_dir / 'trajectory_slam.txt')
    selected_nodes = []
    for state_id in assignment['historical_scan_ids']:
        if state_id in nodes:
            selected_nodes.append(nodes[state_id])
        else:
            row = slam_rows[state_id]
            selected_nodes.append({'id': state_id, 'unique_id': state_id,
                                   'observed_time': row[0], 'x': row[1],
                                   'y': row[2], 'theta': tum_yaw(row)})
    anchor = selected_nodes[ANCHOR_REFERENCE_INDEX[target_label]]
    payload = dict(assignment)
    payload.update({
        'target_label': target_label, 'target_id': refs['target_id'],
        'reference_definition': refs, 'segment_nodes': selected_nodes,
        'anchor_scan': anchor,
        'anchor_reference_index': ANCHOR_REFERENCE_INDEX[target_label],
        'route_start_node_count': old_frozen['route_start_node_count'],
        'frozen_before_probe': True,
        'source_history_result': str(attempt_dir / 'episode_result.json'),
        'canonical_history_complete': result.get('canonical_history_complete'),
    })
    atomic_json(Path(output_path), payload)
    return payload


def action_specs(attempt_dir, frozen_target, a3_dwell_s):
    attempt_dir = Path(attempt_dir)
    result = json.loads((attempt_dir / 'episode_result.json').read_text())
    history = [move for move in result['moves']
               if move['label'].startswith('history_')]
    rotation, translation = estimate_se2(
        [move['tf_pose_after'][:2] for move in history],
        [move['gt_pose_after'][:2] for move in history])
    anchor = frozen_target['anchor_scan']
    anchor_map = [anchor['x'], anchor['y'], anchor['theta']]
    anchor_world = transform_pose(anchor_map, rotation, translation)
    terminal = result['terminal_gt_pose']
    setup = [move['gt_pose_after'] for move in history[:-1]] + [terminal]
    target_index = int(TARGETS[frozen_target['target_id']]
                       ['target_history_waypoint_index'])
    approach_indices = list(range(len(history) - 2, target_index, -1))
    approach = []
    labels = []
    for index in approach_indices:
        pose = list(history[index]['gt_pose_after'])
        next_pose = (anchor_world if index == target_index + 1 else
                     history[index - 1]['gt_pose_after'])
        pose[2] = math.atan2(next_pose[1] - pose[1], next_pose[0] - pose[0])
        approach.append(pose)
        labels.append('probe_approach_history_{:02d}'.format(index + 1))
    base_waypoints = approach + [anchor_world]
    base_labels = labels + ['probe_arrival']
    peak_map = [anchor_map[0], anchor_map[1],
                wrap_angle(anchor_map[2] + A3_ANGLE_RAD)]
    a3_waypoints = base_waypoints + [
        transform_pose(peak_map, rotation, translation), anchor_world]
    a3_labels = base_labels + ['min_trigger_peak', 'min_trigger_return']
    sweep_maps = [
        [anchor_map[0], anchor_map[1], wrap_angle(anchor_map[2] + math.pi / 2)],
        [anchor_map[0], anchor_map[1], wrap_angle(anchor_map[2] - math.pi / 6)],
        [anchor_map[0], anchor_map[1], anchor_map[2]],
        [anchor_map[0], anchor_map[1], wrap_angle(anchor_map[2] + math.pi / 6)],
    ]
    common = {'setup_waypoints': setup, 'hold_s': 6.0,
              'canonical_terminal_gt_pose': terminal,
              'target_anchor_map': anchor_map,
              'target_anchor_world_by_history_only_se2': anchor_world,
              'T_W_M': {'tx': float(translation[0]),
                        'ty': float(translation[1]),
                        'yaw': math.atan2(rotation[1, 0], rotation[0, 0])}}
    return {
        'common': common,
        'actions': {
            'A1_DWELL': {'action_id': 'A1_DWELL',
                         'action_waypoints': base_waypoints,
                         'action_labels': base_labels, 'dwell_s': A1_DWELL_S,
                         'core_action_start_index': len(approach)},
            'A3_MIN_TRIGGER': {'action_id': 'A3_MIN_TRIGGER',
                               'action_waypoints': a3_waypoints,
                               'action_labels': a3_labels,
                               'dwell_s': float(a3_dwell_s),
                               'core_action_start_index': len(approach),
                               'assigned_angle_rad': A3_ANGLE_RAD},
            'A2_SWEEP90': {'action_id': 'A2_SWEEP90',
                           'action_waypoints': approach + [
                               transform_pose(pose, rotation, translation)
                               for pose in sweep_maps],
                           'action_labels': labels + [
                               'probe_arrival', 'sweep_-30deg',
                               'sweep_+0deg', 'sweep_+30deg'],
                           'dwell_s': 0.0,
                           'core_action_start_index': len(approach)},
        },
    }


def write_initial_preregistration(path):
    path = Path(path)
    if path.exists():
        return json.loads(path.read_text())
    payload = preregistration_payload()
    atomic_json(path, payload)
    return payload
