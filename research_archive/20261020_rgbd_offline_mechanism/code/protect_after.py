from pathlib import Path
import json,hashlib,subprocess
D=Path(__file__).resolve().parents[1]
b=json.loads((D/'protocol/protection_before.json').read_text())
def git(a):return subprocess.check_output(['git','-C','/home/wcqw/ac-slam']+a).decode()
a={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in b['files']}
r={'n_files':len(a),'files_equal':a==b['files'],'changed':[p for p in a if a[p]!=b['files'][p]],'main_head_equal':git(['rev-parse','HEAD'])==b['git_head'],'main_status_equal':git(['status','--porcelain'])==b['git_status'],'main_diff_equal':hashlib.sha256(git(['diff']).encode()).hexdigest()==b['git_diff_sha256'],'scope':'36 consumed old source/log/GT/report files, plus original worktree HEAD/status/diff; not all historical data'}
assert all(r[k] for k in ['files_equal','main_head_equal','main_status_equal','main_diff_equal'])
(D/'protocol/protection_after.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
