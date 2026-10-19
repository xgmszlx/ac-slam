from pathlib import Path
import sys,json,csv,re,os,subprocess
import numpy as np
import pandas as pd
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'code'));from evaluate import read_rows,associate,rigid_align
rows=[];details=[];fig,axs=plt.subplots(2,2,figsize=(12,8),layout='constrained')
for i,seq in enumerate(['desk','large_cabinet']):
 d=P/'data'/('rgbd_dataset_freiburg1_desk' if seq=='desk' else 'rgbd_dataset_freiburg3_large_cabinet');assoc=read_rows(d/'associations.txt');g=np.asarray(read_rows(d/'groundtruth.txt'),float);t0=float(assoc[0][0]);gt_in_input=g[(g[:,0]>=float(assoc[0][0]))&(g[:,0]<=float(assoc[-1][0]))];axs[i,0].plot(gt_in_input[:,1],gt_in_input[:,2],c='black',lw=1,label='GT input interval')
 for cond,color in [('B0','#a64c23'),('B1','#187daa')]:
  out=P/'results'/seq/cond;r=json.loads((out/'run.json').read_text());f=pd.read_csv(out/'frame_states.csv');n=f[f.N>=0];res=(out/'resources.txt').read_text();extract=lambda pat:float(re.search(pat,res).group(1));raw_valid=n.valid_depth.sum()+(n.boundary_features.sum() if cond=='B1' else 0)
  row={'sequence':seq,'condition':cond,'exit':r['exit'],'inputs':r['frames_expected'],'processed':r.get('processed_frames'),'ATE_m':r['exported'].get('ATE'),'RPE_1s_t_m':r['exported'].get('RPEt'),'RPE_1s_r_deg':r['exported'].get('RPEr'),'RPE_pairs':r['exported'].get('RPE_pairs'),'online_ATE_m':r['online'].get('ATE'),'online_RPE_1s_t_m':r['online'].get('RPEt'),'exported_coverage':r['exported'].get('coverage'),'online_coverage':r['online'].get('coverage'),'identity_gauge_qualified':r['exported'].get('identity_gauge_qualified'),'non_OK_frames':int((f.state!=2).sum()),'map_ids':str(r['map_ids']),'last_map_points':int(f.current_map_points.iloc[-1]),'last_atlas_points':int(f.atlas_points.iloc[-1]),'last_keyframes':int(f.current_keyframes.iloc[-1]),'boundary_features_total':int(n.boundary_features.sum()),'boundary_share_all_native_features':float(n.boundary_features.sum()/n.N.sum()),'boundary_share_original_valid_depth':float(n.boundary_features.sum()/raw_valid),'changed_native_depth_total':int(n.invalid_boundary.sum()),'mvDepth_mvuRight_both_minus_one':int(n.both_minus_one.sum()),'valid_depth_mean':float(n.valid_depth.mean()),'retained_2d_mean':float(n.retained_2d.mean()),'retained_3d_mean':float(n.retained_3d.mean()),'boundary_associated_mean':float(n.boundary_associated.mean()),'preprocess_ms_mean':float(n.preprocess_seconds.mean()*1000),'track_ms_mean':float(n.track_seconds.mean()*1000),'audit_ms_mean':float(n.audit_seconds.mean()*1000),'wall_s':r['elapsed_wall_s'],'user_CPU_s':extract(r'User time \(seconds\): ([0-9.]+)'),'system_CPU_s':extract(r'System time \(seconds\): ([0-9.]+)'),'peak_RSS_MiB':extract(r'Maximum resident set size \(kbytes\): ([0-9.]+)')/1024}
  # Gaps use true ordered input timestamps and public non-OK samples, never extrapolate state.
  bad=f.state.to_numpy()!=2;longest=0.;start=None
  for j,b in enumerate(bad):
   if b and start is None:start=j
   if start is not None and (not b or j==len(bad)-1):longest=max(longest,float(f.stamp.iloc[j]-f.stamp.iloc[start]));start=None
  row['longest_public_non_OK_s']=longest;rows.append(row)
  details.append({'sequence':seq,'condition':cond,'state_counts':r['states'],'missing_frame_identity':r['frame_identity_missing'],'max_exported_output_gap_s':float(np.diff(np.asarray(read_rows(out/'CameraTrajectory.txt'),float)[:,0]).max()),'map_ids':r['map_ids'],'native_frame_min_max_features':[float(n.N.min()),float(n.N.max())],'boundary_features_per_frame_min_median_max':[float(n.boundary_features.min()),float(n.boundary_features.median()),float(n.boundary_features.max())]})
  e=np.asarray(read_rows(out/'CameraTrajectory.txt'),float);pairs=associate(e[:,0],g[:,0]);ei,gi=np.asarray(pairs).T;rr,tt=rigid_align(e[ei,1:4],g[gi,1:4]);pos=e[:,1:4]@rr.T+tt;axs[i,0].plot(pos[:,0],pos[:,1],c=color,lw=1,label=cond)
  for kind,style in [('exported','-'),('online','--')]:
   a=pd.read_csv(out/'evaluation'/kind/'ate.csv');axs[i,1].plot(a.stamp-t0,a.error_m,c=color,ls=style,lw=.9,label=cond+' '+kind)
 axs[i,0].set(title=seq+' | SE3 aligned XY (no scale)',xlabel='x (m)',ylabel='y (m)',aspect='equal');axs[i,0].legend(fontsize=8);axs[i,1].set(title=seq+' | position error, one run/condition',xlabel='input time (s)',ylabel='ATE point error (m)');axs[i,1].legend(fontsize=8)
 for ax in axs[i]:ax.grid(alpha=.2)
