"""Offline only: compare actual and estimated motion on every evaluated 1s pair."""
from pathlib import Path
import sys,json,csv
import numpy as np
from scipy.spatial.transform import Rotation
from evaluate import read_rows,transforms,associate,stats
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

p=Path(__file__).resolve().parents[1];name=sys.argv[1];seq=p/'data'/('rgbd_dataset_freiburg3_'+name);run=p/'results'/name/'headless01'
et,ep=transforms(read_rows(run/'CameraTrajectory.txt'));gt,gp=transforms(read_rows(seq/'groundtruth.txt'))
match=dict(associate(et,gt));a=[]
for row in csv.DictReader((run/'evaluation/rpe.csv').open()):
    i=int(np.argmin(abs(et-float(row['stamp_start']))));j=int(np.argmin(abs(et-float(row['stamp_end']))))
    g,h=match[i],match[j];truth=np.linalg.inv(gp[g])@gp[h];pred=np.linalg.inv(ep[i])@ep[j]
    a.append({'start':float(et[i]),'end':float(et[j]),'gt_translation_m':float(np.linalg.norm(truth[:3,3])),
              'estimated_translation_m':float(np.linalg.norm(pred[:3,3])),
              'gt_rotation_deg':float(Rotation.from_matrix(truth[:3,:3]).magnitude()*180/np.pi),
              'estimated_rotation_deg':float(Rotation.from_matrix(pred[:3,:3]).magnitude()*180/np.pi),
              'translation_rpe_m':float(row['translation_m']),'rotation_rpe_deg':float(row['rotation_deg'])})
with (run/'evaluation/motion_pairs.csv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=list(a[0]));w.writeheader();w.writerows(a)
x={'all_pairs':len(a),'maximum_RPE_pair':max(a,key=lambda r:r['translation_rpe_m']),
   'gt_1s_translation':stats([r['gt_translation_m'] for r in a]),
   'estimated_1s_translation':stats([r['estimated_translation_m'] for r in a]),
   'causal_dynamic_attribution':'UNRESOLVED; motion comparison does not label erroneous correspondences'}
(run/'evaluation/motion_review.json').write_text(json.dumps(x,indent=2))
fig,axes=plt.subplots(2,1,figsize=(11,6),sharex=True);t=np.array([r['start'] for r in a])-et[0]
for ax,kind,unit in [(axes[0],'translation','m'),(axes[1],'rotation','deg')]:
    for source in ['gt','estimated']:ax.plot(t,[r[f'{source}_{kind}_{unit}'] for r in a],label=source)
    ax.set_ylabel('1s '+kind+' ('+unit+')');ax.legend()
axes[1].set_xlabel('relative input time (s)');fig.suptitle(name+' / every evaluated 1s pair; GT offline only');fig.tight_layout();fig.savefig(run/'evaluation/motion_comparison.png',dpi=160);plt.close(fig)
print(json.dumps(x,indent=2))
