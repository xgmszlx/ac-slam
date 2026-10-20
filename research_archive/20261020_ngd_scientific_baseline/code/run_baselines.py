from pathlib import Path
import json,hashlib,subprocess,os,time,signal,resource,shutil,re
from datetime import datetime,timezone
D=Path(__file__).resolve().parents[1];V=Path('/home/wcqw/ngd_ccl_compat_v2_20261020');E=Path('/media/wcqw/KESU/slam_research/ngd_ccl_compat_v2_20261020');P=E.parent/'ngd_native_recovery_20261020';S=E/'NGD-SLAM';T=Path('/home/wcqw/passive_visual_slam_qualification_20261015/data');B=Path('/home/wcqw/passive_rgbd_combo_20261019/e2e_20261020/data/rgbd_bonn_moving_obstructing_box');H=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert not (D/'protocol/design_frozen.json').exists()
shutil.copy2(V/'config/TUM3_BGR.yaml',D/'config/TUM3_BGR.yaml');shutil.copy2('/home/wcqw/passive_rgbd_combo_20261019/e2e_20261020/config/bonn.yaml',D/'config/bonn.yaml');shutil.copy2(V/'code/evaluate.py',D/'code/evaluate.py')
conditions=[('M0_02',T/'rgbd_dataset_freiburg3_walking_xyz','TUM3_BGR.yaml',827),('M0_03',T/'rgbd_dataset_freiburg3_walking_xyz','TUM3_BGR.yaml',827),('M0_04',T/'rgbd_dataset_freiburg3_sitting_xyz','TUM3_BGR.yaml',1219),('M0_05',B,'bonn.yaml',None)]
files={}
for root in [V]:
 for f in root.rglob('*'):
  if f.is_file():files[str(f)]=H(f)
for f in [E/'lib/libORB_SLAM3.so',E/'rgbd_tum_headless',S/'src/Tracking.cc',S/'src/YOLO.cc',P/'NGD-SLAM/Vocabulary/ORBvoc.txt']:files[str(f)]=H(f)
G=lambda a:subprocess.check_output(['git','-C','/home/wcqw/ac-slam']+a,text=True)
(D/'protocol/protection_before.json').write_text(json.dumps({'files':files,'head':G(['rev-parse','HEAD']),'status':G(['status','--porcelain']),'diff_sha256':hashlib.sha256(G(['diff']).encode()).hexdigest()},indent=2))
items=[]
for tag,q,c,n in conditions:
 rows=[l.split() for l in (q/'associations.txt').read_text().splitlines() if l.strip() and not l.startswith('#')];n=len(rows) if n is None else n;assert len(rows)==n
 for row in rows:assert (q/row[1]).is_file() and (q/row[3]).is_file()
 stamps=[float(x[0]) for x in rows];assert all(y>x for x,y in zip(stamps,stamps[1:]))
 items.append({'tag':tag,'sequence':str(q),'config':str(D/'config'/c),'input_frames':n,'association_sha256':H(q/'associations.txt'),'config_sha256':H(D/'config'/c),'GT_sha256_offline_only':H(q/'groundtruth.txt')})
