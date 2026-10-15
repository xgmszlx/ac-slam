#!/usr/bin/env python3
"""Read-only re-evaluation of saved observations. No new simulation episode or tuning."""
import argparse,csv,json,types
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--out',default='toy_diagnosis02');args=ap.parse_args()
OLD=Path('/home/wcqw/active_slam_ab_decision_20261014')
m=types.ModuleType('old_toy');m.__file__=str(OLD/'code/map_probe.py')
exec(compile(Path(m.__file__).read_text(),m.__file__,'exec'),m.__dict__)
records=json.loads((OLD/'data/A_run01/results.json').read_text())
decisions={(x['case'],x['policy']):x for x in json.loads((OLD/'data/A_run01/decisions.json').read_text())}
rows=[];checks=[]
for p in sorted((OLD/'data/A_run01/raw').glob('*.npz')):
    data=np.load(p);old=data['old'];truth=data['truth'];off=data['offset'];z0=data['z0'];views=data['views']
    hs,w,lw=m.bank(old,z0)
    checks.append(dict(case=p.stem,prior_max_difference=float(abs(w-data['prior']).max())))
    changed=np.array([h['changed'] for h in hs]);offsets=np.array([h['off'] for h in hs])
    correct_pose=np.linalg.norm(offsets-off,axis=1)<1e-6
    same_pose=np.linalg.norm(offsets[:,None,:]-offsets[None,:,:],axis=2)<1e-8
    maps_different=changed[:,None]!=changed[None,:]
    wrong_pose_pair=~(correct_pose[:,None]&correct_pose[None,:])
    for pol in ['nearest','uncertainty','stable','discriminative']:
        row=next(x for x in records if x['case']==p.stem and x['policy']==pol)
        v=np.array(row['view']);z=data[pol+'_scan'];post=np.array(decisions[(p.stem,pol)]['weights'])
        predicted=np.array([m.scan(h['map'],m.pose_shift(v,h['off'])) for h in hs])
        sep=np.minimum((predicted[:,None,:]-predicted[None,:,:])**2/.3**2,1).mean(2)
        terms=w[:,None]*w[None,:]*sep;total=float(terms.sum())
        calc=m.normalize(lw+m.likelihood(z,predicted));k=int(post.argmax());h=hs[k]
        invmask=h['mask'];masked_errors=int(np.count_nonzero((h['map']!=truth)&invmask))
        relevant=np.abs(z-m.scan(truth,m.pose_shift(v,off)))
        expected_truth=m.scan(truth,m.pose_shift(v,off))
        max_error=float(np.abs(predicted[k]-expected_truth).mean())
        checks[-1][pol+'_posterior_max_difference']=float(abs(post-calc).max())
        if pol=='discriminative':
            _,scores,idx=m.choose(old,hs,w,list(views),pol)
            checks[-1]['scores_max_difference']=float(abs(np.array(scores)-np.array(decisions[(p.stem,pol)]['candidate_scores'])).max())
            checks[-1]['selected_view_matches']=bool(np.allclose(v,views[idx]))
        rows.append(dict(case=p.stem,condition=row['condition'],policy=pol,view=v.tolist(),
                         score_separation_before_cost=total,
                         map_difference_pair_fraction=float(terms[maps_different].sum()/max(total,1e-30)),
                         both_change_proposal_pair_fraction=float(terms[changed[:,None]&changed[None,:]].sum()/max(total,1e-30)),
                         pose_difference_pair_fraction=float(terms[~same_pose].sum()/max(total,1e-30)),
                         wrong_pose_pair_fraction=float(terms[wrong_pose_pair].sum()/max(total,1e-30)),
                         prior_correct_pose_mass=float(w[correct_pose].sum()),
                         posterior_correct_pose_mass=float(post[correct_pose].sum()),
                         posterior_change_mass=float(post[changed].sum()),posterior_joint_max=float(post.max()),
                         chosen_pose_error_xy=float(np.linalg.norm(offsets[k,:2]-off[:2])),
                         proposal_error_on_initial_observed_cells=masked_errors,
                         proposal_error_visible_to_selected_scan=max_error,
                         sensor_noise_mean_abs=float(relevant.mean()),
                         false_update_cells=row['false_update_cells'],map_error_before=row['map_error_before'],map_error_after=row['map_error_after'],
                         decision=row['decision'],has_true_pose_hypothesis=bool(correct_pose.any())))
out=R/'results'/args.out;out.mkdir(exist_ok=False);(out/'rows.json').write_text(json.dumps(rows,indent=2));(out/'reconstruction_checks.json').write_text(json.dumps(checks,indent=2))
with (out/'rows.csv').open('w') as f:
    wr=csv.DictWriter(f,list(rows[0]));wr.writeheader();wr.writerows(rows)
summary={}
for pol in ['nearest','uncertainty','stable','discriminative']:
    summary[pol]={}
    for cond in ['none','pose','change','both','out_of_bank']:
        a=[x for x in rows if x['policy']==pol and x['condition']==cond]
        keys=['score_separation_before_cost','map_difference_pair_fraction','both_change_proposal_pair_fraction','pose_difference_pair_fraction','wrong_pose_pair_fraction','posterior_correct_pose_mass','posterior_change_mass','posterior_joint_max','chosen_pose_error_xy','proposal_error_on_initial_observed_cells','proposal_error_visible_to_selected_scan','sensor_noise_mean_abs','false_update_cells','map_error_after']
        summary[pol][cond]={k:float(np.mean([x[k] for x in a])) for k in keys}
(out/'summary.json').write_text(json.dumps(summary,indent=2))
assert all(v<1e-12 for c in checks for k,v in c.items() if k.endswith('_difference'))
assert all(c.get('selected_view_matches',False) for c in checks)
print(json.dumps(summary['discriminative'],indent=2))
