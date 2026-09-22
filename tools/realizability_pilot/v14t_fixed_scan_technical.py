#!/usr/bin/python3
"""Prepare, run, and close the no-backend v14-T technical certification."""

import argparse
import csv
import json
import math
import os
import re
import signal
import subprocess
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from confirmatory_v13c_protocol import ARM_ORDERS
from controlled_branch_suite import (WORLD, atomic_json, pose_error,
                                     wait_topic)
from mechanism_classifier import constraint_family, is_explicit_try_close_loop
from run_pilot import (activated_environment, command_output, start_process,
                       stop_process)
from v14t_fixed_scan_protocol import (
    ARMS, BASE_COMMIT, BLOCKS, MANEUVER_COMPLETION_LABEL, POSTHOC_ROOT,
    PROTOCOL_ID, RESULT_ROOT, ROOT, START_HEADING_TOLERANCE_RAD,
    START_POSITION_TOLERANCE_M, TARGETS, V13C_ROOT, derive_scan_budget,
    git_head, load_json, protocol_payload, sha256, verify_original_artifacts,
    write_frozen_json,
)


TERMINAL_BRANCH_STATUSES = {
    'TECHNICALLY_VALID', 'TECHNICAL_INVALID_BRANCH_START',
    'TECHNICAL_INVALID_MANEUVER_EXCEEDS_SCAN_BUDGET',
    'TECHNICAL_INVALID_SCIENTIFIC_SCAN_COUNT',
    'TECHNICAL_INVALID_DUPLICATE_TIMESTAMP',
    'TECHNICAL_INVALID_NONMONOTONIC_TIMESTAMP',
    'TECHNICAL_INVALID_SCIENTIFIC_STREAM_CONTAMINATION',
    'CONTROLLER_EXCEPTION',
}


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def write_csv(path, rows):
    rows = list(rows)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with open(path, 'w', newline='') as stream:
        if fields:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)


def read_jsonl(path):
    with open(path) as stream:
        return [json.loads(line) for line in stream if line.strip()]


def read_csv(path):
    with open(path, newline='') as stream:
        return list(csv.DictReader(stream))


def _move_map(result):
    return {row['label']: row for row in result['moves']}


def phase_intervals(result, offset):
    """Return left-closed/right-open intervals in stitched replay time."""
    moves = _move_map(result)
    arm = result['action_id']
    arrival = moves['probe_arrival']
    intervals = []
    first_raw = float(result['probe_start_time']) + offset
    treatment_start = float(arrival['start_time']) + offset
    intervals.append(('PRE_TREATMENT_APPROACH', first_raw, treatment_start))
    if arm == 'A1_DWELL':
        intervals.append(('ARRIVAL', treatment_start,
                          float(arrival['end_time']) + offset))
        dwell = result.get('dwell')
        if dwell:
            intervals.append(('STATIC_DWELL', float(dwell['start_time']) + offset,
                              float(dwell['end_time']) + offset))
            final_start = float(dwell['end_time']) + offset
        else:
            final_start = float(arrival['end_time']) + offset
        intervals.append(('FINAL_HOLD', final_start,
                          float(result['probe_end_time']) + offset))
    elif arm == 'A3_MIN_TRIGGER':
        peak, ret = moves['min_trigger_peak'], moves['min_trigger_return']
        intervals.extend([
            ('ARRIVAL', treatment_start, float(arrival['end_time']) + offset),
            ('MIN_TRIGGER_OUT', float(peak['start_time']) + offset,
             float(peak['end_time']) + offset),
            ('MIN_TRIGGER_RETURN', float(ret['start_time']) + offset,
             float(ret['end_time']) + offset),
        ])
        dwell = result.get('dwell')
        if dwell:
            intervals.append(('STATIC_DWELL', float(dwell['start_time']) + offset,
                              float(dwell['end_time']) + offset))
            final_start = float(dwell['end_time']) + offset
        else:
            final_start = float(ret['end_time']) + offset
        intervals.append(('FINAL_HOLD', final_start,
                          float(result['probe_end_time']) + offset))
    else:
        minus = moves['sweep_-30deg']
        zero = moves['sweep_+0deg']
        plus = moves['sweep_+30deg']
        intervals.extend([
            ('ARRIVAL_PLUS90', treatment_start,
             float(arrival['end_time']) + offset),
            ('SWEEP_90_TO_MINUS30', float(minus['start_time']) + offset,
             float(minus['end_time']) + offset),
            ('SWEEP_MINUS30_TO_0', float(zero['start_time']) + offset,
             float(zero['end_time']) + offset),
            ('SWEEP_0_TO_PLUS30', float(plus['start_time']) + offset,
             float(plus['end_time']) + offset),
            ('FINAL_HOLD_PLUS30', float(plus['end_time']) + offset,
             float(result['probe_end_time']) + offset),
        ])
    return intervals


