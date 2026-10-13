"""Offline GT metrics, healthy-first threshold freeze and scientific gates."""
import csv,json,math,re
from collections import defaultdict
from pathlib import Path
import numpy as np
from protocol import ROOT,ASSETS,OUT,SCENARIOS,SEEDS,create_json,atomic_json,sha
from metrics import compose,inverse,interpolate_gt,error,relative_error,events,exposure,geometry_proxy

def rows(path):
    with Path(path).open() as f:return [json.loads(line) for line in f if line.strip()]
def csv_out(path,data):
    data=list(data)
    if not data:return
    path.parent.mkdir(parents=True,exist_ok=True);fields=list(dict.fromkeys(k for r in data for k in r))
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(data)
def evaluate_online(scans,truth,initial_cut):
    if any(b['stamp']<=a['stamp'] for a,b in zip(truth,truth[1:])):raise ValueError('GT stream not strictly ordered')
    paired=[]
    for scan in scans:
        if scan.get('map_base') is None:continue
        gt,gap=interpolate_gt(truth,scan['stamp'])
        if gt is None:continue
        paired.append((scan,gt,gap))
    static=[p for p in paired if p[0]['stamp']<initial_cut]
    if len(static)<2:raise ValueError('initial stationary GT/TF alignment not available')
    scan,g0,_=static[0];transform=compose(g0,inverse(scan['map_base']))
    residual=[error(compose(transform,p[0]['map_base']),p[1])[0] for p in static]
    if max(residual)>.03:raise ValueError('initial supposedly static interval inconsistent')
    evaluated=[]
    for scan,gt,gap in paired:
        estimate=compose(transform,scan['map_base']);xy,yaw=error(estimate,gt)
        evaluated.append({'stamp':scan['stamp'],'scan_index':scan['index'],'translation_error_m':xy,'heading_error_rad':yaw,
                          'estimate':estimate,'gt':gt,'sync_bracket_s':gap,'is_primary_task_metric':True})
    return evaluated,{'map_to_GT_SE2':transform,'initial_pair_stamp':static[0][0]['stamp'],
                      'initial_cut':initial_cut,'initial_static_pairs':len(static),'initial_static_max_error_m':max(residual),'refit_after_task':False}
