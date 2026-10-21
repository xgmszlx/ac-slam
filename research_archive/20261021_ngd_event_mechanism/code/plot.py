from pathlib import Path
import csv,json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
D=Path(__file__).resolve().parents[1]
frames=list(csv.DictReader((D/'results/paired_frame_evidence.csv').open()))
windows=list(csv.DictReader((D/'results/common_RPE_windows.csv').open()))
events=[9.0814898,9.78452,10.01955]
fig,ax=plt.subplots(4,2,figsize=(13,11),sharex=True)
for col,typ in enumerate(['online','exported']):
    f=[x for x in frames if x['type']==typ];w=[x for x in windows if x['type']==typ]
    t=np.array([float(x['time_s']) for x in f]);rt=np.array([float(x['start_s']) for x in w])
    for mode,color in [('M0','tab:blue'),('M2','tab:orange')]:
        ax[0,col].plot(t,[float(x[mode+'_ATE_m']) if x[mode+'_ATE_m'] else np.nan for x in f],label=mode,color=color)
        ax[1,col].plot(rt,[float(x[mode+'_RPEt_m']) for x in w],color=color)
        ax[2,col].plot(rt,[float(x[mode+'_RPEr_deg']) for x in w],color=color)
    ax[0,col].set(title=typ+': ATE and local motion disagree',ylabel='ATE (m)');ax[0,col].legend()
    ax[1,col].set(ylabel='1s RPE translation (m)');ax[2,col].set(ylabel='1s RPE rotation (deg)')
    ax[3,col].plot(t,[float(x['M0_reference_mask_fraction']) for x in f],color='black',label='fixed M0 native area')
    ax[3,col].plot(t,[int(x['M2_extra_pixels'])/(640*480) for x in f],color='purple',label='M2 added area');ax[3,col].set(ylabel='image area fraction',xlabel='input relative time (s)');ax[3,col].legend(fontsize=8)
    for axis in ax[:,col]:
        for e in events:axis.axvline(e,color='red',lw=.6,alpha=.6)
        axis.axvline(16.52,color='green',lw=.8,ls='--')
fig.suptitle('Corrected frame; red=acceptance, green=native loop/correction neighborhood; RPE x=window START\nOverlapping 1s windows are dependent; lines do not establish causality',fontsize=11);fig.tight_layout();fig.savefig(D/'figures/corrected_full_timeline.png',dpi=150);plt.close(fig)
f=[x for x in frames if x['type']=='online'];t=np.array([float(x['time_s']) for x in f]);fig,ax=plt.subplots(3,1,figsize=(12,8),sharex=True)
ax[0].plot(t,[float(x['online_pose_separation_m']) for x in f]);ax[0].set(ylabel='M0/M2 pose separation (m)',title='State divergence precedes mask intervention; final loop history also differs')
for mode in ['M0','M2']:
    ax[1].plot(t,[int(x[mode+'_pnp_inliers']) for x in f],label=mode+' native PnP inlier sum',alpha=.8)
    ax[2].plot(t,[int(x[mode+'_poseopt_edges_sum']) for x in f],label=mode+' PoseOptimization edge sum',alpha=.8)
ax[1].set(ylabel='native PnP inliers');ax[2].set(ylabel='optimizer constructed edges',xlabel='input relative time (s)')
for axis in ax:
    for e in events:axis.axvline(e,color='red',lw=.7)
    axis.axvline(16.52,color='green',ls='--');axis.legend(fontsize=8) if axis!=ax[0] else None
fig.tight_layout();fig.savefig(D/'figures/history_and_constraints.png',dpi=150);plt.close(fig)
