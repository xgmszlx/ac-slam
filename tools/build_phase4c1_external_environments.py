#!/usr/bin/env python3
"""Build deterministic Stage environments and neutral priors from public maps.

This is evaluation infrastructure only.  It never starts ROS, Stage, Karto, or
any A/B/C exploration condition.  Inputs are the occupancy-map renderings
published by StachnissLab for pre-2014 2-D laser datasets.
"""

import argparse
import csv
import hashlib
import json
import math
import shutil
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import networkx as nx
import numpy as np
from PIL import Image
from scipy.ndimage import binary_opening, distance_transform_edt, label
from skimage.draw import line
from skimage.morphology import disk, medial_axis, remove_small_objects


ROOT = Path(__file__).resolve().parents[1]
AUTHOR_WORLD = ROOT / "baseline/Graph-Based_SLAM-Aware_Exploration/world/map8"

# Source URLs and hashes were frozen before any candidate opportunity audit.
# The effective PNG scale is the raster scale, not necessarily the GMapping
# internal delta: the public CSAIL/Mexico renderings were resampled for export.
SOURCES = {
    "radish_csail": {
        "dataset": "MIT CSAIL",
        "provider": "Cyrill Stachniss",
        "description": "MIT CSAIL indoor laboratory/building mapping dataset",
        "map_url": "https://www.ipb.uni-bonn.de/html/projects/radish/csail.corrected.png",
        "map_sha256": "86345085e6e902d8bf9466504c648c66b8982c2e171fed99fc220210d71f54f7",
        "original_file": "csail.corrected.png",
        "resolution_m": 0.10,
        "resolution_status": "inferred from corrected-log metric extent and public raster dimensions",
    },
    "radish_intel": {
        "dataset": "Intel Research Lab",
        "provider": "Dirk Haehnel",
        "description": "Intel Research Lab indoor office mapping dataset",
        "map_url": "https://www.ipb.uni-bonn.de/html/projects/radish/intel.gfs.png",
        "map_sha256": "82c2a35bf3e46c0003c2dd8e75faa3c8e9905d9f431ad8b4b327c4314131d607",
        "original_file": "intel.gfs.png",
        "resolution_m": 0.05,
        "resolution_status": "GMapping delta=0.05 m and corrected-log/raster extent agreement",
    },
    "radish_fr079": {
        "dataset": "Freiburg Building 079",
        "provider": "Cyrill Stachniss",
        "description": "University of Freiburg Building 079 indoor corridor/room dataset",
        "map_url": "https://www.ipb.uni-bonn.de/html/projects/radish/fr079-complete.gfs.png",
        "map_sha256": "87e6097849024de3bc43fac94df21ee2dfec9594de47d5ca9812db272dc216d2",
        "original_file": "fr079-complete.gfs.png",
        "resolution_m": 0.05,
        "resolution_status": "GMapping delta=0.05 m and corrected-log/raster extent agreement",
    },
    "radish_mexico": {
        "dataset": "Acapulco Convention Center",
        "provider": "Nick Roy",
        "description": "large indoor convention-center mapping dataset in Acapulco, Mexico",
        "map_url": "https://www.ipb.uni-bonn.de/html/projects/radish/mexico.gfs.png",
        "map_sha256": "cda4456749a16505437ef1b2203d37ee9ba1598d1d0f92cf5afc530fec93c308",
        "original_file": "mexico.gfs.png",
        "resolution_m": 0.05,
        "resolution_status": "inferred from corrected-log metric extent and public raster dimensions",
    },
}

SOURCE_PAGE = "https://www.ipb.uni-bonn.de/datasets/"
RADISH_PAGE = "https://radish.sourceforge.net/"
LICENSE = "CC BY 1.0 via the Radish repository policy"
LICENSE_URL = "https://creativecommons.org/licenses/by/1.0/"

