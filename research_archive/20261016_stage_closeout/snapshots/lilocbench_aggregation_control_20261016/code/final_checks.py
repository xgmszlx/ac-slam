from pathlib import Path
import json,hashlib,subprocess,os,socket,shutil,time
p=Path(__file__).resolve().parents[1];pro=json.loads((p/'protocol/design_frozen.json').read_text())
def sha(f):
 h=hashlib.sha256()
 with Path(f).open('rb') as q:
  for c in iter(lambda:q.read(1048576),b''):h.update(c)
 return h.hexdigest()
refs={}
for name,root in pro['reference_runs'].items():
 root=Path(root);params=json.loads((root/'parameters.json').read_text());log=(root/'launch.log').read_text(errors='replace');assert log.count('AUDIT_GAUSSIAN_SEED 1702')==1
 assert params['recovery_alpha_slow']==(0.001 if name.endswith('ON') else 0.) and params['recovery_alpha_fast']==(.1 if name.endswith('ON') else 0.)
 refs[name]={'parameters':params,'launch_sha256':sha(root/'launch.log'),'actual_gaussian_seed':1702}
(p/'audit/reference_parameters.json').write_text(json.dumps(refs,indent=2))
before=json.loads((p/'audit/protection_before.json').read_text());changed=[f for f,h in before['files'].items() if sha(f)!=h];env=dict(os.environ,GIT_OPTIONAL_LOCKS='0');git={k:subprocess.check_output(['git','-C','/home/wcqw/ac-slam']+a,env=env).decode() for k,a in [('head',['rev-parse','HEAD']),('status',['status','--porcelain=v1']),('diff',['diff','--binary'])]}
frozen=json.loads((p/'protocol/run_inputs_frozen.json').read_text());fchanged=[f for f,h in frozen['hashes'].items() if sha(f)!=h]
started=[json.loads(x) for x in (p/'protocol/attempts_started.jsonl').read_text().splitlines()];done=[json.loads(x) for x in (p/'protocol/attempts.jsonl').read_text().splitlines()];assert len(started)==len(done)==1 and started[0]['id']==done[0]['id']=='A0_91_R0';assert done[0]['status']=='COMPLETE' and done[0]['process_exit']==[0,0,0,0]
with socket.socket() as s:free=s.connect_ex(('127.0.0.1',11331))!=0
lines=subprocess.check_output(['ps','-eo','pid,comm,args']).decode().splitlines();remaining=[line for line in lines if len(line.split(None,2))==3 and line.split(None,2)[1] not in ['bash','sh','timeout'] and str(p/'results') in line and any(x in line for x in ['rosmaster','rosout','collect_amcl.py'])]
assert not changed and not fchanged and git==before['git'] and free and not remaining
out={'wall':time.time(),'old_files_checked':len(before['files']),'changed_old_files':changed,'git_equal':git==before['git'],'git_head':git['head'].strip(),'git_status':git['status'],'run_input_code_library_hashes_unchanged':not fchanged,'completed_full_runs':1,'extra_runs':0,'new_builds_installs_downloads_training':0,'dedicated_master_port_free':free,'remaining_own_ROS_processes':remaining,'root_start_free_bytes':before['free_bytes'],'root_end_free_bytes':shutil.disk_usage(p).free}
(p/'audit/protection_after.json').write_text(json.dumps(out,indent=2));(p/'protocol/attempts_final.json').write_text(json.dumps({'max_full_runs':1,'used':1,'completed':['A0_91_R0'],'retry':0,'budget_closed':True,'next_experiments_authorized':False},indent=2));print(json.dumps(out,indent=2))
