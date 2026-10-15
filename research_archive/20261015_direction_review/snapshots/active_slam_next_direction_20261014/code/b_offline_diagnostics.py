"""No ROS startup. Timing and constraint diagnostics on the second retained bag."""
import json,math,csv
from pathlib import Path
import numpy as np,rosbag
from time_geometry import compose,inverse,wrap
R=Path(__file__).resolve().parents[1];run=R/'results/B_technical_02'
receipts=json.loads((run/'receipts.json').read_text());wall={};callers={}
for r in receipts:
 callers.setdefault(r['topic'],set()).add(r['caller'])
 if r['stamp_ns'] is not None:wall[(r['topic'],r['stamp_ns'])]=r['receipt_wall']
lat=[wall[('/icp/odom_info',s)]-v for (t,s),v in wall.items() if t=='/scan' and ('/icp/odom_info',s) in wall]
scans=set(s for t,s in wall if t=='/scan');infos=set(s for t,s in wall if t=='/icp/odom_info')
gt={};nodes={};links={};tf_edges={};odom=[];mapstamps=[]
def pose(p):
 q=p.orientation;return [p.position.x,p.position.y,math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))]
with rosbag.Bag(str(run/'raw.bag')) as b:
 for topic,m,t in b.read_messages():
  if topic=='/base_pose_ground_truth':gt[m.header.stamp.to_nsec()]=pose(m.pose.pose)
  elif topic in ['/rtabmap/mapData','/audit/final_map_data']:
   for n in m.nodes:nodes[n.id]=int(round(n.stamp*1e9))
   for l in m.graph.links:links[(l.fromId,l.toId,l.type)]=l
  elif topic=='/icp/odom':odom.append(m.header.stamp.to_sec())
  elif topic=='/tf':
   for x in m.transforms:tf_edges.setdefault(x.header.frame_id+'->'+x.child_frame_id,[]).append(x.header.stamp.to_sec())
rows=[]
for (a,b,k),l in sorted(links.items()):
 sa=nodes.get(a);sb=nodes.get(b)
 if sa not in gt or sb not in gt:continue
 tru=compose(inverse(gt[sa]),gt[sb]);q=l.transform.rotation;p=[l.transform.translation.x,l.transform.translation.y,math.atan2(2*q.w*q.z,1-2*q.z*q.z)]
 rows.append(dict(from_id=a,to_id=b,type=k,from_stamp_ns=sa,to_stamp_ns=sb,GT_relative_error_m=float(np.linalg.norm(np.array(p[:2])-tru[:2])),GT_relative_yaw_error=abs(wrap(p[2]-tru[2])),information_finite=bool(np.isfinite(l.information).all())))
with (run/'constraint_gt.csv').open('x') as f:
 if rows:w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
result=dict(scan_to_odominfo_latency_wall_s_quantiles=np.quantile(lat,[0,.5,.9,1]).tolist(),missing_odominfo_scan_stamps_s=sorted(s/1e9 for s in scans-infos),odom_stamp_gap_quantiles=np.quantile(np.diff(sorted(odom)),[0,.5,.9,1]).tolist(),
 actual_topic_callers={k:sorted(v,key=str) for k,v in callers.items()},edge_GT_evaluated=len(rows),edge_error_quantiles=np.quantile([r['GT_relative_error_m'] for r in rows],[0,.5,.9,1]).tolist() if rows else None,
 edge_types={str(k):dict(count=sum(r['type']==k for r in rows),max_error_m=max(r['GT_relative_error_m'] for r in rows if r['type']==k)) for k in set(r['type'] for r in rows)},
 boundary='Caller identities preserved in receipts by topic, not in bag connection headers. Exact per-TF-message sender cannot be independently reconstructed from bag; no multiple-parent topology observed. Source processData lockTry drops scans when mainLoop holds dataMutex; frontend ingress counters absent, so exact missing-scan cause UNRESOLVED. No missing output is counted as ICP rejection.')
(run/'offline_diagnostics.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
