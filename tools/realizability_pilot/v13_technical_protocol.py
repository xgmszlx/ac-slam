#!/usr/bin/python3
"""Frozen v13-T technical-certification protocol (no science endpoints)."""

import copy
from pathlib import Path

import confirmatory_v12_protocol as v12
from protocol import TARGETS


PROTOCOL_ID = 'p1_v13_technical_20260920'
ROOT = Path(__file__).resolve().parents[2]
RESULT_ROOT = ROOT / 'results/realizability_pilot' / PROTOCOL_ID
TARGET_IDS = {'target_A': 'map3_grid_anchor_01',
              'target_B': 'map3_grid_anchor_03'}
CANDIDATE_SEEDS = {
    'target_A': [81001, 81002, 81003, 81004,
                 81005, 81006, 81007, 81008],
    'target_B': [82001, 82002, 82003, 82004,
                 82005, 82006, 82007, 82008],
}
PREFIX_REPEAT_COUNT = 3
PREFIX_RATE_HZ = 20.0
TARGET_QUANTILES = [0.1, 0.3, 0.5, 0.7, 0.9]
SEGMENT_HALF_WIDTH_STATES = 10
FROZEN_NUMERICAL_TOLERANCE = {
    'node_translation_max_m': 0.0,
    'node_heading_max_rad': 0.0,
    'edge_translation_measurement_max_m': 0.0,
    'edge_heading_measurement_max_rad': 0.0,
    'edge_covariance_max_abs': 0.0,
}


def history_spec(target_label, seed):
    if int(seed) not in CANDIDATE_SEEDS[target_label]:
        raise ValueError('seed is not in the immutable v13 candidate pool')
    target_id = TARGET_IDS[target_label]
    spec = copy.deepcopy(TARGETS[target_id])
    episode_id = 'v13T_{}_s{}'.format(target_label, int(seed))
    spec.update({
        'protocol_version': PROTOCOL_ID,
        'target_id': target_id,
        'condition_id': 'v13T_history_qualification_only',
        'action_id': 'history_only',
        'delta_yaw_deg': 0.0,
        'lateral_offset_m': 0.0,
        'maneuver_type': 'pass',
        'neutral_offset_m': 0.0,
        'diagnostics_enabled': False,
        'provenance_enabled': True,
        'observer_enabled': True,
        'instrumentation_flush_period_s': 0.0,
        'tsp_seed': int(seed),
        'block_id': episode_id,
        'block_position': 0,
        'repeat': 1,
        'sequence': 1,
        'episode_id': episode_id,
        'record_replay_stream': True,
        'stop_after_history': True,
    })
    return spec


def action_budget_provenance():
    """v13-T records the frozen v12b budget; it does not recalibrate it."""
    source = (ROOT / 'results/realizability_pilot/'
              'p1_confirmatory_v12b_20260918/preregistration/'
              'target_specific_budget_preregistration.json')
    return {
        'source': str(source),
        'reuse_rule': ('reuse v12b target-specific dwell durations because '
                       'target identities and physical waypoint regions are '
                       'unchanged; no v13 outcome-based recalibration'),
    }
