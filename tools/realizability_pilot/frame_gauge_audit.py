#!/usr/bin/python3
"""Offline map/world frame audit for the frozen v8 N1 attempts.

This module never changes an old episode verdict.  It estimates one rigid
SE(2) transform from the four *history* move endpoints only, then asks whether
that transform explains the later probe-arrival discrepancy.  The probe is
excluded from fitting so the diagnostic cannot fit away the outcome it audits.
"""

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


OLD_POSITION_GATE_M = 0.75
OLD_HEADING_GATE_RAD = 0.35
MIN_FIT_PAIRS = 3
MIN_FIT_SPREAD_M = 2.0


def wrap_angle(value):
    return math.atan2(math.sin(value), math.cos(value))


def estimate_se2(source_xy, target_xy):
    """Return the no-scale least-squares transform target ~= R source + t."""
    source = np.asarray(source_xy, dtype=float)
    target = np.asarray(target_xy, dtype=float)
    if source.shape != target.shape or source.ndim != 2 or source.shape[1] != 2:
        raise ValueError('source and target must be matching Nx2 arrays')
    if source.shape[0] < MIN_FIT_PAIRS:
        raise ValueError('at least {} pairs required'.format(MIN_FIT_PAIRS))
    source_center = source.mean(axis=0)
    target_center = target.mean(axis=0)
    source_zero = source - source_center
    target_zero = target - target_center
    if np.ptp(source, axis=0).max() < MIN_FIT_SPREAD_M:
        raise ValueError('paired positions have insufficient spatial spread')
    u_matrix, _singular, vt_matrix = np.linalg.svd(source_zero.T @ target_zero)
    rotation = vt_matrix.T @ u_matrix.T
    if np.linalg.det(rotation) < 0:
        vt_matrix[-1, :] *= -1
        rotation = vt_matrix.T @ u_matrix.T
    translation = target_center - rotation @ source_center
    return rotation, translation


def transform_pose(pose, rotation, translation):
    xy = rotation @ np.asarray(pose[:2], dtype=float) + translation
    yaw = wrap_angle(float(pose[2]) + math.atan2(rotation[1, 0], rotation[0, 0]))
    return [float(xy[0]), float(xy[1]), yaw]


def pose_errors(observed, target):
    return (math.hypot(float(observed[0]) - float(target[0]),
                       float(observed[1]) - float(target[1])),
            abs(wrap_angle(float(observed[2]) - float(target[2]))))


def robust_upper(values, floor):
    """Outcome-blind upper fence: max(floor, median + 3 scaled MAD)."""
    values = np.asarray([float(value) for value in values], dtype=float)
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    return max(float(floor), median + 3.0 * 1.4826 * mad), median, mad


def load_json(path):
    with open(path) as stream:
        return json.load(stream)


