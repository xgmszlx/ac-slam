from pathlib import Path
import json,subprocess,difflib,hashlib
N=Path(__file__).resolve().parents[1];P=Path('/home/wcqw/passive_rgbd_combo_20261019');S=Path('/home/wcqw/passive_visual_slam_qualification_20261015/sources/ORB_SLAM3-4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4');records=[]
old=json.loads((P/'audit/build_commands.json').read_text());cmd=old['compile'][3].copy();cmd=[x.replace(str(P/'code'),str(N/'code')).replace(str(P/'build/Combo.o'),str(N/'build/Combo.o')) for x in cmd]
link=[str(N/'build/Combo.o') if x==str(P/'build/Combo.o') else x for x in old['link']];link[link.index('-o')+1]=str(N/'build/libORB_SLAM3.so')
entry=json.loads((P/'audit/entry_build.json').read_text());ec=[x.replace(str(P/'code'),str(N/'code')).replace(str(P/'build/rgbd_combo.o'),str(N/'build/rgbd_combo.o')) for x in entry['compile']]
el=[x.replace(str(P/'build/rgbd_combo.o'),str(N/'build/rgbd_combo.o')).replace(str(P/'build/libORB_SLAM3.so'),str(N/'build/libORB_SLAM3.so')) for x in entry['link']];el[el.index('-o')+1]=str(N/'build/rgbd_combo')
for label,c in [('Combo',cmd),('core_link',link),('entry',ec),('entry_link',el)]:
 with (N/'audit'/('build_'+label+'.log')).open('w') as log:subprocess.run(c,cwd=S/'build',stdout=log,stderr=subprocess.STDOUT,check=True)
 records.append({'label':label,'command':c})
(N/'audit/build_commands.json').write_text(json.dumps(records,indent=2))
patch=''
for name in ['Combo.cc','rgbd_combo.cc']:patch+=''.join(difflib.unified_diff((P/'code'/name).read_text().splitlines(True),(N/'code'/name).read_text().splitlines(True),fromfile='previous/code/'+name,tofile='ablation/code/'+name))
(N/'audit/switches.patch').write_text(patch)
print('Only Combo and small entry recompiled; Frame/Optimizer/System and original objects reused unchanged.')
