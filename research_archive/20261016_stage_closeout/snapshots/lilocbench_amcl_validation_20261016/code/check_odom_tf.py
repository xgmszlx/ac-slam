from pathlib import Path
import rosbag,json
p=Path(__file__).resolve().parents[1];out={}
for seq in ['static_0','lt_changes_0']:
 od={};tf={}
 with rosbag.Bag(str(p/'data'/(seq+'.bag'))) as b:
  for topic,m,t in b.read_messages(topics=['/dingo_velocity_controller/odom','/tf']):
   if topic=='/dingo_velocity_controller/odom':
    x=m.pose.pose;od[m.header.stamp.to_nsec()]=[x.position.x,x.position.y,x.position.z,x.orientation.x,x.orientation.y,x.orientation.z,x.orientation.w]
   else:
    for x in m.transforms:
     if x.header.frame_id=='odom' and x.child_frame_id=='base_link':
      v=x.transform;tf[x.header.stamp.to_nsec()]=[v.translation.x,v.translation.y,v.translation.z,v.rotation.x,v.rotation.y,v.rotation.z,v.rotation.w]
 common=set(od)&set(tf);error=max(max(abs(a-b) for a,b in zip(od[k],tf[k])) for k in common)
 out[seq]={'odom_stamps':len(od),'TF_stamps':len(tf),'exact_stamp_pairs':len(common),'max_pose_element_difference':error,'same_wheel_pose_values':error<1e-12}
 assert error<1e-12
(p/'audit/odom_tf_consistency.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
