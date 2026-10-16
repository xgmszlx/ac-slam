from pathlib import Path
import json,re,csv,math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image
p=Path(__file__).resolve().parents[1];b=Path('/home/wcqw/lilocbench_amcl_validation_20261016');design=json.loads((p/'protocol/design_frozen.json').read_text())
paths={'A0 ON':b/'results/offline_seed1702_lt_changes_0_A0','A1 ON':b/'results/offline_seed1702_lt_changes_0_A1','A1 R0':p/'results/A1_R0','A2 ON':b/'results/offline_seed1702_lt_changes_0_A2','A2 R0':p/'results/A2_R0'}
gt0=np.load(paths['A1 ON']/'offline_errors.npz')['time'][0]
def dump(name,obj):
 def clean(x):
  if isinstance(x,dict):return {k:clean(v) for k,v in x.items()}
  if isinstance(x,list):return [clean(v) for v in x]
  if isinstance(x,(float,np.floating)) and not np.isfinite(x):return None
  return x
 (p/name).write_text(json.dumps(clean(obj),indent=2,allow_nan=False))
def csvout(name,rows):
 with (p/name).open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def intervals(t,mask,min_duration=3.):
 out=[];start=None
 for i,v in enumerate(mask):
  if v and start is None:start=i
  if start is not None and (not v or i==len(mask)-1):
   dur=float(t[i]-t[start])
   if dur>=min_duration:out.append({'start_s':float(t[start]-gt0),'end_s':float(t[i]-gt0),'duration_s':dur})
   start=None
 return out
