#!/usr/bin/python3
"""Unit tests for the direction-decision experiment tooling.

ROS-free except for the driver tests, which skip themselves when rospy is not
importable.
"""

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

import edge_analytics  # noqa: E402
import n0_analysis  # noqa: E402
import n0_certification  # noqa: E402
import n0_extension_decision  # noqa: E402
import replay_compare  # noqa: E402
import n1_analysis  # noqa: E402
import preprobe_signature  # noqa: E402
import se2_information  # noqa: E402
import target_screening  # noqa: E402
from direction_gate import evaluate as gate_evaluate  # noqa: E402
from protocol import TARGETS, episode_specs  # noqa: E402

try:  # pragma: no cover - environment dependent
    import pilot_driver
    DRIVER_AVAILABLE = True
except Exception:  # pragma: no cover
    DRIVER_AVAILABLE = False

V7_SUITE = Path('/home/wcqw/ac-slam/results/realizability_pilot/'
                'p1_preflight_v7_20260916/episodes')


def synthetic_before(positions, edges):
    """Build a minimal before-probe snapshot in the recorder's format."""
    nodes = []
    for node_id, (x, y, theta) in enumerate(positions):
        nodes.append({'id': node_id, 'unique_id': 1000 + node_id,
                      'x': x, 'y': y, 'theta': theta})
    edge_list = []
    for index, (start, end) in enumerate(edges):
        edge_list.append({'index': index, 'start': start, 'end': end,
                          'covariance_upper_triangle': '0.01 0 0 0.01 0 0.002'})
    return {
        'phase': 'before_probe',
        'sim_time': 12.5,
        'nodes': nodes,
        'full_pose_nodes': nodes,
        'edges': edge_list,
        'full_pose_edges': edge_list,
    }


def synthetic_frozen(target_ids, route_start=0):
    return {
        'target_id': 'map3_grid_anchor_01',
        'target_reference': [0.0, 0.0, 0.0],
        'anchor_scan': {'id': target_ids[0], 'unique_id': 1000 + target_ids[0],
                        'x': 0.0, 'y': 0.0, 'theta': 0.0},
        'historical_scan_ids': list(target_ids),
        'historical_unique_ids': [1000 + value for value in target_ids],
        'route_start_node_count': route_start,
        'target_identity_gate': {'passed': True, 'checks': {}},
    }


class SignatureTest(unittest.TestCase):
    def setUp(self):
        self.positions = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)]
        self.edges = [(0, 1), (1, 2)]
        self.before = synthetic_before(self.positions, self.edges)
        self.frozen = synthetic_frozen([0, 1])
        self.spec = {'episode_id': '0001_test', 'condition_id': 'n0_instr_off',
                     'target_id': 'map3_grid_anchor_01', 'tsp_seed': 41001}

    def test_signature_is_deterministic(self):
        first = preprobe_signature.build_signature(
            self.before, self.frozen, self.spec, 'run')
        second = preprobe_signature.build_signature(
            self.before, self.frozen, self.spec, 'run')
        self.assertEqual(json.dumps(first, sort_keys=True),
                         json.dumps(second, sort_keys=True))
        self.assertEqual(first['node_count'], 3)
        self.assertEqual(first['edge_count'], 2)
        self.assertEqual(first['target_segment_size'], 2)
        self.assertTrue(first['before_probe'])

    def test_gate_accepts_identical_signatures(self):
        signature = preprobe_signature.build_signature(
            self.before, self.frozen, self.spec, 'run')
        deviations = n0_analysis.route_anchor_deviations(
            edge_analytics.load_nodes(self.before),
            edge_analytics.load_nodes(self.before), [[0.0, 0.0, 0.0]])
        gate = n0_analysis.compare_signatures(signature, signature, deviations)
        self.assertTrue(gate['passed'], gate['failed_checks'])

    def test_gate_rejects_target_segment_mismatch(self):
        signature = preprobe_signature.build_signature(
            self.before, self.frozen, self.spec, 'run')
        other = dict(signature)
        other['target_segment_size'] = signature['target_segment_size'] + 3
        gate = n0_analysis.compare_signatures(signature, other)
        self.assertFalse(gate['passed'])
        self.assertIn('target_segment_size_equal', gate['failed_checks'])

    def test_gate_rejects_graph_geometry_drift(self):
        signature = preprobe_signature.build_signature(
            self.before, self.frozen, self.spec, 'run')
        drifted = synthetic_before(
            [(0.0, 0.0, 0.0), (1.0, 0.5, 0.0), (2.0, 0.5, 0.0)], self.edges)
        deviations = n0_analysis.route_anchor_deviations(
            edge_analytics.load_nodes(self.before),
            edge_analytics.load_nodes(drifted), [[1.0, 0.0, 0.0]])
        gate = n0_analysis.compare_signatures(signature, signature, deviations)
        self.assertFalse(gate['passed'])
        self.assertIn('route_node_positions_comparable', gate['failed_checks'])

    def test_gate_rejects_edge_count_drift(self):
        signature = preprobe_signature.build_signature(
            self.before, self.frozen, self.spec, 'run')
        wider = synthetic_before(self.positions, self.edges + [(0, 2), (0, 2)])
        other = preprobe_signature.build_signature(
            wider, self.frozen, self.spec, 'run')
        gate = n0_analysis.compare_signatures(signature, other)
        self.assertFalse(gate['passed'])
        self.assertIn('edge_count_within_tolerance', gate['failed_checks'])


class MatchedPairTest(unittest.TestCase):
    def test_paired_difference_and_sign_consistency(self):
        values = {'off': {1: 3.0, 2: 2.0, 3: 4.0},
                  'on': {1: 5.0, 2: 4.0, 3: 6.0}}
        statistics = n0_analysis.paired_difference_statistics(values, 'off', 'on')
        self.assertEqual(statistics['pair_count'], 3)
        self.assertTrue(statistics['all_same_sign_nonzero'])
        self.assertAlmostEqual(statistics['mean_difference'], 2.0)

    def test_verdict_uses_measured_repeatability(self):
        stable = {'outcome': {'n0_instr_off': {1: 3.0, 2: 3.1, 3: 2.9},
                              'n0_prov_on': {1: 3.05, 2: 3.0, 3: 2.95}}}
        verdict = n0_analysis.nonperturbation_verdict(stable)
        self.assertEqual(verdict['outcome'], 'OUTCOME_MEASUREMENT_STABLE')
        shifted = {'outcome': {'n0_instr_off': {1: 3.0, 2: 3.1, 3: 2.9},
                               'n0_prov_on': {1: 9.0, 2: 9.1, 3: 8.9}}}
        verdict = n0_analysis.nonperturbation_verdict(shifted)
        self.assertEqual(verdict['outcome'],
                         'POSSIBLE_INSTRUMENTATION_PERTURBATION')

    def test_verdict_ignores_inconsistent_direction(self):
        noisy = {'outcome': {'n0_instr_off': {1: 3.0, 2: 3.0, 3: 3.0},
                             'n0_prov_on': {1: 9.0, 2: 0.5, 3: 9.0}}}
        verdict = n0_analysis.nonperturbation_verdict(noisy)
        self.assertEqual(verdict['outcome'], 'OUTCOME_MEASUREMENT_STABLE')

    def test_repeatability_scale_ignores_none(self):
        scale = n0_analysis.repeatability_scale([1.0, None, 3.0])
        self.assertEqual(scale['count'], 2)
        self.assertIsNotNone(scale['mad'])


