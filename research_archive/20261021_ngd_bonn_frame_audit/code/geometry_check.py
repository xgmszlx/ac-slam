"""Fixed input-only LK/depth check; NOT native SLAM associations or labels."""
from pathlib import Path
import json,csv
import cv2
import numpy as np
from pose_math import *
D=Path(__file__).resolve().parents[1]
B=Path('/home/wcqw/passive_rgbd_combo_20261019/e2e_20261020/data/rgbd_bonn_moving_obstructing_box')
assoc=[l.split() for l in (B/'associations.txt').read_text().splitlines() if l.strip() and not l.startswith('#')]
gt=read(B/'groundtruth.txt')
K=np.array([[542.822841,0,315.593520],[0,542.576870,237.756098],[0,0,1.]])
dist=np.array([.039903,-.099343,-.000730,-.000144,0.])
variants=json.loads((D/'protocol/scope.json').read_text())['variants']
cv2.setNumThreads(1)
rows=[];all_values=[];panels=[];excluded=[]
for i,j in json.loads((D/'protocol/scope.json').read_text())['geometry_pairs_indices']:
    a,b=assoc[i],assoc[j]
    if float(a[0])<gt[0,0] or float(b[0])>gt[-1,0]:
        excluded.append({'i':i,'j':j,'reason':'GT would require extrapolation'});continue
    im1=cv2.imread(str(B/a[1]));im2=cv2.imread(str(B/b[1]));g1=cv2.cvtColor(im1,cv2.COLOR_BGR2GRAY);g2=cv2.cvtColor(im2,cv2.COLOR_BGR2GRAY)
    z1=cv2.imread(str(B/a[3]),-1).astype(float)/5000;z2=cv2.imread(str(B/b[3]),-1).astype(float)/5000
    p=cv2.goodFeaturesToTrack(g1,600,.02,12)
    q,st,_=cv2.calcOpticalFlowPyrLK(g1,g2,p,None,winSize=(21,21),maxLevel=3)
    back,sb,_=cv2.calcOpticalFlowPyrLK(g2,g1,q,None,winSize=(21,21),maxLevel=3)
    p=p.reshape(-1,2);q=q.reshape(-1,2);back=back.reshape(-1,2)
    valid=st.ravel().astype(bool)&sb.ravel().astype(bool)&(np.linalg.norm(back-p,axis=1)<=1.)
    valid&=(q[:,0]>=2)&(q[:,0]<638)&(q[:,1]>=2)&(q[:,1]<478)&(p[:,0]>=2)&(p[:,0]<638)&(p[:,1]>=2)&(p[:,1]<478)
    p=p[valid];q=q[valid];x1=np.rint(p).astype(int);x2=np.rint(q).astype(int);d1=z1[x1[:,1],x1[:,0]];d2=z2[x2[:,1],x2[:,0]]
    valid=(d1>.1)&(d2>.1)
    # Require stable dual-end depth, independently of any GT model residual.
    for zz,xx in [(z1,x1),(z2,x2)]:
        for k,(x,y) in enumerate(xx):
            patch=zz[y-1:y+2,x-1:x+2];v=patch[patch>0]
            if len(v)<5 or v.max()-v.min()>max(.05,.03*zz[y,x]):valid[k]=False
    p=p[valid];q=q[valid];d1=d1[valid];d2=d2[valid]
    uv=cv2.undistortPoints(p.reshape(-1,1,2),K,dist).reshape(-1,2);xyz=np.c_[uv,np.ones(len(uv))]*d1[:,None]
    h1=interpolate(gt,float(a[0]));h2=interpolate(gt,float(b[0]))
    for variant in variants:
        h=np.linalg.inv(corrected(h2,variant))@corrected(h1,variant);pred=xyz@h[:3,:3].T+h[:3,3]
        positive=pred[:,2]>.1
        projected=cv2.projectPoints(pred,np.zeros(3),np.zeros(3),K,dist)[0].reshape(-1,2)
        err=np.linalg.norm(projected-q,axis=1);dz=abs(pred[:,2]-d2)
        inside=positive&(projected[:,0]>=0)&(projected[:,0]<640)&(projected[:,1]>=0)&(projected[:,1]<480)
        # Occlusion checked against observed target surface, reported separately.
        occluded=np.zeros(len(p),bool)
        for n,(x,y) in enumerate(np.rint(projected).astype(int)):
            if inside[n]:
                obs=z2[y,x]
                occluded[n]=obs>0 and obs<pred[n,2]-max(.05,.03*pred[n,2])
        consistent=inside&(~occluded)&(err<=5)&(dz<=np.maximum(.05,.03*d2))
        row={'source_index':i,'target_index':j,'stamp_source':a[0],'stamp_target':b[0],'variant':variant,'quality_and_depth_pairs':len(p),'positive':int(positive.sum()),'inside':int(inside.sum()),'occluded':int(occluded.sum()),'consistent':int(consistent.sum()),'reprojection_median_px':float(np.median(err[positive])),'depth_error_median_m':float(np.median(dz[positive]))}
        rows.append(row)
        for n in range(len(p)):all_values.append([i,j,variant,n,err[n],dz[n],int(positive[n]),int(inside[n]),int(occluded[n]),int(consistent[n])])
    if i in [60,180,300,480]:
        panel=im1.copy()
        for (x,y) in np.rint(p).astype(int):cv2.circle(panel,(x,y),2,(0,255,0),-1)
        cv2.putText(panel,'OFFLINE LK/depth probe i='+str(i),(10,25),0,.65,(0,0,255),2);panels.append(panel)
with (D/'corrected/geometry_pairs.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
with (D/'corrected/geometry_observations.csv').open('w') as f:w=csv.writer(f);w.writerow(['i','j','variant','pair','reprojection_px','depth_error_m','positive','inside','occluded','consistent']);w.writerows(all_values)
summary={v:{'pairs':sum(x['quality_and_depth_pairs'] for x in rows if x['variant']==v),'consistent':sum(x['consistent'] for x in rows if x['variant']==v),'median_of_pair_reprojection_medians_px':float(np.median([x['reprojection_median_px'] for x in rows if x['variant']==v]))} for v in variants}
(D/'corrected/geometry_summary.json').write_text(json.dumps(summary,indent=2))
(D/'corrected/geometry_excluded.json').write_text(json.dumps(excluded,indent=2))
cv2.imwrite(str(D/'figures/geometry_probe_inputs.jpg'),np.vstack([np.hstack(panels[:2]),np.hstack(panels[2:])]))
print(json.dumps(summary,indent=2))
