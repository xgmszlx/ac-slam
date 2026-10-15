#!/usr/bin/env python3
"""Offline-only GT evaluation. No post-action pose alignment and no GT correction."""
import argparse,csv,json,math
from pathlib import Path
import numpy as np
import rosbag
from time_geometry import TFHistory,compose,inverse,wrap
R=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('run');ap.add_argument('--world',choices=['old','changed'],required=True);args=ap.parse_args();run=Path(args.run)
gt={};amcl=[];scans=[];audits=[];maps=[];tf=TFHistory(max_span=.15,max_per_edge=100000);errors=[];recoveries=[]
def pose(p):
    q=p.orientation;return [p.position.x,p.position.y,math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))]
with rosbag.Bag(str(run/'raw.bag')) as b:
    for topic,msg,t in b.read_messages():
        if topic=='/base_pose_ground_truth':gt[msg.header.stamp.to_nsec()]=pose(msg.pose.pose)
        elif topic=='/amcl_pose':amcl.append((msg.header.stamp.to_nsec(),pose(msg.pose.pose)))
        elif topic=='/scan':scans.append(msg)
        elif topic=='/author_audit':audits.append(json.loads(msg.data))
        elif topic=='/processed_map':maps.append((msg.header.stamp.to_sec(),np.array(msg.data).reshape(msg.info.height,msg.info.width)))
        elif topic=='/initialpose':recoveries.append(dict(stamp=msg.header.stamp.to_sec(),pose=pose(msg.pose.pose)))
        elif topic in ['/tf','/tf_static']:
            for x in msg.transforms:
                tf.add(dict(parent=x.header.frame_id,child=x.child_frame_id,stamp=x.header.stamp.to_sec(),translation=[x.transform.translation.x,x.transform.translation.y,x.transform.translation.z],quaternion=[x.transform.rotation.x,x.transform.rotation.y,x.transform.rotation.z,x.transform.rotation.w]),static=topic=='/tf_static')
truths=np.load(R/'protocol/scenes/truth_maps.npz');old=truths['old'];truth=truths[args.world];changed=truth!=old
visible=np.zeros_like(truth);origin=np.array([-5.25,-4.275]);res=.05
for scan in scans:
    stamp=scan.header.stamp.to_nsec();online,meta=tf.resolve(scan.header.stamp.to_sec());g=gt.get(stamp)
    if online is not None and g is not None:
        errors.append(dict(stamp=scan.header.stamp.to_sec(),seq=scan.header.seq,x=online[0],y=online[1],yaw=online[2],gt_x=g[0],gt_y=g[1],gt_yaw=g[2],translation_error=float(np.linalg.norm(np.array(online[:2])-g[:2])),yaw_error=abs(wrap(online[2]-g[2]))))
    if g is not None:
        # Offline observability: actual laser ray support under recorded world pose.
        for i,d in enumerate(scan.ranges):
            if not math.isfinite(d) or d>=18:continue
            angle=scan.angle_min+i*scan.angle_increment+g[2];steps=np.arange(0,max(0,d)+.05,.025)
            xy=np.array(g[:2])+np.c_[np.cos(angle)*steps,np.sin(angle)*steps];ij=np.floor((xy-origin)/res).astype(int)
            ok=(ij[:,0]>=0)&(ij[:,0]<truth.shape[1])&(ij[:,1]>=0)&(ij[:,1]<truth.shape[0]);visible[ij[ok,1],ij[ok,0]]=True
map_rows=[];last=old.copy();commit_events=0
for stamp,m in maps:
    mapped=m==100;written=mapped!=old;correct=written&changed&(mapped==truth);false=written&~changed
    actual_delta=int(np.count_nonzero(mapped!=last));commit_events+=int(actual_delta>0);last=mapped
    union=mapped|truth;score=1-float(np.mean((mapped[union].astype(float)-truth[union].astype(float))**2)) if union.any() else 1.
    map_rows.append(dict(stamp=stamp,actual_delta=actual_delta,map_error_cells=int(np.count_nonzero(mapped!=truth)),false_update_cells=int(false.sum()),correct_update_cells=int(correct.sum()),change_recall=float(correct.sum()/max(1,int(changed.sum()))),visible_change_recall=float(np.count_nonzero(correct&visible)/max(1,int(np.count_nonzero(changed&visible)))),occupied_union_map_score=score))
