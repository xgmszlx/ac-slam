"""Fixed common-window analysis. Reads saved traces only; never invokes SLAM."""
from pathlib import Path
import sys,json,csv,re
import numpy as np
HERE=Path(__file__).resolve().parents[1]
LOCAL=Path('/home/wcqw/ngd_bonn_frame_audit_20261021')
P0=LOCAL if LOCAL.exists() else HERE.parent/'20261021_ngd_bonn_frame_audit'
sys.path.insert(0,str(P0/'code'))
from pose_math import *
R=Path('/home/wcqw/ngd_region_prototype_20261021/results')
B=Path('/home/wcqw/passive_rgbd_combo_20261019/e2e_20261020/data/rgbd_bonn_moving_obstructing_box')

def table(path):return list(csv.DictReader(Path(path).open()))
def save(name,rows):
    with (HERE/'results'/name).open('w') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

plan=json.loads((HERE/'protocol/analysis_frozen.json').read_text());a=table(R/'M0/frame_states.csv');b=table(R/'M2/frame_states.csv')
ts=np.array([float(x['stamp']) for x in a]);assert np.array_equal(ts,np.array([float(x['stamp']) for x in b]));t0=ts[0]
base=np.array([int(x['base_pixels'])/(640*480) for x in a])
summary={'input_frames':len(ts),'common_stamps_exact':True,'new_SLAM_runs':0,'first_accepted':plan['events'][0]}
summary['differences']={}
for k in ['base_hash','full_hash','N','associations','pnp_inliers','poseopt_last_edges','tx','qx']:
    inds=[i for i,(x,y) in enumerate(zip(a,b)) if x[k]!=y[k]]
    summary['differences'][k]={'count':len(inds),'first':inds[0] if inds else None,'first_time_s':float(ts[inds[0]]-t0) if inds else None}
_,pa=poses(read(R/'M0/OnlineTrajectory.txt'));_,pb=poses(read(R/'M2/OnlineTrajectory.txt'));sep=np.linalg.norm(pa[:,:3,3]-pb[:,:3,3],axis=1)
summary['online_separation_without_fit']={str(th):{'first_index':int(np.where(sep>th)[0][0]),'first_s':float(ts[np.where(sep>th)[0][0]]-t0)} for th in [1e-6,.001,.01,.05,.1,.2]}
summary['pre_first_intervention_max_online_separation_m']=float(sep[:271].max())
summary['loop_log_messages']={}
summary['surviving_exported_keyframes']={}
kf_sets={}
for mode in ['M0','M2']:
    prev=-1;events=[]
    for line in (R/mode/'stdout.log').read_text().splitlines():
        mm=re.search(r'Frame (\d+) end',line)
        if mm:prev=int(mm[1])
        if 'Loop detected' in line or 'Local Mapping STOP' in line or 'Local Mapping RELEASE' in line:events.append({'last_completed_input_when_printed':prev,'text':line})
    summary['loop_log_messages'][mode]=events
    kt=read(R/mode/'KeyFrameTrajectory.txt')[:,0];kf_sets[mode]={int(np.argmin(abs(ts-t))) for t in kt};summary['surviving_exported_keyframes'][mode]=len(kt)