class Se2InformationTest(unittest.TestCase):
    def edge(self, start, end, poses, covariance=(0.01, 0.0, 0.0, 0.01, 0.0, 0.002)):
        return {
            'index': 0, 'start': start, 'end': end,
            'source_pose': list(poses[start]), 'target_pose': list(poses[end]),
            'covariance_upper_triangle': ' '.join(str(value) for value in covariance),
        }

    def test_information_matrix_is_symmetric_psd_with_gauge_nullity(self):
        poses = {0: (0.0, 0.0, 0.0), 1: (1.0, 0.0, 0.1)}
        edges = [self.edge(0, 1, poses)]
        information, contributors, rejected = se2_information.build_information(
            [0, 1], edges)
        self.assertEqual(contributors, 1)
        self.assertEqual(rejected, [])
        self.assertTrue(all(abs(information[i, j] - information[j, i]) < 1e-12
                            for i in range(6) for j in range(6)))
        eigenvalues = [float(value) for value in
                       __import__('numpy').linalg.eigvalsh(information)]
        self.assertLess(min(eigenvalues), 1e-9)
        marginal, nullity, _values = se2_information.pseudoinverse_information(
            information)
        self.assertEqual(nullity, 3)
        self.assertTrue(all(math.isfinite(float(value))
                            for row in marginal for value in row))

    def test_extra_constraint_reduces_uncertainty_and_raises_d_opt(self):
        poses = {0: (0.0, 0.0, 0.0), 1: (1.0, 0.0, 0.0), 2: (2.0, 0.0, 0.0)}
        chain = [self.edge(0, 1, poses), self.edge(1, 2, poses)]
        loop = chain + [self.edge(0, 2, poses)]
        chain_info, _c, _r = se2_information.build_information([0, 1, 2], chain)
        loop_info, _c, _r = se2_information.build_information([0, 1, 2], loop)
        chain_marginal, _, _ = se2_information.pseudoinverse_information(chain_info)
        loop_marginal, _, _ = se2_information.pseudoinverse_information(loop_info)
        self.assertLess(
            se2_information.block_metrics(loop_marginal, 2)['trace'],
            se2_information.block_metrics(chain_marginal, 2)['trace'])
        self.assertGreater(se2_information.d_opt(loop_info),
                           se2_information.d_opt(chain_info))

    def test_excluded_pairs_remove_exactly_that_constraint(self):
        poses = {0: (0.0, 0.0, 0.0), 1: (1.0, 0.0, 0.0)}
        edges = [self.edge(0, 1, poses)]
        information, contributors, _rejected = se2_information.build_information(
            [0, 1], edges, excluded_pairs=[(1, 0)])
        self.assertEqual(contributors, 0)
        self.assertEqual(float(abs(information).sum()), 0.0)

    def test_constraint_d_opt_is_scale_invariant(self):
        covariance = (0.01, 0.0, 0.0, 0.01, 0.0, 0.002)
        small = se2_information.constraint_d_opt(
            __import__('numpy').array(
                [[covariance[0], covariance[1], covariance[2]],
                 [covariance[1], covariance[3], covariance[4]],
                 [covariance[2], covariance[4], covariance[5]]]))
        scaled = se2_information.constraint_d_opt(
            4.0 * __import__('numpy').array(
                [[covariance[0], covariance[1], covariance[2]],
                 [covariance[1], covariance[3], covariance[4]],
                 [covariance[2], covariance[4], covariance[5]]]))
        self.assertAlmostEqual(scaled / small, 0.25, places=6)


class EdgeAnalyticsTest(unittest.TestCase):
    def test_insertion_geodesic_ignores_the_edge_itself(self):
        nodes = {0: {'id': 0, 'x': 0.0, 'y': 0.0, 'theta': 0.0, 'unique_id': 0},
                 1: {'id': 1, 'x': 0.0, 'y': 2.0, 'theta': 0.0, 'unique_id': 1},
                 2: {'id': 2, 'x': 2.0, 'y': 0.0, 'theta': 0.0, 'unique_id': 2}}
        edges = [
            {'index': 0, 'start': 0, 'end': 1},
            {'index': 1, 'start': 1, 'end': 2},
            {'index': 2, 'start': 0, 'end': 2},
        ]
        metrics = edge_analytics.insertion_time_metrics(edges, nodes, [(0, 2)])
        self.assertAlmostEqual(metrics[(0, 2)]['geodesic_m'], 2.0 + math.sqrt(8.0))
        self.assertEqual(metrics[(0, 2)]['hops'], 2)
        self.assertEqual(metrics[(0, 2)]['insertion_index'], 2)
        final = edge_analytics.build_adjacency(edges, nodes)
        self.assertAlmostEqual(edge_analytics.dijkstra(final, 0, 2), 2.0)

    def test_attribution_splits_target_history_and_local(self):
        before_edges = [{'index': 0, 'start': 0, 'end': 1}]
        after_edges = [
            {'index': 0, 'start': 0, 'end': 1},
            {'index': 1, 'start': 3, 'end': 4},
            {'index': 2, 'start': 2, 'end': 5},
            {'index': 3, 'start': 4, 'end': 5},
        ]
        groups = edge_analytics.classify_new_edges(
            before_edges, after_edges, target_ids=[2], history_ids={0, 1, 2})
        self.assertEqual([edge['index'] for edge in groups['target_attributable']],
                         [2])
        self.assertEqual([edge['index'] for edge in groups['local']], [1, 3])
        self.assertEqual(groups['history_touching'], [])

    def test_local_degrees_and_triangles(self):
        nodes = {0: {'id': 0, 'x': 0.0, 'y': 0.0, 'theta': 0.0},
                 1: {'id': 1, 'x': 1.0, 'y': 0.0, 'theta': 0.0},
                 2: {'id': 2, 'x': 1.0, 'y': 1.0, 'theta': 0.0}}
        edges = [{'index': 0, 'start': 0, 'end': 1},
                 {'index': 1, 'start': 1, 'end': 2},
                 {'index': 2, 'start': 0, 'end': 2}]
        degrees = edge_analytics.local_degrees(edges, [0, 1, 2])
        self.assertEqual(degrees, {0: 2, 1: 2, 2: 2})
        triangles = edge_analytics.triangle_count(edges, [0])
        self.assertEqual(triangles[0], 1)

    def test_reconstructed_measurements_are_relative_poses(self):
        nodes = {0: {'id': 0, 'x': 1.0, 'y': 1.0, 'theta': math.pi / 2,
                     'unique_id': 5},
                 1: {'id': 1, 'x': 1.0, 'y': 3.0, 'theta': math.pi / 2,
                     'unique_id': 6}}
        edges = [{'index': 0, 'start': 0, 'end': 1,
                  'covariance_upper_triangle': '0.01 0 0 0.01 0 0.002'}]
        rows = edge_analytics.reconstructed_measurements(edges, nodes)
        self.assertAlmostEqual(rows[0]['measurement_dx'], 2.0, places=9)
        self.assertAlmostEqual(rows[0]['measurement_dy'], 0.0, places=9)
        self.assertAlmostEqual(rows[0]['measurement_dtheta'], 0.0, places=9)
        self.assertAlmostEqual(rows[0]['cov_tt'], 0.002, places=12)

    def test_measurement_ledger_rows_have_required_fields(self):
        record = {
            'provenance_constraints': [{
                'record_type': 'constraint_created',
                'canonical_edge_identity': '0->1', 'source_state_id': 0,
                'target_state_id': 1, 'source_unique_id': 10,
                'target_unique_id': 11, 'relative_mean': [1.0, 2.0, 0.1],
                'covariance_3x3': [[0.01, 0.0, 0.0], [0.0, 0.02, 0.0],
                                   [0.0, 0.0, 0.003]],
                'creation_provenance': 'PREVIOUS_SCAN', 'creation_sequence': 4,
                'matcher_type': 'CoarseToFine', 'match_response': 0.9,
                'match_threshold': 0.7, 'solver_add_constraint_called': True,
                'graph_edge_count_after_creation': 12,
                'before_or_during_probe': 'BEFORE_PROBE',
                'wall_time': 1.0, 'sim_time': 2.0, 'run_id': 'x'}],
            'after_edges': [], 'after_nodes': {},
            'frozen': {'historical_scan_ids': [1]},
            'history_ids': {0, 1},
            'result': {'before_max_scan_id': 1},
            'spec': {'episode_id': 'e', 'condition_id': 'c',
                     'target_id': 't', 'provenance_enabled': True},
            'run_dir': 'd',
        }
        rows = n1_analysis.measurement_ledger_rows(record)
        required = ('source_state_id', 'target_state_id', 'measurement_dx',
                    'measurement_dy', 'measurement_dtheta', 'cov_xx', 'cov_yy',
                    'cov_tt', 'creation_provenance', 'creation_sequence',
                    'before_or_during_probe', 'attribution',
                    'measurement_source')
        for field in required:
            self.assertIn(field, rows[0])
        self.assertEqual(rows[0]['measurement_source'],
                         'PROVENANCE_RELATIVE_MEAN')
        self.assertEqual(rows[0]['attribution'], 'target_attributable')

    def test_ledger_falls_back_when_provenance_disabled(self):
        nodes = {0: {'id': 0, 'x': 0.0, 'y': 0.0, 'theta': 0.0, 'unique_id': 1},
                 1: {'id': 1, 'x': 1.0, 'y': 0.0, 'theta': 0.0, 'unique_id': 2}}
        record = {
            'provenance_constraints': [],
            'after_edges': [{'index': 0, 'start': 0, 'end': 1,
                             'covariance_upper_triangle': '0.01 0 0 0.01 0 0.002'}],
            'after_nodes': nodes,
            'frozen': {'historical_scan_ids': [0]},
            'history_ids': {0, 1},
            'result': {'before_max_scan_id': 1},
            'spec': {'episode_id': 'e', 'condition_id': 'c', 'target_id': 't',
                     'provenance_enabled': False},
            'run_dir': 'd',
        }
        rows = n1_analysis.measurement_ledger_rows(record)
        self.assertEqual(rows[0]['measurement_source'],
                         'RECONSTRUCTED_FROM_CORRECTED_POSES')
        self.assertAlmostEqual(rows[0]['measurement_dx'], 1.0, places=9)


