"""Combine six desk runs, preserving each run as the repeat unit."""
import json,re,collections
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
P=Path(__file__).resolve().parents[1];O=Path('/home/wcqw/passive_rgbd_depth_screen_20261019')
paths=[('B0_01',O/'results/desk/B0'),('B1_01',O/'results/desk/B1')]+[(s,P/'results'/s) for s in ['B1_02','B0_02','B0_03','B1_03']]
rows=[];checks=[];reference=pd.read_csv(paths[0][1]/'frame_states.csv')
for label,out in paths:
    r=json.loads((out/'run.json').read_text());f=pd.read_csv(out/'frame_states.csv');cond=label[:2]
    resources=(out/'resources.txt').read_text();extract=lambda pat:float(re.search(pat,resources).group(1))
    row={'accuracy_qualified':r['online']['identity_gauge_qualified'] and r['exported']['identity_gauge_qualified'],'missing_native_frame_snapshots':int((f.N<0).sum()),'label':label,'condition':cond,'round':1 if label.endswith('01') else 2,'exit':r['exit'],'frames':len(f),'public_OK':int((f.state==2).sum()),'map_ids':str(r['map_ids']),'map_count_max':int(f.map_count.max()),'last_map_points':int(f.current_map_points.iloc[-1]),'last_keyframes':int(f.current_keyframes.iloc[-1]),'last_atlas_points':int(f.atlas_points.iloc[-1]),'exported_keyframes':len([s for s in (out/'KeyFrameTrajectory.txt').read_text().splitlines() if s.strip()]),'boundary_features':int(f.boundary_features.sum()),'changed_depths':int(f.invalid_boundary.sum()),'valid_depth_mean':f.valid_depth.mean(),'retained_2d_mean':f.retained_2d.mean(),'retained_3d_mean':f.retained_3d.mean(),'preprocess_ms':f.preprocess_seconds.mean()*1000,'track_ms':f.track_seconds.mean()*1000,'track_ms_p95':f.track_seconds.quantile(.95)*1000,'audit_ms':f.audit_seconds.mean()*1000,'wall_s':r['elapsed_wall_s'],'CPU_user_s':extract(r'User time \(seconds\): ([0-9.]+)'),'CPU_system_s':extract(r'System time \(seconds\): ([0-9.]+)'),'RSS_MiB':extract(r'Maximum resident set size \(kbytes\): ([0-9.]+)')/1024,'longest_public_non_OK_s':0.}
    for kind in ['online','exported']:
        for metric in ['ATE','RPEt','RPEr','coverage','RPE_pairs','identity_gauge_qualified']:
            row[kind+'_'+metric]=r[kind][metric]
    bad=f.state.to_numpy()!=2;start=None
    for j,b in enumerate(bad):
        if b and start is None:start=j
        if start is not None and (not b or j==len(bad)-1):row['longest_public_non_OK_s']=max(row['longest_public_non_OK_s'],float(f.stamp.iloc[j]-f.stamp.iloc[start]));start=None
    check={'label':label,'same_indices':bool(np.array_equal(f['index'],reference['index'])),'same_input_stamps':bool(np.array_equal(f.stamp,reference.stamp)),'same_native_N_where_available':bool(np.array_equal(f.N[f.N>=0],reference.N[f.N>=0])),'same_boundary_targets':bool(np.array_equal(f.boundary_features,reference.boundary_features)),'same_binary_core_yaml_association':all(r[k]==json.loads((paths[0][1]/'run.json').read_text())[k] for k in ['binary_sha256','core_sha256','yaml_sha256','association_sha256']),'invalid_depth_propagation':bool(((f.invalid_boundary==f.boundary_features)&(f.both_minus_one==f.boundary_features)&(f.valid_boundary==0)).all()) if cond=='B1' else bool(((f.invalid_boundary==0)&(f.valid_boundary==f.boundary_features)).all()),'native_condition_argument':r['command'][-2]==cond,'complete_execution':r['exit']==0 and len(f)==573,'accuracy_qualified':r['online']['identity_gauge_qualified'] and r['exported']['identity_gauge_qualified']}
    checks.append(check);rows.append(row)
    # Complete input coverage is an identity requirement, not a claim of correct pose.
    assert all(check[k] for k in check if k not in ['label','accuracy_qualified']),check
    assert row['boundary_features']==22909
    if row['accuracy_qualified']:assert row['online_coverage']==row['exported_coverage']==1
    if row['accuracy_qualified']:
        assert row['public_OK']==573 and row['map_ids']=='[0]' and row['map_count_max']==1
        assert row['online_RPE_pairs']==row['exported_RPE_pairs']==524
