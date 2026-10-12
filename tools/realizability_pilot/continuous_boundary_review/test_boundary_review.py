#!/usr/bin/python3
"""Regression tests for the doc-78 boundary / mechanism review.

Run from the repository root::

    PYTHONPATH=catkin_ws/python /usr/bin/python3 -m unittest \
        tools.realizability_pilot.continuous_boundary_review.test_boundary_review
"""

import csv
import json
import math
import statistics
import sys
import tempfile
import unittest
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[2]
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

import evidence as ev  # noqa: E402
import review as rv  # noqa: E402
import timeline as tl  # noqa: E402

SUITE = REPO_ROOT / 'results' / 'realizability_pilot' / \
    'p1_continuous_revisit_actions_20261010'
REVIEW = REPO_ROOT / 'results' / 'realizability_pilot' / \
    'p1_continuous_boundary_review_20261012'


def synthetic_graph(extra_leaf=False, closure=False):
    """Small anchored chain used by the J_T mechanism tests."""
    nodes = []
    for state in range(7 + (1 if extra_leaf else 0)):
        nodes.append({'state_id': state, 'unique_id': state,
                      'x': 0.5 * state, 'y': 0.0, 'theta': 0.0})
    covariance = [[0.01, 0.0, 0.0], [0.0, 0.01, 0.0], [0.0, 0.0, 0.001]]
    edges = []
    index = 0
    for state in range(len(nodes) - 1):
        edges.append({'index': index, 'source_state_id': state,
                      'target_state_id': state + 1, 'covariance_3x3': covariance})
        index += 1
    if closure:
        edges.append({'index': index, 'source_state_id': 1,
                      'target_state_id': 5, 'covariance_3x3': covariance})
        index += 1
    return {'nodes': nodes, 'edges': edges}


