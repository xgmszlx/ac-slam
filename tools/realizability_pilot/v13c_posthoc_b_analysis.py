#!/usr/bin/python3
"""Frozen post-lock analysis for the v13-C Target-B diagnostic."""

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

import edge_analytics
from common_prefix_analysis import (
    LOCAL_LABEL, NONTARGET_LABEL, TARGET_LABEL, classify_new_edges,
    edges_from_graph, nodes_from_graph, paper_graph_utilities,
)
from confirmatory_v13c_analysis import (
    circular_fov_union, mechanism_summary, reconstruct_keyscans,
    target_information,
)
from controlled_branch_suite import atomic_json
from v13c_posthoc_b_protocol import (
    ARMS, BLOCKS, DECISION_LABELS, PREREGISTRATION_PATH, RESULT_ROOT,
    ROOT, SOURCE_ROOT, load_json, prefix_reference, sha256,
    source_block_dir, source_capture_dir, verify_source_immutable,
)


def read_jsonl(path):
    with open(path) as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_csv(path, rows):
    rows = list(rows)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with open(path, 'w', newline='') as stream:
        if fields:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)


def analysis_preflight(root):
    root = Path(root)
    lock = load_json(root / 'REPLAY_COLLECTION_LOCKED.json')
    if lock.get('status') != 'REPLAY_COLLECTION_LOCKED':
        raise RuntimeError('analysis requires replay collection lock')
    if lock.get('completed_branches') != 24:
        raise RuntimeError('analysis requires all 24 diagnostic replays')
    prereg = load_json(
        root / 'preregistration/posthoc_diagnostic_preregistration.json')
    if sha256(root / 'preregistration/posthoc_diagnostic_preregistration.json') != \
            lock.get('protocol_sha256'):
        raise RuntimeError('post-hoc preregistration hash mismatch')
    for relative, expected in prereg['code_hashes'].items():
        if sha256(ROOT / relative) != expected:
            raise RuntimeError('frozen code changed: {}'.format(relative))
    source_check = verify_source_immutable(prereg['source_capture_hashes'])
    if not source_check['passed']:
        raise RuntimeError('original v13-C root changed')
    reproduction = load_json(
        root / 'technical/B_H4_reproducibility_gate.json')
    if not reproduction.get('passed'):
        raise RuntimeError('B-H4 replay reproducibility failed')
    crop = load_json(root / 'cropping/crop_summary.json')
    if crop.get('status') != 'EXPOSURE_MATCH_VALID':
        raise RuntimeError('exposure matching technical gate failed')
    return prereg, lock, reproduction, crop


def replay_dir(root, mode, block_id, arm):
    return Path(root) / 'replays' / mode / block_id / arm


def raw_path(root, mode, block_id, arm):
    if mode == 'FULL':
        return source_capture_dir(block_id, arm) / 'probe_stream_raw.jsonl'
    return (Path(root) / 'cropping' / block_id / arm /
            'probe_stream_matched.jsonl')


