#!/usr/bin/python3
"""Infrastructure-only tests for the frozen Phase 4C formal runner."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analyze_phase4c_formal import (
    complete_block_keys, load_loop_insertions, summarize_paired_effects,
    tsp_pairing_audit,
)
import run_phase4b_suite as phase4b
from phase4c_formal_common import CONDITIONS, MAPS, verify_environment
from run_phase4c_formal import canonical_hash, formal_selection_record


class Phase4CFormalRunnerTest(unittest.TestCase):
    def test_only_oracle_mode_differs_between_conditions(self):
        for config in MAPS.values():
            commands = {
                label: phase4b.launch_command(21001, condition, '_test', config)
                for label, condition in CONDITIONS.items()
            }
            normalized = {}
            for label, command in commands.items():
                normalized[label] = [
                    token for token in command if not token.startswith('oracle_mode:=')
                ]
            self.assertEqual(normalized['A'], normalized['B'])
            self.assertEqual(normalized['A'], normalized['C'])
            self.assertIn('oracle_mode:=0', commands['A'])
            self.assertIn('oracle_mode:=1', commands['B'])
            self.assertIn('oracle_mode:=2', commands['C'])

    def test_frozen_source_hashes(self):
        for config in MAPS.values():
            self.assertEqual(verify_environment(config), config['frozen_sha256'])

    def test_selection_record_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            tsp = {'initial_tsp_path': [1, 2, 3], 'full_tsp_path': [1, 2, 1, 3]}
            loops = {'loops': [
                {'loop_id': 1, 'loop_vertex': 7, 'planned_start_time': 2.5,
                 'actual_start_time': 3.0},
                {'loop_id': 2, 'loop_vertex': 9, 'planned_start_time': 8.0,
                 'actual_start_time': None},
            ]}
            (run_dir / 'tsp_record.json').write_text(json.dumps(tsp))
            (run_dir / 'loops.json').write_text(json.dumps(loops))
            record = formal_selection_record(run_dir)
            self.assertEqual(record['selected_loop_vertex_sequence'], [7, 9])
            self.assertEqual(record['planned_loop_count'], 2)
            self.assertEqual(record['executed_loop_count'], 1)
            self.assertEqual(record['initial_tsp_hash'], canonical_hash([1, 2, 3]))
            self.assertTrue((run_dir / 'selection_sequence.json').is_file())

    def test_tsp_pairing_blocks_initial_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inventory = []
            for label in 'ABC':
                run_dir = root / label
                run_dir.mkdir()
                (run_dir / 'tsp_record.json').write_text(json.dumps({
                    'initial_tsp_path': [1, 2, 3] if label != 'C' else [1, 3, 2],
                    'full_tsp_path': [1, 2, 3],
                }))
                inventory.append(('test_map', 21001, label, run_dir))
            with self.assertRaisesRegex(RuntimeError, 'initial TSP mismatch'):
                tsp_pairing_audit(inventory)

    def test_paired_summary_preserves_raw_sign(self):
        rows = [
            {'contrast': 'C-B', 'metric': 'cost', 'difference': value}
            for value in (-2.0, 0.0, 3.0)
        ]
        summary = summarize_paired_effects(rows)
        record = next(row for row in summary if row['contrast'] == 'C-B')
        self.assertEqual(record['paired_block_n'], 3)
        self.assertEqual(record['positive_count'], 1)
        self.assertEqual(record['tie_count'], 1)
        self.assertEqual(record['negative_count'], 1)

    def test_sequence_audit_keeps_zero_loop_blocks(self):
        run_meta = {
            ('map8', 21001, label): {'loops': [1]} for label in 'ABC'
        }
        run_meta.update({
            ('radish_mexico', 21001, label): {'loops': []} for label in 'ABC'
        })
        self.assertEqual(
            complete_block_keys(run_meta),
            [('map8', 21001), ('radish_mexico', 21001)],
        )

    def test_planned_loops_come_from_insertion_events(self):
        with tempfile.TemporaryDirectory() as directory:
            events = Path(directory) / 'events.csv'
            events.write_text(
                'timestamp,event,data\n'
                '8.4,LOOP_INSERTED,"{""path_index"": 11, ""vertex"": 59}"\n'
                '8.4,LOOP_INSERTED,"{""path_index"": 17, ""vertex"": 41}"\n'
                '9.1,GOAL_REACHED,"{""vertex"": 1}"\n',
                encoding='utf-8',
            )
            self.assertEqual(load_loop_insertions(directory), [
                {'selection_order': 1, 'selection_timestamp': 8.4,
                 'path_index': 11, 'loop_vertex': 59},
                {'selection_order': 2, 'selection_timestamp': 8.4,
                 'path_index': 17, 'loop_vertex': 41},
            ])


if __name__ == '__main__':
    unittest.main()