class AcceptLogTest(unittest.TestCase):
    def test_parse_accepts_extracts_identity_and_duplicates(self):
        lines = [
            '10.0 INFO /Mapper [src:1(receiveLaserScan)] '
            'PHASE2C_KEYSCAN_ACCEPTED unique_id=7 state_id=3 sim_time=10.4',
            'some unrelated line',
            'PHASE2C_KEYSCAN_ACCEPTED unique_id=9 state_id=3 sim_time=11.9',
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'rosout.log'
            path.write_text('\n'.join(lines))
            accepts, meta = ev.parse_accepts(path)
        self.assertTrue(meta['present'])
        self.assertEqual(len(accepts), 2)
        self.assertEqual(accepts[0]['unique_id'], 7)
        self.assertAlmostEqual(accepts[1]['sim_time'], 11.9)
        self.assertEqual(meta['duplicate_state_ids'], [3])

    def test_parse_accepts_missing_file(self):
        accepts, meta = ev.parse_accepts('/nonexistent/rosout.log')
        self.assertFalse(meta['present'])
        self.assertEqual(accepts, [])


class StatisticsTest(unittest.TestCase):
    """The two estimators the report reconciles, on the recorded triplets."""

    triplets = {
        'A_L+': [0.16817976007451385, 0.06212, 0.19648],
        'A_L-': [0.2470340017026853, 0.10576, 0.14328],
        'B_L+': [-1.7763568394002505e-15, 0.11905, 0.43548],
        'B_L-': [0.01630, 0.00126, 0.11040],
    }
    five_run_cells = {
        'A_L+': [0.16818, 0.0, 0.0, 0.06212, 0.19648],
        'A_L-': [0.24703, 0.10263, 0.16858, 0.10576, 0.14328],
        'B_L+': [-0.0, -0.0, -0.0, 0.11905, 0.43548],
        'B_L-': [0.0163, 0.30709, 0.19136, 0.00126, 0.11040],
    }

    def test_new_pooled_within_config_sd(self):
        pooled = math.sqrt(statistics.mean(
            [statistics.variance(values) for values in self.triplets.values()]))
        # the recorded triplets here are the 5-decimal printed values, so this
        # test only pins the estimator to the printed precision; the exact rule
        # is verified against the built CSV in RecordedOutputTest
        self.assertAlmostEqual(pooled, 0.12701144, delta=2e-5)

    def test_doc77_estimator_reproduced(self):
        old = statistics.mean(statistics.pstdev(values)
                              for values in self.five_run_cells.values())
        self.assertAlmostEqual(old, 0.10458, delta=2e-5)

    def test_five_run_pooled_sd(self):
        pooled = math.sqrt(statistics.mean(
            [statistics.variance(values) for values in self.five_run_cells.values()]))
        self.assertAlmostEqual(pooled, 0.126363, delta=2e-5)


class MechanismMetricTest(unittest.TestCase):
    """The mechanism law behind the attribution correction."""

    targets = [1, 2, 3, 4, 5]

    def test_chain_leaf_is_jt_neutral(self):
        base = rv.an.target_score(synthetic_graph(), self.targets)['J_T']
        with_leaf = rv.an.target_score(synthetic_graph(extra_leaf=True),
                                       self.targets)['J_T']
        self.assertAlmostEqual(base, with_leaf, places=10)

    def test_closure_changes_jt(self):
        base = rv.an.target_score(synthetic_graph(), self.targets)['J_T']
        with_closure = rv.an.target_score(synthetic_graph(closure=True),
                                          self.targets)['J_T']
        self.assertGreater(with_closure, base + 1e-6)


class TimelineClassificationTest(unittest.TestCase):
    def _run(self):
        scans = [{'index': index, 'stamp': float(index) * 0.1,
                  'odom_base': [0.01 * index, 0.0, 0.0], 'map_base': None,
                  'finite_returns': 900} for index in range(300)]
        result = {'phase_scan_marks': {'history_end_scan': 100,
                                       'return_start_scan': 110},
                  'action_start_scan_index': 200, 'action_frames_target': 50}
        accepts = [
            {'state_id': 0, 'unique_id': 0, 'sim_time': 2.0},
            {'state_id': 1, 'unique_id': 1, 'sim_time': 20.5},
            {'state_id': 2, 'unique_id': 2, 'sim_time': 24.8},
            {'state_id': 3, 'unique_id': 3, 'sim_time': 29.5},
        ]
        snapshots = {}
        for name in ev.SNAPSHOTS:
            snapshots[name] = {'nodes': [], 'edges': []}
        snapshots['G_before_return']['nodes'] = [
            {'state_id': 0, 'unique_id': 0, 'x': 0.0, 'y': 0.0, 'theta': 0.0}]
        snapshots['G_arrival']['nodes'] = [
            {'state_id': 0, 'unique_id': 0, 'x': 0.0, 'y': 0.0, 'theta': 0.0},
            {'state_id': 1, 'unique_id': 1, 'x': 0.1, 'y': 0.0, 'theta': 0.0},
            {'state_id': 2, 'unique_id': 2, 'x': 0.2, 'y': 0.0, 'theta': 0.0}]
        snapshots['G_action_done']['nodes'] = list(snapshots['G_arrival']['nodes'])
        snapshots['G_final']['nodes'] = list(snapshots['G_arrival']['nodes'])
        content = {'G_before_return': 5.0, 'G_arrival': 25.0,
                   'G_action_done': 26.0, 'G_final': 26.0}
        snapshot_time = {name: value + 1.0 for name, value in content.items()}
        return {
            'scans': scans, 'result': result, 'accepts': accepts,
            'snapshots': snapshots, 'content_time': content,
            'snapshot_time': snapshot_time,
        }

    def test_classes(self):
        timeline = tl.build_state_timeline(self._run())
        classes = {item['state_id']: item['class'] for item in timeline['timeline']}
        self.assertEqual(classes[0], 'PUBLISHED_TIMELY')
        # accepted at 24.8 s, first snapshot with content >= 24.8 is G_arrival
        # (content 25.0); it appears in G_arrival -> timely
        self.assertEqual(classes[2], 'PUBLISHED_TIMELY')
        # accepted at 29.5 s, after the last content time, never published
        self.assertEqual(classes[3], 'NEVER_PUBLISHED_SUFFIX')
        # state 1 is accepted at 20.5 s but first appears in G_arrival, whose
        # content is later than that; still timely per the content rule
        self.assertEqual(classes[1], 'PUBLISHED_TIMELY')

    def test_missing_suffix_detection(self):
        timeline = tl.build_state_timeline(self._run())
        self.assertEqual(timeline['missing_ids'], [3])
        self.assertEqual(timeline['suffix_start'], 3)


@unittest.skipUnless(REVIEW.is_dir(), 'review outputs not built yet')
class RecordedOutputTest(unittest.TestCase):
    """Guards the headline numbers the report quotes."""

    def test_statistics_rows(self):
        with open(REVIEW / 'statistical_correction.csv') as handle:
            rows = {row['row_type']: row for row in csv.DictReader(handle)
                    if row['row_type'] in ('POOLED_SD_RECONCILIATION',
                                           'POOLED_SD_ALL_FIVE_RUNS',
                                           'VARIANCE_DECOMPOSITION')}
        self.assertAlmostEqual(float(rows['POOLED_SD_RECONCILIATION']['sd_ddof1']),
                               0.12701144341701123, places=9)
        self.assertAlmostEqual(float(rows['POOLED_SD_RECONCILIATION']['sd_ddof0']),
                               0.10457636463198372, places=11)

    def test_boundary_audit_counts(self):
        with open(REVIEW / 'boundary_event_audit.csv') as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 56 * 4)
        self.assertEqual(sum(1 for row in rows if row['quiescence_satisfied'] == 'False'), 0)
        self.assertEqual(sum(1 for row in rows
                             if row['keyscan_missing_check_vacuous'] == 'True'),
                         len(rows))

    def test_mechanism_law(self):
        with open(REVIEW / 'historical_factor_mechanism.csv') as handle:
            rows = list(csv.DictReader(handle))
        violations = [row for row in rows if row['gain_matches_closure_sum'] == 'False']
        self.assertEqual(violations, [])

    def test_decision_verdict(self):
        decision = json.loads((REVIEW / 'final_research_decision.json').read_text())
        self.assertEqual(decision['verdict'],
                         'D_PURE_ROTATION_SELECTION_NOT_SUPPORTED')
        self.assertFalse(decision['online_diagnostic']['run'])


if __name__ == '__main__':
    unittest.main()
