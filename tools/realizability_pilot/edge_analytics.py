#!/usr/bin/python3
"""Read-only edge analytics for the direction-decision experiment.

All functions consume recorded episode artefacts (pose-graph snapshots, the
loop-closure event log and - when the provenance instrument was enabled - the
provenance JSONL).  Nothing here is imported by the online system.

Attribution rule (structural, works with the provenance instrument disabled):

* ``target_attributable``: a probe-phase constraint with exactly one endpoint in
  the frozen historical target segment and the other endpoint a scan created
  after the freeze.  This is a *revisit* constraint on the historical region.
* ``history_touching``: a probe-phase constraint with one endpoint anywhere on
  the executed history route.
* ``local``: every other probe-phase constraint (both endpoints post-freeze).

The labels describe graph geometry only.  A constraint is never called a false
closure here: closed-loop error is not measurable with this instrumentation.
"""

import heapq
import json
import math

from se2_information import covariance_from_upper_triangle


def load_json(path):
    with open(path) as stream:
        return json.load(stream)


def load_nodes(snapshot):
    """Return {node_id: {id, x, y, theta, unique_id?}} from a snapshot."""
    nodes = {}
    for node in snapshot['full_pose_nodes']:
        nodes[int(node['id'])] = {
            'id': int(node['id']),
            'unique_id': int(node.get('unique_id', -1)),
            'x': float(node['x']),
            'y': float(node['y']),
            'theta': float(node['theta']),
        }
    return nodes


def load_edges(snapshot, nodes):
    """Return the full-graph edge list sorted by creation index.

    ``index`` is the position inside the mapper's edge list, which is the
    insertion order of the underlying graph edges.
    """
    edges = []
    for edge in snapshot['full_pose_edges']:
        start = int(edge['start'])
        end = int(edge['end'])
        if start not in nodes or end not in nodes:
            continue
        edges.append({
            'index': int(edge['index']),
            'start': start,
            'end': end,
            'covariance_upper_triangle': edge.get('covariance_upper_triangle'),
            'source_pose': [nodes[start]['x'], nodes[start]['y'], nodes[start]['theta']],
            'target_pose': [nodes[end]['x'], nodes[end]['y'], nodes[end]['theta']],
        })
    edges.sort(key=lambda item: item['index'])
    return edges


def dijkstra(adjacency, source, target):
    """Shortest-path distance in a small sparse graph; None when disconnected."""
    if source == target:
        return 0.0
    if source not in adjacency:
        return None
    distances = {source: 0.0}
    queue = [(0.0, source)]
    while queue:
        distance, node = heapq.heappop(queue)
        if node == target:
            return distance
        if distance > distances.get(node, float('inf')):
            continue
        for neighbour, weight in adjacency.get(node, ()):  # pragma: no cover
            candidate = distance + weight
            if candidate < distances.get(neighbour, float('inf')):
                distances[neighbour] = candidate
                heapq.heappush(queue, (candidate, neighbour))
    return distances.get(target)


def hop_count(adjacency, source, target):
    """Topological shortest-path length in edges; None when disconnected."""
    if source == target:
        return 0
    if source not in adjacency:
        return None
    seen = {source}
    frontier = [source]
    hops = 0
    while frontier:
        hops += 1
        following = []
        for node in frontier:
            for neighbour, _weight in adjacency.get(node, ()):
                if neighbour in seen:
                    continue
                if neighbour == target:
                    return hops
                seen.add(neighbour)
                following.append(neighbour)
        frontier = following
    return None


def build_adjacency(edges, nodes):
    adjacency = {}
    for edge in edges:
        left = nodes[edge['start']]
        right = nodes[edge['end']]
        weight = math.hypot(right['x'] - left['x'], right['y'] - left['y'])
        adjacency.setdefault(edge['start'], []).append((edge['end'], weight))
        adjacency.setdefault(edge['end'], []).append((edge['start'], weight))
    return adjacency


