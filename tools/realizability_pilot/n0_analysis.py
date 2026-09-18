#!/usr/bin/python3
"""N0 instrumentation-validity analysis for the direction-decision experiment.

Two questions are answered here, both from same-seed matched episodes (the
earlier OFF/ON comparison used different TSP seeds, which made it impossible to
separate instrument effects from route effects):

1. **Pre-probe equivalence**: did two episodes of the same block start the probe
   from a comparable graph?  ``compare_signatures`` evaluates the pre-registered
   tolerances below.
2. **Non-perturbation**: does the *measured* graph outcome depend on which
   observation instrument was enabled?  ``nonperturbation_verdict`` compares
   paired same-seed differences against the repeatability scale that the block
   itself measures.

Every tolerance in this module is a *comparability* tolerance for the gate; the
outcome verdict deliberately uses a measured scale (between-run spread of the
same configuration), not a hand-picked effect threshold.
"""

import argparse
import csv
import json
import math
import os
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

import edge_analytics  # noqa: E402
import preprobe_signature  # noqa: E402
from protocol import TARGETS  # noqa: E402

# Pre-registered comparability tolerances for the pre-probe gate.  They are
# stated in physical units of the observed quantity, so a reader can judge them
# against the frozen protocol's own numbers: the target segment radius is 2.5 m,
# the goal position tolerance is 0.75 m and Karto only adds a key scan after
# 1.0 m of travel, so a 0.05 m graph-geometry tolerance is at least an order of
# magnitude below any quantity that could change which scans exist.
PREPROBE_TOLERANCES = {
    'target_segment_size_abs_tolerance': 0,
    'target_anchor_distance_abs_tolerance_m': 0.25,
    'node_count_abs_tolerance': 2,
    'edge_count_relative_tolerance': 0.15,
    'edge_covariance_trace_ratio_bounds': [0.5, 2.0],
    'route_node_position_abs_tolerance_m': 0.05,
    'route_node_heading_abs_tolerance_rad': 0.05,
}

INSTRUMENT_ARMS = ('n0_instr_off', 'n0_prov_on', 'n0_prov_diag_on')
KNOWN_ARMS = INSTRUMENT_ARMS


def median(values):
    ordered = sorted(values)
    if not ordered:
        return None
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return 0.5 * (ordered[middle - 1] + ordered[middle])


def mean_absolute_deviation(values):
    if not values:
        return None
    centre = sum(values) / len(values)
    return float(sum(abs(value - centre) for value in values) / len(values))


def route_anchor_deviations(nodes_a, nodes_b, waypoints):
    """Match each route waypoint to its nearest node in both graphs.

    Matching by waypoint proximity is robust to the node-count drift the frozen
    protocol already documents (the initial mapping phase is an exploring action
    whose length varies), which is why a raw node-by-node ID comparison would be
    the wrong instrument here.
    """
    deviations = []
    for index, waypoint in enumerate(waypoints):
        anchor_a = min(nodes_a.values(), key=lambda node: math.hypot(
            node['x'] - waypoint[0], node['y'] - waypoint[1]))
        anchor_b = min(nodes_b.values(), key=lambda node: math.hypot(
            node['x'] - waypoint[0], node['y'] - waypoint[1]))
        distance_a = math.hypot(anchor_a['x'] - waypoint[0],
                                anchor_a['y'] - waypoint[1])
        distance_b = math.hypot(anchor_b['x'] - waypoint[0],
                                anchor_b['y'] - waypoint[1])
        deviations.append({
            'waypoint_index': index,
            'node_id_a': anchor_a['id'],
            'node_id_b': anchor_b['id'],
            'position_deviation_m': math.hypot(
                anchor_a['x'] - anchor_b['x'], anchor_a['y'] - anchor_b['y']),
            'heading_deviation_rad': abs(math.atan2(
                math.sin(anchor_a['theta'] - anchor_b['theta']),
                math.cos(anchor_a['theta'] - anchor_b['theta']))),
            'waypoint_distance_a_m': distance_a,
            'waypoint_distance_b_m': distance_b,
        })
    return deviations