class TargetScreeningTest(unittest.TestCase):
    def test_selection_prefers_non_local_and_distinct(self):
        candidates = [
            {'region_index': 0, 'geodesic_separation_m_mean': 8.0,
             'geodesic_hops_mean': 8, 'geodesic_euclidean_ratio_mean': 2.0,
             'alternative_path_redundancy_mean': 2,
             'segment_length_m_mean': 3.0, 'segment_heading_change_rad_mean': 0.2},
            {'region_index': 1, 'geodesic_separation_m_mean': 7.0,
             'geodesic_hops_mean': 7, 'geodesic_euclidean_ratio_mean': 1.8,
             'alternative_path_redundancy_mean': 3,
             'segment_length_m_mean': 3.2, 'segment_heading_change_rad_mean': 1.5},
            {'region_index': 2, 'geodesic_separation_m_mean': 1.0,
             'geodesic_hops_mean': 1, 'geodesic_euclidean_ratio_mean': 1.0,
             'alternative_path_redundancy_mean': 6,
             'segment_length_m_mean': 4.0, 'segment_heading_change_rad_mean': 1.6},
            {'region_index': 3, 'geodesic_separation_m_mean': 0.2,
             'geodesic_hops_mean': 0, 'geodesic_euclidean_ratio_mean': 1.0,
             'alternative_path_redundancy_mean': 5,
             'segment_length_m_mean': 2.0, 'segment_heading_change_rad_mean': 3.0},
        ]
        selection = target_screening.select_targets(candidates)
        self.assertEqual(selection['status'], 'TARGETS_SELECTED')
        self.assertEqual(selection['primary_region_index'], 0)
        self.assertEqual(selection['secondary_region_index'], 1)
        self.assertEqual(selection['target_ids'],
                         ['map3_grid_anchor_01', 'map3_grid_anchor_03'])

    def test_selection_fails_when_candidates_insufficient(self):
        selection = target_screening.select_targets([
            {'region_index': 0, 'geodesic_separation_m_mean': 1.0,
             'geodesic_hops_mean': 1, 'geodesic_euclidean_ratio_mean': 1.0,
             'alternative_path_redundancy_mean': 1,
             'segment_length_m_mean': 1.0, 'segment_heading_change_rad_mean': 0.0}])
        self.assertEqual(selection['status'], 'TARGET_SCREEN_FAILED')

    def test_quantile_interpolates(self):
        self.assertAlmostEqual(
            target_screening.quantile([0.0, 1.0, 2.0, 3.0], 0.5), 1.5)
        self.assertIsNone(target_screening.quantile([], 0.5))


