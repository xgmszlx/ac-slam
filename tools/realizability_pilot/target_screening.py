#!/usr/bin/python3
"""N1-A offline, outcome-blind screen over candidate historical regions.

The screen answers one question for every region the frozen route can create:
how non-local would a revisit constraint on this region be, and how redundant is
the region already?

Inputs are *pre-probe* only (``pose_graph_before.json`` plus
``resolved_history_route.json``), so no probe outcome can leak into the
selection.  Every criterion is a quantile of the measured candidate
distribution, which is why this module contains no physical threshold constant.

Definitions
-----------
geodesic_separation_m
    shortest graph path (edge weights = corrected-pose distance) between the
    region anchor and the last pre-probe scan.  A new constraint that links a
    post-freeze scan to the region closes a cycle of roughly this length.
geodesic_hops
    edge count of that shortest path; a large hop count with a short Euclidean
    distance means the region is connected only through the long way round.
geodesic_euclidean_ratio
    geodesic_separation / Euclidean distance; the redundancy-free indicator of
    non-locality (1.0 means the straight line is already in the graph).
alternative_path_redundancy
    number of graph edges inside the neighbourhood of the anchor, i.e. how much
    local closure the region already has.
local_geometry
    segment length and accumulated heading change of the frozen segment; used
    only to require the two selected regions to differ geometrically.
"""

import argparse
import csv
import json
import math
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

import edge_analytics  # noqa: E402
from protocol import TARGETS  # noqa: E402


def quantile(values, fraction):
    ordered = sorted(float(value) for value in values if value is not None)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    position = fraction * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def region_metrics(nodes, edges, waypoint, radius):
    index_of = {node_id: position for position, node_id in enumerate(
        sorted(nodes))}
    anchor = min(nodes.values(), key=lambda node: math.hypot(
        node['x'] - waypoint[0], node['y'] - waypoint[1]))
    anchor_distance = math.hypot(anchor['x'] - waypoint[0],
                                 anchor['y'] - waypoint[1])
    ordered = [nodes[node_id] for node_id in sorted(nodes)]
    segment = []
    anchor_position = ordered.index(anchor)
    left = anchor_position
    while left > 0 and ordered[left - 1]['id'] + 1 == ordered[left]['id'] \
            and math.hypot(ordered[left - 1]['x'] - anchor['x'],
                           ordered[left - 1]['y'] - anchor['y']) <= radius:
        left -= 1
    right = anchor_position
    while right + 1 < len(ordered) and ordered[right + 1]['id'] == ordered[right]['id'] + 1 \
            and math.hypot(ordered[right + 1]['x'] - anchor['x'],
                           ordered[right + 1]['y'] - anchor['y']) <= radius:
        right += 1
    segment = ordered[left:right + 1]
    last = ordered[-1]
    adjacency = edge_analytics.build_adjacency(edges, nodes)
    geodesic = edge_analytics.dijkstra(adjacency, anchor['id'], last['id'])
    hops = edge_analytics.hop_count(adjacency, anchor['id'], last['id'])
    euclidean = math.hypot(last['x'] - anchor['x'], last['y'] - anchor['y'])
    neighbour_ids = [edge['end'] if edge['start'] == anchor['id'] else edge['start']
                     for edge in edges
                     if anchor['id'] in (edge['start'], edge['end'])]
    neighbour_set = set(neighbour_ids)
    neighbourhood_edges = sum(
        1 for edge in edges
        if edge['start'] in neighbour_set or edge['end'] in neighbour_set)
    segment_length = sum(
        math.hypot(right['x'] - left['x'], right['y'] - left['y'])
        for left, right in zip(segment, segment[1:]))
    heading_change = sum(
        abs(math.atan2(math.sin(right['theta'] - left['theta']),
                       math.cos(right['theta'] - left['theta'])))
        for left, right in zip(segment, segment[1:]))
    return {
        'anchor_node_id': anchor['id'],
        'anchor_distance_to_waypoint_m': anchor_distance,
        'segment_scan_count': len(segment),
        'segment_scan_ids': [node['id'] for node in segment],
        'segment_length_m': segment_length,
        'segment_heading_change_rad': heading_change,
        'segment_scan_spacing_mean_m': (
            segment_length / max(len(segment) - 1, 1) if len(segment) > 1 else None),
        'scan_index_separation': int(last['id']) - int(anchor['id']),
        'geodesic_separation_m': geodesic,
        'geodesic_hops': hops,
        'euclidean_separation_m': euclidean,
        'geodesic_euclidean_ratio': (
            None if not euclidean else (geodesic / euclidean if geodesic else None)),
        'anchor_degree': len(neighbour_ids),
        'alternative_path_redundancy': neighbourhood_edges,
        'index_position': index_of[anchor['id']],
    }


