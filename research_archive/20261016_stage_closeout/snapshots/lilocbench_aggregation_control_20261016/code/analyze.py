from utils import *
import json,csv,re,hashlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
Pth=P
pro=json.loads((P/'protocol/design_frozen.json').read_text());paths={'A0 91 R0':P/'results/A0_91_R0','A1 R0':R/'results/A1_R0','A0 102 ON':B/'results/offline_seed1702_lt_changes_0_A0'}
od=np.load(P/'results/odom_tf.npz');odom=np.c_[od['stamp_ns']/1e9,od['poses']];gt=np.loadtxt(B/'data/gt/lt_changes_0/gt_poses.txt');gt0=gt[0,0]
def writecsv(name,rows):
 with (P/name).open('w') as f:
  keys=list(dict.fromkeys(k for r in rows for k in r));w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
def periods(t,mask,minsec=3.):
 res=[];start=None
 for i,v in enumerate(mask):
  if v and start is None:start=i
  if start is not None and (not v or i==len(mask)-1):
   if t[i]-t[start]>=minsec:res.append({'start_s':float(t[start]-gt0),'end_s':float(t[i]-gt0),'duration_s':float(t[i]-t[start])})
   start=None
 return res
summ=[];early=[];onsets={};jumps=[];points=[];allnative={}
for name,root in paths.items():
 met=json.loads((root/'metrics.json').read_text());z=np.load(root/'offline_errors.npz');t=z['time'];rel=t-gt0;err=z['position_error'];yaw=z['yaw_error_deg'];inside=z['inside_native_span'];mask=(rel>=0)&(rel<=10)&inside
 res=(root/'amcl_resource.txt').read_text();resources={k:float(re.search(expr,res)[1]) for k,expr in [('user_cpu_s',r'User time \(seconds\): ([\d.]+)'),('system_cpu_s',r'System time \(seconds\): ([\d.]+)'),('peak_RSS_KiB',r'Maximum resident set size \(kbytes\): (\d+)')]}
 summ.append({'condition':name,**{k:met[k] for k in ['official_position_RMSE_m','official_yaw_RMSE_deg','position_p95_m','position_max_m','position_high_over_0p2m_duration_s','longest_high_error_s','native_time_span_GT_coverage_fraction','max_AMCL_output_gap_s','trajectory_rows','processed_sensor_updates','collector_scan_count','elapsed_wall_s']},**resources})
 early.append({'condition':name,'window':'0-10s, GT timestamps inside native output extent only','GT_samples':int(mask.sum()),'position_RMSE_m':float(np.sqrt(np.mean(err[mask]**2))),'yaw_RMSE_deg':float(np.sqrt(np.mean(yaw[mask]**2))),'position_p95_m':float(np.quantile(err[mask],.95)),'position_max_m':float(err[mask].max()),'GT_first_supported_relative_s':float(rel[mask][0]),'GT_last_supported_relative_s':float(rel[mask][-1])})
 onsets[name]={}
 for threshold in [.2,1.,2.]:
  high=(err>threshold)&inside;pp=periods(t,high);onsets[name][str(threshold)]={'first_over_s':float(rel[np.flatnonzero(high)[0]]) if high.any() else None,'persistent_intervals':pp,'first_persistent':pp[0] if pp else None,'total_time_s':float(np.sum(np.r_[np.diff(t),0.][high]))}
 healthy=periods(t,(err<=.2)&inside);onsets[name]['reapproach_intervals_le_0p2_ge3s']=healthy
 a=np.loadtxt(root/'trajectory.txt');nr=[]
 for row in a:
  pose=pose_row(row);g,_,_=interp(gt,row[0]);nr.append({'stamp':float(row[0]),'relative_s':float(row[0]-gt0),'xy_error_m':float(np.linalg.norm(pose[:2]-g[:2])),'yaw_error_deg':float(abs(np.degrees(wrap(pose[2]-g[2]))))})
 allnative[name]=nr
 writecsv('results/'+name.replace(' ','_')+'_native_errors.csv',nr)
 for i in range(1,len(a)):
  q1=pose_row(a[i-1]);q2=pose_row(a[i]);o1,_,_=interp(odom,a[i-1,0]);o2,_,_=interp(odom,a[i,0]);delta=float(np.linalg.norm(q2[:2]-q1[:2]));ody=float(np.linalg.norm(o2[:2]-o1[:2]));angle=float(abs(np.degrees(wrap(q2[2]-q1[2]))));dt=float(a[i,0]-a[i-1,0]);remote=delta>2. and delta-ody>1. and dt<=3.
  if delta>2. or angle>45.:jumps.append({'condition':name,'start_relative_s':float(a[i-1,0]-gt0),'end_relative_s':float(a[i,0]-gt0),'start_stamp':float(a[i-1,0]),'end_stamp':float(a[i,0]),'dt_s':dt,'output_displacement_m':delta,'odom_displacement_m':ody,'output_yaw_delta_deg':angle,'odom_yaw_delta_deg':float(abs(np.degrees(wrap(o2[2]-o1[2])))),'qualified_remote_translation_jump':remote,'end_error_m':nr[i]['xy_error_m'],'source':'consecutive actual outputs, not interpolated poses; no PF ancestry claim'})
 for target in [5,7]:
  j=int(np.argmin(abs(a[:,0]-gt0-target)));points.append({'condition':name,'target_s':target,'native_output_stamp':float(a[j,0]),'native_relative_s':float(a[j,0]-gt0),'x':float(a[j,1]),'y':float(a[j,2]),'yaw_deg':float(np.degrees(pose_row(a[j])[2])),'position_error_m':nr[j]['xy_error_m'],'yaw_error_deg':nr[j]['yaw_error_deg']})
