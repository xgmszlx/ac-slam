#!/usr/bin/python3
"""Pure-geometry helpers shared by the analysis and its tests.

Everything here is outcome-blind: no function reads an action label or a gain.
The 2-D alignment is a single rigid transform (yaw + translation) fitted once
per trajectory, so a continuous trajectory keeps its consecutive distances
exactly -- the property the stitched baseline could not offer.
"""

import math

#: 2-D transform as (yaw, tx, ty).
IDENTITY = (0.0, 0.0, 0.0)

#: Laser frame offset in the robot base frame (metres, x forward).
LASER_OFFSET_X = 0.20
LASER_OFFSET_Y = 0.0


def wrap_angle(value):
    return math.atan2(math.sin(float(value)), math.cos(float(value)))


def path_length(samples):
    total = 0.0
    for first, second in zip(samples, samples[1:]):
        total += math.hypot(second[0] - first[0], second[1] - first[1])
    return total


def cumulative_rotation(samples):
    total = 0.0
    for first, second in zip(samples, samples[1:]):
        total += abs(wrap_angle(second[2] - first[2]))
    return total


def consecutive_distances(points):
    return [math.hypot(second[0] - first[0], second[1] - first[1])
            for first, second in zip(points, points[1:])]


def pose_apply(transform, pose):
    yaw, tx, ty = transform
    cos_yaw, sin_yaw = math.cos(yaw), math.sin(yaw)
    x, y = float(pose[0]), float(pose[1])
    return (cos_yaw * x - sin_yaw * y + tx,
            sin_yaw * x + cos_yaw * y + ty,
            wrap_angle(pose[2] + yaw) if len(pose) > 2 else 0.0)


def align_rigid(source, target):
    """Least-squares yaw + translation taking ``source`` onto ``target``.

    Both inputs are sequences of 2-D points with equal length.  Returns
    ``(yaw, tx, ty)``.  This is the only alignment used by the analysis; it is
    fitted once per trajectory so that continuity is a property of the data and
    not of the stitching.
    """
    if len(source) != len(target) or len(source) < 2:
        raise ValueError('alignment needs equally sized point pairs')
    source_mean_x = sum(p[0] for p in source) / len(source)
    source_mean_y = sum(p[1] for p in source) / len(source)
    target_mean_x = sum(p[0] for p in target) / len(target)
    target_mean_y = sum(p[1] for p in target) / len(target)
    covariance = 0.0
    variance = 0.0
    for point_source, point_target in zip(source, target):
        source_x = point_source[0] - source_mean_x
        source_y = point_source[1] - source_mean_y
        target_x = point_target[0] - target_mean_x
        target_y = point_target[1] - target_mean_y
        covariance += source_x * target_y - source_y * target_x
        variance += source_x * target_x + source_y * target_y
    yaw = math.atan2(covariance, variance)
    cos_yaw, sin_yaw = math.cos(yaw), math.sin(yaw)
    tx = target_mean_x - (cos_yaw * source_mean_x - sin_yaw * source_mean_y)
    ty = target_mean_y - (sin_yaw * source_mean_x + cos_yaw * source_mean_y)
    return (yaw, tx, ty)


def apply_rigid(transform, points):
    return [pose_apply(transform, point)[:2] for point in points]


def residuals(source, target, transform):
    moved = apply_rigid(transform, source)
    return [math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(moved, target)]


def laser_hits(odom_pose, ranges, angle_min, angle_increment, indices,
               laser_offset_x=LASER_OFFSET_X, laser_offset_y=LASER_OFFSET_Y):
    """Map valid laser returns to odometry-frame points.

    ``odom_pose`` is the odometry pose of the *base* frame (x, y, yaw).  The
    laser sits at ``laser_offset`` in the base frame; a return at beam ``i`` has
    bearing ``angle_min + i * angle_increment`` in the laser frame.
    """
    base_x, base_y, base_yaw = (float(odom_pose[0]), float(odom_pose[1]),
                                float(odom_pose[2]))
    cos_base, sin_base = math.cos(base_yaw), math.sin(base_yaw)
    laser_x = base_x + cos_base * laser_offset_x - sin_base * laser_offset_y
    laser_y = base_y + sin_base * laser_offset_x + cos_base * laser_offset_y
    laser_yaw = base_yaw
    hits = []
    for index in indices:
        distance = float(ranges[index])
        if not math.isfinite(distance) or distance <= 0.0:
            continue
        bearing = float(angle_min) + index * float(angle_increment)
        total = laser_yaw + bearing
        hits.append((laser_x + math.cos(total) * distance,
                     laser_y + math.sin(total) * distance))
    return hits


def truncate_frames(records, start_index, count):
    """Select ``count`` contiguous records starting at ``start_index``.

    Records carry a monotone ``index`` field.  The function refuses to invent,
    repeat or skip frames: it returns exactly ``count`` consecutive records or
    raises.  This is the chaining contract of the continuous pipeline.
    """
    ordered = sorted(records, key=lambda record: record['index'])
    selected = [record for record in ordered if record['index'] >= start_index]
    if len(selected) < count:
        raise ValueError('phase has {} frames, needs {}'.format(len(selected),
                                                                count))
    selected = selected[:count]
    for offset, record in enumerate(selected):
        if record['index'] != selected[0]['index'] + offset:
            raise ValueError('frame indices are not contiguous around {}'.format(
                start_index))
    return selected