def assign_phase(timestamp, intervals):
    if timestamp is None:
        return None
    candidates = []
    for index, (name, start, end) in enumerate(intervals):
        final = index == len(intervals) - 1
        if timestamp >= start and (timestamp < end or final and timestamp <= end):
            candidates.append(name)
    if len(candidates) == 1:
        return candidates[0]
    return None


def replay_sources(target, index, arm):
    capture = (V13C_ROOT / target / str(index) / arm /
               'raw_attempt_01/capture_result.json')
    if target == 'target_A':
        replay = V13C_ROOT / target / str(index) / arm / 'replay_attempt_01'
        stitch = capture.parents[1] / 'stitch_report.json'
        block_id = 'target_A_H{}'.format(index)
        mechanism_csv = V13C_ROOT / 'analysis/constraint_mechanism.csv'
    else:
        replay = POSTHOC_ROOT / 'replays/FULL/B-H{}'.format(index) / arm
        stitch = replay / 'stitch_report.json'
        block_id = 'B-H{}'.format(index)
        mechanism_csv = POSTHOC_ROOT / 'analysis/FULL/constraint_mechanism.csv'
    return capture, replay, stitch, block_id, mechanism_csv


def constraint_index():
    output = {}
    for path in (V13C_ROOT / 'analysis/constraint_mechanism.csv',
                 POSTHOC_ROOT / 'analysis/FULL/constraint_mechanism.csv'):
        for row in read_csv(path):
            if path == V13C_ROOT / 'analysis/constraint_mechanism.csv':
                if row['target'] != 'target_A':
                    continue
                block = row['block_id']
            else:
                block = row['block_id']
            output[(block, row['arm'], int(row['edge_index']))] = row
    return output


def _float_or_none(value):
    if value in (None, '', 'None', 'null'):
        return None
    return float(value)


def _number_list(value):
    if value in (None, '', 'None', 'null'):
        return []
    parsed = json.loads(value) if isinstance(value, str) else value
    return [float(item) for item in parsed]


def pre_target_connectivity(capture_path, pre_graph):
    reference = load_json(Path(capture_path).parents[2] / 'prefix_reference.json')
    targets = {int(value) for value in reference['local_five_target_state_ids']}
    edges = pre_graph['edges']
    incident = [row for row in edges if (
        int(row['source_state_id']) in targets or
        int(row['target_state_id']) in targets)]
    internal = [row for row in edges if (
        int(row['source_state_id']) in targets and
        int(row['target_state_id']) in targets)]
    parent = {int(row['state_id']): int(row['state_id'])
              for row in pre_graph['nodes']}

    def find(value):
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    for row in edges:
        left, right = (find(int(row['source_state_id'])),
                       find(int(row['target_state_id'])))
        if left != right:
            parent[right] = left
    components = len({find(value) for value in parent})
    return {
        'target_state_ids': sorted(targets),
        'pre_graph_nodes': len(pre_graph['nodes']),
        'pre_graph_edges': len(edges),
        'pre_graph_connected_components': components,
        'pre_graph_cycle_rank': (
            len(edges) - len(pre_graph['nodes']) + components),
        'pre_target_incident_edges': len(incident),
        'pre_target_internal_edges': len(internal),
        'pre_target_degree_by_state': {
            str(state_id): sum(
                int(row['source_state_id']) == state_id or
                int(row['target_state_id']) == state_id for row in edges)
            for state_id in sorted(targets)},
    }