def fit_attempt(attempt_dir):
    result = load_json(attempt_dir / 'episode_result.json')
    spec = load_json(attempt_dir / 'episode_spec.json')
    history = [move for move in result.get('moves', [])
               if move.get('label', '').startswith('history_')
               and move.get('tf_pose_after') is not None
               and move.get('gt_pose_after') is not None]
    source = [move['tf_pose_after'][:2] for move in history]
    target = [move['gt_pose_after'][:2] for move in history]
    rotation, translation = estimate_se2(source, target)
    yaw = math.atan2(rotation[1, 0], rotation[0, 0])

    aligned_positions = []
    before_positions = []
    heading_residuals = []
    for move in history:
        predicted = transform_pose(move['tf_pose_after'], rotation, translation)
        aligned_positions.append(pose_errors(move['gt_pose_after'], predicted)[0])
        before_positions.append(math.hypot(
            float(move['gt_pose_after'][0]) - float(move['tf_pose_after'][0]),
            float(move['gt_pose_after'][1]) - float(move['tf_pose_after'][1])))
        heading_residuals.append(abs(wrap_angle(
            float(move['gt_pose_after'][2]) -
            (float(move['tf_pose_after'][2]) + yaw))))

    probe_moves = [move for move in result.get('moves', [])
                   if move.get('label') == 'probe_arrival']
    probe = probe_moves[-1] if probe_moves else None
    row = {
        'attempt_dir': str(attempt_dir),
        'episode_id': spec.get('episode_id'),
        'block_id': spec.get('block_id'),
        'condition_id': spec.get('condition_id'),
        'target_id': spec.get('target_id'),
        'old_status': result.get('status'),
        'old_reason': result.get('reason', result.get('exclusion_reason')),
        'fit_source': 'history_move_endpoints_only',
        'number_of_pairs': len(history),
        'fit_spread_m': float(np.ptp(np.asarray(source), axis=0).max()),
        'tx': float(translation[0]),
        'ty': float(translation[1]),
        'yaw': float(yaw),
        'rmse_before_alignment_m': float(np.sqrt(np.mean(np.square(before_positions)))),
        'rmse_after_alignment_m': float(np.sqrt(np.mean(np.square(aligned_positions)))),
        'max_error_before_m': float(max(before_positions)),
        'max_error_after_m': float(max(aligned_positions)),
        'heading_rmse_after_rad': float(np.sqrt(np.mean(np.square(heading_residuals)))),
        'heading_max_after_rad': float(max(heading_residuals)),
        'probe_available': probe is not None,
    }
    if probe is not None:
        aligned_target = transform_pose(
            [probe['target_x'], probe['target_y'], probe['target_theta']],
            rotation, translation)
        aligned_position, aligned_heading = pose_errors(
            probe['gt_pose_after'], aligned_target)
        expected_position, expected_heading = pose_errors(
            probe['expected_gt_pose'], aligned_target)
        raw_position = float(probe['gt_position_error_m'])
        raw_heading = float(probe['gt_heading_error_rad'])
        raw_normalized = max(raw_position / OLD_POSITION_GATE_M,
                             raw_heading / OLD_HEADING_GATE_RAD)
        aligned_normalized = max(aligned_position / OLD_POSITION_GATE_M,
                                 aligned_heading / OLD_HEADING_GATE_RAD)
        row.update({
            'probe_label': probe['label'],
            'raw_position_error_m': raw_position,
            'raw_heading_error_rad': raw_heading,
            'aligned_position_error_m': aligned_position,
            'aligned_heading_error_rad': aligned_heading,
            'raw_normalized_gate_error': raw_normalized,
            'aligned_normalized_gate_error': aligned_normalized,
            'normalized_gate_error_reduction': raw_normalized - aligned_normalized,
            'aligned_to_raw_ratio': (aligned_normalized / raw_normalized
                                     if raw_normalized > 0 else 0.0),
            'old_expected_vs_aligned_target_position_m': expected_position,
            'old_expected_vs_aligned_target_heading_rad': expected_heading,
            'aligned_target_world_x': aligned_target[0],
            'aligned_target_world_y': aligned_target[1],
            'aligned_target_world_yaw': aligned_target[2],
            'actual_probe_world_x': float(probe['gt_pose_after'][0]),
            'actual_probe_world_y': float(probe['gt_pose_after'][1]),
            'actual_probe_world_yaw': float(probe['gt_pose_after'][2]),
        })
    signature_path = attempt_dir / 'preprobe_graph_signature.json'
    if signature_path.is_file():
        signature = load_json(signature_path)
        row.update({
            'preprobe_node_count': signature.get('node_count'),
            'preprobe_edge_count': signature.get('edge_count'),
            'preprobe_node_id_set_hash': signature.get('node_id_set_hash'),
            'preprobe_edge_endpoint_set_hash': signature.get('edge_endpoint_set_hash'),
            'preprobe_corrected_path_length_m': signature.get('corrected_path_length_m'),
        })
    frozen_path = attempt_dir / 'frozen_target.json'
    if frozen_path.is_file():
        frozen = load_json(frozen_path)
        anchor = frozen.get('anchor_scan', {})
        reference = frozen.get('target_reference', [None, None, None])
        row['anchor_to_reference_distance_m'] = frozen.get(
            'anchor_to_reference_distance_m')
        if anchor.get('theta') is not None and reference[2] is not None:
            row['anchor_to_reference_heading_rad'] = abs(wrap_angle(
                float(anchor['theta']) - float(reference[2])))
    return row


