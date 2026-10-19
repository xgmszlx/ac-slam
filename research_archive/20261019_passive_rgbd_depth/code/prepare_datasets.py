from pathlib import Path
import sys,json,hashlib,tarfile,shutil
import numpy as np
from PIL import Image
import subprocess
P=Path(__file__).resolve().parents[1];old=Path('/home/wcqw/passive_visual_slam_qualification_20261015')
sys.path.insert(0,str(old/'code'));from evaluate import read_rows,associate
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for short,fr in [('desk','freiburg1'),('large_cabinet','freiburg3')]:
 a=P/'data'/f'{short}.tgz';audit=P/'audit'/f'dataset_{short}.json'
 # Must have every expected range and a full final hash marker, never accept preallocated size alone.
 ledger=json.loads(a.with_suffix('.tgz.ranges.json').read_text());size=a.stat().st_size;starts=sorted(x['start'] for x in ledger);assert starts==list(range(0,size,16*1024*1024));assert sum(x['end']-x['start']+1 for x in ledger)==size
 with tarfile.open(a) as tar:
  members=tar.getmembers();needed=sum(x.size for x in members if x.isfile());assert needed+5*1024**3<shutil.disk_usage(P).free
  for m in members:
   assert not m.name.startswith('/') and '..' not in Path(m.name).parts and (m.isfile() or m.isdir()),m.name
  tar.extractall(P/'data',filter='data')
 d=P/'data'/f'rgbd_dataset_{fr}_{short}';rgb=read_rows(d/'rgb.txt');depth=read_rows(d/'depth.txt');rt=np.array([float(x[0]) for x in rgb]);dt=np.array([float(x[0]) for x in depth]);assert (np.diff(rt)>0).all() and (np.diff(dt)>0).all();pairs=associate(rt,dt)
 with (d/'associations.txt').open('w') as f:
  for i,j in pairs:f.write(' '.join(rgb[i]+depth[j])+'\n')
 images={};zeros=[];color=[]
 for k,(i,j) in enumerate(pairs):
  for typ,row in [('rgb',rgb[i]),('depth',depth[j])]:
   q=d/row[1]
   with Image.open(q) as im:im.load();assert im.size==(640,480)
   images[row[1]]=sha(q)
  raw=np.array(Image.open(d/depth[j][1]));assert raw.ndim==2 and raw.max()<=65535;zeros.append(float(np.mean(raw==0)))
  if k in [0,len(pairs)//2,len(pairs)-1]:
   aRGB=np.array(Image.open(d/rgb[i][1]));probe="import cv2,hashlib,sys,json; a=cv2.imread(sys.argv[1],-1);print(json.dumps({'sha':hashlib.sha256(a[:,:,::-1].tobytes()).hexdigest(),'version':cv2.__version__}))";native=json.loads(subprocess.check_output(['/usr/bin/python3','-c',probe,str(d/rgb[i][1])]).decode());assert hashlib.sha256(aRGB.tobytes()).hexdigest()==native['sha'];color.append(k)
 gt=np.array(read_rows(d/'groundtruth.txt'),dtype=float);assert (np.diff(gt[:,0])>0).all() and np.isfinite(gt).all();diff=[abs(rt[i]-dt[j]) for i,j in pairs]
 yaml=(old/'sources/ORB_SLAM3-4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4/Examples/RGB-D'/('TUM1.yaml' if fr=='freiburg1' else 'TUM3.yaml')).read_text().replace('Camera.RGB: 1','Camera.RGB: 0');(P/'config'/f'{short}.yaml').write_text(yaml)
 (P/'data'/f'{short}_image_hashes.json').write_text(json.dumps(images,sort_keys=True))
 result={'sequence':d.name,'source':'Official TUM -> webshare.cvg.cit.tum.de HTTPS redirect','archive_bytes':size,'archive_sha256':sha(a),'extracted_payload_bytes':needed,'rgb_count':len(rgb),'depth_count':len(depth),'associated_count':len(pairs),'association':'Frozen original greedy unique, abs dt <20ms','association_abs_dt_max_s':max(diff),'association_abs_dt_median_s':float(np.median(diff)),'input_stamp_range':[rt[pairs[0][0]],rt[pairs[-1][0]]],'GT_stamp_range':[gt[0,0],gt[-1,0]],'GT_count':len(gt),'depth_factor':5000,'extra_depth_rescale':False,'invalid_depth_fraction_mean':float(np.mean(zeros)),'association_sha256':sha(d/'associations.txt'),'GT_sha256':sha(d/'groundtruth.txt'),'image_manifest_sha256':sha(P/'data'/f'{short}_image_hashes.json'),'BGR_RGB_pixel_proof_frames':color,'yaml_sha256':sha(P/'config'/f'{short}.yaml'),'GT_online':False,'Python_cv2_version':native['version']};audit.write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
