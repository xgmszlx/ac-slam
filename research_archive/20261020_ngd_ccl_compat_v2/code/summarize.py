from pathlib import Path
import json,hashlib,subprocess,re,csv
import numpy as np
D=Path(__file__).resolve().parents[1];E=Path('/media/wcqw/KESU/slam_research/ngd_ccl_compat_v2_20261020');S=E/'NGD-SLAM';Q=Path('/home/wcqw/passive_visual_slam_qualification_20261015/data/rgbd_dataset_freiburg3_walking_xyz');H=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
b=json.loads((D/'protocol/protection_before.json').read_text());G=lambda a:subprocess.check_output(['git','-C','/home/wcqw/ac-slam']+a,text=True)
changed=[p for p,h in b['files'].items() if H(p)!=h]
prot={'protected_files':len(b['files']),'changed_old_files':changed,'main_head_equal':G(['rev-parse','HEAD'])==b['head'],'main_status_equal':G(['status','--porcelain'])==b['status'],'main_diff_equal':hashlib.sha256(G(['diff']).encode()).hexdigest()==b['diff_sha256']}
assert not changed and all(prot[x] for x in ['main_head_equal','main_status_equal','main_diff_equal'])
(D/'audit/protection_after.json').write_text(json.dumps(prot,indent=2))
short=json.loads((D/'results/short/result.json').read_text());run=json.loads((D/'results/full/result.json').read_text());assert short['exit_status']==0 and short['completed_frame_calls']==12
assert run['exit_status']==0 and run['completed_frame_calls']==827
m=json.loads((D/'evaluation/metrics.json').read_text());assert m['duplicate_saved_timestamps']==0 and m['nonincreasing_saved_time_steps']==0
log=(D/'results/full/stdout.log').read_text();resources=(D/'results/full/resource.txt').read_text()
pattern=r'^Frame (\d+) end$';ids=[int(x) for x in re.findall(pattern,log,re.M)];assert ids==list(range(827))
resources_values={}
for key in ['User time (seconds)','System time (seconds)','Maximum resident set size (kbytes)','Elapsed (wall clock) time (h:mm:ss or m:ss)']:
 match=re.search(r'^\s*'+re.escape(key)+r': (.+)$',resources,re.M)
 resources_values[key]=match.group(1) if match else None
interesting=[l for l in log.splitlines() if re.search(r'map|reset|lost|relocal|initial|points',l,re.I)]
(D/'results/map_and_tracking_messages.txt').write_text('\n'.join(interesting)+'\n')
final_times={}
for name in ['median','mean']:
 t=re.search(name+r' tracking time: ([\d.eE+-]+)',log);final_times[name+'_TrackRGBD_seconds']=float(t.group(1)) if t else None
maps=[l for l in interesting if re.search('Creation of new map|First KF',l)]
summary={'label':'NGD-M0-compat-v2','status':'BASELINE_TECHNICAL_PASS_SINGLE_SEQUENCE','source_commit':'a93a14c4019efc7a209be5fbf9fefa46f5d1d90f','author_changed_files':['src/Tracking.cc','src/YOLO.cc'],'short_completed':12,'full_completed':827,'exit_status':run['exit_status'],'online_ATE':'UNAVAILABLE: unchanged entry records no online poses','exported_ATE_m':m['ate_m']['rmse'],'RPE_1s_translation_m':m['rpe_1s_translation_m'].get('rmse'),'RPE_1s_rotation_deg':m['rpe_1s_rotation_deg'].get('rmse'),'exported_pose_coverage':m['saved_pose_fraction_of_input'],'camera_poses':m['saved_camera_poses'],'keyframes':m['saved_keyframes'],'GT_pairs':m['saved_poses_with_gt'],'management_wall_s':run['wall_seconds'],'resources':resources_values,'tracking_times':final_times,'frame_ids_contiguous_0_826':True,'map_creation_messages':maps,'per_frame_state':'NOT_RECORDED; output presence is not state OK','map_state_boundary':'native messages and trajectory timestamps only; no map-ID-per-pose export','shutdown_boundary':'author Shutdown requests finishes but does not wait for all workers; no changes, not certified fully converged BA','new_algorithms':0}
(D/'results/summary.json').write_text(json.dumps(summary,indent=2))
# Preserve descriptive reference runs, never call this a matched implementation comparison.
p=Path('/home/wcqw/passive_visual_slam_qualification_20261015/diagnostic_comparison_20261015/results/summary.csv')
old=[r for r in csv.DictReader(p.open()) if r['sequence']=='walking' and r['tag'].startswith('P1')]
rows=[{'system':'ORB-SLAM3 P1 historical '+r['tag'],'exported_ATE_m':r['ATE'],'RPEt_1s_m':r['RPEt'],'RPEr_1s_deg':r['RPEr'],'online_ATE_m':r['online_ATE'],'coverage':r['coverage'],'wall_s':r['wall_s'],'RSS_KiB':r['max_rss_kib']} for r in old]
rows.append({'system':'NGD-M0-compat-v2 single run','exported_ATE_m':summary['exported_ATE_m'],'RPEt_1s_m':summary['RPE_1s_translation_m'],'RPEr_1s_deg':summary['RPE_1s_rotation_deg'],'online_ATE_m':'UNAVAILABLE','coverage':summary['exported_pose_coverage'],'wall_s':summary['management_wall_s'],'RSS_KiB':resources_values['Maximum resident set size (kbytes)']})
with (D/'results/descriptive_comparison.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
print(json.dumps(summary,indent=2))
