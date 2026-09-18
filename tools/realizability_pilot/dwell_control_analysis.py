#!/usr/bin/python3
"""Outcome analysis for v10, callable only after its physical budget gate."""

import argparse
import csv
import json
import math
from pathlib import Path

from common_prefix_analysis import analyze_branch, load_json, write_csv


BRANCHES = ('A0_baseline', 'A1_dwell', 'A2_sweep90')
CONTRASTS = (('A2_sweep90', 'A0_baseline'),
             ('A1_dwell', 'A0_baseline'),
             ('A2_sweep90', 'A1_dwell'))


def science_available(root):
    gate = load_json(Path(root) / 'analysis/budget_gate.json')
    return gate.get('verdict') == 'BUDGET_MATCH_PASS'


def contrasts(metrics_rows):
    by_branch = {row['branch']: row for row in metrics_rows}
    fields = ('distance_m', 'duration_s', 'raw_scan_count',
              'accepted_keyscan_count', 'new_edge_count', 'E_T_count',
              'E_N_count', 'local_edge_count', 'delta_U_T',
              'graph_d_opt_all', 'posterior_target_trace_all',
              'posterior_current_trace_all',
              'posterior_target_ablation_delta_trace',
              'posterior_current_ablation_delta_trace')
    rows = []
    for left, right in CONTRASTS:
        for metric in fields:
            left_value, right_value = by_branch[left][metric], by_branch[right][metric]
            rows.append({'contrast': '{}-{}'.format(left, right),
                         'left': left, 'right': right, 'metric': metric,
                         'left_value': left_value, 'right_value': right_value,
                         'paired_difference': (float(left_value) -
                                               float(right_value))})
    return rows


def apply_connectivity_policy(metrics):
    if metrics['history_ablation_disconnects_graph']:
        metrics['delta_U_H_numeric_not_interpreted'] = metrics['delta_U_H']
        metrics['delta_U_H'] = None
        metrics['delta_U_H_per_m'] = None
        metrics['delta_U_H_per_s'] = None
        metrics['delta_U_H_status'] = 'CONNECTIVITY_CRITICAL_UNBOUNDED'
    else:
        metrics['delta_U_H_numeric_not_interpreted'] = None
        metrics['delta_U_H_status'] = 'FINITE_CONNECTED'
    return metrics


def add_posterior_summaries(metrics, posterior_rows):
    index = {(row['variant'], row['group']): row for row in posterior_rows}
    for short, group in (('target', 'target_segment'),
                         ('current', 'current_pose')):
        all_row = index[('all_constraints', group)]
        impact = index[('target_removed_impact', group)]
        metrics['posterior_{}_trace_all'.format(short)] = all_row['trace_mean']
        metrics['posterior_{}_logdet_all'.format(short)] = all_row['logdet_mean']
        metrics['posterior_{}_ablation_delta_trace'.format(short)] = \
            impact['trace_mean']
        metrics['posterior_{}_ablation_delta_logdet'.format(short)] = \
            impact['logdet_mean']
        impact['trace_mean_per_m'] = (impact['trace_mean'] /
                                      metrics['distance_m'])
        impact['trace_mean_per_s'] = (impact['trace_mean'] /
                                      metrics['duration_s'])
        impact['logdet_mean_per_m'] = (impact['logdet_mean'] /
                                       metrics['distance_m'])
        impact['logdet_mean_per_s'] = (impact['logdet_mean'] /
                                       metrics['duration_s'])
    return metrics


def analyze(root, canonical_attempt, out_dir):
    root = Path(root).resolve()
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if not science_available(root):
        raise RuntimeError('science outcomes sealed: physical budget gate absent/failed')
    frozen = load_json(Path(canonical_attempt) / 'frozen_target.json')
    capture_summary = load_json(root / 'analysis/fresh_capture_summary.json')
    raw_dirs = {row['branch']: row['raw_dir']
                for row in capture_summary['branches']}
    metrics_rows, constraint_rows, posterior_rows = [], [], []
    analysis_gates = {}
    for branch in BRANCHES:
        metrics, constraints_, posterior, passed = analyze_branch(
            root, branch, frozen, raw_dir_override=raw_dirs[branch])
        # The reduced-Laplacian history ablation is not a finite scalar utility
        # when it disconnects the graph.  Preserve the computed diagnostic only
        # under an explicitly non-interpretable field.
        apply_connectivity_policy(metrics)
        add_posterior_summaries(metrics, posterior)
        metrics_rows.append(metrics)
        constraint_rows.extend(constraints_)
        posterior_rows.extend(posterior)
        analysis_gates[branch] = passed
    contrast_rows = contrasts(metrics_rows)
    hashes = {row['preprobe_graph_hash'] for row in metrics_rows}
    summary = {
        'protocol': 'v10 time-matched dwell controlled n=1',
        'scope': 'fresh controlled batch; no confirmatory expansion',
        'science_unlocked_by_budget_gate': True,
        'preprobe_graph_hash_identical': len(hashes) == 1,
        'preprobe_graph_hashes': sorted(hashes),
        'expected_canonical_graph_hash':
            'd697659a6ca52d529a14171c3b383fb2b83696d108874edfbf579f570b29fe88',
        'expected_hash_matches': hashes == {
            'd697659a6ca52d529a14171c3b383fb2b83696d108874edfbf579f570b29fe88'},
        'analysis_pipeline_pass': all(analysis_gates.values()),
        'branches': metrics_rows,
        'contrasts': contrast_rows,
        'delta_U_T_is_primary': True,
        'delta_U_H_policy': ('numeric only when history-removed graph remains '
                             'connected; otherwise connectivity-critical flag'),
    }
    write_csv(out_dir / 'branch_metrics.csv', metrics_rows)
    write_csv(out_dir / 'realized_constraints.csv', constraint_rows)
    write_csv(out_dir / 'posterior_uncertainty.csv', posterior_rows)
    write_csv(out_dir / 'contrasts.csv', contrast_rows)
    with open(out_dir / 'science_summary.json', 'w') as stream:
        json.dump(summary, stream, indent=2, sort_keys=True)
        stream.write('\n')
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--canonical-attempt', required=True)
    parser.add_argument('--out-dir', required=True)
    args = parser.parse_args()
    print(json.dumps(analyze(args.root, args.canonical_attempt, args.out_dir),
                     indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