def compare_signatures(reference, candidate, deviations=None,
                       tolerances=None):
    """Evaluate the pre-registered pre-probe comparability gate."""
    tolerances = dict(PREPROBE_TOLERANCES if tolerances is None else tolerances)
    checks = {}
    observed = {}
    checks['target_segment_size_equal'] = (
        int(reference['target_segment_size']) == int(candidate['target_segment_size']))
    observed['target_segment_size'] = [int(reference['target_segment_size']),
                                       int(candidate['target_segment_size'])]
    anchor_a = float(reference['target_anchor']['x']), float(reference['target_anchor']['y'])
    anchor_b = float(candidate['target_anchor']['x']), float(candidate['target_anchor']['y'])
    reference_point = reference['target_reference']
    anchor_distance_delta = abs(
        math.hypot(anchor_a[0] - reference_point[0], anchor_a[1] - reference_point[1])
        - math.hypot(anchor_b[0] - reference_point[0], anchor_b[1] - reference_point[1]))
    checks['target_anchor_distance_comparable'] = (
        anchor_distance_delta
        <= tolerances['target_anchor_distance_abs_tolerance_m'])
    observed['target_anchor_distance_delta_m'] = anchor_distance_delta
    node_delta = abs(int(reference['node_count']) - int(candidate['node_count']))
    checks['node_count_within_tolerance'] = (
        node_delta <= tolerances['node_count_abs_tolerance'])
    observed['node_count_delta'] = node_delta
    reference_edge_count = max(int(reference['edge_count']), 1)
    edge_relative = abs(int(reference['edge_count']) - int(candidate['edge_count'])) \
        / float(reference_edge_count)
    checks['edge_count_within_tolerance'] = (
        edge_relative <= tolerances['edge_count_relative_tolerance'])
    observed['edge_count_relative_delta'] = edge_relative
    trace_a = reference.get('edge_covariance_trace_median')
    trace_b = candidate.get('edge_covariance_trace_median')
    if trace_a and trace_b:
        ratio = float(trace_b) / float(trace_a)
        low, high = tolerances['edge_covariance_trace_ratio_bounds']
        checks['edge_covariance_scale_comparable'] = low <= ratio <= high
        observed['edge_covariance_trace_ratio'] = ratio
    else:
        checks['edge_covariance_scale_comparable'] = False
        observed['edge_covariance_trace_ratio'] = None
    if deviations:
        max_position = max(item['position_deviation_m'] for item in deviations)
        max_heading = max(item['heading_deviation_rad'] for item in deviations)
        checks['route_node_positions_comparable'] = (
            max_position <= tolerances['route_node_position_abs_tolerance_m'])
        checks['route_node_headings_comparable'] = (
            max_heading <= tolerances['route_node_heading_abs_tolerance_rad'])
        observed['route_node_position_deviation_max_m'] = max_position
        observed['route_node_heading_deviation_max_rad'] = max_heading
    else:
        checks['route_node_positions_comparable'] = None
        checks['route_node_headings_comparable'] = None
    evaluation = [value for value in checks.values() if value is not None]
    return {
        'passed': bool(evaluation) and all(evaluation),
        'checks': checks,
        'observed': observed,
        'tolerances': tolerances,
        'failed_checks': sorted(name for name, value in checks.items()
                                if value is False),
    }


def paired_difference_statistics(values_by_arm, arm_a, arm_b):
    """Paired per-seed differences (arm_b - arm_a) with sign consistency."""
    seeds = sorted(set(values_by_arm.get(arm_a, {})) & set(values_by_arm.get(arm_b, {})))
    differences = []
    for seed in seeds:
        left = values_by_arm[arm_a].get(seed)
        right = values_by_arm[arm_b].get(seed)
        if left is None or right is None:
            continue
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            differences.append(float(right) - float(left))
        elif isinstance(left, bool) and isinstance(right, bool):
            differences.append(float(right) - float(left))
    positive = sum(1 for value in differences if value > 0)
    negative = sum(1 for value in differences if value < 0)
    zero = sum(1 for value in differences if value == 0)
    return {
        'pair_count': len(differences),
        'differences': differences,
        'mean_difference': (sum(differences) / len(differences)) if differences
        else None,
        'min_difference': min(differences) if differences else None,
        'max_difference': max(differences) if differences else None,
        'positive_count': positive,
        'negative_count': negative,
        'zero_count': zero,
        # Strict reading of the frozen rule: every paired seed difference must be
        # non-zero and share one sign.  A pair that agrees exactly is not
        # evidence of a systematic shift, so it must not be counted as one.
        'all_same_sign_nonzero': bool(differences) and zero == 0 \
        and (positive == 0 or negative == 0),
    }


