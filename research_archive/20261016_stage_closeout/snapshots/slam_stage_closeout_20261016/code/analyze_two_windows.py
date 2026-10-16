"""OFFLINE_DIAGNOSTIC: two already registered intervals only; no PF or new pose search."""
from pathlib import Path
import sys,json,ctypes as C
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.spatial.transform import Rotation
P=Path(__file__).resolve().parents[1]
B=Path('/home/wcqw/lilocbench_amcl_validation_20261016');A=Path('/home/wcqw/lilocbench_aggregation_control_20261016');L=Path('/home/wcqw/lilocbench_likelihood_audit_20261016')
sys.path.insert(0,str(L/'code'));from common import Native,ptr,F
sys.path.insert(0,str(A/'code'));from utils import interp,wrap,pose_row
native=Native();scans=json.loads((P/'data/scans.json').read_text());gt=np.loadtxt(B/'data/gt/lt_changes_0/gt_poses.txt');est=np.loadtxt(A/'results/A0_91_R0/trajectory.txt');od=np.load(A/'results/odom_tf.npz');odom=np.column_stack((od['stamp_ns']/1e9,od['poses']));gt0=gt[0,0]
rows=[];geometry={};stat=[];equivalence=[]
for r in scans:
 raw=np.ascontiguousarray(np.load(P/'data'/f"{r['id']}.npz")['ranges'],dtype=np.float32);rr=np.empty(len(raw));bb=np.empty(len(raw));quat=np.array(r['laser_in_base_xyz_xyzw'][3:],dtype=float)
 native.lib.probe_prepare(len(raw),raw.ctypes.data_as(F),r['range_min'],r['range_max'],r['angle_min'],r['angle_increment'],ptr(quat),ptr(rr),ptr(bb));native.prepare=lambda unused:(rr,bb)
 t=r['stamp_ns']/1e9;g,_,_=interp(gt,t);eidx=np.flatnonzero(np.abs(est[:,0]-t)<1e-6);assert len(eidx)==1;e=pose_row(est[eidx[0]])
 prob,idx,dist,hx,hy=native.pz(r,[g,e]);scores=np.log(1+(prob**3).sum(axis=1));assert np.isfinite(scores).all()
 for pose,score,name in zip([g,e],scores,['GT','AMCL']):
  cscore=native.native_score(r,pose,0,common=True);err=float(abs(np.log(cscore)-score));assert err<1e-10
  equivalence.append(dict(stamp_ns=r['stamp_ns'],pose=name,absolute_log_score_difference=err))
 # All beams are shown only for descriptive overlay; model statistics use the 91 physical slots.
 _,fullidx,_,fx,fy=native.pz(r,[g,e],indices=np.arange(len(rr)))
 row=dict(window=r['window'],stamp_ns=r['stamp_ns'],seq=r['seq'],relative_s=r['relative_s'],position_error_m=float(np.linalg.norm(e[:2]-g[:2])),yaw_error_deg=float(abs(wrap(e[2]-g[2]))*180/np.pi),sampled_slots=91,valid_sampled_returns=len(idx),all_valid_returns=len(fullidx),GT_endpoint_gt0p5m_fraction=float(np.mean(dist[0]>.5)),AMCL_endpoint_gt0p5m_fraction=float(np.mean(dist[1]>.5)),GT_median_endpoint_distance_m=float(np.median(dist[0])),AMCL_median_endpoint_distance_m=float(np.median(dist[1])),native_additive_log_score_est_minus_GT=float(scores[1]-scores[0]),scan_time_s=r['scan_time'],beam_time_increment_s=r['time_increment'],nominal_acquisition_span_s=r['time_increment']*(len(rr)-1))
 rows.append(row);geometry[r['id']]={'g':g,'e':e,'fx':fx,'fy':fy}
