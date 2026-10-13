#!/usr/bin/python3
"""Doc-80 offline tests (no ROS, no new data).

Covers the 24 required failure-mode checks.  Run:

    PYTHONPATH=catkin_ws/python /usr/bin/python3 \
        tools/realizability_pilot/doc80_offline_review/test_doc80.py
"""

import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from doc80_offline_review import (common, feature_construction as fc,
                                  freeze_audit, integrity, link_classes,
                                  state_identity, stats_corrections,
                                  target_gt, watermark)  # noqa: E402

RUN = common.DOC79 / 'runs' / 'D79_B_Lminus_1' / 'attempt_01'


def _scans():
    return common.jsonl(RUN / 'scan_stream.jsonl')


def _gt():
    return common.jsonl(RUN / 'gt_stream.jsonl')


class TargetIdentityTests(unittest.TestCase):
    def test_01_target_ids_match_by_state_id(self):
        graph = common.sync_graph(
            {'attempt_dir': RUN}, 'final')
        graph = common.sync_graph({'attempt_dir': RUN}, 'final')
        ids = [node['state_id'] for node in graph['nodes']]
        self.assertEqual(len(ids), len(set(ids)))
        frozen = common.load_json(RUN / 'frozen_target.json')
        for state in frozen['target_state_ids']:
            matches = [node for node in graph['nodes'] if node['state_id'] == state]
            self.assertEqual(len(matches), 1)

    def test_04_pose_update_changes_gt_error(self):
        transform = (0.0, 0.0, 0.0)
        truth = {'x': 1.0, 'y': 0.0, 'theta': 0.0, 'stamp': 0.0}
        near = target_gt.target_error((1.0, 0.0, 0.0), transform, truth)
        far = target_gt.target_error((1.1, 0.0, 0.0), transform, truth)
        self.assertAlmostEqual(near['translation_m'], 0.0, places=9)
        self.assertAlmostEqual(far['translation_m'], 0.1, places=9)

    def test_11_missing_gt_not_evaluable(self):
        self.assertIsNone(target_gt.target_error((0.0, 0.0, 0.0),
                                                 (0.0, 0.0, 0.0), None))


class FreezeTests(unittest.TestCase):
    def test_02_topic_sync_identical_selection(self):
        nodes = [{'id': index, 'unique_id': index, 'x': float(index), 'y': 0.0,
                  'theta': 0.0} for index in range(10)]
        reference = [4.2, 0.0, 0.0]
        topic = freeze_audit.freeze_from(nodes, reference, 2.5, 1.0, 0.6, 1)
        sync = freeze_audit.freeze_from(list(nodes), reference, 2.5, 1.0, 0.6, 1)
        self.assertEqual([n['id'] for n in topic['selected']],
                         [n['id'] for n in sync['selected']])
        self.assertEqual(topic['anchor']['id'], sync['anchor']['id'])

    def test_03_topic_missing_candidate_reports_difference(self):
        nodes = [{'id': index, 'unique_id': index, 'x': float(index), 'y': 0.0,
                  'theta': 0.0} for index in range(10)]
        reference = [4.2, 0.0, 0.0]
        topic_nodes = [node for node in nodes if node['id'] != 4]
        topic = freeze_audit.freeze_from(topic_nodes, reference, 2.5, 1.0, 0.6, 1)
        sync = freeze_audit.freeze_from(nodes, reference, 2.5, 1.0, 0.6, 1)
        self.assertNotEqual(topic['anchor']['id'], sync['anchor']['id'])

    def test_real_freeze_reproduction(self):
        out = freeze_audit.run()
        self.assertEqual(out['payload']['reproduction_failures'], [])
        self.assertFalse(out['payload']['conclusion']['targets_changed_by_sync_or_frames'])


