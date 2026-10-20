import unittest,json
from pathlib import Path
import numpy as np
from analyze import match_unique,corr,resid,D,PLAN
class Checks(unittest.TestCase):
 def test_timestamp_rounding(self):
  r=np.array([1548339348.727420092,1548339348.760930061]);q=np.array([1548339348.72742,1548339348.76093]);np.testing.assert_array_equal(match_unique(r,q),[0,1])
 def test_timestamp_reuse_rejected(self):
  with self.assertRaises(AssertionError):match_unique([0,1],[.999999,1.000001])
 def test_timestamp_gap_rejected(self):
  with self.assertRaises(AssertionError):match_unique([0,1],[.5])
 def test_corr_missing_and_constant(self):
  self.assertEqual(corr(np.array([1,2,3,np.nan]),np.array([2,4,6,8]))['n'],3)
  self.assertIsNone(corr(np.ones(3),np.arange(3))['pearson'])
 def test_phase_residual_removes_offsets(self):
  C=np.eye(2)[[0,0,1,1]];np.testing.assert_allclose(resid(np.array([1,3,10,12]),C),[-1,1,-1,1],atol=1e-12)
 def test_rmse_matches_existing_evaluations(self):
  s=json.loads((D/'results/summary.json').read_text());pairs={r['run']:r for r in s['paired']}
  for n,v in pairs.items():
   m=json.loads((Path(PLAN['runs'][n])/'evaluation/online/metrics.json').read_text())
   self.assertAlmostEqual(v['online_ate_rmse'],m['ate_m']['rmse'],places=12)
   self.assertAlmostEqual(v['online_rpet_rmse'],m['rpe_1s_translation_m']['rmse'],places=12)
 def test_all_timestamp_sets(self):
  s=json.loads((D/'results/summary.json').read_text())
  for n in PLAN['runs']:
   c=s['checks'][n];self.assertEqual((c['frames'],c['ate_matches'],c['rpe_pairs']),(589,588,558));self.assertEqual(c['max_rpe_stamp_delta_us'],0)
 def test_fixed_disjoint_windows(self):
  w=json.loads((D/'results/summary.json').read_text())['selected_windows'];self.assertEqual(len(w),3)
  self.assertEqual(len({x['start_s'] for x in w}),3)
  for x in w:self.assertLessEqual(x['last_rpe_end_s'],x['end_s']);self.assertGreaterEqual(x['first_rpe_start_s'],x['start_s'])
if __name__=='__main__':unittest.main(verbosity=2)