class ThresholdAndGateTest(unittest.TestCase):
    def test_thresholds_use_measured_repeatability(self):
        with tempfile.TemporaryDirectory() as directory:
            suite = Path(directory) / 'suite'
            (suite / 'episodes').mkdir(parents=True)
            state = {'episodes': []}
            for seed in (1, 2, 3):
                for arm in n0_analysis.INSTRUMENT_ARMS[:1]:
                    episode_id = '{}_{}'.format(seed, arm)
                    run_dir = suite / 'episodes' / episode_id / 'attempt_01'
                    run_dir.mkdir(parents=True)
                    _write_episode(run_dir, episode_id,
                                   block_id='b{}'.format(seed), seed=seed,
                                   condition_id=arm)
                    state['episodes'].append({
                        'episode_id': episode_id,
                        'attempts': [{'status': 'SUCCEEDED',
                                      'run_dir': str(run_dir.relative_to(suite))}]})
            (suite / 'suite_state.json').write_text(json.dumps(state))
            out = Path(directory) / 'thresholds.json'
            thresholds = n1_analysis.freeze_thresholds(str(suite), None, str(out))
            entry = thresholds['outcomes']['target_attributable_edges']
            self.assertEqual(entry['kind'], 'count')
            self.assertGreaterEqual(entry['mde'], 0.0)
            self.assertTrue(out.is_file())

    def test_measurement_gate_failure_pauses_and_never_stops(self):
        """A measurement-gate failure must not be reported as a scientific stop."""
        thresholds = _thresholds()
        unsupported = _block_rows(sweep={'target_edges_delta': -3.0})
        n0_failed = {'outcome': 'POSSIBLE_INSTRUMENTATION_PERTURBATION',
                     'nonperturbation_outcome': 'POSSIBLE_INSTRUMENTATION_PERTURBATION',
                     'preprobe_gate': {'all_pairs_passed': False},
                     'nonperturbation': {'detectable_shifts': [
                         {'outcome': 'final_edge_count', 'arm': 'n0_prov_on',
                          'mean_difference': -2.67, 'threshold': 1.33}]}}
        payload = gate_evaluate(unsupported, thresholds, n0_failed)
        self.assertEqual(payload['state'],
                         'PAUSED_INSTRUMENTATION_NOT_CERTIFIED')
        self.assertNotEqual(payload['state'], 'STOP_DIRECTION')
        self.assertFalse(payload['measurement_gate']['certified'])
        self.assertIsNone(payload['scientific_gate'])
        self.assertTrue(payload['next_required_action'])
        self.assertIn('hypothesis', payload['interpretation'])

    def test_n0_pass_without_n1_is_run_n1_not_stop(self):
        thresholds = _thresholds()
        payload = gate_evaluate([], thresholds,
                                {'outcome': 'OUTCOME_MEASUREMENT_STABLE'})
        self.assertEqual(payload['state'], 'RUN_N1')
        self.assertFalse(payload['intervention_executed'])
        self.assertNotIn('STOP_DIRECTION', payload['state'])

    def test_repair_failed_state(self):
        payload = gate_evaluate(
            [], _thresholds(),
            {'outcome': 'POSSIBLE_INSTRUMENTATION_PERTURBATION',
             'state': 'PAUSED_INSTRUMENTATION_REPAIR_FAILED'})
        self.assertEqual(payload['state'],
                         'PAUSED_INSTRUMENTATION_REPAIR_FAILED')

    def test_scientific_gate_supported(self):
        payload = gate_evaluate(
            _block_rows(sweep={'target_edges_delta': 4.0, 'trace_per_m': 0.04,
                               'utility_per_m': 0.03}),
            _thresholds(), {'outcome': 'OUTCOME_MEASUREMENT_STABLE'})
        self.assertEqual(payload['state'], 'PROCEED_TO_MODELING')
        criteria = payload['scientific_gate']['criteria']
        self.assertTrue(criteria['both_outcome_families_positive_on_both_targets'][
            'passed'])
        self.assertEqual(payload['scientific_gate']['case'],
                         'CASE_3_BOTH_OUTCOME_FAMILIES_FAVOUR_SWEEP')
        self.assertTrue(criteria['sweep_beats_neutral_on_uncertainty_per_cost'][
            'passed'])
        self.assertTrue(criteria['sweep_beats_neutral_on_utility_per_cost'][
            'passed'])

    def test_scientific_gate_not_supported_when_neutral_matches(self):
        payload = gate_evaluate(
            _block_rows(sweep={'target_edges_delta': 4.0},
                        neutral={'target_edges_delta': 4.0}),
            _thresholds(), {'outcome': 'OUTCOME_MEASUREMENT_STABLE'})
        self.assertEqual(payload['state'], 'STOP_DIRECTION')
        self.assertEqual(payload['scientific_gate']['case'],
                         'CASE_1_EDGE_GAIN_FROM_SENSING_OPPORTUNITY')

    def test_case_2_local_reinforcement_is_not_supported(self):
        payload = gate_evaluate(
            _block_rows(sweep={'target_edges_delta': 5.0},
                        neutral={'target_edges_delta': 0.0}),
            _thresholds(), {'outcome': 'OUTCOME_MEASUREMENT_STABLE'})
        self.assertEqual(payload['state'], 'STOP_DIRECTION')
        self.assertEqual(payload['scientific_gate']['case'],
                         'CASE_2_EDGE_GAIN_IS_LOCAL_REINFORCEMENT')

    def test_case_4_target_disagreement_names_one_blocker(self):
        rows = _block_rows(sweep={'target_edges_delta': 4.0,
                                  'trace_per_m': 0.04, 'utility_per_m': 0.03})
        for row in rows:
            if row['target_id'] == 'map3_grid_anchor_03' \
                    and row['condition_id'] == 'n1_a2_sweep90':
                row['target_ablation_trace_impact_per_extra_m'] = '-0.04'
        payload = gate_evaluate(rows, _thresholds(),
                                {'outcome': 'OUTCOME_MEASUREMENT_STABLE'})
        self.assertEqual(payload['state'],
                         'INCONCLUSIVE_NEEDS_ONE_MORE_CONTROL')
        self.assertEqual(payload['scientific_gate']['case'],
                         'CASE_4_TARGET_DISAGREEMENT')
        blocker = payload['scientific_gate']['single_remaining_blocker']
        self.assertIn('map3_grid_anchor_03', blocker)

    def test_mixed_evidence_is_inconclusive(self):
        rows = _block_rows(sweep={'target_edges_delta': 4.0,
                                  'trace_per_m': 0.04, 'utility_per_m': 0.03})
        for row in rows:
            if row['condition_id'] == 'n1_a1_neutral':
                row['target_ablation_dopt_impact_per_extra_m'] = '0.03'
                row['target_ablation_trace_impact_per_extra_m'] = '0.04'
        payload = gate_evaluate(rows, _thresholds(),
                                {'outcome': 'OUTCOME_MEASUREMENT_STABLE'})
        self.assertIn(payload['state'],
                      ('STOP_DIRECTION', 'INCONCLUSIVE_NEEDS_ONE_MORE_CONTROL'))


def _thresholds():
    return {
        'outcomes': {
            'target_attributable_edges': {'mde': 1.0},
            'target_ablation_dopt_impact_relative': {'mde': 0.05},
            'target_ablation_trace_impact_relative': {'mde': 0.05},
        }}


class GateAbstentionTest(unittest.TestCase):
    """No evaluable block must abstain, never claim a reversal."""

    def thresholds(self):
        return _thresholds()

    def n0_certified(self):
        return {'outcome': 'OUTCOME_MEASUREMENT_STABLE'}

    def test_incomplete_blocks_abstain(self):
        rows = [row for row in _block_rows(sweep={'target_edges_delta': -5.0})
                if row['condition_id'] != 'n1_a0_baseline']
        payload = gate_evaluate(rows, self.thresholds(), self.n0_certified())
        self.assertEqual(payload['state'],
                         'INCONCLUSIVE_NEEDS_ONE_MORE_CONTROL')
        accounting = payload['scientific_gate']['block_accounting']
        self.assertEqual(accounting['evaluable_blocks'], 0)
        self.assertEqual(accounting['blocks_with_three_arms'], 0)
        self.assertTrue(accounting['blocks_incomplete'])

    def test_gate_failed_block_is_not_evidence(self):
        rows = _block_rows(sweep={'target_edges_delta': -5.0},
                           targets=('map3_grid_anchor_01',), blocks=(1,))
        blocked = [dict(row, preprobe_gate_passed=False) for row in rows]
        payload = gate_evaluate(blocked, self.thresholds(),
                                self.n0_certified())
        self.assertEqual(payload['state'],
                         'INCONCLUSIVE_NEEDS_ONE_MORE_CONTROL')
        accounting = payload['scientific_gate']['block_accounting']
        self.assertEqual(accounting['evaluable_blocks'], 0)
        self.assertEqual(len(accounting['blocks_rejected_by_comparability_'
                                         'gate']), 1)

    def test_comparable_blocks_still_decide(self):
        rows = _block_rows(sweep={'target_edges_delta': 6.0},
                           neutral={'target_edges_delta': 1.0})
        payload = gate_evaluate(rows, self.thresholds(), self.n0_certified())
        self.assertNotEqual(payload['state'],
                            'PAUSED_INSTRUMENTATION_NOT_CERTIFIED')
        accounting = payload['scientific_gate']['block_accounting']
        self.assertGreater(accounting['evaluable_blocks'], 0)


def _block_rows(sweep=None, neutral=None, targets=('map3_grid_anchor_01',
                                                   'map3_grid_anchor_03'),
                blocks=(1, 2)):
    """Synthetic per-block action rows.

    ``sweep``/``neutral`` map a column name to the value that action attains in
    every block; the block baseline is the zero reference, so a column value is
    already the delta against the block's own baseline action.
    """
    sweep = sweep or {}
    neutral = neutral or {}
    column_for = {
        'target_edges_delta': 'target_edges_delta',
        'trace': 'target_ablation_trace_impact_relative',
        'utility': 'target_ablation_dopt_impact_relative',
        'trace_per_m': 'target_ablation_trace_impact_per_extra_m',
        'utility_per_m': 'target_ablation_dopt_impact_per_extra_m',
    }
    columns = tuple(column_for.values())
    rows = []
    for target_id in targets:
        for block in blocks:
            block_id = 'blk_{}_{}'.format(target_id, block)
            for condition_id, values in (('n1_a0_baseline', {}),
                                         ('n1_a1_neutral', neutral),
                                         ('n1_a2_sweep90', sweep)):
                row = {
                    'block_id': block_id,
                    'target_id': target_id,
                    'condition_id': condition_id,
                    'is_baseline': condition_id == 'n1_a0_baseline',
                    'preprobe_gate_passed': True,
                    'extra_distance_vs_baseline_m': '3.0',
                }
                for column in columns:
                    row[column] = '0.0'
                for key, value in values.items():
                    row[column_for[key]] = str(value)
                rows.append(row)
    return rows


