import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parents[1];out=R/'figures';out.mkdir(exist_ok=True)
names=['scientific_01_S0','scientific_02_S1','scientific_03_S2','scientific_04_S3']
fig,axes=plt.subplots(2,2,figsize=(11,7))
for name,ax in zip(names,axes.ravel()):
    d=np.genfromtxt(R/'results'/name/'audit_metrics.csv',delimiter=',',names=True,dtype=None,encoding=None)
    ax.plot(d['stamp'],d['ratio'],'.-',label='anomalous beam fraction');ax.axhline(.58,color='red',linestyle='--',label='checked-in threshold 0.58');ax.set_ylim(0,1);ax.set_title(name[-2:]);ax.set_xlabel('simulation time [s]')
    twin=ax.twinx();t=np.genfromtxt(R/'results'/name/'trajectory.csv',delimiter=',',names=True);twin.plot(t['stamp'],t['translation_error'],color='gray',alpha=.5,label='offline pose error');twin.set_ylim(0,1.7);twin.set_ylabel('offline translation error [m]')
axes.ravel()[0].legend(loc='upper left',fontsize=8);fig.tight_layout();fig.savefig(out/'four_conditions.png',dpi=150);plt.close(fig)
labels=['S1 B0','S1 B1','S1 B2 shadow','S3 B0','S3 B1','S3 B2 shadow']
sources=['scientific_02_S1','scientific_05_B1_S1','B2_shadow_scientific_02_S1','scientific_04_S3','scientific_06_B1_S3','B2_shadow_scientific_04_S3'];values=[]
for name in sources:
    if name.startswith('B2'):values.append(json.loads((R/'results'/name/'result.json').read_text())['false_update_cells'])
    else:values.append(json.loads((R/'results'/name/'evaluation.json').read_text())['map_final']['false_update_cells'])
fig,ax=plt.subplots(figsize=(9,4));ax.bar(labels,values);ax.set_ylabel('False map modifications [cells]');ax.set_title('Same recorded observations; B1 ROS replay, B2 commit shadow');fig.tight_layout();fig.savefig(out/'passive_comparison.png',dpi=150);plt.close(fig)
a=np.load(R/'results/scientific_04_S3/evaluation_maps.npz');b=np.load(R/'results/scientific_06_B1_S3/evaluation_maps.npz')
fig,axes=plt.subplots(1,3,figsize=(12,4))
for ax,m,title in zip(axes,[a['truth'],a['final'],b['final']],['S3 hidden truth (evaluation only)','B0 author output','B1 passive output']):
    ax.imshow(m,origin='lower',extent=[-5.25,5.25,-4.275,4.275],cmap='gray_r');ax.set_title(title);ax.set_xlabel('x [m]')
fig.tight_layout();fig.savefig(out/'S3_maps.png',dpi=150);plt.close(fig)
