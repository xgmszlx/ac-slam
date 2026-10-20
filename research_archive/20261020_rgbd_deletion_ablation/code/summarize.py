from pathlib import Path
import json,csv,re
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
N=Path(__file__).resolve().parents[1];O=Path('/home/wcqw/passive_rgbd_combo_20261019/e2e_20261020');cases=[('S0_01',O/'results/S0'),('S0_02',N/'results/S0'),('S1_01',O/'results/S1'),('E1',N/'results/E1'),('E2',N/'results/E2')];summary=[];traces={}
for label,d in cases:
 run=json.loads((d/'run.json').read_text());rows=list(csv.DictReader((d/'frame_states.csv').open()));valid=[r for r in rows if abs(float(r['stamp'])-float(r['frame_stamp']))<1e-6 and float(r['frame_id'])>=0];traces[label]=rows;f=lambda k:np.array([float(x[k]) for x in valid]);r={'condition':label,'source':str(d),'exit':run['exit'],'processed':len(rows),'valid_trace_frames':len(valid),'states':run['states'],'map_ids':run['map_ids'],'map_count_max':int(f('map_count').max())}
 for kind in ['online','exported']:
  m=run[kind];r[kind+'_identity_qualified']=m.get('identity_gauge_qualified',False)
  for key,out in [('ate_m','ATE_m'),('rpe_1s_translation_m','RPEt_m'),('rpe_1s_rotation_deg','RPEr_deg')]:r[kind+'_'+out]=m.get(key,{}).get('rmse');r[kind+'_'+out+'_n']=m.get(key,{}).get('n',0)
  for key in ['saved_pose_fraction_of_input','saved_gt_matched_fraction_of_input','duplicate_saved_timestamps','missing_output_intervals']:r[kind+'_'+key]=m.get(key)
 for key in ['raw_N','kept_N','mutual_matches','good_2d','bad_2d_rejected','motion_rejected','pnp_inliers','both_depth_tested','depth_invalidated','retained_2d','retained_3d']:
  r[key+'_sum']=int(f(key).sum())
 r['deferred_bad_2d_candidates']=r['mutual_matches_sum']-r['good_2d_sum']-r['bad_2d_rejected_sum']
 r['actual_total_deleted']=r['raw_N_sum']-r['kept_N_sum'];r['pnp_success_frames']=int(np.count_nonzero(f('pnp_ok')));r['pnp_inliers_mean_success']=float(f('pnp_inliers')[f('pnp_ok')>0].mean()) if r['pnp_success_frames'] else None
 r['track_total_s']=float(f('track_seconds').sum());r['track_mean_ms']=float(f('track_seconds').mean()*1000);r['track_p95_ms']=float(np.quantile(f('track_seconds'),.95)*1000);r['frontend_total_s']=None if label.startswith('S0') else float(f('frontend_seconds').sum());r['last_map_points']=int(f('atlas_points')[-1]);r['last_keyframes']=int(f('atlas_keyframes')[-1]);r['wall_s']=run['wall_s'];r['max_output_gap_ms']=float(np.diff(f('stamp')).max()*1000)
 resource=(d/'resources.txt').read_text()
 for name,pattern in [('user_CPU_s',r'User time \(seconds\):\s*([\d.]+)'),('system_CPU_s',r'System time \(seconds\):\s*([\d.]+)'),('RSS_KiB',r'Maximum resident set size \(kbytes\):\s*(\d+)')]:r[name]=float(re.search(pattern,resource).group(1))
 r['total_CPU_s']=r['user_CPU_s']+r['system_CPU_s'];log=(d/'stdout.log').read_text();r['map_or_reset_log']=[s for s in log.splitlines() if 'Creation of new map' in s or 'reset' in s.lower() or 'New Map' in s];summary.append(r)
