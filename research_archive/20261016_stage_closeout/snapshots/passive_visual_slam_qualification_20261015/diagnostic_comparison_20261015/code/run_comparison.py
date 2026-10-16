import sys
sys.dont_write_bytecode=True
import pathlib,json,hashlib,subprocess,os,time,collections,csv,shutil
from evaluate import evaluate
N=pathlib.Path(__file__).resolve().parents[1];O=N.parent;S=O/'sources/ORB_SLAM3-4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(seq,tag,p2=False):
 out=N/'results'/seq/tag; out.mkdir(parents=True,exist_ok=False)
 assert shutil.disk_usage(N).free>=1000000000,'disk safety gate'
 dataset=O/'data'/('rgbd_dataset_freiburg3_'+seq+'_xyz')
 binary=N/'build'/('rgbd_masked' if p2 else 'rgbd_diagnostic')
 yaml=N/'config'/('P0.yaml' if tag.startswith('P0') else 'P1.yaml')
 command=[str(binary),str(S/'Vocabulary/ORBvoc.txt'),str(yaml),str(dataset),str(dataset/'associations.txt')]
 if p2: command += [str(N/'masks'/seq)]
 env=os.environ.copy();env['LD_LIBRARY_PATH']=str((N/'build/masked_lib') if p2 else S/'lib')+':'+str(O/'local/lib')+':'+env.get('LD_LIBRARY_PATH','')
 rec={'sequence':seq,'configuration':tag,'command':command,'start_unix':time.time(),'core_sha256':sha((N/'build/masked_lib/libORB_SLAM3.so') if p2 else S/'lib/libORB_SLAM3.so'),'binary_sha256':sha(binary),'yaml_sha256':sha(yaml),'gt_online':False,'frames_expected':len((dataset/'associations.txt').read_text().splitlines()),'diagnostic':'identical memory-buffer public state and TrackRGBD pose; no disk IO in main loop; native trajectory exports precede buffer writes'}
 (out/'run.json').write_text(json.dumps(rec,indent=2))
 ledger=N/'protocol/attempts.jsonl'
 with ledger.open('a') as f:f.write(json.dumps({'event':'start','sequence':seq,'tag':tag,'time':rec['start_unix']})+'\n')
 start=time.monotonic()
 with (out/'stdout.log').open('w') as log:
  try: p=subprocess.run(['/usr/bin/time','-v','-o',str(out/'resources.txt')]+command,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600);rec['exit_status']=p.returncode
  except subprocess.TimeoutExpired:rec['exit_status']='TIMEOUT'
 rec['elapsed_wall_s']=time.monotonic()-start
 (out/'run.json').write_text(json.dumps(rec,indent=2))
 with ledger.open('a') as f:f.write(json.dumps({'event':'end','sequence':seq,'tag':tag,'exit':rec['exit_status'],'elapsed':rec['elapsed_wall_s']})+'\n')
 if rec['exit_status']!=0: print('FAILED',seq,tag,flush=True); return None
 states=list(csv.DictReader((out/'frame_states.csv').open()));rec['state_counts']=dict(collections.Counter(r['state'] for r in states));rec['processed_frames']=len(states)
 getter=[float(r['getter_us']) for r in states];rec['getter_us']={'mean':sum(getter)/len(getter),'max':max(getter)}
 (out/'run.json').write_text(json.dumps(rec,indent=2))
 exported=evaluate(dataset,out,out/'evaluation/exported')
 online=out/'evaluation/online_input';online.mkdir();(online/'CameraTrajectory.txt').symlink_to(out/'OnlineTrajectory.txt');(online/'KeyFrameTrajectory.txt').symlink_to(out/'KeyFrameTrajectory.txt');(online/'run.json').symlink_to(out/'run.json')
 online_result=evaluate(dataset,online,out/'evaluation/online')
 print(json.dumps({'sequence':seq,'tag':tag,'exit':rec['exit_status'],'states':rec['state_counts'],'ATE':exported['ate_m']['rmse'],'RPE':exported['rpe_1s_translation_m']['rmse'],'coverage':exported['saved_pose_fraction_of_input'],'online_ATE':online_result['ate_m']['rmse'],'online_RPE':online_result['rpe_1s_translation_m']['rmse'],'wall_s':rec['elapsed_wall_s']}),flush=True)
 return exported
if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1]=='P2':
  assert json.loads((N/'audit/mask_filter_tests.json').read_text())['PASS']
  for seq,tag in [('walking','P2_01'),('walking','P2_02'),('walking','P2_03'),('sitting','P2_01')]:
   if run(seq,tag,True) is None:raise SystemExit('P2 run failed; no retries')
 else:
  assert json.loads((N/'audit/color_proof.json').read_text())['PASS']
  results=[]
  for label in json.loads((N/'protocol/design_frozen.json').read_text())['sequence_order']:
   seq,tag=label.split('/');r=run(seq,tag)
   if r is None:raise SystemExit('baseline run failed; no retries')
   if seq=='walking' and tag.startswith('P1'):results.append(r)
  gate=all(r['ate_m']['rmse']<=.05 and r['rpe_1s_translation_m']['rmse']<=.05 and r['saved_pose_fraction_of_input']>=.99 for r in results)
  (N/'audit/P1_gate.json').write_text(json.dumps({'walking_P1_runs':len(results),'solves':gate,'P2_allowed_if_masks_and_tests_qualified':not gate,'all_outcomes_retained':True},indent=2))