rows=[];windows=[]
for typ in ['online','exported']:
    aa={};rr={}
    for mode in ['M0','M2']:
        aa[mode]={int(np.argmin(abs(ts-float(x['stamp'])))):float(x['error_m']) for x in table(P0/'corrected'/('NGD_'+mode)/typ/'official_rigid/ate.csv')}
        rr[mode]={(int(np.argmin(abs(ts-float(x['stamp_start'])))),int(np.argmin(abs(ts-float(x['stamp_end']))))):(float(x['translation_m']),float(x['rotation_deg'])) for x in table(P0/'corrected'/('NGD_'+mode)/typ/'official_rigid/rpe.csv')}
    # The candidate window endpoints are solely the common original input clock.
    fixed=[]
    for i in range(len(ts)):
        j=int(np.argmin(abs(ts-ts[i]-1)))
        if j>i and abs(ts[j]-ts[i]-1)<.02 and (i,j) in rr['M0'] and (i,j) in rr['M2']:fixed.append((i,j))
    assert len(fixed)==558
    for i,j in fixed:
        frac=float(base[i:j+1].mean());stratum='low_0_5pct' if frac<=.05 else 'medium_5_30pct' if frac<=.3 else 'high_over30pct'
        row={'type':typ,'i':i,'j':j,'start_s':float(ts[i]-t0),'end_s':float(ts[j]-t0),'M0_reference_mean_mask_fraction':frac,'stratum':stratum,'block':int((ts[i]-t0)//5),'accepted_event_inside':int(any(i<=e<=j for e in plan['events'])),'M0_RPEt_m':rr['M0'][i,j][0],'M2_RPEt_m':rr['M2'][i,j][0],'M0_RPEr_deg':rr['M0'][i,j][1],'M2_RPEr_deg':rr['M2'][i,j][1]}
        row['delta_RPEt_m']=row['M2_RPEt_m']-row['M0_RPEt_m'];windows.append(row)
    for i in range(len(ts)):
        row={'type':typ,'index':i,'stamp':ts[i],'time_s':float(ts[i]-t0),'M0_ATE_m':aa['M0'].get(i),'M2_ATE_m':aa['M2'].get(i),'online_pose_separation_m':sep[i],'M0_reference_mask_fraction':base[i],'M0_export_surviving_KF':int(i in kf_sets['M0']),'M2_export_surviving_KF':int(i in kf_sets['M2'])}
        for m,fr in [('M0',a[i]),('M2',b[i])]:
            for k in ['map','map_count','state','N','associations','lk_checked','lk_retained','lk_deleted_extra','orb_raw','orb_retained','orb_deleted_extra','pnp_calls','pnp_inliers','poseopt_calls','poseopt_edges_sum','poseopt_inliers_sum','poseopt_last_edges','poseopt_last_inliers','accepted','extra_pixels','base_pixels','base_hash','full_hash','api_ms','module_cpu_ms']:row[m+'_'+k]=fr[k]
        rows.append(row)
save('paired_frame_evidence.csv',rows);save('common_RPE_windows.csv',windows)
aggregates=[]
for typ in ['online','exported']:
    for group in ['all','pre_first_event','block0','block1','block2','block3','low_0_5pct','medium_5_30pct','high_over30pct']:
        def choose(x):
            if group=='all':return True
            if group=='pre_first_event':return x['j']<271
            if group.startswith('block'):
                k=int(group[-1]);return 5*k<=x['start_s'] and x['end_s']<5*(k+1)
            return group==x['stratum']
        subset=[x for x in windows if x['type']==typ and choose(x)]
        r={'type':typ,'group':group,'overlapping_windows_n':len(subset)}
        for mode in ['M0','M2']:
            for key in ['RPEt_m','RPEr_deg']:
                for name,val in describe([x[mode+'_'+key] for x in subset]).items():r[mode+'_'+key+'_'+name]=val
        if group.startswith('block'):
            k=int(group[-1]);frames=[x for x in rows if x['type']==typ and 5*k<=x['time_s']<5*(k+1)]
            for mode in ['M0','M2']:
                for name,val in describe([x[mode+'_ATE_m'] for x in frames if x[mode+'_ATE_m'] is not None]).items():r[mode+'_ATE_m_'+name]=val
        aggregates.append(r)
keys=list(dict.fromkeys(k for r in aggregates for k in r))
with (HERE/'results/common_window_groups.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(aggregates)
for event in plan['events']:
    EDIR=HERE/'events'/str(event);EDIR.mkdir(exist_ok=True)
    selected=[r for r in rows if abs(r['stamp']-ts[event])<=.5]
    with (EDIR/'paired_neighborhood.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(selected)
    regs=[x for x in table(R/'M2/regions.csv') if int(x['index'])==event]
    info={'index':event,'stamp':float(ts[event]),'time_s':float(ts[event]-t0),'M0':a[event],'M2':b[event],'region_decisions':regs,'event_mask_pixels':'NOT_RECORDED','deleted_observation_pixel_coordinates':'NOT_RECORDED','deleted_MapPoint_identity_history':'NOT_RECORDED','per_observation_Jacobians_and_residuals':'NOT_RECORDED','local_BA_factor_history':'NOT_RECORDED','YOLO_detection_and_mask_age':'NOT_RECORDED','keyframe_interpretation':'final exported surviving stamps only; not complete creation/culling/BA events','no_reconstructed_masks':True}
    (EDIR/'evidence.json').write_text(json.dumps(info,indent=2))
summary['common_RPE_windows_per_output']=558
summary['surviving_exported_keyframe_stamp_differences_for_pre_event_inputs']=sorted((kf_sets['M0']^kf_sets['M2'])&set(range(271)))
summary['keyframe_limit']='final surviving stamps are hindsight; later culling may affect earlier stamps, so these do not prove pre-event live keyframe state'
grows=read(B/'groundtruth.txt');steps=[]
for i in range(1,len(ts)):
    if ts[i-1]<grows[0,0]:continue
    ga=corrected(interpolate(grows,ts[i-1]));gb=corrected(interpolate(grows,ts[i]));truth=np.linalg.norm(gb[:3,3]-ga[:3,3])
    steps.append({'index':i,'time_s':float(ts[i]-t0),'dt_s':float(ts[i]-ts[i-1]),'GT_step_m':truth,'M0_online_step_m':np.linalg.norm(pa[i,:3,3]-pa[i-1,:3,3]),'M2_online_step_m':np.linalg.norm(pb[i,:3,3]-pb[i-1,:3,3])})
save('all_adjacent_pose_steps.csv',steps)
summary['M2_largest_adjacent_online_step']=max(steps,key=lambda x:x['M2_online_step_m'])
(HERE/'results/summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
