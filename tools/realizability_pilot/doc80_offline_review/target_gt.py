#!/usr/bin/python3
"""Doc-80 section 5: corrected target map GT and robot relative GT.

The Doc-79 ``TARGET_MAP_ERROR`` reused the driver-recorded ``map_base`` at the
target's *acceptance* time for all four stages, so it could not show whether
later graph optimisation moved historical targets.  This module reads the
target node pose from each synchronous stage graph instead, converts the laser
pose to the base frame with the verified static transform
``T_LASER_BASE`` (x = -0.20 m, validated in the frame audit), and evaluates it
against interpolated GT with one pre-action-only map->GT alignment.

Outputs
- analysis/corrected_target_map_gt.csv
- analysis/corrected_robot_relative_gt.csv
"""

import csv
import json
import math
import statistics
from pathlib import Path

from . import common

ALIGNMENT_STAGES = ('history', 'return')  # strictly pre-action inputs


def alignment_inputs(scans, gt_stream, stage_windows):
    """Pre-action (x, y) pairs used to fit the map->GT transform."""
    pairs = []
    max_index = -1
    for record in scans:
        if record.get('map_base') is None:
            continue
        stage = common.stage_of_index(record['index'], stage_windows)
        if stage not in ALIGNMENT_STAGES:
            continue
        truth = common.gt_pose_at(gt_stream, record['stamp'], tolerance=0.06)
        if truth is None:
            continue
        pairs.append(((record['map_base'][0], record['map_base'][1]),
                      (truth['x'], truth['y'])))
        max_index = max(max_index, record['index'])
    return pairs, max_index


def alignment_for(run, scans, gt_stream, stage_windows):
    """One rigid map->GT transform fitted on pre-action scans only."""
    pairs, max_index = alignment_inputs(scans, gt_stream, stage_windows)
    if len(pairs) < 2:
        return None, {'pairs': 0, 'error': 'insufficient pre-action pairs'}
    # reuse the frozen least-squares rigid fit (identical to Doc 79)
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'continuous_revisit'))
    import geometry as ge
    transform = ge.align_rigid([pair[0] for pair in pairs],
                               [pair[1] for pair in pairs])
    return transform, {
        'pairs': len(pairs),
        'all_inputs_pre_action': True,
        'max_input_scan_index': max_index,
        'alignment_yaw_rad': transform[0],
        'alignment_translation_m': math.hypot(transform[1], transform[2]),
        'stages_used': list(ALIGNMENT_STAGES),
    }


def target_error(base_pose, transform, truth):
    """Map error of one target pose against interpolated GT, or None."""
    if truth is None:
        return None
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'continuous_revisit'))
    import geometry as ge
    moved = ge.pose_apply(transform, list(base_pose))
    return {
        'translation_m': common.translation_error(
            moved, (truth['x'], truth['y'], truth['theta'])),
        'rotation_rad': common.rotation_error(
            moved, (truth['x'], truth['y'], truth['theta'])),
    }