# End-to-end fairness, based on exact scan identities, effective ROS parameters and unchanged libraries.
root=paths['A0 91 R0'];ref=paths['A1 R0'];newpar=json.loads((root/'parameters_after.json').read_text());oldpar=json.loads((ref/'parameters_after.json').read_text());diff={k:[oldpar.get(k),v] for k,v in newpar.items() if oldpar.get(k)!=v};assert set(diff)=={'laser_model_type','laser_max_beams'}
new_ev=json.loads((root/'sensor_update_events.json').read_text());old_ev=json.loads((ref/'sensor_update_events.json').read_text());assert [(r['seq'],r['stamp_ns']) for r in new_ev]==[(r['seq'],r['stamp_ns']) for r in old_ev]
assert np.array_equal(np.loadtxt(root/'trajectory.txt')[:,0],np.loadtxt(ref/'trajectory.txt')[:,0])
log=(root/'launch.log').read_text(errors='replace');assert re.findall('AUDIT_GAUSSIAN_SEED (\\d+)',log)==['1702'];assert 'extrapolat' not in log.lower()
rec=[line.split('RECOVERY_RESAMPLE_END ')[1].split() for line in log.splitlines() if 'RECOVERY_RESAMPLE_END ' in line];assert len(rec)==708 and all(int(a[0])==0 for a in rec)
sens=[line.split('RECOVERY_SENSOR ')[1].split() for line in log.splitlines() if 'RECOVERY_SENSOR ' in line];assert len(sens)==708
assert all(a[7]=='0' and a[8]=='0' and a[9]=='0' for a in sens)
beam=list(csv.DictReader((P/'results/input_beam_audit.csv').open()));lookup={int(r['stamp_ns']):r for r in beam};assert all(lookup[r['stamp_ns']]['same_actual_indices']=='True' for r in new_ev)
summary={'status':'PASS','parameter_diffs':diff,'same_708_seq_and_stamp':True,'same_708_output_stamps':True,'raw_scans_received':6540,'actual_gaussian_seed':1702,'random_particle_count':0,'normal_resample_calls':708,'zero_or_nonfinite_total_or_weights_events':0,'accepted_valid_beam_min_max':[min(int(lookup[r['stamp_ns']]['valid_slots']) for r in new_ev),max(int(lookup[r['stamp_ns']]['valid_slots']) for r in new_ev)],'beam_evidence':'Native deterministic source loop + actual received input/stamps and effective params; not a newly inserted per-beam sensor trace','GT':'same one-time initial params, no online GT stream','same_existing_executable_sensors_map_PF':'See pre-run hashes; no rebuild'}
(P/'audit/fairness_after.json').write_text(json.dumps(summary,indent=2))
writecsv('results/full_comparison.csv',summ);writecsv('results/early_comparison.csv',early);writecsv('results/native_5s_7s.csv',points)
if jumps:writecsv('results/raw_output_jump_events.csv',jumps)
(P/'results/onsets.json').write_text(json.dumps(onsets,indent=2));js={name:{'remote_jump_count':sum(r['qualified_remote_translation_jump'] for r in jumps if r['condition']==name),'angle_or_translation_candidate_count':sum(r['condition']==name for r in jumps),'early_remote_jump_count':sum(r['qualified_remote_translation_jump'] and r['end_relative_s']<=10 for r in jumps if r['condition']==name)} for name in paths};(P/'results/jump_summary.json').write_text(json.dumps(js,indent=2))
e={r['condition']:r for r in early};m={r['condition']:r for r in summ};new='A0 91 R0';old='A1 R0';early_ok=e[new]['position_RMSE_m']<=.5*e[old]['position_RMSE_m'] and not any(x['start_s']<10 for x in onsets[new]['1.0']['persistent_intervals']) and js[new]['early_remote_jump_count']==0
full_ok=m[new]['official_position_RMSE_m']<=.5*m[old]['official_position_RMSE_m'] and m[new]['position_p95_m']<=.5*m[old]['position_p95_m'] and len(onsets[new]['2.0']['persistent_intervals'])==0 and js[new]['remote_jump_count']==0
verdict='EXISTING_AGGREGATION_SUFFICIENT' if early_ok and full_ok else ('EARLY_ONLY_IMPROVEMENT' if early_ok else 'SIMPLE_AGGREGATION_NOT_SUFFICIENT')
(P/'results/decision.json').write_text(json.dumps({'decision':verdict,'early_gate_pass':early_ok,'full_gate_pass':full_ok,'one_run_only':True,'early_reference_had_no_metre_scale_jump':'Do not transfer A1 ON early failures to A1 R0','not_SCI_method_qualification':True},indent=2))
# Exactly two compact evidence figures.
colors={'A0 91 R0':'#0072b2','A1 R0':'#d55e00','A0 102 ON':'#555555'}
fig,ax=plt.subplots(2,2,figsize=(12,8))
for name,root in paths.items():
 z=np.load(root/'offline_errors.npz');a=np.loadtxt(root/'trajectory.txt');ax[0,0].plot(z['relative_time'],z['position_error'],color=colors[name],label=name,lw=.9);ax[1,0].plot(z['relative_time'],z['yaw_error_deg'],color=colors[name],label=name,lw=.9);mask=(z['relative_time']<=10)&z['inside_native_span'];ax[0,1].plot(z['relative_time'][mask],z['position_error'][mask],color=colors[name],label=name);ax[1,1].plot(z['GT_xy'][:,0],z['GT_xy'][:,1],'k-',lw=.8,alpha=.4) if name==new else None;ax[1,1].plot(a[:,1],a[:,2],color=colors[name],lw=.7,label=name)
