#!/usr/bin/python3
"""Technical checks before any backend input is published."""
import copy
import math
import json
import tempfile
from pathlib import Path
import unittest
from b0_tools import OUT, SOURCE, base_pose, compose, inverse, max_difference, compare

class AdapterChecks(unittest.TestCase):
    def test_offset_inversion_over_heading(self):
        for yaw in (0., math.pi / 2., -math.pi, 1.3):
            row = {'x': 7.1, 'y': -2.5, 'yaw': yaw}
            result = compose(base_pose(row), [0.2, 0., 0.])
            self.assertLess(max_difference(result, [7.1, -2.5, yaw]), 2e-15)

    def test_restore_anchor_rule_has_no_fitted_alignment(self):
        odom = [1.0, 2.0, .3]
        corrected = [1.1, 1.9, .4]
        self.assertLess(max_difference(compose(compose(corrected, inverse(odom)), odom), corrected), 1e-15)

    def test_zero_tolerance_retains_tiny_difference(self):
        a = [0., 1., 2.]; b = copy.deepcopy(a); b[1] += 1e-12
        self.assertGreater(max_difference(a, b), 0.)

    def test_graph_id_remap_and_real_measurement_difference(self):
        source = [json.loads(line) for line in SOURCE.open() if line.strip()][:2]
        graph = {'nodes': [{'id': i, 'ranges': row['ranges'], 'corrected': [i, 0., 0.],
                            'sensor_pose': [i + .2, 0., 0.]} for i, row in enumerate(source)],
                 'edges': [{'source': 0, 'target': 1, 'measurement': [1., 0., 0.],
                            'covariance': [1., 0., 0., 0., 1., 0., 0., 0., 1.]}]}
        remapped = copy.deepcopy(graph)
        for node in remapped['nodes']: node['id'] += 10
        remapped['edges'][0]['source'] += 10; remapped['edges'][0]['target'] += 10
        with tempfile.TemporaryDirectory(dir=str(OUT / 'technical')) as directory:
            a, b = Path(directory) / 'a.json', Path(directory) / 'b.json'
            a.write_text(json.dumps(graph)); b.write_text(json.dumps(remapped))
            self.assertTrue(compare(a, b)['exact'])
            remapped['edges'][0]['measurement'][0] += 1e-12
            b.write_text(json.dumps(remapped))
            self.assertFalse(compare(a, b)['exact'])
            self.assertGreater(compare(a, b)['max_measurement_difference'], 0.)
            remapped['nodes'].pop(); b.write_text(json.dumps(remapped))
            # A missing endpoint is a hard invalid graph, never aligned away.
            with self.assertRaises(KeyError): compare(a, b)

if __name__ == '__main__':
    unittest.main()
