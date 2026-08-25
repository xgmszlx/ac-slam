#!/usr/bin/python3
"""Create frozen Phase 4B per-run summaries from raw observer/evaluator outputs."""

import argparse
import json
import math
from pathlib import Path


METHODS = {
    0: ('A', 'Original'),
    1: ('B', 'Always-Trace'),
    2: ('C', 'Selective'),
}


def load_json(path, default=None):
    path = Path(path)
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def polyline_length(points):
    return sum(
        math.hypot(float(b[0]) - float(a[0]), float(b[1]) - float(a[1]))
        for a, b in zip(points, points[1:])
    )


def saved_planned_distance(loop):
    early = loop.get('early_stop')
    path = loop.get('planned_loop_path') or []
    trajectory = loop.get('actual_loop_trajectory') or []
    if not early or not path or not trajectory:
        return None
    next_index = int(early.get('at_waypoint', 0))
    if next_index >= len(path):
        return 0.0
    current = trajectory[-1][1:3]
    remaining = [current] + path[next_index:]
    return polyline_length(remaining)


def metric_value(metrics, key):
    item = (metrics or {}).get(key)
    return item.get('rmse') if isinstance(item, dict) else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', required=True, type=Path)
    parser.add_argument('--oracle-mode', required=True, type=int, choices=(0, 1, 2))
    parser.add_argument('--seed', required=True, type=int)
    parser.add_argument('--validity', required=True,
                        choices=('VALID', 'TECHNICAL_INVALID', 'EXPERIMENTAL_FAILURE'))
    parser.add_argument('--exploration-wall-s', type=float)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    label, method = METHODS[args.oracle_mode]

    observer = load_json(run_dir / 'observer_summary.json', {})
    loops_payload = load_json(run_dir / 'loops.json', {'loops': []})
    loops = loops_payload.get('loops', [])
    closure_events = observer.get('loop_closed_events', [])

    attributed_event_indices = set()
    closure_records = []
    for event_index, event in enumerate(closure_events):
        stamp = float(event['stamp'])
        matches = []
        for loop in loops:
            start = loop.get('actual_start_time')
            end = loop.get('actual_end_time')
            if start is not None and stamp + 1e-9 >= float(start):
                if end is None or stamp <= float(end) + 1e-9:
                    matches.append(loop)
        record = dict(event)
        if len(matches) == 1:
            record.update({
                'classification': 'ACTIVE_ATTRIBUTED',
                'loop_id': matches[0]['loop_id'],
                'loop_vertex': matches[0]['loop_vertex'],
            })
            attributed_event_indices.add(event_index)
        elif len(matches) == 0:
            record.update({'classification': 'PASSIVE_OR_UNATTRIBUTED'})
        else:
            record.update({
                'classification': 'AMBIGUOUS',
                'candidate_loop_ids': [loop['loop_id'] for loop in matches],
            })
        closure_records.append(record)

    for loop in loops:
        start = loop.get('actual_start_time')
        end = loop.get('actual_end_time')
        planned_start = loop.get('planned_start_time')
        matching_gates = [
            event for event in observer.get('gate_events', [])
            if event.get('vertex') == loop.get('loop_vertex')
            and (planned_start is None or event.get('timestamp', -float('inf')) >= planned_start - 1e-9)
            and (end is None or event.get('timestamp', float('inf')) <= end + 1e-9)
        ]
        matching_repairs = [
            event for event in observer.get('repair_events', [])
            if event.get('vertex') == loop.get('loop_vertex')
            and (planned_start is None or event.get('timestamp', -float('inf')) >= planned_start - 1e-9)
            and (end is None or event.get('timestamp', float('inf')) <= end + 1e-9)
        ]
        if matching_gates and not loop.get('gate_decision'):
            loop['gate_decision'] = matching_gates[0]
        if matching_repairs and not loop.get('repair_plan'):
            loop['repair_plan'] = matching_repairs[0]
        accepted = [
            event for event in closure_records
            if event.get('loop_id') == loop.get('loop_id')
        ]
        loop['phase4b_execution_started'] = start is not None
        loop['phase4b_execution_finished'] = bool(loop.get('execution_finished'))
        loop['phase4b_accepted_active_loop'] = bool(accepted)
        loop['phase4b_accepted_events'] = accepted
        if args.oracle_mode == 0:
            loop['phase4b_execution_policy'] = 'ORIGINAL'
        elif args.oracle_mode == 1:
            loop['phase4b_execution_policy'] = 'ALWAYS_TRACE'
        else:
            if matching_repairs and matching_repairs[0].get('policy') == 'SELECTIVE_REPAIR':
                loop['phase4b_execution_policy'] = 'SELECTIVE_REPAIR'
            elif matching_gates and matching_gates[0].get('decision') == 'NO_REPAIR':
                loop['phase4b_execution_policy'] = 'NO_REPAIR'
            else:
                loop['phase4b_execution_policy'] = loop.get('execution_policy') or 'UNKNOWN'
        loop['early_stop_saved_planned_distance_m_estimate'] = saved_planned_distance(loop)
        loop['early_stop_saved_time_s'] = None
        loop['early_stop_saved_time_status'] = 'N/A: counterfactual travel time not observed'
        if start is not None and end is not None:
            loop['phase4b_active_loop_time_s'] = float(end) - float(start)

    loops_path = run_dir / 'loops.json'
    loops_path.write_text(
        json.dumps({'loops': loops}, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )
    closure_output = {
        'source': '/Mapper/loop_closed (Karto accepted-closure callback)',
        'events': closure_records,
        'active_attributed_count': sum(
            event['classification'] == 'ACTIVE_ATTRIBUTED' for event in closure_records
        ),
        'passive_or_unattributed_count': sum(
            event['classification'] == 'PASSIVE_OR_UNATTRIBUTED'
            for event in closure_records
        ),
        'ambiguous_count': sum(
            event['classification'] == 'AMBIGUOUS' for event in closure_records
        ),
        'sequence_contiguous': [event.get('seq') for event in closure_records]
        == list(range(1, len(closure_records) + 1)),
    }
    (run_dir / 'closure_events.json').write_text(
        json.dumps(closure_output, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )
    (run_dir / 'gate_events.json').write_text(
        json.dumps({'events': observer.get('gate_events', [])}, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    (run_dir / 'repair_events.json').write_text(
        json.dumps({
            'repairs': observer.get('repair_events', []),
            'early_stops': observer.get('early_stop_events', []),
        }, indent=2, sort_keys=True) + '\n', encoding='utf-8',
    )

    evo = load_json(run_dir / 'evo' / 'metrics.json', {})
    trajectory_output = {
        'protocol': evo.get('protocol'),
        'whole_run': evo.get('whole_run'),
        'loops': evo.get('loops'),
    }
    (run_dir / 'trajectory_metrics.json').write_text(
        json.dumps(trajectory_output, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )
    trajectory = evo.get('whole_run', {})
    mapping = load_json(run_dir / 'mapping_metrics.json', {})
    tsp = load_json(run_dir / 'tsp_record.json', {})

    executed = [loop for loop in loops if loop.get('phase4b_execution_started')]
    accepted = [loop for loop in executed if loop.get('phase4b_accepted_active_loop')]
    repaired = [
        loop for loop in executed
        if loop.get('phase4b_execution_policy') in ('ALWAYS_TRACE', 'SELECTIVE_REPAIR')
    ]
    active_distance = sum(float(loop.get('extra_distance') or 0.0) for loop in executed)
    active_time = sum(float(loop.get('phase4b_active_loop_time_s') or 0.0) for loop in executed)
    repair_distance = sum(float(loop.get('extra_distance') or 0.0) for loop in repaired)
    repair_time = sum(float(loop.get('phase4b_active_loop_time_s') or 0.0) for loop in repaired)
    sim_exploration = observer.get('total_exploration_time')
    wall_ratio = None
    if args.exploration_wall_s is not None and sim_exploration:
        wall_ratio = float(args.exploration_wall_s) / float(sim_exploration)

    summary = {
        'phase': '4B',
        'condition': label,
        'method': method,
        'oracle_mode': args.oracle_mode,
        'seed': args.seed,
        'validity': args.validity,
        'loop_realization': {
            'planned_active_loops': len(loops),
            'executed_active_loops': len(executed),
            'accepted_active_loops': len(accepted),
            'acceptance_rate': (
                float(len(accepted)) / len(executed) if executed else None
            ),
            'accepted_passive_or_unattributed_events': (
                closure_output['passive_or_unattributed_count']
            ),
        },
        'execution_cost': {
            'active_loop_distance_m': active_distance,
            'active_loop_time_s': active_time,
            'repair_trigger_count': len(repaired),
            'no_repair_count': len(executed) - len(repaired),
            'repair_distance_m': repair_distance,
            'repair_time_s': repair_time,
            'early_stop_count': sum(bool(loop.get('early_stopped')) for loop in executed),
            'early_stop_saved_planned_distance_m_estimate': sum(
                float(loop.get('early_stop_saved_planned_distance_m_estimate') or 0.0)
                for loop in executed
            ),
        },
        'exploration': {
            'total_distance_m': observer.get('total_path_length_gt'),
            'sim_time_s': sim_exploration,
            'wall_time_s': args.exploration_wall_s,
            'wall_sim_ratio': wall_ratio,
            'action_status': observer.get('explore_result_status'),
        },
        'trajectory': {
            'ape_se2_translation_rmse_m': metric_value(trajectory, 'ape_se2_translation_m'),
            'rpe_translation_1m_rmse_m': metric_value(trajectory, 'rpe_translation_1m_m'),
            'rpe_rotation_1m_rmse_deg': metric_value(trajectory, 'rpe_rotation_1m_deg'),
        },
        'mapping': {
            'occupied_iou': (mapping.get('occupied_iou') or {}).get('value'),
            'occupied_boundary_f1': (mapping.get('occupied_boundary_f1') or {}).get('f1'),
            'estimated_unknown_ratio': (mapping.get('supporting') or {}).get(
                'estimated_unknown_ratio'
            ),
        },
        'pose_graph': {
            'node_count': observer.get('pose_graph_node_count'),
            'edge_count': observer.get('pose_graph_edge_count'),
        },
        'tsp': {
            key: tsp.get(key) for key in (
                'solver', 'seed', 'initial_tsp_path', 'full_tsp_path',
                'predicted_tsp_length', 'predicted_full_tsp_length',
            )
        },
    }
    (run_dir / 'run_summary.json').write_text(
        json.dumps(summary, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
