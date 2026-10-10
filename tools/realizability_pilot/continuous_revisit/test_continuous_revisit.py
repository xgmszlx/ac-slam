#!/usr/bin/python3
"""Targeted tests for the continuous revisit chain (handoff section 5).

Run with::

    /usr/bin/python3 tools/realizability_pilot/continuous_revisit/test_continuous_revisit.py

These tests cover the four failure modes the handoff calls out before any
backend run: continuity preserved (no suffix stitching), laser/base transform
correctness, phase truncation without lost or duplicated frames, and the frozen
action definitions (including the negative-rotation wrap).
"""

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import geometry as ge  # noqa: E402
import protocol as cr  # noqa: E402


class ContinuityTest(unittest.TestCase):
    def test_single_rigid_alignment_keeps_consecutive_distances(self):
        trajectory = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.6), (2.4, 2.0),
                      (1.0, 3.0)]
        reference = [(x + 5.0, -y + 2.0) for x, y in trajectory]
        transform = ge.align_rigid(trajectory, reference)
        moved = ge.apply_rigid(transform, trajectory)
        before = ge.consecutive_distances(trajectory)
        after = ge.consecutive_distances(moved)
        self.assertEqual(len(before), len(after))
        for first, second in zip(before, after):
            self.assertAlmostEqual(first, second, places=9)

    def test_prefix_and_full_alignment_agree_on_a_rigid_pair(self):
        trajectory = [(0.0, 0.0), (1.0, -0.2), (2.0, 0.4), (3.0, 1.0)]
        yaw, tx, ty = 0.7, 3.0, -2.0
        reference = [ge.pose_apply((yaw, tx, ty), point)[:2]
                     for point in trajectory]
        prefix = ge.align_rigid(trajectory[:2], reference[:2])
        full = ge.align_rigid(trajectory, reference)
        for a, b in zip(prefix, full):
            self.assertAlmostEqual(a, b, places=9)
        self.assertLess(max(ge.residuals(trajectory, reference, full)), 1e-9)

    def test_segment_wise_suffix_transform_is_detectable(self):
        """A stitched suffix would displace the trajectory; a rigid one cannot."""
        trajectory = [(float(i), 0.0) for i in range(6)]
        reference = ge.apply_rigid((0.3, 1.0, 1.0), trajectory)
        stitched_reference = list(reference)
        for index in range(3, len(stitched_reference)):
            x, y = stitched_reference[index]
            stitched_reference[index] = (x + 0.25, y - 0.3)
        rigid_residuals = ge.residuals(trajectory, stitched_reference,
                                       ge.align_rigid(trajectory,
                                                      stitched_reference))
        self.assertGreater(max(rigid_residuals), 0.05)
        # A rigid alignment preserves inter-frame distances exactly; the
        # stitched reference does not, so the distance profile exposes it.
        aligned = ge.apply_rigid(ge.align_rigid(trajectory, stitched_reference),
                                trajectory)
        for first, second in zip(ge.consecutive_distances(aligned),
                                 ge.consecutive_distances(trajectory)):
            self.assertAlmostEqual(first, second, places=12)
        self.assertGreater(
            max(abs(a - b) for a, b in
                zip(ge.consecutive_distances(aligned),
                    ge.consecutive_distances(stitched_reference))), 0.05)

    def test_path_length_and_rotation_helpers(self):
        samples = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.5), (1.0, 1.0, 0.5),
                   (1.0, 1.0, -0.5)]
        self.assertAlmostEqual(ge.path_length(samples), 2.0, places=9)
        self.assertAlmostEqual(ge.cumulative_rotation(samples), 1.5, places=9)
        self.assertAlmostEqual(ge.wrap_angle(2 * math.pi - 0.1), -0.1, places=9)


class LaserTransformTest(unittest.TestCase):
    def test_offset_is_applied_before_the_bearing(self):
        # Robot at the origin facing +x, laser 0.2 m ahead of the base.
        hits = ge.laser_hits((0.0, 0.0, 0.0), [1.0, 1.0], -math.pi / 2,
                             math.pi / 2, [0, 1])
        self.assertAlmostEqual(hits[0][0], 0.2, places=9)  # straight down
        self.assertAlmostEqual(hits[0][1], -1.0, places=9)
        self.assertAlmostEqual(hits[1][0], 1.2, places=9)  # straight ahead
        self.assertAlmostEqual(hits[1][1], 0.0, places=9)

    def test_rotation_of_the_base_is_composed(self):
        hits = ge.laser_hits((3.0, 4.0, math.pi / 2), [2.0], 0.0, 1.0, [0])
        self.assertAlmostEqual(hits[0][0], 3.0, places=9)
        self.assertAlmostEqual(hits[0][1], 6.2, places=9)

    def test_invalid_returns_are_dropped(self):
        increment = 0.1
        hits = ge.laser_hits((0.0, 0.0, 0.0),
                             [float('inf'), -1.0, 1.0], 0.0, increment, [0, 1, 2])
        self.assertEqual(len(hits), 1)
        bearing = 2 * increment
        self.assertAlmostEqual(hits[0][0], 0.2 + math.cos(bearing), places=9)
        self.assertAlmostEqual(hits[0][1], math.sin(bearing), places=9)