def _write_episode(run_dir, episode_id, block_id, seed, condition_id,
                   group_sizes=(2, 1, 5)):
    """Write a minimal recorded episode that the analytics can load."""
    positions = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0),
                 (3.0, 0.0, 0.0), (4.0, 0.0, 0.0)]
    edges = [(0, 1), (1, 2), (2, 3), (3, 4)]
    before = synthetic_before(positions, edges)
    frozen = synthetic_frozen([0, 1], route_start=0)
    after_positions = list(positions) + [(5.0, 0.0, 0.0), (6.0, 0.0, 0.0)]
    after_edges = list(edges) + [(4, 5), (5, 6)]
    new_edges = []
    index = len(after_edges)
    target_count, history_count, local_count = group_sizes
    for offset in range(target_count):
        after_edges.append((0, index))
        new_edges.append((0, index))
        index += 1
    for offset in range(history_count):
        after_edges.append((2, index))
        new_edges.append((2, index))
        index += 1
    for offset in range(local_count):
        after_edges.append((5, index))
        new_edges.append((5, index))
        index += 1
    after = synthetic_before(after_positions, after_edges)
    after['phase'] = 'after_probe'
    (run_dir / 'pose_graph_before.json').write_text(json.dumps(before))
    (run_dir / 'pose_graph_after.json').write_text(json.dumps(after))
    (run_dir / 'resolved_history_route.json').write_text(json.dumps({
        'resolved_history_waypoints': [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
                                       [2.0, 0.0, 0.0], [3.0, 0.0, 0.0]]}))
    spec = dict(TARGETS['map3_grid_anchor_01'])
    spec.update({
        'episode_id': episode_id, 'protocol_version': 'p1_preflight_v7',
        'target_id': 'map3_grid_anchor_01', 'condition_id': condition_id,
        'maneuver_type': 'pass', 'delta_yaw_deg': 0.0, 'lateral_offset_m': 0.0,
        'neutral_offset_m': 0.0, 'diagnostics_enabled': False,
        'provenance_enabled': False, 'tsp_seed': seed, 'block_id': block_id,
        'block_position': 0, 'repeat': 1, 'sequence': 1,
    })
    result = {
        'status': 'SUCCEEDED', 'episode_id': episode_id, 'spec': spec,
        'frozen_target': frozen, 'before_max_scan_id': 4,
        'after_max_scan_id': 6, 'probe_start_time': 10.0, 'probe_end_time': 13.0,
        'action_completed': True, 'new_keyscan_ids': [5, 6],
        'near_target_keyscan_ids': [5], 'near_target_keyscan_generated': True,
        'loop_events_during_probe': [], 'target_match_events': [],
        'target_constraint_events': [], 'new_full_pose_graph_edges': [],
        'target_full_pose_graph_constraints': [],
        'actual_probe_trajectory_gt': [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        'actual_probe_distance_m': 1.0, 'moves': [],
        'analysis_eligible': True, 'exclusion_reason': None,
        'history_contaminated_by_closure': False,
    }
    (run_dir / 'episode_result.json').write_text(json.dumps(result))


class EndToEndAnalysisTest(unittest.TestCase):
    def test_analyze_suite_produces_artifacts_and_excludes_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            suite = Path(directory) / 'n1'
            (suite / 'episodes').mkdir(parents=True)
            state = {'episodes': []}
            actions = ('n1_a0_baseline', 'n1_a1_neutral', 'n1_a2_sweep90')
            for block, seed in enumerate((42001, 42002), start=1):
                for action in actions:
                    episode_id = 'b{}_{}'.format(block, action)
                    run_dir = suite / 'episodes' / episode_id / 'attempt_01'
                    run_dir.mkdir(parents=True)
                    _write_episode(run_dir, episode_id, 'blk{}'.format(block),
                                   seed, action)
                    state['episodes'].append({
                        'episode_id': episode_id,
                        'attempts': [{'status': 'SUCCEEDED',
                                      'run_dir': str(run_dir.relative_to(suite))}]})
            (suite / 'suite_state.json').write_text(json.dumps(state))
            summary = n1_analysis.analyze_suite(str(suite))
            for name in ('edge_measurement_ledger.csv',
                         'posterior_uncertainty_ablation.csv',
                         'graph_utility_ablation.csv',
                         'n1_matched_action_blocks.csv',
                         'n1_effect_summary.json'):
                self.assertTrue((suite / name).is_file(), name)
            self.assertEqual(summary['episode_counts']['eligible'], 6)
            rows = list(__import__('csv').DictReader(
                open(suite / 'n1_matched_action_blocks.csv')))
            self.assertEqual(len(rows), 6)
            self.assertTrue(any(float(row['extra_distance_vs_baseline_m']) == 0.0
                                for row in rows))

    def test_invalid_episode_is_excluded_from_block_deltas(self):
        with tempfile.TemporaryDirectory() as directory:
            suite = Path(directory) / 'n1'
            (suite / 'episodes').mkdir(parents=True)
            state = {'episodes': []}
            for block, seed in enumerate((42001,), start=1):
                for action in ('n1_a0_baseline', 'n1_a2_sweep90'):
                    episode_id = 'b{}_{}'.format(block, action)
                    run_dir = suite / 'episodes' / episode_id / 'attempt_01'
                    run_dir.mkdir(parents=True)
                    _write_episode(run_dir, episode_id, 'blk', seed, action)
                    if action == 'n1_a2_sweep90':
                        result = json.loads(
                            (run_dir / 'episode_result.json').read_text())
                        result['analysis_eligible'] = False
                        result['exclusion_reason'] = 'test exclusion'
                        (run_dir / 'episode_result.json').write_text(
                            json.dumps(result))
                    state['episodes'].append({
                        'episode_id': episode_id,
                        'attempts': [{'status': 'SUCCEEDED',
                                      'run_dir': str(run_dir.relative_to(suite))}]})
            (suite / 'suite_state.json').write_text(json.dumps(state))
            summary = n1_analysis.analyze_suite(str(suite))
            self.assertEqual(summary['episode_counts']['excluded'], 1)
            self.assertEqual(summary['episode_counts']['eligible'], 1)
            rows = list(__import__('csv').DictReader(
                open(suite / 'n1_matched_action_blocks.csv')))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['condition_id'], 'n1_a0_baseline')


