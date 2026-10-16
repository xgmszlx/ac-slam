"""Offline audit of AUTHOR-PROVIDED example trajectories. No estimator run."""
from pathlib import Path
import sys,json,csv,hashlib
import numpy as np,yaml
from scipy.spatial.transform import Rotation
p=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(p/'sources/eval_deps'),str(p/'sources/LILocBench-68e86f33ae3ff660444b92093fb98ca4d5633b46/src')]
import evaluate as ev
config=yaml.safe_load((p/'sources/LILocBench-68e86f33ae3ff660444b92093fb98ca4d5633b46/config/config_public.yaml').read_text())
data=ev.load_data(ev.get_pose_files(str(p/'data/gt'),str(p/'data/example'),config),config)
res=ev.process(data,config)
rows=[]
for name,seq in data.items():
 for idx,(gt,loc) in enumerate(zip(seq['gt'],seq['loc'])):
  tr=res[name]['ape']['transl'][idx];rot=np.degrees(res[name]['ape']['rot'][idx]);t=gt['times'];lt=loc['times']
  inside=(t>=lt[0])&(t<=lt[-1]);gap=np.diff(lt)
  support=np.zeros(len(t),dtype=bool)
  for a,b in zip(lt[:-1],lt[1:]):
   if b-a<=1.:support|=(t>=a)&(t<=b)
  # Native author metrics are unchanged. Independent planar position/yaw math on SAME official interpolation.
  interp=ev.interpolate_poses(t,lt,loc['poses'])
  indep=np.linalg.norm(gt['poses'][:,:2,3]-interp[:,:2,3],axis=1)
  assert np.allclose(indep,tr,atol=1e-11)
  yg=Rotation.from_matrix(gt['poses'][:,:3,:3]).as_euler('ZYX')[:,0]
  yl=Rotation.from_matrix(interp[:,:3,:3]).as_euler('ZYX')[:,0]
  yaw=np.abs(np.degrees(np.arctan2(np.sin(yl-yg),np.cos(yl-yg))))
  assert np.allclose(yaw,rot,atol=1e-10)
  rows.append(dict(provenance='AUTHOR_EXAMPLE_NOT_LOCAL_AMCL',sequence=name,author_start=idx+1,pose_rows=len(lt),gt_rows=len(t),position_RMSE_m=float(np.sqrt(np.mean(tr**2))),heading_RMSE_deg=float(np.sqrt(np.mean(rot**2))),position_p95_m=float(np.quantile(tr,.95)),position_max_m=float(tr.max()),gt_within_native_span_fraction=float(inside.mean()),GT_temporally_bracketed_gap_le_1s_fraction=float(support.mean()),native_max_gap_s=float(gap.max()),first_gt_time=float(t[0]),first_est_time=float(lt[0]),last_gt_time=float(t[-1]),last_est_time=float(lt[-1]),gt_duration_s=float(t[-1]-t[0]),position_over_0p2m_fraction=float((tr>.2).mean()),score=ev.get_score(res[name]['proportions'][idx],config)))
with (p/'results/author_example_metrics.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(p/'results/author_example_metrics.json').write_text(json.dumps(rows,indent=2))
# Analytical controls: a translation remains an error, radians to degrees, endpoint padding semantics.
a=np.tile(np.eye(4),(2,1,1));b=a.copy();b[:,0,3]=1.
tr,rr=ev.ape2d(a,b);assert np.allclose(tr,1.)
b[:,:3,:3]=Rotation.from_euler('z',[.1,.1]).as_matrix()
tr,rr=ev.ape2d(a,b);assert np.allclose(rr,.1)
c=ev.interpolate_poses(np.array([0.,1.,2.,3.]),np.array([1.,2.]),b)
assert np.array_equal(c[0,:3,3],b[0,:3,3]) and np.array_equal(c[-1,:3,3],b[-1,:3,3])
rotation_reconstruction_delta=float(np.max(np.abs(c[[0,-1],:3,:3]-b[:,:3,:3])))
assert rotation_reconstruction_delta < 1e-12
checks={'no_spatial_alignment_1m_control':'PASS','yaw_radians_control':'PASS','author_endpoint_padding_control':'PASS','independent_xy_yaw_agreement_all_12':'PASS','plot_convergence_unit_issue':{'expression':'r < r2d(rot_bound)','config_rot_bound_degrees':5,'computed_radian_comparator':ev.r2d(5),'correct_radian_comparator':ev.d2r(5),'scope':'plot convergence only; scoring uses correct d2r; original source left unchanged'},'SO3_reconstruction_max_element_delta':rotation_reconstruction_delta,'initial_test_failure':'Exact rotation element equality failed after SLERP matrix reconstruction; original script/log retained. Translation endpoint equality remains exact; rotation tested at 1e-12 matrix tolerance. Not a trajectory acceptance change.','provenance':'AUTHOR_EXAMPLE_ONLY'}
(p/'audit/evaluation_checks.json').write_text(json.dumps(checks,indent=2))
print(json.dumps(ev.scoring(res,config),indent=2))
print('Author example independent metric checks PASS for 12 official starts; NOT local runs')