class PhaseTruncationTest(unittest.TestCase):
    def records(self, count):
        return [{'index': index, 'range': index} for index in range(count)]

    def test_no_lost_or_duplicated_frames(self):
        selected = ge.truncate_frames(self.records(500), 120, 347)
        self.assertEqual(len(selected), 347)
        self.assertEqual([r['index'] for r in selected],
                         list(range(120, 120 + 347)))
        self.assertEqual(len({r['index'] for r in selected}), 347)

    def test_duplicate_index_is_rejected(self):
        records = self.records(10)
        records.insert(5, {'index': 4, 'range': 4})
        with self.assertRaises(ValueError):
            ge.truncate_frames(records, 0, 10)

    def test_insufficient_frames_raise(self):
        with self.assertRaises(ValueError):
            ge.truncate_frames(self.records(5), 2, 347)

    def test_phases_partition_the_stream_without_gaps(self):
        """History, return and action phases consume disjoint index ranges."""
        records = self.records(1000)
        history = ge.truncate_frames(records, 0, 200)
        return_leg = ge.truncate_frames(records, history[-1]['index'] + 1, 300)
        action = ge.truncate_frames(records, return_leg[-1]['index'] + 1, 347)
        indices = [r['index'] for r in history + return_leg + action]
        self.assertEqual(indices, list(range(indices[0], indices[0] + len(indices))))
        self.assertEqual(len(indices), len(set(indices)))


class ActionDefinitionTest(unittest.TestCase):
    def test_rotation_signs_and_magnitudes_are_frozen(self):
        """Values are the handoff table: S1 peak 1.087946562824985/2, L+/- pi/2."""
        self.assertEqual(cr.ACTIONS['S0']['planned_cumulative_rotation_rad'], 0.0)
        self.assertAlmostEqual(cr.ACTIONS['S1']['max_abs_yaw_rad'],
                               1.087946562824985 / 2.0, places=12)
        self.assertAlmostEqual(cr.ACTIONS['S1']['planned_cumulative_rotation_rad'],
                               1.087946562824985, places=12)
        self.assertGreater(cr.ACTIONS['L+']['max_abs_yaw_rad'], 0.0)
        self.assertLess(cr.ACTIONS['L-']['max_abs_yaw_rad'], 0.0)
        for action_id in ('L+', 'L-'):
            self.assertAlmostEqual(abs(cr.ACTIONS[action_id]['max_abs_yaw_rad']),
                                   math.pi / 2, places=12)
            self.assertAlmostEqual(
                cr.ACTIONS[action_id]['planned_cumulative_rotation_rad'],
                math.pi, places=12)
        for action_id in ('S1', 'L+', 'L-'):
            self.assertEqual(cr.ACTIONS[action_id]['waypoints'][-1], 0.0)

    def test_goals_are_in_place_yaw_only(self):
        for action_id in cr.ACTION_IDS:
            spec = cr.build_spec('place_B', 1, action_id, 1, 0, 0)
            anchor = (-5.95, -18.0, 0.0)
            goals = cr.action_goals(spec, anchor, [anchor[0], anchor[1],
                                                   anchor[2]])
            self.assertEqual(len(goals), len(spec['action_waypoints']))
            for goal in goals:
                x, y, yaw, label, gt_pose = goal
                self.assertAlmostEqual(x, anchor[0], places=9)
                self.assertAlmostEqual(y, anchor[1], places=9)
                self.assertTrue(label.startswith('action_'))
                self.assertAlmostEqual(gt_pose[0], anchor[0], places=9)
                self.assertAlmostEqual(gt_pose[1], anchor[1], places=9)
            if goals:
                self.assertAlmostEqual(goals[0][2],
                                       spec['max_abs_yaw_rad'], places=9)
                self.assertAlmostEqual(goals[-1][2], anchor[2], places=9)

    def test_positive_and_negative_actions_turn_opposite_ways(self):
        anchor = (-5.95, -18.0, 0.0)
        positive = cr.action_goals(cr.build_spec('place_B', 1, 'L+', 1, 0, 0),
                                   anchor, list(anchor))
        negative = cr.action_goals(cr.build_spec('place_B', 1, 'L-', 1, 0, 0),
                                   anchor, list(anchor))
        self.assertGreater(positive[0][2], 0.0)
        self.assertLess(negative[0][2], 0.0)
        self.assertAlmostEqual(abs(positive[0][2]), abs(negative[0][2]),
                               places=12)
        for goals in (positive, negative):
            cumulative = 0.0
            current = anchor[2]
            for goal in goals:
                cumulative += abs(ge.wrap_angle(goal[2] - current))
                current = goal[2]
            self.assertAlmostEqual(cumulative, math.pi, places=9)
            self.assertAlmostEqual(current, anchor[2], places=9)

    def test_planned_cumulative_rotation_equals_the_executed_sweep(self):
        anchor = (0.0, 0.0, 0.0)
        for action_id in ('S1', 'L+', 'L-'):
            spec = cr.build_spec('place_A', 1, action_id, 1, 0, 0)
            goals = cr.action_goals(spec, anchor, list(anchor))
            current = anchor[2]
            cumulative = 0.0
            for goal in goals:
                cumulative += abs(ge.wrap_angle(goal[2] - current))
                current = goal[2]
            self.assertAlmostEqual(cumulative,
                                   spec['planned_cumulative_rotation_rad'],
                                   places=9)
            self.assertAlmostEqual(current, anchor[2], places=9)
        self.assertAlmostEqual(cr.ACTIONS['S1']['max_abs_yaw_rad'] * 2,
                               1.087946562824985, places=12)


