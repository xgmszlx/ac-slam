#!/usr/bin/python3
"""Observe official ROS topics only. No GT, no initialpose, no estimator services."""
import rospy,json,sys,time,threading,math,signal,os
from pathlib import Path
from geometry_msgs.msg import PoseWithCovarianceStamped,PoseArray
from sensor_msgs.msg import LaserScan
from nav_msgs.msg import Odometry
from tf2_msgs.msg import TFMessage
p=Path(sys.argv[1]);lock=threading.Lock();counts={};last_cloud=-1.;callers={};parents={};closing=False
f=(p/'observations.jsonl').open('w');tr=(p/'trajectory.txt').open('w')
def emit(kind,msg,obj):
 global closing
 with lock:
  if closing:return
  counts[kind]=counts.get(kind,0)+1
  caller=getattr(msg,'_connection_header',{}).get('callerid','UNKNOWN')
  callers.setdefault(kind,set()).add(caller)
  obj.update(kind=kind,receipt_wall=time.monotonic(),ros_now=rospy.Time.now().to_nsec(),caller=caller)
  f.write(json.dumps(obj,separators=(',',':'))+'\n')
def pose(msg):
 v=msg.pose.pose;q=v.orientation
 with lock:
  if closing:return
  tr.write('%d.%09d %.12g %.12g %.12g %.12g %.12g %.12g %.12g\n'%(msg.header.stamp.secs,msg.header.stamp.nsecs,v.position.x,v.position.y,v.position.z,q.x,q.y,q.z,q.w));tr.flush()
 emit('pose',msg,{'stamp_ns':msg.header.stamp.to_nsec(),'frame':msg.header.frame_id,'xy':[v.position.x,v.position.y],'xyzw':[q.x,q.y,q.z,q.w],'covariance':list(msg.pose.covariance)})
def cloud(msg):
 global last_cloud
 now=msg.header.stamp.to_sec()
 if now-last_cloud<1:return
 last_cloud=now
 emit('particles_sampled_1Hz',msg,{'stamp_ns':msg.header.stamp.to_nsec(),'frame':msg.header.frame_id,'particles':[[a.position.x,a.position.y,a.orientation.z,a.orientation.w] for a in msg.poses]})
def scan(msg):emit('scan_received',msg,{'stamp_ns':msg.header.stamp.to_nsec(),'seq':msg.header.seq})
def odom(msg):emit('odom_received',msg,{'stamp_ns':msg.header.stamp.to_nsec()})
def tf(msg):
 arr=[]
 for x in msg.transforms:
  if x.child_frame_id in ['odom','base_link','scan_front_link']:
   v=x.transform
   arr.append({'parent':x.header.frame_id,'child':x.child_frame_id,'stamp_ns':x.header.stamp.to_nsec(),'xyz':[v.translation.x,v.translation.y,v.translation.z],'xyzw':[v.rotation.x,v.rotation.y,v.rotation.z,v.rotation.w]})
 if arr:emit('tf',msg,{'transforms':arr})
rospy.init_node('amcl_observer',anonymous=False)
subs=[rospy.Subscriber('/amcl_pose',PoseWithCovarianceStamped,pose,queue_size=1000),rospy.Subscriber('/particlecloud',PoseArray,cloud,queue_size=1000),rospy.Subscriber(os.environ.get('AMCL_AUDIT_SCAN_TOPIC','/laser_scan_front/scan'),LaserScan,scan,queue_size=20000),rospy.Subscriber('/dingo_velocity_controller/odom',Odometry,odom,queue_size=20000),rospy.Subscriber('/tf',TFMessage,tf,queue_size=20000)]
(p/'collector_ready.json').write_text(json.dumps({'wall':time.time(),'subscribes':[s.resolved_name for s in subs],'GT_access':False}))
rospy.spin()
for s in subs:s.unregister()
with lock:
 closing=True;f.flush();tr.flush();f.close();tr.close()
(p/'collector_summary.json').write_text(json.dumps({'counts':counts,'callers':{k:sorted(v) for k,v in callers.items()},'clean_closed':True},indent=2))
