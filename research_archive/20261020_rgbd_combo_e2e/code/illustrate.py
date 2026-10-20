from pathlib import Path
import json,csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image
P=Path(__file__).resolve().parents[1];data=json.loads((P/'audit/dataset.json').read_text());D=Path(data['path']);pairs=json.loads((P/'protocol/inspection_pairs.json').read_text())['pairs'];traces={c:list(csv.DictReader((P/'results'/c/'frame_states.csv').open())) for c in ['S0','S1','S2']}
fig,ax=plt.subplots(2,3,figsize=(15,8))
for j,p in enumerate(pairs):
 f=p['frames'][0];i=f['index'];ax[0,j].imshow(Image.open(D/f['rgb']));ax[0,j].axis('off');ax[0,j].set_title(f"Fixed sample {p['id']}, t={f['relative_s']:.3f}s")
 s1=traces['S1'][i];s2=traces['S2'][i]
 labels=['S1 bad2D','S1 3D reject','S2 bad2D','S2 3D reject','S2 depth off','S2 mono edges','S2 mono inliers']
 vals=[float(s1['bad_2d_rejected']),float(s1['motion_rejected']),float(s2['bad_2d_rejected']),float(s2['motion_rejected']),float(s2['depth_invalidated']),float(s2['fallback_pose_edges_2d_last']),float(s2['fallback_pose_inlier2d_last'])]
 ax[1,j].barh(labels[::-1],vals[::-1],color=['#467cab']*2+['#ba7e42']*5);ax[1,j].set(xlabel='full-frame observation events',title='Native trace at same input stamp')
fig.suptitle('Real Bonn frames + actual per-frame actions; no pixel motion labels or causal attribution\nS2 edge/inlier counts are tagged fallbacks in last PoseOptimization call')
fig.tight_layout();fig.savefig(P/'figures/real_observation_handling.png',dpi=150);plt.close(fig)
