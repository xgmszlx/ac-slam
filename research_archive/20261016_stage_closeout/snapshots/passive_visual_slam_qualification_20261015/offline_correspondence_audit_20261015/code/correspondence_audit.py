import pathlib,json,csv,hashlib,collections,time,sys
import cv2,numpy as np
from geometry import pose_at,backproject,transform,project,angle_deg
N=pathlib.Path(__file__).resolve().parents[1];D=N.parent/'data/rgbd_dataset_freiburg3_walking_xyz';P=json.loads((N/'protocol/design_v02.json').read_text());A=json.loads((N/'annotations/manual_person_v02.json').read_text());cv2.setNumThreads(1);cv2.setRNGSeed(20261015)
C=P['camera'];K=np.array([[C['fx'],0,C['cx']],[0,C['fy'],C['cy']],[0,0,1.]])

def labels(index):
 mask=np.zeros((480,640),np.uint8);core=np.zeros_like(mask)
 for obj in A['frames'][str(index)]['objects']:
  x1,y1,x2,y2=obj['bbox'];mask[max(0,y1-5):min(480,y2+5),max(0,x1-5):min(640,x2+5)]=2
  poly=obj['person_core_polygon']
  if poly:cv2.fillPoly(core,[np.array(poly,np.int32)],255)
 core=cv2.erode(core,np.ones((7,7),np.uint8));mask[core>0]=1
 return mask
frames={f['index']:f for p in P['pairs'] for f in p['frames']}
if len(sys.argv)>1 and sys.argv[1]=='--labels-only':
 for window in ['before','critical','after']:
  tiles=[]
  for pair in [p for p in P['pairs'] if p['window']==window]:
   row=[]
   for f in pair['frames']:
    im=cv2.imread(str(D/f['rgb']));m=labels(f['index']);v=im.copy();v[m==1]=(v[m==1]*.55+np.array([0,0,255])*.45).astype(np.uint8);v[m==2]=(v[m==2]*.6+np.array([0,210,255])*.4).astype(np.uint8)
    cv2.putText(v,f"{pair['id']} frame {f['index']}",(8,22),cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),2);row.append(v)
   tiles.append(np.hstack(row))
  cv2.imwrite(str(N/'figures'/('annotation_labels_'+window+'.jpg')),np.vstack(tiles))
 print('manual labels only; no feature matches evaluated');sys.exit(0)
assert not (N/'results/matches.csv').exists(),'preserve any previous outcomes'
orb=cv2.ORB_create(nfeatures=1000,scaleFactor=1.2,nlevels=8,edgeThreshold=31,firstLevel=0,WTA_K=2,scoreType=cv2.ORB_HARRIS_SCORE,patchSize=31,fastThreshold=20);gt=np.loadtxt(D/'groundtruth.txt');frame_data={};frame_records=[];start=time.monotonic()
def z_at(depth,xy):return float(depth[int(xy[1]),int(xy[0])])
def stable(depth,xy):
 x,y=int(xy[0]),int(xy[1]);patch=depth[max(0,y-1):y+2,max(0,x-1):x+2];return patch.shape==(3,3) and bool(np.all(patch>0)) and float(patch.max()-patch.min())<=.1
for i,f in sorted(frames.items()):
 assert hashlib.sha256((D/f['rgb']).read_bytes()).hexdigest()==f['rgb_sha256'];assert hashlib.sha256((D/f['depth']).read_bytes()).hexdigest()==f['depth_sha256']
 im=cv2.imread(str(D/f['rgb']),-1);raw=cv2.imread(str(D/f['depth']),-1);assert im.shape==(480,640,3) and raw.dtype==np.uint16;gray=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY);depth=raw.astype(float)/5000;mask=labels(i);keys,des=orb.detectAndCompute(gray,None);Twc,gap=pose_at(gt,float(f['stamp']));frame_data[i]=(keys,des,depth,mask,Twc)
 rec={'index':i,'stamp':f['stamp'],'relative_s':f['relative_s'],'features':len(keys),'depth_valid_fraction':float(np.mean(depth>0)),'RGB_depth_abs_dt_ms':abs(float(f['stamp'])-float(f['depth_stamp']))*1000,'GT_bracket_s':gap,'laplacian_variance':float(cv2.Laplacian(gray,cv2.CV_64F).var())}
 for label,name in [(0,'B'),(1,'P'),(2,'U')]:
  cells=mask==label;pts=[k for k in keys if mask[int(k.pt[1]),int(k.pt[0])]==label];rec[name+'_area_fraction']=float(np.mean(cells));rec[name+'_pixel_depth_valid_fraction']=float(np.mean(depth[cells]>0)) if np.any(cells) else None;rec[name+'_features']=len(pts);rec[name+'_depth_features']=sum(z_at(depth,k.pt)>0 for k in pts);rec[name+'_stable_depth_features']=sum(stable(depth,k.pt) for k in pts)
 frame_records.append(rec)
 cv2.imwrite(str(N/'annotations'/(str(i)+'_labels.png')),mask)