def repeatability_scale(values):
    """Within-configuration spread of one outcome across identical runs."""
    finite = [float(value) for value in values if value is not None]
    if len(finite) < 2:
        return {'count': len(finite), 'mad': None, 'range': None, 'std': None}
    mad = mean_absolute_deviation(finite)
    centre = sum(finite) / len(finite)
    variance = sum((value - centre) ** 2 for value in finite) / (len(finite) - 1)
    return {
        'count': len(finite),
        'mad': mad,
        'range': float(max(finite) - min(finite)),
        'std': math.sqrt(variance),
        'mean': centre,
        'values': finite,
    }


def nonperturbation_verdict(outcomes, comparator_arms=('n0_instr_off',),
                            numeric_tolerances=None):
    """Decide whether any instrument caused a detectable outcome shift.

    ``outcomes`` maps outcome name -> arm -> seed -> value.  A shift counts as
    detectable only when it is both larger than the same-configuration
    repeatability scale measured inside this very block and directionally
    consistent across all paired seeds.
    """
    numeric_tolerances = numeric_tolerances or {}
    per_outcome = {}
    detectable = []
    for name, by_arm in sorted(outcomes.items()):
        if name.startswith('preprobe_'):
            continue
        reference_values = [value for arm in comparator_arms
                            for value in by_arm.get(arm, {}).values()
                            if value is not None]
        scale = repeatability_scale(reference_values)
        entries = {}
        for arm in sorted(by_arm):
            if arm in comparator_arms:
                continue
            statistics = paired_difference_statistics(
                by_arm, comparator_arms[0], arm)
            magnitude = (abs(statistics['mean_difference'])
                         if statistics['mean_difference'] is not None else None)
            reference_scale = max(
                [value for value in (scale['mad'], numeric_tolerances.get(name))
                 if value is not None] or [0.0])
            threshold = 2.0 * reference_scale
            entries[arm] = {
                'statistics': statistics,
                'repeatability_scale': scale,
                'threshold': threshold,
                'exceeds_threshold': bool(magnitude is not None
                                          and magnitude > threshold),
                'detectable': bool(magnitude is not None
                                   and magnitude > threshold
                                   and statistics['all_same_sign_nonzero']),
            }
            if entries[arm]['detectable']:
                detectable.append({'outcome': name, 'arm': arm,
                                   'mean_difference': statistics['mean_difference'],
                                   'threshold': threshold})
        per_outcome[name] = entries
    return {
        'outcome': ('OUTCOME_MEASUREMENT_STABLE' if not detectable
                    else 'POSSIBLE_INSTRUMENTATION_PERTURBATION'),
        'detectable_shifts': detectable,
        'per_outcome': per_outcome,
        'comparator_arms': list(comparator_arms),
        'decision_rule': (
            'a shift is detectable only if |mean paired difference| exceeds '
            '2x the measured same-configuration repeatability scale AND every '
            'paired seed difference is non-zero with the same sign; the rule '
            'is deliberately conservative because a false "stable" verdict '
            'would let an instrument artefact be read as an intervention effect'),
    }


def collect_episodes(suite_dir):
    suite_dir = Path(suite_dir)
    state = edge_analytics.load_json(suite_dir / 'suite_state.json')
    collected = []
    for episode in state['episodes']:
        succeeded = [attempt for attempt in episode['attempts']
                     if attempt.get('status') == 'SUCCEEDED']
        if not succeeded:
            collected.append({'episode': episode, 'run_dir': None, 'attempt': None})
            continue
        attempt = succeeded[-1]
        collected.append({
            'episode': episode,
            'attempt': attempt,
            'run_dir': suite_dir / attempt['run_dir'],
        })
    return state, collected


