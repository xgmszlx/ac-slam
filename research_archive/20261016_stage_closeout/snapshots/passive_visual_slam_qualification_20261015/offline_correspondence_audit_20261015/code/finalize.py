import pathlib,json,hashlib,subprocess,ast,re,os,shutil
N=pathlib.Path(__file__).resolve().parents[1];before=json.loads((N/'audit/protection_before.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();checks=[]
for old in before['manifests']:
 b=pathlib.Path(old['directory']);m=json.loads((b/'MANIFEST.json').read_text());bad=[k for k,v in m.items() if sha(b/k)!=v['sha256']];assert not bad;checks.append({'directory':str(b),'files_checked':len(m),'mismatches':bad,'manifest_equal':sha(b/'MANIFEST.json')==old['manifest_sha']})
git=lambda *a:subprocess.check_output(['git','-C','/home/wcqw/ac-slam',*a],text=True)
r={'old_manifests':checks,'main_HEAD_equal':git('rev-parse','HEAD')==before['HEAD'],'main_status_equal':git('status','--porcelain=v1')==before['status'],'main_diff_equal':hashlib.sha256(git('diff').encode()).hexdigest()==before['diff_sha'],'main_HEAD':git('rev-parse','HEAD').strip(),'main_status':git('status','--porcelain=v1'),'free_bytes':shutil.disk_usage(N).free}
assert all(r[k] for k in ['main_HEAD_equal','main_status_equal','main_diff_equal'])
d=json.loads((N/'protocol/design_v02.json').read_text());data=N.parent/'data/rgbd_dataset_freiburg3_walking_xyz';fs={f['index']:f for q in d['pairs'] for f in q['frames']};r['selected_RGB_depth_files_hash_equal']=all(sha(data/f[typ])==f[typ+'_sha256'] for f in fs.values() for typ in ['rgb','depth']);assert r['selected_RGB_depth_files_hash_equal'];r['selected_frames']=len(fs)
frozen=json.loads((N/'protocol/annotation_frozen_v02.json').read_text());r['annotation_frozen_hash_equal']=sha(N/'annotations/manual_person_v02.json')==frozen['sha256'];assert r['annotation_frozen_hash_equal'];ex=json.loads((N/'audit/execution.json').read_text());r['matching_design_hash_equal']=sha(N/'protocol/design_v02.json')==ex['design_sha256'];assert r['matching_design_hash_equal']
(N/'audit/protection_after.json').write_text(json.dumps(r,indent=2))
syntax=[]
for f in list((N/'code').glob('*.py'))+list((N/'tests').glob('*.py')):ast.parse(f.read_text());syntax.append(str(f.relative_to(N)))
(N/'audit/syntax.json').write_text(json.dumps({'PASS':True,'files':syntax},indent=2))
missing=[t for t in re.findall(r'\]\(([^)]+)\)',(N/'REPORT.md').read_text()) if not t.startswith(('http:','https:')) and not (N/t).exists() and t!='MANIFEST.json'];assert not missing,missing
(N/'protocol/budget_final.json').write_text(json.dumps({'label':'OFFLINE_DIAGNOSTIC','frozen_pairs':9,'selected_frames':18,'additional_pairs':0,'new_SLAM_runs':0,'new_data_or_weights':0,'training_or_compilation':0,'ROS_or_simulator':0,'no_threshold_tuning':True,'manual_labels_never_passed_to_SLAM':True,'stop':'insufficient evidence for actual SLAM causal attribution; no further method experiment'},indent=2))
print(json.dumps(r,indent=2))
