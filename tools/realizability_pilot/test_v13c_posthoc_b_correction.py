import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import v13c_posthoc_b_mechanism_correction as correction


class MechanismCorrectionTest(unittest.TestCase):
    def test_exact_loop_token_is_accepted(self):
        self.assertTrue(correction.is_explicit_try_close_loop({
            'creation_stage': 'TRY_CLOSE_LOOP'}))

    def test_pre_loop_stage_is_not_explicit_loop(self):
        self.assertFalse(correction.is_explicit_try_close_loop({
            'creation_provenance': 'PREVIOUS_SCAN',
            'creation_stage': 'ADD_EDGES_BEFORE_TRY_CLOSE_LOOP',
            'matcher_type': 'SEQUENTIAL_RUNNING_BUFFER'}))

    def test_unrelated_fields_do_not_match(self):
        self.assertFalse(correction.is_explicit_try_close_loop({
            'creation_function': 'TRY_CLOSE_LOOP'}))


if __name__ == '__main__':
    unittest.main()