def branch_data(root, mode, block_id, arm):
    replay = replay_dir(root, mode, block_id, arm)
    before_graph = load_json(replay / 'graph_pre.json')
    final_graph = load_json(replay / 'graph_final.json')
    before_nodes = nodes_from_graph(before_graph)
    final_nodes = nodes_from_graph(final_graph)
    before_edges = edges_from_graph(before_graph, before_nodes)
    final_edges = edges_from_graph(final_graph, final_nodes)
    frozen = load_json(source_block_dir(block_id) / 'frozen_target.json')
    target_ids = [int(value) for value in frozen['historical_scan_ids']]
    history_ids = set(before_nodes)
    new_edges = classify_new_edges(
        before_edges, final_edges, target_ids, history_ids)
    posterior = target_information(final_nodes, final_edges, target_ids)
    utilities = paper_graph_utilities(final_nodes, final_edges, new_edges)
    replay_result = load_json(replay / 'unified_replay_result.json')
    accepted = len(final_nodes) - len(before_nodes)
    keyscans, keyscan_status = reconstruct_keyscans(
        replay / 'combined_stream.jsonl',
        replay_result['prefix_record_count'], accepted)
    capture = load_json(
        source_capture_dir(block_id, arm) / 'capture_result.json')
    raw = read_jsonl(raw_path(root, mode, block_id, arm))
    counts = {label: sum(edge['attribution'] == label for edge in new_edges)
              for label in (TARGET_LABEL, NONTARGET_LABEL, LOCAL_LABEL)}
    provenance_records = edge_analytics.provenance_constraints(
        edge_analytics.load_provenance(replay / 'edge_provenance.jsonl'))
    provenance = {int(row['creation_sequence']) - 1: row
                  for row in provenance_records}
    insertion = edge_analytics.insertion_time_metrics(
        final_edges, final_nodes,
        [(edge['start'], edge['end']) for edge in new_edges])
    constraints = []
    for edge in new_edges:
        record = provenance.get(edge['index'], {})
        covariance = np.asarray(edge['covariance_3x3'], dtype=float)
        eigen_cov = np.linalg.eigvalsh(covariance)
        eigen_info = np.linalg.eigvalsh(np.linalg.inv(covariance))
        metric = insertion[tuple(sorted((edge['start'], edge['end'])))]
        constraints.append({
            'mode': mode,
            'block_id': block_id,
            'target': 'target_B',
            'arm': arm,
            'edge_index': edge['index'],
            'source': edge['start'],
            'target_state': edge['end'],
            'attribution': edge['attribution'],
            'creation_provenance': record.get('creation_provenance'),
            'creation_stage': record.get('creation_stage'),
            'matcher_type': record.get('matcher_type'),
            'match_response': record.get('match_response'),
            'measurement_dx': edge['measurement']['dx'],
            'measurement_dy': edge['measurement']['dy'],
            'measurement_dtheta': edge['measurement']['dtheta'],
            'covariance_eigenvalues': json.dumps(eigen_cov.tolist()),
            'information_eigenvalues': json.dumps(eigen_info.tolist()),
            'geodesic_at_insertion_m': metric['geodesic_m'],
            'hops_at_insertion': metric['hops'],
            'cycle_length_edges': (metric['hops'] + 1
                                   if metric['hops'] is not None else None),
            'explicit_try_close_loop': bool(
                'TRY_CLOSE_LOOP' in str(record.get('creation_stage', '')) or
                'TRY_CLOSE_LOOP' in str(record.get('matcher_type', '')) or
                'TRY_CLOSE_LOOP' in str(record.get(
                    'creation_provenance', ''))),
        })
    fov = circular_fov_union(raw)
    crop_duration = (float(raw[-1]['stamp']) - float(raw[0]['stamp'])
                     if len(raw) > 1 else 0.0)
    row = {
        'mode': mode,
        'block_id': block_id,
        'target': 'target_B',
        'arm': arm,
        'distance_m': capture['actual_distance_m'],
        'original_duration_s': capture['actual_duration_s'],
        'analyzed_scan_span_s': crop_duration,
        'raw_scan_count': len(raw),
        'original_raw_scan_count': capture['raw_scan_count'],
        'accepted_keyscan_count': accepted,
        'keyscan_reconstruction_status': keyscan_status,
        'heading_triggered_keyscan_count': sum(
            item['criterion'] == 'HEADING' for item in keyscans),
        'distance_triggered_keyscan_count': sum(
            item['criterion'] == 'DISTANCE' for item in keyscans),
        'fov_union_rad': fov,
        'fov_union_deg': math.degrees(fov) if fov is not None else None,
        'new_edge_count': len(new_edges),
        'E_T_count': counts[TARGET_LABEL],
        'E_N_count': counts[NONTARGET_LABEL],
        'local_edge_count': counts[LOCAL_LABEL],
        'target_trace': posterior['trace'],
        'target_logdet': posterior['logdet'],
        'J_T': posterior['J_T'],
        'U_all': utilities['all'],
        'U_without_target': utilities['target_removed'],
        'delta_U_T': (None if utilities['target_removed_disconnects_graph']
                      else utilities['all'] - utilities['target_removed']),
        'target_removed_disconnects_graph':
            utilities['target_removed_disconnects_graph'],
        'U_without_history': utilities['history_removed'],
        'history_removed_disconnects_graph':
            utilities['history_removed_disconnects_graph'],
    }
    detail = {
        'metrics': row,
        'target_ids': target_ids,
        'target_posterior': posterior,
        'keyscans': keyscans,
        'new_edges': new_edges,
        'provenance': provenance,
        'target_edge_pairs': sorted({
            tuple(sorted((edge['start'], edge['end']))) for edge in new_edges
            if edge['attribution'] == TARGET_LABEL}),
    }
    return row, detail, constraints


