"""Render original accepted input RGB/depth; missing recorded masks stay missing."""
from pathlib import Path
import json,hashlib
import numpy as np
import cv2
D=Path(__file__).resolve().parents[1]
B=Path('/home/wcqw/passive_rgbd_combo_20261019/e2e_20261020/data/rgbd_bonn_moving_obstructing_box')
a=[x.split() for x in (B/'associations.txt').read_text().splitlines() if x.strip() and not x.startswith('#')]
panels=[]
for i in [271,292,299]:
    e=D/'events'/str(i);im=cv2.imread(str(B/a[i][1]));raw=cv2.imread(str(B/a[i][3]),-1);z=raw.astype(float)/5000
    depth=cv2.applyColorMap(np.uint8(np.clip(z/5,0,1)*255),cv2.COLORMAP_TURBO);depth[raw==0]=0
    # Source derived images are labelled; no feature or mask reconstruction occurs.
    cv2.imwrite(str(e/'input_rgb.jpg'),im);cv2.imwrite(str(e/'depth_visualization_0_5m.png'),depth)
    note=np.full_like(im,55)
    for y,t in enumerate(['Original event masks NOT RECORDED','Deleted LK/ORB pixel identities UNKNOWN','No replay / no synthetic reconstruction']):cv2.putText(note,t,(12,150+y*45),0,.6,(255,255,255),1)
    cv2.putText(im,'Input '+str(i)+' original RGB',(10,25),0,.65,(0,0,255),2);cv2.putText(depth,'Registered depth, display 0-5 m',(10,25),0,.6,(255,255,255),1)
    panels.append(np.hstack([im,depth,note]))
    (e/'input_identity.json').write_text(json.dumps({'index':i,'rgb_stamp':a[i][0],'depth_stamp':a[i][2],'rgb_path':str(B/a[i][1]),'depth_path':str(B/a[i][3]),'rgb_sha256':hashlib.sha256((B/a[i][1]).read_bytes()).hexdigest(),'depth_sha256':hashlib.sha256((B/a[i][3]).read_bytes()).hexdigest(),'visualization':'fixed 0-5m, invalid black; raw pixels not modified'},indent=2))
cv2.imwrite(str(D/'figures/three_event_inputs.jpg'),np.vstack(panels))
