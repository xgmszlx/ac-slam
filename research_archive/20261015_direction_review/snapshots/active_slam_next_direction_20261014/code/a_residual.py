"""Offline attribution only. Original exact binary metrics remain unchanged."""
import sys,json,csv,math,argparse
from pathlib import Path
import numpy as np
from scipy.ndimage import distance_transform_edt
import rosbag
R=Path(__file__).resolve().parents[1];A=Path('/home/wcqw/active_map_author_validation')
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=R/'results/A_residual');args=ap.parse_args()
out=args.output;out.mkdir(parents=True,exist_ok=False)
runs={'B0':A/'results/scientific_04_S3','B1':A/'results/scientific_06_B1_S3'}
def pxy(p):
 q=p.orientation;return np.array([p.position.x,p.position.y,math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))])
data={}
for label,run in runs.items():
 z=np.load(run/'evaluation_maps.npz');old=z['old'];truth=z['truth'];final=z['final'];visible=z['visible']
 gt={};scans={};aud=[];cells=[];maps=[]
 with rosbag.Bag(str(run/'raw.bag')) as b:
  for t,m,bt in b.read_messages():
   if t=='/scan':scans[m.header.stamp.to_nsec()]=m
   elif t=='/base_pose_ground_truth':gt[m.header.stamp.to_nsec()]=pxy(m.pose.pose)
   elif t=='/author_audit':aud.append(json.loads(m.data))
   elif t=='/changed_cells':cells.append((bt.to_sec(),list(m.toOcc),list(m.toFree)))
   elif t=='/processed_map':maps.append((bt.to_sec(),np.array(m.data).reshape(truth.shape)==100))
 stamps={int(round(a['stamp']*1e9)) for a in aud}
 procvis=np.zeros_like(truth);support=np.zeros_like(truth,dtype=int); endpoint=np.zeros_like(truth,dtype=int)
 # Exact original evaluator's ray support for the actually processed subset.
 for ns in stamps:
  s=scans.get(ns);g=gt.get(ns)
  if s is None or g is None:continue
  scanmask=np.zeros_like(truth);ends=np.zeros_like(truth)
  for i,d in enumerate(s.ranges):
   if not math.isfinite(d) or d>=18:continue
   ang=s.angle_min+i*s.angle_increment+g[2]
   step=np.arange(0,max(0,d)+.05,.025)
   xy=g[:2]+np.c_[np.cos(ang)*step,np.sin(ang)*step]
   ij=np.floor((xy-[-5.25,-4.275])/.05).astype(int)
   ok=(ij[:,0]>=0)&(ij[:,0]<truth.shape[1])&(ij[:,1]>=0)&(ij[:,1]<truth.shape[0])
   scanmask[ij[ok,1],ij[ok,0]]=True
   e=np.floor((g[:2]+[math.cos(ang)*d,math.sin(ang)*d]-[-5.25,-4.275])/.05).astype(int)
   if 0<=e[0]<truth.shape[1] and 0<=e[1]<truth.shape[0]:ends[e[1],e[0]]=True
  procvis|=scanmask;support+=scanmask;endpoint+=ends
 last={x[0]:x[1:] for x in aud[-1]['buffers']};mx={};firstcommit={}
 for a in aud:
  for x in a['buffers']:
   mx[x[0]]=max(mx.get(x[0],0),x[1]+x[2])
 previous=old
 for stamp,m in maps:
  for idx in np.flatnonzero(m!=previous):firstcommit.setdefault(int(idx),stamp)
  previous=m
 change=old!=truth;false=(final!=old)&~change;miss=change&(final!=truth)
 dist=distance_transform_edt(~truth)*.05
 summary=dict(processed_scans=len(aud),incoming_scans=len(scans),false_updates=int(false.sum()),missed_changes=int(miss.sum()),final_errors=int((final!=truth).sum()),
              missed_unseen_original=int((miss&~visible).sum()),missed_seen_original=int((miss&visible).sum()),
              missed_unseen_processed=int((miss&~procvis).sum()),missed_seen_processed=int((miss&procvis).sum()),
              missed_seen_no_buffer=int(sum(int(i) not in mx for i in np.flatnonzero(miss&procvis))),
              missed_seen_ever_eligible=int(sum(mx.get(int(i),0)>=7 for i in np.flatnonzero(miss&procvis))),
              missed_seen_final_eligible=int(sum(sum(last.get(int(i),[0,0,0])[:2])>=7 for i in np.flatnonzero(miss&procvis))),
              changed_cells_messages=len(cells),distinct_changed_payloads=len({(tuple(a),tuple(b)) for _,a,b in cells}),
              false_all_added=bool(np.all(final[false])),false_all_seen=bool(np.all(visible[false])),
              boundary_sensitivity={str(t):int((false&(dist>t+1e-9)).sum()) for t in [0,.05,.1,.15,.2]},
              false_distance_quantiles=np.quantile(dist[false],[0,.5,.9,1]).tolist())
 with (out/(label+'_cells.csv')).open('x') as f:
  fields=['id','x','y','old','truth','final','false_update','missed_change','original_visible','processed_visible','processed_support_scans','processed_endpoint_scans','max_count_plus_neighbors','last_changed_count','last_mature_neighbors','last_size','first_transition_bagtime']
  w=csv.DictWriter(f,fields);w.writeheader()
  for idx in np.flatnonzero(final!=truth):
   y,x=divmod(int(idx),truth.shape[1]);buf=last.get(int(idx),[0,0,0])
   w.writerow(dict(zip(fields,[int(idx),x,y,int(old[y,x]),int(truth[y,x]),int(final[y,x]),int(false[y,x]),int(miss[y,x]),int(visible[y,x]),int(procvis[y,x]),int(support[y,x]),int(endpoint[y,x]),mx.get(int(idx),0),*buf,firstcommit.get(int(idx))])))
 data[label]=dict(summary=summary,stamps=sorted(stamps),audits=aud)
 np.savez_compressed(out/(label+'_attribution.npz'),old=old,truth=truth,final=final,visible=visible,processed_visible=procvis,false=false,missed=miss,support=support,endpoint=endpoint)
common=set(data['B0']['stamps'])&set(data['B1']['stamps'])
compare=dict(common_processed_count=len(common),B0_only_stamps_s=[x/1e9 for x in set(data['B0']['stamps'])-common],B1_only_stamps_s=[x/1e9 for x in set(data['B1']['stamps'])-common],
 warning='Same incoming scans; different processed stamp sets. No counterfactual equal-processing replay performed; do not isolate causal pose-estimator effect.')
result=dict(B0=data['B0']['summary'],B1=data['B1']['summary'],processing_comparison=compare,
 interpretation='Boundary proximity is consistent with discretization/pose bias but does not establish exclusive cause. Visibility mask includes 5cm past endpoints as in original evaluation, not proof of independent change evidence. No downstream task-loss experiment, no active necessity established.')
(out/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