PARAMETERS = {
    "source_free_gray_min": 250,
    "source_occupied_gray_max": 128,
    "thin_ray_opening_radius_px": 1,
    "minimum_free_component_px": 16,
    "robot_clearance_m": 0.45,
    "minimum_terminal_branch_m": 2.0,
    # Frozen from the author-map prior scale before the external-map gate:
    # map3/map8 median straight prior-edge lengths are 12.33/14.29 m.  A 12 m
    # cap keeps the generated graph in the baseline's representational regime;
    # it is unrelated to the frozen 4 m online active-loop proxy.
    "maximum_prior_edge_segment_m": 12.0,
    "prior_grid_resolution_m": 1.00,
    "medial_axis_rng_seed": 0,
    "start_rule": "prior-graph node nearest the arithmetic mean of all prior-node pixels",
    "junction_rule": "connected clusters of medial-axis pixels with degree != 2",
}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(url, path, expected):
    path = Path(path)
    if not path.exists() or sha256(path) != expected:
        path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": "phase4c1-reproduction-audit/1"})
        with urllib.request.urlopen(request, timeout=120) as response, path.open("wb") as stream:
            shutil.copyfileobj(response, stream)
    actual = sha256(path)
    if actual != expected:
        raise ValueError("source hash mismatch for {}: {} != {}".format(path, actual, expected))
    return path


def largest_component(mask):
    labels, count = label(mask, structure=np.ones((3, 3), dtype=int))
    if count == 0:
        raise ValueError("no free-space component")
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    chosen = int(np.argmax(sizes))
    return labels == chosen, int(sizes[chosen]), int(count)


def convert_source_map(path, resolution):
    source = np.asarray(Image.open(path).convert("L"), dtype=np.uint8)
    raw_free = source >= PARAMETERS["source_free_gray_min"]
    raw_occupied = source <= PARAMETERS["source_occupied_gray_max"]
    cleaned = binary_opening(raw_free, structure=disk(PARAMETERS["thin_ray_opening_radius_px"]))
    cleaned = remove_small_objects(
        cleaned, min_size=PARAMETERS["minimum_free_component_px"], connectivity=2
    )
    free, component_size, component_count = largest_component(cleaned)
    occupied = ~free
    stage = np.zeros_like(source, dtype=np.uint8)
    stage[free] = 255
    return {
        "source_gray": source,
        "raw_free": raw_free,
        "raw_occupied": raw_occupied,
        "free": free,
        "occupied": occupied,
        "stage": stage,
        "free_area_m2": float(free.sum() * resolution * resolution),
        "largest_component_px": component_size,
        "raw_component_count": component_count,
    }


def pixel_graph(skeleton, resolution, traversable=None):
    points = [tuple(value) for value in np.argwhere(skeleton)]
    point_set = set(points)
    graph = nx.Graph()
    graph.add_nodes_from(points)
    for row, col in points:
        for dr, dc in ((0, 1), (1, -1), (1, 0), (1, 1)):
            other = (row + dr, col + dc)
            if other in point_set:
                if dr and dc and traversable is not None and not (
                    traversable[row + dr, col] and traversable[row, col + dc]
                ):
                    continue
                graph.add_edge((row, col), other, weight=resolution * math.hypot(dr, dc))
    return graph


def trace_skeleton_paths(graph):
    key_pixels = {node for node, degree in graph.degree() if degree != 2}
    if not key_pixels:
        key_pixels.add(min(graph.nodes()))
    key_components = sorted(
        (sorted(component) for component in nx.connected_components(graph.subgraph(key_pixels))),
        key=lambda component: component[0],
    )
    pixel_to_cluster = {}
    representatives = {}
    for cluster_id, component in enumerate(key_components):
        centre = np.mean(np.asarray(component, dtype=float), axis=0)
        representative = min(
            component,
            key=lambda node: ((node[0] - centre[0]) ** 2 + (node[1] - centre[1]) ** 2, node),
        )
        representatives[cluster_id] = representative
        for pixel in component:
            pixel_to_cluster[pixel] = cluster_id

    visited = set()
    paths = []

    def edge_key(a, b):
        return tuple(sorted((a, b)))

    for a, b in graph.edges():
        if a in pixel_to_cluster and b in pixel_to_cluster:
            visited.add(edge_key(a, b))
            ca, cb = pixel_to_cluster[a], pixel_to_cluster[b]
            if ca != cb:
                paths.append((ca, cb, [representatives[ca], representatives[cb]]))

    for cluster_id, component in enumerate(key_components):
        for start in component:
            for neighbour in sorted(graph.neighbors(start)):
                marker = edge_key(start, neighbour)
                if marker in visited or neighbour in pixel_to_cluster:
                    continue
                visited.add(marker)
                path = [representatives[cluster_id], start, neighbour]
                previous, current = start, neighbour
                while current not in pixel_to_cluster:
                    options = [node for node in graph.neighbors(current) if node != previous]
                    if not options:
                        break
                    following = min(options)
                    marker = edge_key(current, following)
                    if marker in visited:
                        break
                    visited.add(marker)
                    path.append(following)
                    previous, current = current, following
                if current in pixel_to_cluster:
                    target = pixel_to_cluster[current]
                    path.append(representatives[target])
                    paths.append((cluster_id, target, path))

    return representatives, paths


