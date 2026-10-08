#!/usr/bin/python3
"""Static regressions for the outcome-blind serial prefix-only screen."""

import tempfile
import unittest
from pathlib import Path

import a1_screen as a1
import serial_unified_replay as replay
from v13_prefix_equivalence import compare_graphs


class ScreeningStaticTests(unittest.TestCase):
    def test_reference_selection_and_frozen_order(self):
        slots = a1.scheduled_slots()
        refs = a1.validate_slots(slots)
        self.assertEqual(refs, {'target_A_H1': 1, 'target_A_H2': 2,
                                'target_B_H1': 3})
        self.assertEqual(len(slots), 24)
        self.assertEqual(slots[:3], [(1, 'P', 1, 'target_A_H1'),
                                     (1, 'P', 1, 'target_A_H2'),
                                     (1, 'P', 1, 'target_B_H1')])

    def test_distinct_six_decimal_clusters(self):
        base = {'nodes': [{'state_id': 0, 'unique_id': 0,
                           'x': 1.0000001, 'y': 0.0, 'theta': 0.0}],
                'edges': []}
        same_six = {'nodes': [{'state_id': 0, 'unique_id': 0,
                               'x': 1.0000002, 'y': 0.0, 'theta': 0.0}],
                    'edges': []}
        other_six = {'nodes': [{'state_id': 0, 'unique_id': 0,
                                'x': 1.0000012, 'y': 0.0, 'theta': 0.0}],
                     'edges': []}
        self.assertTrue(compare_graphs(replay.six_decimal_semantics(base),
                                       replay.six_decimal_semantics(same_six))['numerical']['exact'])
        self.assertFalse(compare_graphs(base, same_six)['numerical']['exact'])
        self.assertFalse(compare_graphs(replay.six_decimal_semantics(base),
                                        replay.six_decimal_semantics(other_six))['numerical']['exact'])

    def test_no_suffix_api(self):
        with self.assertRaisesRegex(ValueError, 'forbids'):
            replay.unified_replay('unused', 'unused', 'unused', combined_path='forbidden')

    def test_runtime_sha_mismatch_stops(self):
        with self.assertRaisesRegex(RuntimeError, 'runtime mapper SHA mismatch'):
            a1.check_runtime({'executable_sha256': 'wrong', 'mapped_paths': []},
                             {'observed_binaries': {'mapper': {'sha256': 'expected'}}})

    def test_dynamic_library_sha_mismatch_stops(self):
        with tempfile.TemporaryDirectory() as temp:
            binaries = {'mapper': {'sha256': 'ok'}}
            mapped = []
            for key in a1.KEY_LIBRARIES[1:]:
                path = Path(temp) / key
                path.write_bytes(b'unchanged library')
                binaries[key] = {'path': str(path), 'sha256': a1.sha(path)}
                mapped.append(str(path))
            binaries['libOpenKarto.so']['sha256'] = 'tampered'
            with self.assertRaisesRegex(RuntimeError, 'runtime isolated library mismatch'):
                a1.check_runtime({'executable_sha256': 'ok', 'mapped_paths': mapped},
                                 {'observed_binaries': binaries})

    def test_frozen_protocol_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'frozen.json'
            a1.save_new(path, {'frozen': True})
            with self.assertRaises(FileExistsError):
                a1.save_new(path, {'frozen': False})

    def test_old_q_cannot_be_reference_and_stop_logic_present(self):
        source = Path(a1.__file__).read_text()
        self.assertIn("'reference_ordinal': references[block]", source)
        self.assertIn('frozen stop event already exists; no further runs', source)
        self.assertIn('NOT_RUN_DUE_TO_FROZEN_STOP_RULE', source)
        self.assertNotIn('qualification_reference_path', source)

    def test_real_input_counts_and_hashes_are_history_specific(self):
        inputs = a1.frozen_inputs()
        self.assertEqual(inputs['target_A_H1']['expected_count'], 35)
        self.assertEqual(inputs['target_A_H2']['expected_count'], 35)
        self.assertEqual(inputs['target_B_H1']['expected_count'], 33)


if __name__ == '__main__':
    unittest.main()
