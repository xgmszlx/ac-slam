from pathlib import Path
import json,subprocess,hashlib
D=Path(__file__).resolve().parents[1];E=Path('/media/wcqw/KESU/slam_research/ngd_native_recovery_20261020');r={}
for p in [E/'rgbd_tum_headless',E/'runtime_probe',E/'NGD-SLAM/lib/libORB_SLAM3.so',E/'NGD-SLAM/Examples/RGB-D/rgbd_tum',E/'NGD-SLAM/Thirdparty/DBoW2/lib/libDBoW2.so']:
 text=subprocess.check_output(['/usr/bin/ldd',str(p)]).decode();assert 'not found' not in text
 cv=[l.strip() for l in text.splitlines() if 'libopencv_' in l]
 assert cv and all(str(E/'opencv-install/lib') in l for l in cv),cv
 assert not any('.so.4.2' in l for l in cv)
 r[str(p)]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'opencv':cv,'ldd':text}
(D/'audit/runtime_linkage.json').write_text(json.dumps(r,indent=2));print('All NGD/DBoW2/probe OpenCV runtime libraries resolve only to isolated 4.5.5')