def analyze_episode(directory):
    directory=Path(directory);spec=json.loads((directory/'episode_spec.json').read_text());result=json.loads((directory/'episode_result.json').read_text())
    scans=rows(directory/'scan_stream.jsonl');truth=rows(directory/'gt_stream.jsonl');reasons=[]
    clock=(directory/'bootstrap_clock.txt').read_text();sec=int(re.search(r'secs:\s*(\d+)',clock).group(1));nsec=int(re.search(r'nsecs:\s*(\d+)',clock).group(1));cut=sec+nsec*1e-9
    evaluated,alignment=evaluate_online(scans,truth,cut)
    task=[r for r in evaluated if result['task_start']<=r['stamp']<=result['task_end']]
    native=[r for r in scans if result['task_start']<=r['stamp']<=result['task_end']]
    if len(task)<20:reasons.append('too few correctly paired task scans')
    if 1-len(task)/max(1,len(native))>.10:reasons.append('GT/TF pairing coverage below 90%')
    boundaries=json.loads((directory/'boundary_manifest.json').read_text())
    if not all(b['all_checks_passed'] for b in boundaries.values()):reasons.append('synchronous boundary check failed')
    final=json.loads((directory/'graph_final_sync.json').read_text())
    provenance=rows(directory/'edge_provenance.jsonl');created=[e for e in provenance if e.get('record_type')=='constraint_created']
    if len(created)!=len(final['edges']):reasons.append('provenance edge-count mismatch')
    if any(b['stamp']<=a['stamp'] for a,b in zip(scans,scans[1:])):reasons.append('scan time invalid')
    task_truth=[g for g in truth if result['task_start']<=g['stamp']<=result['task_end']]
    distance=sum(math.hypot(b['x']-a['x'],b['y']-a['y']) for a,b in zip(task_truth,task_truth[1:]))
    yaw=sum(abs(math.atan2(math.sin(b['theta']-a['theta']),math.cos(b['theta']-a['theta']))) for a,b in zip(task_truth,task_truth[1:]))
    rpe=[]
    for i,a in enumerate(task):
        candidates=[b for b in task[i+1:] if abs(b['stamp']-a['stamp']-1.)<=.025]
        if not candidates:continue
        b=min(candidates,key=lambda p:abs(p['stamp']-a['stamp']-1.));t,h=relative_error(a['estimate'],b['estimate'],a['gt'],b['gt'])
        rpe.append({'stamp':a['stamp'],'translation_rpe_1s_m':t,'rotation_rpe_1s_rad':h})
    threshold_path=OUT/'protocol/healthy_threshold.json';threshold=json.loads(threshold_path.read_text())['threshold_m'] if threshold_path.exists() else None
    ev=events(task,threshold) if threshold else []
    serial=[{k:v for k,v in r.items() if k not in ('estimate','gt')} for r in task]
    for r,p in zip(serial,task):r.update(gt_x=p['gt'][0],gt_y=p['gt'][1],estimate_x=p['estimate'][0],estimate_y=p['estimate'][1])
    csv_out(directory/'localization_error.csv',serial);csv_out(directory/'rpe_1s.csv',rpe)
    geom=[]
    for s in native[::10]:
        proxy=geometry_proxy(s);proxy.update(stamp=s['stamp'],episode_id=spec['episode_id']);geom.append(proxy)
    csv_out(directory/'geometry_risk_metrics.csv',geom)
    metric={'episode_id':spec['episode_id'],'scenario':spec['scenario'],'seed':spec['seed'],'arm':spec['arm'],
      'technical_valid':not reasons,'technical_reasons':reasons,'task_completion':result['status']=='SUCCEEDED',
      'task_time_s':result['task_end']-result['task_start'],'actual_distance_m':distance,'actual_rotation_rad':yaw,
      'translation_rmse_m':float(np.sqrt(np.mean([r['translation_error_m']**2 for r in task]))),
      'translation_p95_m':float(np.percentile([r['translation_error_m'] for r in task],95)),
      'translation_max_m':max(r['translation_error_m'] for r in task),'final_translation_error_m':task[-1]['translation_error_m'],
      'heading_rmse_rad':float(np.sqrt(np.mean([r['heading_error_rad']**2 for r in task]))),
      'rpe_1s_translation_rmse_m':float(np.sqrt(np.mean([r['translation_rpe_1s_m']**2 for r in rpe]))) if rpe else None,
      'rpe_1s_rotation_rmse_rad':float(np.sqrt(np.mean([r['rotation_rpe_1s_rad']**2 for r in rpe]))) if rpe else None,
      'threshold_m':threshold,'degradation_events':ev,'exceedance_time_s':exposure(task,threshold) if threshold else None,
      'event_count':len(ev) if threshold else None,'native_scans':len(native),'paired_scans':len(task),
      'graph_nodes':len(final['nodes']),'graph_edges':len(final['edges']),
      'geometry_translation_ratio_median':float(np.median([g['translation_ratio'] for g in geom if g['proxy_valid']])),
      'alignment':alignment,'gt_online_input':False}
    atomic_json(directory/'metrics.json',metric)
    raw={str(p.relative_to(ROOT)):sha(p) for p in directory.iterdir() if p.is_file() and p.suffix in ('.jsonl','.world','.log')}
    atomic_json(directory/'raw_capture_hashes.json',raw)
    return metric
def freeze_healthy():
    path=OUT/'protocol/healthy_threshold.json'
    if path.exists():return json.loads(path.read_text())
    normal=[]
    for seed in SEEDS:
        p=OUT/'baseline'/('NORMAL_GEOMETRY_'+str(seed))/'metrics.json'
        if not p.exists():raise RuntimeError('all healthy controls required before threshold freeze')
        row=json.loads(p.read_text())
        if not row['technical_valid'] or not row['task_completion']:raise RuntimeError('healthy qualification failed')
        normal.append(row)
    typical=max(r['translation_p95_m'] for r in normal)
    data={'threshold_m':max(.15,3*typical),'healthy_typical_error_m':typical,'definition':'max(0.15m, 3*max healthy episode p95), strict exceedance for >=2s',
          'sources':{r['episode_id']:sha(OUT/'baseline'/r['episode_id']/'metrics.json') for r in normal},'calibrated_only_on_healthy':True}
    create_json(path,data);create_json(path.with_name('healthy_threshold_hash.json'),{'sha256':sha(path)})
    return data
