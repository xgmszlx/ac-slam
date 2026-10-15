#!/usr/bin/python3
"""Raw acquisition + frozen timed motion. GT callback enqueues only."""
import argparse,json,queue,threading,time
from pathlib import Path
import rospy,rosbag
from sensor_msgs.msg import LaserScan
from nav_msgs.msg import Odometry,OccupancyGrid
from geometry_msgs.msg import Twist
from tf2_msgs.msg import TFMessage
from rosgraph_msgs.msg import Clock,Log
from rtabmap_msgs.msg import OdomInfo,Info,MapData,MapGraph
ap=argparse.ArgumentParser();ap.add_argument('run');a=ap.parse_args();run=Path(a.run)
rospy.init_node('b_signal_collector');q=queue.Queue(maxsize=20000);done=False;counts={};dropped=0;ready=set();headers={};receipts=[]
bag=rosbag.Bag(str(run/'raw.bag'),'w',compression=rosbag.Compression.BZ2)
def cb(m,topic):
 global dropped
 wall=time.monotonic();rt=rospy.Time.now();counts[topic]=counts.get(topic,0)+1
 if topic in ['/scan','/icp/odom','/rtabmap/mapGraph','/rtabmap/grid_map']:ready.add(topic)
 h=getattr(m,'header',None)
 receipts.append(dict(topic=topic,receipt_ros=rt.to_sec(),receipt_wall=wall,stamp_ns=h.stamp.to_nsec() if h else None,caller=getattr(m,'_connection_header',{}).get('callerid')))
 try:q.put_nowait((topic,m,rt))
 except queue.Full:dropped+=1
def writer():
 while not done or not q.empty():
  try:t,m,s=q.get(timeout=.1)
  except queue.Empty:continue
  bag.write(t,m,s);q.task_done()
th=threading.Thread(target=writer);th.start()
types={'/scan':LaserScan,'/icp/odom':Odometry,'/icp/odom_info':OdomInfo,'/wheel/odom':Odometry,'/wheel/odom_native':Odometry,'/base_pose_ground_truth':Odometry,'/tf':TFMessage,'/stage_tf':TFMessage,'/tf_static':TFMessage,'/rtabmap/info':Info,'/rtabmap/mapData':MapData,'/rtabmap/mapGraph':MapGraph,'/rtabmap/grid_map':OccupancyGrid,'/clock':Clock,'/cmd_vel':Twist,'/rosout_agg':Log}
subs=[rospy.Subscriber(t,typ,cb,callback_args=t,queue_size=2000) for t,typ in types.items()]
pub=rospy.Publisher('/cmd_vel',Twist,queue_size=5);wall0=time.monotonic();start=None;events=[];status='WAITING'
while not rospy.is_shutdown() and time.monotonic()-wall0<70:
 now=rospy.Time.now().to_sec()
 if start is None and len(ready)==4:
  start=now;status='EXECUTING';events.append(dict(event='START',stamp=now,wall=time.monotonic()))
 if start is not None:
  elapsed=now-start;cmd=Twist()
  if 5<=elapsed<20:cmd.linear.x=.15
  pub.publish(cmd)
  if elapsed>=25:status='COMPLETED';break
 time.sleep(.04)
for _ in range(3):pub.publish(Twist());time.sleep(.05)
# Graph service acquisition is read-only; no new observations or optimizer changes.
try:
 from rtabmap_msgs.srv import GetMap
 rospy.wait_for_service('/rtabmap/get_map_data',timeout=2)
 srv=rospy.ServiceProxy('/rtabmap/get_map_data',GetMap)
 resp=srv(False,True,False);bag.write('/audit/final_map_data',resp.data,rospy.Time.now())
except Exception as e:events.append(dict(event='FINAL_GRAPH_SERVICE_FAILURE',error=str(e)))
done=True;th.join(10);bag.close()
(run/'receipts.json').write_text(json.dumps(receipts))
(run/'collector.json').write_text(json.dumps(dict(status=status,dropped=dropped,counts=counts,events=events,wall_s=time.monotonic()-wall0),indent=2))
if status!='COMPLETED' or dropped or th.is_alive():raise SystemExit(3)
