from pathlib import Path
import json,hashlib
import rosbag,numpy as np
from decimal import Decimal
p=Path(__file__).resolve().parents[1];b=Path('/home/wcqw/lilocbench_amcl_validation_20261016');pro=json.loads((p/'protocol/design_frozen.json').read_text());records=[]
for seq in ['static_0','lt_changes_0']:
 gtfile=b/'data/gt'/seq/'gt_poses.txt';line=next(x for x in gtfile.read_text().splitlines() if x and not x.startswith('#'));gt0ns=int(Decimal(line.split()[0])*10**9)
 frames=[];ex=[]
 with rosbag.Bag(str(b/'data'/f'{seq}.bag'),'r') as bag:
  for topic,m,t in bag.read_messages(topics=['/laser_scan_front/scan','/tf']):
   if topic=='/laser_scan_front/scan':
    ns=m.header.stamp.to_nsec()
    if ns>gt0ns+10*10**9:break
    if ns>=gt0ns:frames.append((m,t.to_nsec()))
   else:
    for x in m.transforms:
     if x.header.frame_id.strip('/')=='base_link' and x.child_frame_id.strip('/')=='scan_front_link':
      a=x.transform;ex.append([a.translation.x,a.translation.y,a.translation.z,a.rotation.x,a.rotation.y,a.rotation.z,a.rotation.w])
 assert ex and np.max(np.ptp(np.asarray(ex),axis=0))<1e-12
 for target in pro['targets_s']:
  m,rec=min(frames,key=lambda a:(abs(a[0].header.stamp.to_nsec()-gt0ns-target*10**9),a[0].header.stamp.to_nsec()))
  stem=f'{seq}_t{target:02d}';ns=m.header.stamp.to_nsec();meta={'id':stem,'sequence':seq,'target_s':target,'gt0_ns':gt0ns,'scan_stamp_ns':ns,'record_stamp_ns':rec,'actual_relative_s':(ns-gt0ns)/1e9,'seq':m.header.seq,'frame':m.header.frame_id,'count':len(m.ranges),'angle_min':m.angle_min,'angle_increment':m.angle_increment,'range_min':m.range_min,'range_max':m.range_max,'time_increment':m.time_increment,'scan_time':m.scan_time,'laser_in_base_xyz_xyzw':ex[0],'header_vs_target_delta_s':(ns-gt0ns)/1e9-target,'source_sha256':hashlib.sha256((b/'data'/f'{seq}.bag').read_bytes()).hexdigest()}
  np.savez_compressed(p/'data'/f'{stem}.npz',ranges=np.array(m.ranges,dtype=np.float32))
  records.append(meta)
(p/'data/scans.json').write_text(json.dumps(records,indent=2));print(json.dumps([{k:r[k] for k in ['id','seq','scan_stamp_ns','actual_relative_s']} for r in records],indent=2))
