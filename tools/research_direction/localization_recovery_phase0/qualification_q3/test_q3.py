import ast
import copy
import hashlib
import json
import math
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace as NS
import common
from common import OUT,OLD,HERE,WORLD,launch_text,OwnedProcesses
from timestamps import TFHistory,MAP_CHAIN,PendingScans,wall_wait,action_connected
from analysis import make_alignment


def transform(parent,child,stamp,x=0.,yaw=0.):
    return {'parent':parent,'child':child,'stamp':stamp,'translation':[x,0.,0.],
            'quaternion':[0.,0.,math.sin(yaw/2),math.cos(yaw/2)]}


def chain(history,stamp,x=0.):
    for i,(parent,child) in enumerate(zip(MAP_CHAIN,MAP_CHAIN[1:])):
        history.add(transform(parent,child,stamp,x if i==0 else 0.))


def alignment_data():
    scans=[{'index':i,'seq':100+i,'stamp':2.+i*.1,'map_base':[0.,0.,0.]} for i in range(21)]
    gt=[{'stamp':s['stamp'],'x':-28.,'y':-28.,'theta':0.} for s in scans]
    return {'window':{'start':2.,'end':4.,'initialization_completed_ros_s':1.},
            'scans':scans,'gt':gt,'no_task_motion_yet':True}


