from pathlib import Path
import json,subprocess,os,resource
import cv2,numpy as np
D=Path(__file__).resolve().parents[1];E=Path('/media/wcqw/KESU/slam_research/ngd_ccl_compat_20261020');P=Path('/media/wcqw/KESU/slam_research/ngd_native_recovery_20261020');B=P/'ngd-build'
l=json.loads((D/'audit/mask_original_link.json').read_text());l[l.index('-o')+1]=str(E/'yolo_compat');l=[x.replace(str(P/'NGD-SLAM/lib'),str(E/'lib')) for x in l]
with (D/'audit/mask_compat_link.log').open('w') as f:subprocess.run(l,cwd=B,stdout=f,stderr=subprocess.STDOUT,check=True)
Q=Path('/home/wcqw/passive_visual_slam_qualification_20261015/data/rgbd_dataset_freiburg3_walking_xyz');pairs=[x.split() for x in (Q/'associations.txt').read_text().splitlines() if x.strip() and not x.startswith('#')];plan=json.loads((D/'protocol/plan.json').read_text());rows=[]
for i in plan['actual_yolo_image_indices']:
 r={'index':i,'stamp':pairs[i][0]}
 for v in ['original','compat']:
  outfile=E/'probe_outputs'/f'mask_{v}_{i}.png';cmd=[str(E/('yolo_'+v)),str(Q/pairs[i][1]),str(Q/pairs[i][3]),str(outfile)]
  env=os.environ.copy();env['OPENCV_FOR_THREADS_NUM']='1';env['LD_LIBRARY_PATH']=':'.join(map(str,[P/'opencv-install/lib',P/'NGD-SLAM/lib' if v=='original' else E/'lib',P/'NGD-SLAM/Thirdparty/g2o/lib',P/'NGD-SLAM/Thirdparty/DBoW2/lib',Path('/home/wcqw/passive_visual_slam_qualification_20261015/local/lib')]))
  with (D/'audit'/f'mask_{v}_{i}.log').open('w') as f:p=subprocess.run(cmd,cwd=P/'NGD-SLAM' if v=='original' else E/'NGD-SLAM',env=env,stdout=f,stderr=subprocess.STDOUT,timeout=30,preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
  r[v+'_returncode']=p.returncode
  if p.returncode==0:
   m=cv2.imread(str(outfile),cv2.IMREAD_UNCHANGED);r[v+'_nonzero']=int(np.count_nonzero(m));r[v+'_shape']=list(m.shape)
 if r['original_returncode']==0 and r['compat_returncode']==0:
  a=cv2.imread(str(E/'probe_outputs'/f'mask_original_{i}.png'),-1);b=cv2.imread(str(E/'probe_outputs'/f'mask_compat_{i}.png'),-1);r['different_pixels']=int(np.count_nonzero(a!=b));r['final_masks_equal']=bool(np.array_equal(a,b))
 rows.append(r)
(D/'results/real_mask_comparison.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows,indent=2))
assert all(r['compat_returncode']==0 for r in rows)
assert all(r.get('final_masks_equal',True) for r in rows)
