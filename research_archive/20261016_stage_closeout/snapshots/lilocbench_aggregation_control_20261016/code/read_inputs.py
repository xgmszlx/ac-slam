from pathlib import Path
import json,csv
import numpy as np,rosbag
p=Path(__file__).resolve().parents[1];b=Path('/home/wcqw/lilocbench_amcl_validation_20261016');rows=[];tf={}
with rosbag.Bag(str(b/'data/lt_changes_0.bag'),'r') as bag:
 for topic,m,record in bag.read_messages(topics=['/tf','/laser_scan_front/scan']):
  if topic=='/tf':
   for x in m.transforms:
    if x.header.frame_id.strip('/')=='odom' and x.child_frame_id.strip('/')=='base_link':
     v=x.transform;tf[x.header.stamp.to_nsec()]=[v.translation.x,v.translation.y,v.translation.z,v.rotation.x,v.rotation.y,v.rotation.z,v.rotation.w]
  else:
   n=len(m.ranges);add_idx=np.arange(0,n,max(1,(n-1)//(91-1)));prob_idx=np.arange(0,n,max(1,int(np.ceil(n/100.))))
   assert n==811 and np.array_equal(add_idx,prob_idx) and len(add_idx)==91
   a=np.asarray(m.ranges,dtype=float)[add_idx];proc=np.where(a<=m.range_min,m.range_max,np.where(a>m.range_max,np.finfo(float).max,a));valid=(proc<m.range_max)&~np.isnan(proc)
   rows.append({'seq':m.header.seq,'stamp_ns':m.header.stamp.to_nsec(),'range_count':n,'physical_slots':len(add_idx),'valid_slots':int(valid.sum()),'range_min':m.range_min,'range_max':m.range_max,'same_actual_indices':True})
assert len(rows)==6540
with (p/'results/input_beam_audit.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
ns=np.array(sorted(tf),dtype=np.int64);poses=np.array([tf[int(t)] for t in ns]);np.savez_compressed(p/'results/odom_tf.npz',stamp_ns=ns,poses=poses)
(p/'audit/physical_beams_before_run.json').write_text(json.dumps({'status':'PASS','scan_count':len(rows),'range_count':811,'physical_indices':list(map(int,add_idx)),'max_beams_add':91,'max_beams_prob':100,'valid_slots_min_max':[min(r['valid_slots'] for r in rows),max(r['valid_slots'] for r in rows)],'evidence':'Fixed source stride formulas plus original raw scan messages; not a new per-beam runtime trace','no_filter_started':True},indent=2));print('Input/beam audit PASS, 6540 scans; odom TF records',len(tf))