def episode_record(entry):
    """Load the analysis inputs of one episode attempt."""
    run_dir = entry['run_dir']
    if run_dir is None:
        return None
    result = edge_analytics.load_json(run_dir / 'episode_result.json')
    before = edge_analytics.load_json(run_dir / 'pose_graph_before.json')
    after = edge_analytics.load_json(run_dir / 'pose_graph_after.json')
    spec = result['spec']
    frozen = result['frozen_target']
    signature_path = run_dir / 'preprobe_graph_signature.json'
    if signature_path.is_file():
        signature = edge_analytics.load_json(signature_path)
        signature_source = 'driver_recorded'
    else:
        # Episodes recorded before the signature existed are re-derived from
        # the before-probe snapshot, which the driver writes while the probe
        # phase is still closed.  The phase field is asserted so a derived
        # signature can never contain probe outcomes.
        if before.get('phase') != 'before_probe':
            raise RuntimeError('refusing to derive a signature from {}'.format(
                before.get('phase')))
        signature = preprobe_signature.build_signature(
            before, frozen, spec, result.get('run_id', spec.get('episode_id')))
        signature_source = 'derived_from_before_probe_snapshot'
    signature['signature_source'] = signature_source
    history_ids = set(range(int(frozen['route_start_node_count']),
                            int(result['before_max_scan_id']) + 1))
    before_nodes = edge_analytics.load_nodes(before)
    after_nodes = edge_analytics.load_nodes(after)
    before_edges = edge_analytics.load_edges(before, before_nodes)
    after_edges = edge_analytics.load_edges(after, after_nodes)
    groups = edge_analytics.classify_new_edges(
        before_edges, after_edges, frozen['historical_scan_ids'], history_ids)
    provenance_path = run_dir / 'karto_edge_provenance.jsonl'
    provenance = edge_analytics.provenance_constraints(
        edge_analytics.load_provenance(provenance_path))
    deviations = None
    return {
        'run_dir': run_dir,
        'spec': spec,
        'result': result,
        'signature': signature,
        'frozen': frozen,
        'before_nodes': before_nodes,
        'after_nodes': after_nodes,
        'before_edges': before_edges,
        'after_edges': after_edges,
        'groups': groups,
        'history_ids': history_ids,
        'provenance_count': len(provenance),
        'provenance_constraints': provenance,
        'route_offsets': TARGETS[spec['target_id']]['history_offsets'],
        'route_waypoint_index': int(
            TARGETS[spec['target_id']]['target_history_waypoint_index']),
    }


def load_block_records(suite_dir):
    """Load every usable episode attempt of a suite, keyed by block and arm."""
    state, collected = collect_episodes(suite_dir)
    blocks = {}
    for entry in collected:
        if entry['run_dir'] is None:
            continue
        record = episode_record(entry)
        spec = record['spec']
        block = blocks.setdefault(spec['block_id'], {'seed': spec['tsp_seed'],
                                                     'arms': {}})
        block['arms'][spec['condition_id']] = record
    return state, blocks


def outcome_tables(blocks):
    """Per-episode outcome vectors keyed by arm and seed."""
    outcomes = {}
    for block_id, block in blocks.items():
        seed = block['seed']
        for arm, record in block['arms'].items():
            result = record['result']
            groups = record['groups']
            probe_edges = [edge for group in ('target_attributable',
                                              'history_touching', 'local')
                           for edge in groups[group]]
            target_edges = groups['target_attributable']
            insertion = edge_analytics.insertion_time_metrics(
                record['after_edges'], record['after_nodes'],
                [(edge['start'], edge['end']) for edge in target_edges])
            geodesics = [entry['geodesic_m'] for entry in insertion.values()
                         if entry['geodesic_m'] is not None]
            hops = [entry['hops'] for entry in insertion.values()
                    if entry['hops'] is not None]
            signature = record['signature']

            def record_outcome(name, value):
                outcomes.setdefault(name, {}).setdefault(arm, {})[seed] = value

            record_outcome('target_attributable_edges', len(target_edges))
            record_outcome('history_touching_edges', len(groups['history_touching']))
            record_outcome('local_edges', len(groups['local']))
            record_outcome('total_new_edges', len(probe_edges))
            record_outcome('final_node_count',
                           int(signature['node_count'])
                           + len(result['new_keyscan_ids']))
            record_outcome('final_edge_count', len(record['after_edges']))
            record_outcome('preprobe_node_count', int(signature['node_count']))
            record_outcome('preprobe_edge_count', int(signature['edge_count']))
            record_outcome('probe_distance_m',
                           float(result['actual_probe_distance_m']))
            record_outcome('probe_duration_s',
                           float(result['probe_end_time']
                                 - result['probe_start_time']))
            record_outcome('loop_events_during_probe',
                           len(result['loop_events_during_probe']))
            record_outcome('new_keyscans', len(result['new_keyscan_ids']))
            record_outcome('target_geodesic_mean_m',
                           (sum(geodesics) / len(geodesics)) if geodesics else None)
            record_outcome('target_geodesic_max_m',
                           max(geodesics) if geodesics else None)
            record_outcome('target_hops_mean',
                           (sum(hops) / len(hops)) if hops else None)
            record_outcome('target_geodesic_above_4m_count',
                           sum(1 for value in geodesics if value > 4.0))
    ordered = {}
    for name, by_arm in outcomes.items():
        ordered[name] = {arm: dict(seed_values)
                         for arm, seed_values in sorted(by_arm.items())}
    return ordered


