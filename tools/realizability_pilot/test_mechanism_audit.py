#!/usr/bin/python3
"""Regression tests for the offline v11 mechanism audit."""

import unittest
from pathlib import Path

import mechanism_audit as audit


REPO = Path(__file__).resolve().parents[2]
V10 = REPO / 'results/realizability_pilot/p1_dwell_control_v10_20260917'


@unittest.skipUnless(V10.exists(), 'v10 evidence is not present')
class MechanismAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graphs = {branch: audit.branch_graph_data(V10, branch)
                      for branch in audit.BRANCHES}
        for branch in audit.BRANCHES:
            audit.attach_provenance(V10, branch, cls.graphs[branch])
        cls.timelines = {
            branch: audit.reconstruct_keyscans(
                V10, branch, cls.graphs[branch])
            for branch in audit.BRANCHES}

    def test_has_moved_enough_reconstruction_matches_mapper_counts(self):
        self.assertEqual(
            {branch: len(rows) for branch, rows in self.timelines.items()},
            {'A0_baseline': 27, 'A1_dwell': 27, 'A2_sweep90': 29})
        extra = [row for row in self.timelines['A2_sweep90']
                 if row['sweep_count_exclusive_keyscan']]
        self.assertEqual([row['node_id'] for row in extra], [60, 61])
        self.assertTrue(all(row['keyscan_criterion'] == 'HEADING'
                            for row in extra))

    def test_lidar_geometry_is_measured_limited_fov(self):
        lidar = audit.lidar_geometry(V10)
        self.assertEqual(lidar['classification'], 'LASER_FOV_LIMITED')
        self.assertEqual(lidar['beam_count'], 901)
        self.assertAlmostEqual(lidar['horizontal_fov_deg'], 180.0, places=4)
        self.assertGreater(lidar['three_sweep_union_sector_deg'], 238.0)

    def test_edge_surplus_dependency(self):
        rows = audit.edge_dependency_rows(self.graphs)
        surplus = [row for row in rows
                   if row['counts_toward_five_edge_net_surplus']]
        self.assertEqual(len(surplus), 5)
        direct = [row for row in surplus if row['dependency_class'] ==
                  'DIRECT_INCIDENT_TO_SWEEP_ONLY_KEYSCAN']
        self.assertEqual(len(direct), 4)
        self.assertEqual({row['target'] for row in direct}, {60, 61})

    def test_target_identity_and_covariance_swap_are_identifiable(self):
        rows = audit.target_factor_rows(self.graphs, self.timelines)
        mechanism = audit.target_mechanism(rows)
        self.assertEqual(mechanism['classification'], 'T3')
        self.assertTrue(mechanism['endpoint_identities_equal'])
        swap = audit.counterfactual_swap(self.graphs)
        self.assertEqual(
            swap['status'],
            'IDENTIFIABLE_SAME_ENDPOINT_TARGET_COVARIANCE_SWAP')
        self.assertAlmostEqual(
            swap['delta_U_T_observed_sweep_minus_dwell'],
            35.5344655, places=5)
        self.assertGreater(
            swap['surrounding_topology_effect_holding_dwell_covariance'],
            swap['target_covariance_effect_on_dwell_topology'])


if __name__ == '__main__':
    unittest.main()