def corrected_target_rows(doc80_root=common.DOC80, doc79_root=common.DOC79):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'continuous_revisit'))
    import geometry as ge

    rows = []
    link_rows = []
    original_lookup = {}
    original_path = Path(doc79_root) / 'analysis' / 'corrected_gt_metrics.csv'
    if original_path.is_file():
        with open(original_path) as handle:
            for row in csv.DictReader(handle):
                if row['family'] == 'TARGET_MAP_ERROR':
                    original_lookup[(row['episode_id'], row['attempt'],
                                     row['stage'], row['metric'])] = row['value']

    for run in common.valid_runs():
        result = run['result']
        stage_windows = common.windows(result)
        scans = common.jsonl(run['attempt_dir'] / 'scan_stream.jsonl')
        gt_stream = common.jsonl(run['attempt_dir'] / 'gt_stream.jsonl')
        frozen = run['frozen']
        targets = [int(value) for value in frozen['target_state_ids']]
        anchor = int(frozen['anchor']['id'])
        accepts = {item['state_id']: item for item in common.accepts(run)}
        graphs = {stem: common.sync_graph(run, stem) for stem in common.STAGES}
        if stage_windows is None or any(graph is None for graph in graphs.values()):
            continue
        transform, align_info = alignment_for(run, scans, gt_stream, stage_windows)
        if transform is None:
            continue

        def gt_of(state):
            item = accepts.get(state)
            if item is None:
                return None, None
            truth = common.gt_pose_at(gt_stream, item['sim_time'], tolerance=0.06)
            return truth, item['sim_time']

        node_lookup = {stem: {node['state_id']: node for node in graph['nodes']}
                       for stem, graph in graphs.items()}
        targets_present = [state for state in targets
                           if all(state in node_lookup[stem] for stem in common.STAGES)]
        for state in targets_present:
            truth, stamp = gt_of(state)
            status = 'EVALUABLE' if truth is not None else 'NOT_EVALUABLE'
            previous = {}
            for stem in common.STAGES:
                node = node_lookup[stem][state]
                base_pose = common.compose((node['x'], node['y'], node['theta']),
                                           common.T_LASER_BASE)
                row = {
                    'episode_id': run['episode_id'], 'attempt': run['attempt'],
                    'place': run['spec'].get('place_id'),
                    'action': run['spec'].get('action_id'),
                    'target_state_id': state, 'stage': stem,
                    'status': status,
                    'gt_stamp': stamp,
                    'node_laser_pose': json.dumps([node['x'], node['y'], node['theta']]),
                    'node_base_pose': json.dumps(list(base_pose)),
                    'displacement_vs_previous_stage_m': (
                        None if not previous else math.hypot(
                            base_pose[0] - previous['base_pose'][0],
                            base_pose[1] - previous['base_pose'][1])),
                    'rotation_vs_previous_stage_rad': (
                        None if not previous else common.rotation_error(
                            base_pose, previous['base_pose'])),
                }
                if truth is not None:
                    error = target_error(base_pose, transform, truth)
                    row['map_error_translation_m'] = error['translation_m']
                    row['map_error_rotation_rad'] = error['rotation_rad']
                    row['error_change_vs_previous_stage_m'] = (
                        None if not previous or previous.get('error') is None
                        else row['map_error_translation_m'] - previous['error'])
                # anchor relative SE(2), same graph
                if anchor in node_lookup[stem]:
                    anchor_node = node_lookup[stem][anchor]
                    anchor_base = common.compose(
                        (anchor_node['x'], anchor_node['y'], anchor_node['theta']),
                        common.T_LASER_BASE)
                    row['anchor_relative_translation_m'] = common.translation_error(
                        base_pose, anchor_base)
                    row['anchor_relative_bearing_rad'] = common.rotation_error(
                        base_pose, anchor_base)
                if truth is not None:
                    previous = {'base_pose': base_pose,
                                'error': row['map_error_translation_m']}
                else:
                    previous = {'base_pose': base_pose, 'error': None}
                # original doc-79 values for comparison
                for metric, key in (('mean_m', 'map_error_translation_m'),
                                    ('max_m', 'map_error_translation_m')):
                    pass
                rows.append(row)
        # per-run/stage aggregates with original comparison
        for stem in common.STAGES:
            stage_rows = [row for row in rows
                          if row['episode_id'] == run['episode_id']
                          and row['stage'] == stem
                          and row.get('map_error_translation_m') is not None]
            if not stage_rows:
                continue
            mean_value = statistics.mean(
                row['map_error_translation_m'] for row in stage_rows)
            max_value = max(row['map_error_translation_m'] for row in stage_rows)
            link_rows.append({
                'episode_id': run['episode_id'], 'attempt': run['attempt'],
                'stage': stem,
                'targets_evaluated': len(stage_rows),
                'corrected_mean_m': mean_value,
                'corrected_max_m': max_value,
                'doc79_original_mean_m': original_lookup.get(
                    (run['episode_id'], run['attempt'], stem, 'mean_m')),
                'doc79_original_max_m': original_lookup.get(
                    (run['episode_id'], run['attempt'], stem, 'max_m')),
                'mean_difference_m': (
                    None if original_lookup.get(
                        (run['episode_id'], run['attempt'], stem, 'mean_m')) in (None, '')
                    else mean_value - float(original_lookup[
                        (run['episode_id'], run['attempt'], stem, 'mean_m')])),
                'alignment_pairs': align_info['pairs'],
                'alignment_yaw_rad': align_info['alignment_yaw_rad'],
                'alignment_translation_m': align_info['alignment_translation_m'],
            })

    common.write_csv(Path(doc80_root) / 'analysis' / 'corrected_target_map_gt.csv',
                     rows)
    common.write_csv(Path(doc80_root) / 'analysis' / 'target_gt_original_comparison.csv',
                     link_rows)
    return {'target_rows': rows, 'comparison': link_rows}


