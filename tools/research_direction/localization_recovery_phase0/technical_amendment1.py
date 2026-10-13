#!/usr/bin/python3
"""Outcome-blind include-path amendment; R0 code, prereg and failed run unchanged.

Global budget unchanged. Three valid healthy controls have priority, hence the
last repetitive baseline is NOT_STARTED_BY_BUDGET before any scientific data.
"""
import argparse,json,os
from pathlib import Path
from protocol import ROOT,ASSETS,OUT,create_json,atomic_json,sha
import runner,analysis

AMEND=OUT/'protocol/technical_amendment1.json'
def freeze_amendment():
    if AMEND.exists():raise RuntimeError('amendment already frozen')
    failed=OUT/'baseline/NORMAL_GEOMETRY_271001'
    streams=list(failed.glob('*stream.jsonl'))
    if not streams or any(p.stat().st_size for p in streams):raise RuntimeError('outcome-blind claim unavailable: source streams not empty')
    if (failed/'episode_result.json').exists() or (failed/'metrics.json').exists():raise RuntimeError('endpoint exists before amendment')
    immutable=[OUT/'protocol/preregistration.json',OUT/'protocol/preregistration_hash.json',OUT/'protocol/frozen_baseline_matrix.json',OUT/'analysis/scientific_gate.json']
    immutable += [p for p in failed.iterdir() if p.is_file()]
    original=json.loads((OUT/'protocol/frozen_baseline_matrix.json').read_text());planned=original[:-1]
    planned[0]={**planned[0],'episode_id':planned[0]['episode_id']+'_A1','technical_retry_of':original[0]['episode_id']}
    # These symlinks supply exactly the already frozen original sensor include.
    # Stage resolves nested relative includes against the top-level world dir.
    inc=OUT/'protocol/worlds/hokuyo.inc'
    if inc.exists() or inc.is_symlink():raise RuntimeError('unexpected pre-existing include alias')
    inc.symlink_to(ASSETS/'baseline/Graph-Based_SLAM-Aware_Exploration/world/map3/hokuyo.inc')
    alias=OUT/'protocol/worlds'/(planned[0]['episode_id']+'.world')
    alias.symlink_to(original[0]['episode_id']+'.world')
    data={'id':'DOC81_TECHNICAL_AMENDMENT1_INCLUDE_PATH','date':'2026-10-13',
          'reason':'Stage resolves p3at.inc nested hokuyo.inc relative to new world root; first Stage exited, no scans/GT/endpoints',
          'change':'read-only sensor include alias; same frozen bytes, no physics or matcher parameter change',
          'unchanged':['routes','seeds','initial nuisance poses','odometry coefficients','sensor','Karto','GT alignment','error metric','healthy threshold rule','event duration','15 total and9 baseline attempts'],
          'coverage_amendment':'8 valid planned baselines plus1 already failed attempt;3 healthy+3 corridor+2 repetitive. Missing repetitive seed271003 is declared before outcomes, not replaced.',
          'planned_matrix':planned,'not_started_by_budget':original[-1],
          'pre_amendment_scientific_capture_bytes':0,'pre_amendment_scientific_endpoint_existed':False,
          'immutable_R0_sha256':{str(p.relative_to(OUT)):sha(p) for p in immutable},
          'amendment_code_sha256':sha(Path(__file__)),
          'included_sensor_sha256':sha(inc),'retry_world_sha256':sha(alias),
          'first_gate':'three healthy eligible controls plus complete corridor3;2/3 corridor events suffice. Repetitive2 is descriptive, cannot claim3-seed replication.'}
    create_json(AMEND,data);create_json(AMEND.with_name('technical_amendment1_hash.json'),{'sha256':sha(AMEND)})
def check():
    a=json.loads(AMEND.read_text())
    if sha(Path(__file__))!=a['amendment_code_sha256']:raise RuntimeError('amendment code changed')
    for p,digest in a['immutable_R0_sha256'].items():
        if sha(OUT/p)!=digest:raise RuntimeError('immutable first attempt/R0 changed '+p)
    runner.verify_frozen();return a
def qualified_rows():
    a=json.loads(AMEND.read_text());found=[]
    for spec in a['planned_matrix']:
        p=OUT/'baseline'/spec['episode_id']/'metrics.json'
        if p.exists():found.append(json.loads(p.read_text()))
    return found
