#!/usr/bin/env python3
"""Private-master collector and frozen timed controller. GT is recorded, never read by control."""
import argparse,json,queue,threading,time
from pathlib import Path
import rospy,rosbag
from sensor_msgs.msg import LaserScan
from nav_msgs.msg import Odometry,OccupancyGrid
from geometry_msgs.msg import PoseWithCovarianceStamped,Twist
from tf2_msgs.msg import TFMessage
from std_msgs.msg import String
from rosgraph_msgs.msg import Clock,Log
from safe_and_robust_lidar_map_update.msg import ChangedCells

ap=argparse.ArgumentParser();ap.add_argument('run');ap.add_argument('--case',required=True);ap.add_argument('--duration',type=float,required=True);args=ap.parse_args()
run=Path(args.run);rospy.init_node('audit_collector',anonymous=False)
q=queue.Queue(maxsize=20000);dropped=0;last_pose=None;last_scan=None;last_odom=None;counts={};done=False
bag=rosbag.Bag(str(run/'raw.bag'),'w',compression=rosbag.Compression.BZ2)
def cb(msg,topic):
    global dropped,last_pose,last_scan,last_odom
    counts[topic]=counts.get(topic,0)+1
    if topic=='/amcl_pose':last_pose=msg
    if topic=='/scan':last_scan=msg
    if topic=='/odom':last_odom=msg
    # Ground-truth callback only enqueues its raw message.
    try:q.put_nowait((topic,msg,rospy.Time.now()))
    except queue.Full:dropped+=1
def writer():
    while not done or not q.empty():
        try:topic,msg,t=q.get(timeout=.1)
        except queue.Empty:continue
        bag.write(topic,msg,t);q.task_done()
thread=threading.Thread(target=writer);thread.start()
topics={'/scan':LaserScan,'/odom':Odometry,'/base_pose_ground_truth':Odometry,'/tf':TFMessage,'/tf_static':TFMessage,'/amcl_pose':PoseWithCovarianceStamped,'/prior_map':OccupancyGrid,'/processed_map':OccupancyGrid,'/changed_cells':ChangedCells,'/author_audit':String,'/initialpose':PoseWithCovarianceStamped,'/cmd_vel':Twist,'/clock':Clock,'/rosout_agg':Log}
subs=[rospy.Subscriber(t,typ,cb,callback_args=t,queue_size=2000) for t,typ in topics.items()]
pub=rospy.Publisher('/teleop_cmd_vel',Twist,queue_size=5);initial=rospy.Publisher('/initialpose',PoseWithCovarianceStamped,queue_size=2)
events=[];wall0=time.monotonic();start=None;injected=False;status='WAITING_FOR_LOCALIZATION'
while not rospy.is_shutdown() and time.monotonic()-wall0<90:
    now=rospy.Time.now().to_sec()
    if start is None and now>0 and last_pose is not None and last_scan is not None and last_odom is not None:
        start=now;events.append(dict(event='START',stamp=now));status='EXECUTING'
    if start is not None:
        elapsed=now-start
        cmd=Twist()
        if 8<=elapsed<28:cmd.linear.x=.15
        pub.publish(cmd)
        if args.case in ['S1','S3'] and not injected and elapsed>=16:
            p=PoseWithCovarianceStamped();p.header.stamp=rospy.Time.now();p.header.frame_id='map';p.pose.pose=last_pose.pose.pose
            # Copy serialized message first: don't mutate recorded observation.
            import copy
            p.pose.pose=copy.deepcopy(last_pose.pose.pose);p.pose.pose.position.x+=1.5
            p.pose.covariance[0]=p.pose.covariance[7]=.0025;p.pose.covariance[35]=.0004
            initial.publish(p);events.append(dict(event='POSE_ERROR_INJECTION',stamp=now,pose=[p.pose.pose.position.x,p.pose.pose.position.y]));injected=True
        if elapsed>=args.duration:status='COMPLETED';break
    time.sleep(.05)
for _ in range(3):pub.publish(Twist());time.sleep(.05)
done=True;thread.join(timeout=10)
if thread.is_alive():raise RuntimeError('Bag writer did not drain')
bag.close();(run/'collector.json').write_text(json.dumps(dict(status=status,dropped=dropped,counts=counts,events=events,wall_elapsed=time.monotonic()-wall0),indent=2))
if status!='COMPLETED' or dropped:raise SystemExit(3)
