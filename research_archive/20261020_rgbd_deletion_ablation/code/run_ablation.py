"""Three authorized full runs only: E1, E2, native S0 repeat; no automatic retries."""
import os,time,json,csv,hashlib,subprocess,shutil,collections
from pathlib import Path
from evaluate import evaluate
P=Path(__file__).resolve().parents[1];S=Path('/home/wcqw/passive_visual_slam_qualification_20261015/sources/ORB_SLAM3-4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 assert json.loads((P/'audit/data_acquisition.json').read_text())['qualified']
 assert json.loads((P/'audit/technical_qualification.json').read_text())['qualified']
 assert json.loads((P/'protocol/design_frozen.json').read_text())['maximum_full_runs']==3
 data=json.loads((P/'audit/dataset.json').read_text());D=Path(data['path']);ledger=P/'protocol/attempts.jsonl';assert not ledger.exists(),'No automatic retry or budget expansion'
 files=[P/'build/rgbd_combo',P/'build/libORB_SLAM3.so',P/'config/bonn.yaml',P/'data/associations.txt',P/'code/evaluate.py',P/'code/Combo.cc',P/'code/Combo.h',P/'code/rgbd_combo.cc',P/'code/run_ablation.py',P/'protocol/design_frozen.json',D/'groundtruth.txt',P/'data/image_hashes.json']
 freeze={'budget':3,'order':['E1','E2','S0'],'file_hashes':{str(f):sha(f) for f in files},'GT_online':False,'no_parameter_tuning':True};(P/'protocol/run_inputs_frozen.json').write_text(json.dumps(freeze,indent=2))
 for condition in freeze['order']:
  assert shutil.disk_usage(P).free>5*1024**3
  for f,h in freeze['file_hashes'].items():assert sha(Path(f))==h
  out=P/'results'/condition;out.mkdir(exist_ok=False)
  cmd=[str(P/'build/rgbd_combo'),str(S/'Vocabulary/ORBvoc.txt'),str(P/'config/bonn.yaml'),str(D),str(P/'data/associations.txt'),condition,str(out)]
  rec={'condition':condition,'command':cmd,'frames_expected':data['associated_inputs'],'GT_online':False,'start_unix':time.time()};(out/'run.json').write_text(json.dumps(rec,indent=2))
  with ledger.open('a') as f:f.write(json.dumps({'event':'START','condition':condition,'unix':time.time()})+'\n')
  env=dict(os.environ,LD_LIBRARY_PATH=str(P/'build')+':/home/wcqw/passive_visual_slam_qualification_20261015/local/lib:'+os.environ.get('LD_LIBRARY_PATH',''));t=time.monotonic()
  with (out/'stdout.log').open('w') as log:
   try:rec['exit']=subprocess.run(['/usr/bin/time','-v','-o',str(out/'resources.txt')]+cmd,env=env,cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=600).returncode
   except subprocess.TimeoutExpired:rec['exit']='TIMEOUT'
  rec['wall_s']=time.monotonic()-t
  if (out/'frame_states.csv').exists():
   rows=list(csv.DictReader((out/'frame_states.csv').open()));rec['processed']=len(rows);rec['states']=dict(collections.Counter(x['state'] for x in rows));rec['map_ids']=sorted({int(float(x['map_id'])) for x in rows})
  for kind,traj in [('exported','CameraTrajectory.txt'),('online','OnlineTrajectory.txt')]:
   try:
    target=out if kind=='exported' else out/'online_eval_input'
    if kind=='online':target.mkdir();(target/'CameraTrajectory.txt').symlink_to(out/traj);(target/'KeyFrameTrajectory.txt').symlink_to(out/'KeyFrameTrajectory.txt')
    ev=evaluate(D,target,out/'evaluation'/kind);rec[kind]=ev
    ev['identity_gauge_qualified']=ev['duplicate_saved_timestamps']==0 and len(rec.get('map_ids',[]))==1
   except Exception as e:rec[kind]={'evaluation_error':str(e)}
  (out/'run.json').write_text(json.dumps(rec,indent=2))
  with ledger.open('a') as f:f.write(json.dumps({'event':'END','condition':condition,'exit':rec['exit']})+'\n')
  if rec['exit']!=0:raise SystemExit('Technical failure retained; no replacement or extra runs.')
 print('3/3 complete, budget closed. No repeats authorized.')
if __name__=='__main__':main()
