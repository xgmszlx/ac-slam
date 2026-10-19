import os,sys,json,hashlib,time,subprocess,csv,collections,shutil
from pathlib import Path
P=Path(__file__).resolve().parents[1];S=Path('/home/wcqw/passive_visual_slam_qualification_20261015/sources/ORB_SLAM3-4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4');from evaluate import evaluate
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def run(seq,condition):
 ledger=P/'protocol/attempts.jsonl';existing=[json.loads(x) for x in ledger.read_text().splitlines()] if ledger.exists() else []
 assert len([x for x in existing if x['event']=='START'])<4
 assert not any(x['event']=='START' and x['sequence']==seq and x['condition']==condition for x in existing)
 assert shutil.disk_usage(P).free>5*1024**3
 d=P/'data'/('rgbd_dataset_freiburg1_desk' if seq=='desk' else 'rgbd_dataset_freiburg3_large_cabinet');out=P/'results'/seq/condition;out.mkdir(parents=True,exist_ok=False)
 cmd=[str(P/'build/rgbd_screen'),str(S/'Vocabulary/ORBvoc.txt'),str(P/'config'/f'{seq}.yaml'),str(d),str(d/'associations.txt'),condition,str(out)]
 env=dict(os.environ,LD_LIBRARY_PATH=str(P/'build')+':/home/wcqw/passive_visual_slam_qualification_20261015/local/lib:'+os.environ.get('LD_LIBRARY_PATH',''))
 rec={'sequence':seq,'condition':condition,'command':cmd,'binary_sha256':sha(P/'build/rgbd_screen'),'core_sha256':sha(P/'build/libORB_SLAM3.so'),'yaml_sha256':sha(P/'config'/f'{seq}.yaml'),'association_sha256':sha(d/'associations.txt'),'GT_online':False,'frames_expected':len((d/'associations.txt').read_text().splitlines()),'start_unix':time.time()};(out/'run.json').write_text(json.dumps(rec,indent=2))
 with ledger.open('a') as f:f.write(json.dumps({'event':'START','sequence':seq,'condition':condition,'unix':time.time()})+'\n')
 t=time.monotonic()
 with (out/'stdout.log').open('w') as log:
  try:r=subprocess.run(['/usr/bin/time','-v','-o',str(out/'resources.txt')]+cmd,env=env,cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=600);rec['exit']=r.returncode
  except subprocess.TimeoutExpired:rec['exit']='TIMEOUT'
 rec['elapsed_wall_s']=time.monotonic()-t
 if (out/'frame_states.csv').exists():
  z=list(csv.DictReader((out/'frame_states.csv').open()));rec['processed_frames']=len(z);rec['states']=dict(collections.Counter(x['state'] for x in z));rec['map_ids']=sorted({int(float(x['map_id'])) for x in z});rec['frame_identity_missing']=sum(float(x['N'])<0 for x in z)
  rec['multi_map_gauge_warning']=len(rec['map_ids'])>1
 for label,trajectory in [('exported','CameraTrajectory.txt'),('online','OnlineTrajectory.txt')]:
  try:
   target=out if label=='exported' else out/'online_eval_input'
   if label=='online':
    target.mkdir();(target/'CameraTrajectory.txt').symlink_to(out/trajectory);(target/'KeyFrameTrajectory.txt').symlink_to(out/'KeyFrameTrajectory.txt')
   ev=evaluate(d,target,out/'evaluation'/label)
   a=[x.split() for x in (out/trajectory).read_text().splitlines() if x.strip()];stamps=[x[0] for x in a];identity=len(stamps)==len(set(stamps)) and not rec.get('multi_map_gauge_warning',True)
   rec[label]={'ATE':ev['ate_m']['rmse'],'RPEt':ev['rpe_1s_translation_m'].get('rmse'),'RPEr':ev['rpe_1s_rotation_deg'].get('rmse'),'RPE_pairs':ev['rpe_1s_translation_m']['n'],'coverage':ev['saved_pose_fraction_of_input'],'identity_gauge_qualified':identity,'rows':len(a),'unique_stamps':len(set(stamps))}
  except Exception as e:rec[label]={'evaluation_error':str(e)}
 (out/'run.json').write_text(json.dumps(rec,indent=2))
 with ledger.open('a') as f:f.write(json.dumps({'event':'END','sequence':seq,'condition':condition,'exit':rec['exit'],'elapsed_s':rec['elapsed_wall_s']})+'\n')
 print(json.dumps(rec),flush=True)
 if rec['exit']!=0:raise SystemExit('Technical failure retained. Stop, no rerun.')
if __name__=='__main__':
 frozen=json.loads((P/'protocol/design_frozen.json').read_text());assert frozen['maximum_runs']==4
 for f,h in frozen['file_hashes'].items():assert sha(Path(f))==h,f
 for seq,condition in [('desk','B0'),('desk','B1'),('large_cabinet','B0'),('large_cabinet','B1')]:run(seq,condition)
