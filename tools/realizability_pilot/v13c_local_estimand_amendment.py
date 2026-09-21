#!/usr/bin/python3
"""Outcome-blind Stage-0 local-estimand amendment for v13-C.

This module reads only the frozen v13-T canonical-history/prefix artifacts.
It never imports action-branch results or computes a scientific endpoint.
"""

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path

from protocol import TARGETS
from v13_technical_protocol import CANDIDATE_SEEDS, TARGET_IDS


BASE_COMMIT = '201e4b78345019af5b0d718a416ce6fa17e063d9'
PROTOCOL_ID = 'p1_confirmatory_v13c_20260921'
ROOT = Path(__file__).resolve().parents[2]
V13T_ROOT = (ROOT / 'results/realizability_pilot' /
             'p1_v13_technical_20260920')
RESULT_ROOT = ROOT / 'results/realizability_pilot' / PROTOCOL_ID
OLD_MANIFEST = V13T_ROOT / 'history_eligibility_manifest.json'
AMENDMENT_PATH = (RESULT_ROOT / 'preregistration' /
                  'v13T_amendment_01_local_estimand.json')
FROZEN_MANIFEST_PATH = (RESULT_ROOT / 'preregistration' /
                        'v13C_frozen_history_manifest.json')
QUANTILES = (0.10, 0.30, 0.50, 0.70, 0.90)


def _load(path):
    return json.loads(Path(path).read_text())


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _distance_xy(node, waypoint):
    return math.hypot(float(node['x']) - float(waypoint[0]),
                      float(node['y']) - float(waypoint[1]))


def _atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = _load(path)
        if existing != payload:
            raise RuntimeError('refusing to change frozen artifact: {}'.format(
                path))
        return
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def _invalid(base, reason):
    payload = dict(base)
    payload.update({
        'selection_valid': False,
        'exclusion_reason': reason,
        'selected_five_state_ids': [],
        'selected_five_unique_ids': [],
    })
    return payload


def select_local_target(attempt_dir, target_label, target_id):
    """Select five states from the frozen 2.5 m target-local state run."""
    attempt_dir = Path(attempt_dir)
    snapshot = _load(attempt_dir / 'pose_graph_before.json')
    route = _load(attempt_dir / 'resolved_history_route.json')
    episode = _load(attempt_dir / 'episode_result.json')
    target_spec = TARGETS[target_id]
    radius_m = float(target_spec['target_segment_radius_m'])
    waypoint_index = int(target_spec['target_history_waypoint_index'])
    waypoint = route['resolved_history_waypoints'][waypoint_index]
    route_start = int(route['route_start_node_count'])
    unique_by_state = {int(row['id']): int(row['unique_id'])
                       for row in snapshot.get('full_pose_nodes', [])}
    legal = [row for row in snapshot['nodes']
             if int(row['id']) >= route_start]
    legal.sort(key=lambda row: int(row['id']))
    base = {
        'target_label': target_label,
        'target_id': target_id,
        'fixed_target_waypoint_index': waypoint_index,
        'fixed_resolved_history_waypoint': waypoint,
        'target_segment_radius_m': radius_m,
        'route_start_node_count': route_start,
        'canonical_history_complete': bool(
            episode.get('canonical_history_complete')),
        'allowed_inputs': [
            'pose_graph_before.json nodes/full_pose_nodes',
            'resolved_history_route.json',
            'episode_result.json canonical_history_complete only',
        ],
        'forbidden_future_inputs_accessed': False,
        'quantiles': list(QUANTILES),
    }
    if not legal:
        return _invalid(base, 'no legal post-route-start historical states')

    anchor = min(legal, key=lambda row: (
        _distance_xy(row, waypoint), int(row['id'])))
    anchor_id = int(anchor['id'])
    anchor_distance = _distance_xy(anchor, waypoint)
    local = [row for row in legal
             if _distance_xy(row, waypoint) <= radius_m]
    local.sort(key=lambda row: int(row['id']))
    base.update({
        'action_anchor_state_id': anchor_id,
        'action_anchor_unique_id': unique_by_state.get(anchor_id),
        'anchor_to_waypoint_distance_m': anchor_distance,
        'local_candidate_state_ids': [int(row['id']) for row in local],
        'local_candidate_count': len(local),
    })
    local_index = {int(row['id']): index for index, row in enumerate(local)}
    if anchor_id not in local_index:
        return _invalid(base, 'action anchor is outside the frozen local radius')

    anchor_index = local_index[anchor_id]
    start = anchor_index
    while (start > 0 and
           int(local[start]['id']) - int(local[start - 1]['id']) == 1):
        start -= 1
    stop = anchor_index
    while (stop + 1 < len(local) and
           int(local[stop + 1]['id']) - int(local[stop]['id']) == 1):
        stop += 1
    run = local[start:stop + 1]
    run_ids = [int(row['id']) for row in run]
    base.update({
        'contiguous_local_run_state_ids': run_ids,
        'contiguous_local_run_count': len(run),
        'contiguous_run_contains_anchor': anchor_id in run_ids,
    })
    if len(run) < 5:
        return _invalid(base, 'contiguous local run contains fewer than five states')

    cumulative = [0.0]
    for left, right in zip(run, run[1:]):
        cumulative.append(cumulative[-1] + math.hypot(
            float(right['x']) - float(left['x']),
            float(right['y']) - float(left['y'])))
    total = cumulative[-1]
    base['local_segment_physical_arc_length_m'] = total
    if total <= 0.0:
        return _invalid(base, 'contiguous local run has zero spatial arc length')

    progress = [value / total for value in cumulative]
    selected_indices = []
    for quantile in QUANTILES:
        selected_indices.append(min(
            range(len(run)),
            key=lambda index: (abs(progress[index] - quantile),
                               int(run[index]['id']))))
    selected_ids = [int(run[index]['id']) for index in selected_indices]
    selected_unique = [unique_by_state.get(state_id)
                       for state_id in selected_ids]
    selections = [{
        'quantile': quantile,
        'state_id': int(run[index]['id']),
        'unique_id': unique_by_state.get(int(run[index]['id'])),
        'normalized_progress': progress[index],
        'quantile_abs_error': abs(progress[index] - quantile),
    } for quantile, index in zip(QUANTILES, selected_indices)]
    base.update({
        'local_run': [{
            'state_id': int(row['id']),
            'unique_id': unique_by_state.get(int(row['id'])),
            'x': float(row['x']),
            'y': float(row['y']),
            'theta': float(row['theta']),
            'arc_length_m': arc,
            'normalized_progress': normalized,
            'distance_to_waypoint_m': _distance_xy(row, waypoint),
        } for row, arc, normalized in zip(run, cumulative, progress)],
        'quantile_selections': selections,
        'selected_five_state_ids': selected_ids,
        'selected_five_unique_ids': selected_unique,
    })
    valid = (
        base['canonical_history_complete'] and
        len(selected_ids) == 5 and len(set(selected_ids)) == 5 and
        all(left < right for left, right in
            zip(selected_ids, selected_ids[1:])) and
        all(value is not None for value in selected_unique))
    base['selection_valid'] = valid
    base['exclusion_reason'] = None if valid else (
        'quantile rule did not produce exactly five distinct strictly '
        'increasing mapped states')
    return base


