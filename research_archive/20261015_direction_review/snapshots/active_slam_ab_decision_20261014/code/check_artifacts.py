#!/usr/bin/env python3
"""Integrity/physics checks of the bounded audit, not performance-fitting tests."""
import ast,hashlib,json,subprocess
from pathlib import Path
import numpy as np
import map_probe as m
R=Path(__file__).resolve().parents[1];checks={}
a=json.loads((R/'data/A_run01/results.json').read_text());b=json.loads((R/'data/B_core_run01/results.json').read_text())
checks['A_rows_150']=len(a)==150
checks['A_four_policies_plus_passive']=set(x['policy'] for x in a)==set(m.CFG['policies'])
checks['A_all_have_two_views']=all(x['candidate_count']>=2 for x in a)
checks['A_safety_offline']=all(x['safe_truth_offline'] for x in a)
checks['B_six_core_calls']=len(b)==6 and all(x['status']=='CORE_EXECUTED' for x in b)
checks['B_no_graph_mapping_claim']=all(x['graph_edge_admission']=='NOT_MEASURED' and x['map_update']=='NOT_MEASURED' for x in b)
tree=ast.parse((R/'code/map_probe.py').read_text())
functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
checks['policy_no_truth_variable']=all(not any(isinstance(n,ast.Name) and n.id in ['truth','true','world'] for n in ast.walk(functions[f])) for f in ['bank','candidates','choose','decision'])
old,_=m.world('asymmetric',False);s=np.array(m.CFG['start']);z=m.scan(old,s);new,mask=m.integrate(old,s,z)
sanity={'noiseless_same_pose_changed_cells':int(np.count_nonzero(new!=old)),
        'note':'Diagnostic of discretization; not repaired or tuned after results.'}
# Gauge counterexample: translate entire environment and all poses together.
shift=np.array([.6,.4,0.]);views=[s,s+np.array([.8,0,0]),s+np.array([0,.8,np.pi/2])]
base=np.array([m.scan(old,v) for v in views])
# An exact translated field queries the old field at position p-shift.
recovered=[np.r_[np.round(((v+shift)-shift)[:2],12),v[2]] for v in views]
translated=np.array([m.scan(old,p) for p in recovered])
sanity['gauge_coordinate_arithmetic']='round inverse-translated XY at 1e-12 m to avoid voxel boundary floating-point artifacts; yaw unchanged'
sanity['gauge_max_range_difference']=float(abs(base-translated).max())
checks['gauge_observation_invariant']=bool(np.allclose(base,translated,atol=1e-12))
before=json.loads((R/'audit/workspace_before.json').read_text());protected={}
for d,states in before.items():
    if d=='paused_probe':continue
    after={cmd:subprocess.check_output(['git','-C',d]+cmd.split(),text=True) for cmd in states}
    protected[d]=after==states
p=Path('/home/wcqw/active_slam_feedback_probe_20261014');now={str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest() for f in p.rglob('*') if f.is_file()}
protected['paused_probe_all_files']=before['paused_probe']==now
checks['old_workspaces_preserved']=all(protected.values())
(R/'audit/protection_after.json').write_text(json.dumps(protected,indent=2))
(R/'audit/checks.json').write_text(json.dumps(checks,indent=2));(R/'data/model_sanity.json').write_text(json.dumps(sanity,indent=2))
print(json.dumps({'checks':checks,'sanity':sanity},indent=2));assert all(checks.values())