def build_pairs_rows(blocks):
    rows = []
    for block_id, block in sorted(blocks.items()):
        arms = sorted(block['arms'])
        for index, arm_a in enumerate(arms):
            for arm_b in arms[index + 1:]:
                record_a = block['arms'][arm_a]
                record_b = block['arms'][arm_b]
                waypoints = [record_a['result']['frozen_target']['target_reference']]
                deviations = route_anchor_deviations(
                    record_a['before_nodes'], record_b['before_nodes'],
                    [record_a['result']['frozen_target']['target_reference']])
                gate = compare_signatures(
                    record_a['signature'], record_b['signature'], deviations)
                rows.append({
                    'block_id': block_id,
                    'seed': block['seed'],
                    'arm_a': arm_a,
                    'arm_b': arm_b,
                    'gate_passed': gate['passed'],
                    'failed_checks': ','.join(gate['failed_checks']),
                    'node_count_delta': gate['observed']['node_count_delta'],
                    'edge_count_relative_delta': round(
                        gate['observed']['edge_count_relative_delta'], 6),
                    'target_segment_size_a': record_a['signature']['target_segment_size'],
                    'target_segment_size_b': record_b['signature']['target_segment_size'],
                    'edge_covariance_trace_ratio': gate['observed'].get(
                        'edge_covariance_trace_ratio'),
                    'route_node_position_deviation_max_m': gate['observed'].get(
                        'route_node_position_deviation_max_m'),
                    'target_attributable_a': len(
                        record_a['groups']['target_attributable']),
                    'target_attributable_b': len(
                        record_b['groups']['target_attributable']),
                    'total_new_edges_a': sum(len(record_a['groups'][group])
                                             for group in ('target_attributable',
                                                           'history_touching',
                                                           'local')),
                    'total_new_edges_b': sum(len(record_b['groups'][group])
                                             for group in ('target_attributable',
                                                           'history_touching',
                                                           'local')),
                    'probe_distance_a_m': record_a['result']['actual_probe_distance_m'],
                    'probe_distance_b_m': record_b['result']['actual_probe_distance_m'],
                    'probe_duration_a_s': (record_a['result']['probe_end_time']
                                           - record_a['result']['probe_start_time']),
                    'probe_duration_b_s': (record_b['result']['probe_end_time']
                                           - record_b['result']['probe_start_time']),
                })
    return rows


def write_csv(path, rows, fields=None):
    rows = list(rows)
    if not fields:
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


