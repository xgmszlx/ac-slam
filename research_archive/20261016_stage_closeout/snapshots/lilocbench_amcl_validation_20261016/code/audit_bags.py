"""Read-only ROS1 bag audit; never publishes or opens an estimator."""
import rosbag,json,math,sys,hashlib
from pathlib import Path
from collections import defaultdict
p=Path(__file__).resolve().parents[1]
for seq in sys.argv[1:]:
 path=p/'data'/f'{seq}.bag'; stats={};tf_static={};tf_edges={};odom={};scans={};n=0
 with rosbag.Bag(str(path),'r') as b:
  info=b.get_type_and_topic_info()
  for top,ti in info.topics.items():stats[top]={'type':ti.msg_type,'count':ti.message_count,'first_header_ns':None,'last_header_ns':None,'nonincreasing':0}
  for top,msg,bt in b.read_messages():
   n+=1;s=stats[top]
   if hasattr(msg,'header'):
    stamp=msg.header.stamp.to_nsec()
    if s['last_header_ns'] is not None and stamp<=s['last_header_ns']:s['nonincreasing']+=1
    if s['first_header_ns'] is None:s['first_header_ns']=stamp
    s['last_header_ns']=stamp
   if msg._type=='sensor_msgs/LaserScan':
    if top not in scans:
     scans[top]={'frame_id':msg.header.frame_id,'angle_min':msg.angle_min,'angle_max':msg.angle_max,'angle_increment':msg.angle_increment,'time_increment':msg.time_increment,'scan_time':msg.scan_time,'range_min':msg.range_min,'range_max':msg.range_max,'range_count':len(msg.ranges),'seq_first':msg.header.seq,'valid_beams_total':0,'all_beams_total':0}
    scans[top]['valid_beams_total']+=sum(math.isfinite(x) and msg.range_min<=x<msg.range_max for x in msg.ranges);scans[top]['all_beams_total']+=len(msg.ranges)
   if msg._type=='nav_msgs/Odometry':
    if top not in odom:odom[top]={'frame_id':msg.header.frame_id,'child_frame_id':msg.child_frame_id,'max_abs_vx':0.,'max_abs_vy':0.,'max_abs_wz':0.}
    for field,value in [('max_abs_vx',msg.twist.twist.linear.x),('max_abs_vy',msg.twist.twist.linear.y),('max_abs_wz',msg.twist.twist.angular.z)]:odom[top][field]=max(odom[top][field],abs(value))
   if msg._type=='tf2_msgs/TFMessage':
    for x in msg.transforms:
     key=x.header.frame_id+' -> '+x.child_frame_id
     if top.endswith('tf_static'):
      v=x.transform;value={'xyz':[v.translation.x,v.translation.y,v.translation.z],'xyzw':[v.rotation.x,v.rotation.y,v.rotation.z,v.rotation.w]}
      if key in tf_static and tf_static[key]!=value:raise ValueError('conflicting static transform '+key)
      tf_static[key]=value
     else:
      if key not in tf_edges:tf_edges[key]={'first_stamp_ns':x.header.stamp.to_nsec(),'last_stamp_ns':x.header.stamp.to_nsec(),'count':0,'first_xyz':[x.transform.translation.x,x.transform.translation.y,x.transform.translation.z],'first_xyzw':[x.transform.rotation.x,x.transform.rotation.y,x.transform.rotation.z,x.transform.rotation.w],'max_transform_element_delta':0.}
      tf_edges[key]['last_stamp_ns']=x.header.stamp.to_nsec();tf_edges[key]['count']+=1
      vals=[x.transform.translation.x,x.transform.translation.y,x.transform.translation.z,x.transform.rotation.x,x.transform.rotation.y,x.transform.rotation.z,x.transform.rotation.w]
      tf_edges[key]['max_transform_element_delta']=max(tf_edges[key]['max_transform_element_delta'],max(abs(a-b) for a,b in zip(vals,tf_edges[key]['first_xyz']+tf_edges[key]['first_xyzw'])))
  out={'sequence':seq,'bag_bytes':path.stat().st_size,'bag_start':b.get_start_time(),'bag_end':b.get_end_time(),'messages_read':n,'topics':stats,'scans':scans,'odometry':odom,'tf_static':tf_static,'tf_dynamic':tf_edges,'status':'COMPLETE_READ_NO_ROS_RUN'}
 out['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
 (p/'audit'/f'{seq}_bag.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
