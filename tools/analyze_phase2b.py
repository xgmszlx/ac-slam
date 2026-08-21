#!/usr/bin/python3
"""Offline Phase 2B audit of global Karto closures and active-loop opportunity."""

import csv
import json
import math
import pickle
import re
from collections import defaultdict, deque
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAIR_ROOT = ROOT / 'results' / 'phase2' / 'map3_pairs'
OUT = ROOT / 'results' / 'phase2b' / 'diagnosis'
LOOP_SEARCH_MAX_M = 4.0
MIN_CHAIN = 4


def wrap_angle(value):
    return abs((value + math.pi) % (2.0 * math.pi) - math.pi)


def euclidean(left, right):
    return math.hypot(left[0] - right[0], left[1] - right[1])


def load_updates(path):
    node_times = {}
    edge_times = {}
    edges = {}
    for line in path.read_text().splitlines():
        update = json.loads(line)
        timestamp = float(update['timestamp'])
        for node_id in update['vertices']:
            node_times.setdefault(int(node_id), timestamp)
        for edge in update['edges']:
            edge_id = int(edge['index'])
            edge_times.setdefault(edge_id, timestamp)
            edges[edge_id] = edge
    # The passive observer's topic-callback clock was wall time while GT and
    # explicit loop markers used Stage simulation time.  Normalize graph update
    # times to elapsed run time so the two streams can be joined.  Node 0 is
    # created at the beginning of the run; the sub-second offset is below the
    # pose-graph publication period and is kept as an explicit limitation.
    if node_times:
        origin = min(node_times.values())
        node_times = {node_id: timestamp - origin for node_id, timestamp in node_times.items()}
        edge_times = {edge_id: timestamp - origin for edge_id, timestamp in edge_times.items()}
    return node_times, edge_times, edges


def load_update_batches(path):
    batches = []
    raw = [json.loads(line) for line in path.read_text().splitlines()]
    origins = [float(update['timestamp']) for update in raw if update['vertices']]
    origin = min(origins) if origins else 0.0
    for update in raw:
        batches.append({
            'elapsed_time': float(update['timestamp']) - origin,
            'vertices': [int(value) for value in update['vertices']],
            'edges': update['edges'],
        })
    return batches


def nearest_node(nodes, point):
    return min(
        nodes.values(),
        key=lambda node: (node['x'] - point[0]) ** 2 + (node['y'] - point[1]) ** 2,
    )


def nearest_actual_history(actual, history_nodes):
    best = None
    for sample in actual:
        for node in history_nodes:
            distance = euclidean((sample[1], sample[2]), (node['x'], node['y']))
            if best is None or distance < best[0]:
                best = (distance, sample, node)
    return best


def path_length_and_overlap(actual, historical_points, threshold):
    total = 0.0
    overlap = 0.0
    for left, right in zip(actual, actual[1:]):
        length = euclidean((left[1], left[2]), (right[1], right[2]))
        total += length
        midpoint = ((left[1] + right[1]) / 2.0, (left[2] + right[2]) / 2.0)
        if historical_points and min(euclidean(midpoint, point) for point in historical_points) <= threshold:
            overlap += length
    return total, overlap


def graph_at_time(edge_times, edges, timestamp):
    adjacency = defaultdict(set)
    for edge_id, edge in edges.items():
        if edge_times.get(edge_id, float('inf')) <= timestamp:
            start, end = int(edge['start']), int(edge['end'])
            adjacency[start].add(end)
            adjacency[end].add(start)
    return adjacency


def near_linked_nodes(current_id, positions, adjacency, max_distance):
    if current_id not in positions:
        return set()
    origin = positions[current_id]
    visited = {current_id}
    queue = deque([current_id])
    valid = set()
    while queue:
        node_id = queue.popleft()
        if node_id not in positions:
            continue
        if euclidean(origin, positions[node_id]) > max_distance:
            continue
        valid.add(node_id)
        for neighbor in adjacency.get(node_id, ()):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return valid


