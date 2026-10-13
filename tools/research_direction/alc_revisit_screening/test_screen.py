"""Offline regression tests: real pre-states plus unit contract tests.

Synthetic contract mutations are NOT scientific observations or gain labels.
No ROS, replay, simulator, robot command or old-result writer is invoked.
"""
import copy
import csv
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import common
from common import OUT,sha,Inputs,base_pose,workspace_snapshot
from candidates import (validate_bundle,local_candidates,global_candidates,actual_outcome,
                        unique_geometry,deployable_motion_candidates,movement_status)
from headroom import nearest_pairs


def read_csv(path):
    with path.open() as f:return list(csv.DictReader(f))


class ScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base=OUT/'audit/pre_state_bundles/D79_B_Lminus_1'
        cls.a1=json.loads((base/'A1.json').read_text());cls.a2=json.loads((base/'A2.json').read_text())
    def test_01_real_arrival_state(self):self.assertTrue(validate_bundle(self.a1,'A1'))
    def test_02_real_before_return_state(self):self.assertTrue(validate_bundle(self.a2,'A2'))
    def test_03_stage_isolation(self):
        with self.assertRaises(ValueError):local_candidates(self.a2)
    def test_04_state_ids_not_list_offsets(self):
        b=copy.deepcopy(self.a1);b['graph']['nodes'].reverse()
        self.assertEqual(local_candidates(b),local_candidates(self.a1))
    def test_05_uid_join(self):
        b=copy.deepcopy(self.a1);b['graph']['nodes'][1]['unique_id']=-44
        with self.assertRaises(ValueError):validate_bundle(b,'A1')
    def test_06_laser_base_reference(self):
        p=base_pose({'x':1.,'y':2.,'theta':math.pi/2})
        self.assertAlmostEqual(p[0],1);self.assertAlmostEqual(p[1],1.8)
    def test_07_first_history_not_return(self):
        self.assertLess(len(self.a1['history_state_ids']),len(self.a1['graph']['nodes']))
        self.assertEqual(set(self.a2['history_state_ids']),{n['state_id'] for n in self.a2['graph']['nodes']})
    def test_08_episode_not_mixed(self):
        b=copy.deepcopy(self.a1);b['graph']['run_id']='other'
        with self.assertRaises(ValueError):validate_bundle(b,'A1')
    def test_09_boundary_counts_not_mixed(self):
        b=copy.deepcopy(self.a1);b['graph']['nodes'].pop()
        with self.assertRaises(ValueError):validate_bundle(b,'A1')
    def test_10_post_scan_rejected(self):
        b=copy.deepcopy(self.a1);b['trajectory_pre'][-1]['stamp']=b['decision_stamp']+1
        with self.assertRaises(ValueError):local_candidates(b)
    def test_11_no_outcome_input(self):
        b=dict(self.a1,outcomes={'gain':99})
        with self.assertRaises(ValueError):local_candidates(b)
    def test_12_no_gt_input(self):
        with self.assertRaises(ValueError):global_candidates(dict(self.a2,gt=[]))
    def test_13_no_Stage_map(self):
        b=dict(self.a1,online_map={'source':'STAGE_GT'})
        with self.assertRaises(ValueError):local_candidates(b)
    def test_14_unexecuted_gain_unknown(self):
        c=local_candidates(self.a1)[2]
        d=actual_outcome(c,'different',{'episode_id':c['episode_id'],'gain':99})
        self.assertIsNone(d['gain']);self.assertEqual(d['status'],'COUNTERFACTUAL_OUTCOME_UNOBSERVED')
    def test_15_unreachable_excluded(self):
        cs=local_candidates(self.a1);cs[2]['eligibility']='UNREACHABLE'
        self.assertNotIn(cs[2],deployable_motion_candidates(cs))
    def test_16_duplicate_geometry(self):
        c=local_candidates(self.a1)[2];d=dict(c,candidate_id='dup')
        out=unique_geometry([c,d]);self.assertEqual(out[1]['eligibility'],'DUPLICATE_GEOMETRY')
    def test_17_missing_map_no_fake_safety(self):
        self.assertIsNone(self.a1['online_map']);self.assertEqual(deployable_motion_candidates(local_candidates(self.a1)),[])
    def test_18_map_without_checker_not_certified(self):
        self.assertEqual(movement_status({'source':'ONLINE_PRE_DECISION'}),'NOT_CERTIFIED_COLLISION_CHECKER_NOT_IMPLEMENTED')
    def test_19_info_separate_from_physical_error(self):
        rows=read_csv(OUT/'analysis/historical_constraint_value.csv')
        self.assertTrue(all('actual_delta_J' in r and 'target_mean_gt_after_m' in r for r in rows))
    def test_20_actual_cost_not_candidate_prediction(self):
        rows=read_csv(OUT/'analysis/actual_revisit_cost.csv')
        self.assertTrue(all(r['estimated_candidate_distance_m']=='' for r in rows))
    def test_21_missing_raw_explicit(self):
        inp=Inputs();self.assertIsNone(inp.json(Path('/nonexistent/screen_raw.json'),required=False));self.assertEqual(len(inp.missing),1)
    def test_22_sha256_verified(self):
        with tempfile.TemporaryDirectory(prefix='alc_screen_test_') as d:
            p=Path(d)/'a';p.write_bytes(b'abc')
            self.assertEqual(sha(p),'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
    def test_23_registered_old_inputs_unchanged(self):
        data=json.loads((OUT/'audit/input_hashes.json').read_text())
        original={p:v for p,v in data.items() if p.startswith('/home/wcqw/ac-slam/') or p.startswith('/home/wcqw/ac-slam_doc81/')}
        self.assertTrue(original);self.assertTrue(all(Path(p).is_file() and sha(p)==v['sha256'] for p,v in original.items()))
    def test_24_other_worktrees_unchanged(self):
        self.assertEqual(workspace_snapshot(),json.loads((OUT/'audit/workspaces_before.json').read_text()))
    def test_25_no_ros_or_simulator_commands(self):
        # Runtime commands in this package are download/PDF operations or git.
        import ast
        for f in Path(__file__).parent.glob('*.py'):
            if f.name.startswith('test'):continue
            tree=ast.parse(f.read_text())
            for n in ast.walk(tree):
                if isinstance(n,ast.Import):self.assertFalse(any(x.name.startswith(('rospy','roslaunch')) for x in n.names))
                if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in ('run','Popen','check_output','call') and n.args:
                    arg=n.args[0]
                    if isinstance(arg,(ast.List,ast.Tuple)) and arg.elts and isinstance(arg.elts[0],ast.Constant):
                        self.assertNotIn(arg.elts[0].value,{'roscore','roslaunch','stage','gazebo','rosrun'})
    def test_26_global_target_not_known_at_decision(self):
        with self.assertRaises(ValueError):global_candidates(dict(self.a2,anchor_state_id=1))
    def test_27_gate_requires_watermark(self):
        with self.assertRaises(ValueError):local_candidates(dict(self.a1,watermark_validated=False))
    def test_28_all_candidates_remain_unobserved(self):
        self.assertTrue(all(c['actual_gain'] is None for c in local_candidates(self.a1)+global_candidates(self.a2)))
    def test_29_wrong_frame_rejected(self):
        with self.assertRaises(ValueError):global_candidates(dict(self.a2,frame='odom'))
    def test_30_time_pairing_excludes_large_gap(self):
        r=np.array([[0.,0,0],[1.,0,0]]);e=np.array([[0.02,0,0],[.4,0,0]])
        a,b,dt=nearest_pairs(r,e);self.assertEqual(len(dt),1);self.assertAlmostEqual(dt[0],.02)
    def test_31_output_cannot_escape(self):
        with self.assertRaises(ValueError):common.write_json('../escape_test.json',{})
    def test_32_counterfactual_cross_episode_join_rejected(self):
        c=local_candidates(self.a1)[0]
        with self.assertRaises(ValueError):actual_outcome(c,c['candidate_id'],{'episode_id':'other','gain':1})
    def test_33_no_missing_registered_inputs(self):
        self.assertEqual(json.loads((OUT/'audit/input_integrity.json').read_text())['missing'],[])
    def test_34_doc80_target_errors_reproduced(self):
        r=read_csv(OUT/'analysis/independent_doc79_target_GT.csv')
        self.assertEqual(len(r),140);self.assertLess(max(float(x['archived_abs_difference_m']) for x in r),1e-9)
    def test_35_frozen_anchor_identity(self):
        with self.assertRaises(ValueError):local_candidates(dict(self.a1,anchor_unique_id=-1))
    def test_36_native_author_paths_reproduced(self):
        r=read_csv(OUT/'analysis/native_RAL_utility_diagnostic.csv')
        self.assertEqual(len(r),45);self.assertTrue(all(x['recorded_path_matches_native_recalculation']=='True' for x in r))
    def test_37_GT_map_only_for_evaluation(self):
        import ast
        for f in ['candidates.py']:
            t=ast.parse((Path(__file__).parent/f).read_text())
            self.assertFalse(any(isinstance(n,ast.ImportFrom) and n.module in ['maps','gt_check','headroom'] for n in ast.walk(t)))
    def test_38_old_no_support_status_preserved(self):
        p=common.ASSETS/'docs/research_log/80_doc79_offline_direction_feasibility_review.md'
        self.assertIn('STOP_PURE_ROTATION_SELECTION',p.read_text())


if __name__=='__main__':unittest.main(verbosity=2)
