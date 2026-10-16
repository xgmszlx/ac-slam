import pathlib,json,hashlib,time
import cv2,numpy as np
from PIL import Image
N=pathlib.Path(__file__).resolve().parents[1]; O=N.parent
result={'opencv':cv2.__version__,'sequences':{}}; start=time.monotonic()
for seq in ['walking_xyz','sitting_xyz']:
 d=O/'data'/('rgbd_dataset_freiburg3_'+seq); rows=[s.split() for s in (d/'associations.txt').read_text().splitlines() if s.strip() and not s.startswith('#')]; differences=[]; digest=hashlib.sha256(); mismatches=[]; pil_checks=[]
 for i,row in enumerate(rows):
  p=d/row[1]; bgr=cv2.imread(str(p),cv2.IMREAD_UNCHANGED); assert bgr.shape==(480,640,3) and bgr.dtype==np.uint8
  p0=cv2.cvtColor(bgr,cv2.COLOR_RGB2GRAY); p1=cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY)
  alternate=cv2.cvtColor(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB),cv2.COLOR_RGB2GRAY)
  if not np.array_equal(p1,alternate):mismatches.append(i)
  differences.append(float(np.abs(p0.astype(float)-p1).mean())); digest.update(row[0].encode());digest.update(p1.tobytes())
  if i in sorted(set([0,len(rows)//4,len(rows)//2,3*len(rows)//4,len(rows)-1,17,103])):
   assert np.array_equal(bgr,np.array(Image.open(p))[:,:,::-1]);pil_checks.append(i)
 assert not mismatches
 result['sequences'][seq]={'frames':len(rows),'equivalence_mismatches':mismatches,'PIL_RGB_vs_imread_BGR_exact_indices':pil_checks,'P1_gray_stream_sha256':digest.hexdigest(),'P0_vs_P1_mean_abs_pixel_difference_mean':float(np.mean(differences)),'P0_vs_P1_mean_abs_pixel_difference_range':[min(differences),max(differences)],'association_sha256':hashlib.sha256((d/'associations.txt').read_bytes()).hexdigest()}
result['elapsed_s']=time.monotonic()-start;result['PASS']=True
(N/'audit/color_proof.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
