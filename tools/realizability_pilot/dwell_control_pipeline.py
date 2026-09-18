#!/usr/bin/python3
"""Budget gate, common-prefix replay, and gated v10 science analysis."""

import argparse
import json
import math
import shutil
from pathlib import Path

from branch_replay import replay_branch
from common_prefix_signature import stream_hash
from controlled_branch_suite import atomic_json, load_json
from dwell_control_analysis import analyze
from dwell_control_suite import (BRANCHES, DISTANCE_TOLERANCE_M,
                                 RAW_RELATIVE_TOLERANCE, TIME_TOLERANCE_S,
                                 capture_metrics, relative_difference)
from stitch_probe_stream import stitch


def raw_dirs(root):
    summary = load_json(Path(root) / 'analysis/fresh_capture_summary.json')
    return {row['branch']: Path(row['raw_dir'])
            for row in summary['branches']}


def budget_gate(root):
    root = Path(root)
    dirs = raw_dirs(root)
    metrics = {branch: capture_metrics(load_json(
        dirs[branch] / 'capture_result.json')) for branch in BRANCHES}
    dwell, sweep = metrics['A1_dwell'], metrics['A2_sweep90']
    differences = {
        'distance_difference_m': abs(dwell['distance_m'] - sweep['distance_m']),
        'time_difference_s': abs(dwell['duration_s'] - sweep['duration_s']),
        'raw_scan_relative_difference': relative_difference(
            dwell['raw_scan_count'], sweep['raw_scan_count']),
    }
    passed = (
        differences['distance_difference_m'] <= DISTANCE_TOLERANCE_M and
        differences['time_difference_s'] <= TIME_TOLERANCE_S and
        differences['raw_scan_relative_difference'] <= RAW_RELATIVE_TOLERANCE)
    result = {
        'comparison': 'A1_dwell vs A2_sweep90',
        'budget_definition': {
            'included': ['GT distance', 'elapsed sensing time',
                         'raw LaserScan count'],
            'excluded': ['accepted Karto keyscan count'],
        },
        'thresholds': {'distance_difference_m_max': DISTANCE_TOLERANCE_M,
                       'time_difference_s_max': TIME_TOLERANCE_S,
                       'raw_scan_relative_difference_max':
                           RAW_RELATIVE_TOLERANCE},
        'arm_metrics': metrics, 'differences': differences,
        'verdict': 'BUDGET_MATCH_PASS' if passed else 'BUDGET_MATCH_INVALID',
        'science_outcomes_available': passed,
    }
    atomic_json(root / 'analysis/budget_gate.json', result)
    return result


def run(root, prefix, mapper_params, frozen_target, canonical_attempt,
        rate_hz=20.0):
    root = Path(root).resolve()
    prefix = Path(prefix).resolve()
    gate = budget_gate(root)
    if gate['verdict'] != 'BUDGET_MATCH_PASS':
        decision = {'decision': 'BUDGET_MATCH_INVALID',
                    'science_outcomes_available': False}
        (root / 'decision').mkdir(parents=True, exist_ok=True)
        atomic_json(root / 'decision/final_gate.json', decision)
        return {'budget_gate': gate, 'decision': decision}

    prefix_hash, prefix_count = stream_hash(prefix)
    common_manifest = {
        'source': str(prefix), 'sha256': prefix_hash,
        'record_count': prefix_count,
        'expected_preprobe_graph_hash':
            'd697659a6ca52d529a14171c3b383fb2b83696d108874edfbf579f570b29fe88',
        'frozen_from_v9': True,
    }
    (root / 'common_prefix').mkdir(parents=True, exist_ok=True)
    atomic_json(root / 'common_prefix/manifest.json', common_manifest)
    dirs = raw_dirs(root)
    replay_results = {}
    for branch in BRANCHES:
        branch_root = root / 'branches' / branch
        stitched_dir = branch_root / 'stitched'
        replay_dir = branch_root / 'replay'
        stitched_dir.mkdir(parents=True, exist_ok=True)
        combined = stitched_dir / 'combined_stream.jsonl'
        report_path = stitched_dir / 'stitch_report.json'
        if report_path.is_file() and combined.is_file():
            report = load_json(report_path)
        else:
            report = stitch(prefix, dirs[branch] / 'probe_stream_raw.jsonl',
                            combined)
            atomic_json(report_path, report)
        result_path = replay_dir / 'branch_replay_result.json'
        if result_path.is_file():
            replay_results[branch] = load_json(result_path)
        else:
            replay_results[branch] = replay_branch(
                combined, prefix, mapper_params, frozen_target, replay_dir,
                rate_hz=rate_hz)
    summary = analyze(root, canonical_attempt, root / 'analysis')
    capture_summary = load_json(root / 'analysis/fresh_capture_summary.json')
    captures = {row['branch']: row['capture']
                for row in capture_summary['branches']}
    dwell_execution = captures['A1_dwell'].get('dwell') or {}
    branch_start_pass = capture_summary['all_branch_starts_passed']
    action_execution_pass = (
        all(row['status'] == 'SUCCEEDED' for row in captures.values()) and
        dwell_execution.get('deliberate_yaw_command') is False and
        float(dwell_execution.get('distance_m', float('inf'))) <= 0.02 and
        float(dwell_execution.get('yaw_excursion_rad', float('inf'))) <= 0.02)
    graph_utility_pass = all(
        math.isfinite(float(row['delta_U_T']))
        for row in summary['branches'])
    gates = {
        'COMMON_PREFIX_IDENTICAL': (summary['preprobe_graph_hash_identical'] and
                                    summary['expected_hash_matches']),
        'BRANCH_START_PASS': branch_start_pass,
        'ACTION_EXECUTION_PASS': action_execution_pass,
        'DWELL_BUDGET_MATCH_PASS': gate['verdict'] == 'BUDGET_MATCH_PASS',
        'CONSTRAINT_ANALYTICS_PASS': summary['analysis_pipeline_pass'],
        'GRAPH_UTILITY_PASS': graph_utility_pass,
        'POSTERIOR_PIPELINE_PASS': summary['analysis_pipeline_pass'],
    }
    ready = all(gates.values())
    decision = {
        'decision': ('READY_FOR_CONFIRMATORY_COMMON_PREFIX_EXPERIMENT' if ready
                     else 'V10_PROOF_GATE_BLOCKER'),
        'gates': gates,
        'budget_gate': gate['verdict'],
        'science_outcomes_available': True,
        'preprobe_graph_hash_identical':
            summary['preprobe_graph_hash_identical'],
        'expected_hash_matches': summary['expected_hash_matches'],
        'analysis_pipeline_pass': summary['analysis_pipeline_pass'],
        'confirmatory_expansion_started': False,
    }
    (root / 'decision').mkdir(parents=True, exist_ok=True)
    atomic_json(root / 'decision/final_gate.json', decision)
    return {'budget_gate': gate, 'replays': replay_results,
            'science_summary': summary, 'decision': decision}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--mapper-params', required=True)
    parser.add_argument('--frozen-target', required=True)
    parser.add_argument('--canonical-attempt', required=True)
    parser.add_argument('--rate-hz', type=float, default=20.0)
    args = parser.parse_args()
    result = run(args.root, args.prefix, args.mapper_params,
                 args.frozen_target, args.canonical_attempt, args.rate_hz)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
