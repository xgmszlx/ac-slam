from pathlib import Path
import sys,json,csv,math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image
from scipy.ndimage import distance_transform_edt
from scipy.spatial.transform import Rotation,Slerp
p=Path(__file__).resolve().parents[1]
rows=[];beamstats=[];seed_records={}
for d in sorted((p/'results').glob('offline_*')):
 if not (d/'metrics.json').exists():continue
 m=json.loads((d/'metrics.json').read_text());log=(d/'launch.log').read_text(errors='replace')
 s=[int(x.split('AUDIT_GAUSSIAN_SEED ')[1].split()[0]) for x in log.splitlines() if 'AUDIT_GAUSSIAN_SEED ' in x]
 effective=s[0] if s else 1
 seed_records[d.name]={'nominal_seed':m['seed'],'actual_initial_gaussian_seed':effective,'direct_log':bool(s),'basis':'direct allocator log' if s else 'fixed native pf_pdf_seed increments 0->1; pf_alloc seed is overwritten','all_allocator_seeds':s}
 r={k:m[k] for k in ['id','sequence','config','binary','seed','official_position_RMSE_m','official_yaw_RMSE_deg','position_p95_m','position_max_m','position_high_over_0p2m_duration_s','longest_high_error_s','native_time_span_GT_coverage_fraction','max_AMCL_output_gap_s','trajectory_rows','elapsed_wall_s','processed_sensor_updates','effective_skipping_events','fallback_events']}
 r['actual_initial_gaussian_seed']=effective
 resources=(d/'amcl_resource.txt').read_text();r['amcl_user_cpu_s']=float(resources.split('User time (seconds): ')[1].splitlines()[0]);r['amcl_system_cpu_s']=float(resources.split('System time (seconds): ')[1].splitlines()[0]);r['peak_RSS_KiB']=int(resources.split('Maximum resident set size (kbytes): ')[1].splitlines()[0])
 r['GT_support_le_1s']=m['GT_bracketed_support_max_gap_s']['1.0'];r['GT_support_le_2s']=m['GT_bracketed_support_max_gap_s']['2.0'];rows.append(r)
 events=json.loads((d/'beam_events.json').read_text());active=[b for b in events if b['effective_skip']]
 if active:
  fractions=np.array([b['skipped_physical_slots']/b['physical_slots'] for b in active]);err=np.load(d/'offline_errors.npz');t=np.array([b['stamp_ns']/1e9 for b in active]);native=np.loadtxt(d/'trajectory.txt');gt=np.loadtxt(p/'data/gt'/m['sequence']/'gt_poses.txt');native_xy=np.c_[np.interp(t,native[:,0],native[:,1]),np.interp(t,native[:,0],native[:,2])];gt_xy=np.c_[np.interp(t,gt[:,0],gt[:,1]),np.interp(t,gt[:,0],gt[:,2])];pos=np.linalg.norm(native_xy-gt_xy,axis=1)
  beamstats.append({'id':d.name,'active_events':len(active),'model_events':len(events),'converged_events':sum(b['converged'] for b in events),'physical_skipped_fraction_p50':float(np.median(fractions)),'physical_skipped_fraction_p95':float(np.quantile(fractions,.95)),'physical_skipped_fraction_max':float(fractions.max()),'full_fallback_count':sum(b['fallback_all'] for b in events),'active_while_error_over_0p2m_count':int((pos>.2).sum()),'allocated_slots':100,'physical_slots':sorted(set(b['physical_slots'] for b in events)),'valid_slots_range':[min(b['valid_slots'] for b in events),max(b['valid_slots'] for b in events)]})