def contrasts(metrics):
    grouped = defaultdict(dict)
    for row in metrics:
        grouped[row['block_id']][row['arm']] = row
    output = []
    for block_id in BLOCKS:
        arms = grouped[block_id]
        output.append({
            'block_id': block_id,
            'J_A1': arms['A1_DWELL']['J_T'],
            'J_A3': arms['A3_MIN_TRIGGER']['J_T'],
            'J_A2': arms['A2_SWEEP90']['J_T'],
            'D_trigger': (arms['A3_MIN_TRIGGER']['J_T'] -
                          arms['A1_DWELL']['J_T']),
            'D_sweep': (arms['A2_SWEEP90']['J_T'] -
                        arms['A3_MIN_TRIGGER']['J_T']),
            'D_total': (arms['A2_SWEEP90']['J_T'] -
                        arms['A1_DWELL']['J_T']),
        })
    return output


def mechanism_extension(constraints):
    historical = [row for row in constraints
                  if row['attribution'] in (TARGET_LABEL, NONTARGET_LABEL)]
    hops = [int(row['hops_at_insertion']) for row in historical
            if row['hops_at_insertion'] is not None]
    geodesics = [float(row['geodesic_at_insertion_m']) for row in historical
                 if row['geodesic_at_insertion_m'] is not None]
    explicit = [row for row in constraints if row['explicit_try_close_loop']]
    return {
        'explicit_TRY_CLOSE_LOOP_count': len(explicit),
        'explicit_loop_verdict': (
            'NO_EXPLICIT_TRY_CLOSE_LOOP_OBSERVED' if not explicit else
            'EXPLICIT_TRY_CLOSE_LOOP_OBSERVED'),
        'historical_factor_count': len(historical),
        'historical_insertion_hops': {
            'min': min(hops) if hops else None,
            'median': float(np.median(hops)) if hops else None,
            'max': max(hops) if hops else None,
            'count_ge_3': sum(value >= 3 for value in hops),
            'count_ge_5': sum(value >= 5 for value in hops),
        },
        'historical_insertion_geodesic_m': {
            'min': min(geodesics) if geodesics else None,
            'median': float(np.median(geodesics)) if geodesics else None,
            'max': max(geodesics) if geodesics else None,
        },
        'creation_provenance': dict(Counter(
            row.get('creation_provenance') or 'UNKNOWN'
            for row in constraints)),
        'matcher_type': dict(Counter(
            row.get('matcher_type') or 'UNKNOWN' for row in constraints)),
    }


def analyze_mode(root, mode):
    metrics, constraints, details = [], [], {}
    for block_id in BLOCKS:
        for arm in ARMS:
            row, detail, rows = branch_data(root, mode, block_id, arm)
            metrics.append(row)
            constraints.extend(rows)
            details['{}:{}'.format(block_id, arm)] = detail
    paired = contrasts(metrics)
    mechanism = mechanism_summary(metrics, constraints, details)
    mechanism['graph_locality'] = mechanism_extension(constraints)
    directory = Path(root) / 'analysis' / mode
    directory.mkdir(parents=True, exist_ok=True)
    write_csv(directory / 'branch_metrics.csv', metrics)
    write_csv(directory / 'paired_contrasts.csv', paired)
    write_csv(directory / 'constraint_mechanism.csv', constraints)
    atomic_json(directory / 'branch_details.json', details)
    atomic_json(directory / 'mechanism_summary.json', mechanism)
    values = [row['D_sweep'] for row in paired]
    summary = {
        'mode': mode,
        'status': 'POSTHOC_DESCRIPTIVE_ONLY',
        'blocks': paired,
        'D_sweep': {
            'values': values,
            'positive': sum(value > 0.0 for value in values),
            'mean': float(np.mean(values)),
            'median': float(np.median(values)),
            'H1_H3_values': values[:3],
            'H1_H3_positive': sum(value > 0.0 for value in values[:3]),
            'H1_H3_mean': float(np.mean(values[:3])),
        },
        'mechanism': mechanism,
    }
    atomic_json(directory / 'summary.json', summary)
    return summary