class DriverManeuverTest(unittest.TestCase):
    def driver(self, spec):
        driver = object.__new__(pilot_driver.PilotDriver)
        driver.spec = spec
        driver.lock = __import__('threading').Lock()
        driver.samples = {}
        return driver

    @unittest.skipUnless(DRIVER_AVAILABLE, 'rospy unavailable')
    def test_neutral_maneuver_translates_away_and_returns_in_place(self):
        spec = {'lateral_offset_m': 0.0, 'delta_yaw_deg': 0.0,
                'maneuver_type': 'neutral', 'neutral_offset_m': 1.5}
        driver = self.driver(spec)
        anchor = {'id': 0, 'x': 0.0, 'y': 0.0, 'theta': 0.0}
        segment = [{'id': 0, 'x': -5.0, 'y': 0.0, 'theta': 0.0}]
        goals = driver.probe_goals(anchor, [0.0, 0.0, 0.0], segment)
        labels = [goal[3] for goal in goals]
        self.assertEqual(labels, ['probe_arrival', 'neutral_out', 'neutral_back'])
        self.assertAlmostEqual(goals[1][0], 1.5, places=9)
        self.assertAlmostEqual(goals[1][2], 0.0, places=9)
        self.assertAlmostEqual(goals[2][0], 0.0, places=9)
        self.assertAlmostEqual(goals[2][1], 0.0, places=9)
        self.assertAlmostEqual(goals[1][4][0], 1.5, places=9)

    @unittest.skipUnless(DRIVER_AVAILABLE, 'rospy unavailable')
    def test_neutral_maneuver_direction_away_from_target(self):
        spec = {'lateral_offset_m': 0.0, 'delta_yaw_deg': 0.0,
                'maneuver_type': 'neutral', 'neutral_offset_m': 1.5}
        driver = self.driver(spec)
        anchor = {'id': 0, 'x': 0.0, 'y': 0.0, 'theta': 0.0}
        segment = [{'id': 0, 'x': 5.0, 'y': 0.0, 'theta': 0.0}]
        goals = driver.probe_goals(anchor, [0.0, 0.0, 0.0], segment)
        self.assertAlmostEqual(goals[1][0], -1.5, places=9)

    @unittest.skipUnless(DRIVER_AVAILABLE, 'rospy unavailable')
    def test_neutral_maneuver_requires_positive_offset(self):
        spec = {'lateral_offset_m': 0.0, 'delta_yaw_deg': 0.0,
                'maneuver_type': 'neutral', 'neutral_offset_m': 0.0}
        driver = self.driver(spec)
        with self.assertRaises(RuntimeError):
            driver.probe_goals({'id': 0, 'x': 0.0, 'y': 0.0, 'theta': 0.0},
                               [0.0, 0.0, 0.0],
                               [{'id': 0, 'x': 1.0, 'y': 0.0, 'theta': 0.0}])

    @unittest.skipUnless(DRIVER_AVAILABLE, 'rospy unavailable')
    def test_sweep_maneuver_holds_position(self):
        spec = {'lateral_offset_m': 0.0, 'delta_yaw_deg': 0.0,
                'maneuver_type': 'sweep', 'neutral_offset_m': 0.0}
        driver = self.driver(spec)
        anchor = {'id': 0, 'x': 2.0, 'y': 3.0, 'theta': 0.3}
        goals = driver.probe_goals(anchor, [2.0, 3.0, 0.3],
                                   [{'id': 0, 'x': 2.0, 'y': 3.0, 'theta': 0.3}])
        self.assertEqual(len(goals), 4)
        for goal in goals:
            self.assertAlmostEqual(goal[0], 2.0, places=9)
            self.assertAlmostEqual(goal[1], 3.0, places=9)


class ProvenanceObservationOnlyTest(unittest.TestCase):
    """The provenance instrument must not change the graph it records."""

    def recorded_on_episode(self):
        if not V7_SUITE.is_dir():
            return None
        for episode in sorted(V7_SUITE.iterdir()):
            if 'baseline_diag_on' not in episode.name:
                continue
            attempt = episode / 'attempt_01'
            if (attempt / 'karto_edge_provenance.jsonl').is_file():
                return attempt
        return None

    def test_recorded_constraints_match_the_final_graph(self):
        attempt = self.recorded_on_episode()
        if attempt is None:
            self.skipTest('no recorded provenance episode available')
        records = edge_analytics.provenance_constraints(
            edge_analytics.load_provenance(attempt / 'karto_edge_provenance.jsonl'))
        after = edge_analytics.load_json(attempt / 'pose_graph_after.json')
        nodes = edge_analytics.load_nodes(after)
        edges = edge_analytics.load_edges(after, nodes)
        recorded = {(int(record['source_state_id']), int(record['target_state_id']))
                    for record in records}
        graph = {(edge['start'], edge['end']) for edge in edges}
        self.assertTrue(recorded.issubset(graph))
        result = edge_analytics.load_json(attempt / 'episode_result.json')
        freeze_max = int(result['before_max_scan_id'])
        probe_records = [record for record in records
                         if max(int(record['source_state_id']),
                                int(record['target_state_id'])) > freeze_max]
        probe_graph = {pair for pair in graph if max(pair) > freeze_max}
        self.assertLessEqual(len(probe_records), len(probe_graph))

    def test_new_edges_are_creation_ordered(self):
        attempt = self.recorded_on_episode()
        if attempt is None:
            self.skipTest('no recorded provenance episode available')
        records = edge_analytics.provenance_constraints(
            edge_analytics.load_provenance(attempt / 'karto_edge_provenance.jsonl'))
        sequences = [int(record['creation_sequence']) for record in records]
        self.assertEqual(sequences, sorted(sequences))
        self.assertEqual(len(set(sequences)), len(sequences))


class InstrumentationArtifactTest(unittest.TestCase):
    """Artifact-level checks of the repaired instrumentation.

    These run against the recorded N0-R suite when it is present, so the checks
    are on real output of the C++ implementation rather than on a mock.
    """

    ROOT = Path('/home/wcqw/ac-slam/results/realizability_pilot/'
                'p1_dir_dec_v8_20260916')

    #: every recorded N0-R block: the pre-repair diagnosis block and the two
    #: zero-in-run-I/O blocks (R2 and the pre-registered extension R3)
    N0R_SUITES = ('n0r_sanity', 'n0r2_sanity', 'n0r3_sanity')

    def episodes(self):
        found = []
        for suite in self.N0R_SUITES:
            directory = self.ROOT / suite / 'episodes'
            if directory.is_dir():
                found.extend(sorted(directory.iterdir()))
        return found

    def test_disabled_instrument_writes_no_provenance_file(self):
        found_off = False
        for episode in self.episodes():
            if 'provenance_off' not in episode.name:
                continue
            found_off = True
            for attempt in sorted(episode.glob('attempt_*')):
                self.assertFalse(
                    (attempt / 'karto_edge_provenance.jsonl').is_file(),
                    '{} must not produce a provenance file'.format(attempt))
        if not found_off:
            self.skipTest('no N0-R provenance-off episode recorded')

    def test_buffered_provenance_matches_the_frozen_schema(self):
        schema = json.loads((THIS_DIR / 'edge_provenance_schema.json').read_text())
        required = schema['constraint_created_required_fields']
        seen = 0
        for episode in self.episodes():
            if 'buffered_provenance_on' not in episode.name:
                continue
            for attempt in sorted(episode.glob('attempt_*')):
                path = attempt / 'karto_edge_provenance.jsonl'
                if not path.is_file():
                    continue
                records = [json.loads(line) for line in path.read_text().splitlines()
                           if line.strip()]
                constraints = [record for record in records
                               if record['record_type'] == 'constraint_created']
                self.assertTrue(constraints, 'no constraint records in {}'.format(path))
                for record in constraints:
                    missing = [field for field in required if field not in record]
                    self.assertEqual(missing, [], 'missing fields in {}'.format(path))
                    seen += 1
                sequences = [record['creation_sequence'] for record in constraints]
                self.assertEqual(sequences, sorted(sequences))
                self.assertEqual(len(set(sequences)), len(sequences))
                # Measurements and covariances must be present and finite.
                for record in constraints:
                    covariance = record['covariance_3x3']
                    self.assertEqual(len(covariance), 3)
                    self.assertEqual(len(covariance[0]), 3)
                    for row in covariance:
                        for value in row:
                            self.assertTrue(math.isfinite(float(value)))
        if not seen:
            self.skipTest('no buffered-provenance episode recorded')

    def test_records_keep_creation_order_across_record_types(self):
        for episode in self.episodes():
            if 'buffered_provenance_on' not in episode.name:
                continue
            for attempt in sorted(episode.glob('attempt_*')):
                path = attempt / 'karto_edge_provenance.jsonl'
                if not path.is_file():
                    continue
                records = [json.loads(line) for line in path.read_text().splitlines()
                           if line.strip()]
                times = [float(record['sim_time']) for record in records]
                self.assertEqual(times, sorted(times),
                                 'records must stay in creation order')

    def test_historical_decision_evidence_is_preserved(self):
        """The pre-amendment label must remain traceable in the log."""
        doc = Path('/home/wcqw/ac-slam/docs/research_log/'
                   '57_direction_decision_experiment.md')
        if not doc.is_file():
            self.skipTest('log not present')
        text = doc.read_text()
        self.assertIn('STOP_DIRECTION', text)
        self.assertIn('PAUSED_INSTRUMENTATION_NOT_CERTIFIED', text)


