from pathlib import Path
import json,numpy as np
from scipy.spatial.transform import Rotation
from evaluate import transforms,read_rows,associate
D=Path(__file__).resolve().parents[1];Q=Path(json.loads((D/'protocol/design_frozen.json').read_text())['sequence']);gt,gp=transforms(read_rows(Q/'groundtruth.txt'));out={}
for tag in ['M0','M2']:
 for kind in ['online','exported']:
  f=D/'results'/tag/('OnlineTrajectory.txt' if kind=='online' else 'CameraTrajectory.txt');et,ep=transforms(read_rows(f));pairs=associate(et,gt);ei,gi=np.array(pairs).T;x=ep[ei,:3,3];y=gp[gi,:3,3];r,_=Rotation.align_vectors(y-y.mean(0),x-x.mean(0));error=np.linalg.norm(r.apply(x-x.mean(0))-(y-y.mean(0)),axis=1);m=json.loads((D/'results'/tag/'evaluation'/kind/'metrics.json').read_text());ad=abs(np.sqrt(np.mean(error**2))-m['ate_m']['rmse']);assert ad<1e-10
  rp=np.genfromtxt(D/'results'/tag/'evaluation'/kind/'rpe.csv',delimiter=',',names=True);look={round(et[e],6):(e,g) for e,g in pairs};d=[]
  for row in rp:
   e,g=look[round(row['stamp_start'],6)];j,h=look[round(row['stamp_end'],6)];re=Rotation.from_matrix(ep[e,:3,:3]).inv();rg=Rotation.from_matrix(gp[g,:3,:3]).inv();te=np.linalg.norm(re.apply(ep[j,:3,3]-ep[e,:3,3])-rg.apply(gp[h,:3,3]-gp[g,:3,3]));rotation=(rg*Rotation.from_matrix(gp[h,:3,:3])).inv()*(re*Rotation.from_matrix(ep[j,:3,:3]));d.append(max(abs(te-row['translation_m']),abs(np.rad2deg(rotation.magnitude())-row['rotation_deg'])))
  assert max(d)<1e-9;out[tag+'_'+kind]={'GT_pairs':len(pairs),'ATE_difference':float(ad),'max_RPE_difference':float(max(d)),'RPE_pairs':len(rp),'scale':1}
(D/'audit/independent_metrics_check.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
