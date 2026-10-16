"""Checks for unsafe ray/clearance claims in the offline qualification helper."""
import unittest
import numpy as np
from entrance_audit import ray_free,analyze

class Geometry(unittest.TestCase):
    def test_blocked_observation_does_not_count_as_visible(self):
        free=np.ones((11,11),dtype=bool);free[5,5]=False
        self.assertFalse(ray_free(free,(5,1),(5,9)))
        self.assertTrue(ray_free(free,(4,1),(4,9)))
    def test_no_unobserved_cells_treated_as_free_views(self):
        image=np.full((31,31),205,dtype=np.uint8)
        image[3:28,3:28]=254
        _,views,_,safe=analyze(image)
        self.assertFalse(safe[0,0])
        for view in views:
            self.assertEqual(image[view['row'],view['col']],254)
            self.assertGreaterEqual(view['clearance_m'],.5)
    def test_fully_unknown_map_has_no_actions(self):
        entries,views,pair,safe=analyze(np.full((20,20),205,dtype=np.uint8))
        self.assertEqual(entries,[]);self.assertEqual(views,[]);self.assertIsNone(pair)
        self.assertEqual(int(safe.sum()),0)

if __name__=='__main__':unittest.main()