plan={'parent_commit':'92156b25a671cce73d0f8055c1953af94ab54a0f','label':'NGD-M0-compat-v2','new_full_run_budget':4,'order':items,'method_changed':False,'binary_sha256':H(E/'rgbd_tum_headless'),'core_sha256':H(E/'lib/libORB_SLAM3.so'),'eval_sha256':H(D/'code/evaluate.py'),'source_sha256':{k:H(S/'src'/k) for k in ['Tracking.cc','YOLO.cc']},'threads':1,'evaluation':'same existing SE3 scale1,20ms GT unique pairing,1s +/-20ms RPE and no >100ms internal gap','new_logs':'no hooks/rebuild; unavailable internal events remain UNKNOWN','on_failure':'record exit and completed inputs; no retries/no algorithm modifications','statistical_policy':'three walking trials report range/median only, no significance or per-frame independent-repeat claims'}
(D/'protocol/design_frozen.json').write_text(json.dumps(plan,indent=2))
env=os.environ.copy();env['PATH']='/usr/bin:/bin';env['OPENCV_FOR_THREADS_NUM']='1';env['TMPDIR']=str(E/'tmp');env['LD_LIBRARY_PATH']=':'.join(map(str,[E/'lib',P/'opencv-install/lib',P/'NGD-SLAM/Thirdparty/DBoW2/lib',P/'NGD-SLAM/Thirdparty/g2o/lib',Path('/home/wcqw/passive_visual_slam_qualification_20261015/local/lib')]))
for item in items:
 tag=item['tag'];q=Path(item['sequence']);R=D/'results'/tag;assert not R.exists();R.mkdir()
 for name in ['CameraTrajectory.txt','KeyFrameTrajectory.txt']:assert not (S/name).exists()
 assert H(E/'rgbd_tum_headless')==plan['binary_sha256'] and H(E/'lib/libORB_SLAM3.so')==plan['core_sha256']
 cmd=['/usr/bin/time','-v','-o',str(R/'resource.txt'),str(E/'rgbd_tum_headless'),str(P/'NGD-SLAM/Vocabulary/ORBvoc.txt'),item['config'],str(q),str(q/'associations.txt')]
 (R/'frozen.json').write_text(json.dumps({'item':item,'command':cmd,'cwd':str(S),'env_specific':{k:env[k] for k in ['OPENCV_FOR_THREADS_NUM','TMPDIR','LD_LIBRARY_PATH']},'started':datetime.now(timezone.utc).isoformat()},indent=2))
 ldd=subprocess.check_output(['/usr/bin/ldd',str(E/'rgbd_tum_headless')],env=env,text=True);assert str(E/'lib/libORB_SLAM3.so') in ldd and '.so.4.2' not in ldd;(R/'ldd.txt').write_text(ldd)
 start=time.monotonic();saved=False;timedout=False
 with (R/'stdout.log').open('w') as log:
  p=subprocess.Popen(cmd,cwd=S,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
  while p.poll() is None:
   if not saved and time.monotonic()-start>2:
    try:
     for kid in Path(f'/proc/{p.pid}/task/{p.pid}/children').read_text().split():
      maps=Path(f'/proc/{kid}/maps').read_text()
      if 'libopencv_' in maps:(R/'runtime_libraries.txt').write_text('\n'.join(l for l in maps.splitlines() if 'libopencv_' in l or 'libORB_SLAM3' in l)+'\n');saved=True
    except (OSError,PermissionError):pass
   if time.monotonic()-start>600:timedout=True;os.killpg(p.pid,signal.SIGTERM);break
   time.sleep(.25)
  try:p.wait(timeout=10)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
 elapsed=time.monotonic()-start;log=(R/'stdout.log').read_text();ids=list(map(int,re.findall(r'^Frame (\d+) end$',log,re.M)))
 result={'tag':tag,'label':'NGD-M0-compat-v2','sequence':str(q),'inputs':item['input_frames'],'exit_status':p.returncode,'completed_frame_calls':len(ids),'frame_ids':ids,'wall_s':elapsed,'timed_out':timedout,'GT_online':False,'online_poses':'not recorded by unchanged entry'}
 for name in ['CameraTrajectory.txt','KeyFrameTrajectory.txt']:
  if (S/name).exists():shutil.move(str(S/name),str(R/name))
 (R/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='frame_ids'}),flush=True)
 if p.returncode==0 and len(ids)==item['input_frames'] and (R/'CameraTrajectory.txt').is_file():
  with (R/'evaluation.log').open('w') as out:
   ev=subprocess.run([os.sys.executable,str(D/'code/evaluate.py'),str(q),str(R),str(R/'evaluation')],stdout=out,stderr=subprocess.STDOUT)
  print(tag,'evaluation exit',ev.returncode,flush=True)
(D/'protocol/attempts_final.json').write_text(json.dumps({'used':4,'budget':4,'new_algorithm_runs':0,'automatic_repeats':0},indent=2))
