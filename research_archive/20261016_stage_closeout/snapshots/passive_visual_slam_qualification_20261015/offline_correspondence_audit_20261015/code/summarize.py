import pathlib,csv,json,collections
import numpy as np
N=pathlib.Path(__file__).resolve().parents[1]
def load(f):return list(csv.DictReader((N/'results'/f).open()))
rows=load('matches.csv');pairs=load('pairs.csv');frames={r['index']:r for r in load('frames.csv')};summary=[];groups=[]
def ratio(n,d):return n/d if d else None
def describe(a):
 a=np.array(a,float)
 return {'n':len(a),'median':float(np.median(a)) if len(a) else None,'p90':float(np.quantile(a,.9)) if len(a) else None,'max':float(a.max()) if len(a) else None}
def distribution(rs):
 if not rs:return {'n':0}
 xy=np.array([[float(r['x1']),float(r['y1'])] for r in rs]);bins=np.floor(xy/[80,80]).astype(int);occupied=len(set(map(tuple,bins)));h=np.bincount(bins[:,1]*8+bins[:,0],minlength=48);p=h/h.sum();ent=-sum(p[p>0]*np.log(p[p>0]))/np.log(48);xyz=np.array([[float(r['X1']),float(r['Y1']),float(r['Z1'])] for r in rs]);ev=np.linalg.eigvalsh(np.cov(xyz.T)) if len(xyz)>3 else None
 return {'n':len(rs),'source_8x6_cells':occupied,'source_entropy':float(ent),'3D_cov_eigenvalues_m2':ev.tolist() if ev is not None else None,'3D_cov_min_max_ratio':float(max(0,ev[0])/ev[-1]) if ev is not None and ev[-1]>0 else None,'not_pose_uncertainty':True}
for p in pairs:
 selected=[r for r in rows if r['pair']==p['pair'] and r['mutual_ratio']=='1'];valid=[r for r in selected if r['valid_3D']=='1'];r={k:v for k,v in p.items()};f=frames[p['source_index']];g=frames[p['target_index']]
 for k in ['B_area_fraction','B_pixel_depth_valid_fraction','B_features','B_depth_features','P_area_fraction','P_features','P_depth_features','U_area_fraction','laplacian_variance']:
  r['source_'+k]=float(f[k]);r['target_'+k]=float(g[k])
 r['selected_valid_3D']=len(valid);r['selected_any_person_core_fraction']=ratio(sum('P' in q['group'] for q in selected),len(selected));r['selected_U_involved']=sum('U' in q['group'] for q in selected);r['person_core_annotation_incomplete']=True
 for group in ['PP','BB']:
  matches=[q for q in selected if q['group']==group];v=[q for q in valid if q['group']==group];stable=[q for q in v if q['stable_depth_both']=='1'];good=[q for q in v if q['consistent_primary']=='1'];r[group+'_mutual_ratio']=len(matches);r[group+'_valid3D']=len(v);r[group+'_consistent']=len(good);r[group+'_inconsistent_fraction']=ratio(len(v)-len(good),len(v));r[group+'_stable3D']=len(stable);r[group+'_stable_inconsistent_fraction']=ratio(sum(q['consistent_primary']=='0' for q in stable),len(stable));r[group+'_reprojection_median_px']=float(np.median([float(q['reprojection_px']) for q in v])) if v else None;r[group+'_residual3D_median_m']=float(np.median([float(q['residual_3D_m']) for q in v])) if v else None
  groups.append({'pair':p['pair'],'window':p['window'],'group':group,'selected':len(matches),'valid3D':len(v),'stable3D':len(stable),'reprojection_px':describe([float(q['reprojection_px']) for q in v]),'depth_error_m':describe([float(q['depth_error_m']) for q in v]),'residual3D_m':describe([float(q['residual_3D_m']) for q in v]),'inconsistent_by_px_3_5_8':{str(th):ratio(sum(not(float(q['reprojection_px'])<=th and float(q['depth_error_m'])<=float(q['depth_tolerance_m'])) for q in v),len(v)) for th in [3,5,8]},'all_valid_distribution':distribution(v),'consistent_distribution':distribution(good)})
 r['BB_consistent_per_10percent_source_B_area']=ratio(r['BB_consistent']*.1,r['source_B_area_fraction']);r['BB_consistent_per_source_B_depth_feature']=ratio(r['BB_consistent'],r['source_B_depth_features']);summary.append(r)
with (N/'results/pair_summary.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
(N/'results/group_geometry.json').write_text(json.dumps(groups,indent=2))
windows=[]
for name in ['before','critical','after']:
 s=[r for r in summary if r['window']==name];w={'window':name,'pairs':len(s),'aggregate_not_independent_frame_trials':True}
 for key in ['PP_mutual_ratio','PP_valid3D','PP_consistent','BB_mutual_ratio','BB_valid3D','BB_consistent','source_B_area_fraction','source_B_depth_features','BB_consistent_per_10percent_source_B_area','BB_consistent_per_source_B_depth_feature','selected_any_person_core_fraction']:
  a=[r[key] for r in s if r[key] is not None];w[key]={'median':float(np.median(a)) if a else None,'range':[float(min(a)),float(max(a))] if a else None}
 for group in ['PP','BB']:
  n=sum(r[group+'_valid3D'] for r in s);bad=sum(r[group+'_valid3D']-r[group+'_consistent'] for r in s);w[group+'_pooled_geometric_inconsistent_fraction']=ratio(bad,n);w[group+'_pooled_denominator']=n;w[group+'_pairwise_inconsistency']=[r[group+'_inconsistent_fraction'] for r in s]
 windows.append(w)
(N/'results/window_summary.json').write_text(json.dumps(windows,indent=2))
print('pair | all_mutual | PPvalid / inconsistent | BBvalid / consistent | PPstable inconsistent')
for r in summary:print(r['pair'],r['mutual_ratio'],r['PP_valid3D'],r['PP_inconsistent_fraction'],r['BB_valid3D'],r['BB_consistent'],r['PP_stable_inconsistent_fraction'])
print(json.dumps(windows,indent=2))
