#!/usr/bin/python3
"""Frozen-gauge Stage-GT sanity metrics for a future v14 analysis."""

import math

import numpy as np


def wrap_angle(value):
    return math.atan2(math.sin(value), math.cos(value))


def freeze_world_gauge(pre_slam_poses, pre_gt_poses):
    """Fit one SE(2) gauge using pre-treatment canonical history only."""
    slam = np.asarray(pre_slam_poses, dtype=float)
    gt = np.asarray(pre_gt_poses, dtype=float)
    if slam.ndim != 2 or gt.ndim != 2 or slam.shape != gt.shape:
        raise ValueError('pre-treatment SLAM/GT pose arrays must match')
    if slam.shape[0] < 2 or slam.shape[1] < 2:
        raise ValueError('at least two 2D pose correspondences are required')
    source = slam[:, :2]
    target = gt[:, :2]
    source_center = source.mean(axis=0)
    target_center = target.mean(axis=0)
    cross = (source - source_center).T @ (target - target_center)
    left, _singular, right_t = np.linalg.svd(cross)
    rotation = right_t.T @ left.T
    if np.linalg.det(rotation) < 0:
        right_t[-1, :] *= -1
        rotation = right_t.T @ left.T
    translation = target_center - rotation @ source_center
    yaw = math.atan2(rotation[1, 0], rotation[0, 0])
    return {'rotation': rotation.tolist(), 'translation': translation.tolist(),
            'yaw': yaw, 'fit_source': 'PRE_TREATMENT_CANONICAL_HISTORY_ONLY'}


def transform_pose(pose, gauge):
    rotation = np.asarray(gauge['rotation'], dtype=float)
    translation = np.asarray(gauge['translation'], dtype=float)
    xy = rotation @ np.asarray(pose[:2], dtype=float) + translation
    yaw = wrap_angle(float(pose[2]) + float(gauge['yaw']))
    return [float(xy[0]), float(xy[1]), yaw]


def target_state_errors(slam_poses, gt_poses, gauge):
    if len(slam_poses) != len(gt_poses) or not slam_poses:
        raise ValueError('non-empty target pose arrays must have equal length')
    transformed = [transform_pose(pose, gauge) for pose in slam_poses]
    translations = [math.hypot(est[0] - gt[0], est[1] - gt[1])
                    for est, gt in zip(transformed, gt_poses)]
    headings = [abs(wrap_angle(est[2] - gt[2]))
                for est, gt in zip(transformed, gt_poses)]
    return {
        'translation_rmse_m': math.sqrt(
            sum(value * value for value in translations) / len(translations)),
        'heading_mae_rad': sum(headings) / len(headings),
        'heading_rmse_rad': math.sqrt(
            sum(value * value for value in headings) / len(headings)),
        'per_state_translation_error_m': translations,
        'per_state_heading_error_rad': headings,
    }


def estimator_effect_sanity(before_slam, after_slam, gt_poses, gauge):
    before = target_state_errors(before_slam, gt_poses, gauge)
    after = target_state_errors(after_slam, gt_poses, gauge)
    corrections = [
        math.hypot(a[0] - b[0], a[1] - b[1])
        for a, b in zip(after_slam, before_slam)]
    return {
        'before': before,
        'after': after,
        'delta_translation_rmse_m': (
            before['translation_rmse_m'] - after['translation_rmse_m']),
        'delta_heading_mae_rad': (
            before['heading_mae_rad'] - after['heading_mae_rad']),
        'delta_heading_rmse_rad': (
            before['heading_rmse_rad'] - after['heading_rmse_rad']),
        'max_historical_target_state_correction_m': max(corrections),
        'mean_historical_target_state_correction_m': (
            sum(corrections) / len(corrections)),
    }
