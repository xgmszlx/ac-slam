#!/usr/bin/python3
"""Pure synthetic certification for v13 technical estimators/selectors."""

import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from se2_information import (anchored_information, edge_jacobian,
                             fixed_root_covariance,
                             fixed_root_joint_marginal,
                             fixed_root_reduced_information, relative_pose,
                             v13_target_information_score)
from v13_prefix_equivalence import certify_repeatability, compare_graphs


def finite_difference_jacobian(source, target, epsilon=1e-7):
    base = np.array(list(source) + list(target), dtype=float)

    def evaluate(values):
        return np.array(relative_pose(values[:3], values[3:]))

    jacobian = np.zeros((3, 6))
    for column in range(6):
        plus = base.copy()
        minus = base.copy()
        plus[column] += epsilon
        minus[column] -= epsilon
        delta = evaluate(plus) - evaluate(minus)
        delta[2] = math.atan2(math.sin(delta[2]), math.cos(delta[2]))
        jacobian[:, column] = delta / (2.0 * epsilon)
    return jacobian


def add_constraint(information, source_position, target_position,
                   source_pose, target_pose, omega):
    result = information.copy()
    jacobian = edge_jacobian(source_pose, target_pose)
    indices = list(range(3 * source_position, 3 * source_position + 3)) + \
        list(range(3 * target_position, 3 * target_position + 3))
    result[np.ix_(indices, indices)] += jacobian.T @ omega @ jacobian
    return 0.5 * (result + result.T)


def connected_chain_information(poses):
    information = np.zeros((3 * len(poses), 3 * len(poses)))
    omega = np.diag([100.0, 100.0, 200.0])
    for index in range(len(poses) - 1):
        information = add_constraint(information, index, index + 1,
                                     poses[index], poses[index + 1], omega)
    return information


class V13EstimatorCertification(unittest.TestCase):
    def test_edge_jacobian_matches_finite_difference(self):
        pairs = [
            ((0.0, 0.0, 0.0), (1.0, 0.2, 0.1)),
            ((-2.0, 1.5, 0.7), (0.3, -1.2, -0.4)),
            ((4.0, -3.0, -1.1), (2.5, 2.0, 1.3)),
        ]
        for source, target in pairs:
            analytical = edge_jacobian(source, target)
            numerical = finite_difference_jacobian(source, target)
            self.assertLess(float(np.max(np.abs(analytical - numerical))),
                            2e-7)

    def test_reduced_inverse_equals_direct_anchored_hessian_inverse(self):
        poses = [(0.0, 0.0, 0.0), (1.0, 0.1, 0.05),
                 (2.0, 0.4, 0.15), (2.7, 1.0, 0.4)]
        information = connected_chain_information(poses)
        reduced_covariance, kept, _ = fixed_root_covariance(information)
        direct = np.linalg.inv(anchored_information(information))
        self.assertTrue(np.allclose(
            reduced_covariance, direct[np.ix_(kept, kept)],
            rtol=1e-10, atol=1e-12))

    def test_information_monotonicity_for_extra_spd_constraint(self):
        poses = [(0.0, 0.0, 0.0), (1.0, 0.1, 0.05),
                 (2.0, 0.4, 0.15), (2.7, 1.0, 0.4)]
        before = connected_chain_information(poses)
        after = add_constraint(before, 1, 3, poses[1], poses[3],
                               np.diag([80.0, 70.0, 120.0]))
        cov_before = fixed_root_joint_marginal(before, [1, 2, 3])
        cov_after = fixed_root_joint_marginal(after, [1, 2, 3])
        eigenvalues = np.linalg.eigvalsh(
            0.5 * ((cov_before - cov_after) +
                   (cov_before - cov_after).T))
        self.assertGreaterEqual(float(np.min(eigenvalues)), -1e-10)
        score_before, _ = v13_target_information_score(before, [1, 2, 3])
        score_after, _ = v13_target_information_score(after, [1, 2, 3])
        self.assertGreaterEqual(score_after + 1e-12, score_before)

    def test_connected_and_disconnected_behavior(self):
        poses = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
                 (2.0, 0.0, 0.0)]
        connected = connected_chain_information(poses)
        reduced, _, eigenvalues = fixed_root_reduced_information(connected)
        self.assertEqual(reduced.shape, (6, 6))
        self.assertGreater(float(np.min(eigenvalues)), 0.0)
        disconnected = np.zeros((9, 9))
        disconnected = add_constraint(disconnected, 0, 1,
                                      poses[0], poses[1], np.eye(3))
        with self.assertRaises(np.linalg.LinAlgError):
            fixed_root_covariance(disconnected)


class V13ComparatorCertification(unittest.TestCase):
    @staticmethod
    def graph(offset=0.0):
        return {
            'nodes': [
                {'state_id': 0, 'unique_id': 0, 'x': 0.0, 'y': 0.0,
                 'theta': 0.0},
                {'state_id': 1, 'unique_id': 1, 'x': 1.0 + offset, 'y': 0.0,
                 'theta': 0.0}],
            'edges': [{
                'source_state_id': 0, 'target_state_id': 1,
                'source_unique_id': 0, 'target_unique_id': 1,
                'measurement': {'dx': 1.0, 'dy': 0.0, 'dtheta': 0.0},
                'covariance_3x3': [[1.0, 0.0, 0.0],
                                   [0.0, 1.0, 0.0],
                                   [0.0, 0.0, 1.0]]}]}

    def test_exact_repeats_freeze_zero_tolerance(self):
        result = certify_repeatability([self.graph(), self.graph(), self.graph()])
        self.assertTrue(result['structural_exact_all_pairs'])
        self.assertTrue(result['numerical_exact_all_pairs'])
        self.assertTrue(all(value == 0.0 for value in
                            result['frozen_numerical_tolerance'].values()))

    def test_structural_and_numerical_are_separate(self):
        result = compare_graphs(self.graph(), self.graph(offset=0.001))
        self.assertTrue(result['structural']['exact'])
        self.assertFalse(result['numerical']['exact'])


if __name__ == '__main__':
    unittest.main()
