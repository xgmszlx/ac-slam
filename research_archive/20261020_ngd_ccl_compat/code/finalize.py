from pathlib import Path
import json,hashlib,subprocess,re
D=Path(__file__).resolve().parents[1];E=Path('/media/wcqw/KESU/slam_research/ngd_ccl_compat_20261020');P=Path('/media/wcqw/KESU/slam_research/ngd_native_recovery_20261020');O=Path('/home/wcqw/ngd_native_recovery_20261020');H=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
b=json.loads((D/'protocol/protection_before.json').read_text());G=lambda a:subprocess.check_output(['git','-C','/home/wcqw/ac-slam']+a).decode()
r={'protected_files':len(b['files']),'files_equal':all(H(p)==h for p,h in b['files'].items()),'main_head_equal':G(['rev-parse','HEAD'])==b['head'],'main_status_equal':G(['status','--porcelain'])==b['status'],'main_diff_equal':hashlib.sha256(G(['diff']).encode()).hexdigest()==b['diff_sha256']}
assert all(r[k] for k in ['files_equal','main_head_equal','main_status_equal','main_diff_equal'])
a=json.loads((O/'audit/source_acceptance.json').read_text());oldbad=[p for p,v in a['files'].items() if H(P/'NGD-SLAM'/p)!=v['sha256']];assert not oldbad
changed=[p for p,v in a['files'].items() if H(E/'NGD-SLAM'/p)!=v['sha256']];assert changed==['src/YOLO.cc']
r['old_author_files_checked']=len(a['files']);r['old_author_files_unchanged']=True;r['new_source_changes']=changed
(D/'audit/protection_after.json').write_text(json.dumps(r,indent=2))
t=json.loads((D/'results/ccl_tests.json').read_text());m=json.loads((D/'results/real_mask_comparison.json').read_text());s=json.loads((D/'results/short/result.json').read_text());g=(D/'audit/compat_short_gdb.log').read_text()
assert all(x['returncode']==0 and x['geometry']['partition_equal_bfs'] for x in t['tests'] if x['algorithm']=='sauf')
assert all(all(x[k] for k in ['partition','max','final']) for x in t['successful_default_vs_sauf'])
assert all(x['final_masks_equal'] for x in m);assert s['completed_frame_calls']==2 and s['exit_status']==139
assert 'Thread 1 "rgbd_tum_headle" received signal SIGSEGV' in g and 'Tracking::CreateMaskFromClusters' in g
assert not (D/'results/full').exists()
summary={'label':'NGD-M0-compat','status':'BASELINE_NOT_QUALIFIED','issue_21366_reproduced':True,'primitive_tests':len(t['tests']),'default_crashes':sum(x['returncode']<0 for x in t['tests'] if x['algorithm']=='default'),'sauf_passes':sum(x['returncode']==0 for x in t['tests'] if x['algorithm']=='sauf'),'successful_pair_comparisons':len(t['successful_default_vs_sauf']),'real_mask_pairs':len(m),'real_mask_different_pixels':sum(x['different_pixels'] for x in m),'first_trackrgbd_pass':True,'short_input_frames':12,'short_completed_frames':2,'short_exit_status':139,'new_fault_thread':'main/thread1','new_fault_stack':'LabelingBolelli4C -> connectedComponentsWithStats -> Tracking::CreateMaskFromClusters -> PredictCurrentMask -> GrabImageRGBD','first_relevant_source_call':'src/Tracking.cc:4565 (unique call in stack-named function; release binary has no source line debug info)','changed_author_files':changed,'full_walking_runs':0,'ATE':None,'RPE':None,'trajectory_coverage':'NOT_AVAILABLE; no trajectory exported, no extrapolated partial metric','new_algorithms':0,'next_action':'Only consider the same explicitly selected 4-connected SAUF compatibility policy at Tracking.cc:4565 in a separately scoped next step; no current additional code change'}
(D/'results/summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
