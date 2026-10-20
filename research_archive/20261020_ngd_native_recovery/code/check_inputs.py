from pathlib import Path
import csv,hashlib,json
import cv2,numpy as np
D=Path(__file__).resolve().parents[1];Q=Path('/home/wcqw/passive_visual_slam_qualification_20261015/data/rgbd_dataset_freiburg3_walking_xyz')
rows=[l.split() for l in (Q/'associations.txt').read_text().splitlines() if l.strip() and not l.startswith('#')]
t=np.array([float(r[0]) for r in rows]);dt=np.array([abs(float(r[0])-float(r[2])) for r in rows]);assert len(rows)==827 and np.all(np.diff(t)>0)
records=[]
for i,r in enumerate(rows):
 rgb=cv2.imread(str(Q/r[1]),cv2.IMREAD_UNCHANGED);dep=cv2.imread(str(Q/r[3]),cv2.IMREAD_UNCHANGED)
 assert rgb.shape==(480,640,3) and rgb.dtype==np.uint8 and dep.shape==(480,640) and dep.dtype==np.uint16
 records.append({'index':i,'stamp':r[0],'rgb':r[1],'depth_stamp':r[2],'depth':r[3],'rgb_sha256':hashlib.sha256((Q/r[1]).read_bytes()).hexdigest(),'depth_sha256':hashlib.sha256((Q/r[3]).read_bytes()).hexdigest(),'valid_depth_fraction':float(np.mean(dep>0))})
gt=np.loadtxt(Q/'groundtruth.txt');assert np.all(np.diff(gt[:,0])>0) and np.all(np.isfinite(gt))
a=Path('/media/wcqw/KESU/slam_research/ngd_native_recovery_20261020/NGD-SLAM/Examples/RGB-D/TUM3.yaml').read_text();b=(D/'config/TUM3_BGR.yaml').read_text()
assert a.replace('Camera.RGB: 1','Camera.RGB: 0').strip()==b.strip()
r={'sequence':str(Q),'inputs':len(rows),'duration_s':float(t[-1]-t[0]),'rgb_depth_max_difference_s':float(dt.max()),'gt_rows':len(gt),'gt_range':[float(gt[0,0]),float(gt[-1,0])],'input_format':'OpenCV BGR; Camera.RGB=0; depth/5000','config':'all author TUM3 settings unchanged except actual BGR input flag','association_sha256':hashlib.sha256((Q/'associations.txt').read_bytes()).hexdigest(),'gt_sha256':hashlib.sha256((Q/'groundtruth.txt').read_bytes()).hexdigest()}
(D/'audit/walking_input.json').write_text(json.dumps(r,indent=2));(D/'audit/input_images.json').write_text(json.dumps(records,indent=2));print(json.dumps(r,indent=2))