class ReplayComparisonTest(unittest.TestCase):
    """The replay comparison must be deterministic and structure-sensitive."""

    def graph(self, poses, edges):
        nodes = []
        for index, (x, y, theta) in enumerate(poses):
            nodes.append({'index': index, 'state_id': index,
                          'unique_id': 100 + index, 'x': x, 'y': y, 'theta': theta})
        edge_list = []
        for index, (source, target) in enumerate(edges):
            edge_list.append({
                'index': index, 'source_state_id': source,
                'target_state_id': target, 'source_unique_id': 100 + source,
                'target_unique_id': 100 + target,
                'measurement': {'dx': 1.0, 'dy': 0.0, 'dtheta': 0.0},
                'covariance_3x3': [[0.01, 0.0, 0.0], [0.0, 0.01, 0.0],
                                   [0.0, 0.0, 0.001]],
            })
        return {'dump_version': 1, 'run_id': 'x', 'nodes': nodes, 'edges': edge_list}

    def test_identical_graphs_certify_neutrality(self):
        graph = self.graph([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)], [(0, 1)])
        comparison = replay_compare.compare_graphs(graph, graph)
        result = replay_compare.verdict([('same', comparison)], comparison)
        self.assertEqual(result['verdict'], 'REPLAY_NEUTRALITY_CERTIFIED')

    def test_extra_edge_is_not_neutral(self):
        base = self.graph([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)], [(0, 1)])
        extra = self.graph([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)], [(0, 1)])
        extra['edges'] = extra['edges'] + [dict(extra['edges'][0],
                                                index=1,
                                                target_state_id=0,
                                                source_state_id=1)]
        comparison = replay_compare.compare_graphs(base, extra)
        result = replay_compare.verdict([('off_vs_on', comparison)], comparison)
        self.assertEqual(result['verdict'], 'REPLAY_INSTRUMENT_NOT_NEUTRAL')
        self.assertTrue(any(failure['field'] == 'edge_count'
                            for failure in result['failures']))

    def test_measurement_difference_within_repeatability_is_tolerated(self):
        base = self.graph([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)], [(0, 1)])
        noisy = self.graph([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)], [(0, 1)])
        noisy['edges'][0]['measurement']['dx'] = 1.0 + 2e-4
        repeatability = replay_compare.compare_graphs(base, noisy)
        comparison = replay_compare.compare_graphs(noisy, base)
        comparison['edge_measurement_max_difference'] = 1e-4
        result = replay_compare.verdict([('off_vs_on', comparison)], repeatability)
        self.assertEqual(result['verdict'], 'REPLAY_NEUTRALITY_CERTIFIED')
        self.assertGreaterEqual(result['tolerance']['edge_measurement_max_difference'],
                                2e-4)


class RelativeMeanTest(unittest.TestCase):
    """The ledger must read the recorded object form and the legacy sequence."""

    def test_object_form_is_read(self):
        self.assertEqual(
            edge_analytics.relative_mean_components(
                {'x': 1.0, 'y': -2.0, 'yaw': 0.5}),
            (1.0, -2.0, 0.5))

    def test_sequence_form_is_read(self):
        self.assertEqual(
            edge_analytics.relative_mean_components([1.0, -2.0, 0.5]),
            (1.0, -2.0, 0.5))

    def test_missing_and_malformed_values_are_rejected(self):
        self.assertIsNone(edge_analytics.relative_mean_components(None))
        self.assertIsNone(edge_analytics.relative_mean_components({'x': 1.0}))
        self.assertIsNone(edge_analytics.relative_mean_components([]))

    def test_measurement_rows_accept_the_recorded_schema(self):
        constraint = {
            'record_type': 'constraint_created',
            'source_state_id': 0,
            'target_state_id': 1,
            'source_unique_id': 0,
            'target_unique_id': 1,
            'relative_mean': {'x': 1.25, 'y': -0.5, 'yaw': 0.25},
            'covariance_3x3': [[1e-3, 0.0, 0.0],
                               [0.0, 2e-3, 0.0],
                               [0.0, 0.0, 3e-3]],
            'creation_sequence': 3,
        }
        rows = edge_analytics.measurement_rows([constraint])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['measurement_dx'], 1.25)
        self.assertEqual(rows[0]['measurement_dy'], -0.5)
        self.assertEqual(rows[0]['measurement_dtheta'], 0.25)
        self.assertEqual(rows[0]['cov_yy'], 2e-3)


class ExtensionProtocolTest(unittest.TestCase):
    """The pre-registered extension must differ from the frozen block in the
    seed list only: same target, same maneuver, same instrument options, same
    arm order pattern."""

    FREEZE_FIELDS = ('target_id', 'condition_id', 'maneuver_type',
                     'neutral_offset_m', 'delta_yaw_deg', 'lateral_offset_m',
                     'diagnostics_enabled', 'provenance_enabled',
                     'observer_enabled', 'instrumentation_flush_period_s')

    def test_extension_reuses_the_frozen_options(self):
        frozen = episode_specs('n0r_sanity')
        extension = episode_specs('n0r_extension')
        self.assertEqual(len(extension), 4)
        self.assertEqual([spec['tsp_seed'] for spec in extension],
                         [41003, 41003, 41004, 41004])
        self.assertEqual({spec['block_id'] for spec in extension},
                         {'n0r_seed41003', 'n0r_seed41004'})
        # The alternating arm order is part of the design: block 0 = [off, on],
        # block 1 = [on, off], and the pattern repeats for the added blocks.
        frozen_orders = [[spec['condition_id'] for spec in frozen
                          if spec['block_id'] == block]
                         for block in sorted({spec['block_id'] for spec in frozen})]
        extension_orders = [[spec['condition_id'] for spec in extension
                             if spec['block_id'] == block]
                            for block in sorted({spec['block_id']
                                                 for spec in extension})]
        self.assertEqual(
            [order for order in extension_orders],
            [frozen_orders[index % len(frozen_orders)]
             for index in range(len(extension_orders))])
        # Every option other than the seed/block bookkeeping is inherited from
        # the frozen condition it belongs to.
        frozen_by_condition = {}
        for spec in frozen:
            frozen_by_condition.setdefault(spec['condition_id'], spec)
        for spec in extension:
            reference = frozen_by_condition[spec['condition_id']]
            for field in self.FREEZE_FIELDS:
                self.assertEqual(
                    spec[field], reference[field],
                    'extension changed {}: {} vs {}'.format(
                        field, spec[field], reference[field]))

    def test_extension_keeps_zero_in_run_io(self):
        for spec in episode_specs('n0r_extension'):
            self.assertEqual(spec['instrumentation_flush_period_s'], 0.0)
            self.assertTrue(spec['observer_enabled'])


