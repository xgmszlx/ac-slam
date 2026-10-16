from pathlib import Path
import sys,json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image
p=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(p/'sources/eval_deps'),str(p/'sources/LILocBench-68e86f33ae3ff660444b92093fb98ca4d5633b46/src')]
import evaluate as ev
fig,axs=plt.subplots(2,2,figsize=(12,8))
mapim=Image.open(p/'data/map/map_office.png').convert('L');w,h=mapim.size
meta={'image_shape':[h,w],'resolution_m':.05,'origin':[-25.,-25.,0.],'extent':[-25.,-25.+w*.05,-25.,-25.+h*.05],'map_image_sha256':__import__('hashlib').sha256((p/'data/map/map_office.png').read_bytes()).hexdigest(),'gt':{}}
for col,seq in enumerate(['static_0','lt_changes_0']):
 tg,pg=ev.load_poses_tum_format(str(p/'data/gt'/seq/'gt_poses.txt'))
 tl,pl=ev.load_poses_tum_format(str(p/'data/example'/seq/'run_1.txt'))
 il=ev.interpolate_poses(tg,tl,pl);tr,rr=ev.ape2d(pg,il)
 ax=axs[0,col];ax.imshow(mapim,cmap='gray',origin='upper',extent=meta['extent'],vmin=0,vmax=255);ax.plot(pg[:,0,3],pg[:,1,3],lw=1,label='GT base_link');ax.plot(pl[:,0,3],pl[:,1,3],lw=.8,label='AUTHOR example run_1')
 ax.scatter(pl[0,0,3],pl[0,1,3],marker='x',color='red',label='Author initial estimate');ax.set_xlim(-15,16);ax.set_ylim(-16,6);ax.set_aspect('equal');ax.legend(fontsize=7);ax.set_title(seq+' | no spatial alignment');ax.set_xlabel('map x [m]');ax.set_ylabel('map y [m]')
 ax=axs[1,col];ax.plot(tg-tg[0],tr,lw=.8);ax.axhline(.2,c='r',ls='--',lw=.8);ax.set_xlabel('Time since GT start [s]');ax.set_ylabel('Position error [m]');ax.set_title('AUTHOR EXAMPLE only; not local pose-tracking run');ax.grid(alpha=.2)
 meta['gt'][seq]={'rows':len(tg),'first_stamp':float(tg[0]),'last_stamp':float(tg[-1]),'max_gap_s':float(np.diff(tg).max()),'unique_strict_increasing':bool(np.all(np.diff(tg)>0)),'z_range_m':[float(pg[:,2,3].min()),float(pg[:,2,3].max())],'initial_xy_yaw':[float(pg[0,0,3]),float(pg[0,1,3]),float(__import__('scipy').spatial.transform.Rotation.from_matrix(pg[0,:3,:3]).as_euler('ZYX')[0])]}
fig.suptitle('Official author example evaluation audit — no local AMCL experiment',fontsize=12);fig.tight_layout();fig.savefig(p/'figures/author_example_audit.png',dpi=150)
(p/'audit/map_gt_qualification.json').write_text(json.dumps(meta,indent=2))