summary=[];onsets={};stats={};events={};fair={};covars={};clouds={}
for name,root in paths.items():
 m=json.loads((root/'metrics.json').read_text());z=np.load(root/'offline_errors.npz');t=z['time'];e=z['position_error'];inside=z['inside_native_span'];high=(e>.2)&inside
 si=intervals(t,high);healthy=intervals(t,(e<=.2)&inside)
 onsets[name]={'first_over_0p2_s':float(t[np.flatnonzero(high)[0]]-gt0) if high.any() else None,'first_persistent':si[0] if si else None,'all_persistent_intervals':si,'first_reapproach_after_persistent':next((x for x in healthy if si and x['start_s']>=si[0]['end_s']),None),'healthy_intervals_ge_3s':healthy}
 res=(root/'amcl_resource.txt').read_text();rr={}
 for k,pattern in [('user_cpu_s',r'User time \(seconds\): ([\d.]+)'),('system_cpu_s',r'System time \(seconds\): ([\d.]+)'),('peak_RSS_KiB',r'Maximum resident set size \(kbytes\): (\d+)')]:rr[k]=float(re.search(pattern,res)[1])
 summary.append(dict(condition=name,**{k:m[k] for k in ['official_position_RMSE_m','official_yaw_RMSE_deg','position_p95_m','position_max_m','position_high_over_0p2m_duration_s','longest_high_error_s','native_time_span_GT_coverage_fraction','max_AMCL_output_gap_s','trajectory_rows','processed_sensor_updates','collector_scan_count','effective_skipping_events','fallback_events','elapsed_wall_s']},**rr))
 covars[name]=[];clouds[name]=[]
 for line in (root/'observations.jsonl').open():
  r=json.loads(line)
  if r['kind']=='pose':covars[name].append({'time_s':r['stamp_ns']/1e9-gt0,'xy_trace_cov_m2':r['covariance'][0]+r['covariance'][7],'yaw_var_rad2':r['covariance'][35]})
  elif r['kind']=='particles_sampled_1Hz':
   xy=np.array(r['particles'])[:,:2];clouds[name].append({'cloud_index':len(clouds[name]),'wall_stamp_ns':r['stamp_ns'],'count':len(xy),'unweighted_xy_mean':xy.mean(0).tolist(),'unweighted_xy_cov_trace':float(np.var(xy,axis=0).sum()),'scan_identity':'UNKNOWN_wall_time_sample'})
 if 'R0' not in name:continue
 rows=[];cur=None;begin=None
 log=(root/'launch.log').read_text(errors='replace');assert re.findall(r'AUDIT_GAUSSIAN_SEED (\d+)',log)==['1702'];assert 'extrapolat' not in log.lower()
 for line in log.splitlines():
  if 'AUDIT_SCAN ' in line:
   a=list(map(int,line.split('AUDIT_SCAN ',1)[1].split()));cur=dict(seq=a[0],stamp_ns=a[1]*10**9+a[2],particles_before=a[3],converged_before=a[4]);cur['time_s']=cur['stamp_ns']/1e9-gt0
  elif 'RECOVERY_SENSOR ' in line:
   a=list(map(float,line.split('RECOVERY_SENSOR ',1)[1].split()));assert cur is not None
   cur.update(dict(zip(['total_sensor_weight','sensor_N','ESS_before_resample','w_slow_before_resample','w_fast_before_resample','max_normalized_weight','sum_normalized_weights','total_zero','total_nonfinite','nonfinite_normalized_count'],a)));cur['ESS_over_N']=a[2]/a[1]
  elif 'RECOVERY_RESAMPLE_BEGIN ' in line:
   a=list(map(float,line.split('RECOVERY_RESAMPLE_BEGIN ',1)[1].split()));cur.update(dict(zip(['w_diff','resample_w_slow','resample_w_fast','resample_N_before','resample_ESS_before'],a)))
  elif 'RECOVERY_RESAMPLE_END ' in line:
   a=list(map(float,line.split('RECOVERY_RESAMPLE_END ',1)[1].split()));cur.update(dict(zip(['random_particles','particles_after','w_slow_after','w_fast_after','clusters_after'],a)));rows.append(cur.copy());cur=None
 assert len(rows)==708 and cur is None
 ev=json.loads((root/'sensor_update_events.json').read_text());assert [r['stamp_ns'] for r in rows]==[r['stamp_ns'] for r in ev]
 events[name]=rows;csvout('results/'+name.replace(' ','_')+'_recovery_events.csv',rows)
 er=np.interp([r['stamp_ns']/1e9 for r in rows],t,e)
 finite=np.array([math.isfinite(r['ESS_before_resample']) for r in rows]);ratio=np.array([r['ESS_over_N'] for r in rows]);n=np.array([r['particles_after'] for r in rows]);w=np.array([r['max_normalized_weight'] for r in rows])
 stats[name]={'resample_events':len(rows),'w_diff_range':[min(r['w_diff'] for r in rows),max(r['w_diff'] for r in rows)],'random_particle_total':sum(int(r['random_particles']) for r in rows),'events_with_random_particles':sum(r['random_particles']>0 for r in rows),'w_slow_range':[min(r['w_slow_after'] for r in rows),max(r['w_slow_after'] for r in rows)],'w_fast_range':[min(r['w_fast_after'] for r in rows),max(r['w_fast_after'] for r in rows)],'total_zero_count':sum(r['total_zero'] for r in rows),'total_nonfinite_count':sum(r['total_nonfinite'] for r in rows),'normalized_weight_nonfinite_events':sum(r['nonfinite_normalized_count']>0 for r in rows),'ESS_nonfinite_count':int((~finite).sum()),'finite_ESS_min_p50_p95':np.quantile([r['ESS_before_resample'] for r in rows if math.isfinite(r['ESS_before_resample'])],[0,.5,.95]).tolist(),'finite_ESS_over_N_min_p50_p95':np.quantile(ratio[finite],[0,.5,.95]).tolist(),'finite_ESS_over_N_lt_0p1_count':int((ratio[finite]<.1).sum()),'max_normalized_weight_p50_p95_max':np.quantile(w,[.5,.95,1]).tolist(),'particles_after_min_p50_max':np.quantile(n,[0,.5,1]).tolist(),'first_update':rows[0],'zero_total_events':[{**r,'offline_error_m':float(ee)} for r,ee in zip(rows,er) if r['total_zero']],'ESS_caution':'ESS is before resampling, not uniform post-resampling weights; infinite value is native zero-total bookkeeping, not valid high ESS'}
 old=json.loads((paths[name.replace('R0','ON')]/'sensor_update_events.json').read_text());new=ev
 op=json.loads((paths[name.replace('R0','ON')]/'parameters.json').read_text());np_=json.loads((root/'parameters.json').read_text());after=json.loads((root/'parameters_after.json').read_text())
 a=np.loadtxt(paths[name.replace('R0','ON')]/'trajectory.txt');c=np.loadtxt(root/'trajectory.txt');equal=np.all(a==c,axis=1);div=np.flatnonzero(~equal)
 fair[name]={'actual_gaussian_seed':1702,'sensor_update_stamps_and_seq_equal':[(r['seq'],r['stamp_ns']) for r in old]==[(r['seq'],r['stamp_ns']) for r in new],'all_708_output_stamps_equal':bool(np.array_equal(a[:,0],c[:,0])),'parameter_diffs':{k:[op.get(k),v] for k,v in np_.items() if op.get(k)!=v},'params_unchanged_during_run':np_==after,'identical_trajectory_prefix_rows':int(div[0]) if len(div) else len(c),'first_exact_output_difference_s':float(c[div[0],0]-gt0) if len(div) else None,'old_ON_recovery_event_times':'UNKNOWN','old_ON_ESS':'UNKNOWN','new_zero_total_count':stats[name]['total_zero_count']}
 assert fair[name]['sensor_update_stamps_and_seq_equal'] and fair[name]['all_708_output_stamps_equal'] and fair[name]['params_unchanged_during_run'];assert set(fair[name]['parameter_diffs'])=={'recovery_alpha_slow','recovery_alpha_fast'}
 csvout('results/'+name.replace(' ','_')+'_pose_covariance.csv',covars[name])
