#!/usr/bin/env python3
"""Bounded synthetic decision audit, NOT SLAM or a paper reproduction.

Simulator truth enters sensor generation and offline evaluation only.
Planner sees old map, initial scan, nominal pose, and its own hypothesis bank.
"""
import argparse, hashlib, itertools, json, math
from pathlib import Path
import numpy as np
from scipy.ndimage import distance_transform_edt
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
CFG = dict(resolution=.1, size=120, beams=121, range=10., noise_std=.03,
           seeds=[7,17,27], start=[4.,4.,0.], offsets_x=[-.6,0.,.6],
           offsets_y=[-.4,0.,.4], offsets_yaw=[-.04,0.,.04],
           decision_confidence=.9, effective_beams=8., robust_scale=.15,
           change_prior=.35, footprint_radius=.35,
           scenes=['asymmetric','symmetric'], conditions=['none','pose','change','both','out_of_bank'],
           policies=['nearest','uncertainty','stable','discriminative','passive'],
           experiment_scope='one additional view; synthetic; no trajectory SLAM')
ANG = np.linspace(-np.pi/2,np.pi/2,CFG['beams'])
D = np.arange(.05,CFG['range']+.025,.05)
DIST = {}

def pose_shift(p, h):
    # Hypothesis is error relative to nominal initial frame, not absolute rotation about world origin.
    p=np.asarray(p); h=np.asarray(h); s=np.asarray(CFG['start'])
    c,t=np.cos(h[2]),np.sin(h[2]); R=np.array([[c,-t],[t,c]])
    return np.r_[s[:2]+h[:2]+R@(p[:2]-s[:2]),p[2]+h[2]]

def scan(m,p):
    a=ANG+p[2];x=p[0]+np.cos(a)[:,None]*D;y=p[1]+np.sin(a)[:,None]*D
    ix=(x/CFG['resolution']).astype(int);iy=(y/CFG['resolution']).astype(int)
    outside=(ix<0)|(iy<0)|(ix>=m.shape[1])|(iy>=m.shape[0])
    hits=m[np.clip(iy,0,m.shape[0]-1),np.clip(ix,0,m.shape[1]-1)]|outside
    first=hits.argmax(1);return np.where(hits.any(1),D[first],CFG['range'])

def integrate(m,p,z):
    """Two-pass inverse sensor model: endpoints override free rays; ignores wall thickness."""
    out=m.copy();seen=np.zeros_like(m);r=CFG['resolution']
    for a,d in zip(ANG+p[2],z):
        ds=np.arange(.05,max(.05,d-.1),.05)
        x=((p[0]+np.cos(a)*ds)/r).astype(int);y=((p[1]+np.sin(a)*ds)/r).astype(int)
        ok=(x>=0)&(y>=0)&(x<m.shape[1])&(y<m.shape[0]);out[y[ok],x[ok]]=False;seen[y[ok],x[ok]]=True
    for a,d in zip(ANG+p[2],z):
        if d>=CFG['range']-.1:continue
        x=int((p[0]+np.cos(a)*d)/r);y=int((p[1]+np.sin(a)*d)/r)
        if 0<=x<m.shape[1] and 0<=y<m.shape[0]:out[y,x]=True;seen[y,x]=True
    # Do not clear known outer containment boundary.
    out[:2,:]=out[-2:,:]=True;out[:,:2]=out[:,-2:]=True
    return out,seen

def likelihood(z,pred):
    e=np.abs(np.asarray(pred)-z)
    # Cauchy mixture + broad contamination, tempered for correlated beams.
    probs=.9/(1+(e/CFG['robust_scale'])**2)+.1
    return CFG['effective_beams']*np.log(probs).mean(axis=-1)

def normalize(logw):
    w=np.exp(logw-logw.max());return w/w.sum()

def bank(old,z):
    hs=[];pred=[];lp=[]
    for off in itertools.product(CFG['offsets_x'],CFG['offsets_y'],CFG['offsets_yaw']):
        p=pose_shift(CFG['start'],off)
        proposal,mask=integrate(old,p,z)
        for changed,m in [(False,old),(True,proposal)]:
            # Geometry proposal is built ONLY from observed initial scan under this pose.
            hs.append(dict(off=np.array(off),changed=changed,map=m,mask=mask))
            pred.append(scan(m,p));lp.append(np.log(CFG['change_prior'] if changed else 1-CFG['change_prior']))
    logw=np.array(lp)+likelihood(z,np.array(pred));return hs,normalize(logw),logw

def safe(m,p):
    x,y=(np.asarray(p[:2])/CFG['resolution']).astype(int)
    if not (0<=x<m.shape[1] and 0<=y<m.shape[0]):return False
    key=id(m)
    if key not in DIST:DIST[key]=distance_transform_edt(~m)*CFG['resolution']
    return DIST[key][y,x]>=CFG['footprint_radius']

