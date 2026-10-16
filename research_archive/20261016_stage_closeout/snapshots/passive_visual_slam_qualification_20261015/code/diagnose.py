"""Offline state/coverage/image-space diagnosis, not a dynamic classifier."""
import csv
import json
from pathlib import Path
import sys
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from evaluate import read_rows, stats, associate

p=Path(__file__).resolve().parents[1];name,run_name=sys.argv[1:]
seq=p/'data'/('rgbd_dataset_freiburg3_'+name);run=p/'results'/name/run_name
out=run/'diagnosis';out.mkdir(exist_ok=True)
rows=list(csv.DictReader((run/'frame_states.csv').open()))
frames={}
for row in csv.DictReader((run/'keypoints.csv').open()):
    k=int(row['index']);frames.setdefault(k,[]).append([float(row['x']),float(row['y']),int(row['nonnull_association'])])
assoc=read_rows(seq/'associations.txt')
data=[]
for row in rows:
    i=int(row['index']); xy=np.asarray(frames.get(i,[]),dtype=float).reshape(-1,3)
    selected=xy[xy[:,2]>0,:2] if len(xy) else np.empty((0,2))
    if len(selected)>=3:
        z=selected/np.array([640,480]);ev=np.linalg.eigvalsh(np.cov(z.T))
        ratio=float(ev[0]/max(ev[1],1e-12))
        cells=np.clip((selected/np.array([80,80])).astype(int),[0,0],[7,5])
        occupancy=len(set(map(tuple,cells)))/48
    else:ratio=float('nan');occupancy=0
    with Image.open(seq/assoc[i][1]) as im:
        gray=np.asarray(im.convert('L'),dtype=float)
    lap=-4*gray[1:-1,1:-1]+gray[2:,1:-1]+gray[:-2,1:-1]+gray[1:-1,2:]+gray[1:-1,:-2]
    with Image.open(seq/assoc[i][3]) as im:depth=np.asarray(im)
    data.append({'index':i,'stamp':float(row['stamp']),'state':int(row['state']),
                 'n_keypoints':int(row['n_keypoints']),'n_nonnull':int(row['n_nonnull_associations']),
                 'xy_cov_eigen_ratio':ratio,'occupied_8x6_fraction':occupancy,
                 'depth_zero_fraction':float(np.mean(depth==0)),
                 'image_laplacian_variance':float(lap.var()),
                 'track_s':float(row['track_s']),'observer_s':float(row['observer_s'])})
with (out/'per_frame.csv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
states=np.array([r['state'] for r in data]);ts=np.array([r['stamp'] for r in data]);t=ts-ts[0]
intervals=[]
for row in data:
    if not intervals or intervals[-1]['state']!=row['state']:
        intervals.append({'state':row['state'],'first':row['index'],'last':row['index'],'start':row['stamp'],'end':row['stamp'],'n':1})
    else:intervals[-1].update(last=row['index'],end=row['stamp'],n=intervals[-1]['n']+1)
summary={'rows':len(data),'state_counts':{str(s):int(sum(states==s)) for s in np.unique(states)},
         'state_intervals':intervals,'tracking_time_s':stats([r['track_s'] for r in data]),
         'observer_time_s':stats([r['observer_s'] for r in data]),
         'nonnull_is_not_verified_static_or_inlier':True,
         'xy_distribution_is_not_pose_uncertainty':True,
         'relocalization_event':'transition to OK is observable; success against old-map identity not certified by these getters'}
(out/'summary.json').write_text(json.dumps(summary,indent=2))
ate=list(csv.DictReader((run/'evaluation/ate.csv').open()))
at=np.array([float(r['stamp']) for r in ate]);av=np.array([float(r['error_m']) for r in ate])
fig,ax=plt.subplots(4,1,figsize=(12,10),sharex=True)
ax[0].step(t,states,where='post');ax[0].set(yticks=[1,2,3,4],yticklabels=['INIT','OK','RECENT_LOST','LOST'],ylabel='state')
ax[1].plot(t,[r['n_keypoints'] for r in data],label='extracted')
ax[1].plot(t,[r['n_nonnull'] for r in data],label='nonnull associations');ax[1].legend();ax[1].set_ylabel('features')
ax[2].plot(t,[r['occupied_8x6_fraction'] for r in data],label='image cells occupied')
ax[2].plot(t,[r['xy_cov_eigen_ratio'] for r in data],label='2D covariance ratio');ax[2].legend();ax[2].set_ylabel('image-space only')
ax[3].plot(at-ts[0],av,label='final-trajectory ATE (offline GT)');ax[3].legend();ax[3].set(xlabel='input timestamp relative time (s)',ylabel='m')
fig.suptitle(name+' / public-getter observer replay\nViewer SIGSEGV after export; these are pre-shutdown states');fig.tight_layout();fig.savefig(out/'tracking_timeline.png',dpi=160);plt.close(fig)
choices=[0,len(data)//2,len(data)-1,int(np.argmin(abs(ts-at[np.argmax(av)])))]
lost=np.flatnonzero(np.isin(states,[3,4]))
if len(lost):choices.append(int(lost[0]))
else:choices.append(min(data[10:],key=lambda r:r['n_nonnull'])['index'])
choices=list(dict.fromkeys(choices))
fig,axes=plt.subplots(len(choices),1,figsize=(10,5*len(choices)))
for axis,i in zip(np.atleast_1d(axes),choices):
    axis.imshow(Image.open(seq/assoc[i][1]));xy=np.asarray(frames[i]);yes=xy[:,2]>0
    axis.scatter(xy[~yes,0],xy[~yes,1],s=3,c='gray',alpha=.5)
    axis.scatter(xy[yes,0],xy[yes,1],s=6,c='lime',alpha=.8)
    r=data[i];axis.set_title(f"frame {i}, t={t[i]:.3f}s, state={r['state']}, nonnull={r['n_nonnull']} (not a static/inlier label)");axis.axis('off')
fig.tight_layout();fig.savefig(out/'diagnostic_examples.jpg',dpi=110);plt.close(fig)
(out/'example_selection.json').write_text(json.dumps({'indices':choices,'rule':'first, middle, last, max offline ATE, first lost or minimum nonnull after input 10; no screenshot-only mechanism inference'},indent=2))
print(json.dumps(summary,indent=2))
