#!/usr/bin/env python3
"""Six frozen laser pair controls. Ground truth is used for evaluation ONLY.
Core accepts/rejects are not SLAM graph-edge admission or mapping evidence.
"""
import argparse,csv,json,subprocess
from pathlib import Path
import numpy as np
import map_probe as sim
ROOT=Path(__file__).resolve().parents[1]
CASES=[('corner','asymmetric',False,[4.4,4.,0.]),
       ('structure_view','asymmetric',False,[4.,4.4,np.pi/2]),
       ('changed_front','asymmetric',True,[4.4,4.,0.]),
       ('changed_side','asymmetric',True,[4.,4.4,np.pi/2]),
       ('symmetric_front','symmetric',False,[4.4,4.,0.]),
       ('symmetric_side','symmetric',False,[4.,4.4,np.pi/2])]
CFG=dict(cases=CASES,beams=901,range=25.,noise=.03,seed=7,guess_error=[.2,.0,.02],
         actual_algorithm='installed RTAB-Map RegistrationIcp; default ICP parameters except PointToPlane=true',
         scope='pairwise registration, not full SLAM; no closed-loop policy')
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',default='B_core_run01');args=ap.parse_args()
    p=ROOT/'protocol/B_frozen.json'
    serial=json.loads(json.dumps(CFG))
    if p.exists():assert json.loads(p.read_text())==serial,'Frozen configuration differs'
    else:
        with p.open('x') as f:json.dump(CFG,f,indent=2)
    out=ROOT/'data'/args.out;out.mkdir(exist_ok=False);rng=np.random.default_rng(7);rows=[]
    sim.CFG['beams']=901;sim.CFG['range']=25.;sim.ANG=np.linspace(-np.pi/2,np.pi/2,901);sim.D=np.arange(.05,25.025,.05)
    for name,scene,changed,v in CASES:
        old,truth=sim.world(scene,changed);s=np.array([4.,4.,0.]);v=np.array(v)
        za=sim.scan(old,s)+rng.normal(0,.03,901);zb=sim.scan(truth,v)+rng.normal(0,.03,901)
        _,observed=sim.integrate(old,s,za)
        # Coverage prediction uses a PARTIAL prior only; unobserved cells assumed transparent.
        partial=old & observed;zp=sim.scan(partial,v);_,future=sim.integrate(partial,v,zp)
        gain=int(np.count_nonzero(future & ~observed))
        for label,z in [('a',za),('b',zb)]:
            xy=np.c_[z*np.cos(sim.ANG),z*np.sin(sim.ANG)];np.savetxt(out/(name+'_'+label+'.xy'),xy,fmt='%.8f')
        # Guess uses biased wheel-motion surrogate. Oracle transform never enters registration.
        # The known commanded displacement is available to the robot; truth evaluates the result.
        cmd=v-s;guess=cmd+np.array(CFG['guess_error'])
        result=out/(name+'.tsv');log=out/(name+'.log')
        with log.open('x') as f:
            ret=subprocess.run([str(ROOT/'code/registration_probe'),str(out/(name+'_a.xy')),str(out/(name+'_b.xy')),*map(str,guess),str(result)],stdout=f,stderr=subprocess.STDOUT)
        if ret.returncode:rows.append(dict(case=name,status='TECHNICAL_RUN_FAIL',returncode=ret.returncode));continue
        with result.open() as f:d=next(csv.DictReader(f,delimiter='\t'))
        accepted=d['accepted']=='1';est=np.array([float(d[k]) for k in ['x','y','yaw']]);error=est-cmd;error[2]=(error[2]+np.pi)%(2*np.pi)-np.pi
        rows.append(dict(case=name,status='CORE_EXECUTED',predicted_new_cells=gain,accepted=accepted,
                         translation_error_offline=float(np.linalg.norm(error[:2])) if accepted else None,
                         yaw_error_offline=float(abs(error[2])) if accepted else None,registration=d,
                         graph_edge_admission='NOT_MEASURED',map_update='NOT_MEASURED'))
    (out/'results.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows,indent=2))