def analyze_suite():
    metrics=[];ledger=json.loads((OUT/'protocol/budget_ledger.json').read_text())
    for r in ledger['attempts']:
        p=OUT/r['kind']/r['episode_id']/'metrics.json'
        if p.exists():metrics.append(json.loads(p.read_text()))
    if len([r for r in metrics if r['scenario']=='NORMAL_GEOMETRY' and r['technical_valid'] and r['task_completion']])==3:
        freeze_healthy()
        metrics=[analyze_episode(OUT/r['kind']/r['episode_id']) for r in ledger['attempts'] if (OUT/r['kind']/r['episode_id']/'metrics.json').exists()]
    csv_out(OUT/'baseline/episode_ledger.csv',[{k:v for k,v in r.items() if k not in ('alignment','degradation_events')} for r in metrics])
    csv_out(OUT/'audit/technical_validity.csv',[{'episode_id':r['episode_id'],'valid':r['technical_valid'],'reasons':json.dumps(r['technical_reasons'])} for r in metrics])
    failures=any(r['status'] in ('TECHNICAL_FAILURE','INTERRUPTED') for r in ledger['attempts']) or any(not r['technical_valid'] for r in metrics)
    complete=len(metrics)==9;groups=defaultdict(list)
    for r in metrics:groups[r['scenario']].append(r)
    candidate=[]
    for s,rr in groups.items():
        if s!='NORMAL_GEOMETRY' and len(rr)==3 and sum(bool(r['event_count']) for r in rr)>=2:candidate.append(s)
    gate={'level_1':'TECHNICAL_GATE_FAIL' if failures else ('TECHNICAL_GATE_PASS' if complete else 'PENDING'),
          'level_2':'SCIENTIFIC_MEASUREMENT_INCOMPLETE' if failures else ('MEANINGFUL_DEGRADATION_FOUND' if candidate else ('NO_MEANINGFUL_DEGRADATION_FOUND' if complete else 'PENDING')),
          'level_3':'RECOVERY_NOT_TESTED','baseline_completed':len(metrics),'attempt_budget_used':len(ledger['attempts']),
          'confirmed_weak_scenarios':candidate,'intervention_authorized_by_first_gate':bool(complete and not failures and candidate),
          'method_novelty':'NOVELTY_NOT_ESTABLISHED','unit':'independent fresh episode, seed controls initial physical nuisance only',
          'no_scans_as_independent_samples':True}
    atomic_json(OUT/'analysis/scientific_gate.json',gate)
    fig(metrics)
    status='# Doc81 当前进度\n\n'+json.dumps(gate,ensure_ascii=False,indent=2)+'\n'
    (OUT/'STATUS.md').write_text(status)
    print(json.dumps(gate,indent=2),flush=True);return gate
def fig(metrics):
    if not metrics:return
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axs=plt.subplots(1,3,figsize=(13,4),sharey=True)
    for ax,(s,_) in zip(axs,SCENARIOS.items()):
        for r in metrics:
            if r['scenario']!=s:continue
            data=list(csv.DictReader((OUT/'baseline'/r['episode_id']/'localization_error.csv').open()))
            start=float(data[0]['stamp']);ax.plot([float(x['stamp'])-start for x in data],[float(x['translation_error_m']) for x in data],label=str(r['seed']),lw=1)
            if r['threshold_m'] is not None:ax.axhline(r['threshold_m'],c='black',ls='--',lw=.7)
        ax.set_title(s.replace('_','\n'),fontsize=9);ax.set_xlabel('Task simulated seconds');ax.grid(alpha=.2);ax.legend(fontsize=7)
    axs[0].set_ylabel('Online map-base / GT translation error [m]');fig.tight_layout();fig.savefig(OUT/'figures/gt_error.png',dpi=150);plt.close(fig)