def phase_forensic(root=RESULT_ROOT):
    root = Path(root)
    indexed_constraints = constraint_index()
    keyscan_rows, factor_rows, branch_summaries = [], [], []
    for target in TARGETS:
        for index in range(1, 5):
            for arm in ARMS:
                capture_path, replay, stitch_path, block_id, _csv = \
                    replay_sources(target, index, arm)
                capture = load_json(capture_path)
                offset = float(load_json(stitch_path)['timestamp_offset_s'])
                intervals = phase_intervals(capture, offset)
                pre = load_json(replay / 'graph_pre.json')
                final = load_json(replay / 'graph_final.json')
                pre_ids = {int(row['state_id']) for row in pre['nodes']}
                final_ids = {int(row['state_id']) for row in final['nodes']}
                new_ids = final_ids - pre_ids
                provenance = read_jsonl(replay / 'edge_provenance.jsonl')
                constraints = [row for row in provenance
                               if row.get('record_type') == 'constraint_created']
                interval_start = min(row[1] for row in intervals)
                interval_end = max(row[2] for row in intervals)
                provenance_times = [float(row['sim_time']) for row in constraints
                                    if row.get('sim_time') is not None]
                timestamp_domains_compatible = bool(provenance_times) and not (
                    max(provenance_times) < interval_start or
                    min(provenance_times) > interval_end)
                times_by_state = defaultdict(set)
                for record in constraints:
                    state_id = record.get('current_keyscan_state_id')
                    if state_id is not None and int(state_id) in new_ids:
                        times_by_state[int(state_id)].add(float(record['sim_time']))
                keyscan_identifiable = (
                    set(times_by_state) == new_ids and
                    all(len(values) == 1 for values in times_by_state.values()))
                for state_id in sorted(new_ids):
                    times = times_by_state.get(state_id, set())
                    provenance_time = next(iter(times)) if len(times) == 1 else None
                    timestamp = provenance_time if timestamp_domains_compatible else None
                    phase = assign_phase(timestamp, intervals)
                    keyscan_rows.append({
                        'target': target, 'block': block_id, 'arm': arm,
                        'state_id': state_id,
                        'provenance_sim_time': provenance_time,
                        'observed_scan_timestamp': timestamp,
                        'phase': phase or 'UNIDENTIFIABLE',
                        'attribution_status': (
                            'IDENTIFIABLE' if keyscan_identifiable and phase else
                            'PHASE_KEYSCAN_ATTRIBUTION_NOT_IDENTIFIABLE'),
                        'timestamp_basis': (
                            'none: graph node has no timestamp and provenance '
                            'sim_time is replay wall-clock time'),
                        'failure_reason': ('' if phase else
                            'NO_AUDITABLE_SCAN_TIMESTAMP_FOR_ACCEPTED_KEYSCAN'),
                    })

                factor_identifiable = True
                selected = []
                for record in constraints:
                    edge_index = int(record['creation_sequence']) - 1
                    key = (block_id, arm, edge_index)
                    if key not in indexed_constraints:
                        continue
                    source = indexed_constraints[key]
                    provenance_time = record.get('sim_time')
                    timestamp = (float(provenance_time)
                                 if provenance_time is not None and
                                 timestamp_domains_compatible else None)
                    phase = assign_phase(timestamp, intervals)
                    if phase is None:
                        factor_identifiable = False
                    row = {
                        'target': target, 'block': block_id, 'arm': arm,
                        'edge_index': edge_index,
                        'source_state': int(source['source']),
                        'target_state': int(source['target_state']),
                        'attribution': source['attribution'],
                        'creation_provenance_sim_time': provenance_time,
                        'creation_scan_timestamp': timestamp,
                        'phase': phase or 'UNIDENTIFIABLE',
                        'attribution_status': (
                            'IDENTIFIABLE' if phase else
                            'PHASE_FACTOR_ATTRIBUTION_NOT_IDENTIFIABLE'),
                        'constraint_family': constraint_family(record),
                        'explicit_try_close_loop':
                            is_explicit_try_close_loop(record),
                        'creation_provenance': record.get('creation_provenance'),
                        'creation_stage': record.get('creation_stage'),
                        'matcher_type': record.get('matcher_type'),
                        'match_response': _float_or_none(
                            source.get('match_response')),
                        'covariance_eigenvalues': source.get(
                            'covariance_eigenvalues'),
                        'information_eigenvalues': source.get(
                            'information_eigenvalues'),
                        'geodesic_at_insertion_m': _float_or_none(
                            source.get('geodesic_at_insertion_m')),
                        'hops_at_insertion': _float_or_none(
                            source.get('hops_at_insertion')),
                        'cycle_length_edges': _float_or_none(
                            source.get('cycle_length_edges')),
                        'failure_reason': ('' if phase else
                            'NO_AUDITABLE_SCAN_TIMESTAMP_FOR_FACTOR_CREATION'),
                    }
                    factor_rows.append(row)
                    selected.append(row)
                expected = sum(
                    key[0] == block_id and key[1] == arm
                    for key in indexed_constraints)
                if len(selected) != expected:
                    factor_identifiable = False
                branch_summaries.append({
                    'target': target, 'block': block_id, 'arm': arm,
                    'new_keyscans': len(new_ids),
                    'mapped_keyscans': len(times_by_state),
                    'keyscan_phase_status': (
                        'IDENTIFIABLE' if keyscan_identifiable and all(
                            row['phase'] != 'UNIDENTIFIABLE'
                            for row in keyscan_rows
                            if row['block'] == block_id and row['arm'] == arm)
                        else 'PHASE_KEYSCAN_ATTRIBUTION_NOT_IDENTIFIABLE'),
                    'new_factors': expected,
                    'mapped_factors': len(selected),
                    'factor_phase_status': (
                        'IDENTIFIABLE' if factor_identifiable else
                        'PHASE_FACTOR_ATTRIBUTION_NOT_IDENTIFIABLE'),
                    'timestamp_domains_compatible': timestamp_domains_compatible,
                    'phase_keyscan_counts': dict(Counter(
                        row['phase'] for row in keyscan_rows
                        if row['block'] == block_id and row['arm'] == arm)),
                    'phase_factor_counts': dict(Counter(
                        row['phase'] for row in selected)),
                })
    write_csv(root / 'analysis/phase_resolved_keyscans.csv', keyscan_rows)
    write_csv(root / 'analysis/phase_resolved_factors.csv', factor_rows)
    status = ('PHASE_ATTRIBUTION_IDENTIFIABLE' if all(
        row['keyscan_phase_status'] == 'IDENTIFIABLE' and
        row['factor_phase_status'] == 'IDENTIFIABLE'
        for row in branch_summaries) else 'PHASE_ATTRIBUTION_PARTIALLY_UNIDENTIFIABLE')
    comparisons = {}
    for block in ('B-H1', 'B-H3'):
        comparisons[block] = {}
        for arm in ('A3_MIN_TRIGGER', 'A2_SWEEP90'):
            rows = [row for row in factor_rows
                    if row['block'] == block and row['arm'] == arm]
            hist = [row for row in rows if row['attribution'] in (
                'E_T_target', 'E_N_nontarget_history')]
            responses = [row['match_response'] for row in hist
                         if row['match_response'] is not None]
            geodesics = [row['geodesic_at_insertion_m'] for row in hist
                         if row['geodesic_at_insertion_m'] is not None]
            hops = [row['hops_at_insertion'] for row in hist
                    if row['hops_at_insertion'] is not None]
            covariance = [value for row in hist
                          for value in _number_list(row['covariance_eigenvalues'])]
            information = [value for row in hist
                           for value in _number_list(row['information_eigenvalues'])]
            comparisons[block][arm] = {
                'factor_count': len(rows),
                'target_historical_count': sum(
                    row['attribution'] == 'E_T_target' for row in rows),
                'nontarget_historical_count': sum(
                    row['attribution'] == 'E_N_nontarget_history' for row in rows),
                'historical_endpoint_pairs': sorted({
                    '{}-{}'.format(row['source_state'], row['target_state'])
                    for row in hist}),
                'phase_counts': dict(Counter(row['phase'] for row in rows)),
                'family_counts': dict(Counter(
                    row['constraint_family'] for row in rows)),
                'match_response_mean': float(np.mean(responses)) if responses else None,
                'geodesic_median_m': float(np.median(geodesics)) if geodesics else None,
                'hops_median': float(np.median(hops)) if hops else None,
                'covariance_eigenvalue_median': (
                    float(np.median(covariance)) if covariance else None),
                'information_eigenvalue_median': (
                    float(np.median(information)) if information else None),
            }
        capture_path, replay, _stitch, _block, _csv = replay_sources(
            'target_B', int(block[-1]), 'A1_DWELL')
        comparisons[block]['pre_existing_target_connectivity'] = \
            pre_target_connectivity(capture_path, load_json(replay / 'graph_pre.json'))
    payload = {
        'status': status,
        'graph_dump_contains_node_timestamps': False,
        'timestamp_basis': (
            'graph nodes lack observed scan timestamps; provenance sim_time is '
            'replay wall-clock time and cannot be exactly mapped to scan time'),
        'boundary_convention': 'left-closed/right-open; final phase closed at end',
        'branch_summaries': branch_summaries,
        'B_H1_vs_B_H3': comparisons,
        'previously_observed_D_sweep_context': {
            'B-H1': 0.008068837161202325,
            'B-H3': 0.3982040704695704,
            'source': ('frozen post-hoc FULL summary; context only, not a new '
                       'v14-T scientific endpoint'),
        },
        'mechanism_hypotheses_not_causal_conclusions': [
            ('factor-count increase alone does not explain the posterior '
             'contrast because A2 adds nine factors over A3 in both blocks'),
            ('B-H3 has lower pre-existing global cycle rank than B-H1 and its '
             'A2 historical constraints differ in endpoints and information; '
             'either could affect marginal information utility'),
            ('action-phase mediation remains untestable from these frozen '
             'artifacts because exact accepted-scan timestamps were not logged'),
        ],
        'interpretation_scope': 'MECHANISM_HYPOTHESES_ONLY',
        'scientific_endpoint_created': False,
    }
    atomic_json(root / 'analysis/phase_resolved_summary.json', payload)
    return payload