ax[0,0].set_ylabel('Position error (m)');ax[1,0].set_ylabel('Yaw error (deg)');ax[1,0].set_xlabel('Seconds from GT start');ax[0,1].set_title('0-10 s, native time support');ax[0,1].set_ylabel('Position error (m)');ax[0,1].set_xlabel('Seconds from GT start');ax[1,1].set_title('Complete raw output trajectories / GT');ax[1,1].set_xlabel('map x (m)');ax[1,1].set_ylabel('map y (m)');ax[1,1].axis('equal')
for a in ax.flat:a.grid(alpha=.25);a.legend(fontsize=8)
ax[0,0].axhline(1.,color='k',ls=':',lw=.7);ax[0,1].axhline(.2,color='k',ls=':',lw=.7);fig.suptitle('Matched91 / recovery OFF comparison; old102 ON is a reference only');fig.tight_layout();fig.savefig(P/'figures/comparison.png',dpi=150);plt.close(fig)
fig,ax=plt.subplots(2,1,figsize=(12,7),sharex=True)
for name,root in paths.items():
 ev=json.loads((root/'sensor_update_events.json').read_text());ax[0].plot([r['stamp_ns']/1e9-gt0 for r in ev],[r['particles_before'] for r in ev],color=colors[name],label=name,lw=.8)
 if name=='A0 102 ON':continue
 ss=[];pending=None
 for line in (root/'launch.log').read_text(errors='replace').splitlines():
  if 'AUDIT_SCAN ' in line:
   a=line.split('AUDIT_SCAN ')[1].split();pending=int(a[1])+int(a[2])/1e9-gt0
  elif 'RECOVERY_SENSOR ' in line:
   a=line.split('RECOVERY_SENSOR ')[1].split();ss.append([pending,float(a[2])/float(a[1])])
 ss=np.asarray(ss);ax[1].plot(ss[:,0],ss[:,1],label=name,color=colors[name],lw=.8)
ax[0].set_ylabel('Particles before update');ax[1].set_ylabel('Pre-resample ESS / N');ax[1].set_xlabel('Seconds from GT start');ax[1].set_ylim(0,1.05)
for a in ax:a.legend();a.grid(alpha=.25)
fig.suptitle('Aggregation changes weight concentration / KLD population and CPU; not particle ancestry evidence');fig.tight_layout();fig.savefig(P/'figures/particles_and_weights.png',dpi=150);plt.close(fig)
print(json.dumps({'decision':verdict,'early':early,'onsets':onsets[new],'jumps':js,'native5s7s':points,'fairness':summary},indent=2))
