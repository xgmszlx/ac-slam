import sys
sys.dont_write_bytecode=True
import pathlib,csv,json,collections,hashlib
import numpy as np
from scipy.spatial.transform import Rotation
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from evaluate import read_rows,transforms,associate,stats
N=pathlib.Path(__file__).resolve().parents[1];O=N.parent;B=O/'diagnostic_comparison_20261015';D=O/'data/rgbd_dataset_freiburg3_walking_xyz';a=read_rows(D/'associations.txt');stamps=np.array([float(r[0]) for r in a]);t0=stamps[0];gt,gp=transforms(read_rows(D/'groundtruth.txt'))
protocol=json.loads((N/'protocol/design.json').read_text());inds=set(range(0,len(a),83));inds.add(len(a)-1)
for t in protocol['quality_sample_seconds']:inds.add(int(np.argmin(abs(stamps-t0-t))))
(N/'protocol/quality_samples_walking.json').write_text(json.dumps([{'index':i,'stamp':a[i][0],'relative_s':float(stamps[i]-t0),'RGB':a[i][1],'RGB_sha256':hashlib.sha256((D/a[i][1]).read_bytes()).hexdigest()} for i in sorted(inds)],indent=2))
feature=collections.defaultdict(list)
for r in csv.DictReader((N/'results/raw_ORB_features.csv').open()):feature[int(r['index'])].append([float(r['x']),float(r['y']),float(r['depth_m'])])
imstats=list(csv.DictReader((N/'results/window_image_metrics.csv').open()));ims={int(r['index']):r for r in imstats};motion=[]
for tag in ['P1_01','P1_02','P1_03']:
 for mode,file in [('exported','CameraTrajectory.txt'),('online','OnlineTrajectory.txt')]:
  et,ep=transforms(read_rows(B/'results/walking'/tag/file));pairs=dict(associate(et,gt))
  for i in range(len(et)):
   rel=et[i]-t0
   if not 18<=rel<=27 or i not in pairs:continue
   j=int(np.argmin(abs(et-et[i]-1)))
   if j<=i or abs(et[j]-et[i]-1)>=.02 or j not in pairs:continue
   truth=np.linalg.inv(gp[pairs[i]])@gp[pairs[j]];pred=np.linalg.inv(ep[i])@ep[j];delta=np.linalg.inv(truth)@pred
   motion.append({'run':tag,'mode':mode,'stamp_start':float(et[i]),'stamp_end':float(et[j]),'relative_start_s':float(rel),'relative_end_s':float(et[j]-t0),'GT_translation_m':float(np.linalg.norm(truth[:3,3])),'estimated_translation_m':float(np.linalg.norm(pred[:3,3])),'GT_rotation_deg':float(Rotation.from_matrix(truth[:3,:3]).magnitude()*180/np.pi),'estimated_rotation_deg':float(Rotation.from_matrix(pred[:3,:3]).magnitude()*180/np.pi),'RPE_translation_m':float(np.linalg.norm(delta[:3,3])),'RPE_rotation_deg':float(Rotation.from_matrix(delta[:3,:3]).magnitude()*180/np.pi)})