def b_h4_j_consistency(full_summary):
    original_rows = list(csv.DictReader(open(
        SOURCE_ROOT / 'analysis/branch_metrics.csv')))
    expected = {row['arm']: float(row['J_T']) for row in original_rows
                if row['block_id'] == 'target_B_H4'}
    block = next(row for row in full_summary['blocks']
                 if row['block_id'] == 'B-H4')
    observed = {
        'A1_DWELL': block['J_A1'],
        'A3_MIN_TRIGGER': block['J_A3'],
        'A2_SWEEP90': block['J_A2'],
    }
    return {
        'expected': expected,
        'observed': observed,
        'exact': observed == expected,
        'max_abs_difference': max(
            abs(observed[arm] - expected[arm]) for arm in ARMS),
    }


def decision(full, matched, crop_valid):
    f = full['D_sweep']
    m = matched['D_sweep']
    support = (
        f['H1_H3_positive'] >= 2 and f['H1_H3_mean'] > 0.0 and
        f['positive'] >= 3 and
        m['H1_H3_positive'] >= 2 and m['H1_H3_mean'] > 0.0 and
        m['positive'] >= 3 and
        f['mean'] > 0.0 and m['mean'] > 0.0 and
        f['H1_H3_positive'] > 0 and m['H1_H3_positive'] > 0 and
        crop_valid)
    against = (
        f['H1_H3_positive'] <= 1 and f['H1_H3_mean'] <= 0.0 and
        m['H1_H3_positive'] <= 1 and m['H1_H3_mean'] <= 0.0 and
        f['positive'] <= 2 and f['mean'] <= 0.0 and
        m['positive'] <= 2 and m['mean'] <= 0.0)
    if support:
        return DECISION_LABELS[0]
    if against:
        return DECISION_LABELS[2]
    return DECISION_LABELS[1]


def analyze(root=RESULT_ROOT):
    root = Path(root)
    prereg, lock, reproduction, crop = analysis_preflight(root)
    full = analyze_mode(root, 'FULL')
    matched = analyze_mode(root, 'MATCHED')
    j_consistency = b_h4_j_consistency(full)
    if not j_consistency['exact']:
        raise RuntimeError('B-H4 J_T did not exactly reproduce')
    crop_valid = all(row['cropping_valid'] for row in crop['reports'])
    verdict = decision(full, matched, crop_valid)
    comparison = []
    by_full = {row['block_id']: row for row in full['blocks']}
    by_matched = {row['block_id']: row for row in matched['blocks']}
    for block_id in BLOCKS:
        comparison.append({
            'block_id': block_id,
            'D_sweep_FULL': by_full[block_id]['D_sweep'],
            'D_sweep_MATCHED': by_matched[block_id]['D_sweep'],
            'same_sign': ((by_full[block_id]['D_sweep'] > 0.0) ==
                          (by_matched[block_id]['D_sweep'] > 0.0)),
            'difference_MATCHED_minus_FULL': (
                by_matched[block_id]['D_sweep'] -
                by_full[block_id]['D_sweep']),
        })
    final = {
        'status': 'ANALYZED',
        'label': 'POSTHOC_NONCONFIRMATORY_TARGET_B_DIAGNOSTIC',
        'protocol_sha256': sha256(
            root / 'preregistration/posthoc_diagnostic_preregistration.json'),
        'posthoc_descriptive_only': True,
        'B_H4_ENDPOINT_PREVIOUSLY_OBSERVED': True,
        'B_H4_graph_reproducibility': reproduction,
        'B_H4_J_T_reproducibility': j_consistency,
        'FULL': full,
        'MATCHED': matched,
        'robustness': comparison,
        'diagnostic_decision': verdict,
        'original_v13C_confirmatory_status':
            'CONFIRMATORY_EXPERIMENT_TECHNICALLY_INCOMPLETE',
        'v13C_confirmatory_sample_changed': False,
        'automatic_next_phase_started': False,
    }
    atomic_json(root / 'analysis/diagnostic_summary.json', final)
    atomic_json(root / 'decision/posthoc_diagnostic_gate.json', final)
    print(json.dumps(final, indent=2, sort_keys=True))
    return final


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=RESULT_ROOT)
    args = parser.parse_args()
    analyze(args.root)


if __name__ == '__main__':
    main()

