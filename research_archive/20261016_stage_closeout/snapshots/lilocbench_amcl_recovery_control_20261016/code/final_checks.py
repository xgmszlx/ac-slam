from pathlib import Path
import hashlib,json,subprocess,os,socket,shutil,time,re
p=Path(__file__).resolve().parents[1];b=Path('/home/wcqw/lilocbench_amcl_validation_20261016')
def sha(f):
 h=hashlib.sha256()
 with Path(f).open('rb') as q:
  for c in iter(lambda:q.read(1048576),b''):h.update(c)
 return h.hexdigest()
before=json.loads((p/'audit/protection_before.json').read_text());diff=[f for f,h in before['files'].items() if not Path(f).is_file() or sha(f)!=h]
env=dict(os.environ,GIT_OPTIONAL_LOCKS='0')
git={k:subprocess.check_output(['git','-C','/home/wcqw/ac-slam']+a,env=env).decode() for k,a in [('head',['rev-parse','HEAD']),('status',['status','--porcelain=v1']),('diff',['diff','--binary'])]}
with socket.socket() as s:port_free=s.connect_ex(('127.0.0.1',11331))!=0
status=subprocess.check_output(['ps','-eo','pid,comm,args']).decode();ours=[x for x in status.splitlines() if len(x.split(None,2))==3 and x.split(None,2)[1] not in ['bash','sh','timeout'] and 'lilocbench_amcl_recovery_control_20261016/results/' in x and ('rosmaster' in x or 'rosout' in x or 'collect_amcl.py ' in x)]
started=[json.loads(x) for x in (p/'protocol/attempts_started.jsonl').read_text().splitlines()];done=[json.loads(x) for x in (p/'protocol/attempts.jsonl').read_text().splitlines()]
assert [r['id'] for r in started]==['A1_R0','A2_R0'];assert all(r['status']=='COMPLETE' and r['process_exit']==[0,0,0,0] for r in done)
freeze=json.loads((p/'protocol/run_inputs_frozen.json').read_text());hash_changed=[f for f,h in freeze['hashes'].items() if sha(f)!=h]
assert not hash_changed
result={'protected_files_checked':len(before['files']),'changed_old_files':diff,'old_hashes_equal':not diff,'git_equal':git==before['git'],'git_head':git['head'].strip(),'git_status':git['status'],'root_start_free_bytes':before['disk_free_bytes'],'root_end_free_bytes':shutil.disk_usage(p).free,'dedicated_master_port_free':port_free,'remaining_own_ROS_processes':ours,'frozen_input_and_run_code_hashes_unchanged':not hash_changed,'completed_runs':len(done),'extra_runs':0,'new_downloads_installs_training':0,'created_wall':time.time()}
(p/'audit/protection_after.json').write_text(json.dumps(result,indent=2));assert not diff and result['git_equal'] and port_free and not ours
(p/'protocol/attempts_final.json').write_text(json.dumps({'maximum':2,'used':2,'completed':['A1_R0','A2_R0'],'retry':0,'budget_closed':True,'next_experiment_automatically_authorized':False},indent=2))
# The fixture must exercise a positive random-injection branch, not merely test zero counts.
text=(p/'audit/fixture_1_new.stderr').read_text();n=sum(int(x.split()[1]) for x in text.splitlines() if x.startswith('RECOVERY_RESAMPLE_END '));assert n>0
(p/'audit/counter_positive_control.json').write_text(json.dumps({'scope':'software PF fixture ONLY, not LILocBench recovery-ON evidence','counted_random_particles_in_fixture':n,'status':'PASS'},indent=2))
print(json.dumps(result,indent=2))