def build_amendment(v13t_root=V13T_ROOT):
    v13t_root = Path(v13t_root)
    old_manifest_path = v13t_root / 'history_eligibility_manifest.json'
    old_manifest = _load(old_manifest_path)
    old_records = {(row['target_label'], int(row['seed'])): row
                   for row in old_manifest['records']}
    records = []
    for target_label in ('target_A', 'target_B'):
        target_id = TARGET_IDS[target_label]
        for seed in CANDIDATE_SEEDS[target_label]:
            old = old_records[(target_label, int(seed))]
            attempt = (v13t_root / 'histories' / target_label /
                       'seed_{}'.format(seed) / 'attempt_01')
            selection = select_local_target(attempt, target_label, target_id)
            old_eligible = old['status'] == 'TECHNICALLY_ELIGIBLE'
            confirmatory_eligible = old_eligible and selection['selection_valid']
            exclusion = []
            if not old_eligible:
                exclusion.append('old_v13T_technical_ineligible')
            if not selection['selection_valid']:
                exclusion.append(selection['exclusion_reason'])
            records.append({
                'target_label': target_label,
                'target_id': target_id,
                'seed': int(seed),
                'old_v13T_status': old['status'],
                'old_v13T_technical_eligible': old_eligible,
                **selection,
                'confirmatory_eligible': confirmatory_eligible,
                'confirmatory_exclusion_reasons': exclusion,
            })
    targets = {}
    for target_label in ('target_A', 'target_B'):
        rows = [row for row in records
                if row['target_label'] == target_label]
        eligible = [row['seed'] for row in rows
                    if row['confirmatory_eligible']]
        targets[target_label] = {
            'target_id': TARGET_IDS[target_label],
            'candidate_seeds_in_immutable_order':
                list(CANDIDATE_SEEDS[target_label]),
            'confirmatory_eligible_seeds_in_immutable_order': eligible,
            'confirmatory_eligible_count': len(eligible),
            'frozen_first_four_seeds': eligible[:4],
        }
    gate_pass = all(targets[target]['confirmatory_eligible_count'] >= 4
                    for target in ('target_A', 'target_B'))
    return {
        'protocol_id': PROTOCOL_ID,
        'stage': 'STAGE_0_LOCAL_ESTIMAND_AMENDMENT',
        'base_commit': BASE_COMMIT,
        'current_head_at_amendment': subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=str(ROOT), text=True).strip(),
        'source_v13T_manifest': str(old_manifest_path.relative_to(ROOT)),
        'source_v13T_manifest_sha256': _sha256(old_manifest_path),
        'target_identities_unchanged': TARGET_IDS,
        'frozen_radius_source': 'TARGETS[target_id][target_segment_radius_m]',
        'target_segment_radius_m': {
            target: float(TARGETS[TARGET_IDS[target]][
                'target_segment_radius_m'])
            for target in ('target_A', 'target_B')},
        'selector_rule': (
            'post-route-start states within 2.5 m of fixed resolved history '
            'waypoint; maximal contiguous state-ID run containing unchanged '
            'action anchor; fixed arc-length quantiles with lower-state-ID '
            'tie break'),
        'quantiles': list(QUANTILES),
        'required_state_count': 5,
        'history_rerun': False,
        'action_launched': False,
        'scientific_endpoints_read': [],
        'forbidden_reads': [
            'J_T', 'Delta U', 'E_T', 'E_N', 'final action graph',
            'action provenance', 'arm contrast'],
        'records': records,
        'targets': targets,
        'stage0_gate': ('LOCAL_ESTIMAND_AMENDMENT_PASS' if gate_pass else
                        'PAUSED_LOCAL_ESTIMAND_NOT_ROBUST'),
    }