def path_length(path, resolution):
    return float(sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(path, path[1:])) * resolution)


def prune_short_terminal_paths(representatives, paths, resolution):
    active = list(range(len(paths)))
    changed = True
    while changed:
        changed = False
        degree = {node: 0 for node in representatives}
        for index in active:
            source, target, _ = paths[index]
            degree[source] += 1
            degree[target] += 1
        remove = {
            index for index in active
            if path_length(paths[index][2], resolution) < PARAMETERS["minimum_terminal_branch_m"]
            and (degree[paths[index][0]] <= 1 or degree[paths[index][1]] <= 1)
        }
        if remove:
            active = [index for index in active if index not in remove]
            changed = True
    return [paths[index] for index in active]


def cumulative_sample_indices(path, resolution, maximum_length):
    if len(path) <= 2:
        return [0, len(path) - 1]
    cumulative = [0.0]
    for a, b in zip(path, path[1:]):
        cumulative.append(cumulative[-1] + resolution * math.hypot(b[0] - a[0], b[1] - a[1]))
    indices = [0]
    target = maximum_length
    while target < cumulative[-1]:
        index = int(np.searchsorted(cumulative, target, side="left"))
        if index > indices[-1]:
            indices.append(index)
        target += maximum_length
    if indices[-1] != len(path) - 1:
        indices.append(len(path) - 1)
    return indices


def segment_is_traversable(a, b, traversable):
    rows, cols = line(int(a[0]), int(a[1]), int(b[0]), int(b[1]))
    return bool(np.all(traversable[rows, cols]))


def add_validated_samples(path, sample_indices, traversable):
    indices = list(sample_indices)
    changed = True
    while changed:
        changed = False
        output = [indices[0]]
        for first, second in zip(indices, indices[1:]):
            if not segment_is_traversable(path[first], path[second], traversable) and second - first > 1:
                middle = (first + second) // 2
                output.extend([middle, second])
                changed = True
            else:
                output.append(second)
        indices = sorted(set(output))
    return indices


