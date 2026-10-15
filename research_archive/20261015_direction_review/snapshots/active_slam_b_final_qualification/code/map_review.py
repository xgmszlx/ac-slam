"""Offline representation audit of existing nominal data; exact 604 untouched."""
import argparse,json,math
from pathlib import Path
import numpy as np,rosbag
from scipy.ndimage import distance_transform_edt
R=Path(__file__).resolve().parents[1];p=Path('/home/wcqw/active_slam_next_direction_20261014/results/B_technical_02');z=np.load(p/'map_evaluation.npz');truth=z['truth'];vis=z['visible'];estimate=z['estimate'];gt={};scans=[];grids=[]
with rosbag.Bag(str(p/'raw.bag')) as bag:
 for t,m,b in bag.read_messages():
  if t=='/base_pose_ground_truth':
   q=m.pose.pose.orientation;gt[m.header.stamp.to_nsec()]=[m.pose.pose.position.x,m.pose.pose.position.y,math.atan2(2*q.w*q.z,1-2*q.z*q.z)]
  elif t=='/scan':scans.append(m)
  elif t=='/rtabmap/grid_map':grids.append(m)
end=np.zeros_like(truth);overlaps=[]
for s in scans:
 g=gt[s.header.stamp.to_nsec()]
 for k,d in enumerate(s.ranges):
  if not math.isfinite(d) or d>=18:continue
  a=s.angle_min+k*s.angle_increment+g[2];xy=np.array(g[:2])+[d*math.cos(a),d*math.sin(a)];ij=np.floor((xy-[-5.25,-4.275])/.05).astype(int)
  if 0<=ij[0]<truth.shape[1] and 0<=ij[1]<truth.shape[0]:end[ij[1],ij[0]]=True
known=estimate>=0;fp=known&vis&(estimate>=50)&~truth;fn=known&vis&(estimate<50)&truth;D=distance_transform_edt(~truth)*.05
for m in grids:
 y,x=np.indices((m.info.height,m.info.width));ox=m.info.origin.position.x-3;oy=m.info.origin.position.y-2
 ij=np.floor((np.c_[(x.ravel()+.5)*m.info.resolution+ox,(y.ravel()+.5)*m.info.resolution+oy]-[-5.25,-4.275])/.05).astype(int)
 ok=(ij[:,0]>=0)&(ij[:,0]<truth.shape[1])&(ij[:,1]>=0)&(ij[:,1]<truth.shape[0]);lin=ij[ok,1]*truth.shape[1]+ij[ok,0]
 overlaps.append(int(len(lin)-len(np.unique(lin))))
res=dict(original_errors=int(fp.sum()+fn.sum()),FP=int(fp.sum()),FN=int(fn.sum()),unknown_visible=int((vis&~known).sum()),FP_with_GT_endpoints=int((fp&end).sum()),GT_endpoint_free_cells=int((end&~truth).sum()),GT_endpoint_free_distance_quantiles=np.quantile(D[end&~truth],[0,.5,.9,1]).tolist(),forward_resampling_duplicate_target_cells=overlaps,
 evaluation_issues=['Bitmap solid thickness versus surface laser returns','floor rasterization and float32 grid origin/resolution phase','GT ray visibility overshoots endpoints by5cm','unknown excluded from binary errors but separately reported','final visibility includes all recorded scans, not necessarily mapper accepted inputs','free-space/occupied cell count mixes coverage, representation, pose and integration'],
 judgment='UNRESOLVED as standalone SLAM map-quality outcome. Coordinate/unknown conventions are auditable; 604 cannot be interpreted as nominal SLAM failure. GT endpoint agreement supports representation effects, not exclusive cause.')
(R/'audit/map_review.json').write_text(json.dumps(res,indent=2));np.savez_compressed(R/'audit/map_review_arrays.npz',truth=truth,estimate=estimate,visible=vis,GT_endpoints=end);print(json.dumps(res,indent=2))