def build_frozen_manifest(amendment, amendment_path=AMENDMENT_PATH):
    targets = amendment['targets']
    gate = amendment['stage0_gate']
    selected = {}
    for target_label in ('target_A', 'target_B'):
        frozen_seeds = targets[target_label]['frozen_first_four_seeds']
        selected[target_label] = []
        for block_index, seed in enumerate(frozen_seeds, 1):
            row = next(item for item in amendment['records']
                       if item['target_label'] == target_label and
                       item['seed'] == seed)
            selected[target_label].append({
                'block_id': '{}_H{}'.format(target_label, block_index),
                'seed': seed,
                'target_id': row['target_id'],
                'action_anchor_state_id': row['action_anchor_state_id'],
                'action_anchor_unique_id': row['action_anchor_unique_id'],
                'anchor_to_waypoint_distance_m':
                    row['anchor_to_waypoint_distance_m'],
                'local_candidate_state_ids':
                    row['local_candidate_state_ids'],
                'contiguous_local_run_state_ids':
                    row['contiguous_local_run_state_ids'],
                'local_segment_physical_arc_length_m':
                    row['local_segment_physical_arc_length_m'],
                'selected_five_state_ids': row['selected_five_state_ids'],
                'selected_five_unique_ids': row['selected_five_unique_ids'],
                'old_v13T_status': row['old_v13T_status'],
                'selection_valid': row['selection_valid'],
                'confirmatory_eligible': row['confirmatory_eligible'],
            })
    return {
        'protocol_id': PROTOCOL_ID,
        'base_commit': BASE_COMMIT,
        'amendment_path': str(Path(amendment_path).relative_to(ROOT)),
        'amendment_sha256': _sha256(amendment_path),
        'immutable_seed_order': CANDIDATE_SEEDS,
        'selection_rule': (
            'first four old-v13T-technically-eligible and local-selector-valid '
            'seeds in the original immutable seed order'),
        'runtime_reserve_allowed': False,
        'substitution_allowed': False,
        'selected_blocks': selected,
        'planned_block_count': sum(len(rows) for rows in selected.values()),
        'planned_branch_count': 3 * sum(len(rows) for rows in selected.values()),
        'stage0_gate': gate,
        'stage1_authorized': gate == 'LOCAL_ESTIMAND_AMENDMENT_PASS',
    }


def run_stage0(result_root=RESULT_ROOT, v13t_root=V13T_ROOT):
    result_root = Path(result_root)
    amendment_path = (result_root / 'preregistration' /
                      AMENDMENT_PATH.name)
    manifest_path = (result_root / 'preregistration' /
                     FROZEN_MANIFEST_PATH.name)
    amendment = build_amendment(v13t_root)
    _atomic_json(amendment_path, amendment)
    manifest = build_frozen_manifest(amendment, amendment_path)
    _atomic_json(manifest_path, manifest)
    return amendment, manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--result-root', default=str(RESULT_ROOT))
    parser.add_argument('--v13t-root', default=str(V13T_ROOT))
    args = parser.parse_args()
    amendment, manifest = run_stage0(args.result_root, args.v13t_root)
    print(json.dumps({
        'stage0_gate': amendment['stage0_gate'],
        'targets': amendment['targets'],
        'frozen_blocks': manifest['selected_blocks'],
    }, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
