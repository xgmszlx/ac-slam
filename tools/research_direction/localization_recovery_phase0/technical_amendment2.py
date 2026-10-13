#!/usr/bin/python3
"""Last bounded runtime compatibility repair: -g is no-GUI; -u was namespacing.

No thresholds, data, matcher, or frozen source changed. Two failed attempts
remain; seven possible scientifically captured baseline attempts remain.
"""
import argparse,json
from pathlib import Path
import runner,analysis,technical_amendment1 as a1
from protocol import OUT,ASSETS,create_json,atomic_json,sha

FILE=OUT/'protocol/technical_amendment2.json'
def freeze():
    original=a1.check()
    failed=OUT/'baseline/NORMAL_GEOMETRY_271001_A1'
    if (failed/'metrics.json').exists() or (failed/'episode_result.json').exists():raise RuntimeError('scientific endpoint exists')
    if any(p.stat().st_size for p in failed.glob('*stream.jsonl') if p.name!='tf_stream.jsonl'):raise RuntimeError('scientific capture exists')
    planned=original['planned_matrix'][:-1];planned[0]={**planned[0],'episode_id':'NORMAL_GEOMETRY_271001_A2'}
    world=OUT/'protocol/worlds/NORMAL_GEOMETRY_271001_A2.world';world.symlink_to('NORMAL_GEOMETRY_271001.world')
    immutable={**original['immutable_R0_sha256'],str(a1.AMEND.relative_to(OUT)):sha(a1.AMEND),
               'analysis/A1_scientific_gate.json':sha(OUT/'analysis/A1_scientific_gate.json')}
    immutable.update({str(p.relative_to(OUT)):sha(p) for p in failed.iterdir() if p.is_file()})
    data={**original,'id':'DOC81_TECHNICAL_AMENDMENT2_STAGE_CLI','reason':'installed stageros -u uses model names; observed /robot/odom and /robot/base_scan namespace. Upstream main confirms -g disables GUI and leaves unprefixed topics.',
          'change':'only new generated launch -u replaced by -g; original source/launch/failed files unchanged',
          'planned_matrix':planned,'coverage_amendment':'3healthy+3corridor+1repetitive valid episodes;2 technical failures consume9 baseline slots. Repetitive seeds271002/271003 unstarted before outcomes.',
          'immutable_R0_sha256':immutable,'amendment2_code_sha256':sha(Path(__file__)),
          'scientific_capture_before_amendment':False,'not_started_seeds':{'REPETITIVE_OR_TRANSITION_GEOMETRY':[271002,271003]},
          'predeclared_repair_limit':'No further physical attempt after a new qualification failure; stop current round',
          'retry_world_sha256':sha(world)}
    create_json(FILE,data);create_json(FILE.with_name('technical_amendment2_hash.json'),{'sha256':sha(FILE)})
def configure():
    data=json.loads(FILE.read_text())
    if sha(Path(__file__))!=data['amendment2_code_sha256']:raise RuntimeError('A2 code changed')
    a1.AMEND=FILE;a1.check()
    original_launch=runner.create_launch
    def launch(row,directory):
        p=original_launch(row,directory);text=p.read_text()
        if text.count('args="-u ')!=1:raise RuntimeError('unexpected original Stage invocation')
        p.write_text(text.replace('args="-u ','args="-g '));return p
    runner.create_launch=launch;return data
def summary():
    a1.check();data=a1.qualified_rows();normal=[r for r in data if r['scenario']=='NORMAL_GEOMETRY']
    if len(normal)==3 and all(r['technical_valid'] and r['task_completion'] for r in normal):
        a1.healthy();data=[analysis.analyze_episode(OUT/'baseline'/r['episode_id']) for r in data]
    ledger=json.loads((OUT/'protocol/budget_ledger.json').read_text());expected={r['episode_id'] for r in json.loads(FILE.read_text())['planned_matrix']}
    fail=any(r['episode_id'] in expected and r['status'] in ('TECHNICAL_FAILURE','INTERRUPTED') for r in ledger['attempts']) or any(not r['technical_valid'] for r in data)
    complete=len(data)==7;corr=[r for r in data if r['scenario']=='CORRIDOR_DEGENERACY'];validhealth=len(normal)==3 and all(r['technical_valid'] and r['task_completion'] for r in normal)
    count=sum(bool(r['event_count']) for r in corr);issue=len(corr)==3 and count>=2 and validhealth
    gate={'protocol_id':'DOC81_TECHNICAL_AMENDMENT2_STAGE_CLI','level_1':'TECHNICAL_GATE_FAIL' if fail else ('TECHNICAL_GATE_PASS' if complete else 'PENDING'),
          'level_2':'SCIENTIFIC_MEASUREMENT_INCOMPLETE' if fail else ('MEANINGFUL_DEGRADATION_FOUND' if issue else ('NO_MEANINGFUL_DEGRADATION_FOUND' if complete else 'PENDING')),
          'level_3':'RECOVERY_NOT_TESTED','valid_baseline_episodes':len(data),'total_attempts':len(ledger['attempts']),
          'healthy_qualified_episodes':len(normal),'corridor_event_seed_count':count,'intervention_first_gate':bool(issue and complete and not fail),
          'repetitive_seed_replication_unresolved':True,'original_two_failures_immutable':True,'method_novelty':'NOVELTY_NOT_ESTABLISHED'}
    atomic_json(OUT/'analysis/A2_scientific_gate.json',gate)
    analysis.csv_out(OUT/'baseline/A2_episode_ledger.csv',[{k:v for k,v in r.items() if k not in ('alignment','degradation_events')} for r in data])
    analysis.fig(data);(OUT/'A2_STATUS.md').write_text('# Doc81 A2\n\n'+json.dumps(gate,indent=2)+'\n');print(json.dumps(gate,indent=2),flush=True)
    return gate
def run(n):
    data=configure();a1.summarize=summary
    a1.run(n)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['freeze','run','analyze']);p.add_argument('--max-episodes',type=int,default=7);a=p.parse_args()
    if a.command=='freeze':freeze()
    elif a.command=='run':run(a.max_episodes)
    else:configure();summary()
