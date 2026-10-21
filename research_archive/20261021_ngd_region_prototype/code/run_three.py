from pathlib import Path
import os,json,hashlib,subprocess,time,signal,resource,sys,re
from datetime import datetime
from zoneinfo import ZoneInfo
D=Path(__file__).resolve().parents[1];E=Path('/media/wcqw/KESU/slam_research/ngd_region_prototype_20261021');S=E/'NGD-SLAM';P=E.parent/'ngd_native_recovery_20261020';Q=Path('/home/wcqw/passive_rgbd_combo_20261019/e2e_20261020/data/rgbd_bonn_moving_obstructing_box');H=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert not (D/'protocol/design_frozen.json').exists();assert 'ALL_TESTS_PASS' in (D/'audit/unit_tests_final.log').read_text()
files=[E/'rgbd_region',E/'lib/libORB_SLAM3.so',D/'config/bonn.yaml',D/'code/evaluate.py',D/'code/run_three.py',Q/'associations.txt',Q/'groundtruth.txt']+list((D/'code').glob('*.cc'))+list((D/'code').glob('*.h'))+[S/'src'/n for n in ['Tracking.cc','Frame.cc','ORBmatcher.cc','Optimizer.cc','RegionExpansion.cc','YOLO.cc']]+[S/'include/RegionExpansion.h']
params={'grid':4,'max_regions':4,'min_pixels':64,'max_region_fraction':.35,'max_extra_fraction':.45,'max_union_fraction':.8,'depth_gate_m':.3,'min_depth_m':.05,'LK_FB_px':1.5,'grid_sampling_px':15,'max_points':400,'previous_dt_max_s':.2,'previous_map_observations_min':3,'previous_state':2,'bg_PnP_iterations':100,'bg_PnP_px':5,'bg_PnP_confidence':.99,'bg_inliers_min':20,'bg_cells_min':4,'bg_grid':'8x6','fit_gate_m':.05,'motion_gain_m':.05,'min_pairs':18,'min_train_inliers':8,'min_validation':6,'train_validation_split':'index%3==0 heldout; remaining train','validation_required_fraction':.8,'min_second_singular_ratio':.02,'min_3D_RMS_spread_m':.02,'sample_triplet_spread_m':.005,'sample_triplet_singular_ratio':.01,'min_holdout_pixel_span':20,'min_holdout_20px_cells':4,'RANSAC_iterations':100,'SVD_RANSAC_seed':1729,'bg_PnP_seed':73,'native_CV_RNG':'save and restore','max_heldout_occlusion_fraction':1/3,'3x3_depth_valid_neighbors_min':5,'visibility_depth_tolerance_m':.05}
plan={'parent_commit':'7ec1810143f78a394d5bd2868cca4d60c3eef9d2','registered_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'sequence':str(Q),'input_frames':589,'order':['M0','M1','M2'],'run_budget':3,'automatic_retries':0,'common_binary':str(E/'rgbd_region'),'mode_values':{'M0':0,'M1':1,'M2':2},'mode0_calls_algorithm_helper':False,'parameters':params,'hashes':{str(p):H(p) for p in files},'GT_online':False,'candidate_pairing':'same Generate function and parameters, equality verified for identical inputs; native per-run mask/history/async timing can differ; log hashes, no claim of exact counterfactual pool equality','pacing':'same prior headless timestamp wait; source original TrackRGBD and no-viewer constructor','common_diagnostics':'buffered online pose, public state, actual pre-mask feature decisions, pose-optimization counters; no estimator formula changes','source_risks_unfixed':['ComputePixelPotential counters','roll expression','80 percent clearing','empty pointsDepth median','native asynchronous shutdown'],'evaluation':'prior scale1 SE3; unique20ms GT pairing;1s +/-20ms RPE, no >100ms internal output gap; online only OK set finite poses, exported independent'}
(D/'protocol/design_frozen.json').write_text(json.dumps(plan,indent=2));env=os.environ.copy();env['PATH']='/usr/bin:/bin';env['OPENCV_FOR_THREADS_NUM']='1';env['TMPDIR']=str(E/'tmp');env['LD_LIBRARY_PATH']=':'.join(map(str,[E/'lib',P/'opencv-install/lib',P/'NGD-SLAM/Thirdparty/DBoW2/lib',P/'NGD-SLAM/Thirdparty/g2o/lib',Path('/home/wcqw/passive_visual_slam_qualification_20261015/local/lib')]))
for mode,tag in enumerate(plan['order']):
 for p,h in plan['hashes'].items():assert H(p)==h,p
 R=D/'results'/tag;assert not R.exists();R.mkdir();cmd=['/usr/bin/time','-v','-o',str(R/'resource.txt'),str(E/'rgbd_region'),str(P/'NGD-SLAM/Vocabulary/ORBvoc.txt'),str(D/'config/bonn.yaml'),str(Q),str(Q/'associations.txt'),str(mode),str(R)]
 (R/'started.json').write_text(json.dumps({'tag':tag,'mode':mode,'cmd':cmd,'cwd':str(S),'env_specific':{k:env[k] for k in ['LD_LIBRARY_PATH','OPENCV_FOR_THREADS_NUM','TMPDIR']},'started_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()},indent=2))
 ldd=subprocess.check_output(['/usr/bin/ldd',str(E/'rgbd_region')],env=env,text=True);assert str(E/'lib/libORB_SLAM3.so') in ldd and '.so.4.2' not in ldd;(R/'ldd.txt').write_text(ldd)
 start=time.monotonic();saved=False;timeout=False
 with (R/'stdout.log').open('w') as log:
  proc=subprocess.Popen(cmd,cwd=S,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
  while proc.poll() is None:
   if not saved and time.monotonic()-start>2:
    try:
     for kid in Path(f'/proc/{proc.pid}/task/{proc.pid}/children').read_text().split():
      maps=Path(f'/proc/{kid}/maps').read_text()
      if 'libopencv_' in maps:(R/'runtime_libraries.txt').write_text('\n'.join(x for x in maps.splitlines() if 'libopencv_' in x or 'libORB_SLAM3' in x)+'\n');saved=True
    except OSError:pass
   if time.monotonic()-start>600:timeout=True;os.killpg(proc.pid,signal.SIGTERM);break
   time.sleep(.3)
  try:proc.wait(timeout=10)
  except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
 text=(R/'stdout.log').read_text();n=len(re.findall(r'^Frame \d+ end$',text,re.M));result={'condition':tag,'mode':mode,'exit_status':proc.returncode,'completed_calls':n,'inputs':589,'entry_completed_marker':'REGION_COMPLETED_INPUTS 589' in text,'timedout':timeout,'wall_s':time.monotonic()-start,'GT_online':False}
 (R/'run.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
 if proc.returncode==0 and n==589 and result['entry_completed_marker']:
  for typ in ['exported','online']:
   input_dir=R
   if typ=='online':
    input_dir=R/'online_input';input_dir.mkdir();(input_dir/'CameraTrajectory.txt').symlink_to(R/'OnlineTrajectory.txt');(input_dir/'KeyFrameTrajectory.txt').symlink_to(R/'KeyFrameTrajectory.txt');(input_dir/'run.json').symlink_to(R/'run.json')
   with (R/(typ+'_evaluation.log')).open('w') as log:ev=subprocess.run([sys.executable,str(D/'code/evaluate.py'),str(Q),str(input_dir),str(R/'evaluation'/typ)],stdout=log,stderr=subprocess.STDOUT)
   print(tag,typ,'evaluation',ev.returncode,flush=True)
(D/'protocol/attempts_final.json').write_text(json.dumps({'used':3,'budget':3,'conditions':plan['order'],'automatic_retries':0,'additional_sequences':0},indent=2))