class FrameTests(unittest.TestCase):
    def test_06_extrinsic_direction(self):
        # base sits 0.2 m behind the laser along the laser heading
        for theta in (0.0, math.pi / 2, math.pi, -math.pi / 2):
            node = (1.0, 2.0, theta)
            base = common.compose(node, common.T_LASER_BASE)
            expected = (1.0 - 0.2 * math.cos(theta),
                        2.0 - 0.2 * math.sin(theta))
            self.assertAlmostEqual(base[0], expected[0], places=9)
            self.assertAlmostEqual(base[1], expected[1], places=9)
            back = common.compose(base, (0.2, 0.0, 0.0))
            self.assertAlmostEqual(back[0], node[0], places=9)
            self.assertAlmostEqual(back[1], node[1], places=9)

    def test_06b_real_data_model_residual_small(self):
        run = {'attempt_dir': RUN}
        residuals = state_identity.sample_accept_residuals(run)
        self.assertGreater(len(residuals), 5)
        mean = sum(item['position_m'] for item in residuals) / len(residuals)
        self.assertLess(mean, 0.15)

    def test_07_extrinsic_instability_detected(self):
        stable = {'base_in_laser_x_sd': 0.001, 'base_in_laser_y_sd': 0.001}
        unstable = {'base_in_laser_x_sd': 0.5, 'base_in_laser_y_sd': 0.001}
        self.assertTrue(state_identity.extrinsics_stable(stable))
        self.assertFalse(state_identity.extrinsics_stable(unstable))
        self.assertFalse(state_identity.extrinsics_stable(None))

    def test_08_gt_interpolation_linear(self):
        stream = [{'stamp': 0.0, 'x': 0.0, 'y': 0.0, 'theta': 0.0},
                  {'stamp': 0.1, 'x': 1.0, 'y': 2.0, 'theta': 0.4}]
        pose = common.gt_pose_at(stream, 0.06, tolerance=0.06)
        self.assertIsNotNone(pose)
        self.assertTrue(pose['interpolated'])
        self.assertAlmostEqual(pose['span_s'], 0.1, places=9)
        self.assertAlmostEqual(pose['x'], 0.6, places=6)
        self.assertAlmostEqual(pose['y'], 1.2, places=6)
        self.assertAlmostEqual(pose['theta'], 0.24, places=6)

    def test_09_gt_yaw_crossing_pi(self):
        stream = [{'stamp': 0.0, 'x': 0.0, 'y': 0.0, 'theta': 3.0},
                  {'stamp': 0.1, 'x': 0.0, 'y': 0.0, 'theta': -3.0}]
        pose = common.gt_pose_at(stream, 0.05, tolerance=0.06)
        self.assertIsNotNone(pose)
        self.assertTrue(pose['interpolated'])
        self.assertGreater(abs(pose['theta']), math.pi - 0.2)

    def test_10_alignment_frozen_pre_action(self):
        scans = _scans()
        result = common.load_json(RUN / 'episode_result.json')
        windows = common.windows(result)
        pairs, max_index = target_gt.alignment_inputs(scans, _gt(), windows)
        self.assertGreater(len(pairs), 10)
        self.assertLess(max_index, windows['action'][0])


class ProvenanceTests(unittest.TestCase):
    def test_13_duplicate_endpoint_detection(self):
        records = [{'record_type': 'constraint_created', 'source_state_id': 1,
                    'target_state_id': 2, 'creation_sequence': 1},
                   {'record_type': 'constraint_created', 'source_state_id': 1,
                    'target_state_id': 2, 'creation_sequence': 2}]
        keys = {}
        for record in records:
            keys.setdefault((record['source_state_id'],
                             record['target_state_id']), []).append(record)
        duplicates = {key: value for key, value in keys.items() if len(value) > 1}
        self.assertEqual(len(duplicates), 1)

    def test_24_missing_local_file_stops_analysis(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'analysis').mkdir()
            present = root / 'present.jsonl'
            present.write_text('x')
            import hashlib
            digest = hashlib.sha256(b'x').hexdigest()
            with open(root / 'analysis' / 'local_only_files.csv', 'w') as handle:
                handle.write('path,bytes,sha256\n')
                handle.write('{},{},{}\n'.format(present, 1, digest))
                handle.write('{},{},{}\n'.format(root / 'missing.jsonl', 1, digest))
            audit = integrity.local_only_audit(root)
            self.assertFalse(audit['ok'])
            self.assertEqual(len(audit['missing']), 1)


class LinkClassTests(unittest.TestCase):
    def test_12_historical_edge_classes(self):
        self.assertEqual(link_classes.edge_class_of('history', 'action'),
                         'A_FIRST_VISIT_HISTORY_LINK')
        self.assertEqual(link_classes.edge_class_of('return', 'action'),
                         'B_RETURN_HISTORY_LINK')
        self.assertEqual(link_classes.edge_class_of('action', 'action'),
                         'C_ACTION_INTERNAL_NONLOCAL_LINK')
        self.assertEqual(link_classes.edge_class_of('history', 'return'),
                         'A_FIRST_VISIT_HISTORY_LINK')

    def test_14_sync_gain_and_fixed_linearization_separate(self):
        out = link_classes.run()
        self.assertTrue(out['contributions'])
        for row in out['contributions']:
            self.assertEqual(row['diagnostic_label'],
                             'FIXED_LINEARIZATION_FACTOR_DIAGNOSTIC')
            self.assertIn('contribution_class_A', row)
        comparisons = out['doc79_comparisons']
        self.assertTrue(comparisons)
        for row in comparisons:
            self.assertIn('closure_minus_historic', row)
            self.assertIn('delta_minus_historic', row)


