"""Four authorized repeats only. Labels never replace the native B0/B1 argument."""
import os,sys,json,hashlib,time,subprocess,csv,collections,shutil
from pathlib import Path
from evaluate import evaluate
P=Path(__file__).resolve().parents[1]
OLD=Path('/home/wcqw/passive_rgbd_depth_screen_20261019')
S=Path('/home/wcqw/passive_visual_slam_qualification_20261015/sources/ORB_SLAM3-4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4')
ORDER=['B1_02','B0_02','B0_03','B1_03']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def run(label):
    ledger=P/'protocol/attempts.jsonl'
    existing=[json.loads(x) for x in ledger.read_text().splitlines()] if ledger.exists() else []
    started=[x['label'] for x in existing if x['event']=='START']
    assert started==ORDER[:len(started)] and len(started)<4 and label==ORDER[len(started)]
    assert len([x for x in existing if x['event']=='END'])==len(started)
    assert shutil.disk_usage(P).free>5*1024**3
    condition=label.split('_')[0];assert condition in ('B0','B1')
    d=OLD/'data/rgbd_dataset_freiburg1_desk';out=P/'results'/label;out.mkdir(exist_ok=False)
    cmd=[str(OLD/'build/rgbd_screen'),str(S/'Vocabulary/ORBvoc.txt'),str(OLD/'config/desk.yaml'),str(d),str(d/'associations.txt'),condition,str(out)]
    env=dict(os.environ,LD_LIBRARY_PATH=str(OLD/'build')+':/home/wcqw/passive_visual_slam_qualification_20261015/local/lib:'+os.environ.get('LD_LIBRARY_PATH',''))
    rec={'sequence':'desk','label':label,'condition':condition,'command':cmd,'binary_sha256':sha(OLD/'build/rgbd_screen'),'core_sha256':sha(OLD/'build/libORB_SLAM3.so'),'yaml_sha256':sha(OLD/'config/desk.yaml'),'association_sha256':sha(d/'associations.txt'),'GT_online':False,'frames_expected':573,'start_unix':time.time(),'loadavg_before':os.getloadavg(),'LD_LIBRARY_PATH':env['LD_LIBRARY_PATH']}
    (out/'run.json').write_text(json.dumps(rec,indent=2))
    with ledger.open('a') as f:f.write(json.dumps({'event':'START','sequence':'desk','label':label,'condition':condition,'unix':time.time()})+'\n')
    t=time.monotonic()
    with (out/'stdout.log').open('w') as log:
        try:r=subprocess.run(['/usr/bin/time','-v','-o',str(out/'resources.txt')]+cmd,env=env,cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=600);rec['exit']=r.returncode
        except subprocess.TimeoutExpired:rec['exit']='TIMEOUT'
    rec['elapsed_wall_s']=time.monotonic()-t
    if (out/'frame_states.csv').exists():
        z=list(csv.DictReader((out/'frame_states.csv').open()));rec['processed_frames']=len(z);rec['states']=dict(collections.Counter(x['state'] for x in z));rec['map_ids']=sorted({int(float(x['map_id'])) for x in z});rec['frame_identity_missing']=sum(float(x['N'])<0 for x in z);rec['multi_map_gauge_warning']=len(rec['map_ids'])>1
    for name,trajectory in [('exported','CameraTrajectory.txt'),('online','OnlineTrajectory.txt')]:
        try:
            target=out if name=='exported' else out/'online_eval_input'
            if name=='online':
                target.mkdir();(target/'CameraTrajectory.txt').symlink_to(out/trajectory);(target/'KeyFrameTrajectory.txt').symlink_to(out/'KeyFrameTrajectory.txt')
            ev=evaluate(d,target,out/'evaluation'/name)
            rows=[x.split() for x in (out/trajectory).read_text().splitlines() if x.strip()];stamps=[x[0] for x in rows]
            identity=len(stamps)==len(set(stamps)) and not rec.get('multi_map_gauge_warning',True)
            rec[name]={'ATE':ev['ate_m']['rmse'],'RPEt':ev['rpe_1s_translation_m'].get('rmse'),'RPEr':ev['rpe_1s_rotation_deg'].get('rmse'),'RPE_pairs':ev['rpe_1s_translation_m']['n'],'coverage':ev['saved_pose_fraction_of_input'],'identity_gauge_qualified':identity,'rows':len(rows),'unique_stamps':len(set(stamps))}
        except Exception as e:rec[name]={'evaluation_error':str(e)}
    (out/'run.json').write_text(json.dumps(rec,indent=2))
    with ledger.open('a') as f:f.write(json.dumps({'event':'END','sequence':'desk','label':label,'exit':rec['exit'],'elapsed_s':rec['elapsed_wall_s']})+'\n')
    print(json.dumps(rec),flush=True)
    if rec['exit']!=0 or rec.get('processed_frames')!=573 or any('evaluation_error' in rec[x] for x in ['online','exported']):raise SystemExit('Technical failure retained. Stop, no replacement run.')
if __name__=='__main__':
    frozen=json.loads((P/'protocol/design_frozen.json').read_text());assert frozen['maximum_new_runs']==4 and frozen['order']==ORDER
    for f,h in frozen['file_hashes'].items():assert sha(Path(f))==h,f
    assert not (P/'protocol/attempts.jsonl').exists(),'No automatic restart/resume of the run budget.'
    for label in ORDER:run(label)
