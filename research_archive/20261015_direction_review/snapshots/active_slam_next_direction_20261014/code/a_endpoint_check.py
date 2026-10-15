"""Existing scans reprojected offline; diagnostics, not replacement map metric."""
import json,math,csv
from pathlib import Path
import numpy as np,rosbag
R=Path(__file__).resolve().parents[1];out=R/'results/A_residual';z=np.load(out/'B1_attribution.npz');fp=z['false'];truth=z['truth'];h,w=truth.shape
scans={};gt={};audit=[];lastcells=None
def pose(p):
 q=p.orientation;return [p.position.x,p.position.y,math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))]
with rosbag.Bag('/home/wcqw/active_map_author_validation/results/scientific_06_B1_S3/raw.bag') as bag:
 for topic,m,t in bag.read_messages():
  if topic=='/scan':scans[m.header.stamp.to_nsec()]=m
  elif topic=='/base_pose_ground_truth':gt[m.header.stamp.to_nsec()]=pose(m.pose.pose)
  elif topic=='/author_audit':audit.append(json.loads(m.data))
  elif topic=='/changed_cells':lastcells=m
endpoint={'GT':np.zeros((h,w),int),'online':np.zeros((h,w),int)};mxb={};lastb={}
for a in audit:
 ns=round(a['stamp']*1e9);s=scans.get(ns)
 if s is None:continue
 for x in a['buffers']:mxb[x[0]]=max(mxb.get(x[0],0),x[1]+x[2]);lastb[x[0]]=x[1:]
 for label,p in [('GT',gt.get(ns)),('online',a['pose'])]:
  if p is None:continue
  cells=set()
  for i,d in enumerate(s.ranges):
   if not math.isfinite(d) or d>=18:continue
   ang=s.angle_min+i*s.angle_increment+p[2];xy=np.array(p[:2])+[d*math.cos(ang),d*math.sin(ang)]
   x,y=np.floor((xy-[-5.25,-4.275])/.05).astype(int)
   if 0<=x<w and 0<=y<h:cells.add((y,x))
  for y,x in cells:endpoint[label][y,x]+=1
ids=np.flatnonzero(fp)
result=dict(false_original=92,false_in_final_toOcc=int(sum(int(i) in set(lastcells.toOcc) for i in ids)),
 false_ever_buffer_eligible=int(sum(mxb.get(int(i),0)>=7 for i in ids)),
 false_final_buffer_eligible=int(sum(sum(lastb.get(int(i),[0,0,0])[:2])>=7 for i in ids)),
 false_with_GT_endpoints=int(np.count_nonzero(fp&(endpoint['GT']>0))),
 false_with_online_endpoints=int(np.count_nonzero(fp&(endpoint['online']>0))),
 false_without_GT_but_with_online_endpoints=int(np.count_nonzero(fp&(endpoint['GT']==0)&(endpoint['online']>0))),
 GT_endpoint_false_cells_total=int(np.count_nonzero((endpoint['GT']>0)&~truth)),
 limits='Exact raw endpoint rasterization diagnostic only, not author inverse beam/update model. Perfect-GT endpoints outside binary bitmap prove rendering/raster conventions also differ, not that all errors are harmless. Buffer counts omit flag ordering and per-beam associations.')
(out/'endpoint_check.json').write_text(json.dumps(result,indent=2));np.savez_compressed(out/'endpoint_support.npz',**endpoint);print(json.dumps(result,indent=2))
