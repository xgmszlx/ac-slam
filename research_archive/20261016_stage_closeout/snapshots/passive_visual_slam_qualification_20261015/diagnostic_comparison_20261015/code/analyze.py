import sys
sys.dont_write_bytecode=True
import pathlib,json,csv,collections,re
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from evaluate import read_rows
N=pathlib.Path(__file__).resolve().parents[1];O=N.parent
rows=[]
for seq in ['walking','sitting']:
 for p in sorted((N/'results'/seq).glob('*')):
  if not (p/'run.json').exists():continue
  rec=json.loads((p/'run.json').read_text());r={'sequence':seq,'tag':p.name,'exit':rec.get('exit_status','RUNNING'),'wall_s':rec.get('elapsed_wall_s'),'states':rec.get('state_counts',{}),'diagnostic_getter_us':rec.get('getter_us',{}),'path':str(p.relative_to(N))}
  resources=(p/'resources.txt').read_text() if (p/'resources.txt').exists() else ''
  hit=re.search(r'Maximum resident set size \(kbytes\): (\d+)',resources);r['max_rss_kib']=int(hit.group(1)) if hit else None
  for kind in ['exported','online']:
   m=p/'evaluation'/kind/'metrics.json'
   if m.exists():
    a=json.loads(m.read_text());r[kind]={'ATE':a['ate_m']['rmse'],'RPEt':a['rpe_1s_translation_m']['rmse'],'RPEr':a['rpe_1s_rotation_deg']['rmse'],'pose_coverage':a['saved_pose_fraction_of_input'],'gt_eligible_coverage':a['saved_gt_match_fraction_of_gt_eligible_input'],'poses':a['saved_camera_poses'],'keyframes':a['saved_keyframes'],'ATE_p90':a['ate_m']['p90'],'RPEt_p90':a['rpe_1s_translation_m']['p90'],'RPEt_max':a['rpe_1s_translation_m']['max'],'missing_intervals':a['missing_output_intervals'],'duplicate_saved_timestamps':a['duplicate_saved_timestamps'],'nonincreasing_saved_time_steps':a['nonincreasing_saved_time_steps'],'metric_qualified':a['duplicate_saved_timestamps']==0 and a['nonincreasing_saved_time_steps']==0}
  text=(p/'stdout.log').read_text();r['map_initialization_log_lines']=[l for l in text.splitlines() if 'First KF:' in l];r['multiple_map_gauge_warning']=len(r['map_initialization_log_lines'])>1
  rows.append(r)