def prepare(root=RESULT_ROOT):
    if git_head() != BASE_COMMIT:
        raise RuntimeError('unexpected git base before v14-T freeze')
    root = Path(root)
    (root / 'preregistration').mkdir(parents=True, exist_ok=True)
    budget = derive_scan_budget()
    write_frozen_json(root / 'preregistration/v14T_scan_budget_derivation.json',
                      budget)
    phases = phase_forensic(root)
    protocol = protocol_payload(budget)
    write_frozen_json(root / 'preregistration/v14T_protocol.json', protocol)
    return {
        'status': 'V14T_PREREGISTERED_TECHNICAL_ONLY',
        'M': budget['M'], 'S': budget['S'], 'N': budget['N'],
        'phase_status': phases['status'],
        'protocol_sha256': sha256(root / 'preregistration/v14T_protocol.json'),
        'budget_sha256': sha256(
            root / 'preregistration/v14T_scan_budget_derivation.json'),
        'code_bundle_sha256': protocol['code_bundle_sha256'],
    }


def block_rows():
    rows = []
    for target in TARGETS:
        for index in range(1, 5):
            rows.append({'target': target, 'index': index,
                         'block': '{}-H{}'.format(target[-1], index),
                         'arm_order': ARM_ORDERS[target][index - 1]})
    return rows