def screen_region(region_index, snapshots):
    """Aggregate one candidate region over every available pre-probe graph."""
    route = TARGETS['map3_grid_anchor_01']
    rows = []
    for snapshot in snapshots:
        nodes = edge_analytics.load_nodes(snapshot['before'])
        edges = edge_analytics.load_edges(snapshot['before'], nodes)
        waypoints = snapshot['route']['resolved_history_waypoints']
        waypoint = waypoints[region_index]
        rows.append(region_metrics(nodes, edges, waypoint,
                                   float(route['target_segment_radius_m'])))
    summary = {
        'region_index': region_index,
        'snapshot_count': len(rows),
        'per_snapshot': rows,
    }
    for field in ('geodesic_separation_m', 'geodesic_hops',
                  'geodesic_euclidean_ratio', 'anchor_degree',
                  'alternative_path_redundancy', 'segment_scan_count',
                  'segment_length_m', 'segment_heading_change_rad',
                  'segment_scan_spacing_mean_m', 'scan_index_separation'):
        values = [row[field] for row in rows if row[field] is not None]
        summary['{}_mean'.format(field)] = (
            sum(values) / len(values)) if values else None
        summary['{}_min'.format(field)] = min(values) if values else None
    return summary


def collect_snapshots(paths):
    snapshots = []
    for path in paths:
        directory = Path(path)
        before_path = directory / 'pose_graph_before.json'
        route_path = directory / 'resolved_history_route.json'
        if not before_path.is_file() or not route_path.is_file():
            continue
        snapshots.append({
            'run_dir': str(directory),
            'before': edge_analytics.load_json(before_path),
            'route': edge_analytics.load_json(route_path),
        })
    return snapshots


def region_target_ids():
    """Map a candidate region (history waypoint index) to its target id."""
    mapping = {}
    for target_id, target in TARGETS.items():
        mapping[int(target['candidate_region_waypoint_index'])] = target_id
    return mapping