fig.suptitle('First screen: four complete runs. Solid=exported, dashed=online. No repeats/significance claim.');fig.savefig(P/'figures/trajectory_error.png',dpi=160);plt.close(fig)
pd.DataFrame(rows).to_csv(P/'results/summary.csv',index=False);(P/'results/frame_summary.json').write_text(json.dumps(details,indent=2))
# First/middle/last native-Frame feature probes, never chosen from trajectory errors.
fig,axs=plt.subplots(2,3,figsize=(15,8),layout='constrained');probes=[];env=dict(os.environ,LD_LIBRARY_PATH=str(P/'build')+':/home/wcqw/passive_visual_slam_qualification_20261015/local/lib')
(P/'results/feature_probes').mkdir(exist_ok=True)
for i,seq in enumerate(['desk','large_cabinet']):
 d=P/'data'/('rgbd_dataset_freiburg1_desk' if seq=='desk' else 'rgbd_dataset_freiburg3_large_cabinet');assoc=read_rows(d/'associations.txt');native_runtime=pd.read_csv(P/'results'/seq/'B0/frame_states.csv')
 for ax,k in zip(axs[i],[0,len(assoc)//2,len(assoc)-1]):
  row=assoc[k];prefix=P/'results/feature_probes'/f'{seq}_{k}';out=prefix.with_suffix('.csv');maskfile=prefix.with_suffix('.png');cmd=[str(P/'build/probe_features'),str(P/'config'/f'{seq}.yaml'),str(d/row[1]),str(d/row[3]),str(out),str(maskfile)];subprocess.run(cmd,env=env,check=True)
  f=pd.read_csv(out);assert len(f)==int(native_runtime.N.iloc[k]);im=np.array(Image.open(d/row[1]));ax.imshow(im);valid=f.depth_m>0;target=f.boundary>0
  for select,c,label in [(~valid,'#bfbfbf','No depth'),(valid&~target,'#2bdc76','Valid non-boundary'),(target,'#ff3c38','Boundary valid depth')]:ax.scatter(f.x[select],f.y[select],s=6,c=c,linewidths=0,label=label)
  ax.set(title=f'{seq} | frame {k}\n{int(target.sum())}/{len(f)} native boundary features',xticks=[],yticks=[]);probes.append({'sequence':seq,'index':k,'RGB_stamp':row[0],'depth_stamp':row[2],'features':len(f),'boundary_valid_features':int(target.sum()),'boundary_close_3d_eligible':int(((f.close_3d_eligible>0)&target).sum()),'runtime_B0_feature_count_agrees':True})
axs[0,0].legend(fontsize=7,loc='lower left');fig.suptitle('Native ORB-SLAM3 Frame features + fixed depth boundary; independent probe, NOT optimizer inlier labels');fig.savefig(P/'figures/native_depth_boundary.png',dpi=160);plt.close(fig)
(P/'results/feature_probe_summary.json').write_text(json.dumps(probes,indent=2));print(pd.DataFrame(rows).to_string(index=False));print('feature probes',probes)