(N/'results/comparison.json').write_text(json.dumps(summary,indent=2))
with (N/'results/comparison.csv').open('w') as out:
 w=csv.DictWriter(out,fieldnames=list(summary[0]),lineterminator='\n');w.writeheader();w.writerows([{k:json.dumps(v) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in summary])
base=summary[:2];ranges={k:{'n':2,'min':min(s[k] for s in base),'max':max(s[k] for s in base),'median':float(np.median([s[k] for s in base]))} for k in ['online_ATE_m','exported_ATE_m','online_RPEt_m','exported_RPEt_m','online_RPEr_deg','exported_RPEr_deg','track_mean_ms','total_CPU_s']};(N/'results/S0_two_run_range.json').write_text(json.dumps(ranges,indent=2))
checks={'same_input_stamps':len({tuple(x['stamp'] for x in rows) for rows in traces.values()})==1,'same_S1_E1_E2_raw_matches_LK_PnP_counts':all(all(a[k]==b[k]==c[k] for k in ['raw_N','mutual_matches','good_2d','pnp_ok','pnp_inliers','both_depth_tested','reference_stamp']) for a,b,c in zip(traces['S1_01'],traces['E1'],traces['E2'])),'E1_only_2d_deletion':all(float(x['motion_rejected'])==0 for x in traces['E1']),'E2_only_3d_deletion':all(float(x['bad_2d_rejected'])==0 for x in traces['E2']),'E1_2d_deletions_match_old_S1':all(x['bad_2d_rejected']==y['bad_2d_rejected'] for x,y in zip(traces['E1'],traces['S1_01'])),'E2_3d_deletions_match_old_S1':all(x['motion_rejected']==y['motion_rejected'] for x,y in zip(traces['E2'],traces['S1_01'])),'counts_equal_actual_N_subsets':all(r['actual_total_deleted']==r['bad_2d_rejected_sum']+r['motion_rejected_sum'] for r in summary),'no_new_depth_invalidation':all(r['depth_invalidated_sum']==0 for r in summary)}
assert all(checks.values()),checks;(N/'audit/comparison_checks.json').write_text(json.dumps(checks,indent=2))
fig,ax=plt.subplots(2,3,figsize=(14,8));x=np.arange(len(summary));labels=[r['condition'] for r in summary];width=.34
for j,(title,key,unit) in enumerate([('ATE','ATE_m','m'),('1-second translation RPE','RPEt_m','m'),('1-second rotation RPE','RPEr_deg','deg')]):
 for offset,kind,color in [(-width/2,'online','#327bac'),(width/2,'exported','#c98835')]:ax[0,j].bar(x+offset,[r[kind+'_'+key] for r in summary],width,label=kind,color=color)
 ax[0,j].set(xticks=x,xticklabels=labels,title=title,ylabel=unit);ax[0,j].legend()
ax[1,0].bar(x,[r['bad_2d_rejected_sum'] for r in summary],label='bad 2D');ax[1,0].bar(x,[r['motion_rejected_sum'] for r in summary],bottom=[r['bad_2d_rejected_sum'] for r in summary],label='3D residual');ax[1,0].set(title='Actually removed observations',ylabel='frame-observation events');ax[1,0].legend()
ax[1,1].bar(x,[r['retained_2d_sum'] for r in summary],label='2D retained');ax[1,1].bar(x,[r['retained_3d_sum'] for r in summary],bottom=[r['retained_2d_sum'] for r in summary],label='3D retained');ax[1,1].set(title='Native retained associations (not correctness)',ylabel='frame-observation events');ax[1,1].legend()
ax[1,2].bar(x,[r['total_CPU_s'] for r in summary],label='total CPU (s)',color='#40886f');right=ax[1,2].twinx();right.plot(x,[r['track_mean_ms'] for r in summary],'ko-',label='mean TrackRGBD (ms)');right.set_ylabel('mean TrackRGBD (ms)');ax[1,2].set(title='Compute cost',ylabel='CPU user+system (s)');ax[1,2].legend(loc='upper left');right.legend(loc='upper right')
for a in ax[1]:a.set(xticks=x,xticklabels=labels)
fig.suptitle('Bonn deletion ablation: S0 n=2, S1/E1/E2 n=1; no significance claim; full coverage for all')
fig.tight_layout();fig.savefig(N/'figures/ablation_comparison.png',dpi=160);plt.close(fig)
print(json.dumps([{k:r[k] for k in ['condition','exit','processed','online_ATE_m','exported_ATE_m','online_RPEt_m','exported_RPEt_m','actual_total_deleted','retained_2d_sum','retained_3d_sum','pnp_success_frames','track_mean_ms','total_CPU_s']} for r in summary],indent=2))