class Tests(unittest.TestCase):
    def test_stage_resources_nested_and_original_world(self):
        for name in ('map3.world','p3at.inc','hokuyo.inc','floorplan.inc','map3.png'):
            self.assertTrue((WORLD.parent/name).is_file())
        self.assertIn('include "hokuyo.inc"',(WORLD.parent/'p3at.inc').read_text())

    def test_launch_gui_and_no_robot_namespace(self):
        tree=ET.fromstring(launch_text());stage=next(n for n in tree.findall('node') if n.attrib['name']=='Stage')
        self.assertEqual(stage.attrib['args'],str(WORLD))
        self.assertNotIn('-g ',stage.attrib['args']);self.assertNotIn('-u ',stage.attrib['args'])
        self.assertFalse(any(n.attrib.get('ns') for n in tree.findall('node')))

    def test_real_tf_chain_and_namespace_identity(self):
        history=TFHistory();chain(history,1.,2.)
        self.assertEqual(history.resolve(1.)[0],[2.,0.,0.])
        wrong=TFHistory()
        for p,c in zip(MAP_CHAIN,MAP_CHAIN[1:]):wrong.add(transform('/robot/'+p,'/robot/'+c,1.))
        self.assertIsNone(wrong.resolve(1.)[0])

    def test_no_latest_pose_for_missing_time(self):
        history=TFHistory();chain(history,2.)
        value,metadata=history.resolve(1.)
        self.assertIsNone(value);self.assertEqual(metadata['status'],'OUTSIDE_RECORDED_RANGE')

    def test_exact_requested_stamp_and_scan_identity_after_delay(self):
        pending=PendingScans();history=TFHistory();item={'index':17,'seq':481,'stamp':1.}
        pending.add(item,20.);self.assertEqual(pending.drain(history.resolve,20.5),[])
        chain(history,1.,3.);done=pending.drain(history.resolve,20.6)
        self.assertEqual(done[0][0],item);self.assertEqual(done[0][2]['evaluation_stamp'],1.)
        self.assertFalse(done[0][2]['latest_fallback']);self.assertEqual(done[0][1],[3.,0.,0.])

    def test_strict_interpolation_no_outside_extrapolation(self):
        history=TFHistory();history.add(transform('map','offset',1.,0.,math.pi-.01))
        history.add(transform('map','offset',1.1,1.,-math.pi+.01))
        p,metadata=history.resolve(1.05,('map','offset'))
        self.assertAlmostEqual(p[0],.5);self.assertAlmostEqual(abs(p[2]),math.pi)
        self.assertAlmostEqual(metadata['max_span_s'],.1)
        self.assertIsNone(history.resolve(.99,('map','offset'))[0])
        self.assertIsNone(history.resolve(1.11,('map','offset'))[0])

    def test_tf_interpolation_span_boundary(self):
        history=TFHistory();history.add(transform('map','offset',1.));history.add(transform('map','offset',1.15))
        self.assertIsNotNone(history.resolve(1.075,('map','offset'))[0])
        other=TFHistory();other.add(transform('map','offset',1.));other.add(transform('map','offset',1.16))
        self.assertEqual(other.resolve(1.08,('map','offset'))[1]['status'],'TF_BRACKET_TOO_WIDE')

    def test_first_receipt_duplicate_policy(self):
        history=TFHistory();history.add(transform('map','offset',1.,1.));history.add(transform('map','offset',1.,2.))
        self.assertEqual(history.resolve(1.,('map','offset'))[0][0],1.)
        self.assertEqual(history.conflicting_duplicates,1)

    def test_fixed_joint_requires_explicit_static_topic(self):
        history=TFHistory();history.add(transform('base_footprint','base_link',0.),static=True)
        self.assertIsNotNone(history.resolve(8.,('base_footprint','base_link'))[0])
        other=TFHistory();other.add(transform('base_footprint','base_link',0.))
        self.assertIsNone(other.resolve(8.,('base_footprint','base_link'))[0])

    def test_queue_capacity_is_explicit(self):
        pending=PendingScans(capacity=2)
        for i in range(2):self.assertIsNone(pending.add({'index':i,'stamp':1.},0.))
        overflow=pending.add({'index':2,'stamp':1.},0.)
        self.assertEqual(overflow[0]['index'],0);self.assertEqual(len(pending.items),2)

    def test_queue_wall_timeout_explicit_missing(self):
        pending=PendingScans(timeout_s=2.);pending.add({'index':0,'stamp':1.},10.)
        done=pending.drain(TFHistory().resolve,12.)
        self.assertIsNone(done[0][1]);self.assertEqual(done[0][2]['status'],'WALL_QUEUE_TIMEOUT')
        self.assertEqual(len(pending.items),0)

    def test_tf_history_bounded(self):
        history=TFHistory(cache_s=20.,max_per_edge=3)
        for t in (1.,2.,3.,4.):history.add(transform('map','offset',t))
        self.assertEqual(history.times[('map','offset')],[2.,3.,4.])

    def test_wall_clock_timeout_independent_of_ros_clock(self):
        state=[0.]
        def sleep(dt):state[0]+=dt
        with self.assertRaises(TimeoutError):wall_wait(lambda:False,.1,clock=lambda:state[0],sleep=sleep)
        self.assertGreaterEqual(state[0],.1)

    def test_wait_server_failure_exits_if_process_dies(self):
        with self.assertRaises(RuntimeError):wall_wait(lambda:False,30.,alive=lambda:False)

    def test_actual_action_connections_not_just_topic_names(self):
        publisher=NS(impl=NS(has_connection=lambda server:server=='/Navigator'))
        subscriber=NS(impl=NS(connections=[NS(callerid_pub='/Navigator')]))
        ac=NS(last_status_msg=NS(_connection_header={'callerid':'/Navigator'}),pub_goal=publisher,pub_cancel=publisher,
              result_sub=subscriber,feedback_sub=subscriber)
        self.assertTrue(action_connected(NS(action_client=ac)))
        ac.feedback_sub=NS(impl=NS(connections=[]));self.assertFalse(action_connected(NS(action_client=ac)))

    def test_alignment_after_mapping_and_before_motion(self):
        result=make_alignment(alignment_data())
        self.assertEqual(result['alignment_samples'],21);self.assertTrue(result['alignment_frozen_before_motion'])
        self.assertEqual(result['alignment_transform'],[-28.,-28.,0.])
        data=alignment_data();data['window']['initialization_completed_ros_s']=3.
        with self.assertRaises(ValueError):make_alignment(data)

    def test_alignment_cannot_refit_later_motion(self):
        data=alignment_data();expected=make_alignment(data)
        data['scans'].append({'index':999,'seq':999,'stamp':10.,'map_base':[0.,0.,0.]})
        data['gt'].append({'stamp':10.,'x':999.,'y':999.,'theta':1.})
        self.assertEqual(make_alignment(data)['alignment_transform'],expected['alignment_transform'])

    def test_alignment_rejects_motion_and_missing_or_bad_gt(self):
        data=alignment_data();data['no_task_motion_yet']=False
        with self.assertRaises(ValueError):make_alignment(data)
        data=alignment_data();data['gt']=data['gt'][:1]
        with self.assertRaises(ValueError):make_alignment(data)
        data=alignment_data();data['gt'][-1]['x']+=.1
        with self.assertRaises(ValueError):make_alignment(data)

    def test_control_never_reads_gt_or_alignment_transform(self):
        tree=ast.parse((HERE/'driver.py').read_text())
        control=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='execute_goal')
        for node in ast.walk(control):
            if isinstance(node,ast.Attribute):self.assertNotIn(node.attr,('gt','gt_pose','alignment_transform'))
        self.assertNotIn('wait_for_server', (HERE/'driver.py').read_text())

    def test_scan_callback_does_not_block_on_tf(self):
        tree=ast.parse((HERE/'driver.py').read_text())
        scan=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='on_scan')
        for node in ast.walk(scan):
            if isinstance(node,ast.Attribute):self.assertNotIn(node.attr,('waitForTransform','lookupTransform','sleep','wait'))

    def test_stage_spawn_failure_closes_own_lifecycle(self):
        with tempfile.TemporaryDirectory(prefix='doc81_q3_test_') as tmp:
            owned=OwnedProcesses()
            try:
                with self.assertRaises(FileNotFoundError):owned.start(['/missing/doc81_q3_test_executable'],{},Path(tmp)/'fail.log')
            finally:report=owned.close()
            self.assertEqual(report['residual_owned_pids'],[]);self.assertFalse(report['global_kill_used'])

    def test_owned_dummy_process_is_cleaned(self):
        with tempfile.TemporaryDirectory(prefix='doc81_q3_test_') as tmp:
            owned=OwnedProcesses();p=owned.start(['/usr/bin/python3','-c','import time; time.sleep(15)'],{},Path(tmp)/'dummy.log')
            report=owned.close();self.assertIsNotNone(p.poll());self.assertEqual(report['residual_owned_pids'],[])

    def test_navigation_failure_has_log_and_close_paths(self):
        source=(HERE/'driver.py').read_text()
        self.assertIn('driver_failure.json',source);self.assertIn('raw_close_report.json',source)
        self.assertIn('finally:recorder.close()',source);self.assertIn('self.move.cancel_goal()',source)

    def test_unique_reservation_and_immutable_old_budget(self):
        previous_out,previous_old=common.OUT,common.OLD
        with tempfile.TemporaryDirectory(prefix='doc81_q3_test_') as tmp:
            common.OUT=Path(tmp)/'q3';common.OLD=Path(tmp)/'old'
            (common.OUT/'protocol').mkdir(parents=True);(common.OLD/'protocol').mkdir(parents=True)
            path=common.OLD/'protocol/budget_ledger.json';common.create(path,{'attempts':[{}, {}, {}]});before=common.sha(path)
            try:
                common.reserve()
                with self.assertRaises(RuntimeError):common.reserve()
                self.assertEqual(common.sha(path),before)
                self.assertEqual(common.read(common.OUT/'protocol/physical_attempt.json')['cumulative_total'],4)
            finally:common.OUT,common.OLD=previous_out,previous_old

    def test_all_old_attempts_and_budget_still_sealed(self):
        manifest=common.read(OLD/'audit/local_only_capture_manifest.json')
        for row in manifest['files']:self.assertEqual(common.sha(OLD/row['path']),row['sha256'])
        self.assertEqual(len(common.read(OLD/'protocol/budget_ledger.json')['attempts']),3)


if __name__=='__main__':unittest.main()