def fixed_spec(target, index, arm, n_value):
    payload = load_json(V13C_ROOT / target / str(index) / 'action_specs.json')
    spec = dict(payload['common'], **payload['actions'][arm])
    spec.update({
        'dwell_s': 0.0,
        'hold_s': 0.0,
        'scientific_treatment_scan_budget': int(n_value),
        'protocol_role': 'v14T_fixed_scan_technical_only',
        'backend_started': False,
        'scientific_endpoint_read': False,
        'source_action_specs_path': str((V13C_ROOT / target / str(index) /
                                         'action_specs.json').relative_to(ROOT)),
        'source_action_specs_sha256': sha256(
            V13C_ROOT / target / str(index) / 'action_specs.json'),
    })
    return spec


def run_fixed_stage_capture(env, spec, run_dir):
    run_dir = Path(run_dir)
    if run_dir.exists():
        raise RuntimeError('refusing to overwrite {}'.format(run_dir))
    run_dir.mkdir(parents=True)
    spec_path = run_dir / 'capture_spec.json'
    atomic_json(spec_path, spec)
    local_env = dict(env)
    local_env['ROS_LOG_DIR'] = str(run_dir / 'ros_logs')
    Path(local_env['ROS_LOG_DIR']).mkdir(parents=True)
    roscore = stage = None
    try:
        if command_output(['rosparam', 'list'], local_env, timeout=5).returncode == 0:
            raise RuntimeError('ROS master already running')
        roscore = start_process(['roscore'], local_env, run_dir / 'roscore.log')
        for _ in range(120):
            if command_output(['rosparam', 'list'], local_env,
                              timeout=5).returncode == 0:
                break
            time.sleep(0.25)
        stage = start_process(
            ['rosrun', 'stage_ros', 'stageros', str(WORLD)], local_env,
            run_dir / 'stage.log')
        for topic in ('/base_pose_ground_truth', '/odom', '/base_scan', '/cmd_vel'):
            wait_topic(local_env, topic)
        with open(run_dir / 'driver.log', 'w') as driver_log:
            completed = subprocess.run(
                ['/usr/bin/python3', str(ROOT /
                 'tools/realizability_pilot/fixed_scan_capture.py'),
                 '--spec', str(spec_path), '--output-dir', str(run_dir)],
                env=local_env, cwd=str(ROOT), stdout=driver_log,
                stderr=subprocess.STDOUT, timeout=600, text=True)
        result_path = run_dir / 'capture_result.json'
        result = load_json(result_path) if result_path.exists() else None
        if completed.returncode != 0 and result is None:
            raise RuntimeError('fixed-scan capture failed without result')
        return result
    finally:
        stop_process(stage)
        stop_process(roscore)