def candidate_chains(current_id, positions, near_linked, max_distance):
    """Reconstruct the explicit spatial/linked filters in FindPossibleLoopClosure."""
    origin = positions[current_id]
    chains = []
    chain = []
    for candidate in sorted(node for node in positions if node < current_id):
        if euclidean(origin, positions[candidate]) < max_distance:
            if candidate in near_linked:
                chain = []
            else:
                chain.append(candidate)
        else:
            if len(chain) >= MIN_CHAIN:
                chains.append(chain)
            chain = []
    if len(chain) >= MIN_CHAIN:
        chains.append(chain)
    return chains


def read_gt_samples(path):
    samples = []
    with path.open() as input_file:
        for row in csv.DictReader(input_file):
            samples.append((
                float(row['timestamp']), float(row['x']) + 28.0,
                float(row['y']) + 28.0, float(row['yaw']),
            ))
    return samples


def global_passive_audit():
    rows = []
    detail = []
    for run_dir in sorted(PAIR_ROOT.glob('pair_*/*')):
        if not (run_dir / 'pose_graph_updates.jsonl').is_file():
            continue
        pair = int(run_dir.parent.name.split('_')[1])
        method = run_dir.name
        node_times, edge_times, edges = load_updates(run_dir / 'pose_graph_updates.jsonl')
        loops = []
        loops_path = run_dir / 'loops.json'
        if loops_path.is_file():
            loops = json.loads(loops_path.read_text()).get('loops', [])
        rosout = (run_dir / 'rosout.log').read_text(errors='replace')
        accepted_lines = re.findall(r'^.*Add one Loop closure\..*$', rosout, re.MULTILINE)
        # No accepted event exists in Phase 2A, so graph gap statistics remain
        # auxiliary and must not be promoted into true closure constraints.
        gaps = sorted(abs(int(edge['start']) - int(edge['end'])) for edge in edges.values())
        large = [gap for gap in gaps if gap > 70]
        marker_count = json.loads((run_dir / 'observer_summary.json').read_text()).get(
            'karto_closure_edge_count'
        )
        row = {
            'pair': pair, 'method': method,
            'total_true_loop_constraints': len(accepted_lines),
            'passive_loop_constraints': 0,
            'planned_active_loop_constraints': 0,
            'unknown_loop_constraints': len(accepted_lines),
            'closure_scan_index_gaps': json.dumps([]),
            'closure_times_positions': json.dumps([]),
            'auxiliary_edges_gap_gt70_count': len(large),
            'auxiliary_edges_gap_gt70_distribution': json.dumps(large),
            'maximum_auxiliary_edge_gap': max(gaps) if gaps else None,
            'closure_marker_final_count_auxiliary': marker_count,
            'accepted_loop_log_count': len(accepted_lines),
        }
        rows.append(row)
        detail.append({
            'pair': pair, 'method': method, 'accepted_log_lines': accepted_lines,
            'active_intervals': [
                [loop.get('actual_start_time'), loop.get('actual_end_time')]
                for loop in loops
            ],
            'interpretation': (
                'Only OpenKarto accepted-loop callbacks count as true constraints. '
                'Large-index and closure-marker edges are retained as auxiliary local/unknown links.'
            ),
        })
    with (OUT / 'passive_loop_audit.csv').open('w', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    (OUT / 'passive_loop_audit_detail.json').write_text(
        json.dumps(detail, indent=2, sort_keys=True) + '\n'
    )
    return rows


def active_opportunity():
    rows = []
    for loop_path in sorted(PAIR_ROOT.glob('pair_*/slam_aware/loops.json')):
        run_dir = loop_path.parent
        pair = int(run_dir.parent.name.split('_')[1])
        node_times, edge_times, all_edges = load_updates(run_dir / 'pose_graph_updates.jsonl')
        update_batches = load_update_batches(run_dir / 'pose_graph_updates.jsonl')
        prior_path = next((run_dir / 'author_outputs').glob('prior_map*.pickle'))
        with prior_path.open('rb') as input_file:
            prior_graph = pickle.load(input_file)
        loops = json.loads(loop_path.read_text())['loops']
        for loop in loops:
            before = json.loads((run_dir / loop['snapshot_before']).read_text())
            after = json.loads((run_dir / loop['snapshot_after']).read_text())
            before_nodes = {int(key): value for key, value in before['pose_graph_nodes'].items()}
            after_nodes = {int(key): value for key, value in after['pose_graph_nodes'].items()}
            positions = {
                node_id: (float(node['x']), float(node['y']))
                for node_id, node in after_nodes.items()
            }
            positions.update({
                node_id: (float(node['x']), float(node['y']))
                for node_id, node in before_nodes.items() if node_id not in positions
            })
            selected_nodes = []
            selected_match_errors = []
            for point in loop['planned_loop_path']:
                selected = nearest_node(before_nodes, point)
                selected_nodes.append(selected)
                selected_match_errors.append(euclidean(point, (selected['x'], selected['y'])))

            actual = [
                (float(sample[0]), float(sample[1]) + 28.0, float(sample[2]) + 28.0,
                 float(sample[3]))
                for sample in loop['actual_loop_trajectory']
            ]
            nearest = nearest_actual_history(actual, selected_nodes)
            min_distance, closest_sample, closest_history = nearest
            heading_difference = wrap_angle(closest_sample[3] - closest_history['theta'])
            high_vertex = prior_graph.nodes[int(loop['loop_vertex'])]['position']
            target_to_history = min(
                euclidean(high_vertex, (node['x'], node['y'])) for node in selected_nodes
            )
            target_to_actual = min(
                euclidean(high_vertex, (sample[1], sample[2])) for sample in actual
            )
            each_history_min = [
                min(euclidean((sample[1], sample[2]), (node['x'], node['y'])) for sample in actual)
                for node in selected_nodes
            ]

            historical_points = [(node['x'], node['y']) for node in before_nodes.values()]
            path_length, overlap05 = path_length_and_overlap(actual, historical_points, 0.5)
            _, overlap10 = path_length_and_overlap(actual, historical_points, 1.0)
            _, overlap20 = path_length_and_overlap(actual, historical_points, 2.0)

            eligible_at_closest = [
                node_id for node_id, timestamp in node_times.items()
                if timestamp <= closest_sample[0]
            ]
            current_id = max(eligible_at_closest) if eligible_at_closest else max(before_nodes)
            current_time = node_times.get(current_id, closest_sample[0])
            adjacency = graph_at_time(edge_times, all_edges, current_time)
            nearlinked = near_linked_nodes(current_id, positions, adjacency, LOOP_SEARCH_MAX_M)
            chains = candidate_chains(current_id, positions, nearlinked, LOOP_SEARCH_MAX_M)
            spatial_history = [
                node_id for node_id in positions
                if node_id < current_id
                and euclidean(positions[current_id], positions[node_id]) < LOOP_SEARCH_MAX_M
            ] if current_id in positions else []
            selected_ids = [int(node['id']) for node in selected_nodes]
            selected_gaps = [current_id - node_id for node_id in selected_ids]
            selected_temporal_gaps = [
                closest_sample[0] - node_times[node_id]
                for node_id in selected_ids if node_id in node_times
            ]
            selected_nearlinked = [node_id in nearlinked for node_id in selected_ids]
            new_nodes_during = [
                node_id for node_id, timestamp in node_times.items()
                if loop['actual_start_time'] <= timestamp <= loop['actual_end_time']
            ]
            post_batches = [
                batch for batch in update_batches
                if loop['actual_end_time'] < batch['elapsed_time'] <= loop['actual_end_time'] + 15.0
                and batch['vertices']
            ]
            first_post_batch = post_batches[0] if post_batches else None
            if new_nodes_during:
                keyscan_timing_status = 'ObservedWithinLoopWindow'
            elif first_post_batch:
                keyscan_timing_status = 'AmbiguousPostLoopBatch'
            else:
                keyscan_timing_status = 'NoKeyscanBatchObservedWithin15s'
            row = {
                'pair': pair, 'loop_id': loop['loop_id'],
                'loop_vertex': loop['loop_vertex'],
                'high_level_target_x': high_vertex[0], 'high_level_target_y': high_vertex[1],
                'reliable_history_pose_ids': json.dumps(selected_ids),
                'reliable_history_pose_xytheta': json.dumps([
                    [node['x'], node['y'], node['theta']] for node in selected_nodes
                ]),
                'service_pose_match_max_error_m': max(selected_match_errors),
                'planned_loop_path': json.dumps(loop['planned_loop_path']),
                'actual_loop_trajectory_map_frame': json.dumps(actual),
                'target_to_history_distance_m': target_to_history,
                'target_to_actual_min_distance_m': target_to_actual,
                'actual_to_history_min_distance_m': min_distance,
                'actual_to_each_history_min_mean_m': sum(each_history_min) / len(each_history_min),
                'actual_to_each_history_min_max_m': max(each_history_min),
                'heading_difference_at_min_distance_rad': heading_difference,
                'closest_history_pose_id': int(closest_history['id']),
                'current_scan_id_lower_bound_at_closest_revisit': current_id,
                'selected_scan_index_gap_lower_bound_min': min(selected_gaps),
                'selected_scan_index_gap_lower_bound_max': max(selected_gaps),
                'selected_temporal_gap_lower_bound_min_s': min(selected_temporal_gaps) if selected_temporal_gaps else None,
                'selected_temporal_gap_lower_bound_max_s': max(selected_temporal_gaps) if selected_temporal_gaps else None,
                'history_scans_spatially_within_4m': len(spatial_history),
                'selected_history_nearlinked_count': sum(selected_nearlinked),
                'selected_history_nearlinked_fraction': sum(selected_nearlinked) / len(selected_nearlinked),
                'karto_candidate_chains_ge4_reconstructed': len(chains),
                'karto_candidate_history_scan_count_reconstructed': sum(len(chain) for chain in chains),
                'karto_candidate_chain_max_size_reconstructed': max(map(len, chains), default=0),
                'reconstructed_candidate_chains': json.dumps(chains),
                'active_loop_path_length_m': path_length,
                'historical_overlap_length_within_0_5m': overlap05,
                'historical_overlap_length_within_1m': overlap10,
                'historical_overlap_length_within_2m': overlap20,
                'active_loop_trajectory_overlap_ratio_1m': overlap10 / path_length if path_length else None,
                'entered_historical_pose_neighborhood_1m': min_distance <= 1.0,
                'entered_history_position_heading_neighborhood': (
                    min_distance <= 1.0 and heading_difference <= 0.52
                ),
                'new_karto_keyscans_during_loop': len(new_nodes_during),
                'new_karto_keyscan_ids_during_loop': json.dumps(sorted(new_nodes_during)),
                'keyscan_timing_status': keyscan_timing_status,
                'first_post_loop_batch_delay_s': (
                    first_post_batch['elapsed_time'] - loop['actual_end_time']
                    if first_post_batch else None
                ),
                'first_post_loop_batch_keyscan_count': (
                    len(first_post_batch['vertices']) if first_post_batch else 0
                ),
                'matching_covariance_status': 'Unknown: coarse/fine matcher covariance was not emitted in Phase 2A logs',
                'karto_accepted_loop_events': loop['karto_closure_events_during_execution'],
                'new_nonlocal_constraint': loop['successful_slam_loop'],
                'new_edges_gap_gt70_count': len(loop.get('new_edges_beyond_70_scan_running_buffer', [])),
                'measurement_note': (
                    'Candidate-chain reconstruction uses saved corrected scan poses and graph edges '
                    'available by timestamp; scan barycenters and rejected matcher covariance are unavailable.'
                ),
            }
            rows.append(row)
    with (OUT / 'active_loop_opportunity.csv').open('w', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)

    summary = {
        'loops': len(rows),
        'entered_selected_history_neighborhood_1m': sum(
            str(row['entered_historical_pose_neighborhood_1m']) == 'True' for row in rows
        ),
        'candidate_chain_present': sum(row['karto_candidate_chains_ge4_reconstructed'] > 0 for row in rows),
        'keyscan_batches_observed_within_window': sum(
            row['keyscan_timing_status'] == 'ObservedWithinLoopWindow' for row in rows
        ),
        'keyscan_timing_ambiguous_post_loop_batch': sum(
            row['keyscan_timing_status'] == 'AmbiguousPostLoopBatch' for row in rows
        ),
        'target_to_history_distance_m': [row['target_to_history_distance_m'] for row in rows],
        'actual_to_history_min_distance_m': [row['actual_to_history_min_distance_m'] for row in rows],
        'overlap_ratio_1m': [row['active_loop_trajectory_overlap_ratio_1m'] for row in rows],
        'definitions': {
            'overlap_ratio_1m': 'actual loop GT path length within 1 m of any pre-loop Karto pose / actual loop GT path length',
            'entered_history_neighborhood': 'minimum distance to a service-selected historical pose <= 1 m',
            'candidate_reconstruction': 'OpenKarto 4 m spatial filter, graph near-linked exclusion, and chain size >= 4',
        },
    }
    (OUT / 'planned_vs_realized_summary.json').write_text(
        json.dumps(summary, indent=2, sort_keys=True) + '\n'
    )
    return rows, summary


def classify_failures(rows):
    """Assign an evidence-bounded diagnosis without changing planner behavior.

    Candidate reconstruction is necessarily approximate because Phase 2A did
    not record Karto's rejected coarse/fine matcher responses or scan
    barycenters.  Consequently C/D assignments are Probable rather than
    Confirmed; publication timing ambiguity remains Unknown.
    """
    classified = []
    for row in rows:
        timing = row['keyscan_timing_status']
        candidates = int(row['karto_candidate_chains_ge4_reconstructed'])
        if timing != 'ObservedWithinLoopWindow':
            category = 'F. Unknown'
            evidence = 'Unknown'
            rationale = (
                'The incremental pose-graph publication placed the first new '
                'keyscan batch after the recorded loop interval, so candidate '
                'and matcher attribution cannot be aligned reliably.'
            )
        elif candidates == 0:
            category = 'C. Opportunity failure'
            evidence = 'Probable'
            rationale = (
                'A Karto keyscan was observed during execution, but the saved '
                'graph/poses reconstruct no eligible historical chain of at '
                'least four scans within 4 m after near-linked exclusion.'
            )
        else:
            category = 'D. Matching failure'
            evidence = 'Probable'
            rationale = (
                'A Karto keyscan and at least one eligible historical candidate '
                'chain are reconstructed, but Karto emitted no accepted-loop '
                'event; rejected coarse/fine responses were not logged.'
            )
        classified.append({
            'pair': row['pair'],
            'loop_id': row['loop_id'],
            'primary_failure_category': category,
            'evidence_level': evidence,
            'rationale': rationale,
            'karto_keyscan_timing': timing,
            'reconstructed_candidate_chain_count': candidates,
            'actual_to_history_min_distance_m': row['actual_to_history_min_distance_m'],
            'heading_difference_at_min_distance_rad': row['heading_difference_at_min_distance_rad'],
            'active_loop_trajectory_overlap_ratio_1m': row['active_loop_trajectory_overlap_ratio_1m'],
            'accepted_karto_loop_events': row['karto_accepted_loop_events'],
        })
    with (OUT / 'failure_taxonomy.csv').open('w', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=list(classified[0]))
        writer.writeheader(); writer.writerows(classified)
    counts = defaultdict(int)
    evidence_counts = defaultdict(int)
    for row in classified:
        counts[row['primary_failure_category']] += 1
        evidence_counts[row['evidence_level']] += 1
    result = {
        'counts': dict(sorted(counts.items())),
        'evidence_counts': dict(sorted(evidence_counts.items())),
        'experiment_level_findings': {
            'A. Measurement failure': (
                'Not supported as the explanation for 0/21: accepted callbacks '
                'are present in the positive controls and absent from all Phase 2A rosout logs.'
            ),
            'B. Backend/configuration failure': (
                'Not supported as a global inability: the unchanged Karto setup '
                'accepts closures in the map3 positive controls.'
            ),
        },
        'redundant_loop_cases_confirmed': 0,
        'classification_limit': (
            'C/D are Probable because Karto rejected-match response/covariance '
            'and exact scan barycenters were not recorded in Phase 2A.'
        ),
    }
    (OUT / 'failure_taxonomy_summary.json').write_text(
        json.dumps(result, indent=2, sort_keys=True) + '\n'
    )
    return classified, result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    passive = global_passive_audit()
    opportunity, summary = active_opportunity()
    taxonomy, taxonomy_summary = classify_failures(opportunity)
    print(json.dumps({
        'passive_runs': len(passive), 'active_loops': len(opportunity),
        'planned_vs_realized': summary,
        'failure_taxonomy': taxonomy_summary,
    }, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
