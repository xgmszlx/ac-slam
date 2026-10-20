from pathlib import Path
import json,csv,re,hashlib,subprocess
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
D=Path(__file__).resolve().parents[1];V=Path('/home/wcqw/ngd_ccl_compat_v2_20261020');E=Path('/media/wcqw/KESU/slam_research/ngd_ccl_compat_v2_20261020');S=E/'NGD-SLAM';H=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
rows=[];details={};inputs=[('M0_01',V/'results/full',V/'evaluation')]+[(t,D/'results'/t,D/'results'/t/'evaluation') for t in ['M0_02','M0_03','M0_04','M0_05']]
for tag,p,ev in inputs:
 run=json.loads((p/'result.json').read_text());log=(p/'stdout.log').read_text();res=(p/'resource.txt').read_text();m=json.loads((ev/'metrics.json').read_text()) if (ev/'metrics.json').exists() else None
 seq='walking' if tag in ['M0_01','M0_02','M0_03'] else 'sitting' if tag=='M0_04' else 'Bonn_box'
 r={'tag':tag,'sequence':seq,'exit':run['exit_status'],'completed':run['completed_frame_calls'],'inputs':run.get('inputs',run.get('input_frames')),'ATE_m':m['ate_m']['rmse'] if m else None,'RPEt_m':m['rpe_1s_translation_m'].get('rmse') if m else None,'RPEr_deg':m['rpe_1s_rotation_deg'].get('rmse') if m else None,'coverage':m['saved_pose_fraction_of_input'] if m else None,'GT_pairs':m['saved_poses_with_gt'] if m else None,'keyframes':m['saved_keyframes'] if m else None,'wall_s':run.get('wall_s',run.get('wall_seconds'))}
 for label,key in [('User time (seconds)','cpu_user_s'),('System time (seconds)','cpu_system_s'),('Maximum resident set size (kbytes)','RSS_KiB')]:
  match=re.search(r'^\s*'+re.escape(label)+r': (.+)$',res,re.M);r[key]=float(match.group(1)) if match else None
 for label,key in [('mean','TrackRGBD_mean_ms'),('median','TrackRGBD_median_ms')]:
  match=re.search(label+r' tracking time: ([\deE.+-]+)',log);r[key]=1000*float(match.group(1)) if match else None
 events=[x for x in log.splitlines() if re.search(r'Creation of new map|Reset|lost|Relocaliz|Not enough matches|First KF',x,re.I)]
 r['map_creation_count']=sum('Creation of new map with id:' in x for x in events);r['LK_insufficient_messages']=sum('Not enough matches' in x for x in events);r['reset_messages']=sum(bool(re.search('Reset',x,re.I)) for x in events)
 details[tag]={'events':events,'online_pose':'NOT_RECORDED','per_frame_state_and_map_id':'NOT_RECORDED','actual_mask_area':'NOT_RECORDED','80_percent_clear_events':'NOT_RECORDED','inliers_and_map_associations':'NOT_RECORDED','detector_age':'NOT_RECORDED'}
 if tag!='M0_01':
  maps=(p/'runtime_libraries.txt').read_text();assert str(E/'lib/libORB_SLAM3.so') in maps and '.so.4.2' not in maps
  if run['exit_status']==0 and run['completed_frame_calls']==r['inputs']:
   assert m and m['duplicate_saved_timestamps']==0 and m['nonincreasing_saved_time_steps']==0
 rows.append(r)
with (D/'results/comparison.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
(D/'results/observable_events.json').write_text(json.dumps(details,indent=2))
walk=[x for x in rows if x['sequence']=='walking'];stats={k:{'min':min(x[k] for x in walk),'median':float(np.median([x[k] for x in walk])),'max':max(x[k] for x in walk)} for k in ['ATE_m','RPEt_m','RPEr_deg','TrackRGBD_mean_ms','wall_s']}
(D/'results/walking_repeat_summary.json').write_text(json.dumps(stats,indent=2))
# Complete trajectory identities are used for metric eligibility, not equated with internal OK states.
old=json.loads((D/'protocol/protection_before.json').read_text());G=lambda a:subprocess.check_output(['git','-C','/home/wcqw/ac-slam']+a,text=True)
changed=[p for p,h in old['files'].items() if H(p)!=h];prot={'protected_files':len(old['files']),'changed_files':changed,'main_head_equal':G(['rev-parse','HEAD'])==old['head'],'main_status_equal':G(['status','--porcelain'])==old['status'],'main_diff_equal':hashlib.sha256(G(['diff']).encode()).hexdigest()==old['diff_sha256']};assert not changed and all(prot[x] for x in ['main_head_equal','main_status_equal','main_diff_equal']);(D/'audit/protection_after.json').write_text(json.dumps(prot,indent=2))
fig,ax=plt.subplots(1,3,figsize=(12.5,3.7));names=[x['tag']+'\n'+x['sequence'] for x in rows];col=['#3b82bf']*3+['#2b9c62','#ce7842']
ax[0].bar(names,[x['ATE_m'] or 0 for x in rows],color=col);ax[0].set(ylabel='Exported ATE RMSE (m)',title='Walking n=3; sitting/box n=1')
ax[1].bar(names,[x['RPEt_m'] or 0 for x in rows],color=col);ax[1].set(ylabel='1 s translation RPE RMSE (m)',title='No scale fitting; coverage in CSV')
ax[2].bar(names,[x['cpu_user_s']+x['cpu_system_s'] for x in rows],color=col);ax[2].set(ylabel='Total user + system CPU (s)',title='All processes; not just TrackRGBD')
for a in ax:a.tick_params(axis='x',labelsize=7)
fig.tight_layout();fig.savefig(D/'figures/baseline_comparison.png',dpi=160);plt.close(fig)
fig,ax=plt.subplots(2,1,figsize=(9.5,6),sharex=False)
for tag,p,ev in inputs:
 if not (ev/'ate.csv').exists():continue
 a=np.genfromtxt(ev/'ate.csv',delimiter=',',names=True);t=a['stamp']-a['stamp'][0];axes=ax[0] if tag in ['M0_01','M0_02','M0_03'] else ax[1];axes.plot(t,a['error_m'],label=tag)
ax[0].set(title='Walking: all three complete runs',ylabel='Exported SE3 ATE (m)');ax[1].set(title='Independent scenes: complete output',ylabel='Exported SE3 ATE (m)',xlabel='Time from first GT-matched output (s)')
for a in ax:a.legend()
fig.tight_layout();fig.savefig(D/'figures/error_timelines.png',dpi=160);plt.close(fig)
print(json.dumps({'runs':rows,'walking':stats},indent=2))
