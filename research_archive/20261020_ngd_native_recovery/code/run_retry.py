"""One headless author-baseline run; no logging hooks or estimator modification."""
from pathlib import Path
import hashlib,json,os,subprocess,time,signal,resource
from datetime import datetime, timezone, timedelta
D=Path(__file__).resolve().parents[1];E=Path('/media/wcqw/KESU/slam_research/ngd_native_recovery_20261020');S=E/'NGD-SLAM';R=D/'results/walking02';R.mkdir(parents=True,exist_ok=False)
H=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
source=json.loads((D/'audit/source_acceptance.json').read_text())
assert all(H(S/p)==r['sha256'] for p,r in source['files'].items())
subprocess.run(['/usr/bin/python3',str(D/'code/linkage.py')],check=True)
info=json.loads((D/'audit/walking_input.json').read_text());Q=Path(info['sequence'])
assert H(Q/'associations.txt')==info['association_sha256']
assert H(Q/'groundtruth.txt')==info['gt_sha256']
assert all(not (S/p).exists() for p in ['CameraTrajectory.txt','KeyFrameTrajectory.txt'])
cmd=['/usr/bin/time','-v','-o',str(R/'resource.txt'),str(E/'rgbd_tum_headless'),str(S/'Vocabulary/ORBvoc.txt'),str(D/'config/TUM3_BGR.yaml'),str(Q),str(Q/'associations.txt')]
env=os.environ.copy();env['OPENCV_FOR_THREADS_NUM']='1';env['PATH']='/usr/bin:/bin';env['TMPDIR']=str(E/'tmp');env['LD_LIBRARY_PATH']=':'.join(map(str,[E/'opencv-install/lib',S/'lib',S/'Thirdparty/DBoW2/lib',S/'Thirdparty/g2o/lib',Path('/home/wcqw/passive_visual_slam_qualification_20261015/local/lib')]))
tracked=[E/'rgbd_tum_headless',S/'lib/libORB_SLAM3.so',S/'Examples/RGB-D/rgbd_tum',S/'Thirdparty/YOLO/yolo-fastest-xl.cfg',S/'Thirdparty/YOLO/yolo-fastest-xl.weights',S/'Vocabulary/ORBvoc.txt',D/'config/TUM3_BGR.yaml',D/'code/evaluate.py']
frozen={'new_run_budget':1,'runtime_threads':1,'amendment':'thread_runtime_amendment.json','run_order':['walking02'],'command':cmd,'cwd':str(S),'input_frames':827,'source_commit':'a93a14c4019efc7a209be5fbf9fefa46f5d1d90f','hashes':{str(p):H(p) for p in tracked},'entry':'author rgbd_tum with only viewer bool false; no logging hooks','evaluator':'existing SE3 scale1/1s RPE/20ms GT matching/100ms gap exclusion','frozen_at':datetime.now(timezone(timedelta(hours=8))).isoformat()}
(D/'protocol/retry_run_frozen.json').write_text(json.dumps(frozen,indent=2))
(R/'started.json').write_text(json.dumps({'command':cmd,'time':frozen['frozen_at']},indent=2))
def no_core():resource.setrlimit(resource.RLIMIT_CORE,(0,0))
start=time.monotonic();timedout=False
with (R/'stdout.log').open('w') as log:
 p=subprocess.Popen(cmd,cwd=S,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=no_core)
 recorded=False
 while p.poll() is None:
  if not recorded and time.monotonic()-start>2:
   children=Path('/proc')/str(p.pid)/'task'/str(p.pid)/'children'
   if children.exists():
    for pid in children.read_text().split():
     try:
      m=Path('/proc')/pid/'maps';maps=m.read_text()
      if 'libopencv_' in maps:(R/'runtime_opencv_maps.txt').write_text('\n'.join(l for l in maps.splitlines() if 'libopencv_' in l)+'\n');recorded=True
     except (FileNotFoundError,PermissionError):pass
  if time.monotonic()-start>600:timedout=True;os.killpg(p.pid,signal.SIGTERM);break
  time.sleep(.5)
 try:p.wait(timeout=10)
 except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
result={'command':cmd,'cwd':str(S),'exit_status':p.returncode,'timed_out':timedout,'wall_seconds':time.monotonic()-start,'finished_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),'gt_online':False,'notes':'native estimator; viewer-disabled copied author example, no state/mask/constraint hooks'}
for name in ['CameraTrajectory.txt','KeyFrameTrajectory.txt']:
 if (S/name).exists():(R/name).write_bytes((S/name).read_bytes())
(R/'run.json').write_text(json.dumps(result,indent=2));(D/'protocol/attempts_retry_final.json').write_text(json.dumps({'budget':1,'used':1,'remaining':0,'runs':[result]},indent=2))
print(json.dumps(result,indent=2))