for k in [1,2]:
 z=[r for r in scans if r['window']==k];d=pd.DataFrame([r for r in rows if r['window']==k]);t0=z[0]['stamp_ns']/1e9;t1=z[-1]['stamp_ns']/1e9
 def relative(a):
  p,_,_=interp(a,t0);q,_,_=interp(a,t1);c,s=np.cos(p[2]),np.sin(p[2]);return np.r_[np.array([[c,s],[-s,c]])@(q[:2]-p[:2]),wrap(q[2]-p[2])]
 dg=relative(gt);do=relative(odom)
 gtpart=gt[(gt[:,0]>=t0)&(gt[:,0]<=t1)];path=float(np.linalg.norm(np.diff(gtpart[:,1:3],axis=0),axis=1).sum());yaw=Rotation.from_quat(gtpart[:,4:8]).as_euler('ZYX')[:,0];yawtravel=float(np.abs(wrap(np.diff(yaw))).sum()*180/np.pi)
 stat.append(dict(window=k,actual_first_scan_s=t0-gt0,actual_last_scan_s=t1-gt0,updates=len(z),error_range_m=[d.position_error_m.min(),d.position_error_m.max()],yaw_error_range_deg=[d.yaw_error_deg.min(),d.yaw_error_deg.max()],GT_conflict_fraction_median=float(d.GT_endpoint_gt0p5m_fraction.median()),GT_conflict_fraction_range=[d.GT_endpoint_gt0p5m_fraction.min(),d.GT_endpoint_gt0p5m_fraction.max()],AMCL_conflict_fraction_median=float(d.AMCL_endpoint_gt0p5m_fraction.median()),additive_score_est_better_count=int((d.native_additive_log_score_est_minus_GT>0).sum()),additive_log_score_difference_range=[d.native_additive_log_score_est_minus_GT.min(),d.native_additive_log_score_est_minus_GT.max()],GT_path_length_m=path,GT_abs_yaw_travel_deg=yawtravel,GT_relative_SE2=dg.tolist(),odom_relative_SE2=do.tolist(),odom_GT_relative_translation_difference_m=float(np.linalg.norm(do[:2]-dg[:2])),odom_GT_relative_yaw_difference_deg=float(abs(wrap(do[2]-dg[2]))*180/np.pi),valid_return_count_range=[int(d.valid_sampled_returns.min()),int(d.valid_sampled_returns.max())]))
pd.DataFrame(rows).to_csv(P/'results/scan_diagnostics.csv',index=False);(P/'results/window_summary.json').write_text(json.dumps(stat,indent=2));pd.DataFrame([{k:json.dumps(v) if isinstance(v,list) else v for k,v in s.items()} for s in stat]).to_csv(P/'results/window_summary.csv',index=False)
(P/'audit/native_score_equivalence.json').write_text(json.dumps({'comparisons':len(equivalence),'tolerance':1e-10,'maximum_absolute_log_difference':max(x['absolute_log_score_difference'] for x in equivalence),'status':'PASS','details':equivalence},indent=2))
fig,axs=plt.subplots(2,3,figsize=(14,9),layout='constrained');state=native.state
for ax,r in zip(axs.ravel(),[r for k in [1,2] for r in scans if r['window']==k and r['display']]):
 geom=geometry[r['id']];g,e=geom['g'],geom['e'];fx,fy=geom['fx'],geom['fy'];chosen=(np.abs(fx[0]-g[0])<7)&(np.abs(fy[0]-g[1])<7);points=np.column_stack([fx[0,chosen],fy[0,chosen]]);lo=np.minimum(g[:2],e[:2])-3.5;hi=np.maximum(g[:2],e[:2])+3.5
 j,i=np.nonzero(state==1);mx=(i-native.nx//2)*native.scale+native.ox;my=(j-native.ny//2)*native.scale+native.oy;sel=(mx>=lo[0])&(mx<=hi[0])&(my>=lo[1])&(my<=hi[1]);ax.scatter(mx[sel],my[sel],s=2,c='.55',label='Old occupied map')
 for k,c,label,pose in [(0,'#16853b','GT-projected scan',g),(1,'#cb4c2f','AMCL-projected scan',e)]:
  ax.scatter(fx[k],fy[k],s=2,c=c,alpha=.5,label=label);ax.quiver(pose[0],pose[1],np.cos(pose[2]),np.sin(pose[2]),angles='xy',scale_units='xy',scale=1,color=c,width=.008)
 row=next(x for x in rows if x['stamp_ns']==r['stamp_ns']);ax.set(xlim=(lo[0],hi[0]),ylim=(lo[1],hi[1]),aspect='equal',title=f"W{r['window']}  {r['relative_s']:.3f}s | error {row['position_error_m']:.2f}m\nGT endpoints >0.5m: {100*row['GT_endpoint_gt0p5m_fraction']:.1f}%",xlabel='map x (m)',ylabel='map y (m)');ax.grid(alpha=.15)
axs[0,0].legend(fontsize=7,loc='upper left');fig.suptitle('OFFLINE_DIAGNOSTIC: fixed first / middle / last scans; mismatch is NOT change ground truth',fontsize=12);fig.savefig(P/'figures/two_windows.png',dpi=160);plt.close(fig)
print(json.dumps(stat,indent=2));print('time_increment',sorted(set(r['time_increment'] for r in scans)),'scan_time',sorted(set(r['scan_time'] for r in scans)))
