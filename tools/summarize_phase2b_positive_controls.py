#!/usr/bin/python3
"""Finalize and aggregate completed Phase 2B positive-control trials."""

import argparse
import csv
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--root', type=Path,
        default=ROOT / 'results' / 'phase2b' / 'positive_control',
    )
    args = parser.parse_args()
    suite_root = args.root.resolve()
    rows = []
    invalid_trials = []
    for run_dir in sorted(suite_root.glob('trial_*')):
        result_path = run_dir / 'positive_control.json'
        if not result_path.is_file():
            continue
        raw_result = json.loads(result_path.read_text())
        if (
            raw_result.get('status') != 'SUCCEEDED'
            or not (run_dir / 'pose_graph_before.json').is_file()
            or not (run_dir / 'pose_graph_after.json').is_file()
        ):
            invalid_trials.append({
                'trial': int(run_dir.name.split('_')[1]),
                'status': raw_result.get('status'),
                'reason': raw_result.get('reason', 'missing complete before/after snapshots'),
                'counted_as_karto_negative': False,
            })
            continue
        subprocess.run([
            '/usr/bin/python3',
            str(ROOT / 'tools' / 'finalize_phase2b_positive_control.py'),
            '--run-dir', str(run_dir),
        ], check=True, capture_output=True, text=True)
        result = json.loads(result_path.read_text())
        rosout = (run_dir / 'rosout.log').read_text(errors='replace')
        all_accepted = re.findall(r'Add one Loop closure\.', rosout)
        revisit_accepted = result.get('karto_accepted_loop_events_during_revisit', [])
        targets = result.get('targets', [])
        correction = result.get('trajectory_correction', {})
        rows.append({
            'trial': int(run_dir.name.split('_')[1]),
            'success': bool(result['positive_control_success']),
            'history_node_count_before_revisit': result['before_node_count'],
            'node_count_after_revisit': result['after_node_count'],
            'accepted_closures_whole_run': len(all_accepted),
            'accepted_closures_during_explicit_revisit': len(revisit_accepted),
            'cross_cutoff_nonlocal_marker_edges': len(
                result.get('marker_nonlocal_history_link_edges', [])
            ),
            'targets_attempted': len(targets),
            'targets_succeeded': sum(
                target.get('action_state') == 3 for target in targets
            ),
            'historical_poses_compared': correction.get('compared_historical_poses'),
            'mean_historical_trajectory_correction_m': correction.get(
                'mean_translation_shift_m'
            ),
            'max_historical_trajectory_correction_m': correction.get(
                'max_translation_shift_m'
            ),
            'incremental_pose_graph_topic_stale': result.get(
                'incremental_pose_graph_topic_stale_after_exploration'
            ),
        })
    if not rows:
        raise SystemExit('No completed positive-control trials')
    with (suite_root / 'positive_control_summary.csv').open('w', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    successes = sum(row['success'] for row in rows)
    summary = {
        'requested_valid_trials': 3,
        'attempted_trials': len(rows) + len(invalid_trials),
        'valid_completed_trials': len(rows),
        'invalid_trials': invalid_trials,
        'successful_trials': successes,
        'karto_success_rate_given_valid_revisit': successes / len(rows),
        'end_to_end_attempt_success_rate': successes / (len(rows) + len(invalid_trials)),
        'success_definition': (
            'At least one Karto accepted-loop callback during the explicit revisit '
            'and at least one new full-graph marker edge crossing the pre-revisit '
            'node cutoff with scan-index gap > 70.'
        ),
        'trials': rows,
        'instrumentation_finding': (
            'The custom incremental /slam_pose_graph stream can stop advancing '
            'after exploration; full /slam_path and /Mapper/closure_edges plus '
            'the accepted callback are used for the positive-control before/after audit.'
        ),
    }
    (suite_root / 'positive_control_summary.json').write_text(
        json.dumps(summary, indent=2, sort_keys=True) + '\n'
    )
    state = {
        'status': (
            'SUCCEEDED_WITH_INVALID_TRIALS' if len(rows) >= 3 and invalid_trials
            else 'SUCCEEDED' if len(rows) >= 3 else 'INCOMPLETE'
        ),
        'requested_valid_trials': 3,
        'attempted_trials': len(rows) + len(invalid_trials),
        'completed_trials': [
            {'trial': row['trial'], 'success': row['success']} for row in rows
        ],
        'invalid_trials': invalid_trials,
        'successful_trials': successes,
        'karto_success_rate_given_valid_revisit': successes / len(rows),
        'end_to_end_attempt_success_rate': successes / (len(rows) + len(invalid_trials)),
    }
    (suite_root / 'suite_state.json').write_text(
        json.dumps(state, indent=2, sort_keys=True) + '\n'
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
