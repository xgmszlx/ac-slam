import hashlib,json,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1]
roots=['active_map_author_validation','active_slam_ab_decision_20261014','active_slam_topic_audit_20261014','active_slam_feedback_probe_20261014','active_slam_next_direction_20261014']
files={}
for name in roots:
 for p in (Path('/home/wcqw')/name).rglob('*'):
  if p.is_file() and not p.is_symlink(): files[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
git={}
for name in ['ac-slam','ac-slam_doc81','ac-slam_alc_screen']:
 p='/home/wcqw/'+name
 git[name]={k:subprocess.check_output(['git','-C',p]+v).decode() for k,v in {'head':['rev-parse','HEAD'],'status':['status','--porcelain'],'diff':['diff','--binary']}.items()}
out=dict(files=files,git=git)
if sys.argv[1]=='before': (R/'audit/protection_before.json').write_text(json.dumps(out))
else:
 old=json.loads((R/'audit/protection_before.json').read_text());result=dict(equal=old==out,changed=[k for k in old['files'] if old['files'][k]!=files.get(k)],git_equal=old['git']==git)
 (R/'audit/protection_after.json').write_text(json.dumps(result,indent=2)); print(result)
