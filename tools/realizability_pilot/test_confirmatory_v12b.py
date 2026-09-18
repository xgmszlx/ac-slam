#!/usr/bin/python3

import inspect
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import branch_replay
import common_prefix_replay
import confirmatory_v12_protocol as v12_protocol
import confirmatory_v12b_analysis as analysis
import confirmatory_v12b_protocol as protocol
import confirmatory_v12b_preflight as preflight
from same_input_replay import write_launch_file


class ConfirmatoryV12bTechnicalTest(unittest.TestCase):
    def test_relative_sweep_offsets_survive_pi_wrap(self):
        expected = [math.pi / 2.0, -math.pi / 6.0, 0.0, math.pi / 6.0]
        for theta0 in (0.0, math.pi - 1e-4, -math.pi + 1e-4):
            targets = preflight.relative_sweep_yaws(theta0)
            recovered = [preflight.wrap_angle(value - theta0)
                         for value in targets]
            for actual, wanted in zip(recovered, expected):
                self.assertAlmostEqual(
                    preflight.wrap_angle(actual - wanted), 0.0, places=12)

    def test_shortest_angle_across_pi_boundary(self):
        self.assertAlmostEqual(preflight.wrap_angle(
            (-math.pi + 0.01) - (math.pi - 0.01)), 0.02, places=12)
        self.assertAlmostEqual(preflight.wrap_angle(
            (math.pi - 0.01) - (-math.pi + 0.01)), -0.02, places=12)

    def test_canonical_and_branch_replay_default_to_zero_io(self):
        self.assertEqual(common_prefix_replay.DEFAULT_REPLAY_FLUSH_PERIOD_S, 0.0)
        self.assertEqual(branch_replay.DEFAULT_REPLAY_FLUSH_PERIOD_S, 0.0)
        self.assertEqual(inspect.signature(common_prefix_replay.replay)
                         .parameters['flush_period_s'].default, 0.0)
        self.assertEqual(inspect.signature(branch_replay.replay_branch)
                         .parameters['flush_period_s'].default, 0.0)

    def test_launch_serializes_zero_flush_period(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'mapper.launch'
            write_launch_file(path, {}, 'on', Path(directory) / 'graph.json',
                              Path(directory) / 'prov.jsonl', 0.0)
            self.assertIn('instrumentation_flush_period_s" value="0.0"',
                          path.read_text())

    def test_zero_flush_keeps_pose_graph_dump_polling_live(self):
        source = (Path(__file__).resolve().parents[2] /
                  'dependencies/navigation_2d/nav2d_karto/src/MultiMapper.cpp')
        text = source.read_text()
        self.assertIn(
            'mInstrumentationFlushPeriod > 0.0 || !mPoseGraphDumpPath.empty()',
            text)
        self.assertIn('if(mInstrumentationFlushPeriod > 0.0)\n\t\t{\n'
                      '\t\t\tmMapper->FlushEdgeProvenance();', text)

    def test_budget_gate_uses_only_physical_variables(self):
        rows = [
            {'actual_distance_m': 10.00, 'actual_duration_s': 50.0,
             'raw_scan_count': 500},
            {'actual_distance_m': 10.04, 'actual_duration_s': 50.8,
             'raw_scan_count': 506},
            {'actual_distance_m': 10.02, 'actual_duration_s': 50.4,
             'raw_scan_count': 503},
        ]
        self.assertTrue(preflight.budget_gate(rows)['passed'])

    def test_v12b_seeds_are_fresh_and_disjoint(self):
        old = set()
        fresh = set()
        for target in ('target_A', 'target_B'):
            old.update(v12_protocol.PRIMARY_SEEDS[target])
            old.update(v12_protocol.RESERVE_SEEDS[target])
            fresh.update(protocol.PRIMARY_SEEDS[target])
            fresh.update(protocol.RESERVE_SEEDS[target])
            self.assertEqual(len(protocol.PRIMARY_SEEDS[target]), 4)
            self.assertEqual(len(protocol.RESERVE_SEEDS[target]), 2)
        self.assertTrue(old.isdisjoint(fresh))
        self.assertEqual(len(fresh), 12)

    def test_preregistration_refuses_missing_phase_r_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                protocol.preregistration_payload(Path(directory))

    def test_analysis_refuses_without_collection_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, 'COLLECTION_LOCKED'):
                analysis.analysis_preflight(Path(directory))

    @staticmethod
    def _contrast_rows(values_a, values_b):
        rows = []
        for target, values in (('target_A', values_a),
                               ('target_B', values_b)):
            for index, value in enumerate(values, 1):
                block = '{}_H{}'.format(target, index)
                rows.extend((
                    {'block_id': block, 'target': target,
                     'arm': 'A3_MIN_TRIGGER', 'J_T': 1.0},
                    {'block_id': block, 'target': target,
                     'arm': 'A2_SWEEP90', 'J_T': 1.0 + value},
                ))
        return rows

    def test_support_rule_uses_counts_magnitude_and_stratified_ci(self):
        rows = self._contrast_rows(
            [0.20, 0.18, 0.16, -0.01],
            [0.22, 0.17, 0.15, -0.01])
        _, result = analysis.contrast_summary(
            rows, 'A2_SWEEP90', 'A3_MIN_TRIGGER', 'D_view',
            bootstrap_repetitions=2000)
        self.assertEqual(result['positive_blocks'], 6)
        self.assertEqual(result['target_positive'],
                         {'target_A': 3, 'target_B': 3})
        self.assertGreater(
            result['target_stratified_block_bootstrap_mean_95pct_CI'][0], 0)
        self.assertTrue(result['supported_by_preregistered_rule'])

    def test_target_heterogeneity_gate(self):
        rows = self._contrast_rows(
            [0.20, 0.18, 0.16, 0.12],
            [0.05, -0.04, -0.06, -0.08])
        _, result = analysis.contrast_summary(
            rows, 'A2_SWEEP90', 'A3_MIN_TRIGGER', 'D_view',
            bootstrap_repetitions=200)
        self.assertTrue(result['target_dependent_heterogeneity'])
        self.assertFalse(result['supported_by_preregistered_rule'])


if __name__ == '__main__':
    unittest.main()
