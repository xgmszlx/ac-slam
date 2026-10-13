#!/usr/bin/python3
"""Observation-only Q3 recorder; estimated TF/action state control a fixed goal.

GT is serialized only. A separate ROS-free subprocess computes the initial
alignment from a closed stationary-window file before any task goal is sent.
"""
import json
import math
import os
import subprocess
import threading
import time
from pathlib import Path
import actionlib
import rospy
from actionlib_msgs.msg import GoalStatus
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import LaserScan
from tf2_msgs.msg import TFMessage
from nav2d_navigator.msg import MoveToPosition2DAction,MoveToPosition2DGoal,GetFirstMapAction,GetFirstMapActionResult
from common import OUT,HERE,create,atomic,read,sha
from timestamps import TFHistory,PendingScans,wall_wait,action_connected,wrap


class Recorder:
    def __init__(self):
        self.lock=threading.RLock();self.closed=False;self.stop_worker=threading.Event()
        self.history=TFHistory(max_span=.15,cache_s=20.,max_per_edge=4096)
        self.pending=PendingScans(capacity=200,timeout_s=2.)
        self.scans=[];self.evaluations={};self.gt=[];self.odom=[];self.clock=[];self.mapping_result=None
        self.streams={n:(OUT/'raw'/('%s.jsonl'%n)).open('x') for n in
                      ('scan_stream','scan_tf_evaluation','tf_stream','gt_stream','odom_stream','control_stream','clock_stream')}
        self.readiness={'events':[],'status':'STARTING','clock_basis_for_waits':'time.monotonic wall seconds'}
        self.subscribers=[rospy.Subscriber('/base_scan',LaserScan,self.on_scan,queue_size=200),
            rospy.Subscriber('/tf',TFMessage,self.on_tf,queue_size=500),
            rospy.Subscriber('/tf_static',TFMessage,lambda m:self.on_tf(m,True),queue_size=100),
            rospy.Subscriber('/base_pose_ground_truth',Odometry,self.on_gt,queue_size=200),
            rospy.Subscriber('/odom',Odometry,self.on_odom,queue_size=200),
            rospy.Subscriber('/cmd_vel',Twist,self.on_cmd,queue_size=100),
            rospy.Subscriber('/clock',Clock,self.on_clock,queue_size=200),
            rospy.Subscriber('/GetFirstMap/result',GetFirstMapActionResult,self.on_mapping_result,queue_size=20)]
        self.worker=threading.Thread(target=self.resolve_pending,daemon=True);self.worker.start()
        self.getmap=actionlib.SimpleActionClient('/GetFirstMap',GetFirstMapAction)
        self.move=actionlib.SimpleActionClient('/MoveTo',MoveToPosition2DAction)

    def write(self,name,row):
        self.streams[name].write(json.dumps(row,separators=(',',':'))+'\n')

    def event(self,label,**details):
        row={'stage':label,'wall_monotonic_s':time.monotonic(),'ros_s':rospy.get_time(),**details}
        self.readiness['events'].append(row)
        atomic(OUT/'results/readiness_report.json',self.readiness)
        print(json.dumps(row),flush=True)

    def wait(self,label,predicate,timeout):
        self.event(label+'_WAIT')
        elapsed=wall_wait(predicate,timeout,alive=lambda:not rospy.is_shutdown())
        self.event(label+'_READY',elapsed_wall_s=elapsed)

    def on_scan(self,msg):
        wall=time.monotonic()
        with self.lock:
            if self.closed:return
            record={'index':len(self.scans),'seq':int(msg.header.seq),'stamp':msg.header.stamp.to_sec(),
                    'stamp_ns':msg.header.stamp.to_nsec(),'frame_id':msg.header.frame_id,
                    'scan_received_wall_time':wall,'scan_received_ros_time':rospy.get_time(),
                    'ranges':list(msg.ranges),'angle_min':msg.angle_min,'angle_increment':msg.angle_increment,
                    'range_min':msg.range_min,'range_max':msg.range_max}
            self.write('scan_stream',record);small={k:v for k,v in record.items() if k!='ranges'}
            self.scans.append(small);overflow=self.pending.add(small,wall)
            if overflow:self.finish(overflow[0],None,{'status':'QUEUE_CAPACITY_EXCEEDED'},wall)

    def on_tf(self,msg,static=False):
        received=rospy.get_time();wall=time.monotonic()
        transforms=[{'stamp':t.header.stamp.to_sec(),'parent':t.header.frame_id,'child':t.child_frame_id,
                     'translation':[t.transform.translation.x,t.transform.translation.y,t.transform.translation.z],
                     'quaternion':[t.transform.rotation.x,t.transform.rotation.y,t.transform.rotation.z,t.transform.rotation.w]}
                    for t in msg.transforms]
        with self.lock:
            if self.closed:return
            self.write('tf_stream',{'received':received,'received_wall_monotonic_s':wall,'static_topic':static,'transforms':transforms})
            for t in transforms:self.history.add(t,static)

    def on_gt(self,msg):
        p=msg.pose.pose;q=p.orientation
        row={'stamp':msg.header.stamp.to_sec(),'x':p.position.x,'y':p.position.y,
             'theta':math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))}
        with self.lock:
            if not self.closed:self.gt.append(row);self.write('gt_stream',row)

    def on_odom(self,msg):
        row={'stamp':msg.header.stamp.to_sec(),'vx':msg.twist.twist.linear.x,'wz':msg.twist.twist.angular.z}
        with self.lock:
            if not self.closed:self.odom.append(row);self.write('odom_stream',row)

    def on_cmd(self,msg):
        with self.lock:
            if not self.closed:self.write('control_stream',{'stamp':rospy.get_time(),'wall_monotonic_s':time.monotonic(),'vx':msg.linear.x,'wz':msg.angular.z})

    def on_clock(self,msg):
        row={'sim_s':msg.clock.to_sec(),'wall_monotonic_s':time.monotonic()}
        with self.lock:
            if not self.closed:self.clock.append(row);self.write('clock_stream',row)

    def on_mapping_result(self,msg):
        with self.lock:
            self.mapping_result={'status':int(msg.status.status),'result_stamp':msg.header.stamp.to_sec(),
                                 'received_ros_s':rospy.get_time(),'received_wall_monotonic_s':time.monotonic()}

    def finish(self,item,value,metadata,wall):
        row={**item,'map_base':value,'tf_status':metadata['status'],
             'tf_resolved_wall_time':wall,'tf_interpolation_span':metadata.get('max_span_s'),
             'tf_metadata':metadata,'evaluation_stamp':item['stamp'],'latest_tf_fallback':False}
        self.evaluations[item['index']]=row;self.write('scan_tf_evaluation',row)

    def resolve_pending(self):
        while not self.stop_worker.wait(.02):
            with self.lock:
                for result in self.pending.drain(self.history.resolve,time.monotonic()):self.finish(*result)

    def pacing_ready(self):
        with self.lock:
            if len(self.clock)<20 or not self.scans or not self.gt or not self.odom:return False
            rows=self.clock[-100:];elapsed=rows[-1]['wall_monotonic_s']-rows[0]['wall_monotonic_s']
            if elapsed<2.:return False
            delta=rows[-1]['sim_s']-rows[0]['sim_s'];ratio=delta/elapsed
            if any(b['sim_s']<=a['sim_s'] for a,b in zip(rows,rows[1:])):raise RuntimeError('Clock not strictly increasing')
            if not .25<=ratio<=2.5:raise RuntimeError('GUI pacing outside frozen 0.25--2.5 sim/wall range: '+str(ratio))
            self.readiness['clock_pacing']={'sim_elapsed_s':delta,'wall_elapsed_s':elapsed,'sim_wall_ratio':ratio,'gui':True}
            return True

    def current_estimate(self):
        with self.lock:
            stamp=self.history.latest_common_stamp()
            if stamp is None:return None
            p,meta=self.history.resolve(stamp)
            return None if p is None else (stamp,p,meta)

    def stationary_after(self,initialization):
        with self.lock:
            if not self.odom:return False
            end=self.odom[-1]['stamp'];rows=[r for r in self.odom if end-2.<=r['stamp']<=end]
            return bool(end-2.>initialization and len(rows)>=15 and rows[-1]['stamp']-rows[0]['stamp']>=1.8
                        and all(abs(r['vx'])<.01 and abs(r['wz'])<.01 for r in rows))

    def collect_alignment(self,initialization):
        self.wait('POST_INITIALIZATION_STATIONARY',lambda:self.stationary_after(initialization),30.)
        start=rospy.get_time();end=start+2.
        self.wait('FIXED_STATIC_WINDOW',lambda:rospy.get_time()>end+.2,10.)
        self.wait('STATIC_WINDOW_TF_DRAIN',lambda:all(s['index'] in self.evaluations for s in self.scans if start<=s['stamp']<=end),3.)
        with self.lock:
            samples=[self.evaluations[s['index']] for s in self.scans if start<=s['stamp']<=end]
            truth=[g for g in self.gt if start-.15<=g['stamp']<=end+.15]
            create(OUT/'raw/alignment_input.json',{'window':{'start':start,'end':end,'initialization_completed_ros_s':initialization},
                  'scans':samples,'gt':truth,'no_task_motion_yet':True})
        result=subprocess.run(['/usr/bin/python3',str(HERE/'analysis.py'),'alignment'],capture_output=True,text=True,timeout=10)
        create(OUT/'results/alignment_subprocess.json',{'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr,
               'ros_free_closed_file_evaluator':True})
        if result.returncode:raise RuntimeError('Offline static alignment qualification failed')
        # Navigation never reads GT values or the alignment transform.
        self.event('ALIGNMENT_FROZEN_BEFORE_TASK',report_sha256=sha(OUT/'results/gt_alignment_report.json'))
        return start

    def execute_goal(self,qualification_start):
        estimate=self.current_estimate()
        if estimate is None:raise RuntimeError('Current estimated map pose unavailable')
        _,origin,_=estimate;c,s=math.cos(origin[2]),math.sin(origin[2])
        target=[origin[0]+2.*c,origin[1]+2.*s,origin[2]]
        goal=MoveToPosition2DGoal();goal.header.frame_id='map';goal.header.stamp=rospy.Time.now()
        goal.target_pose.x,goal.target_pose.y,goal.target_pose.theta=target;goal.target_distance=.25;goal.target_angle=.1
        nav={'qualification_record_start_ros_s':qualification_start,'task_start_ros_s':rospy.get_time(),
             'task_goal_wall_monotonic_s':time.monotonic(),'origin_map_base':origin,'target_map_base':target,
             'goal_distance_m':2.,'control_inputs':['estimated map TF','frozen relative goal','action status'],
             'gt_online_navigation_input':False,'alignment_frozen_before_goal':(OUT/'results/gt_alignment_report.json').is_file()}
        atomic(OUT/'results/navigation_report.json',nav)
        self.move.send_goal(goal)
        try:wall_wait(lambda:self.move.get_state() in (2,3,4,5,8,9),120.,alive=lambda:not rospy.is_shutdown())
        except BaseException:
            self.move.cancel_goal();raise
        nav.update(action_state=int(self.move.get_state()),action_status_text=self.move.get_goal_status_text(),
                   task_end_ros_s=rospy.get_time(),task_end_wall_monotonic_s=time.monotonic())
        atomic(OUT/'results/navigation_report.json',nav)
        if nav['action_state']!=GoalStatus.SUCCEEDED:raise RuntimeError('MoveTo did not succeed')
        self.wait('TASK_STOPPED',lambda:self.stationary_after(nav['task_end_ros_s']),10.)
        nav['task_end_ros_s']=rospy.get_time();nav['task_end_wall_monotonic_s']=time.monotonic()
        nav['completed']=True;atomic(OUT/'results/navigation_report.json',nav)

    def run(self):
        self.wait('NATIVE_CLOCK_SCAN_GT_ODOM',self.pacing_ready,30.)
        self.wait('GET_FIRST_MAP_ACTION',lambda:action_connected(self.getmap),30.)
        self.event('START_MAPPING_REQUEST')
        result=subprocess.run(['rosservice','call','/StartMapping','{}'],capture_output=True,text=True,timeout=10)
        create(OUT/'results/start_mapping_service.json',{'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        if result.returncode or 'success: True' not in result.stdout:raise RuntimeError('StartMapping request failed')
        self.wait('GET_FIRST_MAP_RESULT',lambda:self.mapping_result is not None,120.)
        if self.mapping_result['status']!=3:raise RuntimeError('GetFirstMap unsuccessful')
        self.event('INITIALIZATION_COMPLETE',result=self.mapping_result)
        self.wait('REAL_MAP_BASE_CHAIN',lambda:self.current_estimate() is not None,10.)
        self.wait('MOVE_TO_CONNECTED',lambda:action_connected(self.move),30.)
        self.readiness['move_to_connected']=True
        start=self.collect_alignment(self.mapping_result['received_ros_s'])
        self.execute_goal(start)
        self.readiness['status']='COMPLETED';self.event('SHORT_NAVIGATION_COMPLETE')

    def close(self):
        for subscriber in self.subscribers:subscriber.unregister()
        self.stop_worker.set();self.worker.join(3)
        with self.lock:
            for item,_ in self.pending.items:self.finish(item,None,{'status':'SHUTDOWN_UNRESOLVED'},time.monotonic())
            self.pending.items.clear();self.closed=True
            for stream in self.streams.values():stream.flush();stream.close()
        create(OUT/'results/raw_close_report.json',{'all_files_closed':all(f.closed for f in self.streams.values()),
             'received_native_scans':len(self.scans),'resolved_or_explicit_missing':len(self.evaluations),
             'worker_joined':not self.worker.is_alive(),'queue_capacity':200,'queue_timeout_wall_s':2.})


if __name__=='__main__':
    rospy.init_node('doc81_q3_recorder');recorder=Recorder();success=False
    try:recorder.run();success=True
    except BaseException as exc:
        # Fresh, private master: cancel only this qualification's actions.
        recorder.move.cancel_all_goals();recorder.getmap.cancel_all_goals()
        recorder.readiness['status']='FAILED';recorder.event('QUALIFICATION_DRIVER_FAILURE',error=str(exc))
        atomic(OUT/'results/driver_failure.json',{'error':str(exc),'ros_s':rospy.get_time(),'wall_monotonic_s':time.monotonic()})
    finally:recorder.close()
    raise SystemExit(0 if success else 1)
