"""Offline GT evaluator and explicit measurement/node/map associations."""
import sys,json,math,csv,hashlib,argparse
from pathlib import Path
import numpy as np
import rosbag
from time_geometry import TFHistory,compose,inverse,wrap
R=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('run',type=Path);ap.add_argument('--output',type=Path);args=ap.parse_args();run=args.run
output=args.output or run
if args.output:output.mkdir(parents=True,exist_ok=False)
gt={};scans={};od={};oi={};infos={};graphs={};maps=[];nodes={};tf=TFHistory(max_span=.15,max_per_edge=100000);parents={};owners={};clock=[];links={};data_stamps=[]
def pose(p):
 q=p.orientation;return [p.position.x,p.position.y,math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))]
with rosbag.Bag(str(run/'raw.bag')) as b:
 for topic,m,t in b.read_messages():
  if topic=='/base_pose_ground_truth':gt[m.header.stamp.to_nsec()]=pose(m.pose.pose)
  elif topic=='/scan':scans[m.header.stamp.to_nsec()]=m
  elif topic=='/icp/odom':od[m.header.stamp.to_nsec()]=m
  elif topic=='/icp/odom_info':oi[m.header.stamp.to_nsec()]=m
  elif topic=='/rtabmap/info':infos[m.header.stamp.to_nsec()]=m
  elif topic=='/rtabmap/mapGraph':graphs[m.header.stamp.to_nsec()]=m
  elif topic in ['/rtabmap/mapData','/audit/final_map_data']:
   data_stamps.append(m.header.stamp.to_nsec())
   for n in m.nodes:nodes[n.id]=n
   for l in m.graph.links:links[(l.fromId,l.toId,l.type)]=l
  elif topic=='/rtabmap/grid_map':maps.append(m)
  elif topic in ['/tf','/tf_static']:
   for x in m.transforms:
    parent=x.header.frame_id.lstrip('/');child=x.child_frame_id.lstrip('/');parents.setdefault(child,set()).add(parent)
    owners.setdefault(parent+'->'+child,set()).add(getattr(m,'_connection_header',{}).get('callerid','unknown'))
    tf.add(dict(parent=parent,child=child,stamp=x.header.stamp.to_sec(),translation=[x.transform.translation.x,x.transform.translation.y,x.transform.translation.z],quaternion=[x.transform.rotation.x,x.transform.rotation.y,x.transform.rotation.z,x.transform.rotation.w]),static=topic=='/tf_static')
  elif topic=='/clock':clock.append(m.clock.to_sec())
rows=[];missing={}
for ns,s in sorted(scans.items()):
 g=gt.get(ns);o=od.get(ns);info=oi.get(ns)
 if g is None or o is None or info is None:missing['EXACT_STAMP_ABSENT']=missing.get('EXACT_STAMP_ABSENT',0)+1;continue
 corr,meta=tf.edge_at(('map','icp_odom'),ns/1e9)
 if corr is None:missing[meta.get('reason','TF_ABSENT')]=missing.get(meta.get('reason','TF_ABSENT'),0)+1;continue
 p=compose(corr,pose(o.pose.pose));gmap=compose([3,2,0],g)
 rows.append(dict(stamp=ns/1e9,stamp_ns=ns,scan_seq=s.header.seq,x=p[0],y=p[1],yaw=p[2],gt_x=gmap[0],gt_y=gmap[1],gt_yaw=gmap[2],translation_error=float(np.linalg.norm(np.array(p[:2])-gmap[:2])),yaw_error=abs(wrap(p[2]-gmap[2])),lost=info.lost,icp_ratio=info.icpInliersRatio,icp_correspondences=info.icpCorrespondences,processing_s=info.timeEstimation))
rpe=[];bytime={r['stamp_ns']:r for r in rows}
for r in rows:
 s=bytime.get(r['stamp_ns']+1000000000)
 if s:
  a=compose(inverse([r['x'],r['y'],r['yaw']]),[s['x'],s['y'],s['yaw']]);b=compose(inverse([r['gt_x'],r['gt_y'],r['gt_yaw']]),[s['gt_x'],s['gt_y'],s['gt_yaw']]);rpe.append(float(np.linalg.norm(np.array(a[:2])-b[:2])))
association=[]
for nid,n in sorted(nodes.items()):
 ns=int(round(n.stamp*1e9));i=infos.get(ns);graph=graphs.get(ns)
 same=[m for m in maps if m.header.stamp.to_nsec()==ns]
 association.append(dict(node_id=nid,stamp_ns=ns,scan_present=ns in scans,odom_present=ns in od,odominfo_present=ns in oi,info_present=i is not None,info_ref=i.refId if i else None,graph_snapshot_present=graph is not None,graph_node_present=bool(graph and nid in graph.posesId),map_snapshot_count=len(same),node_link_count=sum(nid in k[:2] for k in links),weight=n.weight,local_grid_cell_size=n.data.grid_cell_size))
maprows=[];old=np.load(R/'protocol/scenes/truth_maps.npz')['old'];previous=None;visibility=np.zeros_like(old)
for ns,s in scans.items():
 if ns not in gt:continue
 g=gt[ns]
 for k,d in enumerate(s.ranges):
  if not math.isfinite(d) or d>=18:continue
  angle=s.angle_min+k*s.angle_increment+g[2];step=np.arange(0,d+.05,.025)
  xy=np.array(g[:2])+np.c_[np.cos(angle)*step,np.sin(angle)*step];ij=np.floor((xy-[-5.25,-4.275])/.05).astype(int)
  ok=(ij[:,0]>=0)&(ij[:,0]<old.shape[1])&(ij[:,1]>=0)&(ij[:,1]<old.shape[0]);visibility[ij[ok,1],ij[ok,0]]=True
