from pathlib import Path
import json,hashlib,subprocess,datetime,shutil
D=Path(__file__).resolve().parents[1];O=Path('/home/wcqw/ngd_native_recovery_20261020');E=Path('/media/wcqw/KESU/slam_research/ngd_ccl_compat_20261020');P=Path('/media/wcqw/KESU/slam_research/ngd_native_recovery_20261020')
H=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert not (D/'protocol/plan.json').exists()
paths=[O/'REPORT.md',O/'results/summary.json',O/'results/walking01/run.json',O/'results/walking02/run.json',P/'NGD-SLAM/lib/libORB_SLAM3.so',P/'rgbd_tum_headless',P/'NGD-SLAM/Examples/RGB-D/rgbd_tum',P/'NGD-SLAM/src/YOLO.cc',Path('/home/wcqw/ac-slam/tools/realizability_pilot/same_input_replay.py'),Path('/home/wcqw/ac-slam/tools/realizability_pilot/se2_information.py')]
G=lambda a:subprocess.check_output(['git','-C','/home/wcqw/ac-slam']+a).decode()
(D/'protocol/protection_before.json').write_text(json.dumps({'files':{str(p):H(p) for p in paths},'head':G(['rev-parse','HEAD']),'status':G(['status','--porcelain']),'diff_sha256':hashlib.sha256(G(['diff']).encode()).hexdigest()},indent=2))
for p in [P/'NGD-SLAM/lib/libORB_SLAM3.so',P/'rgbd_tum_headless',P/'NGD-SLAM/Examples/RGB-D/rgbd_tum']:shutil.copy2(p,E/'original_binaries'/p.name)
plan={'registered_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),'opencv_issue':'https://github.com/opencv/opencv/issues/21366','opencv_dir':str(P/'opencv-install'),'repro_cases':['zero10','zero480','diag10','rects','tie','edge'],'algorithms':['default','sauf'],'threads':[1,4],'ccl_reference':'independent 4-neighbor BFS; compare canonical foreground partitions, maximal foreground masks, original largest-label/dilate/80%-clear output','actual_yolo_image_indices':[0,206,413,620,826],'actual_yolo_compare_threads':1,'runtime_threads':1,'patch_scope':'one YOLO.cc call gains cv::CCL_SAUF; connectivity4 and CV_32S unchanged','short_inputs':12,'full_sequence_budget':1,'if_new_crash':'capture exact bounded-prefix stack and stop further code changes','no_estimator_state_hooks':True}
(D/'protocol/plan.json').write_text(json.dumps(plan,indent=2))
shutil.copy2(O/'config/TUM3_BGR.yaml',D/'config/TUM3_BGR.yaml');shutil.copy2(O/'code/evaluate.py',D/'code/evaluate.py')
print('Registered; original binaries copied and hashed')
