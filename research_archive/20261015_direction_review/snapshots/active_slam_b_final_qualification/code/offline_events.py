"""Read-only per-scan reconstruction; internal events remain UNKNOWN without tracing."""
import argparse,csv,json,math
from pathlib import Path
import numpy as np,rosbag
from time_geometry import TFHistory,compose
R=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('run',type=Path);ap.add_argument('output',type=Path);args=ap.parse_args();run=args.run;out=args.output;out.mkdir(parents=True,exist_ok=False)
scans=[];odom={};info={};gt={};nodes={};edges={};first_edges={};graphs=[];maps=[];tf=TFHistory(max_span=.15,max_per_edge=100000)
def pose(p):
 q=p.orientation;return [p.position.x,p.position.y,math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))]
with rosbag.Bag(str(run/'raw.bag')) as bag:
 for topic,m,t in bag.read_messages():
  if topic=='/scan':scans.append(m)
  elif topic=='/icp/odom':odom[m.header.stamp.to_nsec()]=m
  elif topic=='/icp/odom_info':info[m.header.stamp.to_nsec()]=m
  elif topic=='/base_pose_ground_truth':gt[m.header.stamp.to_nsec()]=m
  elif topic in ['/tf','/tf_static']:
   for x in m.transforms:tf.add(dict(parent=x.header.frame_id,child=x.child_frame_id,stamp=x.header.stamp.to_sec(),translation=[x.transform.translation.x,x.transform.translation.y,x.transform.translation.z],quaternion=[x.transform.rotation.x,x.transform.rotation.y,x.transform.rotation.z,x.transform.rotation.w]),static=topic=='/tf_static')
  elif topic=='/rtabmap/grid_map':maps.append(m.header.stamp.to_nsec())
  elif topic=='/rtabmap/mapGraph':graphs.append(m)
  elif topic in ['/rtabmap/mapData','/audit/final_map_data']:
   for n in m.nodes:nodes[int(round(n.stamp*1e9))]=n
   for e in m.graph.links:
    key=(e.fromId,e.toId,e.type);edges[key]=e;first_edges.setdefault(key,m.header.stamp.to_nsec())
receipts=json.loads((run/'receipts.json').read_text());wall={(x['topic'],x['stamp_ns']):x['receipt_wall'] for x in receipts if x['stamp_ns'] is not None}
start=json.loads((run/'collector.json').read_text())['events'][0]['stamp'];rows=[];miss_tf=[]
for s in scans:
 ns=s.header.stamp.to_nsec();stamp=s.header.stamp.to_sec();i=info.get(ns);o=odom.get(ns);n=nodes.get(ns);corr,meta=tf.edge_at(('map','icp_odom'),stamp);full,fmeta=tf.resolve(stamp)
 phase='INITIALIZATION' if stamp<start else 'MOTION' if start+5<=stamp<start+20 else 'STATIONARY'
 r=dict(scan_seq=s.header.seq,scan_stamp_ns=ns,scan_stamp=stamp,receive_wall=wall.get(('/scan',ns),'UNKNOWN'),phase=phase,
        odom_identity='%s:%s'%(o.header.seq,o.header.stamp.to_nsec()) if o else 'NONE',
        map_TF_query=corr is not None,map_TF_reason=meta.get('reason','OK'),complete_base_TF=full is not None,complete_TF_reason=fmeta['status'],
        frontend_callback='UNKNOWN',processing_queue_enter='UNKNOWN',lock_drop='UNKNOWN',ICP_enter='UNKNOWN',
        OdomInfo_output=i is not None,OdomInfo_lost=i.lost if i else 'UNKNOWN',ICP_correspondences=i.icpCorrespondences if i else 'UNKNOWN',
        node_id=n.id if n else 'NONE',local_grid_available=bool(n and (n.data.grid_empty_cells or n.data.grid_obstacles or n.data.grid_ground)),
        incident_edge_ids=json.dumps([list(k) for k in edges if n and n.id in k[:2]]),first_edge_publications_at_stamp=json.dumps([list(k) for k,st in first_edges.items() if st==ns]),
        map_output_at_stamp=ns in maps,used_in_global_map='UNKNOWN',
        latency_wall=wall.get(('/icp/odom_info',ns),0)-wall.get(('/scan',ns),0) if i and ('/icp/odom_info',ns) in wall else 'UNKNOWN',
        processing_s=i.timeEstimation if i else 'UNKNOWN',strict_pair=bool(i and o and ns in gt and corr is not None))
 rows.append(r)
 if i and o and ns in gt and corr is None:miss_tf.append(stamp)
with (out/'scan_events.csv').open('x') as f:
 w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
phase_summary={p:dict(input=sum(r['phase']==p for r in rows),odominfo=sum(r['phase']==p and r['OdomInfo_output'] for r in rows),strict=sum(r['phase']==p and r['strict_pair'] for r in rows)) for p in ['INITIALIZATION','STATIONARY','MOTION']}
for v in phase_summary.values():v['strict_coverage']=v['strict']/max(1,v['input'])
missing=[r for r in rows if not r['OdomInfo_output']];after=[]
for r in missing:
 prior=[q for q in rows if q['scan_stamp']<r['scan_stamp'] and isinstance(q['latency_wall'],float)]
 if prior:
  q=prior[-1];after.append(dict(stamp=r['scan_stamp'],prior_stamp=q['scan_stamp'],prior_latency=q['latency_wall'],prior_processing_s=q['processing_s']))
result=dict(inputs=len(rows),no_OdomInfo=len(missing),strict_pairs=sum(r['strict_pair'] for r in rows),strict_coverage=sum(r['strict_pair'] for r in rows)/len(rows),map_TF_missing_with_output=miss_tf,map_TF_recorded_range=[min(tf.times[('map','icp_odom')]),max(tf.times[('map','icp_odom')])],phases=phase_summary,
 missing_after_prior_latency_gt_scanperiod=sum(x['prior_latency']>=.1 for x in after),missing_with_prior=sum(1 for x in after),
 internal_events='UNKNOWN for all old scans; missing output is not evidence of callback entry, lock drop, or ICP rejection',
 map_membership='Local grid presence and graph/map publication are observed; exact per-node MapsManager cache inclusion not recorded; used_in_global_map UNKNOWN')
(out/'missing_context.json').write_text(json.dumps(after,indent=2));(out/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
