from pathlib import Path
import json,hashlib,subprocess,re,os
D=Path(__file__).resolve().parents[1];E=Path('/media/wcqw/KESU/slam_research/ngd_native_recovery_20261020');S=E/'NGD-SLAM';H=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
b=json.loads((D/'protocol/protection_before.json').read_text());G=lambda a:subprocess.check_output(['git','-C','/home/wcqw/ac-slam']+a).decode()
protection={'old_files_checked':len(b['files']),'old_files_equal':all(H(p)==h for p,h in b['files'].items()),'head_equal':G(['rev-parse','HEAD'])==b['head'],'status_equal':G(['status','--porcelain'])==b['status'],'diff_equal':hashlib.sha256(G(['diff']).encode()).hexdigest()==b['diff_sha256'],'scope':'five listed old reports/code files plus original main worktree HEAD/status/diff; not all historical data'}
assert all(protection[k] for k in ['old_files_equal','head_equal','status_equal','diff_equal'])
a=json.loads((D/'audit/source_acceptance.json').read_text());changed=[p for p,v in a['files'].items() if H(S/p)!=v['sha256']];assert not changed
for r in ['walking01','walking02']:
 p=D/'results'/r;text=(p/'stdout.log').read_text();run=json.loads((p/'run.json').read_text());res=(p/'resource.txt').read_text();frames=re.findall(r'^Frame (\d+) end$',text,re.M)
 row={'run':r,'exit_status_wrapper':run['exit_status'],'signal':11,'logged_completed_frame_calls':len(frames),'announced_inputs':827,'saved_camera_poses':0,'saved_input_pose_coverage':0.0,'ate_m':None,'rpe_1s_t_m':None,'rpe_1s_r_deg':None,'tracking_loss_frames':'UNKNOWN; no completed first call or per-frame state hooks','subsequent_map_reset':'not observed before crash; only map0 initialization logged','management_wall_seconds':run['wall_seconds']}
 for label,k in [('User time (seconds)','user_cpu_seconds'),('System time (seconds)','system_cpu_seconds'),('Maximum resident set size (kbytes)','peak_rss_kib')]:
  m=re.search(re.escape(label)+r':\s*([\d.]+)',res);row[k]=float(m.group(1))
 maps=(p/'runtime_opencv_maps.txt').read_text();assert 'libopencv_' in maps and '.so.4.2' not in maps
 row['runtime_opencv_only_isolated_455']=all(str(E/'opencv-install/lib') in l for l in maps.splitlines() if 'libopencv_' in l)
 (p/'result_summary.json').write_text(json.dumps(row,indent=2))
(D/'audit/protection_after.json').write_text(json.dumps(protection,indent=2))
summary={'status':'BASELINE_NOT_QUALIFIED','source_files_verified':len(a['files']),'author_source_changes':changed,'opencv':'4.5.5 isolated source build','native_cpp_build':'PASS','headless_entry_only_change':'viewer bool true to false','native_yolo_cpu_forward':'PASS','first_image_yolo_Detect_threads1':'PASS','real_sequence_launches':2,'complete_sequence_runs':0,'completed_frame_calls':0,'diagnostic_gdb_starts':2,'gdb_scope':'first attempt stopped at PLT/real entry before body; corrected attempt bounded to first body/second-call entry and caught SIGBUS in four-connected component parallel code','no_further_retry':True,'M1_M2':'NOT_DEVELOPED','runs':[json.loads((D/'results'/r/'result_summary.json').read_text()) for r in ['walking01','walking02']]}
(D/'results/summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({'source_files_unchanged':len(a['files']),'protection':protection,'status':summary['status']},indent=2))
