from pathlib import Path
import csv,json,re
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
P=Path(__file__).resolve().parents[1];conditions=['S0','S1','S2'];allrows={};summary=[];data=json.loads((P/'audit/dataset.json').read_text());t0=data['RGB_range'][0]
for c in conditions:
 d=P/'results'/c;run=json.loads((d/'run.json').read_text());rows=list(csv.DictReader((d/'frame_states.csv').open()));allrows[c]=rows
 valid=[r for r in rows if abs(float(r['frame_stamp'])-float(r['stamp']))<1e-6 and float(r['frame_id'])>=0]
 f=lambda k:np.array([float(x[k]) for x in valid]);rec={'condition':c,'exit':run['exit'],'processed':len(rows),'trace_valid_frames':len(valid),'states':run['states'],'map_ids':run['map_ids'],'max_map_count':max(f('map_count'))}
 for kind in ['online','exported']:
  m=run.get(kind,{});rec[kind+'_identity_gauge_qualified']=m.get('identity_gauge_qualified',False)
  for field,key in [('ate_m','ATE_m'),('rpe_1s_translation_m','RPEt_m'),('rpe_1s_rotation_deg','RPEr_deg')]:rec[kind+'_'+key]=m.get(field,{}).get('rmse');rec[kind+'_'+key+'_n']=m.get(field,{}).get('n',0)
  for field in ['saved_pose_fraction_of_input','saved_gt_matched_fraction_of_input','saved_keyframes','duplicate_saved_timestamps']:rec[kind+'_'+field]=m.get(field)
  rec[kind+'_missing_intervals']=m.get('missing_output_intervals',[])
 for k in ['raw_N','kept_N','mutual_matches','good_2d','bad_2d_rejected','pnp_inliers','both_depth_tested','motion_rejected','depth_invalidated','fallback_candidates','fallback_pose_edges_2d_last','fallback_pose_edges_3d_last','fallback_pose_inlier2d_last','fallback_retained_2d','fallback_retained_3d','retained_2d','retained_3d','fallback_range_reason','fallback_neighborhood_reason','fallback_already_invalid']:
  rec[k+'_sum']=int(f(k).sum());rec[k+'_frames_nonzero']=int(np.count_nonzero(f(k)))
 rec['pnp_success_frames']=int(np.count_nonzero(f('pnp_ok')));rec['track_total_s']=float(f('track_seconds').sum());rec['track_mean_ms']=float(f('track_seconds').mean()*1000);rec['track_p95_ms']=float(np.quantile(f('track_seconds'),.95)*1000)
 rec['frontend_total_s']=None if c=='S0' else float(f('frontend_seconds').sum());rec['final_atlas_points']=int(f('atlas_points')[-1]);rec['final_atlas_keyframes']=int(f('atlas_keyframes')[-1]);rec['wall_s']=run['wall_s']
 resources=(d/'resources.txt').read_text()
 for name,pat in [('user_CPU_s',r'User time \(seconds\):\s*([\d.]+)'),('system_CPU_s',r'System time \(seconds\):\s*([\d.]+)'),('peak_RSS_KiB',r'Maximum resident set size \(kbytes\):\s*(\d+)')]:
  z=re.search(pat,resources);rec[name]=float(z.group(1)) if z else None
 log=(d/'stdout.log').read_text();rec['new_map_log_lines']=[x for x in log.splitlines() if 'Creation of new map' in x or 'reset' in x.lower() or 'New Map' in x];summary.append(rec)
(P/'results/summary.json').write_text(json.dumps(summary,indent=2))
flat=[{k:json.dumps(v) if isinstance(v,(dict,list)) else v for k,v in s.items()} for s in summary]
with (P/'results/summary.csv').open('w') as out:w=csv.DictWriter(out,fieldnames=list(flat[0]),lineterminator='\n');w.writeheader();w.writerows(flat)
fig,ax=plt.subplots(2,3,figsize=(13,7));x=np.arange(3);width=.34
for j,(title,key,unit) in enumerate([('ATE','ATE_m','m'),('1-second translation RPE','RPEt_m','m'),('Exact-input pose coverage','saved_pose_fraction_of_input','fraction')]):
 for off,kind,color in [(-width/2,'online','#3878ac'),(width/2,'exported','#d78e28')]:
  val=[s.get(kind+'_'+key) for s in summary];ax[0,j].bar(x+off,[v if v is not None else np.nan for v in val],width,label=kind,color=color)
 ax[0,j].set(xticks=x,xticklabels=conditions,title=title,ylabel=unit);ax[0,j].legend()
for c in conditions:
 d=P/'results'/c/'evaluation'/'online';f=d/'ate.csv'
 if f.exists():
  a=np.genfromtxt(f,delimiter=',',skip_header=1);ax[1,0].plot(a[:,0]-t0,a[:,1],label=c)
 rows=allrows[c];tt=np.array([float(r['stamp']) for r in rows])-t0
 ax[1,1].plot(tt,[float(r['retained_2d']) for r in rows],label=c)
 ax[1,2].plot(tt,np.array([float(r['track_seconds']) for r in rows])*1000,label=c)
ax[1,0].set(xlabel='input time (s)',ylabel='SE3 online ATE (m)',title='Complete online errors')
ax[1,1].set(xlabel='input time (s)',ylabel='native retained associations / frame',title='2D associations (not all optimizer edges)')
ax[1,2].set(xlabel='input time (s)',ylabel='TrackRGBD (ms)',title='Track cost includes screening')
for a in ax[1]:a.legend()
fig.suptitle('Bonn moving_obstructing_box: one run per condition; no significance or motion-label claim');fig.tight_layout();fig.savefig(P/'figures/comparison.png',dpi=160);plt.close(fig)
fig,ax=plt.subplots(3,1,figsize=(11,8),sharex=True)
for c in ['S1','S2']:
 rows=allrows[c];tt=np.array([float(r['stamp']) for r in rows])-t0
 ax[0].plot(tt,[float(r['motion_rejected']) for r in rows],label=c+' 3D-motion rejection')
 ax[1].plot(tt,[float(r['bad_2d_rejected']) for r in rows],label=c+' bad 2D rejection')
rows=allrows['S2'];tt=np.array([float(r['stamp']) for r in rows])-t0
for key,label in [('depth_invalidated','positive depth invalidated'),('fallback_pose_edges_2d_last','tagged native mono edges (last call)'),('fallback_pose_inlier2d_last','tagged mono inliers (last call)')]:ax[2].plot(tt,[float(r[key]) for r in rows],label=label)
for a in ax:a.legend();a.set(ylabel='observation events / frame')
ax[0].set_title('Native frontend actions and S2 actual pose-edge acceptance; no physical motion truth')
ax[2].set(xlabel='input time (s)');fig.tight_layout();fig.savefig(P/'figures/actions_and_edges.png',dpi=160);plt.close(fig)
print(json.dumps([{k:v for k,v in s.items() if k in ['condition','exit','online_ATE_m','exported_ATE_m','online_RPEt_m','exported_RPEt_m','pnp_success_frames','motion_rejected_sum','depth_invalidated_sum','fallback_pose_edges_2d_last_sum','fallback_pose_inlier2d_last_sum','retained_2d_sum','track_mean_ms','states','map_ids']} for s in summary],indent=2))
