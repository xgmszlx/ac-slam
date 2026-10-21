from pathlib import Path
import json,csv,re,collections,hashlib,subprocess
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image,ImageDraw
D=Path(__file__).resolve().parents[1];t0=1548339348.69390;summary=[];events={};frame_data={}
def rows(p):return list(csv.DictReader(p.open()))
def total(a,k):return sum(float(r[k]) for r in a)
for tag in ['M0','M1','M2']:
 R=D/'results'/tag;r=json.loads((R/'run.json').read_text());text=(R/'resource.txt').read_text();out={'condition':tag,'exit':r['exit_status'],'completed':r['completed_calls'],'inputs':589,'full_success':r['entry_completed_marker'] and r['exit_status']==0,'wall_s':r['wall_s']}
 for key,label in [('cpu_user_s','User time (seconds)'),('cpu_system_s','System time (seconds)'),('RSS_KiB','Maximum resident set size (kbytes)')]:
  m=re.search(r'^\s*'+re.escape(label)+r': (.+)$',text,re.M);out[key]=float(m.group(1)) if m else None
 for kind in ['online','exported']:
  p=R/'evaluation'/kind/'metrics.json'
  for name in ['ATE_m','RPEt_m','RPEr_deg','coverage','GT_pairs','RPE_pairs']:out[kind+'_'+name]=None
  if p.exists():
   m=json.loads(p.read_text());out.update({kind+'_ATE_m':m['ate_m']['rmse'],kind+'_RPEt_m':m['rpe_1s_translation_m'].get('rmse'),kind+'_RPEr_deg':m['rpe_1s_rotation_deg'].get('rmse'),kind+'_coverage':m['saved_pose_fraction_of_input'],kind+'_GT_pairs':m['saved_poses_with_gt'],kind+'_RPE_pairs':m['rpe_1s_translation_m']['n']})
   rp=np.genfromtxt(R/'evaluation'/kind/'rpe.csv',delimiter=',',names=True);w=rp[(rp['stamp_start']>=t0+9.08)&(rp['stamp_end']<=t0+10.09)];out[kind+'_fixed_window_pairs']=len(w);out[kind+'_fixed_window_RPEt']=float(np.sqrt(np.mean(w['translation_m']**2))) if len(w) else None;out[kind+'_fixed_window_RPEr']=float(np.sqrt(np.mean(w['rotation_deg']**2))) if len(w) else None
 if (R/'frame_states.csv').exists():
  a=rows(R/'frame_states.csv');frame_data[tag]=a;assert len(a)==589 and [int(x['index']) for x in a]==list(range(589));assert all(float(x['stamp'])>float(y['stamp']) for y,x in zip(a,a[1:]));out['states']=dict(collections.Counter(x['state'] for x in a));out['map_IDs']=sorted(set(x['map'] for x in a));out['atlas_map_counts']=sorted(set(x['map_count'] for x in a));out['keyframes']=len((R/'KeyFrameTrajectory.txt').read_text().splitlines())
  for key in ['candidates','accepted','extra_pixels','orb_raw','orb_deleted_base','orb_deleted_extra','orb_retained','lk_checked','lk_deleted_base','lk_deleted_extra','lk_retained','pnp_calls','pnp_inliers','poseopt_calls','poseopt_edges_sum','poseopt_inliers_sum']:
   out[key]=int(total(a,key))
  for key in ['api_ms','module_ms','module_cpu_ms','candidate_ms','bg_ms','region_ms']:
   v=np.array([float(x[key]) for x in a]);out[key+'_mean']=float(v.mean());out[key+'_p95']=float(np.quantile(v,.95));out[key+'_sum']=float(v.sum())
  out['candidate_frames']=sum(int(x['candidates'])>0 for x in a);out['accept_frames']=sum(int(x['accepted'])>0 for x in a);out['bg_reason_counts']=dict(collections.Counter(x['bg_reason'] for x in a));reg=rows(R/'regions.csv');out['region_reason_counts']=dict(collections.Counter(x['reason'] for x in reg));events[tag]=[r for r in reg if r['accepted']=='1']
 else:
  out['missing_trace_reason']='SIGABRT before normal flush: frame/region/online-pose/mask buffers not saved; do not fill zeros or reconstruct as ground truth'
 summary.append(out)
