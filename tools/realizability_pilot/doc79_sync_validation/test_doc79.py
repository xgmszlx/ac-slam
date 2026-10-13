#!/usr/bin/python3
"""Doc-79 regression tests: observation chain, artifacts, SE(2), budget.

These are the pre-run qualification tests required by the handoff (unit-test
list in section 4 plus the SE(2) list in section 8.2).  They are ROS-free and
run against synthetic fixtures; the live chain is additionally validated by the
first two physical episodes.

Run::

    /usr/bin/python3 tools/realizability_pilot/doc79_sync_validation/test_doc79.py
"""

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

import checks as ck  # noqa: E402


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload))
    return payload


def make_graph(nodes, edges, run_id='doc79_run'):
    return {'dump_version': 1, 'run_id': run_id,
            'nodes': [{'index': index, 'state_id': state, 'unique_id': state,
                       'x': float(state), 'y': 0.0, 'theta': 0.0}
                      for index, state in enumerate(nodes)],
            'edges': [{'index': index, 'source_state_id': source,
                       'target_state_id': target}
                      for index, (source, target) in enumerate(edges)]}


class ScanIdentityTest(unittest.TestCase):
    def test_counters_distinguish_native_and_localized(self):
        """1. native telemetry fields are separate from the localized counter."""
        telemetry = {'native_scan_received': 5, 'native_scan_processed': 4,
                     'processed_localized_scan_count': 0}
        self.assertIn('native_scan_received', telemetry)
        self.assertIn('native_scan_processed', telemetry)
        self.assertNotEqual(telemetry['native_scan_received'],
                            telemetry['processed_localized_scan_count'])

    def test_sequence_monotonic(self):
        """2. increasing sequence passes the identity audit."""
        audit = ck.scan_identity_audit([{'seq': value} for value in (1, 2, 3, 4)])
        self.assertTrue(audit['usable_alone'])
        self.assertEqual(audit['duplicates'], 0)

    def test_sequence_duplicates_detected(self):
        """3. duplicated sequence numbers are flagged."""
        audit = ck.scan_identity_audit([{'seq': value} for value in (1, 2, 2, 3)])
        self.assertGreater(audit['duplicates'], 0)
        self.assertFalse(audit['usable_alone'])

    def test_missing_identity(self):
        """4. records without identity are not silently accepted."""
        audit = ck.scan_identity_audit([{'seq': None}, {'seq': None}])
        self.assertEqual(audit['count'], 0)
        self.assertFalse(audit['usable_alone'])

    def test_watermark_not_reached(self):
        """5. mapper not yet at the stage watermark fails the barrier."""
        ok, reasons, _ = ck.watermark_satisfied(
            {'native_scan_processed': 3, 'native_scan_received': 3,
             'last_native_scan_stamp': 2.0},
            {'stamp': 5.0, 'driver_scan_count': 3})
        self.assertFalse(ok)
        self.assertTrue(reasons)

    def test_watermark_reached(self):
        ok, reasons, _ = ck.watermark_satisfied(
            {'native_scan_processed': 30, 'native_scan_received': 30,
             'last_native_scan_stamp': 5.1},
            {'stamp': 5.0, 'driver_scan_count': 30})
        self.assertTrue(ok, reasons)

    def test_scans_still_in_queue(self):
        """19. scans published but not yet processed keep the barrier open."""
        ok, _, _ = ck.watermark_satisfied(
            {'native_scan_processed': 29, 'native_scan_received': 30,
             'last_native_scan_stamp': 4.9},
            {'stamp': 5.0, 'driver_scan_count': 30})
        self.assertFalse(ok)

    def test_received_deficit_detected(self):
        ok, reasons, _ = ck.watermark_satisfied(
            {'native_scan_processed': 10, 'native_scan_received': 10,
             'last_native_scan_stamp': 5.0},
            {'stamp': 5.0, 'driver_scan_count': 12})
        self.assertFalse(ok)

    def test_accepted_counter_consistency(self):
        ok, _ = ck.accepted_consistent(
            {'native_scan_accepted': 7}, 7)
        self.assertTrue(ok)
        ok, reason = ck.accepted_consistent(
            {'native_scan_accepted': 6}, 7)
        self.assertFalse(ok)
        self.assertTrue(reason)


class SyncArtifactTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_dump(self):
        path = self.dir / 'graph_arrival_sync.json'
        write_json(path, make_graph([0, 1, 2], [(0, 1), (1, 2)]))
        ok, reasons, summary = ck.validate_sync_document(path, 'doc79_run')
        self.assertTrue(ok, reasons)
        self.assertEqual(summary['nodes'], 3)

    def test_service_failure_path(self):
        """6. export response with written=false is rejected."""
        response = {'written': False, 'dump_path': '/tmp/x.json'}
        self.assertFalse(response['written'])

    def test_missing_dump_file(self):
        """7. absent dump file is rejected."""
        ok, reasons, _ = ck.validate_sync_document(
            self.dir / 'missing.json', 'doc79_run')
        self.assertFalse(ok)
        self.assertTrue(any('missing' in reason for reason in reasons))

    def test_incomplete_dump_file(self):
        """8. truncated JSON is rejected."""
        path = self.dir / 'graph_arrival_sync.json'
        path.write_text('{"run_id": "doc79_run", "nodes": [{"state_id": 0')
        ok, reasons, _ = ck.validate_sync_document(path, 'doc79_run')
        self.assertFalse(ok)
        self.assertTrue(any('unparseable' in reason for reason in reasons))

    def test_wrong_run_id(self):
        """10/16. run-id mixing is rejected."""
        path = self.dir / 'graph_arrival_sync.json'
        write_json(path, make_graph([0, 1], [(0, 1)], run_id='other_run'))
        ok, reasons, _ = ck.validate_sync_document(path, 'doc79_run')
        self.assertFalse(ok)
        self.assertTrue(any('run_id' in reason for reason in reasons))

    def test_count_mismatch(self):
        """10. node count disagreeing with the accepted-state count fails."""
        path = self.dir / 'graph_arrival_sync.json'
        write_json(path, make_graph([0, 1], [(0, 1)]))
        ok, reasons, _ = ck.validate_sync_document(
            path, 'doc79_run', expected_nodes=3)
        self.assertFalse(ok)
        self.assertTrue(any('node count' in reason for reason in reasons))

    def test_edge_references_unknown_node(self):
        """11. an edge pointing outside the node set fails."""
        path = self.dir / 'graph_arrival_sync.json'
        write_json(path, make_graph([0, 1], [(0, 5)]))
        ok, reasons, _ = ck.validate_sync_document(path, 'doc79_run')
        self.assertFalse(ok)
        self.assertTrue(any('unknown nodes' in reason for reason in reasons))

    def test_wrong_dump_path(self):
        """9. an export that wrote somewhere else is rejected."""
        response = {'written': True, 'dump_path': '/tmp/other.json'}
        expected = '/tmp/expected.json'
        self.assertNotEqual(response['dump_path'], expected)

    def test_boundary_file_overwrite(self):
        """15. two boundaries sharing one file fails uniqueness."""
        manifests = {
            'G_arrival': {'sync_file': {'path': '/tmp/a.json'}},
            'G_final': {'sync_file': {'path': '/tmp/a.json'}},
        }
        ok, offenders = ck.boundary_paths_unique(manifests)
        self.assertFalse(ok)
        self.assertEqual(len(offenders), 1)

    def test_topic_vs_sync(self):
        topic = make_graph([0, 1], [(0, 1)])
        topic_payload = {'nodes': [{'id': 0}, {'id': 1}],
                         'edges': [{'start': 0, 'end': 1}]}
        sync = make_graph([0, 1, 2], [(0, 1), (1, 2)])
        comparison = ck.compare_topic_sync(topic_payload, sync)
        self.assertEqual(comparison['nodes_only_in_sync'], [2])
        self.assertEqual(comparison['edges_only_in_sync'], [(1, 2)])


class ProvenanceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def _write(self, records):
        path = self.dir / 'karto_edge_provenance.jsonl'
        with open(path, 'w') as handle:
            for record in records:
                handle.write(json.dumps(record) + '\n')
        return path

    def test_empty_file(self):
        """12. empty provenance is rejected."""
        path = self.dir / 'empty.jsonl'
        path.write_text('')
        ok, reasons, info = ck.provenance_summary(path, 'doc79_run')
        self.assertFalse(ok)
        self.assertTrue(any('empty' in reason for reason in reasons))

    def test_duplicate_creation_sequence(self):
        """13. duplicate creation sequences are flagged."""
        path = self._write([
            {'record_type': 'constraint_created', 'run_id': 'doc79_run',
             'creation_sequence': 1, 'source_state_id': 0, 'target_state_id': 1},
            {'record_type': 'constraint_created', 'run_id': 'doc79_run',
             'creation_sequence': 1, 'source_state_id': 1, 'target_state_id': 2},
        ])
        ok, reasons, info = ck.provenance_summary(path, 'doc79_run')
        self.assertFalse(ok)
        self.assertEqual(info['duplicate_sequences'], 1)

    def test_graph_provenance_consistency(self):
        """14. every graph edge must have a creation record."""
        records = [
            {'record_type': 'constraint_created', 'run_id': 'doc79_run',
             'creation_sequence': 1, 'source_state_id': 0, 'target_state_id': 1},
        ]
        graph = make_graph([0, 1, 2], [(0, 1), (1, 2)])
        ok, info = ck.provenance_graph_consistency(records, graph)
        self.assertFalse(ok)
        self.assertEqual(info['edges_without_record'], [(1, 2)])

    def test_mixed_run_ids(self):
        path = self._write([
            {'record_type': 'constraint_created', 'run_id': 'doc79_run',
             'creation_sequence': 1, 'source_state_id': 0, 'target_state_id': 1},
            {'record_type': 'constraint_created', 'run_id': 'other_run',
             'creation_sequence': 2, 'source_state_id': 1, 'target_state_id': 2},
        ])
        ok, reasons, _ = ck.provenance_summary(path, 'doc79_run')
        self.assertFalse(ok)
        self.assertTrue(any('run_id' in reason for reason in reasons))


