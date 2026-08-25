#!/usr/bin/python3
"""Deterministic offline occupancy-map evaluation for Phase 4B.

The estimated map is sampled at ground-truth cell centres using the two saved map
origins.  No data-dependent registration or trajectory alignment is performed.
"""

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml
from PIL import Image
from scipy.ndimage import binary_erosion, distance_transform_edt


@dataclass
class MapGrid:
    state: np.ndarray  # int8: -1 unknown, 0 free, 1 occupied; image row order
    resolution: float
    origin_x: float
    origin_y: float
    origin_yaw: float
    image_path: Path
    yaml_path: Path
    occupied_thresh: float
    free_thresh: float
    negate: int

    @property
    def height(self):
        return int(self.state.shape[0])

    @property
    def width(self):
        return int(self.state.shape[1])


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def finite_float(value, default=None):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = float('nan')
    if math.isfinite(parsed):
        return parsed
    if default is None:
        raise ValueError('non-finite numeric value: {!r}'.format(value))
    return float(default)


def load_map(yaml_path):
    yaml_path = Path(yaml_path).resolve()
    metadata = yaml.safe_load(yaml_path.read_text(encoding='utf-8'))
    image_path = Path(metadata['image'])
    if not image_path.is_absolute():
        image_path = (yaml_path.parent / image_path).resolve()
    gray = np.asarray(Image.open(str(image_path)).convert('L'), dtype=np.float64)
    negate = int(metadata.get('negate', 0))
    probability = gray / 255.0 if negate else (255.0 - gray) / 255.0
    occupied_thresh = finite_float(metadata.get('occupied_thresh', 0.65))
    free_thresh = finite_float(metadata.get('free_thresh', 0.196))
    state = np.full(gray.shape, -1, dtype=np.int8)
    state[probability > occupied_thresh] = 1
    state[probability < free_thresh] = 0
    origin = metadata.get('origin', [0.0, 0.0, 0.0])
    if len(origin) < 3:
        raise ValueError('map origin must contain x, y, yaw')
    return MapGrid(
        state=state,
        resolution=finite_float(metadata['resolution']),
        origin_x=finite_float(origin[0]),
        origin_y=finite_float(origin[1]),
        # map_saver on this stack writes -nan for a zero yaw; freeze it to zero.
        origin_yaw=finite_float(origin[2], default=0.0),
        image_path=image_path,
        yaml_path=yaml_path,
        occupied_thresh=occupied_thresh,
        free_thresh=free_thresh,
        negate=negate,
    )


def sample_source_on_target(source, target):
    """Nearest-cell sample of source at every target cell centre."""
    rows, cols = np.indices((target.height, target.width), dtype=np.float64)
    target_grid_y = target.height - 1.0 - rows
    tx = (cols + 0.5) * target.resolution
    ty = (target_grid_y + 0.5) * target.resolution
    t_cos = math.cos(target.origin_yaw)
    t_sin = math.sin(target.origin_yaw)
    world_x = target.origin_x + t_cos * tx - t_sin * ty
    world_y = target.origin_y + t_sin * tx + t_cos * ty

    dx = world_x - source.origin_x
    dy = world_y - source.origin_y
    s_cos = math.cos(source.origin_yaw)
    s_sin = math.sin(source.origin_yaw)
    local_x = s_cos * dx + s_sin * dy
    local_y = -s_sin * dx + s_cos * dy
    source_cols = np.floor(local_x / source.resolution).astype(np.int64)
    source_grid_y = np.floor(local_y / source.resolution).astype(np.int64)
    source_rows = source.height - 1 - source_grid_y
    valid = (
        (source_cols >= 0) & (source_cols < source.width)
        & (source_rows >= 0) & (source_rows < source.height)
    )
    sampled = np.full(target.state.shape, -1, dtype=np.int8)
    sampled[valid] = source.state[source_rows[valid], source_cols[valid]]
    return sampled


def safe_ratio(numerator, denominator, both_empty_value=1.0):
    if denominator == 0:
        return float(both_empty_value)
    return float(numerator) / float(denominator)


def occupied_boundary(mask):
    structure = np.ones((3, 3), dtype=bool)
    return mask & ~binary_erosion(mask, structure=structure, border_value=0)