def healthy():
    p=OUT/'protocol/healthy_threshold.json'
    if p.exists():return json.loads(p.read_text())
    rows=[r for r in qualified_rows() if r['scenario']=='NORMAL_GEOMETRY']
    if len(rows)!=3 or any(not r['technical_valid'] or not r['task_completion'] for r in rows):raise RuntimeError('three valid healthy controls still mandatory')
    typ=max(r['translation_p95_m'] for r in rows)
    data={'threshold_m':max(.15,3*typ),'healthy_typical_error_m':typ,'definition':'unchanged max(0.15m,3*max healthy episode p95); >=2s strict exceedance',
          'sources':{r['episode_id']:sha(OUT/'baseline'/r['episode_id']/'metrics.json') for r in rows},'calibrated_only_on_healthy':True,'protocol_id':'DOC81_TECHNICAL_AMENDMENT1_INCLUDE_PATH'}
    create_json(p,data);create_json(p.with_name('healthy_threshold_hash.json'),{'sha256':sha(p)});return data
def summarize():
    a=check();data=qualified_rows()
    normal=[r for r in data if r['scenario']=='NORMAL_GEOMETRY']
    if len(normal)==3 and all(r['technical_valid'] and r['task_completion'] for r in normal):
        healthy();data=[analysis.analyze_episode(OUT/'baseline'/r['episode_id']) for r in data]
    ledger=json.loads((OUT/'protocol/budget_ledger.json').read_text());ids={r['episode_id'] for r in a['planned_matrix']}
    failures=[r for r in ledger['attempts'] if r['episode_id'] in ids and r['status'] in ('TECHNICAL_FAILURE','INTERRUPTED')]
    bad=bool(failures or any(not r['technical_valid'] for r in data));complete=len(data)==8
    corridor=[r for r in data if r['scenario']=='CORRIDOR_DEGENERACY'];health_valid=len(normal)==3 and all(r['technical_valid'] and r['task_completion'] for r in normal)
    issue=len(corridor)==3 and sum(bool(r['event_count']) for r in corridor)>=2 and health_valid
    gate={'protocol_id':a['id'],'level_1':'TECHNICAL_GATE_FAIL' if bad else ('TECHNICAL_GATE_PASS' if complete else 'PENDING'),
          'level_2':'SCIENTIFIC_MEASUREMENT_INCOMPLETE' if bad else ('MEANINGFUL_DEGRADATION_FOUND' if issue else ('NO_MEANINGFUL_DEGRADATION_FOUND' if complete else 'PENDING')),
          'level_3':'RECOVERY_NOT_TESTED','amendment_valid_baseline_episodes':len(data),'total_attempts':len(ledger['attempts']),
          'original_qualification_failure_preserved':True,'repetitive_planned_missing_seed':271003,
          'corridor_event_seed_count':sum(bool(r['event_count']) for r in corridor),'intervention_first_gate':bool(issue and complete and not bad),
          'novelty':'NOVELTY_NOT_ESTABLISHED','scope':'3healthy/3corridor/2repetitive outcome-blind technical amendment, no drop of scientific failure'}
    atomic_json(OUT/'analysis/A1_scientific_gate.json',gate)
    analysis.csv_out(OUT/'baseline/A1_episode_ledger.csv',[{k:v for k,v in r.items() if k not in ('alignment','degradation_events')} for r in data])
    analysis.fig(data)
    (OUT/'A1_STATUS.md').write_text('# Doc81 Amendment1\n\n'+json.dumps(gate,indent=2)+'\n')
    print(json.dumps(gate,indent=2),flush=True);return gate
def run(max_episodes):
    a=check();used=0;ledger=json.loads((OUT/'protocol/budget_ledger.json').read_text());prior={r['episode_id']:r['status'] for r in ledger['attempts']}
    if any(prior.get(r['episode_id']) in ('TECHNICAL_FAILURE','INTERRUPTED','RESERVED') for r in a['planned_matrix']):raise RuntimeError('A1 failed/in-flight run must not auto-retry')
    for row in a['planned_matrix']:
        if row['episode_id'] in prior:continue
        if used>=max_episodes:break
        if row['scenario']!='NORMAL_GEOMETRY':healthy()
        print('START '+row['episode_id'],flush=True);s=runner.execute(row);used+=1
        print('END '+row['episode_id']+' '+s,flush=True)
        if s not in ('SUCCEEDED','NAVIGATION_FAILED'):break
        r=analysis.analyze_episode(OUT/'baseline'/row['episode_id'])
        if not r['technical_valid'] or row['scenario']=='NORMAL_GEOMETRY' and not r['task_completion']:
            print('STOP on qualification failure '+str(r['technical_reasons']),flush=True);break
    summarize()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=('freeze','run','analyze'));p.add_argument('--max-episodes',type=int,default=8);a=p.parse_args()
    if a.command=='freeze':freeze_amendment()
    elif a.command=='run':run(a.max_episodes)
    else:summarize()