def insertion_time_metrics(edges, nodes, pairs_of_interest):
    """Geodesic distance and hop count at the moment each edge is inserted.

    The after-probe edge list is replayed in creation order and the shortest
    path between the two endpoints is measured *before* the edge itself enters
    the graph.  This is the only correct way to ask "how non-local is this
    constraint at insertion time": measuring against the final graph would see
    the edge itself and report zero.
    """
    of_interest = {tuple(sorted(pair)) for pair in pairs_of_interest}
    adjacency = {}
    result = {}
    for edge in edges:
        pair = tuple(sorted((edge['start'], edge['end'])))
        if pair in of_interest and pair not in result:
            result[pair] = {
                'geodesic_m': dijkstra(adjacency, pair[0], pair[1]),
                'hops': hop_count(adjacency, pair[0], pair[1]),
                'insertion_index': edge['index'],
            }
        left = nodes[edge['start']]
        right = nodes[edge['end']]
        weight = math.hypot(right['x'] - left['x'], right['y'] - left['y'])
        adjacency.setdefault(edge['start'], []).append((edge['end'], weight))
        adjacency.setdefault(edge['end'], []).append((edge['start'], weight))
    for pair in of_interest:
        result.setdefault(pair, {'geodesic_m': None, 'hops': None,
                                 'insertion_index': None})
    return result


def local_degrees(edges, node_ids):
    """Degree of the given nodes in an edge list."""
    degrees = {int(node_id): 0 for node_id in node_ids}
    for edge in edges:
        for endpoint in (edge['start'], edge['end']):
            if endpoint in degrees:
                degrees[endpoint] += 1
    return degrees


def triangle_count(edges, node_ids):
    """Number of edges between neighbours of the given nodes (local density)."""
    neighbours = {int(node_id): set() for node_id in node_ids}
    for edge in edges:
        for left, right in ((edge['start'], edge['end']),
                            (edge['end'], edge['start'])):
            if left in neighbours:
                neighbours[left].add(right)
    counts = {}
    for node_id, adjacent in neighbours.items():
        counts[node_id] = sum(
            1 for left in adjacent for right in adjacent
            if left < right and any(
                edge['start'] == left and edge['end'] == right
                or edge['start'] == right and edge['end'] == left
                for edge in edges))
    return counts


def classify_new_edges(before_edges, after_edges, target_ids, history_ids):
    """Split probe-phase constraints into target / history / local groups."""
    before_keys = {(edge['start'], edge['end']) for edge in before_edges}
    before_indices = {edge['index'] for edge in before_edges}
    target_ids = set(int(value) for value in target_ids)
    history_ids = set(int(value) for value in history_ids)
    freeze_max = max((edge['end'] for edge in before_edges), default=-1)
    groups = {'target_attributable': [], 'history_touching': [], 'local': []}
    for edge in after_edges:
        if edge['index'] in before_indices:
            continue
        if (edge['start'], edge['end']) in before_keys:
            continue
        start, end = edge['start'], edge['end']
        is_target = ((start in target_ids) != (end in target_ids))
        is_history = ((start in history_ids) != (end in history_ids))
        if is_target:
            groups['target_attributable'].append(edge)
        elif is_history:
            groups['history_touching'].append(edge)
        else:
            groups['local'].append(edge)
    groups['freeze_max_scan_id'] = freeze_max
    return groups


def load_provenance(path):
    records = []
    try:
        with open(path) as stream:
            for line in stream:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    except IOError:
        return records
    return records


def provenance_constraints(records):
    return [record for record in records
            if record.get('record_type') == 'constraint_created']


def relative_mean_components(mean):
    """Normalise a recorded ``relative_mean`` to ``(dx, dy, dtheta)``.

    The instrumentation writes the canonical object form
    ``{"x": ..., "y": ..., "yaw": ...}`` (see ``edge_provenance_schema.json``);
    the pre-schema analysis fixtures used a three-element sequence.  Both are
    accepted so that either artefact can be read without rewriting history.
    """
    if mean is None:
        return None
    if isinstance(mean, dict):
        try:
            return (float(mean['x']), float(mean['y']), float(mean['yaw']))
        except KeyError:
            return None
    try:
        return (float(mean[0]), float(mean[1]), float(mean[2]))
    except (TypeError, IndexError, ValueError):
        return None


