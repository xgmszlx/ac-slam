from pathlib import Path
import json, numpy as np
from scipy.spatial.transform import Rotation
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from evaluate import read_rows,transforms,associate
D=Path(__file__).resolve().parents[1];Q=Path('/home/wcqw/passive_visual_slam_qualification_20261015/data/rgbd_dataset_freiburg3_walking_xyz')
et,ep=transforms(read_rows(D/'results/full/CameraTrajectory.txt'));gt,gp=transforms(read_rows(Q/'groundtruth.txt'));pairs=associate(et,gt);ei,gi=np.array(pairs).T
x=ep[ei,:3,3];y=gp[gi,:3,3];rot,_=Rotation.align_vectors(y-y.mean(0),x-x.mean(0));pos=rot.apply(ep[:,:3,3]-x.mean(0))+y.mean(0)
a=np.linalg.norm(pos[ei]-y,axis=1);m=json.loads((D/'evaluation/metrics.json').read_text());diff=abs(np.sqrt(np.mean(a*a))-m['ate_m']['rmse']);assert diff<1e-10
rpe=np.genfromtxt(D/'evaluation/rpe.csv',delimiter=',',names=True);values=[]
# Independent relative translation and quaternion composition on the same frozen accepted pairs.
valid={round(float(et[e]),6):(int(e),int(g)) for e,g in pairs}
for row in rpe:
 e,g=valid[round(float(row['stamp_start']),6)];j,h=valid[round(float(row['stamp_end']),6)]
 rr=Rotation.from_matrix(ep[e,:3,:3]).inv();rg=Rotation.from_matrix(gp[g,:3,:3]).inv()
 p=rr.apply(ep[j,:3,3]-ep[e,:3,3]);t=rg.apply(gp[h,:3,3]-gp[g,:3,3])
 te=np.linalg.norm(p-t)
 er=(rg*Rotation.from_matrix(gp[h,:3,:3])).inv()*(rr*Rotation.from_matrix(ep[j,:3,:3]));deg=np.rad2deg(er.magnitude())
 values.append(max(abs(te-float(row['translation_m'])),abs(deg-float(row['rotation_deg']))))
assert max(values)<1e-9
out={'matched_poses':len(pairs),'independent_SE3_ATE_RMSE_m':float(np.sqrt(np.mean(a*a))),'ATE_difference_m':float(diff),'accepted_RPE_pairs':len(rpe),'max_independent_RPE_difference':float(max(values)),'scale':1.0,'no_parameter_fitting_to_errors':True}
(D/'audit/evaluation_check.json').write_text(json.dumps(out,indent=2))
# Correct factual run title; inherited evaluator's fallback title is not used in the published figure.
fig,axes=plt.subplots(1,3,figsize=(13,3.7))
axes[0].plot(gp[:,0,3],gp[:,1,3],c='k',label='GT');axes[0].plot(pos[:,0],pos[:,1],label='NGD-M0-compat-v2');axes[0].axis('equal');axes[0].set(xlabel='x (m)',ylabel='y (m)');axes[0].legend(fontsize=8)
axes[1].plot(et[ei]-et[0],a);axes[1].set(xlabel='Time from first input (s)',ylabel='Exported SE3 ATE (m)',title='RMSE %.4f m; 826 GT pairs'%m['ate_m']['rmse'])
axes[2].plot(rpe['stamp_start']-et[0],rpe['translation_m']);axes[2].set(xlabel='RPE start time (s)',ylabel='1 s translation RPE (m)',title='RMSE %.4f m; %d pairs'%(m['rpe_1s_translation_m']['rmse'],len(rpe)))
fig.suptitle('NGD-M0-compat-v2: 827/827 calls and exported poses; exit 0; one walking run')
fig.tight_layout();(D/'figures').mkdir(exist_ok=True);fig.savefig(D/'figures/walking_result.png',dpi=150);plt.close(fig)
print(json.dumps(out,indent=2))