(D/'results/summary.json').write_text(json.dumps({'decision':'INCONCLUSIVE','methods':summary,'new_full_attempts':3,'new_prototype_source_was_frozen':True,'M1_trace_missing':True,'causal_inlier_identity_or_static_labels':'not available'},indent=2))
keys=['condition','exit','completed','online_ATE_m','exported_ATE_m','online_RPEt_m','exported_RPEt_m','online_RPEr_deg','exported_RPEr_deg','online_coverage','exported_coverage','wall_s','cpu_user_s','cpu_system_s','RSS_KiB','api_ms_mean','module_cpu_ms_mean','candidates','accepted','lk_deleted_extra','orb_deleted_extra','poseopt_edges_sum','poseopt_inliers_sum']
with (D/'results/comparison.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(summary)
(D/'results/accepted_events.json').write_text(json.dumps(events,indent=2))
# Actual frozen snapshot files only. An aborted M1 is a gray N/A panel, never a substitute probe or replay.
fig=Image.new('RGB',(640*3,505*3),'white');draw=ImageDraw.Draw(fig)
for row,i in enumerate([147,294,441]):
 for col,t in enumerate(['M0','M1','M2']):
  p=D/'results'/t/f'mask_{i}.png';x=col*640;y=row*505
  if p.exists():fig.paste(Image.open(p),(x,y+25))
  else:draw.rectangle((x,y+25,x+639,y+504),fill=(220,220,220));draw.text((x+30,y+230),'M1 aborted: snapshot buffer NOT SAVED',fill='black')
  draw.text((x+4,y+4),(f'{t}: actual saved frame {i}; green base; magenta extra' if p.exists() else f'{t}: frame {i} snapshot NOT AVAILABLE'),fill='black')
fig.save(D/'figures/actual_masks.jpg')
mask_rows=[]
for i in [0,147,294,441,588]:
 a=np.array(Image.open(D/'results/M0'/f'full_{i}.png'))>0;b=np.array(Image.open(D/'results/M2'/f'full_{i}.png'))>0;e=np.array(Image.open(D/'results/M2'/f'extra_{i}.png'))>0
 mask_rows.append({'frame':i,'M0_mask_pixels':int(a.sum()),'M2_mask_pixels':int(b.sum()),'M2_added_this_frame':int(e.sum()),'pixel_xor_M0_M2':int((a!=b).sum()),'mask_IoU':float((a&b).sum()/max(1,(a|b).sum()))})
with (D/'results/snapshot_differences.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=mask_rows[0].keys());w.writeheader();w.writerows(mask_rows)
fig,ax=plt.subplots(2,2,figsize=(11,7));colors={'M0':'#2677b8','M2':'#c45c34'}
for tag in ['M0','M2']:
 for kind,style in [('online','--'),('exported','-')]:
  a=np.genfromtxt(D/'results'/tag/'evaluation'/kind/'ate.csv',delimiter=',',names=True);ax[0,0].plot(a['stamp']-t0,a['error_m'],style,c=colors[tag],label=tag+' '+kind)
  r=np.genfromtxt(D/'results'/tag/'evaluation'/kind/'rpe.csv',delimiter=',',names=True);ax[0,1].plot(r['stamp_start']-t0,r['translation_m'],style,c=colors[tag],label=tag+' '+kind)
 a=frame_data[tag];ts=np.array([float(x['stamp'])-t0 for x in a]);ax[1,0].plot(ts,[int(x['extra_pixels']) for x in a],c=colors[tag],label=tag+' extra pixels');ax[1,1].plot(ts,[float(x['api_ms']) for x in a],c=colors[tag],label=tag+' TrackRGBD')
ax[0,0].set(title='ATE: M2 lower, one run each',ylabel='SE3 ATE (m)');ax[0,1].set(title='1 s RPE: M2 worse overall',ylabel='Translation RPE (m)');ax[1,0].set(title='Actual M2 accepted additions, three frames',ylabel='Added mask pixels',xlabel='Input relative time (s)');ax[1,1].set(title='Measured TrackRGBD cost',ylabel='ms',xlabel='Input relative time (s)')
for a in ax.flat:a.legend(fontsize=7)
fig.suptitle('INCONCLUSIVE: M1 aborted after 175 calls; no M1 trajectory fabricated');fig.tight_layout();fig.savefig(D/'figures/errors_and_actions.png',dpi=160);plt.close(fig)
# Common SE3-aligned whole trajectories, using each frozen evaluator transform.
fig,ax=plt.subplots(1,2,figsize=(10,4));Q=Path('/home/wcqw/passive_rgbd_combo_20261019/e2e_20261020/data/rgbd_bonn_moving_obstructing_box');gt=np.loadtxt(Q/'groundtruth.txt');ax[0].plot(gt[:,1],gt[:,2],c='black',label='GT')
for tag in ['M0','M2']:
 a=np.loadtxt(D/'results'/tag/'CameraTrajectory.txt');m=json.loads((D/'results'/tag/'evaluation/exported/metrics.json').read_text());R=np.array(m['alignment']['rotation']);t=np.array(m['alignment']['translation']);pos=a[:,1:4]@R.T+t;ax[0].plot(pos[:,0],pos[:,1],label=tag,c=colors[tag])
vals=[r for r in summary if r['condition'] in ['M0','M2']];x=np.arange(2);ax[1].bar(x-.17,[r['api_ms_mean'] for r in vals],width=.34,label='TrackRGBD mean');ax[1].bar(x+.17,[r['module_cpu_ms_mean'] for r in vals],width=.34,label='helper thread CPU mean');ax[1].set_xticks(x);ax[1].set_xticklabels(['M0','M2']);ax[1].set_ylabel('ms / input frame');ax[0].axis('equal');ax[0].set(xlabel='x (m)',ylabel='y (m)',title='Complete exported trajectories; SE3 scale 1');ax[1].set_title('M2 costs more per tracked frame')
for a in ax:a.legend(fontsize=8)
fig.tight_layout();fig.savefig(D/'figures/trajectories_and_cost.png',dpi=160);plt.close(fig)
# Method-level equality does not imply same counterfactual histories.
(D/'results/candidate_pairing_limit.json').write_text(json.dumps({'identical_inputs_generate_identical_candidates':'unit tested, same function with no mode argument','formal_M1_M2_per_frame_equality':'UNRESOLVED: M1 trace lost and asynchronous/native mask histories differ','M0_helper_calls':0,'M0_extra_pixels':summary[0].get('extra_pixels')},indent=2))
print(json.dumps({'decision':'INCONCLUSIVE','comparison':[{k:r.get(k) for k in keys} for r in summary]},indent=2))
