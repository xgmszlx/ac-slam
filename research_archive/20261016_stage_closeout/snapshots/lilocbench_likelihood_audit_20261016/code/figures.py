from common import *
import csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
native=Native();scans=json.loads((P/'data/scans.json').read_text());cc={r['id']:r for r in json.loads((P/'data/candidate_manifest.json').read_text())};su=json.loads((P/'results/summary.json').read_text());sm={(r['id'],r['model']):r for r in su['profiles']}
# Figure 1: all fixed scans, uniform GT-local grid, no score-picked scan exclusion.
fig,axes=plt.subplots(2,6,figsize=(18,6.6),sharex=True,sharey=True)
for a,r in zip(axes.flat,scans):
 z=np.load(P/'data'/f"{r['id']}_candidates.npz");s=np.load(P/'results'/f"{r['id']}_profiles.npz");gi=z['grid_member_indices'][list(z['names']).index('GT')]
 for model,key,col in [('add','add_log','#0072b2'),('product','product_log','#d55e00')]:
  g=s[key][gi].reshape(25,25,21);line=np.max(g,axis=(1,2));a.plot(np.arange(-12,13)*.05,np.exp(line-line.max()),color=col,label=model)
 a.axvline(0,color='k',lw=.7,ls=':');a.set_title(f"{r['sequence']}\ntarget {r['target_s']}s / {sm[(r['id'],'add')]['valid_beams']} valid beams",fontsize=9)
 dn=sm[(r['id'],'product')]['far_minus_near_log'];a.text(.03,.08,'far-near log product:\n'+(f'{dn:+.1f}' if dn is not None else 'unavailable'),transform=a.transAxes,fontsize=8);a.grid(alpha=.2);a.set_ylim(0,1.05)
for a in axes[-1]:a.set_xlabel('dx from GT (m)')
for a in axes[:,0]:a.set_ylabel('Locally normalized profile\nmax over dy and yaw')
axes[0,0].legend(fontsize=8);fig.suptitle('Product scores are concentrated in BOTH sequences; concentration alone is not a failure diagnosis',fontsize=12)
fig.tight_layout(rect=[0,0,1,.95]);fig.savefig(P/'figures/01_profiles.png',dpi=150);plt.close(fig)
# Figure 2: explicitly post-hoc display of named conflict examples; full numerical table is retained.
chosen=['static_0_t05','lt_changes_0_t05','lt_changes_0_t07'];fig,ax=plt.subplots(1,3,figsize=(16,6))
colors={'GT':'black','A0':'#0072b2','A1':'#d55e00','A2':'#009e73'}
image=np.full(native.state.shape,.6);image[native.state==-1]=1.;image[native.state==1]=0.
ext=[-25,-25+native.nx*native.scale,-25,-25+native.ny*native.scale]
for a,ident in zip(ax,chosen):
 r=next(x for x in scans if x['id']==ident);a.imshow(image,origin='lower',extent=ext,cmap='gray',vmin=0,vmax=1,alpha=.7)
 for name,c in cc[ident]['centers'].items():
  if c is None:continue
  _,_,_,xx,yy=native.pz(r,[c]);a.scatter(xx[0],yy[0],s=7,color=colors[name],alpha=.65,label=name+' endpoints')
  a.plot(c[0],c[1],marker='x',ms=7,color=colors[name]);a.quiver(c[0],c[1],np.cos(c[2]),np.sin(c[2]),color=colors[name],angles='xy',scale_units='xy',scale=1.5,width=.006)
 a.set_title(ident+'\nInterpolated estimates, no particle identities');a.set_xlim(-14,17);a.set_ylim(-13,6);a.set_aspect('equal');a.set_xlabel('map x (m)');a.set_ylabel('map y (m)');a.legend(fontsize=7,loc='upper left')
fig.suptitle('Post-hoc illustrations: a plausible map fit at a wrong pose is not proof of a polluted PF constraint',fontsize=12);fig.tight_layout(rect=[0,0,1,.94]);fig.savefig(P/'figures/02_map_scan_overlays.png',dpi=150);plt.close(fig)
# Figure 3: all noninitial fixed scans, fixed angular sectors; no change-region labels are inferred.
sector=list(csv.DictReader((P/'results/sector_contributions.csv').open()));fig,ax=plt.subplots(2,2,figsize=(13,8))
for j,(key,label) in enumerate([('add_raw_score_delta_to_GT','Add score difference: A1 - GT'),('product_log_score_delta_to_GT','Product log-score difference: A1 - GT')]):
 mats=[]
 for seq in ['static_0','lt_changes_0']:
  arr=np.zeros((5,5))
  for i,t in enumerate([1,2,5,7,10]):
   for k in range(5):arr[i,k]=float(next(r[key] for r in sector if r['sequence']==seq and r['candidate']=='A1' and int(r['target_s'])==t and int(r['sector'])==k))
  mats.append(arr)
 vmax=max(np.abs(m).max() for m in mats)
 for i,(seq,arr) in enumerate(zip(['static_0','lt_changes_0'],mats)):
  a=ax[i,j];im=a.imshow(arr,cmap='coolwarm',norm=TwoSlopeNorm(vmin=-vmax,vcenter=0,vmax=vmax),aspect='auto')
  for row in range(5):
   for col in range(5):a.text(col,row,f'{arr[row,col]:+.1f}',ha='center',va='center',fontsize=9,color='black')
  a.set_xticks(range(5),['-135:-81','-81:-27','-27:27','27:81','81:135']);a.set_yticks(range(5),[1,2,5,7,10]);a.set_xlabel('Laser-frame angular sector (deg)');a.set_ylabel('Target scan time (s)');a.set_title(seq+'\n'+label);fig.colorbar(im,ax=a,shrink=.8)
fig.suptitle('Different angular sectors reverse candidate rankings; sectors are NOT ground-truth map-change labels',fontsize=12);fig.tight_layout(rect=[0,0,1,.95]);fig.savefig(P/'figures/03_sector_contributions.png',dpi=150);plt.close(fig)
print('Exactly three evidence figures saved')