class ExtensionDecisionTest(unittest.TestCase):
    """The pre-registered four-pair extension rule."""

    @property
    def module(self):
        return n0_extension_decision

    def suite_payload(self, seed_values_off, seed_values_on,
                      outcome='final_edge_count'):
        return {
            'comparator_arm': 'n0r_provenance_off',
            'outcomes': {outcome: {
                'n0r_provenance_off': dict(seed_values_off),
                'n0r_buffered_provenance_on': dict(seed_values_on)}},
        }

    def test_merge_unions_suites(self):
        merged = self.module.merge_outcomes(
            self.suite_payload({41001: 1}, {41001: 2}),
            self.suite_payload({41003: 3}, {41003: 4}))
        self.assertEqual(sorted(merged['final_edge_count'][
            'n0r_provenance_off']), [41001, 41003])

    def test_pause_requires_all_four_pairs(self):
        suites = [
            self.suite_payload({41001: 10, 41002: 10}, {41001: 5, 41002: 5}),
            self.suite_payload({41003: 10, 41004: 10}, {41003: 5, 41004: 5}),
        ]
        merged = self.module.evaluate_from_payloads(
            suites, {'repeatability': {'final_edge_count': {'mad': 1.0}}})
        self.assertEqual(merged['outcome'],
                         self.module.OUTCOME_PAUSED)

    def test_mixed_signs_are_uninformative(self):
        suites = [
            self.suite_payload({41001: 10, 41002: 10}, {41001: 5, 41002: 5}),
            self.suite_payload({41003: 10, 41004: 10}, {41003: 15, 41004: 15}),
        ]
        payload = self.module.evaluate_from_payloads(
            suites, {'repeatability': {'final_edge_count': {'mad': 1.0}}})
        self.assertEqual(payload['outcome'],
                         self.module.OUTCOME_UNINFORMATIVE)

    def test_within_repeatability_shift_is_uninformative(self):
        suites = [
            self.suite_payload({41001: 10, 41002: 10}, {41001: 9, 41002: 9}),
            self.suite_payload({41003: 10, 41004: 10}, {41003: 9, 41004: 9}),
        ]
        payload = self.module.evaluate_from_payloads(
            suites, {'repeatability': {'final_edge_count': {'mad': 5.0}}})
        self.assertEqual(payload['outcome'],
                         self.module.OUTCOME_UNINFORMATIVE)


class CertificationTest(unittest.TestCase):
    def sanity_payload(self, differences, outcome='final_edge_count',
                       comparable_seeds=(1, 2), preprobe_classes=True):
        statistics = {
            'differences': differences,
            'mean_difference': sum(differences) / len(differences),
            'all_same_sign_nonzero': all(value != 0 for value in differences)
            and (all(value > 0 for value in differences)
                 or all(value < 0 for value in differences)),
        }
        reference = {seed: 10 for seed in range(1, len(differences) + 1)}
        instrumented = {seed: 10 + difference for seed, difference in
                        zip(sorted(reference), differences)}
        outcomes = {outcome: {'n0r_provenance_off': dict(reference),
                              'n0r_buffered_provenance_on': instrumented}}
        payload = {
            'suite_dir': 'x',
            'comparator_arm': 'n0r_provenance_off',
            'outcomes': outcomes,
            'nonperturbation': {'per_outcome': {outcome: {
                'n0r_buffered_provenance_on': {'statistics': statistics}}}},
        }
        if preprobe_classes:
            payload['preprobe_gate'] = {
                'all_pairs_passed': len(comparable_seeds) == len(differences),
                'tolerances': {'node_count_abs_tolerance': 2},
                'measured_pair_deviation': [
                    {'seed': seed,
                     'arm_a': 'n0r_buffered_provenance_on',
                     'arm_b': 'n0r_provenance_off',
                     'preprobe_node_count_a': 35 if seed in comparable_seeds
                     else 43,
                     'preprobe_node_count_b': 35,
                     'passed': seed in comparable_seeds}
                    for seed in sorted(reference)],
            }
        return payload

    def test_persistent_shift_pauses_the_round(self):
        sanity = self.sanity_payload([-3, -3])
        payload = n0_certification.certify(
            sanity, None, {'repeatability': {'final_edge_count': {'mad': 1.5}}})
        self.assertEqual(payload['outcome'],
                         'PAUSED_INSTRUMENTATION_REPAIR_FAILED')

    def test_small_shift_within_repeatability_passes(self):
        sanity = self.sanity_payload([-1, -1])
        payload = n0_certification.certify(
            sanity, None, {'repeatability': {'final_edge_count': {'mad': 1.5}}})
        self.assertEqual(payload['outcome'], 'PENDING_SAME_INPUT_REPLAY')

    def test_incomparable_pair_cannot_accuse_the_instrument(self):
        sanity = self.sanity_payload([-3, -3], comparable_seeds=(1,))
        payload = n0_certification.certify(
            sanity, None, {'repeatability': {'final_edge_count': {'mad': 1.5}}})
        # One matched pair cannot accuse the instrument; with no replay yet the
        # round stays open instead of being closed either way.
        self.assertEqual(payload['outcome'],
                         'PAUSED_INSTRUMENTATION_INCONCLUSIVE')
        self.assertFalse(payload['online_sanity_usable'])
        entry = payload['online_sanity']['entries'][0]
        self.assertEqual(entry['paired_differences'], [-3.0])
        self.assertEqual(entry['excluded_incomparable_seeds'], ['2'])
        self.assertFalse(entry['triggers_stop_rule'])

    def test_unusable_online_block_falls_through_to_the_replay(self):
        sanity = self.sanity_payload([-3, -3], comparable_seeds=(1,))
        payload = n0_certification.certify(
            sanity, {'verdict': {'verdict': 'REPLAY_NEUTRALITY_CERTIFIED'}},
            {'repeatability': {'final_edge_count': {'mad': 1.5}}})
        self.assertFalse(payload['online_sanity_usable'])
        self.assertEqual(payload['outcome'], 'OUTCOME_MEASUREMENT_STABLE')

    def test_comparable_shift_pauses_even_with_replay_neutral(self):
        sanity = self.sanity_payload([-3, -3])
        payload = n0_certification.certify(
            sanity, {'verdict': {'verdict': 'REPLAY_NEUTRALITY_CERTIFIED'}},
            {'repeatability': {'final_edge_count': {'mad': 1.5}}})
        self.assertEqual(payload['outcome'],
                         'PAUSED_INSTRUMENTATION_REPAIR_FAILED')

    def test_two_comparable_pairs_are_enough_to_pass(self):
        sanity = self.sanity_payload([2, 2, 5],
                                     comparable_seeds=(1, 2))
        payload = n0_certification.certify(
            sanity, None, {'repeatability': {'final_edge_count': {'mad': 3.0}}})
        self.assertEqual(payload['outcome'], 'PENDING_SAME_INPUT_REPLAY')
        entry = payload['online_sanity']['entries'][0]
        self.assertEqual(entry['paired_differences'], [2.0, 2.0])
        self.assertFalse(entry['triggers_stop_rule'])

    def test_missing_preprobe_information_does_not_block(self):
        sanity = self.sanity_payload([-3, -3], preprobe_classes=False)
        payload = n0_certification.certify(
            sanity, None, {'repeatability': {'final_edge_count': {'mad': 1.5}}})
        self.assertEqual(payload['online_sanity']['comparability']['source'],
                         'not_evaluable')
        self.assertEqual(payload['outcome'],
                         'PAUSED_INSTRUMENTATION_REPAIR_FAILED')

    def test_replay_certifies_only_when_neutral(self):
        sanity = self.sanity_payload([-1, -1])
        reference = {'repeatability': {'final_edge_count': {'mad': 1.5}}}
        neutral = n0_certification.certify(sanity, {
            'verdict': {'verdict': 'REPLAY_NEUTRALITY_CERTIFIED'}}, reference)
        self.assertEqual(neutral['outcome'], 'OUTCOME_MEASUREMENT_STABLE')
        not_neutral = n0_certification.certify(sanity, {
            'verdict': {'verdict': 'REPLAY_INSTRUMENT_NOT_NEUTRAL',
                        'failures': [{'field': 'edge_count'}]}}, reference)
        self.assertEqual(not_neutral['outcome'], 'INSTRUMENTATION_NOT_NEUTRAL')


if __name__ == '__main__':
    unittest.main()
