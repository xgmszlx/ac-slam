#!/usr/bin/python3

import json
import sys
import tempfile
import unittest
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

import dwell_control_analysis  # noqa: E402
import dwell_control_pipeline  # noqa: E402
import dwell_control_preflight  # noqa: E402
import dwell_control_suite  # noqa: E402


ROOT = THIS_DIR.parents[1]
V9 = ROOT / 'results/realizability_pilot/p1_common_prefix_v9_20260917'
ATTEMPT = (V9 / 'canonical_history/episodes' /
           '0001_v9_canonical_history_anchor_01/attempt_01')
SPECS = V9 / 'preregistration/controlled_action_specs_v2_uniform_approach.json'


class DwellControlTest(unittest.TestCase):
    def test_dwell_preserves_baseline_geometry_and_has_no_sweep(self):
        frozen = dwell_control_suite.load_frozen_specs(SPECS)
        a0 = frozen['actions']['A0_baseline']
        dwell = frozen['actions']['A1_dwell']
        self.assertTrue(dwell_control_suite.validate_dwell_action(a0, dwell))
        self.assertEqual(a0['action_waypoints'], dwell['action_waypoints'])
        self.assertFalse(any('sweep' in label.lower()
                             for label in dwell['action_labels']))

    def test_target_region_is_derived_from_frozen_ids_and_exact_gt_time(self):
        region = dwell_control_preflight.target_region(ATTEMPT)
        self.assertEqual([row['state_id'] for row in region['mappings']],
                         [13, 14, 15, 16, 17])
        self.assertTrue(region['not_derived_from_nominal_waypoint'])
        self.assertTrue(all(row['karto_vs_trajectory_slam_position_error_m'] < 1e-5
                            for row in region['mappings']))

    def test_timestamp_audit_schema_and_verdict(self):
        audit = dwell_control_preflight.timestamp_audit(ROOT)
        self.assertEqual(audit['schema_version'],
                         'v10_timestamp_source_audit_v1')
        self.assertEqual(audit['verdict'],
                         'DETERMINISTIC_RETIMING_ACCEPTABLE')
        self.assertTrue(all(audit['checks'].values()))

    def test_budget_uses_distance_time_raw_and_excludes_keyscan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = []
            values = {'A0_baseline': (14.0, 58.0, 580),
                      'A1_dwell': (14.0, 65.0, 650),
                      'A2_sweep90': (14.0, 65.1, 651)}
            for branch, (distance, duration, scans) in values.items():
                raw = root / branch
                raw.mkdir()
                (raw / 'capture_result.json').write_text(json.dumps({
                    'actual_distance_m': distance,
                    'actual_duration_s': duration,
                    'raw_scan_count': scans,
                    'accepted_keyscan_count': 999 if branch == 'A1_dwell' else 1,
                }))
                rows.append({'branch': branch, 'raw_dir': str(raw),
                             'capture': {}})
            (root / 'analysis').mkdir()
            (root / 'analysis/fresh_capture_summary.json').write_text(
                json.dumps({'branches': rows}))
            gate = dwell_control_pipeline.budget_gate(root)
            self.assertEqual(gate['verdict'], 'BUDGET_MATCH_PASS')
            self.assertEqual(gate['budget_definition']['excluded'],
                             ['accepted Karto keyscan count'])
            self.assertNotIn('accepted_keyscan_count', gate['arm_metrics']['A1_dwell'])

    def test_science_unavailable_before_budget_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'analysis').mkdir()
            (root / 'analysis/budget_gate.json').write_text(
                json.dumps({'verdict': 'BUDGET_MATCH_INVALID'}))
            self.assertFalse(dwell_control_analysis.science_available(root))

    def test_three_contrasts_and_connectivity_flag(self):
        template = {'distance_m': 1, 'duration_s': 2, 'raw_scan_count': 3,
                    'accepted_keyscan_count': 4, 'new_edge_count': 5,
                    'E_T_count': 6, 'E_N_count': 7, 'local_edge_count': 8,
                    'delta_U_T': 9, 'graph_d_opt_all': 10,
                    'posterior_target_trace_all': 0.1,
                    'posterior_current_trace_all': 0.2,
                    'posterior_target_ablation_delta_trace': 0.3,
                    'posterior_current_ablation_delta_trace': 0.4}
        rows = [dict(template, branch=branch, distance_m=index + 1)
                for index, branch in enumerate(dwell_control_analysis.BRANCHES)]
        contrasts = dwell_control_analysis.contrasts(rows)
        self.assertEqual({row['contrast'] for row in contrasts}, {
            'A2_sweep90-A0_baseline', 'A1_dwell-A0_baseline',
            'A2_sweep90-A1_dwell'})
        metrics = {'history_ablation_disconnects_graph': True,
                   'delta_U_H': 2.5, 'delta_U_H_per_m': 1.0,
                   'delta_U_H_per_s': 0.5}
        dwell_control_analysis.apply_connectivity_policy(metrics)
        self.assertIsNone(metrics['delta_U_H'])
        self.assertEqual(metrics['delta_U_H_status'],
                         'CONNECTIVITY_CRITICAL_UNBOUNDED')

    def test_posterior_impact_is_cost_normalized(self):
        metrics = {'distance_m': 2.0, 'duration_s': 4.0}
        rows = []
        for group in ('target_segment', 'current_pose'):
            rows.extend([
                {'variant': 'all_constraints', 'group': group,
                 'trace_mean': 1.0, 'logdet_mean': 2.0},
                {'variant': 'target_removed_impact', 'group': group,
                 'trace_mean': 0.4, 'logdet_mean': 0.8},
            ])
        dwell_control_analysis.add_posterior_summaries(metrics, rows)
        impact = next(row for row in rows
                      if row['variant'] == 'target_removed_impact')
        self.assertAlmostEqual(impact['trace_mean_per_m'], 0.2)
        self.assertAlmostEqual(impact['trace_mean_per_s'], 0.1)


if __name__ == '__main__':
    unittest.main()