def state_path(root):
    return Path(root) / 'technical/controller_preflight_state.json'


def save_state(root, state):
    state['updated_utc'] = now()
    Path(root, 'technical').mkdir(parents=True, exist_ok=True)
    atomic_json(state_path(root), state)


def initial_state(protocol_hash, n_value):
    return {
        'status': 'PLANNED', 'protocol_id': PROTOCOL_ID,
        'protocol_sha256': protocol_hash, 'N': n_value,
        'created_utc': now(), 'branches': [],
        'backend_started': False, 'scientific_endpoint_read': False,
    }


def branch_key(target, index, arm):
    return '{}-H{}:{}'.format(target[-1], index, arm)


def result_row(target, index, arm, result, spec, n_value):
    terminal = spec['canonical_terminal_gt_pose']
    start_error = pose_error(result['branch_start_gt_pose'], terminal)
    start_valid = (start_error[0] <= START_POSITION_TOLERANCE_M and
                   start_error[1] <= START_HEADING_TOLERANCE_RAD)
    status = result['status']
    if status == 'SUCCEEDED' and not start_valid:
        status = 'TECHNICAL_INVALID_BRANCH_START'
    elif status == 'SUCCEEDED':
        status = 'TECHNICALLY_VALID'
    return {
        'target': target, 'block': '{}-H{}'.format(target[-1], index),
        'arm': arm, 'N': n_value,
        'completion_scan_index': result['completion_scan_index'],
        'completion_margin': result['completion_margin'],
        'duration_s': result['wall_clock_duration_s'],
        'distance_m': result['treatment_path_length_m'],
        'yaw_excursion_rad': result['treatment_yaw_excursion_rad'],
        'raw_scan_count': result['raw_scan_count'],
        'scientific_treatment_scan_count': result[
            'scientific_treatment_scan_count'],
        'static_tail_scan_count': result['static_tail_scan_count'],
        'duplicate_timestamp_count': result['duplicate_timestamp_count'],
        'nonmonotonic_timestamp_count': result[
            'nonmonotonic_timestamp_count'],
        'scientific_stream_exact_first_N': result[
            'scientific_stream_exact_first_N'],
        'no_contamination_after_N': result[
            'no_scientific_stream_contamination_after_N'],
        'branch_start_position_error_m': start_error[0],
        'branch_start_heading_error_rad': start_error[1],
        'branch_start_valid': start_valid,
        'controller_exception': False,
        'technical_status': status,
        'treatment_start_timestamp': result['treatment_start_time'],
        'treatment_end_timestamp': result['treatment_end_timestamp'],
    }