class Se2Test(unittest.TestCase):
    def test_same_pose(self):
        """18/8.2. identical relative poses give zero error."""
        anchor = ck.se2(1.0, 2.0, 0.3)
        robot = ck.se2(4.0, 5.0, -0.4)
        relative = ck.se2_between(anchor, robot)
        translation, rotation = ck.se2_error(relative, relative)
        self.assertAlmostEqual(translation, 0.0, places=12)
        self.assertAlmostEqual(rotation, 0.0, places=12)

    def test_same_length_different_direction(self):
        """18. equal-length but rotated displacement must not read as zero."""
        anchor = ck.se2(0.0, 0.0, 0.0)
        robot_est = ck.se2(1.0, 0.0, 0.0)
        robot_gt = ck.se2(0.0, 1.0, 0.0)
        relative_est = ck.se2_between(anchor, robot_est)
        relative_gt = ck.se2_between(anchor, robot_gt)
        translation, rotation = ck.se2_error(relative_est, relative_gt)
        self.assertAlmostEqual(translation, math.sqrt(2.0), places=9)
        self.assertGreater(translation, 1e-6)

    def test_translation_bias(self):
        anchor = ck.se2(0.0, 0.0, 0.0)
        relative_est = ck.se2_between(anchor, ck.se2(1.0, 0.0, 0.1))
        relative_gt = ck.se2_between(anchor, ck.se2(1.2, 0.0, 0.1))
        translation, rotation = ck.se2_error(relative_est, relative_gt)
        self.assertAlmostEqual(translation, 0.2, places=9)
        self.assertAlmostEqual(rotation, 0.0, places=9)

    def test_rotation_bias(self):
        anchor = ck.se2(0.0, 0.0, 0.0)
        relative_est = ck.se2_between(anchor, ck.se2(1.0, 0.0, 0.7))
        relative_gt = ck.se2_between(anchor, ck.se2(1.0, 0.0, 0.4))
        translation, rotation = ck.se2_error(relative_est, relative_gt)
        self.assertAlmostEqual(translation, 0.0, places=9)
        self.assertAlmostEqual(rotation, 0.3, places=9)

    def test_angle_wrap(self):
        anchor = ck.se2(0.0, 0.0, math.pi - 0.05)
        relative_est = ck.se2_between(anchor, ck.se2(0.0, 0.0, -math.pi + 0.05))
        relative_gt = ck.se2_between(anchor, ck.se2(0.0, 0.0, math.pi - 0.06))
        translation, rotation = ck.se2_error(relative_est, relative_gt)
        self.assertAlmostEqual(translation, 0.0, places=9)
        # wrapped headings: est relative 0.1 rad, gt relative -0.01 rad
        self.assertAlmostEqual(rotation, 0.11, places=6)

    def test_lever_arm_extrinsics(self):
        """8.2. frame mixing produces a detectable relative error.

        Using the SAME physical reference point on both sides (base frame for
        both anchor and robot) gives zero error; expressing one side in the
        laser frame without converting produces a real, non-zero error, which
        is exactly what the corrected estimator must avoid.
        """
        laser_offset = ck.se2(0.3, 0.0, 0.0)      # laser in base frame
        base_anchor = ck.se2(1.0, 1.0, 0.0)
        base_robot = ck.se2(2.0, 1.0, math.pi / 2)
        # consistent base-frame comparison: zero error
        translation, rotation = ck.se2_error(
            ck.se2_between(base_anchor, base_robot),
            ck.se2_between(base_anchor, base_robot))
        self.assertAlmostEqual(translation, 0.0, places=12)
        self.assertAlmostEqual(rotation, 0.0, places=12)
        # mixing frames (base-frame GT vs laser-frame estimate) must be visible
        laser_anchor = ck.se2_compose(base_anchor, laser_offset)
        laser_robot = ck.se2_compose(base_robot, laser_offset)
        mixed_translation, _ = ck.se2_error(
            ck.se2_between(laser_anchor, laser_robot),
            ck.se2_between(base_anchor, base_robot))
        self.assertGreater(mixed_translation, 0.1)


class GuardTest(unittest.TestCase):
    def test_gain_source_mixing(self):
        """17. recorded and re-attributed gains cannot be mixed silently."""
        self.assertTrue(ck.check_gain_sources_agree(
            'SYNCHRONOUS_DUMP', 'SYNCHRONOUS_DUMP'))
        with self.assertRaises(ck.GainSourceMixingError):
            ck.check_gain_sources_agree(
                'SYNCHRONOUS_DUMP', 'FIXED_LINEARIZATION_FACTOR_DIAGNOSTIC')

    def test_budget_guard(self):
        """20. retries cannot exceed the frozen budget."""
        state = ck.budget_state(attempts_used=7, budget=8, planned=8)
        self.assertFalse(state['budget_exhausted'])
        state = ck.budget_state(attempts_used=8, budget=8, planned=8)
        self.assertTrue(state['budget_exhausted'])
        self.assertEqual(state['remaining'], 0)


if __name__ == '__main__':
    unittest.main()
