"""Read existing logs only. No SLAM calls, source changes, or fitted decision rules."""
import csv,json,hashlib
from pathlib import Path
import numpy as np
from scipy.stats import pearsonr,spearmanr,rankdata
from scipy.spatial.transform import Rotation
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
D=Path(__file__).resolve().parents[1]
PLAN=json.loads((D/'protocol/analysis_frozen.json').read_text())

def load(path):
 with Path(path).open() as f:return list(csv.DictReader(f))
def arr(rows,key):return np.array([float(r[key]) for r in rows])
def match_unique(reference,query,tol=2e-6):
 reference=np.asarray(reference);query=np.asarray(query)
 assert np.all(np.diff(reference)>0) and np.all(np.diff(query)>0)
 ids=np.array([np.argmin(abs(reference-t)) for t in query])
 assert len(np.unique(ids))==len(ids), 'reused timestamp'
 assert np.all(abs(reference[ids]-query)<=tol), 'timestamp outside tolerance'
 return ids

def corr(x,y):
 ok=np.isfinite(x)&np.isfinite(y);x=np.asarray(x)[ok];y=np.asarray(y)[ok]
 if len(x)<3 or np.ptp(x)==0 or np.ptp(y)==0:return {'n':int(len(x)),'pearson':None,'spearman':None}
 return {'n':int(len(x)),'pearson':float(pearsonr(x,y).statistic),'spearman':float(spearmanr(x,y).statistic)}
def resid(x,C):return x-C@np.linalg.lstsq(C,x,rcond=None)[0]
def adjusted(x,y,C):
 ok=np.isfinite(x)&np.isfinite(y)&np.isfinite(C).all(1)
 return corr(resid(x[ok],C[ok]),resid(y[ok],C[ok]))
def writecsv(path,rows):
 with path.open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n");w.writeheader();w.writerows(rows)
def rmse(x):return float(np.sqrt(np.mean(np.square(x))))
def phase(t):return np.floor(t/2).astype(int)
def design(t,motion=None):
 C=np.eye(10)[np.clip(phase(t),0,9)]
 return C if motion is None else np.column_stack([C,motion])
def gt_pairs(et,gt):
 cand=[]
 for i,t in enumerate(et):
  for j in range(np.searchsorted(gt,t-.02,side='right'),np.searchsorted(gt,t+.02,side='left')):cand.append((abs(t-gt[j]),i,j))
 a,b=set(),set();out={}
 for _,i,j in sorted(cand):
  if i not in a and j not in b:a.add(i);b.add(j);out[i]=j
 return out

