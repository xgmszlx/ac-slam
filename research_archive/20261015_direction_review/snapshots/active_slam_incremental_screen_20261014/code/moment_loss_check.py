"""Algebraic audit of mean/variance compression. No planner or SLAM experiment."""
from pathlib import Path
import json,math
R=Path(__file__).resolve().parents[1]
# Two finite ensembles of predicted unknown occupancy along a single three-cell ray.
A=[[0,0,0],[1,1,1],[0,0,0]]
B=[[0,0,1],[0,1,0],[1,0,0]]
def moments(m):
 mean=[sum(r[i] for r in m)/len(m) for i in range(3)]
 var=[sum((r[i]-mean[i])**2 for r in m)/len(m) for i in range(3)]
 return mean,var
def stop(mean):
 acc=0
 for i,v in enumerate(mean,1):
  acc+=v
  if acc>=.8:return i
 return 3
def observations(m):
 ret=[]
 for row in m:
  # Distinguish hit cell from max-range no-hit. No sensor likelihood is fitted here.
  hit=next((i+1 for i,v in enumerate(row) if v),None)
  ret.append({'first_hit':hit,'visible_cells':hit if hit else 3})
 return ret
ma,va=moments(A);mb,vb=moments(B)
assert ma==mb and va==vb
ra,rb=observations(A),observations(B)
out={'classification':'ALGEBRAIC_SOURCE_AUDIT_ONLY','ensembles':{'A':A,'B':B},'same_mean':ma,'same_variance':va,'paper_intended_1D_threshold':.8,'paper_intended_stop_equal':stop(ma)==stop(mb),'paper_intended_stop':stop(ma),'paper_intended_1D_variance_sum_equal':sum(va[:stop(ma)])==sum(vb[:stop(mb)]),'first_hit_A':ra,'first_hit_B':rb,'expected_visible_cells_A':sum(x['visible_cells'] for x in ra)/3,'expected_visible_cells_B':sum(x['visible_cells'] for x in rb)/3,'limitations':['Finite controlled input, not trained LaMa outputs','Paper intended 1D cumulative stopping rule, not the released implementation or full flood-fill','Not calibrated map posterior','No robot action executed','No scientific task benefit demonstrated']}
assert out['expected_visible_cells_A']!=out['expected_visible_cells_B']
(R/'audit/moment_loss.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
