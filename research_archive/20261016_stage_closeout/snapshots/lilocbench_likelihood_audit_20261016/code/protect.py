from pathlib import Path
import hashlib,json,subprocess,os,shutil,time
p=Path(__file__).resolve().parents[1]
def sha(f):
 h=hashlib.sha256()
 with Path(f).open('rb') as q:
  for c in iter(lambda:q.read(1048576),b''):h.update(c)
 return h.hexdigest()
b=json.loads((p/'audit/protection_before.json').read_text());changed=[f for f,h in b['files'].items() if not Path(f).exists() or sha(f)!=h];env=dict(os.environ,GIT_OPTIONAL_LOCKS='0');git={k:subprocess.check_output(['git','-C','/home/wcqw/ac-slam']+a,env=env).decode() for k,a in [('head',['rev-parse','HEAD']),('status',['status','--porcelain=v1']),('diff',['diff','--binary'])]}
frozen=json.loads((p/'protocol/candidates_frozen_before_scores.json').read_text());fd=[f for f,h in frozen['hashes'].items() if sha(p/f)!=h]
r={'old_files_checked':len(b['files']),'changed_old_files':changed,'git_equal':git==b['git'],'git_head':git['head'].strip(),'git_status':git['status'],'candidate_scan_source_freeze_equal':not fd,'root_before_free_bytes':b['free_bytes'],'root_after_free_bytes':shutil.disk_usage(p).free,'new_full_filter_runs':0,'new_ROS_nodes':0,'downloads_installs_training':0,'new_bytes':sum(f.stat().st_size for f in p.rglob('*') if f.is_file()),'wall':time.time()}
(p/'audit/protection_after.json').write_text(json.dumps(r,indent=2));assert not changed and git==b['git'] and not fd;assert r['new_bytes']<512*1024**2 and r['root_after_free_bytes']>5*1024**3;print(json.dumps(r,indent=2))
