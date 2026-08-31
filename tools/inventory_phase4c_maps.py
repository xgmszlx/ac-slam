#!/usr/bin/env python3
"""Blind inventory and topology-only selection of existing author maps."""

import argparse
import csv
import json
import math
import re
import sys
from itertools import combinations
from pathlib import Path

import networkx as nx
import numpy as np
import yaml
from PIL import Image
from scipy.ndimage import distance_transform_edt, label
from skimage.morphology import medial_axis


def parse_world(path):
    text = Path(path).read_text(encoding="utf-8")
    sizes = re.findall(r"size\s*\[([^]]+)\]", text)
    poses = re.findall(r"pose\s*\[([^]]+)\]", text)
    if not sizes or not poses:
        raise ValueError("missing size/start pose in {}".format(path))
    size = [float(value) for value in sizes[-1].split()[:2]]
    start = [float(value) for value in poses[-1].split()]
    return size, start


def skeleton_metrics(free, resolution):
    skeleton, clearance = medial_axis(free, return_distance=True)
    points = np.argwhere(skeleton)
    index = {tuple(point): idx for idx, point in enumerate(points)}
    degrees = np.zeros(len(points), dtype=int)
    edge_count = 0
    length_cells = 0.0
    for idx, (row, col) in enumerate(points):
        for dr, dc in ((0, 1), (1, -1), (1, 0), (1, 1)):
            neighbour = (row + dr, col + dc)
            other = index.get(neighbour)
            if other is None:
                continue
            edge_count += 1
            length_cells += math.sqrt(2.0) if dr and dc else 1.0
            degrees[idx] += 1
            degrees[other] += 1
    junction_pixels = np.zeros_like(skeleton, dtype=bool)
    junction_points = points[degrees >= 3]
    if len(junction_points):
        junction_pixels[junction_points[:, 0], junction_points[:, 1]] = True
    junction_count = int(label(junction_pixels, structure=np.ones((3, 3), dtype=int))[1])
    components = int(label(skeleton, structure=np.ones((3, 3), dtype=int))[1])
    length_m = float(length_cells * resolution)
    cycle_rank = int(edge_count - len(points) + components)
    return {
        "free_space_skeleton_length_m": length_m,
        "skeleton_junction_count": junction_count,
        "skeleton_junction_density_per_100m": (
            100.0 * junction_count / length_m if length_m > 0 else None
        ),
        "skeleton_cycle_count": cycle_rank,
        "median_corridor_width_m": float(2.0 * np.median(clearance[skeleton]) * resolution),
    }


def load_prior(xml_path, width):
    script_dir = Path("baseline/Graph-Based_SLAM-Aware_Exploration/scripts").resolve()
    sys.path.insert(0, str(script_dir))
    from read_drawio_to_nx import build_prior_map_from_drawio
    return build_prior_map_from_drawio(
        str(xml_path), actual_map_width=width,
        need_normalize=False, need_noise=False, variance=0,
    )