def boundary_scores(gt_boundary, est_boundary, resolution, tolerance_m):
    gt_count = int(gt_boundary.sum())
    est_count = int(est_boundary.sum())
    if gt_count == 0 and est_count == 0:
        return {
            'precision': 1.0, 'recall': 1.0, 'f1': 1.0,
            'gt_boundary_cells': 0, 'estimated_boundary_cells': 0,
            'estimated_matched_cells': 0, 'gt_matched_cells': 0,
        }
    if gt_count == 0 or est_count == 0:
        return {
            'precision': 0.0, 'recall': 0.0, 'f1': 0.0,
            'gt_boundary_cells': gt_count, 'estimated_boundary_cells': est_count,
            'estimated_matched_cells': 0, 'gt_matched_cells': 0,
        }
    distance_to_gt = distance_transform_edt(~gt_boundary, sampling=resolution)
    distance_to_est = distance_transform_edt(~est_boundary, sampling=resolution)
    est_matched = int((est_boundary & (distance_to_gt <= tolerance_m + 1e-12)).sum())
    gt_matched = int((gt_boundary & (distance_to_est <= tolerance_m + 1e-12)).sum())
    precision = safe_ratio(est_matched, est_count, both_empty_value=0.0)
    recall = safe_ratio(gt_matched, gt_count, both_empty_value=0.0)
    f1 = 0.0 if precision + recall == 0 else 2.0 * precision * recall / (precision + recall)
    return {
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'gt_boundary_cells': gt_count,
        'estimated_boundary_cells': est_count,
        'estimated_matched_cells': est_matched,
        'gt_matched_cells': gt_matched,
    }


def evaluate_maps(gt, estimated, boundary_tolerance_m=0.20):
    if boundary_tolerance_m < 0:
        raise ValueError('boundary tolerance must be non-negative')
    estimated_on_gt = sample_source_on_target(estimated, gt)
    domain = gt.state >= 0
    gt_occ = (gt.state == 1) & domain
    est_occ = (estimated_on_gt == 1) & domain
    gt_free = (gt.state == 0) & domain
    est_free = (estimated_on_gt == 0) & domain

    occ_intersection = int((gt_occ & est_occ).sum())
    occ_union = int((gt_occ | est_occ).sum())
    free_intersection = int((gt_free & est_free).sum())
    free_union = int((gt_free | est_free).sum())
    gt_boundary = occupied_boundary(gt_occ)
    est_boundary = occupied_boundary(est_occ)
    boundary = boundary_scores(
        gt_boundary, est_boundary, gt.resolution, boundary_tolerance_m
    )
    domain_count = int(domain.sum())
    estimated_unknown = int(((estimated_on_gt < 0) & domain).sum())
    return {
        'protocol': {
            'registration': 'identity map-frame rule; deterministic cell-centre resampling',
            'registration_transform_xyyaw': [0.0, 0.0, 0.0],
            'gt_unknown_policy': 'excluded from evaluation domain',
            'estimated_unknown_policy': (
                'neither occupied nor free inside GT-known domain; therefore false negative '
                'where the GT class is occupied/free'
            ),
            'occupied_boundary': 'occupied minus one 8-neighbour 3x3 binary erosion',
            'boundary_tolerance_m': float(boundary_tolerance_m),
            'sampling': 'nearest source cell at each GT cell centre',
        },
        'grid': {
            'gt': grid_metadata(gt),
            'estimated': grid_metadata(estimated),
            'evaluation_domain_cells': domain_count,
        },
        'occupied_iou': {
            'value': safe_ratio(occ_intersection, occ_union),
            'intersection_cells': occ_intersection,
            'union_cells': occ_union,
            'gt_occupied_cells': int(gt_occ.sum()),
            'estimated_occupied_cells': int(est_occ.sum()),
        },
        'occupied_boundary_f1': boundary,
        'supporting': {
            'free_iou': safe_ratio(free_intersection, free_union),
            'free_intersection_cells': free_intersection,
            'free_union_cells': free_union,
            'estimated_unknown_cells_in_gt_known_domain': estimated_unknown,
            'estimated_unknown_ratio': safe_ratio(
                estimated_unknown, domain_count, both_empty_value=0.0
            ),
            'gt_unknown_cells_excluded': int((gt.state < 0).sum()),
        },
    }


def grid_metadata(grid):
    return {
        'yaml': str(grid.yaml_path),
        'image': str(grid.image_path),
        'yaml_sha256': sha256_file(grid.yaml_path),
        'image_sha256': sha256_file(grid.image_path),
        'width': grid.width,
        'height': grid.height,
        'resolution_m': grid.resolution,
        'origin_xyyaw': [grid.origin_x, grid.origin_y, grid.origin_yaw],
        'occupied_thresh': grid.occupied_thresh,
        'free_thresh': grid.free_thresh,
        'negate': grid.negate,
        'occupied_cells': int((grid.state == 1).sum()),
        'free_cells': int((grid.state == 0).sum()),
        'unknown_cells': int((grid.state < 0).sum()),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gt-yaml', required=True, type=Path)
    parser.add_argument('--estimated-yaml', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--boundary-tolerance-m', type=float, default=0.20)
    args = parser.parse_args()
    result = evaluate_maps(
        load_map(args.gt_yaml), load_map(args.estimated_yaml),
        boundary_tolerance_m=args.boundary_tolerance_m,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )
    print(json.dumps({
        'occupied_iou': result['occupied_iou']['value'],
        'boundary_f1': result['occupied_boundary_f1']['f1'],
        'estimated_unknown_ratio': result['supporting']['estimated_unknown_ratio'],
    }, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
