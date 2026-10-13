#!/usr/bin/python3
"""Doc81 native continuous capture. GT callback records only; never controls motion."""
import argparse,importlib.util,json,math,sys,time
from pathlib import Path
import actionlib,rospy,tf
from nav2d_navigator.msg import MoveToPosition2DAction,MoveToPosition2DGoal
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from tf2_msgs.msg import TFMessage
ROOT=Path(__file__).resolve().parents[3]
frozen=ROOT/'tools/realizability_pilot/doc79_sync_validation/driver.py'
spec=importlib.util.spec_from_file_location('frozen_doc79_driver',str(frozen));mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
from metrics import wrap

class Driver(mod.ContinuousRevisitDriver):
    def __init__(self,spec,output):
        super().__init__(spec,output)
        self.extra={n:open(str(Path(output)/(n+'.jsonl')),'x') for n in ('tf_stream','odom_stream','control_stream')}
        rospy.Subscriber('/tf',TFMessage,self.record_tf,queue_size=500)
        rospy.Subscriber('/odom',Odometry,self.record_odom,queue_size=200)
        rospy.Subscriber('/cmd_vel',Twist,self.record_cmd,queue_size=100)
    def write_extra(self,name,row):
        with self.lock:
            f=self.extra.get(name)
            if f is not None:f.write(json.dumps(row,separators=(',',':'))+'\n')
    def record_tf(self,msg):
        self.write_extra('tf_stream',{'received':float(rospy.get_time()),'transforms':[
          {'stamp':t.header.stamp.to_sec(),'parent':t.header.frame_id,'child':t.child_frame_id,
           'translation':[t.transform.translation.x,t.transform.translation.y,t.transform.translation.z],
           'quaternion':[t.transform.rotation.x,t.transform.rotation.y,t.transform.rotation.z,t.transform.rotation.w]} for t in msg.transforms]})
    def record_odom(self,msg):
        p=msg.pose.pose;self.write_extra('odom_stream',{'stamp':msg.header.stamp.to_sec(),'x':p.position.x,'y':p.position.y,
          'theta':mod.yaw_from_quaternion(p.orientation),'vx':msg.twist.twist.linear.x,'wz':msg.twist.twist.angular.z})
    def record_cmd(self,msg):
        self.write_extra('control_stream',{'stamp':float(rospy.get_time()),'vx':msg.linear.x,'vy':msg.linear.y,'wz':msg.angular.z})
    def close_stream(self):
        super().close_stream()
        if hasattr(self,'extra'):
            with self.lock:
                for f in self.extra.values():
                    if f is not None:f.close()
                self.extra={}
    def resolve_tf(self,parent,child,stamp):
        try:
            self.tf_listener.waitForTransform(parent,child,rospy.Time(stamp),rospy.Duration(.12))
            t,q=self.tf_listener.lookupTransform(parent,child,rospy.Time(stamp))
            return [t[0],t[1],mod.yaw_from_tf_rotation(q)],0.
        except tf.Exception:return None,None

    def task_move(self,client,goal_pose,label):
        """No GT read, tolerance, abort, or target used on this control path."""
        goal=MoveToPosition2DGoal();goal.header.frame_id='map';goal.header.stamp=rospy.Time.now()
        goal.target_pose.x,goal.target_pose.y,goal.target_pose.theta=goal_pose
        goal.target_distance=.25;goal.target_angle=.1
        start=float(rospy.get_time());client.send_goal(goal)
        finished=client.wait_for_result(rospy.Duration(150.))
        if not finished:client.cancel_goal()
        rospy.sleep(.5)  # physical settling only; graph drain still uses the verified watermark service
        row={'label':label,'goal_map_base':goal_pose,'start':start,'end':float(rospy.get_time()),
             'finished':bool(finished),'action_state':int(client.get_state()),'map_pose_after':self.current_tf_pose()}
        self.moves.append(row);self.write_json('task_goals.json',self.moves)
        if not finished or client.get_state()!=3:raise RuntimeError('navigation failed: '+label)
        return row

    def run_doc81(self):
        rospy.set_param('/doc81/recorder_ready',True)
        while not rospy.get_param('/doc81/start_gate',False):time.sleep(.1)
        origin=self.current_tf_pose()
        if origin is None:raise RuntimeError('initial map pose unavailable')
        client=actionlib.SimpleActionClient('/MoveTo',MoveToPosition2DAction)
        if not client.wait_for_server(rospy.Duration(30.)):raise RuntimeError('MoveTo unavailable')
        self.boundary_export('G_task_start')
        start=float(rospy.get_time());self.write_json('phase_markers.json',{'task_start':start,'origin_map_base':origin})
        success=False;reason=None
        try:
            # Stage odom / initial mapper x axis is the frozen task axis.
            # Do not rotate the whole corridor task by bootstrap turn overshoot.
            axis=0.;c,s=math.cos(axis),math.sin(axis)
            for i,(x,y,yaw) in enumerate(self.spec['route']):
                goal=[origin[0]+c*x-s*y,origin[1]+s*x+c*y,wrap(axis+yaw)]
                self.task_move(client,goal,'route_%d'%i)
                self.boundary_export('G_waypoint_%d'%i)
            success=True
        except Exception as exc:reason=str(exc)
        finally:
            end=float(rospy.get_time());self.boundary_export('G_final')
            self.write_json('episode_result.json',{'status':'SUCCEEDED' if success else 'NAVIGATION_FAILED',
              'reason':reason,'task_start':start,'task_end':end,'origin_map_base':origin,'moves':self.moves,
              'online_control_inputs':['map TF','fixed route','MoveTo result'],'gt_used_for_control':False})
            self.close_stream()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--spec',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    rospy.init_node('doc81_recorder');d=Driver(json.loads(Path(a.spec).read_text()),a.output)
    try:d.run_doc81()
    except Exception as e:
        d.write_json('driver_failure.json',{'error':str(e),'sim_time':float(rospy.get_time())});d.close_stream();raise