def classify(rows):
    position_threshold, position_median, position_mad = robust_upper(
        [row['rmse_after_alignment_m'] for row in rows], 0.25)
    heading_threshold, heading_median, heading_mad = robust_upper(
        [row['heading_rmse_after_rad'] for row in rows], 0.15)

    block_signatures = defaultdict(Counter)
    for row in rows:
        signature = (row.get('preprobe_node_count'), row.get('preprobe_edge_count'),
                     row.get('preprobe_node_id_set_hash'),
                     row.get('preprobe_edge_endpoint_set_hash'))
        block_signatures[row.get('block_id')][signature] += 1

    for row in rows:
        signature = (row.get('preprobe_node_count'), row.get('preprobe_edge_count'),
                     row.get('preprobe_node_id_set_hash'),
                     row.get('preprobe_edge_endpoint_set_hash'))
        counter = block_signatures[row.get('block_id')]
        row['exact_preprobe_signature_repetitions_in_block'] = counter[signature]
        row['distinct_preprobe_signatures_in_block'] = len(counter)
        row['independent_history_structural_divergence'] = len(counter) > 1
        reliable = (row['rmse_after_alignment_m'] <= position_threshold and
                    row['heading_rmse_after_rad'] <= heading_threshold)
        row['se2_fit_reliable'] = reliable
        reduction = row.get('normalized_gate_error_reduction', float('-inf'))
        correspondence_norm = max(
            row.get('old_expected_vs_aligned_target_position_m', float('inf')) /
            OLD_POSITION_GATE_M,
            row.get('old_expected_vs_aligned_target_heading_rad', float('inf')) /
            OLD_HEADING_GATE_RAD)
        row['target_correspondence_normalized_error'] = correspondence_norm
        if not reliable:
            arrival_class = 'G2_TRUE_TRAJECTORY_OR_MAP_DIVERGENCE'
        elif correspondence_norm <= 0.5 and abs(reduction) <= 0.25:
            arrival_class = 'G0_FRAME_ALIGNED'
        else:
            arrival_class = 'G2_TRUE_TRAJECTORY_OR_MAP_DIVERGENCE'
        row['arrival_gauge_class'] = arrival_class
        row['old_gate_audit_label'] = (
            'OLD_GATE_POSSIBLY_FRAME_CONFUNDED'
            if arrival_class == 'G1_GAUGE_DOMINATED' else 'NO_RETROSPECTIVE_RELABEL')
    return {
        'position_fit_rmse_upper_m': position_threshold,
        'position_fit_rmse_median_m': position_median,
        'position_fit_rmse_mad_m': position_mad,
        'heading_fit_rmse_upper_rad': heading_threshold,
        'heading_fit_rmse_median_rad': heading_median,
        'heading_fit_rmse_mad_rad': heading_mad,
        'g0_rule': ('reliable fit, transformed map anchor agrees with its claimed '
                    'historical world pose within 0.5 normalized gate units, and '
                    '|raw_norm-aligned_norm| <= 0.25'),
        'g1_rule': ('not assignable in this corpus: the old raw gate already compares '
                    'two Stage-world poses, so it contains no direct map/world '
                    'subtraction that a global gauge transform can repair'),
        'g2_rule': ('unreliable fit, target-correspondence mismatch, or raw/aligned '
                    'difference not compatible with one global target transform'),
        'outcome_blindness': ('thresholds use all history-only fit residuals; no old '
                              'status, action outcome, or new constraint outcome is used'),
    }