class SuitePlanTest(unittest.TestCase):
    def test_forty_eight_episodes_covering_all_places_repeats_actions(self):
        specs = cr.episode_specs()
        self.assertEqual(len(specs), 48)
        for place_id in cr.PLACES:
            for repeat in range(1, cr.REPEATS + 1):
                actions = [spec['action_id'] for spec in specs
                           if spec['place_id'] == place_id
                           and spec['repeat'] == repeat]
                self.assertEqual(sorted(actions), sorted(cr.ACTION_IDS))
        groups = sorted({spec['group_index'] for spec in specs})
        self.assertEqual(groups, list(range(cr.GROUP_COUNT)))
        for group in groups:
            actions = [spec['action_id'] for spec in specs
                       if spec['group_index'] == group]
            self.assertEqual(sorted(actions), sorted(cr.ACTION_IDS))
            self.assertEqual(len({spec['group_id'] for spec in specs
                                  if spec['group_index'] == group}), 1)

    def test_order_position_rotates_with_the_group(self):
        specs = cr.episode_specs()
        for group in range(cr.GROUP_COUNT):
            ordered = sorted([spec for spec in specs
                              if spec['group_index'] == group],
                             key=lambda spec: spec['order_position'])
            self.assertEqual([spec['order_position'] for spec in ordered],
                             [0, 1, 2, 3])
            expected = cr.rotate(cr.ACTION_IDS, group % 4)
            self.assertEqual([spec['action_id'] for spec in ordered], expected)
            self.assertEqual(len({spec['group_id'] for spec in ordered}), 1)

    def test_target_states_are_a_quantile_sample_of_the_segment(self):
        segment = [{'index': index, 'x': float(index), 'y': 0.0}
                   for index in range(41)]
        selected = cr.select_target_states(segment, count=5)
        self.assertEqual(len(selected), 5)
        self.assertEqual(selected[0]['index'], 0)
        self.assertEqual(selected[-1]['index'], 40)
        self.assertEqual([row['index'] for row in selected],
                         sorted(row['index'] for row in selected))

    def test_specs_carry_the_auxiliary_fields_the_driver_needs(self):
        spec = cr.build_spec('place_C', 2, 'L+', 7, 1, 2)
        for key in ('episode_id', 'target_history_waypoint_index', 'action_waypoints',
                    'record_stream', 'tsp_seed', 'history_offsets',
                    'action_frames', 'map_name', 'robot_position',
                    'max_abs_yaw_rad', 'planned_cumulative_rotation_rad'):
            self.assertIn(key, spec)
        self.assertTrue(spec['record_stream'])
        self.assertEqual(spec['target_history_waypoint_index'],
                         cr.PLACES['place_C']['waypoint_index'])
        self.assertEqual(len(spec['action_waypoints']), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
