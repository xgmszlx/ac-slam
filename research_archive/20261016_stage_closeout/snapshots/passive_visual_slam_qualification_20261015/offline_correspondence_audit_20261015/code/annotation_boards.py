import pathlib,json
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
N=pathlib.Path(__file__).resolve().parents[1];D=N.parent/'data/rgbd_dataset_freiburg3_walking_xyz';p=json.loads((N/'protocol/design_v02.json').read_text())
for name in ['before','critical','after']:
 fig,axes=plt.subplots(3,2,figsize=(13,13))
 for row,pair in zip(axes,[x for x in p['pairs'] if x['window']==name]):
  for ax,f in zip(row,pair['frames']):
   ax.imshow(Image.open(D/f['rgb']));ax.set(xticks=list(range(0,641,80)),yticks=list(range(0,481,80)),title=f"{pair['id']} / index {f['index']} / t={f['relative_s']:.3f}s");ax.grid(alpha=.25)
 fig.suptitle('OFFLINE MANUAL ANNOTATION: original RGB only; before any correspondence outcomes');fig.tight_layout(rect=[0,0,1,.97]);fig.savefig(N/'figures'/('annotation_raw_'+name+'.jpg'),dpi=120);plt.close(fig)
