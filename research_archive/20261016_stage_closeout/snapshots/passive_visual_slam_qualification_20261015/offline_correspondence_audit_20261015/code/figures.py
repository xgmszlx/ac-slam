import pathlib,csv,json,collections
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
N=pathlib.Path(__file__).resolve().parents[1];D=N.parent/'data/rgbd_dataset_freiburg3_walking_xyz';P=json.loads((N/'protocol/design_v02.json').read_text());summary=list(csv.DictReader((N/'results/pair_summary.csv').open()));matches=list(csv.DictReader((N/'results/matches.csv').open()));native=list(csv.DictReader((N/'results/native_increment_context.csv').open()));labels=[r['pair'] for r in summary];x=np.arange(9)
fig,axes=plt.subplots(4,1,figsize=(13,12),sharex=True)
axes[0].bar(x,[int(r['mutual_ratio']) for r in summary],color='#dddddd',label='all mutual+ratio matches');axes[0].bar(x-.14,[int(r['BB_valid3D']) for r in summary],width=.25,color='#277da1',label='BB valid 3D');axes[0].bar(x+.14,[int(r['PP_valid3D']) for r in summary],width=.25,color='#9d4edd',label='PP valid 3D');axes[0].set_ylabel('correspondences');axes[0].legend(ncol=3)
for j,r in enumerate(summary):
 for group,offset,c in [('BB',-.12,'#277da1'),('PP',.12,'#9d4edd')]:
  v=r[group+'_inconsistent_fraction'];n=r[group+'_valid3D']
  if v:axes[1].scatter(j+offset,float(v)*100,c=c,marker='s' if group=='PP' else 'o',s=55);axes[1].annotate('n='+n,(j+offset,float(v)*100),xytext=(0,6),textcoords='offset points',ha='center',fontsize=7)
  else:axes[1].annotate('PP n=0',(j+.12,8),ha='center',fontsize=7,color=c)
axes[1].set(ylabel='static-geometry violations (%)',ylim=(-8,116));axes[1].text(.01,.97,'Blue: BB; purple: PP. PP n=0 is undefined, not 0% error.',transform=axes[1].transAxes,va='top',fontsize=9)
axes[2].plot(x,[int(r['BB_consistent']) for r in summary],'o-',color='#43aa8b',label='BB GT-consistent 3D matches');axes[2].plot(x,[float(r['source_B_depth_features']) for r in summary],'s--',color='#777777',label='source nonperson depth-positive ORB features');axes[2].set_ylabel('count (diagnostic only)');axes[2].legend(ncol=2)
for j,label in enumerate(labels):
 for k,tag in enumerate(['P1_01','P1_02','P1_03']):
  row=next(r for r in native if r['pair']==label and r['run']==tag and r['mode']=='exported');axes[3].scatter(j+(k-1)*.09,float(row['increment_error_m']),c=['#0077b6','#00b4d8','#03045e'][k],s=40,label=tag if j==0 else None)
axes[3].set_ylabel('old native increment error (m)');axes[3].legend(ncol=3);axes[3].set_xticks(x);axes[3].set_xticklabels(labels,rotation=25,ha='right')
for ax in axes:ax.axvspan(2.5,5.5,color='red',alpha=.055);ax.axvline(2.5,color='gray',ls=':');ax.axvline(5.5,color='gray',ls=':');ax.grid(axis='y',alpha=.2)
fig.suptitle('OFFLINE_DIAGNOSTIC: all 9 frozen endpoint pairs, no RANSAC prefilter\nPP = conservative person core; BB = nonperson candidate; both-depth required for geometry.\nBottom: supplemental ~0.25s increments from old P1 trajectories, not replacements for frozen 1s RPE.',fontsize=11);fig.tight_layout(rect=[0,0,1,.94]);fig.savefig(N/'figures/frozen_pair_comparison.png',dpi=180);fig.savefig(N/'figures/frozen_pair_comparison.pdf');plt.close(fig)
for window in ['before','critical','after']:
 fig,axes=plt.subplots(3,2,figsize=(13,10))
 for ar,pair in zip(axes,[p for p in P['pairs'] if p['window']==window]):
  f1,f2=pair['frames'];sel=[r for r in matches if r['pair']==pair['id'] and r['mutual_ratio']=='1' and r['valid_3D']=='1' and r['group'] in ['PP','BB']]
  for ax,f in zip(ar,[f1,f2]):ax.imshow(Image.open(D/f['rgb']));ax.set(xlim=(0,640),ylim=(480,0));ax.axis('off')
  for r in sel:
   good=r['consistent_primary']=='1';color=('#9d4edd' if good else '#e639c4') if r['group']=='PP' else ('#39b54a' if good else '#f94144');ar[0].scatter(float(r['x1']),float(r['y1']),s=9,c=color,alpha=.75);ar[1].scatter(float(r['x2']),float(r['y2']),s=7,c=color,alpha=.7)
   if not good:ar[1].annotate('',xy=(float(r['x2']),float(r['y2'])),xytext=(float(r['predicted_x2']),float(r['predicted_y2'])),arrowprops=dict(arrowstyle='->',color=color,lw=.6),annotation_clip=True)
  ar[0].set_title(f"{pair['id']} source {f1['relative_s']:.3f}s / positive-depth mutual-ratio BB/PP",fontsize=9);ar[1].set_title(f"target {f2['relative_s']:.3f}s / arrows: GT static prediction to matched pixel",fontsize=9)
 fig.suptitle('OFFLINE_DIAGNOSTIC; not SLAM inliers\nBB consistent green, inconsistent red; PP consistent purple, inconsistent magenta; uncertain labels omitted.',fontsize=10);fig.tight_layout(rect=[0,0,1,.93]);fig.savefig(N/'figures'/('correspondence_geometry_'+window+'.png'),dpi=160);plt.close(fig)
# Descriptive distributions only; no confidence intervals from dependent matches.
fig,axes=plt.subplots(1,2,figsize=(11,4.5));colors={'before':'#666666','critical':'#d62828','after':'#0077b6'}
for ax,group in zip(axes,['PP','BB']):
 for window in ['before','critical','after']:
  a=sorted(float(r['reprojection_px']) for r in matches if r['window']==window and r['group']==group and r['mutual_ratio']=='1' and r['valid_3D']=='1')
  if a:ax.step(a,np.arange(1,len(a)+1)/len(a),where='post',label=window+' n='+str(len(a)),c=colors[window])
  else:ax.plot([],[],label=window+' n=0 (undefined)',c=colors[window])
 ax.axvline(5,c='gray',ls='--',lw=1);ax.set(xlabel='GT reprojection error (px)',ylabel='empirical cumulative fraction',xlim=(0,80),ylim=(0,1.02),title=group+' endpoint correspondences');ax.legend(fontsize=8);ax.grid(alpha=.2)
fig.suptitle('OFFLINE_DIAGNOSTIC: pooled descriptive CDF; matches are not independent trials');fig.tight_layout();fig.savefig(N/'figures/reprojection_distributions.png',dpi=180);plt.close(fig)
print('figures written')