def select_targets(candidates):
    """Quantile-based, outcome-blind selection of two distinct regions.

    A: top-ranked combined non-locality score.
    B: next-ranked region whose local geometry differs from A's by at least the
       median pairwise geometry difference of the candidate set.
    """
    scored = []
    for candidate in candidates:
        if candidate['geodesic_separation_m_mean'] is None:
            continue
        scored.append(candidate)
    if len(scored) < 2:
        return {'status': 'TARGET_SCREEN_FAILED',
                'reason': 'fewer than two measurable candidate regions'}
    separation_hops = [candidate['geodesic_hops_mean'] for candidate in scored]
    separation_ratio = [candidate['geodesic_euclidean_ratio_mean']
                        for candidate in scored]
    redundancy = [candidate['alternative_path_redundancy_mean']
                  for candidate in scored]
    for candidate in scored:
        candidate['quantile_hops'] = (
            sum(1 for value in separation_hops
                if value <= candidate['geodesic_hops_mean']) / len(scored))
        candidate['quantile_ratio'] = (
            sum(1 for value in separation_ratio
                if value <= candidate['geodesic_euclidean_ratio_mean']) / len(scored))
        candidate['quantile_redundancy_inverse'] = (
            sum(1 for value in redundancy
                if value >= candidate['alternative_path_redundancy_mean'])
            / len(scored))
        candidate['score'] = (
            0.4 * candidate['quantile_hops']
            + 0.4 * candidate['quantile_ratio']
            + 0.2 * candidate['quantile_redundancy_inverse'])
    ranked = sorted(scored, key=lambda candidate: (-candidate['score'],
                                                   candidate['region_index']))
    geometry = [(candidate['segment_length_m_mean'],
                 candidate['segment_heading_change_rad_mean'])
                for candidate in scored]
    pairwise = []
    for index, (length_a, heading_a) in enumerate(geometry):
        for length_b, heading_b in geometry[index + 1:]:
            pairwise.append(abs(length_a - length_b)
                            + 5.0 * abs(heading_a - heading_b))
    median_geometry_difference = quantile(pairwise, 0.5)
    primary = ranked[0]
    secondary = None
    for candidate in ranked[1:]:
        difference = abs(candidate['segment_length_m_mean']
                         - primary['segment_length_m_mean']) \
            + 5.0 * abs(candidate['segment_heading_change_rad_mean']
                        - primary['segment_heading_change_rad_mean'])
        if candidate['quantile_hops'] >= 0.5 and \
                candidate['quantile_ratio'] >= 0.5 and \
                (median_geometry_difference is None
                 or difference >= median_geometry_difference):
            secondary = candidate
            break
    if secondary is None:
        for candidate in ranked[1:]:
            if candidate['quantile_hops'] >= 0.5 and \
                    candidate['quantile_ratio'] >= 0.5:
                secondary = candidate
                break
    if secondary is None:
        return {'status': 'TARGET_SCREEN_FAILED',
                'reason': 'no second region with above-median non-locality',
                'ranked_regions': [candidate['region_index'] for candidate in ranked]}
    mapping = region_target_ids()
    target_ids = [mapping[int(primary['region_index'])],
                  mapping[int(secondary['region_index'])]]
    return {
        'status': 'TARGETS_SELECTED',
        'primary_region_index': primary['region_index'],
        'secondary_region_index': secondary['region_index'],
        'target_ids': target_ids,
        'median_geometry_difference': median_geometry_difference,
        'ranked_regions': [
            {'region_index': candidate['region_index'],
             'score': candidate['score'],
             'quantile_hops': candidate['quantile_hops'],
             'quantile_ratio': candidate['quantile_ratio'],
             'quantile_redundancy_inverse': candidate['quantile_redundancy_inverse']}
            for candidate in ranked],
    }


def write_csv(path, rows):
    if not rows:
        open(path, 'w').close()
        return
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with open(path, 'w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def screen(paths, out_dir):
    snapshots = collect_snapshots(paths)
    if not snapshots:
        raise SystemExit('no usable pre-probe snapshots found')
    candidates = [screen_region(index, snapshots) for index in range(4)]
    selection = select_targets(candidates)
    payload = {
        'preregistered_before_n1_execution': True,
        'outcome_blind': True,
        'inputs': [snapshot['run_dir'] for snapshot in snapshots],
        'candidate_set': ('the four waypoint regions of the frozen three-sided '
                          'rectangle route in map3'),
        'candidate_radius_m': float(TARGETS['map3_grid_anchor_01'][
            'target_segment_radius_m']),
        'selection_rule': (
            'rank every candidate by the mean of its quantile positions in '
            'geodesic hops, geodesic/Euclidean ratio and inverse local '
            'redundancy; take the top region as A and the next region that is '
            'above the median on both non-locality quantiles and differs from A '
            'in local geometry by at least the median pairwise geometry '
            'difference as B'),
        'candidates': candidates,
        'selection': selection,
    }
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / 'target_candidate_screen.csv', [
        {key: value for key, value in candidate.items()
         if not isinstance(value, (list, dict))}
        for candidate in candidates])
    with open(out_dir / 'n1_target_selection_preregistration.json', 'w') as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, default=str)
        stream.write('\n')
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', action='append', dest='snapshots',
                        required=True,
                        help='episode attempt directory with pose_graph_before.json')
    parser.add_argument('--out-dir', required=True)
    args = parser.parse_args()
    payload = screen(args.snapshots, args.out_dir)
    print(json.dumps({'status': payload['selection']['status'],
                      'target_ids': payload['selection'].get('target_ids')},
                     indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
