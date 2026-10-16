"""Summarize actual qualification outputs, never fabricate task outcomes."""
from pathlib import Path
import csv,datetime,hashlib,json,statistics
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parents[1]
j=json.loads((R/'results/phase0_qualified_extraction.json').read_text())
rows=[]
for item in j['predictions']:
    rows.append({'input':Path(item['path']).name,'kind':item['kind'],'label_offline':item.get('label_offline','UNKNOWN'),
                 'p_EX':item['p_EX'],'stop_at_08':item['stop_at_08'],'inference_wall_s':item['wall_s']})
with (R/'results/cnn_observations.csv').open('x',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
fig,ax=plt.subplots(figsize=(10,4.6))
names=[x['input'].replace('.png','').replace('@',' / ') for x in rows]
ax.bar(range(len(rows)),[x['p_EX'] for x in rows],color=['#3572aa']*4+['#aa7135']*3)
ax.axhline(.8,color='red',linestyle='--',label='Frozen threshold 0.8');ax.set_ylim(0,1.08)
ax.set_xticks(range(len(rows)),names,rotation=28,ha='right');ax.set_ylabel('p_EX (qualified frozen model)')
ax.set_title('Four author inputs and three native final maps; no action comparison')
ax.legend();fig.tight_layout();fig.savefig(R/'figures/phase0_p_ex.png',dpi=150);plt.close(fig)
with (R/'results/scientific_comparison.csv').open('x',newline='') as f:
    w=csv.DictWriter(f,fieldnames=['method','scientific_tasks','status','room_omission','GT_free_coverage','extra_motion_m','extra_time_s','scan_count']);w.writeheader()
    for method in ['B0','B1','B2','P','temporal_shadow']:
        w.writerow(dict(method=method,scientific_tasks=0,status='NOT_RUN_PRECONDITIONS_UNQUALIFIED',room_omission='NA',GT_free_coverage='NA',extra_motion_m='NA',extra_time_s='NA',scan_count='NA'))
decision={'CNN_TECHNICAL_QUALIFICATION':'PASS_WITH_DOCUMENTED_INITIALIZATION_IO_EXTRACTION',
          'arrays_equal':j['arrays_loaded_and_equal'],'CPU_warm_mean_s':statistics.mean(j['warm_times_s']),
          'peak_RSS_MiB':j['peak_rss_bytes']/1024**2,'CANDIDATE_DISCOVERABILITY':'UNRESOLVED_NO_CORRESPONDING_MISSED_ROOM_TRUTH',
          'ACTION_SPACE':'GEOMETRIC_DIFFERENCE_FOUND_RUNTIME_SAFETY_NOT_QUALIFIED',
          'STOP_EVENT_QUALIFICATION':'NO_QUALIFYING_EVENT_EVIDENCE_IN_AVAILABLE_NATIVE_RECORDS',
          'within_300s_event_exists':'UNKNOWN_NOT_PROVEN_ABSENT','ROS_TECHNICAL_QUALIFICATION':'NOT_RUN',
          'SCIENTIFIC_COMPARISON':'NOT_RUN','scientific_hypothesis':'UNRESOLVED',
          'technical_ROS_used':0,'scientific_used':0,'method_development':'NO_GO_CURRENT_EVIDENCE',
          'execution_decision':'DO_NOT_START_CURRENT_MAP3_MATRIX',
          'future_condition':'Only reconsider with directly reusable native map time series and legal shared state for an actual missed-room stop event; no new backend construction',
          'author_4_0_raw_pair':'One offline labelled false stop is rejected by the next available saved map; elapsed time unknown, no cost-normalized passive success claim',
          'unqualified_variant':'results/phase0_inference.json is superseded for original-model equivalence; do not cite as author-model probabilities'}
(R/'results/DECISION.json').write_text(json.dumps(decision,indent=2))
initial=R/'audit/protocol_freeze.json'
if not (R/'audit/protocol_freeze_initial.json').exists():(R/'audit/protocol_freeze_initial.json').write_bytes(initial.read_bytes())
files=[R/'protocol/D1_EXPLORATORY_PROTOCOL_V2.md',*sorted((R/'code').glob('*.py')),R/'sources/author/Code/checkpoint_weights/weights_classification/weights_old.h5',R/'data/cnn_inputs_manifest.json']
freeze={'frozen_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'ROS_runs':0,'scientific_runs':0,
        'files':{str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        'scene':'Original map3 unchanged','science_task_matrix':'NOT_ACTIVATED_PRECONDITIONS_UNQUALIFIED',
        'revision_reason':'Faithful source extraction corrections only; no method outcomes, threshold, noise, budget, or scene selection changes',
        'initial_freeze_preserved':'audit/protocol_freeze_initial.json'}
initial.write_text(json.dumps(freeze,indent=2));print(json.dumps(decision,indent=2))