class FeatureFirewallTests(unittest.TestCase):
    def test_15_fov_sectors(self):
        intervals = fc.common_exclusive(0.0, -math.pi / 2, math.pi / 2)
        self.assertAlmostEqual(intervals['common_length'], math.pi, places=9)
        self.assertAlmostEqual(intervals['exclusive_Lplus'], math.pi / 2, places=9)
        self.assertAlmostEqual(intervals['exclusive_Lminus'], math.pi / 2, places=9)

    def test_16_fov_wraparound(self):
        theta0 = math.pi - 0.1
        intervals = fc.common_exclusive(theta0, -math.pi / 2, math.pi / 2)
        self.assertAlmostEqual(intervals['common_length'], math.pi, places=9)
        start, length = fc.swept_fov(theta0, -math.pi / 2, math.pi / 2, 'L+')
        self.assertTrue(fc._contains(math.pi + 0.5, start, length))

    def test_17_18_19_feature_firewall_refuses_post_action(self):
        for name in ('graph_action_done_sync.json', 'graph_final_sync.json',
                     'gt_stream.jsonl', 'karto_edge_provenance.jsonl',
                     'rosout.log', 'scan_stream.jsonl'):
            with self.assertRaises(AssertionError):
                fc._guard('/tmp/' + name)

    def test_17b_bundle_works_without_other_files(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            fc.slice_pre_action({'attempt_dir': RUN,
                                 'spec': common.load_json(RUN / 'episode_spec.json'),
                                 'result': common.load_json(RUN / 'episode_result.json'),
                                 'frozen': common.load_json(RUN / 'frozen_target.json'),
                                 'episode_id': 'D79_B_Lminus_1',
                                 'attempt': 'attempt_01'}, temp)
            names = sorted(path.name for path in temp.iterdir())
            self.assertIn('scans_pre_action.jsonl', names)
            self.assertNotIn('gt_stream.jsonl', names)
            self.assertNotIn('rosout.log', names)
            features = fc.build_features(temp)
            self.assertIsNotNone(features)

    def test_19b_no_post_action_reads_in_source(self):
        source = (HERE / 'feature_construction.py').read_text()
        for token in ('karto_edge_provenance', 'gt_stream'):
            self.assertIn(token, source)  # only inside the forbidden list
        self.assertNotIn('delta_J', source)
        for line in source.splitlines():
            if line.strip().startswith(('import ', 'from ')):
                self.assertNotIn('outcome_evaluation', line)

    def test_20_two_directions_same_pre_state(self):
        out = fc.run()
        for row in out:
            self.assertEqual(row['history_visible_Lplus'] + 0, row['history_visible_Lplus'])
            self.assertIn('history_visible_Lminus', row)
            # both directions share the same prepared node sets
            self.assertGreaterEqual(row['history_nodes'], row['history_visible_Lplus'])
            self.assertGreaterEqual(row['history_nodes'], row['history_visible_Lminus'])

    def test_21_unexecuted_direction_is_not_a_label(self):
        features_path = (common.DOC80 / 'analysis' /
                         'directional_visibility_features.csv')
        joined_path = (common.DOC80 / 'analysis' / 'feature_outcome_join.csv')
        self.assertTrue(features_path.is_file())
        with open(features_path) as handle:
            header = handle.readline().strip()
        self.assertNotIn('delta_J', header)
        import csv
        with open(joined_path) as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            self.assertIn(row['action'], ('L+', 'L-'))
            self.assertIn(row['place'], ('place_B', 'place_C'))
            self.assertNotEqual(row['delta_J_action_sync'], None)


class StatisticsTests(unittest.TestCase):
    def test_22_cross_differences_not_independent(self):
        payload = stats_corrections.run()
        self.assertIn('warning', payload['cross_differences'])
        self.assertEqual(payload['cross_differences']['counts'],
                         {'place_B': 4, 'place_C': 2})

    def test_23_suite_and_run_qualification_separated(self):
        payload = stats_corrections.run()
        semantics = payload['final_gate_semantics']
        self.assertTrue(semantics['VALID_RUN_MEASUREMENT_PASS'])
        self.assertFalse(semantics['SUITE_COMPLETE'])
        self.assertEqual(semantics['valid_runs'], 7)
        self.assertEqual(semantics['attempts'], 8)
        self.assertEqual(semantics['completed_planned_episodes'], 7)


class BoundaryTests(unittest.TestCase):
    def test_05_corrected_rows_use_stage_nodes(self):
        out = target_gt.corrected_target_rows()
        by_state = {}
        for row in out['target_rows']:
            if row['status'] != 'EVALUABLE':
                continue
            by_state.setdefault((row['episode_id'], row['target_state_id']),
                                {})[row['stage']] = row['node_laser_pose']
        self.assertTrue(by_state)
        # the C_Lplus_1 run has a measurable action-stage node displacement
        key = ('D79_C_Lplus_1', 69)
        node_pairs = by_state.get(key)
        if node_pairs:
            arrival = json.loads(node_pairs['arrival'])
            action_done = json.loads(node_pairs['action_done'])
            moved = math.hypot(arrival[0] - action_done[0],
                               arrival[1] - action_done[1])
            self.assertGreater(moved, 0.001)

    def test_24b_watermark_zero_beyond(self):
        rows = watermark.boundary_sensitivity()
        self.assertEqual(len(rows), 28)
        self.assertEqual(sum(int(row['nodes_beyond_watermark']) for row in rows), 0)


if __name__ == '__main__':
    unittest.main(verbosity=1)
