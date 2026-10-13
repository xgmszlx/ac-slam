"""Independent archived GT/SLAM pairing; no fitting and no outcome for unexecuted actions."""
import csv
import json
import math
import re
import numpy as np
from common import ASSETS,DOC79,DOC80,OUT,distance,wrap,csv_out,write_json


def accepted_times(reader,run,tum_data):
    p=run/'rosout.log';reader.register(p);times={};uids={}
    pattern=re.compile(r'PHASE2C_KEYSCAN_ACCEPTED unique_id=(\d+) state_id=(\d+) sim_time=([0-9.]+)')
    with p.open(errors='replace') as f:
        for line in f:
            m=pattern.search(line)
            if m:times[int(m.group(2))]=float(m.group(3));uids[int(m.group(2))]=int(m.group(1))
    deviations=[abs(times[i]-tum_data[i,0]) for i in times if i<len(tum_data)]
    if not deviations or max(deviations)>1e-6:raise ValueError('Native state stamp / author TUM ordinal mismatch')
    if len(set(uids.values()))!=len(uids):raise ValueError('Duplicate native accepted unique ID')
    return times,uids


def tum(reader,path):
    if not reader.register(path):return None
    data=np.loadtxt(path,ndmin=2)
    if data.shape[1]!=8 or len(data)<2:raise ValueError('Invalid TUM record '+str(path))
    if not np.isfinite(data).all() or np.any(np.diff(data[:,0])<=0):raise ValueError('TUM stamps not strictly monotonic')
    return data


def nearest_pairs(reference,estimate,tolerance=.05):
    indices=np.searchsorted(reference[:,0],estimate[:,0]);indices=np.clip(indices,0,len(reference)-1)
    previous=np.maximum(0,indices-1)
    closer=np.abs(reference[previous,0]-estimate[:,0])<=np.abs(reference[indices,0]-estimate[:,0])
    indices=np.where(closer,previous,indices)
    delta=np.abs(reference[indices,0]-estimate[:,0]);mask=delta<=tolerance+1e-9
    return reference[indices[mask]],estimate[mask],delta[mask]