def path_safe(m,v,off):
    s=np.array(CFG['start']);return all(safe(m,pose_shift(s+(np.array(v)-s)*t,off)) for t in np.linspace(0,1,24))

def candidates(old,hs,w):
    views=[];s=np.array(CFG['start'])
    # Safety is consensus over ALL pose hypotheses on old map, not truth.
    # Scan-derived map veto only for posterior-supported hypotheses (w >= .01).
    offs=list(itertools.product(CFG['offsets_x'],CFG['offsets_y'],CFG['offsets_yaw']))
    for dx,dy in [(.8,0),(-.8,0),(0,.8),(0,-.8),(1.6,1.2),(-1.6,1.2),(1.6,-1.2),(-1.6,-1.2)]:
        for yaw in [0,np.pi/2,-np.pi/2,np.pi]:
            v=s+np.array([dx,dy,yaw])
            if not all(path_safe(old,v,o) for o in offs):continue
            if any(not path_safe(h['map'],v,h['off']) for h,wi in zip(hs,w) if wi>=.01):continue
            views.append(v)
    return views

def choose(old,hs,w,views,policy):
    if policy=='passive':return np.array(CFG['start']),[],0.
    conflict=np.zeros_like(old,dtype=float)
    for h,wi in zip(hs,w):conflict+=wi*(h['map']!=old)
    scores=[]
    for v in views:
        preds=np.array([scan(h['map'],pose_shift(v,h['off'])) for h in hs])
        d=np.linalg.norm(v[:2]-np.array(CFG['start'])[:2]);a=ANG+v[2];zr=scan(old,v)
        x=np.clip(((v[0]+np.cos(a)*zr)/CFG['resolution']).astype(int),0,119)
        y=np.clip(((v[1]+np.sin(a)*zr)/CFG['resolution']).astype(int),0,119)
        if policy=='nearest':score=-d-.001*abs(v[2])
        elif policy=='uncertainty':score=float(conflict[y,x].sum())/(1+d)
        elif policy=='stable':
            # Historical-map endpoints outside observed conflict; no true static labels.
            normals=np.c_[np.cos(a),np.sin(a)];weights=1-conflict[y,x]
            score=float(np.linalg.eigvalsh((normals*weights[:,None]).T@normals)[0])/(1+d)
        else:
            # Bounded predictive separation over pose-map hypotheses; not a new formula.
            dif=(preds[:,None,:]-preds[None,:,:])**2
            sep=np.minimum(dif/.3**2,1.).mean(2)
            score=float(w@sep@w)/(1+d)
        scores.append(score)
    idx=int(np.argmax(scores));return views[idx],scores,idx

def decision(hs,w):
    ids=np.array([h['changed'] for h in hs]);pc=float(w[ids].sum())
    # Do not write when the joint pose-map state remains distributed.
    k=int(w.argmax());conf=float(w[k]);h=hs[k]
    result='UPDATE' if pc>=CFG['decision_confidence'] and conf>=.15 else ('KEEP' if pc<=1-CFG['decision_confidence'] else 'DEFER')
    return result,pc,k,conf

def world(scene,changed):
    m=np.zeros((120,120),dtype=bool);m[:2,:]=m[-2:,:]=True;m[:,:2]=m[:,-2:]=True
    if scene=='asymmetric':m[85:100,25:28]=True;m[75:78,75:100]=True;m[20:40,95:98]=True
    else:m[25:95,100:103]=True;m[25:95,17:20]=True
    old=m.copy()
    if changed:m[30:80,72:75]=True;m[75:78,75:100]=False
    return old,m

