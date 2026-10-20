"""Unique per-stage immutable registration; short12 then exactly one full run."""
from pathlib import Path
import json,hashlib,subprocess,time,os,signal,resource,sys,shutil
from datetime import datetime,timezone,timedelta
D=Path(__file__).resolve().parents[1];E=Path('/media/wcqw/KESU/slam_research/ngd_ccl_compat_20261020');P=Path('/media/wcqw/KESU/slam_research/ngd_native_recovery_20261020');S=E/'NGD-SLAM';Q=Path('/home/wcqw/passive_visual_slam_qualification_20261015/data/rgbd_dataset_freiburg3_walking_xyz');H=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
stage=sys.argv[1];assert stage in ['short','full'];R=D/'results'/stage
assert not R.exists(),'No overwrites or automatic retries'
mask=json.loads((D/'results/real_mask_comparison.json').read_text());assert all(x['compat_returncode']==0 for x in mask)
if stage=='full':
 previous=json.loads((D/'results/short/result.json').read_text());assert previous['exit_status']==0 and previous['completed_frame_calls']==12
R.mkdir();rows=(Q/'associations.txt').read_text().splitlines();assoc=Q/'associations.txt';n=827
if stage=='short':
 n=12;assoc=R/'associations_first12.txt';assoc.write_text('\n'.join(rows[:12])+'\n')
for name in ['CameraTrajectory.txt','KeyFrameTrajectory.txt']:assert not (S/name).exists()
env=os.environ.copy();env['PATH']='/usr/bin:/bin';env['OPENCV_FOR_THREADS_NUM']='1';env['TMPDIR']=str(E/'tmp');env['LD_LIBRARY_PATH']=':'.join(map(str,[E/'lib',P/'opencv-install/lib',P/'NGD-SLAM/Thirdparty/DBoW2/lib',P/'NGD-SLAM/Thirdparty/g2o/lib',Path('/home/wcqw/passive_visual_slam_qualification_20261015/local/lib')]))
cmd=['/usr/bin/time','-v','-o',str(R/'resource.txt'),str(E/'rgbd_tum_headless'),str(P/'NGD-SLAM/Vocabulary/ORBvoc.txt'),str(D/'config/TUM3_BGR.yaml'),str(Q),str(assoc)]
freeze={'stage':stage,'label':'NGD-M0-compat','source_commit':'a93a14c4019efc7a209be5fbf9fefa46f5d1d90f','inputs':n,'command':cmd,'cwd':str(S),'runtime_threads':1,'hashes':{str(p):H(p) for p in [E/'rgbd_tum_headless',E/'lib/libORB_SLAM3.so',S/'src/YOLO.cc',D/'config/TUM3_BGR.yaml',assoc,D/'code/evaluate.py']},'gt_sha256_offline_only':H(Q/'groundtruth.txt'),'registered_at':datetime.now(timezone(timedelta(hours=8))).isoformat()}
(R/'frozen.json').write_text(json.dumps(freeze,indent=2));(R/'started.json').write_text(json.dumps({'command':cmd,'stage':stage},indent=2))
ldd=subprocess.check_output(['/usr/bin/ldd',str(E/'rgbd_tum_headless')],env=env).decode();assert str(E/'lib/libORB_SLAM3.so') in ldd and '.so.4.2' not in ldd;(R/'ldd.txt').write_text(ldd)
start=time.monotonic();timedout=False;limit=120 if stage=='short' else 600
with (R/'stdout.log').open('w') as log:
 p=subprocess.Popen(cmd,cwd=S,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
 saved=False
 while p.poll() is None:
  if not saved and time.monotonic()-start>2:
   kids=Path(f'/proc/{p.pid}/task/{p.pid}/children')
   if kids.exists():
    for kid in kids.read_text().split():
     try:
      maps=Path(f'/proc/{kid}/maps').read_text()
      if 'libopencv_' in maps:(R/'runtime_libraries.txt').write_text('\n'.join(l for l in maps.splitlines() if 'libopencv_' in l or 'libORB_SLAM3' in l)+'\n');saved=True
     except (FileNotFoundError,PermissionError):pass
  if time.monotonic()-start>limit:timedout=True;os.killpg(p.pid,signal.SIGTERM);break
  time.sleep(.25)
 try:p.wait(timeout=10)
 except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
text=(R/'stdout.log').read_text();import re
result={'stage':stage,'label':'NGD-M0-compat','command':cmd,'exit_status':p.returncode,'timed_out':timedout,'wall_seconds':time.monotonic()-start,'completed_frame_calls':len(re.findall(r'^Frame \d+ end$',text,re.M)),'input_frames':n,'finished_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),'gt_online':False}
for name in ['CameraTrajectory.txt','KeyFrameTrajectory.txt']:
 if (S/name).exists():shutil.move(str(S/name),str(R/name))
(R/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