with (p/'results/all_run_metrics.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(p/'audit/effective_seed_register.json').write_text(json.dumps(seed_records,indent=2));(p/'results/beam_summary.json').write_text(json.dumps(beamstats,indent=2))
# Basic map-distance diagnostics, OFFLINE only, never supplied to localization.
mapim=np.asarray(Image.open(p/'data/map/map_office.png').convert('L'));occupied=(1-mapim/255.)>.65;dist=distance_transform_edt(~occupied)*.05
h,w=mapim.shape;extent=[-25,-25+w*.05,-25,-25+h*.05];summary={};cache={}
for seq in ['static_0','lt_changes_0']:
 gt=np.loadtxt(p/'data/gt'/seq/'gt_poses.txt');sample=np.load(p/'results'/(seq+'_scan_samples.npz'));times=sample['stamp_ns']/1e9;validt=(times>=gt[0,0])&(times<=gt[-1,0]);times=times[validt];ranges=sample['ranges'][validt];ids=sample['seq'][validt]
 bg=json.loads((p/'audit'/(seq+'_bag.json')).read_text());sensor=bg['scans']['/laser_scan_front/scan'];angles=sensor['angle_min']+np.arange(ranges.shape[1])*sensor['angle_increment'];extr=bg['tf_dynamic']['base_link -> scan_front_link'];ex,ey,_=extr['first_xyz'];qyaw=Rotation.from_quat(extr['first_xyzw']).as_euler('ZYX')[0]
 yaw=Slerp(gt[:,0],Rotation.from_quat(gt[:,4:8]))(times).as_euler('ZYX')[:,0];x=np.interp(times,gt[:,0],gt[:,1]);y=np.interp(times,gt[:,0],gt[:,2]);fractions=[];endpoints=[];dists=[]
 for k,(t,r) in enumerate(zip(times,ranges)):
  valid=np.isfinite(r)&(r>sensor['range_min'])&(r<sensor['range_max']);theta=angles[valid]+yaw[k]+qyaw
  sx=x[k]+math.cos(yaw[k])*ex-math.sin(yaw[k])*ey;sy=y[k]+math.sin(yaw[k])*ex+math.cos(yaw[k])*ey
  xy=np.c_[sx+r[valid]*np.cos(theta),sy+r[valid]*np.sin(theta)];mx=np.floor((xy[:,0]+25)/.05+.5).astype(int);my=np.floor((xy[:,1]+25)/.05+.5).astype(int);inside=(mx>=0)&(mx<w)&(my>=0)&(my<h)
  distance=np.full(len(xy),2.);distance[inside]=dist[h-1-my[inside],mx[inside]];frac=float(np.mean(distance>.5)) if len(distance) else float('nan');fractions.append(frac);endpoints.append(xy);dists.append(distance)
 cache[seq]={'times':times,'ranges':ranges,'ids':ids,'xy':np.c_[x,y],'yaw':yaw,'fractions':np.array(fractions),'endpoints':endpoints,'dists':dists,'angles':angles,'extrinsic':extr,'gt':gt}
 summary[seq]={'OFFLINE_DIAGNOSTIC':True,'fixed_stride':10,'samples':len(times),'disagreement_distance_m':.5,'fraction_p50':float(np.nanmedian(fractions)),'fraction_p95':float(np.nanquantile(fractions,.95)),'limitations':'GT planar base pose + original front extrinsic; nearest prior occupied-cell distance; not true map-change labels, not particle-based native beam-mask statistic.'}
 with (p/'results'/(seq+'_offline_map_disagreement.csv')).open('w') as f:
  cw=csv.writer(f);cw.writerow(['scan_seq','stamp','time_since_GT_start_s','GT_endpoint_fraction_over_0p5m']);cw.writerows(zip(ids,times,times-gt[0,0],fractions))
(p/'results/scan_map_summary.json').write_text(json.dumps(summary,indent=2))
# Only the controlled/dignostic runs in main figures; installed runs remain separate table rows.
colors={'A0':'#555555','A1':'#d95f02','A2':'#1b9e77'}
fig,axs=plt.subplots(3,2,figsize=(13,10),sharex='col')
for col,seq in enumerate(['static_0','lt_changes_0']):
 gt0=cache[seq]['gt'][0,0]
 for r in rows:
  if r['sequence']!=seq or r['binary']!='diagnostic':continue
  d=p/'results'/r['id'];e=np.load(d/'offline_errors.npz');a=r['actual_initial_gaussian_seed'];label=r['config']+' seed '+str(a)
  # Same-seed second A0 is deliberately shown as another line, not relabelled seed1702.
  axs[0,col].plot(e['relative_time'],e['position_error'],color=colors[r['config']],lw=.8,alpha=.75,ls='-' if a==1 else '--',label=label)
  if r['config']=='A2':
   ev=json.loads((d/'beam_events.json').read_text());active=[b for b in ev if b['effective_skip']]
   axs[2,col].plot([b['stamp_ns']/1e9-gt0 for b in active],[b['skipped_physical_slots']/b['physical_slots'] for b in active],color=colors['A2'],ls='-' if a==1 else '--',lw=.8,label='A2 seed '+str(a))
   for b in active:
    if b['fallback_all']:axs[2,col].axvline(b['stamp_ns']/1e9-gt0,c='r',alpha=.5)
 axs[0,col].set_title(seq);axs[0,col].set_ylabel('Position error [m], no alignment');axs[0,col].legend(fontsize=7,ncol=2);axs[0,col].axhline(.2,c='k',ls=':',lw=.8)
 axs[1,col].plot(cache[seq]['times']-gt0,cache[seq]['fractions'],c='#7570b3');axs[1,col].set_ylabel('GT endpoint disagreement >0.5m\nOFFLINE_DIAGNOSTIC')
 axs[2,col].set_ylabel('Native A2 physical slots skipped\n(excludes 9 unused allocation slots)');axs[2,col].set_xlabel('Time since first GT [s]');axs[2,col].legend(fontsize=7)
 for ax in axs[:,col]:ax.grid(alpha=.2)
fig.tight_layout();fig.savefig(p/'figures/main_timelines.png',dpi=160)
# Two diagnostic cases selected by prespecified maximum-error rule. Entire curves above retained.
seq='lt_changes_0';c=cache[seq];a1=p/'results/offline_seed1701_lt_changes_0_A1';a2=p/'results/offline_seed1701_lt_changes_0_A2';err=np.load(a1/'offline_errors.npz');idx=int(np.argmax(err['position_error']));target=err['time'][idx]
# Case2: maximum physical skip (fallback if any), restricted to active updates.
ev=json.loads((a2/'beam_events.json').read_text());ev=[b for b in ev if b['effective_skip']];chosen=next((b for b in ev if b['fallback_all']),max(ev,key=lambda b:b['skipped_physical_slots']/b['physical_slots']))
targets=[target,chosen['stamp_ns']/1e9];cases=[];fig,axs=plt.subplots(1,2,figsize=(12,5.5))
for ax,tt,title in zip(axs,targets,['Maximum A1 position error','First fallback / otherwise maximum A2 skip']):
 k=int(np.argmin(np.abs(c['times']-tt)));t=c['times'][k];xy=c['endpoints'][k];distance=c['dists'][k]
 ax.imshow(mapim,cmap='gray',origin='upper',extent=extent,vmin=0,vmax=255);ax.scatter(xy[:,0],xy[:,1],s=3,c=np.where(distance>.5,'#d95f02','#1b9e77'),label='Scan endpoints at GT (offline)');ax.scatter(*c['xy'][k],marker='*',s=100,c='blue',label='GT base_link')
 info={'selection':title,'target_stamp':float(tt),'nearest_fixed_sample_stamp':float(t),'sample_delta_s':float(t-tt),'GT_map_disagreement_fraction':float(c['fractions'][k]),'estimates':{}}
 for d,label,color in [(a1,'A1','#d95f02'),(a2,'A2','#7570b3')]:
  tr=np.loadtxt(d/'trajectory.txt');xx=float(np.interp(t,tr[:,0],tr[:,1]));yy=float(np.interp(t,tr[:,0],tr[:,2]));ax.scatter(xx,yy,marker='x',s=80,c=color,label=label+' base_link (interpolated)');info['estimates'][label]={'xy':[xx,yy],'xy_error_m':float(np.linalg.norm(np.array([xx,yy])-c['xy'][k]))}
 ax.set_xlim(-15,16);ax.set_ylim(-16,6);ax.set_aspect('equal');ax.set_title(title+'\nt='+format(t-c['gt'][0,0],'.2f')+'s, OFFLINE_DIAGNOSTIC');ax.set_xlabel('map x [m]');ax.set_ylabel('map y [m]');ax.legend(fontsize=6);cases.append(info)
fig.tight_layout();fig.savefig(p/'figures/changed_map_cases.png',dpi=180);(p/'results/case_records.json').write_text(json.dumps(cases,indent=2))
# Repetition facts: do not conflate duplicate seed1 A0 with independent seeds.
repeat={}
for seq in ['static_0','lt_changes_0']:
 for model in ['A0','A1','A2']:
  group=[r for r in rows if r['binary']=='diagnostic' and r['sequence']==seq and r['config']==model]
  values=[r['official_position_RMSE_m'] for r in group];repeat[seq+'_'+model]={'n':len(group),'actual_seeds':[r['actual_initial_gaussian_seed'] for r in group],'RMSE_values_m':values,'range_m':float(max(values)-min(values)) if values else None,'claim':'descriptive only; native internal update selection can differ despite same full bag'}
(p/'results/repeat_summary.json').write_text(json.dumps(repeat,indent=2))
print(json.dumps({'rows':len(rows),'beam_summary':beamstats,'scan_map':summary,'cases':cases},indent=2))