def inventory_map(map_dir):
    name = map_dir.name
    yaml_path = map_dir / (name + ".yaml")
    world_path = map_dir / (name + ".world")
    xml_path = map_dir / (name + ".xml")
    metadata = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    image_path = map_dir / metadata["image"]
    image = np.asarray(Image.open(image_path).convert("L"), dtype=float)
    probability = (255.0 - image) / 255.0 if not int(metadata.get("negate", 0)) else image / 255.0
    occupied = probability > float(metadata.get("occupied_thresh", 0.65))
    free = probability < float(metadata.get("free_thresh", 0.196))
    resolution = float(metadata["resolution"])
    world_size, stage_start = parse_world(world_path)
    prior = load_prior(xml_path, world_size[0])
    known = occupied | free
    metrics = skeleton_metrics(free, resolution)
    prior_cycles = prior.number_of_edges() - prior.number_of_nodes() + nx.number_connected_components(prior)
    expected_size = [image.shape[1] * resolution, image.shape[0] * resolution]
    size_consistent = all(abs(a - b) <= max(resolution, 1e-6) for a, b in zip(world_size, expected_size))
    origin = metadata["origin"]
    start_col = int(math.floor((0.0 - float(origin[0])) / resolution))
    start_grid_y = int(math.floor((0.0 - float(origin[1])) / resolution))
    start_row = image.shape[0] - 1 - start_grid_y
    start_free = (
        0 <= start_row < image.shape[0] and 0 <= start_col < image.shape[1]
        and bool(free[start_row, start_col])
    )
    row = {
        "map_name": name,
        "world_path": str(world_path), "gt_yaml_path": str(yaml_path),
        "gt_image_path": str(image_path), "prior_graph_path": str(xml_path),
        "stage_start_pose": json.dumps(stage_start), "map_frame_start_pose": json.dumps([0.0, 0.0, 0.0]),
        "width_m": world_size[0], "height_m": world_size[1], "aspect_ratio": world_size[0] / world_size[1],
        "resolution_m": resolution,
        "free_area_m2": float(free.sum() * resolution ** 2),
        "obstacle_fraction_known": float(occupied.sum() / known.sum()),
        "prior_graph_nodes": prior.number_of_nodes(), "prior_graph_edges": prior.number_of_edges(),
        "prior_graph_cycle_rank": int(prior_cycles),
        "baseline_launch_support": True,
        "evaluation_GT_ready": bool(size_consistent and start_free),
        "world_image_size_consistent": bool(size_consistent), "map_frame_start_is_free": bool(start_free),
    }
    row.update(metrics)
    return row


def select_maps(rows):
    # Frozen topology-only features.  Standardization is across all inventoried
    # author maps and uses no A/B/C performance observation.
    features = [
        "aspect_ratio", "obstacle_fraction_known",
        "skeleton_junction_density_per_100m", "skeleton_cycle_count",
        "median_corridor_width_m", "prior_graph_cycle_rank",
    ]
    values = np.array([[float(row[key]) for key in features] for row in rows], dtype=float)
    scale = values.std(axis=0)
    scale[scale == 0] = 1.0
    standardized = (values - values.mean(axis=0)) / scale
    index = {row["map_name"]: idx for idx, row in enumerate(rows)}
    if "map3" not in index:
        raise ValueError("map3 must be present as M1")
    eligible = [row["map_name"] for row in rows if row["map_name"] != "map3" and row["evaluation_GT_ready"]]

    def distance(a, b):
        return float(np.linalg.norm(standardized[index[a]] - standardized[index[b]]))

    candidates = []
    for first, second in combinations(eligible, 2):
        score = distance("map3", first) + distance("map3", second) + distance(first, second)
        candidates.append({
            "maps": [first, second], "diversity_score": score,
            "distance_M1_first": distance("map3", first),
            "distance_M1_second": distance("map3", second),
            "distance_between_new_maps": distance(first, second),
        })
    candidates.sort(key=lambda item: (-item["diversity_score"], item["maps"]))
    selected = candidates[0]
    return {
        "selection_status": "FROZEN_BEFORE_NEW_MAP_PERFORMANCE_RUNS",
        "performance_results_consulted": False,
        "M1": "map3", "M2": selected["maps"][0], "M3": selected["maps"][1],
        "selection_features": features,
        "standardization": "population z-score across existing author maps",
        "pair_rule": "maximize d(M1,M2)+d(M1,M3)+d(M2,M3)",
        "selected_pair_metrics": selected,
        "all_pair_scores": candidates,
        "label_policy": "topology-distinct; corridor/room labels are descriptive only and are not forced",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--world-root", type=Path,
                        default=Path("baseline/Graph-Based_SLAM-Aware_Exploration/world"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/phase4c0/maps"))
    args = parser.parse_args()
    rows = [inventory_map(path) for path in sorted(args.world_root.glob("map*")) if path.is_dir()]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "map_inventory.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    selection = select_maps(rows)
    (args.output_dir / "map_selection.json").write_text(
        json.dumps(selection, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(selection, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