def write_csv(path, rows, fields):
    with open(path, 'w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def quantiles(values):
    values = np.asarray(values, dtype=float)
    return {key: float(value) for key, value in zip(
        ('min', 'q25', 'median', 'q75', 'max'),
        np.quantile(values, [0, 0.25, 0.5, 0.75, 1]))}


def make_plots(rows, output_dir):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    labels = [row['episode_id'] + '/' + Path(row['attempt_dir']).name for row in rows]
    for metric, unit in (('position', 'm'), ('heading', 'rad')):
        raw = [row['raw_{}_error_{}'.format(metric, unit)] for row in rows]
        aligned = [row['aligned_{}_error_{}'.format(metric, unit)] for row in rows]
        figure, axis = plt.subplots(figsize=(7, 6))
        axis.scatter(raw, aligned, c=['tab:orange' if row['old_status'] != 'SUCCEEDED'
                                      else 'tab:blue' for row in rows])
        limit = max(raw + aligned + [0.01]) * 1.05
        axis.plot([0, limit], [0, limit], '--', color='0.5', label='raw = aligned')
        axis.set(xlabel='raw {} error ({})'.format(metric, unit),
                 ylabel='SE(2)-aligned {} error ({})'.format(metric, unit),
                 title='v8 N1 raw vs gauge-aware {} error'.format(metric))
        axis.grid(alpha=0.25)
        axis.legend()
        figure.tight_layout()
        figure.savefig(output_dir / 'raw_vs_aligned_{}_error.png'.format(metric), dpi=180)
        plt.close(figure)

    figure, axes = plt.subplots(1, 2, figsize=(12, 5))
    x = np.arange(len(rows))
    axes[0].bar(x, [row['rmse_before_alignment_m'] for row in rows], label='identity')
    axes[0].bar(x, [row['rmse_after_alignment_m'] for row in rows], label='SE(2) fit')
    axes[0].set_ylabel('history endpoint RMSE (m)')
    axes[0].set_yscale('log')
    axes[0].legend()
    axes[1].scatter([row['tx'] for row in rows], [row['ty'] for row in rows],
                    c=[row['yaw'] for row in rows], cmap='coolwarm')
    axes[1].set(xlabel='T_W_M tx (m)', ylabel='T_W_M ty (m)',
                title='Per-attempt rigid transforms')
    for axis in axes:
        axis.grid(alpha=0.25)
    figure.suptitle('History-only frame alignment ({} attempts)'.format(len(labels)))
    figure.tight_layout()
    figure.savefig(output_dir / 'trajectory_alignment_examples.png', dpi=180)
    plt.close(figure)


def audit(input_dir, output_dir):
    attempts = sorted(Path(input_dir).glob('episodes/*/attempt_*'))
    rows = []
    failures = []
    for attempt in attempts:
        try:
            rows.append(fit_attempt(attempt))
        except Exception as exc:
            failures.append({'attempt_dir': str(attempt), 'error': repr(exc)})
    if not rows:
        raise RuntimeError('no auditable attempts found under {}'.format(input_dir))
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rules = classify(rows)

    alignment_fields = [
        'attempt_dir', 'episode_id', 'block_id', 'condition_id', 'target_id',
        'old_status', 'old_reason', 'fit_source', 'number_of_pairs', 'fit_spread_m',
        'tx', 'ty', 'yaw', 'rmse_before_alignment_m', 'rmse_after_alignment_m',
        'max_error_before_m', 'max_error_after_m', 'heading_rmse_after_rad',
        'heading_max_after_rad', 'se2_fit_reliable', 'arrival_gauge_class',
        'old_gate_audit_label', 'preprobe_node_count', 'preprobe_edge_count',
        'preprobe_node_id_set_hash', 'preprobe_edge_endpoint_set_hash',
        'preprobe_corrected_path_length_m',
        'anchor_to_reference_distance_m', 'anchor_to_reference_heading_rad',
        'exact_preprobe_signature_repetitions_in_block',
        'distinct_preprobe_signatures_in_block',
        'independent_history_structural_divergence']
    arrival_fields = [
        'attempt_dir', 'episode_id', 'condition_id', 'target_id', 'old_status',
        'raw_position_error_m', 'aligned_position_error_m',
        'raw_heading_error_rad', 'aligned_heading_error_rad',
        'raw_normalized_gate_error', 'aligned_normalized_gate_error',
        'normalized_gate_error_reduction', 'aligned_to_raw_ratio',
        'target_correspondence_normalized_error',
        'old_expected_vs_aligned_target_position_m',
        'old_expected_vs_aligned_target_heading_rad', 'aligned_target_world_x',
        'aligned_target_world_y', 'aligned_target_world_yaw',
        'actual_probe_world_x', 'actual_probe_world_y', 'actual_probe_world_yaw',
        'arrival_gauge_class', 'old_gate_audit_label']
    write_csv(output_dir / 'frame_alignment_per_attempt.csv', rows, alignment_fields)
    write_csv(output_dir / 'arrival_error_raw_vs_aligned.csv', rows, arrival_fields)

    classes = Counter(row['arrival_gauge_class'] for row in rows)
    summary = {
        'audit_version': 'v9-frame-gauge-audit-1',
        'input_dir': str(Path(input_dir).resolve()),
        'attempts_discovered': len(attempts),
        'attempts_audited': len(rows),
        'attempts_not_audited': failures,
        'fit_definition': ('one no-scale SE(2) transform from history move endpoint '
                           'map TF poses to Stage world base poses; probe excluded'),
        'saved_gt_trajectory_note': ('trajectory_gt.txt is a shifted laser trajectory, '
                                     'not the raw Stage base pose used by the old gate'),
        'classification_rules': rules,
        'class_counts': dict(classes),
        'raw_position_error_m': quantiles([row['raw_position_error_m'] for row in rows]),
        'aligned_position_error_m': quantiles(
            [row['aligned_position_error_m'] for row in rows]),
        'raw_heading_error_rad': quantiles([row['raw_heading_error_rad'] for row in rows]),
        'aligned_heading_error_rad': quantiles(
            [row['aligned_heading_error_rad'] for row in rows]),
        'target_correspondence_position_error_m': quantiles(
            [row['old_expected_vs_aligned_target_position_m'] for row in rows]),
        'target_correspondence_heading_error_rad': quantiles(
            [row['old_expected_vs_aligned_target_heading_rad'] for row in rows]),
        'transform_tx_m': quantiles([row['tx'] for row in rows]),
        'transform_ty_m': quantiles([row['ty'] for row in rows]),
        'transform_yaw_rad': quantiles([row['yaw'] for row in rows]),
        'alignment_position_rmse_m': quantiles(
            [row['rmse_after_alignment_m'] for row in rows]),
        'alignment_heading_rmse_rad': quantiles(
            [row['heading_rmse_after_rad'] for row in rows]),
        'blocks_with_nonidentical_preprobe_signatures': sorted({
            row['block_id'] for row in rows
            if row['independent_history_structural_divergence']}),
        'retrospective_relabel_performed': False,
        'old_gate_failures': sum(
            1 for row in rows if row['raw_position_error_m'] > OLD_POSITION_GATE_M
            or row['raw_heading_error_rad'] > OLD_HEADING_GATE_RAD),
        'aligned_map_goal_failures': sum(
            1 for row in rows if row['aligned_position_error_m'] > OLD_POSITION_GATE_M
            or row['aligned_heading_error_rad'] > OLD_HEADING_GATE_RAD),
    }
    with open(output_dir / 'frame_alignment_summary.json', 'w') as stream:
        json.dump(summary, stream, indent=2, sort_keys=True)
        stream.write('\n')

    audit_payload = {
        'question_1': {
            'answer': 'NO_DIRECT_MAP_WORLD_SUBTRACTION_FLAW',
            'reason': ('the old gate compared the current Stage-world base pose with a '
                       'stored Stage-world history pose.  The actual defect is a target '
                       'correspondence mismatch: navigation used a nearby Karto keyscan '
                       'anchor, while the GT gate used the history waypoint endpoint as '
                       'if it were that same observation'),
        },
        'question_2': {
            'gauge_dominated_attempt_count': classes.get('G1_GAUGE_DOMINATED', 0),
            'total_audited_attempt_count': len(rows),
            'old_gate_failure_count': summary['old_gate_failures'],
            'aligned_map_goal_failure_count': summary['aligned_map_goal_failures'],
            'interpretation': ('the SE(2)-aligned numbers show map-goal arrival, not '
                               'physical return to the stored historical observation; '
                               'they must not be called rescued old episodes'),
            'continuous_metrics_file': 'arrival_error_raw_vs_aligned.csv',
        },
        'question_3': {
            'blocks_with_exact_common_preprobe_graph': [],
            'blocks_with_structurally_different_independent_histories':
                summary['blocks_with_nonidentical_preprobe_signatures'],
            'interpretation': ('global SE(2) can align poses but cannot change node count, '
                               'edge topology, or keyscan identity; those differences are '
                               'genuine independent-history structural divergence'),
        },
        'attempt_diagnostics': rows,
        'old_results_preserved': True,
        'warning': ('post-hoc diagnostic only; no old FAILED or SUCCEEDED label was '
                    'changed and these results must not enter the v8 effect analysis'),
    }
    with open(output_dir / 'old_n1_frame_confusion_audit.json', 'w') as stream:
        json.dump(audit_payload, stream, indent=2, sort_keys=True)
        stream.write('\n')
    make_plots(rows, output_dir)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-dir', required=True)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    summary = audit(args.input_dir, args.output_dir)
    print(json.dumps({
        'attempts_audited': summary['attempts_audited'],
        'class_counts': summary['class_counts'],
        'output_dir': str(Path(args.output_dir).resolve()),
    }, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