all_rows=[];pair_records=[];occlusion=[];bf=cv2.BFMatcher(cv2.NORM_HAMMING)
name={0:'B',1:'P',2:'U'}
for pair in P['pairs']:
 f1,f2=pair['frames'];k1,d1,z1,m1,T1=frame_data[f1['index']];k2,d2,z2,m2,T2=frame_data[f2['index']];T=np.linalg.inv(T2)@T1;forward=bf.knnMatch(d1,d2,k=2);reverse=bf.knnMatch(d2,d1,k=2);rev={r[0].queryIdx:r for r in reverse if len(r)==2}
 nratio=nmutual=nselected=0
 for ds in forward:
  if len(ds)<2:continue
  match,second=ds;qi,ti=match.queryIdx,match.trainIdx;xy1=k1[qi].pt;xy2=k2[ti].pt;ra=bool(match.distance<.75*second.distance);back=rev.get(ti);mut=back is not None and back[0].trainIdx==qi;br=back is not None and back[0].distance<.75*back[1].distance;sel=ra and mut and br;nratio+=ra;nmutual+=mut;nselected+=sel
  l1,l2=name[int(m1[int(xy1[1]),int(xy1[0])])],name[int(m2[int(xy2[1]),int(xy2[0])])];depth1=z_at(z1,xy1);depth2=z_at(z2,xy2)
  r={'pair':pair['id'],'window':pair['window'],'source_index':f1['index'],'target_index':f2['index'],'queryIdx':qi,'trainIdx':ti,'x1':float(xy1[0]),'y1':float(xy1[1]),'x2':float(xy2[0]),'y2':float(xy2[1]),'hamming':float(match.distance),'distance_ratio':float(match.distance/second.distance) if second.distance else None,'forward_ratio':int(ra),'mutual_NN':int(mut),'mutual_ratio':int(sel),'label1':l1,'label2':l2,'group':l1+l2,'depth1_m':depth1,'depth2_m':depth2,'both_depth':int(depth1>0 and depth2>0),'stable_depth_both':int(stable(z1,xy1) and stable(z2,xy2)),'valid_3D':0,'reprojection_px':None,'depth_error_m':None,'depth_tolerance_m':None,'residual_3D_m':None,'consistent_primary':0,'reproj3_and_depth':0,'reproj8_and_depth':0,'predicted_x2':None,'predicted_y2':None,'X1':None,'Y1':None,'Z1':None}
  if depth1>0 and depth2>0:
   X1=backproject(xy1,depth1,K);pred=transform(T,X1);X2=backproject(xy2,depth2,K)
   if pred[2]>0:
    uv=project(pred,K);err=float(np.linalg.norm(uv-np.array(xy2)));ze=float(abs(pred[2]-depth2));tol=max(.05,.03*pred[2]);r.update(valid_3D=1,reprojection_px=err,depth_error_m=ze,depth_tolerance_m=float(tol),residual_3D_m=float(np.linalg.norm(pred-X2)),predicted_x2=float(uv[0]),predicted_y2=float(uv[1]),X1=float(X1[0]),Y1=float(X1[1]),Z1=float(X1[2]),consistent_primary=int(err<=5 and ze<=tol),reproj3_and_depth=int(err<=3 and ze<=tol),reproj8_and_depth=int(err<=8 and ze<=tol))
  all_rows.append(r)
 pair_records.append({'pair':pair['id'],'window':pair['window'],'source_index':f1['index'],'target_index':f2['index'],'source_t':f1['relative_s'],'target_t':f2['relative_s'],'dt_s':float(f2['stamp'])-float(f1['stamp']),'features1':len(k1),'features2':len(k2),'forward_NN':len(forward),'forward_ratio':int(nratio),'mutual_NN':int(nmutual),'mutual_ratio':int(nselected),'GT_translation_m':float(np.linalg.norm(T[:3,3])),'GT_rotation_deg':angle_deg(T[:3,:3]),'T_target_source_GT':T.tolist()})
 # Separate no-descriptor test: GT-warp source nonperson 3D features into target image.
 occ={'pair':pair['id'],'window':pair['window'],'source_B_depth':0,'projected_in_image':0,'target_depth_valid':0,'target_nearer_than_static_prediction':0,'nearer_and_target_P':0,'nearer_and_target_U':0,'nearer_and_target_B':0,'GT_depth_consistent_B':0}
 for key in k1:
  xy=key.pt;z=z_at(z1,xy)
  if m1[int(xy[1]),int(xy[0])]!=0 or z<=0:continue
  occ['source_B_depth']+=1;pred=transform(T,backproject(xy,z,K))
  if pred[2]<=0:continue
  uv=project(pred,K);x,y=int(np.floor(uv[0])),int(np.floor(uv[1]))
  if not(0<=x<640 and 0<=y<480):continue
  occ['projected_in_image']+=1;observed=z2[y,x]
  if observed<=0:continue
  occ['target_depth_valid']+=1;tol=max(.05,.03*pred[2]);label=name[int(m2[y,x])]
  if observed<pred[2]-tol:occ['target_nearer_than_static_prediction']+=1;occ['nearer_and_target_'+label]+=1
  if label=='B' and abs(observed-pred[2])<=tol:occ['GT_depth_consistent_B']+=1
 occlusion.append(occ)
for file,rows in [('matches.csv',all_rows),('frames.csv',frame_records),('pairs.csv',[{k:v for k,v in r.items() if k!='T_target_source_GT'} for r in pair_records]),('occlusion.csv',occlusion)]:
 with (N/'results'/file).open('w') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(N/'results/pair_GT_geometry.json').write_text(json.dumps(pair_records,indent=2));(N/'audit/execution.json').write_text(json.dumps({'label':'OFFLINE_DIAGNOSTIC','opencv':cv2.__version__,'frames':len(frame_data),'pairs':len(P['pairs']),'elapsed_s':time.monotonic()-start,'matches_are_actual_SLAM_inliers':False,'manual_annotation_sha256':hashlib.sha256((N/'annotations/manual_person_v02.json').read_bytes()).hexdigest(),'design_sha256':hashlib.sha256((N/'protocol/design_v02.json').read_bytes()).hexdigest(),'GT_offline_only':True,'RANSAC_prefilter':False},indent=2));print('OFFLINE_DIAGNOSTIC complete: 9 pairs; all raw correspondence rows retained')