def run(out):
    out.mkdir(parents=True,exist_ok=False);(out/'raw').mkdir()
    rows=[];details=[]
    for scene,condition,seed in itertools.product(CFG['scenes'],CFG['conditions'],CFG['seeds']):
        DIST.clear()
        changed=condition in ['change','both','out_of_bank']
        off=np.array([.6,.4,.04]) if condition in ['pose','both'] else np.zeros(3)
        if condition=='out_of_bank':off=np.array([1.1,.7,.12])
        old,true=world(scene,changed);rng=np.random.default_rng(seed)
        z0=scan(true,pose_shift(CFG['start'],off))+rng.normal(0,CFG['noise_std'],len(ANG))
        hs,w,logw=bank(old,z0);views=candidates(old,hs,w)
        label=f'{scene}_{condition}_{seed}'
        init_conflict=float((np.abs(z0-scan(old,CFG['start']))>.3).mean())
        snap=dict(old=old,truth=true,offset=off,z0=z0,views=np.array(views),prior=w)
        if len(views)<2:
            rows.append(dict(case=label,status='TECHNICAL_GATE_FAIL',candidate_count=len(views)));continue
        for policy in CFG['policies']:
            v,scores,idx=choose(old,hs,w,views,policy)
            # Shared candidate-specific noise across policies. Passive supplies NO new independent evidence.
            rv=np.random.default_rng(seed*1000+int(idx));zt=scan(true,pose_shift(v,off))+rv.normal(0,CFG['noise_std'],len(ANG))
            posterior=w if policy=='passive' else normalize(logw+likelihood(zt,np.array([scan(h['map'],pose_shift(v,h['off'])) for h in hs])))
            action,pc,k,conf=decision(hs,posterior);h=hs[k]
            updated=old.copy()
            if action=='UPDATE':updated,_=integrate(h['map'],pose_shift(v,h['off']),zt)
            change_mask=true!=old;written=updated!=old
            false=int(np.count_nonzero(written&~change_mask));recalled=int(np.count_nonzero(written&change_mask))
            correct=(action=='UPDATE' and changed and false<=recalled) or (action=='KEEP' and not changed)
            row=dict(case=label,scene=scene,condition=condition,seed=seed,policy=policy,status='EXECUTED_SYNTHETIC',candidate_count=len(views),
                     view=v.tolist(),distance=float(np.linalg.norm(v[:2]-np.array(CFG['start'])[:2])),
                     initial_conflict=init_conflict,anchor_inspired_freeze=init_conflict>.2,
                     decision=action,change_probability=pc,joint_max=conf,chosen_pose=h['off'].tolist(),
                     posterior_entropy=float(-np.sum(posterior*np.log(posterior+1e-30))),
                     false_update_cells=false,change_recall=recalled/max(1,int(change_mask.sum())),
                     map_error_before=int(change_mask.sum()),map_error_after=int(np.count_nonzero(updated!=true)),
                     decision_correct=bool(correct),safe_truth_offline=bool(path_safe(true,v,off)))
            rows.append(row);details.append(dict(case=label,policy=policy,candidate_scores=scores,weights=posterior.tolist()))
            snap[policy+'_scan']=zt;snap[policy+'_map']=updated
        np.savez_compressed(out/'raw'/f'{label}.npz',**snap)
    (out/'results.json').write_text(json.dumps(rows,indent=2));(out/'decisions.json').write_text(json.dumps(details,indent=2))
    import csv
    keys=sorted(set().union(*(x.keys() for x in rows)))
    with (out/'results.csv').open('w') as f:
        wr=csv.DictWriter(f,keys);wr.writeheader();wr.writerows(rows)
    summary={}
    for pol in CFG['policies']:
        a=[x for x in rows if x.get('policy')==pol];summary[pol]={
            'n':len(a),'correct':sum(x['decision_correct'] for x in a),
            'defer':sum(x['decision']=='DEFER' for x in a),'update':sum(x['decision']=='UPDATE' for x in a),
            'false_update_cells':sum(x['false_update_cells'] for x in a),
            'mean_distance':float(np.mean([x['distance'] for x in a])),
            'mean_map_error_after':float(np.mean([x['map_error_after'] for x in a])),
            'unsafe':sum(not x['safe_truth_offline'] for x in a)}
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    fails=[x for x in rows if not x.get('decision_correct',False) or not x.get('safe_truth_offline',True)]
    (out/'failures.json').write_text(json.dumps(fails,indent=2))
    fig,axes=plt.subplots(1,3,figsize=(13,4))
    for ax,key in zip(axes,['correct','false_update_cells','mean_map_error_after']):
        ax.bar(range(len(summary)),[summary[p][key] for p in summary]);ax.set_xticks(range(len(summary)));ax.set_xticklabels(list(summary),rotation=30,ha='right');ax.set_title(key)
    fig.tight_layout();fig.savefig(ROOT/'figures/A_summary.png',dpi=150);plt.close(fig)
    sample=next((out/'raw').glob('asymmetric_both_7.npz'));a=np.load(sample)
    fig,axes=plt.subplots(1,3,figsize=(12,4))
    for ax,key in zip(axes,['old','truth','discriminative_map']):
        ax.imshow(a[key],origin='lower',extent=[0,12,0,12],cmap='gray_r');ax.set_title(key)
        if key=='old':ax.scatter(a['views'][:,0],a['views'][:,1],s=8,color='green')
    fig.tight_layout();fig.savefig(ROOT/'figures/A_case.png',dpi=150);plt.close(fig)
    print(json.dumps(summary,indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['freeze','run']);ap.add_argument('--out',default='A_run01');args=ap.parse_args()
    p=ROOT/'protocol/A_frozen.json'
    if args.mode=='freeze':
        with p.open('x') as f:json.dump(CFG,f,indent=2)
    else:
        assert json.loads(p.read_text())==CFG,'Frozen configuration differs'
        run(ROOT/'data'/args.out)