for m in maps:
 grid=np.array(m.data,dtype=np.int16).reshape(m.info.height,m.info.width);origin=pose(m.info.origin)
 # Known a-priori Stage start defines the fresh SLAM anchor; no fitted post-motion alignment.
 y,x=np.indices(grid.shape);c=np.cos(origin[2]);s=np.sin(origin[2]);local=np.c_[((x.ravel()+.5)*m.info.resolution),((y.ravel()+.5)*m.info.resolution)]
 world=local@np.array([[c,s],[-s,c]])+np.array(origin[:2])+[-3,-2];ij=np.floor((world-[-5.25,-4.275])/.05).astype(int)
 ok=(ij[:,0]>=0)&(ij[:,0]<old.shape[1])&(ij[:,1]>=0)&(ij[:,1]<old.shape[0]);estimate=np.full(old.shape,-1,dtype=np.int16);estimate[ij[ok,1],ij[ok,0]]=grid.ravel()[ok]
 known=estimate>=0;observed=known&visibility;fp=observed&(estimate>=50)&~old;fn=observed&(estimate<50)&old
 actual_delta=int(np.count_nonzero(estimate!=previous)) if previous is not None else int(known.sum());previous=estimate
 maprows.append(dict(stamp_ns=m.header.stamp.to_nsec(),resolution=m.info.resolution,width=m.info.width,height=m.info.height,known_truth_cells=int(known.sum()),observed_known_cells=int(observed.sum()),false_occupied_cells=int(fp.sum()),false_free_cells=int(fn.sum()),unknown_visible_cells=int((visibility&~known).sum()),observed_binary_errors=int(fp.sum()+fn.sum()),actual_aligned_delta_cells=actual_delta,info_at_stamp=m.header.stamp.to_nsec() in infos,graph_at_stamp=m.header.stamp.to_nsec() in graphs))
if maps:np.savez_compressed(output/'map_evaluation.npz',truth=old,estimate=previous,visible=visibility)
for name,a in [('trajectory',rows),('node_associations',association),('map_metrics',maprows)]:
 with (output/(name+'.csv')).open('x') as f:
  if a:w=csv.DictWriter(f,list(a[0]));w.writeheader();w.writerows(a)
collection=json.loads((run/'collector.json').read_text());noninitial=[m for m in oi.values() if m.icpCorrespondences>0]
result=dict(scan_count=len(scans),odom_count=len(od),odominfo_count=len(oi),strict_pairs=len(rows),pair_fraction=len(rows)/max(1,len(scans)),missing=missing,tf_conflicting_duplicates=tf.conflicting_duplicates,tf_multiple_parents={k:list(v) for k,v in parents.items() if len(v)>1},tf_owners={k:list(v) for k,v in owners.items()},
 mean_translation_error=float(np.mean([r['translation_error'] for r in rows])) if rows else None,max_translation_error=max([r['translation_error'] for r in rows]+[0]),mean_1s_rpe=float(np.mean(rpe)) if rpe else None,
 icp_nonlost=sum(not m.lost for m in oi.values()),icp_lost=sum(m.lost for m in oi.values()),icp_noninitial_with_correspondences=len(noninitial),icp_mean_processing_s=float(np.mean([m.timeEstimation for m in oi.values()])) if oi else None,
 graph_nodes=len(nodes),graph_links=len(links),link_types={str(k):sum(x[2]==k for x in links) for k in set(x[2] for x in links)},
 linked_node_records=sum(a['scan_present'] and a['odominfo_present'] and a['info_ref']==a['node_id'] and a['graph_node_present'] and a['map_snapshot_count']>0 for a in association),map_messages=len(maps),map_final=maprows[-1] if maprows else None,
 gt_motion_m=sum(np.linalg.norm(np.array(b[:2])-a[:2]) for a,b in zip(list(gt.values()),list(gt.values())[1:])),clock_monotonic=all(b>=a for a,b in zip(clock,clock[1:])),collector=collection,
 map_metric_boundary='Exact occupied/free error within both observed and known support. Unknown reported separately. Thick GT bitmap and endpoint-only occupancy differ; no whole-map accuracy claim.',GT_alignment='A-priori initial world pose [-3,-2,0]; map anchor equals initial ICP coordinate. No optimized/final GT fit. GT only offline.',limitations='No induced failure/reject qualification; neighbor graph links derive from odometry, not independent frontend matches; ICP accepted is not correctness; map updates need not improve GT metric.')
g=json.loads((R/'protocol/b_frozen.json').read_text())['gates']
result['signal_qualified']=bool(collection['status']=='COMPLETED' and collection['dropped']==0 and result['pair_fraction']>=g['minimum_exact_scan_odom_GT_pair_fraction'] and result['max_translation_error']<=g['maximum_normal_translation_error_m'] and not result['tf_multiple_parents'] and result['tf_conflicting_duplicates']==0 and result['graph_nodes']>=g['minimum_graph_nodes'] and result['linked_node_records']>=g['minimum_graph_nodes'] and result['map_final'] is not None)
(output/'evaluation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