def measurement_rows(constraints, phase_cut=None):
    """Per-constraint measurement ledger rows from provenance records."""
    rows = []
    for record in constraints:
        if phase_cut is not None and float(record.get('sim_time', 0.0)) > phase_cut:
            continue
        mean = relative_mean_components(record.get('relative_mean'))
        covariance = record.get('covariance_3x3')
        if mean is None or covariance is None:
            continue
        rows.append({
            'canonical_edge_identity': record.get('canonical_edge_identity'),
            'source_state_id': int(record['source_state_id']),
            'target_state_id': int(record['target_state_id']),
            'source_unique_id': record.get('source_unique_id'),
            'target_unique_id': record.get('target_unique_id'),
            'measurement_dx': float(mean[0]),
            'measurement_dy': float(mean[1]),
            'measurement_dtheta': float(mean[2]),
            'cov_xx': float(covariance[0][0]),
            'cov_xy': float(covariance[0][1]),
            'cov_xt': float(covariance[0][2]),
            'cov_yy': float(covariance[1][1]),
            'cov_yt': float(covariance[1][2]),
            'cov_tt': float(covariance[2][2]),
            'creation_provenance': record.get('creation_provenance'),
            'creation_sequence': int(record.get('creation_sequence', -1)),
            'matcher_type': record.get('matcher_type'),
            'match_response': record.get('match_response'),
            'match_threshold': record.get('match_threshold'),
            'solver_add_constraint_called': record.get('solver_add_constraint_called'),
            'graph_edge_count_after_creation': record.get(
                'graph_edge_count_after_creation'),
            'before_or_during_probe': record.get('before_or_during_probe'),
            'wall_time': record.get('wall_time'),
            'sim_time': record.get('sim_time'),
        })
    rows.sort(key=lambda row: row['creation_sequence'])
    return rows


def reconstructed_measurements(edges, nodes):
    """Fallback measurements from corrected poses (instrument-free episodes).

    These are *not* raw Karto measurements; they are the relative poses implied
    by the corrected estimate, which is all that an instrument-free episode can
    offer.  The column ``measurement_source`` distinguishes the two origins.
    """
    rows = []
    for edge in edges:
        source = nodes[edge['start']]
        target = nodes[edge['end']]
        cosine = math.cos(source['theta'])
        sine = math.sin(source['theta'])
        dx = target['x'] - source['x']
        dy = target['y'] - source['y']
        rows.append({
            'canonical_edge_identity': None,
            'source_state_id': edge['start'],
            'target_state_id': edge['end'],
            'source_unique_id': source['unique_id'],
            'target_unique_id': target['unique_id'],
            'measurement_dx': cosine * dx + sine * dy,
            'measurement_dy': -sine * dx + cosine * dy,
            'measurement_dtheta': math.atan2(
                math.sin(target['theta'] - source['theta']),
                math.cos(target['theta'] - source['theta'])),
            'cov_xx': None, 'cov_xy': None, 'cov_xt': None,
            'cov_yy': None, 'cov_yt': None, 'cov_tt': None,
            'creation_provenance': None,
            'creation_sequence': edge['index'],
            'matcher_type': None,
            'match_response': None,
            'match_threshold': None,
            'solver_add_constraint_called': None,
            'graph_edge_count_after_creation': None,
            'before_or_during_probe': None,
            'wall_time': None,
            'sim_time': None,
        })
        if edge.get('covariance_upper_triangle'):
            covariance = covariance_from_upper_triangle(
                edge['covariance_upper_triangle'])
            rows[-1].update({
                'cov_xx': float(covariance[0, 0]),
                'cov_xy': float(covariance[0, 1]),
                'cov_xt': float(covariance[0, 2]),
                'cov_yy': float(covariance[1, 1]),
                'cov_yt': float(covariance[1, 2]),
                'cov_tt': float(covariance[2, 2]),
            })
    return rows
