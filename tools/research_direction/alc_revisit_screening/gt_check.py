"""Independent stage-node GT check. Not callable from candidate generation."""
import math
import re
import numpy as np
from common import base_pose,csv_out,wrap

ACCEPT=re.compile(r'PHASE2C_KEYSCAN_ACCEPTED unique_id=(\d+) state_id=(\d+) sim_time=([0-9.]+)')


def interpolate_gt(samples,stamp,tolerance=.06):
    ts=np.array([s['stamp'] for s in samples]);k=int(np.searchsorted(ts,stamp))
    if 0<k<len(ts) and 0<ts[k]-ts[k-1]<=2*tolerance:
        a,b=samples[k-1],samples[k];r=(stamp-a['stamp'])/(b['stamp']-a['stamp'])
        return [a['x']+r*(b['x']-a['x']),a['y']+r*(b['y']-a['y']),wrap(a['theta']+r*wrap(b['theta']-a['theta']))]
    j=min([i for i in [k-1,k] if 0<=i<len(ts)],key=lambda i:abs(ts[i]-stamp))
    s=samples[j]
    return [s['x'],s['y'],s['theta']] if abs(ts[j]-stamp)<=tolerance else None


def fit_pre_action(pairs):
    x=np.array([p[0] for p in pairs]);y=np.array([p[1] for p in pairs]);xc=x-x.mean(axis=0);yc=y-y.mean(axis=0)
    yaw=math.atan2(np.sum(xc[:,0]*yc[:,1]-xc[:,1]*yc[:,0]),np.sum(xc*yc))
    r=np.array([[math.cos(yaw),-math.sin(yaw)],[math.sin(yaw),math.cos(yaw)]])
    return r,y.mean(axis=0)-r@x.mean(axis=0),yaw


def check_run(reader,run,manifest,graphs,scans,result,frozen,archived):
    gt=list(reader.lines(run/'gt_stream.jsonl'));pairs=[]
    marks=result['phase_scan_marks'];history_end=marks['history_end_scan'];return_start=marks['return_start_scan']
    for s in scans:
        if s['index']>=result['action_start_scan_index']:break
        if not (s['index']<history_end or s['index']>=return_start):continue
        if s.get('map_base') is None:continue
        truth=interpolate_gt(gt,s['stamp'])
        if truth is not None:pairs.append((s['map_base'][:2],truth[:2]))
    if len(pairs)<2:raise ValueError('Insufficient pre-action alignment')
    rot,trans,yaw=fit_pre_action(pairs);accepts={}
    reader.register(run/'rosout.log')
    with (run/'rosout.log').open(errors='replace') as f:
        for line in f:
            m=ACCEPT.search(line)
            if m:accepts[int(m.group(2))]=(int(m.group(1)),float(m.group(3)))
    rows=[]
    for stage,g in graphs.items():
        lookup={n['state_id']:n for n in g['nodes']}
        for state in frozen['target_state_ids']:
            n=lookup[state];uid,stamp=accepts[state]
            if uid!=n['unique_id']:raise ValueError('GT state/UID join differs')
            truth=interpolate_gt(gt,stamp);p=base_pose(n)
            error=float(np.linalg.norm(rot@p[:2]+trans-truth[:2])) if truth is not None else None
            original=next(r for r in archived if r['episode_id']==manifest['episode_id'] and r['stage']==stage and int(r['target_state_id'])==state)
            diff=abs(error-float(original['map_error_translation_m'])) if error is not None else None
            if diff is not None and diff>1e-9:raise ValueError('Independent target GT differs from corrected Doc80')
            rows.append({'episode_id':manifest['episode_id'],'stage':stage,'state_id':state,'unique_id':uid,
                'GT_stamp':stamp,'laser_to_base_offset_x_m':-.2,'pre_action_fit_pairs':len(pairs),
                'target_position_error_m':error,'archived_abs_difference_m':diff,
                'alignment_scope':'history + return only; one SE2 fit; no post-action alignment',
                'evaluation_scope':'frozen historical target; not whole-run global APE'})
    return rows
