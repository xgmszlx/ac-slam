from pathlib import Path
import json,numpy as np
from scipy.spatial.transform import Rotation
from evaluate import transforms,read_rows,associate
D=Path(__file__).resolve().parents[1];out={}
for item in json.loads((D/'protocol/design_frozen.json').read_text())['order']:
 R=D/'results'/item['tag'];Q=Path(item['sequence']);et,ep=transforms(read_rows(R/'CameraTrajectory.txt'));gt,gp=transforms(read_rows(Q/'groundtruth.txt'));pairs=associate(et,gt);ei,gi=np.array(pairs).T;x=ep[ei,:3,3];y=gp[gi,:3,3];rot,_=Rotation.align_vectors(y-y.mean(0),x-x.mean(0));err=np.linalg.norm(rot.apply(x-x.mean(0))-(y-y.mean(0)),axis=1);m=json.loads((R/'evaluation/metrics.json').read_text());ad=abs(np.sqrt(np.mean(err**2))-m['ate_m']['rmse']);assert ad<1e-10
 rp=np.genfromtxt(R/'evaluation/rpe.csv',delimiter=',',names=True);lookup={round(et[e],6):(e,g) for e,g in pairs};diff=[]
 for row in rp:
  e,g=lookup[round(row['stamp_start'],6)];j,h=lookup[round(row['stamp_end'],6)];re=Rotation.from_matrix(ep[e,:3,:3]).inv();rg=Rotation.from_matrix(gp[g,:3,:3]).inv();te=np.linalg.norm(re.apply(ep[j,:3,3]-ep[e,:3,3])-rg.apply(gp[h,:3,3]-gp[g,:3,3]));dr=(rg*Rotation.from_matrix(gp[h,:3,:3])).inv()*(re*Rotation.from_matrix(ep[j,:3,:3]));diff.append(max(abs(te-row['translation_m']),abs(np.rad2deg(dr.magnitude())-row['rotation_deg'])))
 assert max(diff)<1e-9
 out[item['tag']]={'GT_pairs':len(pairs),'ATE_difference':float(ad),'max_RPE_difference':float(max(diff)),'accepted_RPE_pairs':len(rp),'scale':1}
(D/'audit/independent_math_check.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
