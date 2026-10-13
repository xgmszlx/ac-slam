#!/usr/bin/python3
import ast,copy,json,math,tempfile,unittest
from pathlib import Path
import numpy as np
import metrics,protocol
from metrics import compose,inverse,error,relative_error,events,exposure,interpolate_gt,geometry_proxy,initial_state_difference

class Tests(unittest.TestCase):
    def test_pose_error(self):self.assertEqual(error([0,0,0],[3,4,0]),(5.,0.))
    def test_heading_wrap(self):self.assertLess(error([0,0,math.pi-.01],[0,0,-math.pi+.01])[1]-.02,1e-10)
    def test_relative_error_global_gauge(self):
        a=[1,2,.3];b=[3,4,-.2];t=[6,-3,1.]
        self.assertLess(max(relative_error(a,b,compose(t,a),compose(t,b))),1e-10)
    def test_laser_base_inverse(self):
        base=[2,4,.7];laser=compose(base,[.2,0,0]);back=compose(laser,[-.2,0,0]);self.assertLess(max(error(base,back)),1e-12)
    def test_interpolation_heading_short_path(self):
        rows=[{'stamp':1,'x':0,'y':0,'theta':math.pi-.01},{'stamp':1.1,'x':1,'y':2,'theta':-math.pi+.01}]
        p,gap=interpolate_gt(rows,1.05);self.assertAlmostEqual(p[0],.5);self.assertLess(abs(abs(p[2])-math.pi),1e-10)
    def test_time_sync_rejects_long_gap(self):
        rows=[{'stamp':1,'x':0,'y':0,'theta':0},{'stamp':2,'x':0,'y':0,'theta':0}]
        self.assertIsNone(interpolate_gt(rows,1.5)[0])
    def test_event_duration(self):
        r=[{'stamp':i*.1,'translation_error_m':.2} for i in range(21)]
        self.assertEqual(len(events(r,.15)),1);self.assertEqual(len(events(r[:-1],.15)),0)
    def test_threshold_strict(self):
        r=[{'stamp':i*.1,'translation_error_m':.15} for i in range(30)]
        self.assertEqual(events(r,.15),[]);self.assertEqual(exposure(r,.15),0)
    def test_data_gap_does_not_bridge_event(self):
        r=[{'stamp':i*.1,'translation_error_m':.2} for i in range(10)]
        r += [{'stamp':3+i*.1,'translation_error_m':.2} for i in range(10)]
        self.assertEqual(events(r,.15),[])
    def test_initial_state_seed_not_exact_backend(self):
        a={'map_base':[0,0,0],'nodes':10,'edges':9};b={'map_base':[.1,0,0],'nodes':11,'edges':10}
        r=initial_state_difference(a,b);self.assertAlmostEqual(r['map_translation_m'],.1);self.assertFalse(r['exact_backend_state_claim'])
    def test_budget_and_failed_id_preservation(self):
        old=protocol.OUT
        with tempfile.TemporaryDirectory(prefix='doc81_test_') as tmp:
            protocol.OUT=Path(tmp);(protocol.OUT/'protocol').mkdir();protocol.create_json(protocol.OUT/'protocol/budget_ledger.json',{'maximum':15,'attempts':[]})
            try:
                protocol.reserve_episode('fail','baseline',{});protocol.update_episode('fail','TECHNICAL_FAILURE')
                with self.assertRaises(RuntimeError):protocol.reserve_episode('fail','baseline',{})
                for i in range(8):protocol.reserve_episode('base'+str(i),'baseline',{})
                with self.assertRaises(RuntimeError):protocol.reserve_episode('too_many_base','baseline',{})
                for i in range(6):protocol.reserve_episode('arm'+str(i),'intervention',{})
                with self.assertRaises(RuntimeError):protocol.reserve_episode('sixteen','intervention',{})
                ledger=json.loads((protocol.OUT/'protocol/budget_ledger.json').read_text());self.assertEqual(len(ledger['attempts']),15);self.assertEqual(ledger['attempts'][0]['status'],'TECHNICAL_FAILURE')
            finally:protocol.OUT=old
    def test_control_does_not_read_gt(self):
        tree=ast.parse((Path(__file__).parent/'driver.py').read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.FunctionDef) and node.name in ('task_move','run_doc81'):
                for child in ast.walk(node):
                    if isinstance(child,ast.Attribute):self.assertNotIn(child.attr,('gt_pose','current_gt_pose','gt_samples'))
    def test_geometry_is_not_primary_metric(self):
        angles=np.linspace(-math.pi/2,math.pi/2,901);ranges=np.minimum(100,1.55/np.maximum(abs(np.sin(angles)),1e-12))
        scan={'ranges':ranges,'angle_min':angles[0],'angle_increment':angles[1]-angles[0],'range_min':0,'range_max':25}
        p=geometry_proxy(scan);self.assertTrue(p['proxy_valid']);self.assertFalse(p['is_karto_matcher_hessian']);self.assertLess(p['translation_ratio'],1e-12)
        self.assertNotIn('translation_error_m',p)
    def test_seeds_are_preplanned_units_not_frames(self):
        self.assertEqual(len(protocol.SEEDS),3);self.assertEqual(len(set(protocol.SEEDS)),3)
        a=protocol.seeded_start('NORMAL_GEOMETRY',protocol.SEEDS[0]);b=protocol.seeded_start('NORMAL_GEOMETRY',protocol.SEEDS[0]);self.assertEqual(a,b)
        self.assertNotEqual(a,protocol.seeded_start('NORMAL_GEOMETRY',protocol.SEEDS[1]))
    def test_initial_only_alignment_cannot_hide_later_error(self):
        from analysis import evaluate_online
        gt=[{'stamp':t,'x':0 if t<3 else 1,'y':0,'theta':0} for t in (1.,1.1,3.)]
        scans=[{'stamp':t,'index':i,'map_base':[0,0,0]} for i,t in enumerate((1.,1.1,3.))]
        r,g=evaluate_online(scans,gt,2.);self.assertEqual(r[-1]['translation_error_m'],1.);self.assertFalse(g['refit_after_task'])
    def test_freeze_cannot_overwrite_existing_failure(self):
        with tempfile.TemporaryDirectory(prefix='doc81_test_') as tmp:
            p=Path(tmp)/'failure.json';protocol.create_json(p,{'status':'FAILED'})
            with self.assertRaises(FileExistsError):protocol.create_json(p,{'status':'SUCCESS'})
            self.assertEqual(json.loads(p.read_text())['status'],'FAILED')

if __name__=='__main__':unittest.main()
