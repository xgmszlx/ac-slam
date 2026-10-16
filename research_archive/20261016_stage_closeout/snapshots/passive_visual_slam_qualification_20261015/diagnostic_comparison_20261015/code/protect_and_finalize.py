import pathlib,json,hashlib,subprocess,shutil,time
N=pathlib.Path(__file__).resolve().parents[1];O=N.parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before=json.loads((N/'audit/protection_before.json').read_text());manifest=json.loads((O/'MANIFEST.json').read_text());files={k:sha(O/k)==v['sha256'] for k,v in manifest.items()}
git=lambda *a:subprocess.check_output(['git','-C','/home/wcqw/ac-slam',*a],text=True)
after={'old_manifest_unchanged':before['old_manifest']==sha(O/'MANIFEST.json'),'old_manifest_files_checked':len(files),'old_manifest_files_equal':all(files.values()),'mismatches':[k for k,v in files.items() if not v],'main_HEAD_unchanged':before['git_head']==git('rev-parse','HEAD'),'main_status_unchanged':before['git_status']==git('status','--porcelain=v1'),'main_diff_unchanged':before['git_diff_sha']==hashlib.sha256(git('diff').encode()).hexdigest(),'main_HEAD':git('rev-parse','HEAD').strip(),'main_status':git('status','--porcelain=v1'),'disk_free_bytes':shutil.disk_usage(N).free,'frozen_core_sha256':sha(O/'sources/ORB_SLAM3-4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4/lib/libORB_SLAM3.so')}
assert all(after[k] for k in ['old_manifest_unchanged','old_manifest_files_equal','main_HEAD_unchanged','main_status_unchanged','main_diff_unchanged'])
assert after['frozen_core_sha256']=='a20db0416fc54ca5949e6b6ac834c12f59dc0bae5f08dc2945e46943a3532c46'
# No claims of pre/post equality for directories not snapshotted; check only modification-time evidence, explicitly bounded.
fence=(N/'audit/protection_before.json').stat().st_mtime
names=['active_slam_topic_audit_20261014','active_slam_ab_decision_20261014','active_map_author_validation','active_slam_next_direction_20261014','active_slam_b_final_qualification','active_slam_anchor_selection_20261014','active_slam_incremental_screen_20261014','active_slam_feedback_probe_20261014']
after['other_old_directories_mtime_only']={}
for name in names:
 d=O.parent/name
 if not d.exists():after['other_old_directories_mtime_only'][name]={'exists':False};continue
 recent=[];count=0
 for p in d.rglob('*'):
  if p.is_file() and not p.is_symlink():
   count+=1
   if p.stat().st_mtime>fence:recent.append(str(p.relative_to(d)))
 after['other_old_directories_mtime_only'][name]={'files_checked':count,'files_modified_since_fence':recent,'not_a_full_hash_snapshot':True}
(N/'audit/protection_after.json').write_text(json.dumps(after,indent=2))
ledger=[json.loads(l) for l in (N/'protocol/attempts.jsonl').read_text().splitlines()];starts=[r for r in ledger if r['event']=='start'];ends=[r for r in ledger if r['event']=='end'];assert len(starts)==len(ends)==6
(N/'protocol/attempts_final.json').write_text(json.dumps({'phase_B':{'walking_P0_new':2,'walking_P1':3,'sitting_P1':1,'all_native_exits_zero':all(r['exit']==0 for r in ends),'P0_02_export_identity_qualification':'FAIL, retained'},'phase_D':{'walking_P2':0,'sitting_P2':0,'status':'NOT_RUN_MASK_NOT_QUALIFIED'},'no_failed_run_retries':True,'no_ROS_or_training':True,'all_old_budgets_unchanged':True,'mask_download_stop':'bounded attempts exhausted; no additional retrieval','no_new_data':True},indent=2))
print(json.dumps(after,indent=2))
