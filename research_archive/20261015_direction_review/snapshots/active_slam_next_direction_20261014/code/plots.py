from pathlib import Path
import json,csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parents[1]
z=np.load(R/'results/A_residual/B1_attribution.npz');image=np.ones((*z['truth'].shape,3));image[z['truth']]=[.2,.2,.2];image[z['missed']&~z['visible']]=[.4,.65,.9];image[z['missed']&z['visible']]=[1,.65,.15];image[z['false']]=[.9,.05,.5]
fig,axes=plt.subplots(1,2,figsize=(11,4.5));axes[0].imshow(image,origin='lower');axes[0].set_title('S3 / B1: 92 false writes, 738 missed changes');axes[0].set_xlabel('Magenta: false; orange: seen missed; blue: unseen missed')
axes[1].bar(['False writes','Unseen missed','Seen missed'],[92,524,214],color=['#e60d80','#66a6e5','#ffa626']);axes[1].set_ylabel('Exact original binary cells');axes[1].set_title('830 final errors; no tolerance replacement');fig.tight_layout();fig.savefig(R/'figures/A_residual.png',dpi=160);plt.close(fig)
run=R/'results/B_technical_02';e=json.loads((run/'evaluation.json').read_text());rows=list(csv.DictReader((run/'trajectory.csv').open()));maps=list(csv.DictReader((run/'map_metrics.csv').open()))
fig,ax=plt.subplots(3,1,figsize=(10,8),sharex=True)
ax[0].plot([float(x['stamp']) for x in rows],[float(x['translation_error']) for x in rows],'.-',ms=3,label='Offline GT error on strict pairs');ax[0].set_ylabel('Translation error (m)');ax[0].legend()
ax[1].plot([float(x['stamp']) for x in rows],[float(x['icp_ratio']) for x in rows],'.',label='OdomInfo inlier ratio');d=json.loads((run/'offline_diagnostics.json').read_text());ax[1].scatter(d['missing_odominfo_scan_stamps_s'],[0]*len(d['missing_odominfo_scan_stamps_s']),marker='x',s=20,label='No OdomInfo (not a rejection label)');ax[1].legend();ax[1].set_ylabel('Ratio / missing')
ax[2].plot([int(x['stamp_ns'])/1e9 for x in maps],[int(x['observed_binary_errors']) for x in maps],'o-',label='Observed+known exact map error');ax[2].set_ylabel('Cells');ax[2].set_xlabel('Original simulation stamp (s)');ax[2].legend();fig.suptitle('Technical attempt 2: 199/283 strict pairs; NOT qualified');fig.tight_layout();fig.savefig(R/'figures/B_signal_partial.png',dpi=160);plt.close(fig)
z=np.load(run/'map_evaluation.npz');img=np.ones((*z['truth'].shape,3));img[z['truth']]=[.2,.2,.2];known=z['estimate']>=0;vis=z['visible'];fp=known&vis&(z['estimate']>=50)&~z['truth'];fn=known&vis&(z['estimate']<50)&z['truth'];img[fp]=[.9,.05,.5];img[fn]=[1,.6,.1];img[vis&~known]=[.5,.8,1]
plt.figure(figsize=(7,6));plt.imshow(img,origin='lower');plt.title('B attempt 2: exact binary map comparison\n539 false occupied + 65 false free; 671 unknown visible');plt.xlabel('Thick bitmap vs endpoint occupancy; no method claim');plt.tight_layout();plt.savefig(R/'figures/B_map_metric.png',dpi=150);plt.close()