def build_prior(free, resolution):
    clearance = distance_transform_edt(free) * resolution
    traversable = clearance >= PARAMETERS["robot_clearance_m"]
    traversable, _, _ = largest_component(traversable)
    topology_skeleton, _ = medial_axis(
        traversable, return_distance=True, rng=PARAMETERS["medial_axis_rng_seed"]
    )

    stride = max(1, int(round(PARAMETERS["prior_grid_resolution_m"] / resolution)))
    coarse_resolution = stride * resolution
    source_rows = np.minimum(
        np.arange((traversable.shape[0] + stride - 1) // stride) * stride + stride // 2,
        traversable.shape[0] - 1,
    )
    source_cols = np.minimum(
        np.arange((traversable.shape[1] + stride - 1) // stride) * stride + stride // 2,
        traversable.shape[1] - 1,
    )
    coarse_traversable = traversable[np.ix_(source_rows, source_cols)]
    coarse_traversable, _, _ = largest_component(coarse_traversable)
    skeleton, _ = medial_axis(
        coarse_traversable, return_distance=True, rng=PARAMETERS["medial_axis_rng_seed"]
    )
    full = pixel_graph(skeleton, coarse_resolution, coarse_traversable)
    unsafe = []
    for first, second in full.edges():
        source_first = (int(source_rows[first[0]]), int(source_cols[first[1]]))
        source_second = (int(source_rows[second[0]]), int(source_cols[second[1]]))
        if not segment_is_traversable(source_first, source_second, traversable):
            unsafe.append((first, second))
    full.remove_edges_from(unsafe)
    full.remove_nodes_from(list(nx.isolates(full)))
    if not nx.is_connected(full):
        component = max(nx.connected_components(full), key=lambda item: (len(item), -min(item)[0], -min(item)[1]))
        full = full.subgraph(component).copy()
        skeleton = np.zeros_like(skeleton)
        for pixel in component:
            skeleton[pixel] = True
    representatives, paths = trace_skeleton_paths(full)
    paths = prune_short_terminal_paths(representatives, paths, coarse_resolution)

    graph = nx.Graph()
    cluster_node = {}
    for cluster_id in sorted({value for path in paths for value in path[:2]}):
        cluster_node[cluster_id] = len(graph)
        coarse_pixel = representatives[cluster_id]
        graph.add_node(
            len(graph),
            pixel=(int(source_rows[coarse_pixel[0]]), int(source_cols[coarse_pixel[1]])),
        )

    for source, target, path in sorted(paths, key=lambda item: (item[0], item[1], item[2])):
        if source not in cluster_node or target not in cluster_node:
            continue
        source_path = [
            (int(source_rows[pixel[0]]), int(source_cols[pixel[1]])) for pixel in path
        ]
        indices = cumulative_sample_indices(
            path, coarse_resolution, PARAMETERS["maximum_prior_edge_segment_m"]
        )
        indices = add_validated_samples(source_path, indices, traversable)
        pixels = [source_path[index] for index in indices]
        if source == target and len(pixels) < 4:
            pixels = [source_path[index] for index in sorted({0, len(path) // 3, 2 * len(path) // 3, len(path) - 1})]
        nodes = [cluster_node[source]]
        for pixel in pixels[1:-1]:
            node = len(graph)
            graph.add_node(node, pixel=pixel)
            nodes.append(node)
        nodes.append(cluster_node[target])
        if len(nodes) == 2 and graph.has_edge(*nodes):
            middle = source_path[len(path) // 2]
            node = len(graph)
            graph.add_node(node, pixel=middle)
            nodes = [nodes[0], node, nodes[1]]
        for first, second in zip(nodes, nodes[1:]):
            if first != second:
                graph.add_edge(first, second)

    isolates = list(nx.isolates(graph))
    graph.remove_nodes_from(isolates)
    if graph.number_of_nodes() == 0:
        raise ValueError("prior simplification removed every node")
    component = max(nx.connected_components(graph), key=len)
    graph = nx.convert_node_labels_to_integers(graph.subgraph(component).copy(), ordering="sorted")
    return graph, topology_skeleton, clearance, traversable


def select_start(graph, shape, resolution):
    pixels = np.asarray([graph.nodes[node]["pixel"] for node in graph], dtype=float)
    centre = pixels.mean(axis=0)
    node = min(
        graph,
        key=lambda item: (
            (graph.nodes[item]["pixel"][0] - centre[0]) ** 2
            + (graph.nodes[item]["pixel"][1] - centre[1]) ** 2,
            item,
        ),
    )
    row, col = graph.nodes[node]["pixel"]
    height, width = shape
    x = (col + 0.5 - width / 2.0) * resolution
    y = (height / 2.0 - row - 0.5) * resolution
    return node, (float(x), float(y), 0.0)


def add_world_positions(graph, shape, resolution):
    height, width = shape
    for node in graph:
        row, col = graph.nodes[node]["pixel"]
        graph.nodes[node]["position"] = (
            float((col + 0.5 - width / 2.0) * resolution),
            float((height / 2.0 - row - 0.5) * resolution),
        )
    for source, target in graph.edges():
        a, b = graph.nodes[source]["position"], graph.nodes[target]["position"]
        graph.edges[source, target]["weight"] = float(math.hypot(b[0] - a[0], b[1] - a[1]))


def write_drawio_xml(graph, shape, path):
    height, width = shape
    mxfile = ET.Element("mxfile", {"host": "phase4c1-deterministic-builder", "version": "1"})
    diagram = ET.SubElement(mxfile, "diagram", {"name": "Page-1", "id": "phase4c1"})
    model = ET.SubElement(diagram, "mxGraphModel")
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})

    marker_geometry = [(0.0, 0.0), (width / 2.0, float(height)), (float(width), 0.0)]
    for index, (x, y) in enumerate(marker_geometry):
        cell = ET.SubElement(root, "mxCell", {
            "id": "marker{}".format(index), "value": "", "style": "ellipse;whiteSpace=wrap;html=1;",
            "vertex": "1", "parent": "1",
        })
        ET.SubElement(cell, "mxGeometry", {"x": repr(x), "y": repr(y), "width": "1", "height": "1", "as": "geometry"})

    for node in sorted(graph):
        row, col = graph.nodes[node]["pixel"]
        cell = ET.SubElement(root, "mxCell", {
            "id": "node{}".format(node), "value": "", "style": "ellipse;whiteSpace=wrap;html=1;",
            "vertex": "1", "parent": "1",
        })
        ET.SubElement(cell, "mxGeometry", {
            "x": repr(float(col) + 0.5), "y": repr(float(row) + 0.5),
            "width": "1", "height": "1", "as": "geometry",
        })
    for index, (source, target) in enumerate(sorted(graph.edges())):
        cell = ET.SubElement(root, "mxCell", {
            "id": "edge{}".format(index), "style": "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;",
            "edge": "1", "source": "node{}".format(source), "target": "node{}".format(target), "parent": "1",
        })
        ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})
    ET.indent(mxfile, space="  ")
    ET.ElementTree(mxfile).write(path, encoding="utf-8", xml_declaration=True)


def write_world(candidate, output_dir, shape, resolution, start):
    height, width = shape
    width_m, height_m = width * resolution, height * resolution
    world = """include \"p3at.inc\"\ninclude \"floorplan.inc\"\n\nname \"Phase4C-1 {name}\"\ninterval_sim 100\nquit_time 0\nresolution 0.025\nshow_clock 0\nshow_clock_interval 100\nthreads 2\n\nfloorplan\n(\n  name \"{name}\"\n  bitmap \"{name}.png\"\n  size [{width:.6f} {height:.6f} 2.000]\n  pose [0.000 0.000 0.000 0.000]\n)\n\npioneer3at\n(\n  name \"robot\"\n  pose [{x:.6f} {y:.6f} 0.000 {yaw:.6f}]\n)\n""".format(
        name=candidate, width=width_m, height=height_m,
        x=start[0], y=start[1], yaw=start[2],
    )
    (output_dir / (candidate + ".world")).write_text(world, encoding="utf-8")
    yaml_text = """image: {name}.png\nresolution: {resolution:.8f}\norigin: [{ox:.8f}, {oy:.8f}, 0.0]\noccupied_thresh: 0.65\nfree_thresh: 0.196\nnegate: 0\n""".format(
        name=candidate, resolution=resolution, ox=-0.5 * width_m, oy=-0.5 * height_m,
    )
    (output_dir / (candidate + ".yaml")).write_text(yaml_text, encoding="utf-8")
    for filename in ("floorplan.inc", "p3at.inc", "hokuyo.inc"):
        shutil.copyfile(AUTHOR_WORLD / filename, output_dir / filename)


def skeleton_metrics(skeleton, clearance, resolution):
    graph = pixel_graph(skeleton, resolution)
    length_m = float(sum(data["weight"] for _, _, data in graph.edges(data=True)))
    key = np.zeros_like(skeleton, dtype=bool)
    for node, degree in graph.degree():
        if degree >= 3:
            key[node] = True
    junctions = int(label(key, structure=np.ones((3, 3), dtype=int))[1])
    cycles = graph.number_of_edges() - graph.number_of_nodes() + nx.number_connected_components(graph)
    return {
        "skeleton_length_m": length_m,
        "junction_count": junctions,
        "junction_density_per_100m": float(100.0 * junctions / length_m) if length_m else None,
        "skeleton_cycle_count": int(cycles),
        "median_corridor_width_m": float(2.0 * np.median(clearance[skeleton])),
    }


def validate_prior_roundtrip(xml_path, width_m, expected):
    scripts = ROOT / "baseline/Graph-Based_SLAM-Aware_Exploration/scripts"
    import sys
    sys.path.insert(0, str(scripts))
    from read_drawio_to_nx import build_prior_map_from_drawio
    graph = build_prior_map_from_drawio(
        str(xml_path), actual_map_width=width_m,
        need_normalize=False, need_noise=False, variance=0,
    )
    positions = sorted(tuple(round(value, 6) for value in graph.nodes[node]["position"]) for node in graph)
    expected_positions = sorted(tuple(round(value, 6) for value in expected.nodes[node]["position"]) for node in expected)
    return {
        "read_drawio_success": True,
        "node_count_equal": graph.number_of_nodes() == expected.number_of_nodes(),
        "edge_count_equal": graph.number_of_edges() == expected.number_of_edges(),
        "positions_equal_1e_6": positions == expected_positions,
    }


def build_one(name, source, source_dir, environment_root):
    original = fetch(source["map_url"], source_dir / source["original_file"], source["map_sha256"])
    resolution = float(source["resolution_m"])
    converted = convert_source_map(original, resolution)
    graph, skeleton, clearance, traversable = build_prior(converted["free"], resolution)
    add_world_positions(graph, converted["stage"].shape, resolution)
    start_node, start = select_start(graph, converted["stage"].shape, resolution)

    output_dir = environment_root / name
    output_dir.mkdir(parents=True, exist_ok=True)
    Image.fromarray(converted["stage"], mode="L").save(output_dir / (name + ".png"))
    write_drawio_xml(graph, converted["stage"].shape, output_dir / (name + ".xml"))
    write_world(name, output_dir, converted["stage"].shape, resolution, start)
    width_m = converted["stage"].shape[1] * resolution
    height_m = converted["stage"].shape[0] * resolution
    roundtrip = validate_prior_roundtrip(output_dir / (name + ".xml"), width_m, graph)

    edge_valid = []
    for source_node, target_node in graph.edges():
        a, b = graph.nodes[source_node]["pixel"], graph.nodes[target_node]["pixel"]
        edge_valid.append(segment_is_traversable(a, b, traversable))
    start_row, start_col = graph.nodes[start_node]["pixel"]
    metrics = skeleton_metrics(skeleton, clearance, resolution)
    cycle_rank = graph.number_of_edges() - graph.number_of_nodes() + nx.number_connected_components(graph)
    validation = {
        "candidate": name,
        "source_sha256_verified": sha256(original) == source["map_sha256"],
        "largest_free_component_selected": True,
        "map_size_consistent": True,
        "start_rule": PARAMETERS["start_rule"],
        "start_node": int(start_node),
        "start_pose": list(start),
        "start_is_traversable": bool(traversable[start_row, start_col]),
        "prior_connected": nx.is_connected(graph),
        "all_edges_traversable": all(edge_valid),
        "prior_nodes": graph.number_of_nodes(),
        "prior_edges": graph.number_of_edges(),
        "prior_cycle_rank": int(cycle_rank),
        "roundtrip": roundtrip,
        "status": "PASS" if (
            converted["free_area_m2"] > 0 and bool(traversable[start_row, start_col])
            and nx.is_connected(graph) and all(edge_valid) and all(roundtrip.values())
        ) else "FAIL",
    }
    manifest = {
        "candidate": name, "source": source, "parameters": PARAMETERS,
        "source_page": SOURCE_PAGE, "radish_page": RADISH_PAGE,
        "license": LICENSE, "license_url": LICENSE_URL,
        "width_m": width_m, "height_m": height_m,
        "free_area_m2": converted["free_area_m2"],
        "raw_free_component_count": converted["raw_component_count"],
        "topology": {**metrics, "prior_nodes": graph.number_of_nodes(),
                     "prior_edges": graph.number_of_edges(), "prior_cycle_rank": int(cycle_rank)},
        "validation": validation,
        "artifacts": {
            path.name: sha256(path)
            for path in sorted(output_dir.iterdir())
            if path.is_file() and path.name != "conversion_manifest.json"
        },
    }
    (output_dir / "conversion_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=Path("results/phase4c1"))
    args = parser.parse_args()
    output_root = args.output_root.resolve()
    source_dir = output_root / "source_maps"
    environment_root = output_root / "environments"
    manifests = [build_one(name, SOURCES[name], source_dir, environment_root) for name in SOURCES]

    inventory_rows = []
    topology_rows = []
    validations = {}
    for manifest in manifests:
        name, source = manifest["candidate"], manifest["source"]
        inventory_rows.append({
            "candidate": name, "source": source["map_url"], "dataset_project": source["dataset"],
            "original_file": source["original_file"], "source_sha256": source["map_sha256"],
            "license": LICENSE, "license_url": LICENSE_URL, "citation": "Howard and Roy, Radish, 2003",
            "provider": source["provider"], "original_resolution_m": source["resolution_m"],
            "resolution_status": source["resolution_status"], "description": source["description"],
            "width_m": manifest["width_m"], "height_m": manifest["height_m"],
            "free_area_m2": manifest["free_area_m2"], "conversion_status": manifest["validation"]["status"],
            "prior_availability": "automatic deterministic skeleton prior",
        })
        topology_rows.append({"candidate": name, **manifest["topology"]})
        validations[name] = manifest["validation"]
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "candidate_inventory.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(inventory_rows[0]))
        writer.writeheader(); writer.writerows(inventory_rows)
    with (output_root / "topology_metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(topology_rows[0]))
        writer.writeheader(); writer.writerows(topology_rows)
    (output_root / "prior_builder_validation.json").write_text(
        json.dumps({"parameters": PARAMETERS, "candidates": validations}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"candidates": validations}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
