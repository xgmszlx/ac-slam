#!/usr/bin/python3
"""Post-hoc audit of target-attributable non-sequential Karto marker edges.

This does not relabel marker edges as explicit TryCloseLoop closures. It checks
whether the already-frozen reliable-loop history IDs acquired a new graph edge
to a post-loop keyscan in the 21 Phase 2A active-loop snapshots.
"""

import argparse
import csv
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def resolve_edges(raw_edges, trajectory):
    resolved = []
    for raw_edge in raw_edges:
        endpoints = []
        for point in raw_edge:
            distances = sorted(
                (math.hypot(float(node['x']) - float(point[0]),
                            float(node['y']) - float(point[1])), node_id)
                for node_id, node in enumerate(trajectory)
            )
            endpoints.append({
                'node_id': int(distances[0][1]),
                'match_error_m': float(distances[0][0]),
                'second_best_margin_m': (
                    float(distances[1][0] - distances[0][0])
                    if len(distances) > 1 else None),
            })
        resolved.append({
            'source': endpoints[0]['node_id'],
            'target': endpoints[1]['node_id'],
            'scan_index_gap': abs(
                endpoints[0]['node_id'] - endpoints[1]['node_id']),
            'endpoint_match_error_max_m': max(
                endpoints[0]['match_error_m'], endpoints[1]['match_error_m']),
            'source_second_best_margin_m': endpoints[0]['second_best_margin_m'],
            'target_second_best_margin_m': endpoints[1]['second_best_margin_m'],
            'raw_points': raw_edge,
        })
    return resolved


def audit(opportunity_csv, pairs_root, endpoint_tolerance):
    rows = []
    details = []
    with opportunity_csv.open(newline='') as stream:
        source_rows = list(csv.DictReader(stream))
    for source in source_rows:
        pair = int(source['pair'])
        loop_id = int(source['loop_id'])
        target_ids = {int(value) for value in json.loads(
            source['reliable_history_pose_ids'])}
        snapshot_root = (
            pairs_root / 'pair_{:02d}'.format(pair) / 'slam_aware' /
            'loop_snapshots')
        before_path = snapshot_root / 'loop_{:02d}_before.json'.format(loop_id)
        after_path = snapshot_root / 'loop_{:02d}_after.json'.format(loop_id)
        before = json.loads(before_path.read_text())
        after = json.loads(after_path.read_text())
        before_edges = resolve_edges(
            before.get('karto_closure_edge_endpoints', []),
            before['trajectory_estimate'])
        after_edges = resolve_edges(
            after.get('karto_closure_edge_endpoints', []),
            after['trajectory_estimate'])
        before_pairs = {
            tuple(sorted((edge['source'], edge['target'])))
            for edge in before_edges
            if edge['endpoint_match_error_max_m'] <= endpoint_tolerance
        }
        new_edges = [
            edge for edge in after_edges
            if edge['endpoint_match_error_max_m'] <= endpoint_tolerance
            and tuple(sorted((edge['source'], edge['target']))) not in before_pairs
        ]
        before_max = len(before['trajectory_estimate']) - 1
        target_edges = [
            edge for edge in new_edges
            if ((edge['source'] in target_ids and edge['target'] > before_max)
                or (edge['target'] in target_ids and edge['source'] > before_max))
        ]
        record = {
            'pair': pair,
            'loop_id': loop_id,
            'loop_vertex': int(source['loop_vertex']),
            'before_max_scan_id': before_max,
            'after_max_scan_id': len(after['trajectory_estimate']) - 1,
            'reliable_history_pose_ids': sorted(target_ids),
            'explicit_karto_loop_events': int(source['karto_accepted_loop_events']),
            'new_resolved_nonsequential_marker_edges': len(new_edges),
            'target_attributable_marker_edges': len(target_edges),
            'target_backend_measurement_marker_evidence': bool(target_edges),
            'target_edge_pairs': [
                [edge['source'], edge['target']] for edge in target_edges],
            'target_edge_endpoint_error_max_m': (
                max(edge['endpoint_match_error_max_m'] for edge in target_edges)
                if target_edges else None),
            'attribution_status': (
                'MARKER_RESOLVED_NONEXPLICIT_CONSTRAINT'
                if target_edges else 'NO_TARGET_MARKER_EDGE_OBSERVED'),
        }
        rows.append(record)
        details.append({
            **record,
            'before_snapshot': str(before_path),
            'after_snapshot': str(after_path),
            'target_edges': target_edges,
        })
    return rows, details


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--opportunity-csv', type=Path,
        default=ROOT / 'results/phase2b/diagnosis/active_loop_opportunity.csv')
    parser.add_argument(
        '--pairs-root', type=Path,
        default=ROOT / 'results/phase2/map3_pairs')
    parser.add_argument('--endpoint-tolerance', type=float, default=0.05)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows, details = audit(
        args.opportunity_csv.resolve(), args.pairs_root.resolve(),
        args.endpoint_tolerance)
    csv_path = args.output_dir / 'historical_marker_constraint_audit.csv'
    with csv_path.open('w', newline='') as stream:
        fields = [
            'pair', 'loop_id', 'loop_vertex', 'before_max_scan_id',
            'after_max_scan_id', 'reliable_history_pose_ids',
            'explicit_karto_loop_events',
            'new_resolved_nonsequential_marker_edges',
            'target_attributable_marker_edges',
            'target_backend_measurement_marker_evidence', 'target_edge_pairs',
            'target_edge_endpoint_error_max_m', 'attribution_status',
        ]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                **row,
                'reliable_history_pose_ids': json.dumps(
                    row['reliable_history_pose_ids']),
                'target_edge_pairs': json.dumps(row['target_edge_pairs']),
            })
    summary = {
        'analysis_status': 'POST_HOC_MEASUREMENT_REAUDIT',
        'loop_count': len(rows),
        'explicit_karto_loop_event_count': sum(
            row['explicit_karto_loop_events'] for row in rows),
        'loops_with_target_attributable_marker_edges': sum(
            row['target_backend_measurement_marker_evidence'] for row in rows),
        'target_attributable_marker_edge_count': sum(
            row['target_attributable_marker_edges'] for row in rows),
        'endpoint_tolerance_m': args.endpoint_tolerance,
        'measurement_definition': (
            'New /Mapper/closure_edges pair absent before the loop, resolved '
            'within tolerance to one frozen reliable-history ID and one '
            'post-before-snapshot keyscan ID.'),
        'interpretation_boundary': (
            'Marker edges are backend graph constraints but include ordinary '
            'near-chain/running-scan links; they are not explicit TryCloseLoop '
            'closures and their construction path/covariance is unavailable.'),
        'rows_with_measurement': [
            {'pair': row['pair'], 'loop_id': row['loop_id'],
             'edge_count': row['target_attributable_marker_edges']}
            for row in rows if row['target_backend_measurement_marker_evidence']
        ],
    }
    (args.output_dir / 'historical_marker_constraint_audit.json').write_text(
        json.dumps({'summary': summary, 'loops': details}, indent=2,
                   sort_keys=True) + '\n')
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
