from pathlib import Path
import json,subprocess,os,time
import numpy as np
from PIL import Image,ImageDraw
D=Path(__file__).resolve().parents[1];P=Path('/media/wcqw/KESU/slam_research/ngd_native_recovery_20261020');E1=P.parent/'ngd_ccl_compat_20261020';E=P.parent/'ngd_scientific_baseline_20261020';E.mkdir(exist_ok=True);frozen=D/'protocol/bonn_probe_frozen.json';plan=json.loads(frozen.read_text());B=Path(plan['sequence']);out=D/'results/independent_YOLO';assert not out.exists();out.mkdir()
# Visible-box polygon authored from the raw contact sheet BEFORE any mask/inference score; not per-feature motion ground truth.
poly={'frame':294,'polygon_xy':[[0,8],[297,35],[295,465],[0,479]],'label':'coarse visible box interior, assistant annotation from raw RGB only; not motion truth or independent human verification'}
(D/'protocol/visible_box_region_before_masks.json').write_text(json.dumps(poly,indent=2))
env=os.environ.copy();env['OPENCV_FOR_THREADS_NUM']='1';env['LD_LIBRARY_PATH']=':'.join(map(str,[E1/'lib',P/'opencv-install/lib',P/'NGD-SLAM/Thirdparty/DBoW2/lib',P/'NGD-SLAM/Thirdparty/g2o/lib',Path('/home/wcqw/passive_visual_slam_qualification_20261015/local/lib')]))
binary=E1/'yolo_compat';summary=[];sheet=Image.new('RGB',(640*3,510*2),'white');dr=ImageDraw.Draw(sheet)
for n,row in enumerate(plan['frames']):
 i=row['index'];a=row['assoc'];mask=E/f'mask_{i}.png';cmd=[str(binary),str(B/a[1]),str(B/a[3]),str(mask)]
 start=time.monotonic()
 with (out/f'{i}.log').open('w') as log:r=subprocess.run(cmd,cwd=E1/'NGD-SLAM',env=env,stdout=log,stderr=subprocess.STDOUT,timeout=30)
 item={'index':i,'stamp':a[0],'exit':r.returncode,'standalone_process_wall_s':time.monotonic()-start,'command':cmd,'NOT_actual_M0_mask':True}
 im=Image.open(B/a[1]).convert('RGB')
 if r.returncode==0:
  z=np.array(Image.open(mask))>0;item['postprocessed_mask_fraction']=float(z.mean());arr=np.array(im).copy();arr[z]=(arr[z]*.5+np.array([255,0,0])*.5).astype(np.uint8);im=Image.fromarray(arr)
  if i==poly['frame']:
   roi=Image.new('1',im.size);ImageDraw.Draw(roi).polygon([tuple(p) for p in poly['polygon_xy']],fill=1);roi=np.array(roi,dtype=bool);item['coarse_visible_box_pixels']=int(roi.sum());item['coarse_visible_box_masked_fraction']=float(z[roi].mean());ImageDraw.Draw(im).line([tuple(p) for p in poly['polygon_xy']]+[tuple(poly['polygon_xy'][0])],fill='yellow',width=3)
 x=(n%3)*640;y=(n//3)*510;sheet.paste(im,(x,y+25));dr.text((x+5,y+5),f'Bonn frame {i}; standalone YOLO (not M0 trace)',fill='black');summary.append(item)
sheet.save(D/'figures/bonn_independent_detector.jpg');(out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