def finalize(root, state, protocol, budget):
    rows = state['branches']
    margins = [int(row['completion_margin']) for row in rows
               if row.get('completion_margin') is not None]
    all_valid = (len(rows) == 24 and
                 len({(r['target'], r['block'], r['arm']) for r in rows}) == 24 and
                 all(row['technical_status'] == 'TECHNICALLY_VALID'
                     for row in rows))
    margin_valid = bool(margins) and min(margins) >= int(
        protocol['technical_gate']['minimum_completion_margin'])
    envelope = ('SCAN_BUDGET_TECHNICALLY_CERTIFIED'
                if all_valid and margin_valid else
                'SCAN_BUDGET_ENVELOPE_INSUFFICIENT')
    final_gate = ('V14_FIXED_SCAN_TECHNICALLY_READY'
                  if envelope == 'SCAN_BUDGET_TECHNICALLY_CERTIFIED' else
                  'V14_FIXED_SCAN_TECHNICAL_REDESIGN_REQUIRED')
    summary = {
        'status': 'TECHNICAL_PREFLIGHT_COMPLETE',
        'planned_captures': 24, 'completed_rows': len(rows),
        'technically_valid': sum(
            row['technical_status'] == 'TECHNICALLY_VALID' for row in rows),
        'N': budget['N'], 'M': budget['M'], 'S': budget['S'],
        'completion_margin': {
            'minimum': min(margins) if margins else None,
            'median': float(np.median(margins)) if margins else None,
            'maximum': max(margins) if margins else None,
        },
        'scan_budget_gate': envelope,
        'backend_started': False,
        'scientific_endpoint_read': False,
        'automatic_N_change': False,
        'rows': rows,
    }
    write_csv(Path(root) / 'technical/controller_preflight.csv', rows)
    atomic_json(Path(root) / 'technical/controller_preflight_summary.json', summary)
    decision = {
        'protocol_id': PROTOCOL_ID,
        'technical_gate': final_gate,
        'scan_budget_gate': envelope,
        'scientific_decision': None,
        'v13C_status': 'CONFIRMATORY_EXPERIMENT_TECHNICALLY_INCOMPLETE',
        'posthoc_status': 'DIAGNOSTIC_SUPPORTS_ONE_PROSPECTIVE_RETRY',
        'no_v14_confirmatory_collection_started': True,
        'original_artifacts_unchanged': verify_original_artifacts(
            protocol['original_artifact_manifest']),
    }
    Path(root, 'decision').mkdir(parents=True, exist_ok=True)
    atomic_json(Path(root) / 'decision/v14T_technical_gate.json', decision)
    state['status'] = final_gate
    state['completed_utc'] = now()
    state.pop('worker_pid', None)
    state.pop('worker_pgid', None)
    save_state(root, state)
    return decision