aud_eval=[]
for x in audits:
    n=int(round(x['stamp']*1e9));g=gt.get(n);err=None if g is None else float(np.linalg.norm(np.array(x['pose'][:2])-g[:2]))
    aud_eval.append(dict(stamp=x['stamp'],event=x['event'],anomalous=x['anomalous'],valid=x['valid'],ratio=x['anomalous']/max(1,x['valid']),pose_error=err,active_buffers=len(x['buffers']),max_buffer_count=max([t[1] for t in x['buffers']]+[0])))
rpe=[];bytime={round(x['stamp'],6):x for x in errors}
for x in errors:
    y=bytime.get(round(x['stamp']+1,6))
    if y:
        est=compose(inverse([x['x'],x['y'],x['yaw']]),[y['x'],y['y'],y['yaw']]);tru=compose(inverse([x['gt_x'],x['gt_y'],x['gt_yaw']]),[y['gt_x'],y['gt_y'],y['gt_yaw']]);rpe.append(float(np.linalg.norm(np.array(est[:2])-tru[:2])))
collector=json.loads((run/'collector.json').read_text());start=collector['events'][0]['stamp'] if collector['events'] else 0
task=[x for x in errors if x['stamp']>=start]
summary=dict(scan_count=len(scans),strict_tf_gt_pairs=len(errors),pair_fraction=len(errors)/max(1,len(scans)),tf_conflicting_duplicates=tf.conflicting_duplicates,
             processed_scan_count=len(audits),freeze_count=sum(x['event']=='FREEZE' for x in audits),max_anomalous_ratio=max([x['ratio'] for x in aud_eval]+[0]),
             mean_translation_error=float(np.mean([x['translation_error'] for x in task])) if task else None,
             max_translation_error=max([x['translation_error'] for x in task]+[0]),mean_1s_translation_rpe=float(np.mean(rpe)) if rpe else None,
             gt_displacement_m=float(np.linalg.norm(np.array(gt[max(gt)][:2])-gt[min(gt)][:2])) if gt else None,
             changed_cells=int(changed.sum()),visible_changed_cells=int(np.count_nonzero(changed&visible)),map_before_error=int(changed.sum()),actual_map_commit_events=commit_events,
             map_final=map_rows[-1] if map_rows else None,initialpose_messages=recoveries,collector_dropped=collector['dropped'],collector_status=collector['status'],
             note='GT header says odom but installed Stage publishes GetGlobalPose world coordinates; known map frame equals Stage world, no fitted alignment')
passed=collector['status']=='COMPLETED' and collector['dropped']==0 and summary['pair_fraction']>=.9 and len(audits)>=8 and summary['tf_conflicting_duplicates']==0
if args.world=='old' and 'technical' in run.name:passed=passed and summary['mean_translation_error'] is not None and summary['max_translation_error']<=.15 and summary['freeze_count']==0 and summary['map_final']['false_update_cells']==0
summary['technical_qualification']=bool(passed)
for name,a in [('trajectory',errors),('map_metrics',map_rows),('audit_metrics',aud_eval)]:
    with (run/(name+'.csv')).open('x') as f:
        if a:wr=csv.DictWriter(f,list(a[0]));wr.writeheader();wr.writerows(a)
(run/'evaluation.json').write_text(json.dumps(summary,indent=2));np.savez_compressed(run/'evaluation_maps.npz',old=old,truth=truth,final=last,visible=visible)
print(json.dumps(summary,indent=2))
