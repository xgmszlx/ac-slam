import pathlib,csv,collections,numpy as np
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=pathlib.Path(__file__).resolve().parents[1];d=p.parent/'data/rgbd_dataset_freiburg3_walking_xyz';a=[l.split() for l in (d/'associations.txt').read_text().splitlines()];features=collections.defaultdict(list)
for r in csv.DictReader((p/'results/raw_ORB_features.csv').open()):
 i=int(r['index'])
 if i in [657,671,759]:features[i].append([float(r['x']),float(r['y']),float(r['depth_m'])])
fig,axes=plt.subplots(1,3,figsize=(15,4.7))
for ax,i in zip(axes,[657,671,759]):
 im=Image.open(d/a[i][1]);xy=np.array(features[i]);ax.imshow(im);good=xy[:,2]>0;ax.scatter(xy[good,0],xy[good,1],s=3,facecolors='none',edgecolors='lime',linewidth=.4);ax.scatter(xy[~good,0],xy[~good,1],s=2,c='orange',alpha=.65);ax.set_title(f'frame {i}, t={float(a[i][0])-float(a[0][0]):.3f}s\nraw features only; green depth>0',fontsize=10);ax.axis('off')
fig.suptitle('Native ORB extraction is NOT a P1 inlier or MapPoint trace; original images unchanged',fontsize=11,y=.98);fig.tight_layout(rect=[0,0,1,.92]);fig.savefig(p/'figures/critical_feature_map.png',dpi=200);plt.close(fig)