def robot_relative_rows(doc80_root=common.DOC80):
    """Robot localisation at the arrival and action_done boundaries (§5.6)."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'continuous_revisit'))
    import geometry as ge

    rows = []
    for run in common.valid_runs():
        result = run['result']
        stage_windows = common.windows(result)
        scans = common.jsonl(run['attempt_dir'] / 'scan_stream.jsonl')
        gt_stream = common.jsonl(run['attempt_dir'] / 'gt_stream.jsonl')
        frozen = run['frozen']
        anchor = int(frozen['anchor']['id'])
        graphs = {stem: common.sync_graph(run, stem) for stem in common.STAGES}
        if stage_windows is None or any(graph is None for graph in graphs.values()):
            continue
        transform, align_info = alignment_for(run, scans, gt_stream, stage_windows)
        if transform is None:
            continue
        arrival_index = stage_windows['action'][0] - 1
        action_done_index = stage_windows['action'][1] - 1
        samples = {}
        for tag, index in (('arrival', arrival_index), ('action_done', action_done_index)):
            record = next((item for item in scans if item['index'] == index), None)
            if record is None or record.get('map_base') is None:
                continue
            truth = common.gt_pose_at(gt_stream, record['stamp'], tolerance=0.06)
            samples[tag] = {'record': record, 'truth': truth}
        if len(samples) != 2:
            rows.append({'episode_id': run['episode_id'],
                         'attempt': run['attempt'],
                         'status': 'GT_EFFECT_NOT_ESTIMABLE',
                         'note': 'boundary scan or GT missing'})
            continue
        out = {'episode_id': run['episode_id'], 'attempt': run['attempt'],
               'place': run['spec'].get('place_id'),
               'action': run['spec'].get('action_id'),
               'alignment_yaw_rad': align_info['alignment_yaw_rad'],
               'alignment_pairs': align_info['pairs']}
        for tag, sample in samples.items():
            moved = ge.pose_apply(transform, sample['record']['map_base'])
            truth = sample['truth']
            out['{}_localisation_error_m'.format(tag)] = (
                None if truth is None else common.translation_error(
                    moved, (truth['x'], truth['y'], truth['theta'])))
            out['{}_heading_error_rad'.format(tag)] = (
                None if truth is None else common.rotation_error(
                    moved, (truth['x'], truth['y'], truth['theta'])))
            out['{}_stamp'.format(tag)] = sample['record']['stamp']
        if any(out.get('{}_localisation_error_m'.format(tag)) is None
               for tag in ('arrival', 'action_done')):
            out['status'] = 'GT_EFFECT_NOT_ESTIMABLE'
            out['note'] = 'GT gap at boundary stamps'
        else:
            gt_arrival = samples['arrival']['truth']
            gt_done = samples['action_done']['truth']
            out['gt_pose_difference_m'] = common.translation_error(
                (gt_arrival['x'], gt_arrival['y'], gt_arrival['theta']),
                (gt_done['x'], gt_done['y'], gt_done['theta']))
            out['gt_heading_difference_rad'] = common.rotation_error(
                (gt_arrival['x'], gt_arrival['y'], gt_arrival['theta']),
                (gt_done['x'], gt_done['y'], gt_done['theta']))
            comparable = (out['gt_pose_difference_m'] <= 0.35
                          and out['gt_heading_difference_rad'] <= 0.35)
            out['status'] = 'EVALUABLE' if comparable else 'NOT_COMPARABLE_STATES'
            out['localisation_error_change_m'] = (
                out['action_done_localisation_error_m']
                - out['arrival_localisation_error_m'])
            # SE(2) relative to the anchor at both boundaries (map frame)
            anchor_node = graphs['arrival']['nodes']
            anchor_by_id = {node['state_id']: node for node in anchor_node}
            if anchor in anchor_by_id:
                anchor_base = common.compose(
                    (anchor_by_id[anchor]['x'], anchor_by_id[anchor]['y'],
                     anchor_by_id[anchor]['theta']), common.T_LASER_BASE)
                for tag, sample in samples.items():
                    rel_est = common.between(anchor_base,
                                             tuple(sample['record']['map_base']))
                    rel_gt = common.between(
                        (None, None, None), (None, None, None)) \
                        if sample['truth'] is None else None
                    out['{}_anchor_relative_est_m'.format(tag)] = math.hypot(
                        rel_est[0], rel_est[1])
                    if sample['truth'] is not None:
                        anchor_truth = common.gt_pose_at(
                            gt_stream, samples['arrival']['record']['stamp'],
                            tolerance=0.06)
                        # anchor GT uses the anchor's acceptance time
                        accept = {item['state_id']: item for item in common.accepts(run)}
                        anchor_stamp = accept.get(anchor, {}).get('sim_time')
                        anchor_truth = (common.gt_pose_at(gt_stream, anchor_stamp,
                                                          tolerance=0.06)
                                        if anchor_stamp else None)
                        if anchor_truth is not None and out.get(
                                '{}_localisation_error_m'.format(tag)) is not None:
                            mapped_anchor = ge.pose_apply(transform, list(anchor_base))
                            rel_gt = common.between(
                                (mapped_anchor[0], mapped_anchor[1], mapped_anchor[2]),
                                (sample['truth']['x'], sample['truth']['y'],
                                 sample['truth']['theta']))
                            est = common.between(anchor_base,
                                                 tuple(sample['record']['map_base']))
                            out['{}_anchor_relative_se2_translation_error_m'.format(tag)] = abs(
                                math.hypot(est[0], est[1]) - math.hypot(rel_gt[0], rel_gt[1]))
                            out['{}_anchor_relative_se2_rotation_error_rad'.format(tag)] = (
                                common.rotation_error(est, rel_gt))
        rows.append(out)
    common.write_csv(Path(doc80_root) / 'analysis' / 'corrected_robot_relative_gt.csv',
                     rows)
    return rows


if __name__ == '__main__':
    corrected_target_rows()
    robot_relative_rows()