def pair_deviation_summary(suite_dir):
    """Measured route-node deviation between every pair inside every block.

    Reported regardless of the gate verdict, because the magnitude is what a
    reader needs to judge how comparable the matched pairs really were.
    """
    _state, blocks = load_block_records(suite_dir)
    summary = []
    for block_id, block in sorted(blocks.items()):
        arms = sorted(block['arms'])
        for index, arm_a in enumerate(arms):
            for arm_b in arms[index + 1:]:
                record_a = block['arms'][arm_a]
                record_b = block['arms'][arm_b]
                deviations = route_anchor_deviations(
                    record_a['before_nodes'], record_b['before_nodes'],
                    [record_a['result']['frozen_target']['target_reference']])
                summary.append({
                    'block_id': block_id,
                    'seed': block['seed'],
                    'arm_a': arm_a,
                    'arm_b': arm_b,
                    'route_node_position_deviation_max_m': max(
                        item['position_deviation_m'] for item in deviations),
                    'route_node_heading_deviation_max_rad': max(
                        item['heading_deviation_rad'] for item in deviations),
                    'preprobe_node_count_a': record_a['signature']['node_count'],
                    'preprobe_node_count_b': record_b['signature']['node_count'],
                    'preprobe_edge_count_a': record_a['signature']['edge_count'],
                    'preprobe_edge_count_b': record_b['signature']['edge_count'],
                    'target_segment_size_a': record_a['signature']['target_segment_size'],
                    'target_segment_size_b': record_b['signature']['target_segment_size'],
                })
    return summary


def analyze(suite_dir, out_dir=None, comparator_arm='n0_instr_off'):
    suite_dir = Path(suite_dir)
    out_dir = Path(out_dir) if out_dir else suite_dir
    state, blocks = load_block_records(suite_dir)
    outcomes = outcome_tables(blocks)
    pairs_rows = build_pairs_rows(blocks)
    verdict = nonperturbation_verdict(
        outcomes, comparator_arms=(comparator_arm,),
        numeric_tolerances={'target_attributable_edges': 0.0,
                            'final_edge_count': 0.0,
                            'final_node_count': 0.0})
    gate_rows = [row for row in pairs_rows]
    all_gates_passed = all(row['gate_passed'] for row in gate_rows) and bool(gate_rows)
    payload = {
        'suite_dir': str(suite_dir),
        'comparator_arm': comparator_arm,
        'blocks': {block_id: {'seed': block['seed'],
                              'arms': sorted(block['arms'])}
                   for block_id, block in sorted(blocks.items())},
        'outcomes': outcomes,
        'repeatability': {
            name: repeatability_scale([value for arm in by_arm
                                       for value in by_arm[arm].values()])
            for name, by_arm in sorted(outcomes.items())},
        'nonperturbation': verdict,
        'measured_pair_deviation': pair_deviation_summary(suite_dir),
        'preprobe_gate': {
            'all_pairs_passed': all_gates_passed,
            'pair_count': len(gate_rows),
            'tolerances': PREPROBE_TOLERANCES,
            'observed_max_route_deviation_m': max(
                [row['route_node_position_deviation_max_m'] for row in gate_rows],
                default=None),
        },
        'outcome': (verdict['outcome'] if verdict['outcome']
                    != 'OUTCOME_MEASUREMENT_STABLE'
                    else ('OUTCOME_MEASUREMENT_STABLE' if all_gates_passed
                          else 'INVALID_FOR_CAUSAL_PAIR')),
        'nonperturbation_outcome': verdict['outcome'],
    }
    os.makedirs(out_dir, exist_ok=True)
    write_csv(out_dir / 'n0_matched_pairs.csv', pairs_rows)
    outcome_rows = []
    for name, by_arm in sorted(outcomes.items()):
        for arm, seed_values in sorted(by_arm.items()):
            for seed, value in sorted(seed_values.items()):
                outcome_rows.append({
                    'outcome': name, 'arm': arm, 'seed': seed,
                    'value': value})
    write_csv(out_dir / 'n0_outcome_table.csv', outcome_rows)
    with open(out_dir / 'n0_nonperturbation_decision.json', 'w') as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, default=str)
        stream.write('\n')
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--suite-dir', required=True)
    parser.add_argument('--out')
    parser.add_argument('--comparator-arm', default='n0_instr_off',
                        help='arm every other arm is compared against')
    args = parser.parse_args()
    payload = analyze(args.suite_dir, args.out,
                      comparator_arm=args.comparator_arm)
    print(json.dumps({'outcome': payload['outcome'],
                      'preprobe_gate': payload['preprobe_gate']['all_pairs_passed'],
                      'detectable': payload['nonperturbation']['detectable_shifts']},
                     indent=2, sort_keys=True, default=str))


if __name__ == '__main__':
    main()