def main():
 runs={};base=None;checks={}
 for name,path in PLAN['runs'].items():
  p=Path(path);rows=load(p/'frame_states.csv'); f={k:arr(rows,k) for k in rows[0]}
  assert len(rows)==589
  if base is None:base=f['stamp'].copy()
  assert np.array_equal(base,f['stamp'])
  assert np.array_equal(f['stamp'],f['frame_stamp'])
  assert np.all(f['state']==2) and np.all(f['map_id']==0) and np.all(f['map_count']==1)
  f['support']=f['retained_2d']+f['retained_3d'];f['deleted']=f['bad_2d_rejected']+f['motion_rejected'];f['delete_fraction']=f['deleted']/f['raw_N']
  assert np.array_equal(f['raw_N']-f['kept_N'],f['deleted'])
  assert np.all(f['support']<=f['associated_points'])
  for field in ['ate','rpet','rper','rpe_end']:f[field]=np.full(len(rows),np.nan)
  er=load(p/'evaluation/online/ate.csv');ei=match_unique(base,arr(er,'stamp'));f['ate'][ei]=arr(er,'error_m')
  rr=load(p/'evaluation/online/rpe.csv');ri=match_unique(base,arr(rr,'stamp_start'));rj=match_unique(base,arr(rr,'stamp_end'))
  f['rpet'][ri]=arr(rr,'translation_m');f['rper'][ri]=arr(rr,'rotation_deg');f['rpe_end'][ri]=base[rj]
  checks[name]={'frames':len(rows),'ate_matches':len(ei),'rpe_pairs':len(ri),'max_ate_stamp_delta_us':float(max(abs(base[ei]-arr(er,'stamp')))*1e6),'max_rpe_stamp_delta_us':float(max(abs(base[ri]-arr(rr,'stamp_start')))*1e6),'map_ids':np.unique(f['map_id']).tolist()}
  f['ri']=ri;f['rj']=rj;runs[name]=f
 for f in runs.values():assert np.array_equal(f['ri'],runs['S0']['ri']) and np.array_equal(f['rj'],runs['S0']['rj'])
 t=base-base[0];ri=runs['S0']['ri'];rj=runs['S0']['rj']
 # Same nearest GT association as saved evaluator; no GT extrapolation or dynamic labels.
 gtpath=Path('/home/wcqw/passive_rgbd_combo_20261019/e2e_20261020/data/rgbd_bonn_moving_obstructing_box/groundtruth.txt')
 g=np.loadtxt(gtpath);q=Rotation.from_quat(g[:,4:8]);M=gt_pairs(base,g[:,0]);gti=np.array([M[int(i)] for i in ri]);gtj=np.array([M[int(j)] for j in rj])
 gtd=np.linalg.norm(g[gtj,1:4]-g[gti,1:4],axis=1);gtr=(q[gti].inv()*q[gtj]).magnitude()*180/np.pi
 motion=np.column_stack([gtd,gtr]);C=design(t[ri],motion)
 correlations={};corrows=[];paired=[];bins=[]
 for name,f in runs.items():
  cs={}
  for xname in ['support','associated_points','deleted','delete_fraction']:
   for yname in ['ate','rpet','rper']:
    x,y=f[xname],f[yname];ok=np.isfinite(y);raw=corr(x,y);within=adjusted(x[ok],y[ok],design(t[ok]))
    v={'raw':raw,'within_2s_phase':within,'time_error':corr(t,y)}
    if yname!='ate':
     v['phase_and_gt_motion']=adjusted(x[ri],y[ri],C)
     v['first_difference']=corr(np.diff(x[ri]),np.diff(y[ri]))
    cs[xname+'__'+yname]=v
    corrows.append({'run':name,'x':xname,'y':yname,'n':raw['n'],'pearson':raw['pearson'],'spearman':raw['spearman'],'phase_centered_pearson':within['pearson'],'phase_centered_spearman':within['spearman'],'phase_motion_pearson':v.get('phase_and_gt_motion',{}).get('pearson'),'first_difference_pearson':v.get('first_difference',{}).get('pearson')})
  correlations[name]=cs
  # Descriptive support quartiles at RPE start; never interpreted as a decision threshold.
  limits=np.quantile(f['support'][ri],[0,.25,.5,.75,1]); bi=np.searchsorted(limits[1:-1],f['support'][ri],side='right')
  for b in range(4):
   use=ri[bi==b];bins.append({'run':name,'quartile':b+1,'support_low':float(limits[b]),'support_high':float(limits[b+1]),'n':len(use),'time_median_s':float(np.median(t[use])),'rpet_mean_m':float(np.mean(f['rpet'][use])),'rpet_median_m':float(np.median(f['rpet'][use])),'rper_median_deg':float(np.median(f['rper'][use])),'ate_median_m':float(np.nanmedian(f['ate'][use]))})
 for name in ['S1','S2','E1','E2','S0_02']:
  f=runs[name];s=runs['S0'];vals={}
  for x in ['support','deleted','delete_fraction']:
   for y in ['ate','rpet','rper']:
    dx=f[x]-s[x];dy=f[y]-s[y];ok=np.isfinite(dy)
    vals[x+'__delta_'+y]={'raw':corr(dx,dy),'within_2s_phase':adjusted(dx[ok],dy[ok],design(t[ok]))}
    if y!='ate':vals[x+'__delta_'+y]['phase_and_gt_motion']=adjusted(dx[ri],dy[ri],C)
  paired.append({'run':name,'correlations':vals,'online_ate_rmse':rmse(f['ate'][np.isfinite(f['ate'])]),'online_rpet_rmse':rmse(f['rpet'][ri]),'online_rper_rmse':rmse(f['rper'][ri]),'total_support':int(sum(f['support'])),'total_deleted':int(sum(f['deleted']))})
 windows=[]
 for b in range(10):
  a,z=2*b,2*b+2
  use=ri[(t[ri]>=a)&(t[rj]<z)]
  if not len(use):continue
  ids=np.where((t>=a)&(t<z))[0];row={'start_s':a,'end_s':min(z,float(t[-1])),'rpe_pairs':len(use),'gt_displacement_mean_m':float(np.mean(gtd[np.isin(ri,use)])),'gt_rotation_mean_deg':float(np.mean(gtr[np.isin(ri,use)]))}
  row.update({'first_rgb_stamp':format(base[ids[0]],'.9f'),'last_rgb_stamp':format(base[ids[-1]],'.9f'),'first_rpe_start_s':float(t[use[0]]),'last_rpe_end_s':float(t[rj[np.where(ri==use[-1])[0][0]]])})
  for name,f in runs.items():
   row.update({name+'_rpet_rmse':rmse(f['rpet'][use]),name+'_rper_rmse':rmse(f['rper'][use]),name+'_ate_mean':float(np.nanmean(f['ate'][ids])),name+'_support_mean':float(np.mean(f['support'][ids])),name+'_delete_sum':int(sum(f['deleted'][ids])),name+'_bad_2d_sum':int(sum(f['bad_2d_rejected'][ids])),name+'_motion_rejected_sum':int(sum(f['motion_rejected'][ids])),name+'_delete_fraction':float(sum(f['deleted'][ids])/sum(f['raw_N'][ids])),name+'_associated_mean':float(np.mean(f['associated_points'][ids]))})
   if name!='S0':row.update({name+'_delta_rpet':row[name+'_rpet_rmse']-row['S0_rpet_rmse'],name+'_delta_ate':row[name+'_ate_mean']-row['S0_ate_mean'],name+'_delta_support':row[name+'_support_mean']-row['S0_support_mean']})
  row['selection_score']=max(row['S1_delta_rpet'],row['S2_delta_rpet']);windows.append(row)
 selected=sorted(windows,key=lambda r:(-r['selection_score'],r['start_s']))[:3]
 s2=runs['S2'];totkeys=['fallback_candidates','fallback_already_invalid','depth_invalidated','fallback_range_reason','fallback_neighborhood_reason','fallback_pose_edges_2d_last','fallback_pose_edges_3d_last','fallback_pose_inlier2d_last','fallback_retained_2d']
 s2sum={k:int(sum(s2[k])) for k in totkeys}
 assert s2sum['fallback_candidates']==s2sum['depth_invalidated']+s2sum['fallback_already_invalid']
 assert s2sum['depth_invalidated']==s2sum['fallback_range_reason']+s2sum['fallback_neighborhood_reason']
 assert np.all(s2['fallback_pose_inlier2d_last']<=s2['fallback_pose_edges_2d_last'])
 assert np.array_equal(s2['fallback_retained_2d'],s2['fallback_pose_inlier2d_last'])
 checks['S2_count_invariants']='PASS; tags only mark current positive depth (Combo.cc45), already-invalid candidates untagged'
 checks['S2_active_frames']={k:int(sum(s2[k]>0)) for k in ['depth_invalidated','fallback_pose_edges_2d_last','fallback_pose_inlier2d_last']}
 # Full aligned table to make every temporal pairing and delta inspectable.
 rows=[]
 for i in range(len(t)):
  row={'index':i,'stamp':format(base[i],'.9f'),'relative_s':float(t[i])}
  for name,f in runs.items():
   for k in ['raw_N','deleted','delete_fraction','associated_points','support','retained_2d','retained_3d','ate','rpet','rper','depth_invalidated','fallback_pose_edges_2d_last','fallback_pose_inlier2d_last']:row[name+'_'+k]=float(f[k][i]) if np.isfinite(f[k][i]) else ''
  rows.append(row)
 writecsv(D/'results/aligned_frames.csv',rows);writecsv(D/'results/correlations.csv',corrows);writecsv(D/'results/support_bins.csv',bins);writecsv(D/'results/windows.csv',windows)
 summary={'checks':checks,'correlations':correlations,'paired':paired,'selected_windows':selected,'s2':s2sum,'motion_correlations':{n:{'gt_translation_vs_rpet':corr(gtd,f['rpet'][ri]),'gt_rotation_vs_rpet':corr(gtr,f['rpet'][ri]),'time_vs_support':corr(t,f['support'])} for n,f in runs.items()},'limitations':['overlapping RPE pairs and video frames are dependent; no iid inference','only 1 run for S1/S2/E1/E2; same timestamp does not control map and optimizer history','ATE uses different full-trajectory SE3 fits, RPE is primary','phase/motion adjustment is descriptive and does not identify causal effects','no per-point geometry, motion labels, MapPoint identities or complete edge set']}
 (D/'results/summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False))
 # Three figures, English labels to avoid missing local CJK fonts.
 colors={'S0':'#222222','S1':'#d55e00','S2':'#0072b2','S0_02':'#999999','E1':'#a85390','E2':'#54a048'}
 fig,ax=plt.subplots(4,1,figsize=(11,10),sharex=True,constrained_layout=True)
 for n in ['S0','S1','S2']:ax[0].plot(t[ri],runs[n]['rpet'][ri],label=n,color=colors[n],lw=1.3)
 ax[0].set_ylabel('Forward 1s RPEt (m)');ax[0].legend(ncol=3)
 for n in ['S1','S2']:
  ax[1].plot(t[ri],runs[n]['rpet'][ri]-runs['S0']['rpet'][ri],color=colors[n],label=n+' - S0');ax[2].plot(t,runs[n]['support']-runs['S0']['support'],color=colors[n],label=n+' - S0')
 ax[1].axhline(0,c='gray',lw=.7);ax[1].set_ylabel('Paired delta RPEt (m)');ax[2].set_ylabel('Delta retained links')
 ax[3].plot(t[ri],gtd,c='#009e73',label='GT 1s displacement (m)');twin=ax[3].twinx();twin.plot(t[ri],gtr,c='#cc79a7',label='GT 1s rotation (deg)');ax[3].set_ylabel('GT displacement (m)');twin.set_ylabel('GT rotation (deg)');ax[3].set_xlabel('Seconds from first associated RGB')
 for a in ax:
  for w in selected:a.axvspan(w['start_s'],min(w['end_s']-1,t[ri][-1]),color='#e69f00',alpha=.12)
  a.grid(alpha=.15)
 fig.suptitle('Same inputs, different histories: link-count changes do not consistently track RPE changes\nShading: RPE-start portions of three outcome-selected 2s windows')
 fig.savefig(D/'figures/01_paired_time.png',dpi=170);plt.close(fig)
 fig,ax=plt.subplots(2,3,figsize=(12,7.3),constrained_layout=True)
 for row,n in enumerate(['S1','S2']):
  f=runs[n]
  for col,y in enumerate(['ate','rpet']):
   ok=np.isfinite(f[y]);sc=ax[row,col].scatter(f['support'][ok],f[y][ok],c=t[ok],s=9,cmap='viridis',alpha=.7);ax[row,col].set_xlabel('Track-return retained links');ax[row,col].set_ylabel(n+' '+('online ATE (m)' if y=='ate' else 'forward 1s RPEt (m)'))
   cr=correlations[n]['support__'+y];ax[row,col].set_title('Spearman %.3f; phase-centered %.3f'%(cr['raw']['spearman'],cr['within_2s_phase']['spearman']))
  bb=[r for r in bins if r['run']==n];ax[row,2].plot(range(1,5),[r['rpet_median_m'] for r in bb],'o-',label='median RPEt');ax[row,2].plot(range(1,5),[r['rpet_mean_m'] for r in bb],'s--',label='mean RPEt');ax[row,2].set_xlabel('Within-run support quartile');ax[row,2].set_ylabel('Forward 1s RPEt (m)');ax[row,2].set_title(n+': descriptive bins; no threshold');ax[row,2].legend()
 fig.colorbar(sc,ax=ax[:,:2],label='Time (s)',shrink=.7);fig.suptitle('Time-colored associations and descriptive bins do not establish static-support causality')
 fig.savefig(D/'figures/02_counts_error.png',dpi=170);plt.close(fig)
 fig,ax=plt.subplots(1,3,figsize=(16,4.7),constrained_layout=True)
 keys=['depth_invalidated','fallback_pose_edges_2d_last','fallback_pose_inlier2d_last'];vals=[s2sum[k] for k in keys]
 ax[0].bar(range(3),vals,color=['#999999','#56b4e9','#0072b2']);ax[0].set_xticks(range(3),['Depth invalidated','Mono edges\n(last pose call)','Mono inliers\n(last pose call)']);ax[0].set_ylabel('Frame-observation events');ax[0].set_title('S2: participation is recorded, influence is not')
 for i,v in enumerate(vals):ax[0].text(i,v+230,str(v),ha='center')
 for k,label in zip(keys,['Invalidated','Edges','Inliers']):ax[1].plot(t,s2[k],label=label,lw=1)
 ax[1].set_xlabel('Time (s)');ax[1].set_ylabel('S2 events per frame');ax[1].legend();ax[1].set_title('No point identity or geometry is logged')
 names=list(runs);at=[rmse(runs[n]['ate'][np.isfinite(runs[n]['ate'])]) for n in names];rp=[rmse(runs[n]['rpet'][ri]) for n in names]
 x=np.arange(len(names));ax[2].bar(x-.18,at,.36,label='Online ATE');ax[2].bar(x+.18,rp,.36,label='1s RPEt');ax[2].set_xticks(x,names,rotation=40);ax[2].set_ylabel('RMSE (m)');ax[2].legend();ax[2].set_title('Existing E1/E2 do not rescue the prototype')
 fig.suptitle('Measured constraint participation does not imply geometric observability or localization benefit')
 fig.savefig(D/'figures/03_s2_and_ablations.png',dpi=170);plt.close(fig)
 print(json.dumps({'reproduced':{n:{k:v['raw'] for k,v in correlations[n].items() if k in ['support__ate','support__rpet','delete_fraction__ate']} for n in ['S1','S2']},'windows':[{k:v for k,v in w.items() if k in ['start_s','end_s','S0_rpet_rmse','S1_rpet_rmse','S2_rpet_rmse','S1_support_mean','S2_support_mean','S1_delete_sum','S2_delete_sum']} for w in selected],'s2':s2sum},indent=2))

if __name__=="__main__":
 main()