(N/'results/summary.json').write_text(json.dumps(rows,indent=2))
fields=['sequence','tag','exit','ATE','RPEt','RPEr','online_ATE','online_RPEt','coverage','online_OK_coverage','keyframes','wall_s','max_rss_kib','multiple_map_gauge_warning']
with (N/'results/summary.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
 for r in rows:
  a=r.get('exported',{});b=r.get('online',{});w.writerow({'sequence':r['sequence'],'tag':r['tag'],'exit':r['exit'],'ATE':a.get('ATE'),'RPEt':a.get('RPEt'),'RPEr':a.get('RPEr'),'online_ATE':b.get('ATE'),'online_RPEt':b.get('RPEt'),'coverage':a.get('pose_coverage'),'online_OK_coverage':b.get('pose_coverage'),'keyframes':a.get('keyframes'),'wall_s':r['wall_s'],'max_rss_kib':r['max_rss_kib'],'multiple_map_gauge_warning':r['multiple_map_gauge_warning']})
walk=[r for r in rows if r['sequence']=='walking' and 'exported' in r];colors={'P0':'#777777','P1':'#277da1','P2':'#43aa8b'}
fig,axes=plt.subplots(1,3,figsize=(12,4))
for metric,ax,label in zip(['ATE','RPEt','RPEr'],axes,['ATE RMSE (m), SE3/no scale','1s translation RPE RMSE (m)','1s rotation RPE RMSE (deg)']):
 for k in range(3):
  group='P'+str(k);rs=[r for r in walk if r['tag'].startswith(group)]
  if not rs:continue
  values=[r['exported'][metric] for r in rs];xx=k+np.linspace(-.12,.12,len(rs));
  for xpos,value,r in zip(xx,values,rs):ax.scatter([xpos],[value],color=colors[group] if r['exported']['metric_qualified'] and not r['multiple_map_gauge_warning'] else 'red',marker='o' if r['exported']['metric_qualified'] and not r['multiple_map_gauge_warning'] else 'x',s=60,zorder=4)
  valid=[r['exported'][metric] for r in rs if r['exported']['metric_qualified'] and not r['multiple_map_gauge_warning']]
  if len(valid)>1:ax.plot([k-.18,k+.18],[np.median(valid)]*2,c=colors[group],lw=2)
  if metric in ['ATE','RPEt']:ax.scatter(xx,[r['online'][metric] for r in rs],edgecolors=colors[group],facecolors='none',marker='s',s=65,zorder=3)
 ax.set(xticks=[0,1,2],xticklabels=['P0','P1','P2'],ylabel=label);ax.grid(axis='y',alpha=.2)
fig.suptitle('All new walking runs; dot: native export, open square: online return\nRed x: unqualified native export (duplicate stamps + multi-map); P2 NOT RUN; horizontal line: valid-run median');fig.tight_layout();fig.savefig(N/'figures/repeat_comparison.png',dpi=200);fig.savefig(N/'figures/repeat_comparison.pdf');plt.close(fig)
fig,axes=plt.subplots(3,1,figsize=(12,9),sharex=True)
for r in walk:
 p=N/r['path'];state=list(csv.DictReader((p/'frame_states.csv').open()));ts=np.array([float(s['stamp']) for s in state]);t0=ts[0];group=r['tag'][:2];alpha=.8 if group=='P2' else .45
 a=list(csv.DictReader((p/'evaluation/exported/ate.csv').open()));b=list(csv.DictReader((p/'evaluation/exported/rpe.csv').open()))
 axes[0].plot([float(v['stamp'])-t0 for v in a],[float(v['error_m']) for v in a],color=colors[group],alpha=alpha,label=r['tag'])
 axes[1].plot([float(v['stamp_start'])-t0 for v in b],[float(v['translation_m']) for v in b],color=colors[group],alpha=alpha)
 axes[2].step(ts-t0,[int(v['state'])+(int(r['tag'][-1])-1)*.025 for v in state],where='post',color=colors[group],alpha=alpha)
axes[0].set_ylabel('ATE (m)');axes[0].legend(ncol=4);axes[1].set_ylabel('1s RPE translation (m)');axes[2].set(yticks=[0,1,2,3,4],yticklabels=['NO_IMAGES','INIT','OK','RECENT_LOST','LOST'],xlabel='relative RGB timestamp (s)',ylabel='public tracking state');fig.tight_layout();fig.savefig(N/'figures/error_state_timeline.png',dpi=180);plt.close(fig)
# Select failure images by predeclared max local RPE, not by screenshots.
examples=[];fig,axes=plt.subplots(1,len(set(r['tag'][:2] for r in walk)),figsize=(12,4));axes=np.atleast_1d(axes)
selected=[]
for group in ['P0','P1','P2']:
 rs=[r for r in walk if r['tag'].startswith(group) and r['exported']['metric_qualified'] and not r['multiple_map_gauge_warning']]
 if rs:selected.append(rs[0])
for ax,r in zip(axes,selected):
 p=N/r['path'];a=list(csv.DictReader((p/'evaluation/exported/rpe.csv').open()));v=max(a,key=lambda z:float(z['translation_m']));d=O/'data/rgbd_dataset_freiburg3_walking_xyz';assoc=read_rows(d/'associations.txt');stamps=np.array([float(x[0]) for x in assoc]);idx=int(np.argmin(abs(stamps-float(v['stamp_start']))));ax.imshow(Image.open(d/assoc[idx][1]));ax.set_title(r['tag']+' max local RPE start\nframe '+str(idx)+', RPE='+str(round(float(v['translation_m']),3))+' m');ax.axis('off');examples.append({'run':r['tag'],'frame':idx,'rgb_stamp':assoc[idx][0],'rpe_pair':v,'mechanism':'UNKNOWN; visible persons are not verified wrong associations'})
fig.tight_layout();fig.savefig(N/'figures/failure_examples.jpg',dpi=150);plt.close(fig);(N/'audit/failure_examples.json').write_text(json.dumps(examples,indent=2))
# Frozen RPE definition reused without selecting a favourable interval. Report all aligned windows.
windows=[]
for r in walk:
 p=N/r['path'];a=list(csv.DictReader((p/'evaluation/exported/rpe.csv').open()));t0=float(read_rows(O/'data/rgbd_dataset_freiburg3_walking_xyz/associations.txt')[0][0])
 for low,high in [(0,5),(5,10),(10,15),(15,20),(20,25),(25,30)]:
  v=[float(v['translation_m']) for v in a if low<=float(v['stamp_start'])-t0<high];windows.append({'run':r['tag'],'start_s':low,'end_s':high,'pairs':len(v),'rpe_rmse_m':float(np.sqrt(np.mean(np.square(v)))) if v else None})
(N/'results/local_RPE_windows.json').write_text(json.dumps(windows,indent=2))
print(json.dumps(rows,indent=2))