csvout('results/comparison_metrics.csv',summary);dump('results/onsets.json',onsets);dump('results/recovery_summary.json',stats);dump('audit/fairness.json',fair);dump('results/cloud_samples_summary.json',clouds)
# Plot all complete timelines; old N is pre-sensor-update and not old ESS.
colors={'A0 ON':'#555555','A1 ON':'#d55e00','A1 R0':'#0072b2','A2 ON':'#cc79a7','A2 R0':'#009e73'}
fig,ax=plt.subplots(4,1,figsize=(12,12),sharex=True)
for name,root in paths.items():
 z=np.load(root/'offline_errors.npz');ax[0].plot(z['relative_time'],z['position_error'],label=name,color=colors[name],lw=1)
 if name=='A0 ON':continue
 ev=json.loads((root/'sensor_update_events.json').read_text());ax[1].plot([r['stamp_ns']/1e9-gt0 for r in ev],[r['particles_before'] for r in ev],color=colors[name],label=name,lw=.8)
 if 'R0' in name:
  rows=events[name];times=np.array([r['time_s'] for r in rows]);ratio=np.array([r['ESS_over_N'] for r in rows]);ax[2].plot(times,np.where(np.isfinite(ratio),ratio,np.nan),color=colors[name],label=name,lw=.8)
  for r in rows:
   if r['total_zero']:ax[2].axvline(r['time_s'],color='r',ls='--',label='zero weight / infinite stored ESS')
 if name.startswith('A2'):
  be=json.loads((root/'beam_events.json').read_text());act=[r for r in be if r['effective_skip']];ax[3].plot([r['stamp_ns']/1e9-gt0 for r in act],[r['skipped_physical_slots']/r['physical_slots'] for r in act],color=colors[name],label=name,lw=.8)
  for r in be:
   if r['fallback_all']:ax[3].axvline(r['stamp_ns']/1e9-gt0,color='r',ls='--',label='A2 R0 full fallback')
ax[0].axhline(.2,color='k',ls=':',lw=.8);ax[0].set_ylabel('Position error (m)');ax[1].set_ylabel('Particles before update');ax[2].set_ylabel('Pre-resampling ESS / N');ax[3].set_ylabel('Physical slots masked');ax[3].set_xlabel('Seconds from first GT stamp')
for a in ax:a.grid(alpha=.25);a.legend(ncol=3,fontsize=8)
ax[2].set_ylim(0,1.05);fig.suptitle('Same input / actual Gaussian seed 1702; ON events and ESS not recorded historically');fig.tight_layout();fig.savefig(p/'figures/recovery_timelines.png',dpi=150);plt.close(fig)
fig,ax=plt.subplots(2,2,figsize=(12,10));img=np.asarray(Image.open(b/'data/map/map_office.png'));extent=[-25,-25+img.shape[1]*.05,-25,-25+img.shape[0]*.05]
for a,name in zip(ax.flat,['A1 ON','A1 R0','A2 ON','A2 R0']):
 root=paths[name];z=np.load(root/'offline_errors.npz');a.imshow(img,cmap='gray',origin='upper',extent=extent,alpha=.5)
 a.plot(z['GT_xy'][:,0],z['GT_xy'][:,1],'k-',lw=1,label='GT (offline only)');a.plot(z['est_interpolated_xy'][:,0],z['est_interpolated_xy'][:,1],color=colors[name],lw=.8,label=name);a.set_title(name);a.axis('equal');a.set_xlim(-25,25);a.set_ylim(-25,25);a.legend(fontsize=8);a.set_xlabel('map x (m)');a.set_ylabel('map y (m)')
fig.tight_layout();fig.savefig(p/'figures/trajectories.png',dpi=140);plt.close(fig)
# Exact first error onset positions from official interpolation, complete 0-60 s segment retained.
fig,ax=plt.subplots(2,1,figsize=(12,7),sharex=True)
for name,root in paths.items():
 z=np.load(root/'offline_errors.npz');m=z['relative_time']<=60
 ax[0].plot(z['relative_time'][m],z['position_error'][m],color=colors[name],label=name)
 if name=='A0 ON':continue
 cc=covars[name];x=np.array([r['time_s'] for r in cc]);m=x<=60
 ax[1].plot(x[m],np.array([r['xy_trace_cov_m2'] for r in cc])[m],color=colors[name],label=name)
ax[0].axhline(.2,color='k',ls=':');ax[0].set_ylabel('Position error (m)');ax[1].set_ylabel('Reported global XY covariance trace');ax[1].set_yscale('symlog',linthresh=.001);ax[1].set_xlabel('Seconds from first GT stamp');ax[0].legend(ncol=3);ax[0].set_title('First 60 seconds (fixed post-run display, not event selection)')
for a in ax:a.grid(alpha=.25)
fig.tight_layout();fig.savefig(p/'figures/onset_and_covariance.png',dpi=150);plt.close(fig)
print(json.dumps({'onsets':onsets,'recovery':stats,'fairness':fair},indent=2))
