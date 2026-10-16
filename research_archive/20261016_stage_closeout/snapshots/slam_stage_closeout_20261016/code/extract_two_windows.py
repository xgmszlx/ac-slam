from pathlib import Path
import numpy as np,json,rosbag
p=Path(__file__).resolve().parents[1];b=Path('/home/wcqw/lilocbench_amcl_validation_20261016');a=Path('/home/wcqw/lilocbench_aggregation_control_20261016');spec=json.loads((p/'protocol/scope_frozen.json').read_text());gt=np.loadtxt(b/'data/gt/lt_changes_0/gt_poses.txt');gt0=gt[0,0];ev=json.loads((a/'results/A0_91_R0/sensor_update_events.json').read_text());selected={};register=[]
for k,w in enumerate(spec['windows'],1):
 ids=[r for r in ev if w['start_s']<=r['stamp_ns']/1e9-gt0<=w['end_s']];assert len(ids)>=3
 middle=min(ids,key=lambda r:abs(r['stamp_ns']/1e9-gt0-(w['start_s']+w['end_s'])/2));show={ids[0]['stamp_ns'],middle['stamp_ns'],ids[-1]['stamp_ns']}
 for r in ids:selected[r['stamp_ns']]=dict(r,window=k,display=r['stamp_ns'] in show)
 register.append({'window':k,'bounds':w,'exact_sensor_update_count':len(ids),'display_stamps':sorted(show)})
scans=[];ext=None
with rosbag.Bag(str(b/'data/lt_changes_0.bag'),'r') as bag:
 for topic,m,t in bag.read_messages(topics=['/laser_scan_front/scan','/tf']):
  if topic=='/tf' and ext is None:
   for x in m.transforms:
    if x.header.frame_id.strip('/')=='base_link' and x.child_frame_id.strip('/')=='scan_front_link':
     v=x.transform;ext=[v.translation.x,v.translation.y,v.translation.z,v.rotation.x,v.rotation.y,v.rotation.z,v.rotation.w]
  elif topic=='/laser_scan_front/scan' and m.header.stamp.to_nsec() in selected:
   r=selected[m.header.stamp.to_nsec()];assert r['seq']==m.header.seq
   ident=f"w{r['window']}_{r['stamp_ns']}";np.savez_compressed(p/'data'/f'{ident}.npz',ranges=np.asarray(m.ranges,dtype=np.float32))
   scans.append(dict(r,id=ident,sequence='lt_changes_0',relative_s=r['stamp_ns']/1e9-gt0,range_count=len(m.ranges),range_min=m.range_min,range_max=m.range_max,angle_min=m.angle_min,angle_increment=m.angle_increment,scan_time=m.scan_time,time_increment=m.time_increment,laser_in_base_xyz_xyzw=ext))
assert len(scans)==len(selected) and ext is not None
(p/'data/scans.json').write_text(json.dumps(scans,indent=2));(p/'protocol/window_scan_register.json').write_text(json.dumps(register,indent=2));print(register,'scan_count',len(scans))
