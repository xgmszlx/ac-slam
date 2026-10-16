"""Offline only: official evaluation semantics plus coverage, no GT spatial fit."""
from pathlib import Path
import sys,json,re
import numpy as np
from scipy.spatial.transform import Rotation
p=Path(__file__).resolve().parents[1];b=Path('/home/wcqw/lilocbench_amcl_validation_20261016');out=p/'results'/sys.argv[1]
sys.path[:0]=[str(b/'sources/eval_deps'),str(b/'sources/LILocBench-68e86f33ae3ff660444b92093fb98ca4d5633b46/src')]
import evaluate as ev
run=json.loads((out/'run.json').read_text());seq=run['spec']['sequence']
tg,pg=ev.load_poses_tum_format(str(b/'data/gt'/seq/'gt_poses.txt'));tl,pl=ev.load_poses_tum_format(str(out/'trajectory.txt'))
if not np.all(np.diff(tl)>0):raise ValueError('Estimator timestamps not strictly increasing')
if not np.isfinite(pl).all():raise ValueError('Nonfinite estimator pose')
if len(tl)<2:raise ValueError('No valid trajectory')
interp=ev.interpolate_poses(tg,tl,pl);tr,rr=ev.ape2d(pg,interp);rd=np.degrees(rr)
inside=(tg>=tl[0])&(tg<=tl[-1]);support={}
# Time support only; this is not a per-input-scan tracking success label.
for gap in [1.,2.]:
 ids=np.searchsorted(tl,tg,side='right');idx=np.clip(ids,1,len(tl)-1)
 supported=inside & ((tl[idx]-tl[idx-1])<=gap)
 support[str(gap)]=float(supported.mean())
# At the native AMCL output stamps, interpolate GT only within its range, never extrapolate.
within=(tl>=tg[0])&(tl<=tg[-1]);g_native=ev.interpolate_poses(tl[within],tg,pg)
nt,nr=ev.ape2d(g_native,pl[within])
weights=np.r_[np.diff(tg),0.]
high=(tr>.2)&inside;dur=float(weights[high].sum())
longest=0.;begin=None
for i,v in enumerate(high):
 if v and begin is None:begin=tg[i]
 if begin is not None and (not v or i==len(high)-1):longest=max(longest,float(tg[i]-begin));begin=None
# Actual observed TF publishers / parents from this run; no inferred callers.
parents={};poseframes=set();scan_ns=[];poses=0
with (out/'observations.jsonl').open() as f:
 for line in f:
  r=json.loads(line)
  if r['kind']=='tf':
   for x in r['transforms']:
    k=x['child'];parents.setdefault(k,set()).add((x['parent'],r['caller']))
  if r['kind']=='scan_received':scan_ns.append(r['stamp_ns'])
  if r['kind']=='pose':poses+=1;poseframes.add(r['frame'])
bs=[];pending=None;scan_events=[]
for line in (out/'launch.log').read_text(errors='replace').splitlines():
 if 'AUDIT_SCAN ' in line:
  a=line.split('AUDIT_SCAN ',1)[1].split();pending={'seq':int(a[0]),'stamp_ns':int(a[1])*10**9+int(a[2]),'particles_before':int(a[3]),'converged_before':int(a[4])};scan_events.append(pending.copy())
 if 'AUDIT_BEAMS ' in line:
  a=list(map(int,line.split('AUDIT_BEAMS ',1)[1].split()))
  r=dict(zip(['configured_skip','converged','particles','effective_skip','physical_slots','valid_slots','skipped_allocated_slots','skipped_physical_slots','fallback_all'],a));r.update(pending or {});bs.append(r)
metric={'id':run['id'],'sequence':seq,'config':run['spec']['config'],'binary':run['spec']['binary'],'seed':run['spec']['seed'],'status':run['status'],'trajectory_rows':len(tl),'unique_monotonic_finite':True,'official_position_RMSE_m':float(np.sqrt(np.mean(tr**2))),'official_yaw_RMSE_deg':float(np.sqrt(np.mean(rd**2))),'no_endpoint_padding_position_RMSE_m':float(np.sqrt(np.mean(tr[inside]**2))),'native_output_stamp_position_RMSE_m':float(np.sqrt(np.mean(nt**2))),'native_output_stamp_yaw_RMSE_deg':float(np.sqrt(np.mean(np.degrees(nr)**2))),'position_p95_m':float(np.quantile(tr,.95)),'position_max_m':float(tr.max()),'position_high_over_0p2m_duration_s':dur,'longest_high_error_s':longest,'native_time_span_GT_coverage_fraction':float(inside.mean()),'GT_bracketed_support_max_gap_s':support,'max_AMCL_output_gap_s':float(np.diff(tl).max()),'poses_per_front_scan_fraction_not_tracking_rate':len(tl)/json.loads((b/'audit'/f'{seq}_bag.json').read_text())['topics']['/laser_scan_front/scan']['count'],'collector_scan_count':len(scan_ns),'expected_scan_count':json.loads((b/'audit'/f'{seq}_bag.json').read_text())['topics']['/laser_scan_front/scan']['count'],'pose_frames':sorted(poseframes),'TF_parent_and_publisher':{k:sorted(v) for k,v in parents.items()},'processed_sensor_updates':len(scan_events) if scan_events else 'UNKNOWN_installed_binary','beam_diagnostic_events':len(bs),'effective_skipping_events':sum(x['effective_skip'] for x in bs),'fallback_events':sum(x['fallback_all'] for x in bs),'elapsed_wall_s':run['elapsed_wall_s'],'first_pose_stamp':float(tl[0]),'last_pose_stamp':float(tl[-1]),'initialization':'registered single GT initial pose; not global localization'}
np.savez_compressed(out/'offline_errors.npz',time=tg,relative_time=tg-tg[0],position_error=tr,yaw_error_deg=rd,inside_native_span=inside,GT_xy=pg[:,:2,3],est_interpolated_xy=interp[:,:2,3])
(out/'beam_events.json').write_text(json.dumps(bs,indent=2));(out/'sensor_update_events.json').write_text(json.dumps(scan_events,indent=2));(out/'metrics.json').write_text(json.dumps(metric,indent=2));print(json.dumps(metric),flush=True)
# Qualification gates are only technical/time/frame/provenance, never pose-error thresholds.
assert run['status']=='COMPLETE' and run['clean_collector']
assert len(scan_ns)==metric['expected_scan_count'],'collector did not receive all input scans'
assert metric['pose_frames']==['map']
assert metric['native_time_span_GT_coverage_fraction']>=.98,'AMCL output does not span this complete sequence'
assert all(len(set(a for a,c in v))==1 for v in parents.values()),'TF multi-parent'
assert len(parents.get('odom',[]))==1,'map->odom must have exactly one observed publisher'
print('TECHNICAL_RUN_VALID',flush=True)