def collect(root=RESULT_ROOT):
    root = Path(root)
    protocol_path = root / 'preregistration/v14T_protocol.json'
    budget_path = root / 'preregistration/v14T_scan_budget_derivation.json'
    protocol = load_json(protocol_path)
    budget = load_json(budget_path)
    for relative, expected in protocol['code_hashes'].items():
        if sha256(ROOT / relative) != expected:
            raise RuntimeError('frozen v14-T code changed: {}'.format(relative))
    original = verify_original_artifacts(protocol['original_artifact_manifest'])
    if not original['passed']:
        raise RuntimeError('original artifacts changed before v14-T collection')
    protocol_hash = sha256(protocol_path)
    state = (load_json(state_path(root)) if state_path(root).exists()
             else initial_state(protocol_hash, budget['N']))
    if state['protocol_sha256'] != protocol_hash:
        raise RuntimeError('v14-T protocol hash changed')
    state.update(status='RUNNING', worker_pid=os.getpid(),
                 worker_pgid=os.getpgrp(), started_utc=state.get(
                     'started_utc', now()))
    save_state(root, state)
    completed_keys = {row['key'] for row in state['branches']}
    env = activated_environment()
    try:
        for block in block_rows():
            for arm in block['arm_order']:
                key = branch_key(block['target'], block['index'], arm)
                if key in completed_keys:
                    continue
                spec = fixed_spec(block['target'], block['index'], arm,
                                  budget['N'])
                directory = (root / 'technical/captures' / block['target'] /
                             'H{}'.format(block['index']) / arm)
                directory.parent.mkdir(parents=True, exist_ok=True)
                try:
                    result = run_fixed_stage_capture(env, spec, directory)
                    row = result_row(block['target'], block['index'], arm,
                                     result, spec, budget['N'])
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    directory.mkdir(parents=True, exist_ok=True)
                    row = {
                        'target': block['target'], 'block': block['block'],
                        'arm': arm, 'N': budget['N'],
                        'completion_scan_index': None,
                        'completion_margin': None, 'duration_s': None,
                        'distance_m': None, 'yaw_excursion_rad': None,
                        'raw_scan_count': None,
                        'scientific_treatment_scan_count': None,
                        'static_tail_scan_count': None,
                        'duplicate_timestamp_count': None,
                        'nonmonotonic_timestamp_count': None,
                        'scientific_stream_exact_first_N': False,
                        'no_contamination_after_N': False,
                        'branch_start_position_error_m': None,
                        'branch_start_heading_error_rad': None,
                        'branch_start_valid': False,
                        'controller_exception': True,
                        'technical_status': 'CONTROLLER_EXCEPTION',
                        'reason': '{}: {}'.format(type(exc).__name__, exc),
                    }
                    atomic_json(directory / 'TECHNICAL_FAILURE.json', {
                        'status': row['technical_status'],
                        'reason': row['reason'],
                        'traceback': traceback.format_exc(),
                        'no_retry': True,
                    })
                row['key'] = key
                row['capture_dir'] = str(directory.relative_to(ROOT))
                state['branches'].append(row)
                completed_keys.add(key)
                save_state(root, state)
        return finalize(root, state, protocol, budget)
    except KeyboardInterrupt:
        state['status'] = 'INTERRUPTED'
        state['interrupted_utc'] = now()
        state.pop('worker_pid', None)
        state.pop('worker_pgid', None)
        save_state(root, state)
        return {'technical_gate': 'INTERRUPTED'}


def live_worker(root):
    path = state_path(root)
    if not path.exists():
        return None
    state = load_json(path)
    pid = state.get('worker_pid')
    if not pid or not (Path('/proc') / str(pid) / 'cmdline').exists():
        return None
    command = (Path('/proc') / str(pid) / 'cmdline').read_bytes().replace(
        b'\0', b' ').decode(errors='replace')
    if 'v14t_fixed_scan_technical.py' not in command:
        return None
    return int(pid), int(state['worker_pgid'])


def main():
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(
        KeyboardInterrupt()))
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('prepare', 'run', 'start',
                                           'status', 'stop'))
    parser.add_argument('--root', type=Path, default=RESULT_ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == 'prepare':
        output = prepare(root)
    elif args.command == 'run':
        output = collect(root)
    elif args.command == 'start':
        if live_worker(root):
            raise SystemExit('verified v14-T worker already live')
        if not (root / 'preregistration/v14T_protocol.json').exists():
            raise SystemExit('run prepare and freeze v14-T before collection')
        (root / 'technical').mkdir(parents=True, exist_ok=True)
        log = open(root / 'technical/controller_preflight.log', 'a', buffering=1)
        command = ['/usr/bin/python3', str(Path(__file__).resolve()), 'run',
                   '--root', str(root)]
        process = subprocess.Popen(
            command, cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT,
            text=True, start_new_session=True)
        atomic_json(root / 'technical/launcher.json', {
            'pid': process.pid, 'pgid': process.pid, 'command': command,
            'started_utc': now()})
        output = {'status': 'STARTED', 'pid': process.pid, 'root': str(root)}
    elif args.command == 'status':
        state = load_json(state_path(root)) if state_path(root).exists() else {
            'status': 'NOT_STARTED', 'branches': []}
        output = {'status': state['status'],
                  'completed_branches': len(state.get('branches', [])),
                  'valid_branches': sum(
                      row.get('technical_status') == 'TECHNICALLY_VALID'
                      for row in state.get('branches', [])),
                  'live_worker': bool(live_worker(root)),
                  'updated_utc': state.get('updated_utc')}
    else:
        worker = live_worker(root)
        if not worker:
            raise SystemExit('no verified v14-T worker')
        os.killpg(worker[1], signal.SIGINT)
        output = {'status': 'SIGINT_SENT', 'pgid': worker[1]}
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