def formal_headroom(reader):
    table=reader.csv(ASSETS/'results/phase4c/aggregate/run_table.csv');rows=[];run_inventory=[];preloop=[]
    for item in table:
        run=ASSETS/item['run_dir'];manifest=reader.json(run/'manifest.json',False)
        row={'dataset_id':'phase4c','episode_id':'%s_%s_%s'%(item['map'],item['seed'],item['condition']),
             'map':item['map'],'seed':item['seed'],'method':item['method'],'validity':item['validity'],
             'run_dir':str(run),'source_commit':(manifest or {}).get('commits',{}).get('root'),
             'published_ape_rmse_m':float(item['ape_rmse_m']),'no_alignment_or_scale_fitting':True,
             'headroom_scope':'completed exploration' if item['validity']=='VALID' else 'incomplete exploration: separate descriptive evidence',
             'stage_sync_qualification':False,'counterfactual_outcome_unobserved':True}
        try:
            gt=tum(reader,run/'trajectory_gt.txt');slam=tum(reader,run/'trajectory_slam.txt')
            if gt is None or slam is None:raise FileNotFoundError('Missing raw trajectory')
            g,s,dt=nearest_pairs(gt,slam,.05)
            if len(g)<2:raise ValueError('Insufficient timestamp association')
            residual=np.linalg.norm(g[:,1:3]-s[:,1:3],axis=1)
            times,uids=accepted_times(reader,run,slam)
            raw=reader.csv(run/'ground_truth_samples.csv')
            raw_t=np.array([float(r['timestamp']) for r in raw]);j=np.searchsorted(raw_t,gt[:,0]);j=np.clip(j,0,len(raw_t)-1)
            previous=np.maximum(j-1,0);j=np.where(abs(raw_t[previous]-gt[:,0])<=abs(raw_t[j]-gt[:,0]),previous,j)
            strict=abs(raw_t[j]-gt[:,0])<1e-7
            start=(manifest or {}).get('start_pose_xyyaw')
            if start is None:raise ValueError('Start frame not recorded')
            expected=np.array([[float(raw[k]['x'])-start[0]+.2*math.cos(float(raw[k]['yaw'])),
                                float(raw[k]['y'])-start[1]+.2*math.sin(float(raw[k]['yaw']))] for k in j])
            frame_res=np.linalg.norm(expected[strict]-gt[strict,1:3],axis=1)
            row.update(analysis_status='RAW_RECOMPUTED',matched_state_count=len(g),trajectory_coverage=len(g)/len(slam),
               recomputed_ape_rmse_m=float(np.sqrt(np.mean(residual**2))),error_p95_m=float(np.percentile(residual,95)),
               error_max_m=float(max(residual)),time_association_max_s=float(max(dt)),
               gt_raw_identity_pairs=int(sum(strict)),gt_laser_conversion_max_residual_m=float(max(frame_res)),
               archived_rmse_abs_difference_m=abs(float(np.sqrt(np.mean(residual**2)))-float(item['ape_rmse_m'])),
               initial_gauge_residual_m=float(residual[0]),slam_gt_frame='laser/laser; recorded initial pose translation; no fitted alignment')
            loops=reader.json(run/'loops.json',False)
            for loop in (loops or {}).get('loops',[]):
                before=reader.json(run/loop.get('snapshot_before','missing_before'),False)
                after=reader.json(run/loop.get('snapshot_after','missing_after'),False)
                if before is None:continue
                # Estimate poses come from the ACTUAL pre-loop cache. Only stamp
                # identity is taken from author TUM; future positions are never used.
                historic=before.get('pose_graph_nodes',{});errors=[]
                for key,n in historic.items():
                    state=int(key)
                    if state not in times:continue
                    if int(n['id'])!=state:raise ValueError('Published graph node index/ID mismatch')
                    target_time=times[state];k=np.argmin(abs(gt[:,0]-target_time))
                    if abs(gt[k,0]-target_time)>.05+1e-9:continue
                    x=n.get('x');y=n.get('y')
                    if x is None or y is None:continue
                    errors.append(math.hypot(x-gt[k,1],y-gt[k,2]))
                preloop.append({'episode_id':row['episode_id'],'map':item['map'],'loop_id':loop['loop_id'],
                    'pre_loop_time':loop.get('actual_start_time'),'actual_executed_distance_m':loop.get('extra_distance'),
                    'executed':loop.get('actual_start_time') is not None,'target_constraints_status':'see actual closure/provenance audit',
                    'cached_nodes_with_gt':len(errors),'cached_pre_history_rmse_m':float(np.sqrt(np.mean(np.square(errors)))) if errors else None,
                    'timestamp_identity':'native state_id/unique_id acceptance log; author TUM stamps independently agree <=1us; not raw scan acquisition time',
                    'pre_cache_age_s':loop['actual_start_time']-times[max(int(i) for i in historic)] if loop.get('actual_start_time') is not None else None,
                    'snapshot_semantics':'published cache, not synchronous graph; exploratory headroom only',
                    'after_snapshot_available':after is not None,'candidate_counterfactual_outcome':'UNOBSERVED'})
        except (OSError,ValueError,KeyError,IndexError) as exc:row.update(analysis_status='NOT_EVALUABLE',reason=str(exc))
        rows.append(row)
        run_inventory.append({'dataset_id':'phase4c','episode_id':row['episode_id'],'run_dir':str(run),
            'source_commit':row['source_commit'],'raw_trajectory_available':row['analysis_status']=='RAW_RECOMPUTED',
            'recorded_validity':item['validity'],'pre_decision_state':'published per-loop caches, not synchronous before-target-selection',
            'usable_for_A1':'descriptive execution/whole-run outcomes only','usable_for_A2':'planner traces/native prior diagnostics only'})
    csv_out('analysis/task_headroom_audit.csv',rows);csv_out('analysis/formal_preloop_headroom.csv',preloop)
    summary=[]
    for map_id in sorted(set(r['map'] for r in rows)):
        for validity in ('VALID','EXPERIMENTAL_FAILURE'):
            rr=[r for r in rows if r['map']==map_id and r['validity']==validity and r.get('analysis_status')=='RAW_RECOMPUTED']
            if rr:
                values=[r['recomputed_ape_rmse_m'] for r in rr]
                summary.append({'map':map_id,'validity':validity,'runs':len(rr),'min_rmse_m':min(values),
                      'median_rmse_m':float(np.median(values)),'max_rmse_m':max(values),
                      'max_gt_conversion_residual_m':max(r['gt_laser_conversion_max_residual_m'] for r in rr),
                      'max_published_rmse_difference_m':max(r['archived_rmse_abs_difference_m'] for r in rr)})
    write_json('analysis/formal_headroom_summary.json',summary)
    return run_inventory,rows,preloop