x=pd.DataFrame(rows).sort_values('label');x.to_csv(P/'results/desk_six_runs.csv',index=False)
metrics=['online_ATE','exported_ATE','online_RPEt','exported_RPEt','online_RPEr','exported_RPEr','track_ms','track_ms_p95','preprocess_ms','audit_ms','wall_s','CPU_user_s','CPU_system_s','RSS_MiB','last_map_points','last_keyframes','exported_keyframes','retained_2d_mean','retained_3d_mean']
stats=[]
for metric in metrics:
    z=x[x.accuracy_qualified] if metric.startswith(('online_','exported_')) and metric!='exported_keyframes' else x
    a=z[z.condition=='B0'][metric];b=z[z.condition=='B1'][metric]
    stats.append({'metric':metric,'B0_n':len(a),'B1_n':len(b),'scope':'qualified accuracy only; all runs for native snapshots/cost','B0_min':a.min(),'B0_median':a.median(),'B0_max':a.max(),'B1_min':b.min(),'B1_median':b.median(),'B1_max':b.max(),'B1_minus_B0_median':b.median()-a.median(),'B1_median_relative_change_percent':100*(b.median()/a.median()-1),'worst_B1_below_best_B0':bool(b.max()<a.min()),'best_B0_minus_worst_B1':a.min()-b.max()})
s=pd.DataFrame(stats);s.to_csv(P/'results/ranges_medians.csv',index=False)
gates={m:bool(s[s.metric==m].iloc[0].worst_B1_below_best_B0) for m in ['online_ATE','exported_ATE','online_RPEt','exported_RPEt']}
status='B1_REPEATABLE_SIGNAL' if all(gates.values()) and x.accuracy_qualified.all() else 'B1_INCONCLUSIVE'
x.groupby('condition')[metrics].agg(['min','median','max']).to_csv(P/'results/all_run_raw_ranges_UNQUALIFIED_INCLUDED.csv')
(P/'results/decision.json').write_text(json.dumps({'status':status,'primary_nonoverlap_gates':gates,'unit':'complete run; attempted n=3 per condition; qualified accuracy B0 n=2, B1 n=3; no significance claim','technical_checks':checks},indent=2))
# Six small panels show every complete-run value; no frame pseudo-replication.
colors={'B0':'#b3542c','B1':'#187daa'}
fig,axs=plt.subplots(2,3,figsize=(12,7),layout='constrained')
for ax,m in zip(axs.flat,['online_ATE','exported_ATE','online_RPEt','exported_RPEt','online_RPEr','exported_RPEr']):
    for j,c in enumerate(['B0','B1']):
        z=x[x.condition==c];vals=z[m].to_numpy();labels=z.label.to_list();xx=j+np.array([-.08,0,.08]);valid=z.accuracy_qualified.to_numpy();ax.scatter(xx[valid],vals[valid],c=colors[c],s=40)
        ax.plot([j-.17,j+.17],[np.median(vals[valid])]*2,c=colors[c],lw=2)
        for xi,v,lab,ok in zip(xx,vals,labels,valid):
            if ok:ax.annotate(lab[-2:],(xi,v),xytext=(3,4),textcoords='offset points',fontsize=8)
            else:ax.text(.02,.98,f'{lab} unqualified raw: {v:.4f}',transform=ax.transAxes,va='top',color='darkred',fontsize=8,bbox=dict(facecolor='white',alpha=.8,edgecolor='none'))
    ax.set_xticks([0,1],['B0','B1']);ax.set_title(m);ax.set_ylabel('degrees' if m.endswith('RPEr') else 'metres');ax.grid(axis='y',alpha=.25)
fig.suptitle('Desk: B0_03 multi-map/export identity failure retained; dots/median=qualified accuracy only')
fig.savefig(P/'figures/01_accuracy_repeats.png',dpi=160);plt.close(fig)
fig,axs=plt.subplots(2,3,figsize=(12,7),layout='constrained')
for ax,m in zip(axs.flat,['last_map_points','last_keyframes','retained_2d_mean','retained_3d_mean','track_ms','CPU_user_s']):
    for c in ['B0','B1']:
        z=x[x.condition==c];ax.plot([1,2,3],z[m],'-o',color=colors[c],label=c)
    ax.set(title=m,xlabel='run index (not paired random trials)',xticks=[1,2,3]);ax.grid(alpha=.25);ax.legend()
fig.suptitle('Native end-of-Track snapshots and measured cost | maps are not frozen query maps')
fig.savefig(P/'figures/02_maps_cost.png',dpi=160);plt.close(fig)
print(x[['label','online_ATE','exported_ATE','online_RPEt','exported_RPEt','track_ms','last_map_points','last_keyframes']].to_string(index=False))
print(s.to_string(index=False));print(status)
