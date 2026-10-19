"""Archive/data consistency only. Never execute a SLAM run."""
from pathlib import Path
import json,hashlib,csv,ast,re
import numpy as np
P=Path(__file__).resolve().parents[1]
def main():
 inv=json.loads((P/'publication/inventory.json').read_text())
 for r in inv['files']:
  assert hashlib.sha256((P/r['path']).read_bytes()).hexdigest()==r['sha256']
  assert hashlib.sha256(Path(r['source']).read_bytes()).hexdigest()==r['sha256']
 for f in P.rglob('*.py'):ast.parse(f.read_text())
 rows=list(csv.DictReader((P/'results/summary.csv').open()));assert len(rows)==4
 for row in rows:assert row['exit']=='0' and row['exported_coverage']=='1.0' and row['identity_gauge_qualified']=='True'
 for seq,n,target in [('desk',573,22909),('large_cabinet',984,58687)]:
  a=list(csv.DictReader((P/'results'/seq/'B0/frame_states.csv').open()));b=list(csv.DictReader((P/'results'/seq/'B1/frame_states.csv').open()));assert len(a)==len(b)==n
  for x,y in zip(a,b):
   assert x['stamp']==y['stamp'] and x['N']==y['N'] and x['boundary_features']==y['boundary_features']
   assert float(y['boundary_features'])==float(y['invalid_boundary'])==float(y['both_minus_one'])
  assert sum(float(y['invalid_boundary']) for y in b)==target
  for condition in ['B0','B1']:
   path=P/'results'/seq/condition;run=json.loads((path/'run.json').read_text());assert run['exit']==0 and run['processed_frames']==n
   for name in ['CameraTrajectory.txt','OnlineTrajectory.txt']:
    t=np.loadtxt(path/name);assert len(t)==n and np.isfinite(t).all() and (np.diff(t[:,0])>0).all()
 ledger=[json.loads(x) for x in (P/'protocol/attempts.jsonl').read_text().splitlines()];assert sum(x['event']=='START' for x in ledger)==4
 bad_ext={'.bag','.db','.tgz','.zip','.pdf','.so','.o','.h5','.onnx','.npy','.npz','.pyc'};assert not [f for f in P.rglob('*') if f.is_file() and f.suffix in bad_ext]
 suspect=[]
 patterns=[r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----',r'gh[pousr]_[A-Za-z0-9]{30,}',r'github_pat_[A-Za-z0-9_]{30,}',r'AKIA[0-9A-Z]{16}',r'https?://[^\s/@:]+:[^\s/@]+@']
 for f in P.rglob('*'):
  if not f.is_file() or f.suffix=='.png' or f.name=='verify_archive.py':continue
  if any(re.search(q,f.read_text(errors='replace')) for q in patterns):suspect.append(str(f.relative_to(P)))
 assert not suspect,suspect
 result={'status':'PASS','byte_exact_sources':len(inv['files']),'full_runs':4,'input_pairs':{'desk':573,'large_cabinet':984},'changed_native_depth_observations':81596,'trajectory_identity':'finite unique increasing, full input coverage','python_AST':'PASS','artifact_scope':'No input data/models/builds. Small self-generated trajectories and scalar Frame diagnostics intentionally included.','scientific_status':'ANALYZED; n=1 per condition; no new-method qualification','extra_SLAM_runs_during_publication':0};(P/'publication/verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':main()