with (N/'results/local_motion.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=list(motion[0]));w.writeheader();w.writerows(motion)
windows=[]
for tag in ['P1_01','P1_02','P1_03']:
 for mode in ['exported','online']:
  for name,lo,hi in [('normal_before',18,21),('critical',22,24.5),('normal_after',25,27)]:
   selected=[r for r in motion if r['run']==tag and r['mode']==mode and lo<=r['relative_start_s'] and r['relative_end_s']<=hi]
   windows.append({'run':tag,'mode':mode,'window':name,'endpoints_both_within':[lo,hi],'pairs':len(selected),'RPEt_m':stats([r['RPE_translation_m'] for r in selected]),'RPEr_deg':stats([r['RPE_rotation_deg'] for r in selected]),'GT_translation_m':stats([r['GT_translation_m'] for r in selected]),'estimated_translation_m':stats([r['estimated_translation_m'] for r in selected]),'GT_rotation_deg':stats([r['GT_rotation_deg'] for r in selected]),'estimated_rotation_deg':stats([r['estimated_rotation_deg'] for r in selected])})
(N/'audit/window_motion_summary.json').write_text(json.dumps(windows,indent=2))
# Time-ordered RGB, depth and freshly extracted ORB are explicit separate evidence.
times=[19.,20.5,22.,22.5,23.,23.5,24.,24.5,25.5,26.5];indices=[int(np.argmin(abs(stamps-t0-t))) for t in times]
fig,axes=plt.subplots(len(indices),3,figsize=(13,2.7*len(indices)))
for ar,i in zip(axes,indices):
 im=np.array(Image.open(D/a[i][1]));depth=np.array(Image.open(D/a[i][3])).astype(float)/5000;xy=np.array(feature[i]);row=ims[i];rel=stamps[i]-t0
 ar[0].imshow(im);ar[0].set_title(f't={rel:.3f}s, frame {i} / original RGB',fontsize=10)
 z=np.ma.masked_where(depth<=0,depth);ar[1].set_facecolor('black');ar[1].imshow(z,cmap='viridis',vmin=0,vmax=6);ar[1].set_title(f'depth valid {float(row["depth_valid_fraction"]):.1%}; dt={float(row["RGB_depth_abs_dt_ms"]):.3f} ms',fontsize=10)
 ar[2].imshow(im);valid=xy[:,2]>0;ar[2].scatter(xy[~valid,0],xy[~valid,1],s=1,c='orange',alpha=.55);ar[2].scatter(xy[valid,0],xy[valid,1],s=1,c='lime',alpha=.7);ar[2].set_title(f'fresh ORB N={len(xy)}; green depth>0, orange invalid\nNOT tracked matches or optimizer inliers',fontsize=9)
 for ax in ar:ax.axis('off')
fig.suptitle('Time-ordered existing walking evidence; no detector/person mask available\nDepth uses fixed 0..6m display; black = invalid. GT is offline only.',fontsize=12);fig.tight_layout(rect=[0,0,1,.98]);fig.savefig(N/'figures/time_ordered_evidence.png',dpi=165);fig.savefig(N/'figures/time_ordered_evidence.pdf');plt.close(fig)
# Full resolution RGB contact sheet for qualitative visual review, no claimed segmentation.
fig,axes=plt.subplots(3,4,figsize=(16,9));
for ax in axes.flat:ax.axis('off')
for ax,i in zip(axes.flat,indices):ax.imshow(Image.open(D/a[i][1]));ax.set_title(f'{stamps[i]-t0:.3f}s / frame {i}')
fig.suptitle('Fixed normal and critical window RGB samples, ascending time');fig.tight_layout();fig.savefig(N/'figures/RGB_contact_sheet.png',dpi=170);plt.close(fig)
fig,ax=plt.subplots(6,1,figsize=(13,13),sharex=True)
colors=['#0077b6','#00b4d8','#023e8a']
for tag,c in zip(['P1_01','P1_02','P1_03'],colors):
 sel=[r for r in motion if r['run']==tag and r['mode']=='exported'];t=[r['relative_start_s'] for r in sel]
 ax[0].plot(t,[r['RPE_translation_m'] for r in sel],color=c,label=tag);ax[1].plot(t,[r['estimated_translation_m'] for r in sel],color=c,label=tag+' estimated')
 if tag=='P1_01':ax[1].plot(t,[r['GT_translation_m'] for r in sel],color='black',lw=2,label='GT actual 1s displacement');ax[2].plot(t,[r['GT_rotation_deg'] for r in sel],c='black',label='GT actual 1s rotation')
 ax[2].plot(t,[r['estimated_rotation_deg'] for r in sel],color=c,alpha=.7,label=tag+' estimated')
t=np.array([float(r['relative_s']) for r in imstats]);ax[3].plot(t,[float(r['depth_valid_fraction']) for r in imstats],label='image depth-valid fraction',c='#548c2f');ax[3].plot(t,[float(r['raw_ORB_depth_valid_fraction']) for r in imstats],label='fresh ORB depth-valid fraction',c='#a6b03d');ax[3].legend(loc='upper left')
ax[4].plot(t,[float(r['laplacian_variance']) for r in imstats],label='gray Laplacian variance (proxy, not measured blur)',c='#9d4edd');ax[4].legend(loc='upper left');ax[5].plot(t,[float(r['RGB_depth_abs_dt_ms']) for r in imstats],label='RGB-depth stamp difference (ms)',c='#f77f00');ax[5].legend(loc='upper left')
for axis in ax:axis.axvspan(22,24.5,color='red',alpha=.07);axis.set_xlim(18,27);axis.grid(alpha=.2)
for axis,label in zip(ax,['1s RPE (m)','1s displacement (m)','1s rotation (deg)','valid fraction','Laplacian variance','RGB-D dt (ms)']):axis.set_ylabel(label)
for axis in ax[:3]:axis.legend(ncol=2,fontsize=8)
ax[-1].set_xlabel('RGB timestamp relative to first associated image (s)');fig.suptitle('Same old P1 runs; error peak versus acquisition/feature evidence\nEach motion curve is anchored at its 1s interval start; shaded region is a fixed diagnostic window.');fig.tight_layout(rect=[0,0,1,.96]);fig.savefig(N/'figures/window_timeline.png',dpi=175);fig.savefig(N/'figures/window_timeline.pdf');plt.close(fig)
(N/'audit/evidence_image_selection.json').write_text(json.dumps({'requested_relative_s':times,'nearest_indices':indices,'RGB_stamps':[a[i][0] for i in indices],'selection_pre_mask':True,'no_visual_person_GT_or_inlier_claim':True},indent=2))
print('window evidence figures and motion summaries written')
