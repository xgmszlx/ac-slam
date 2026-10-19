from pathlib import Path
import json,subprocess
P=Path(__file__).resolve().parents[1];O=Path('/home/wcqw/passive_rgbd_depth_screen_20261019');S=Path('/home/wcqw/passive_visual_slam_qualification_20261015/sources/ORB_SLAM3-4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4');c=json.loads((O/'audit/entry_build.json').read_text())[0]
comp=c['compile'].copy();comp.insert(1,'-I'+str(P/'code'));comp[comp.index('-c')+1]=str(P/'code/rgbd_combo.cc');comp[-1]=str(P/'build/rgbd_combo.o')
link=c['link'].copy();link=[str(P/'build/rgbd_combo.o') if x==str(O/'build/rgbd_screen.o') else str(P/'build/libORB_SLAM3.so') if x==str(O/'build/libORB_SLAM3.so') else x for x in link];link[link.index('-o')+1]=str(P/'build/rgbd_combo')
with (P/'audit/build_entry.log').open('w') as log:
 subprocess.run(comp,cwd=S/'build',stdout=log,stderr=subprocess.STDOUT,check=True);subprocess.run(link,cwd=S/'build',stdout=log,stderr=subprocess.STDOUT,check=True)
(P/'audit/entry_build.json').write_text(json.dumps({'compile':comp,'link':link},indent=2));print('Entry built.')
