import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parents[1]
a=json.loads((R/'data/B_core_run01/results.json').read_text())
f,axs=plt.subplots(1,3,figsize=(13,4.8))
for ax,key,title in zip(axs,['predicted_new_cells','accepted','translation_error_offline'],['Geometric new-cell proxy','Core accepted (not graph edges)','Offline pair translation error [m]']):
    values=[float(x[key]) if x[key] is not None else np.nan for x in a]
    ax.bar(range(6),values);ax.set_xticks(range(6));ax.set_xticklabels([x['case'] for x in a],rotation=55,ha='right',fontsize=8);ax.set_title(title,fontsize=10)
    if key=='translation_error_offline':
        for i,x in enumerate(a):
            if not x['accepted']:ax.text(i,.015,'rejected',rotation=90,ha='center',fontsize=8)
f.tight_layout();f.savefig(R/'figures/B_core_probe.png',dpi=150)
