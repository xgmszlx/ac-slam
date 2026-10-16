import pathlib,json,hashlib,subprocess,ast,os,shutil
N=pathlib.Path(__file__).resolve().parents[1];O=N.parent;D=O/'diagnostic_comparison_20261015';S=O/'sources/ORB_SLAM3-4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before=json.loads((N/'audit/protection_before.json').read_text());old=[]
for base in [O,D]:
 m=json.loads((base/'MANIFEST.json').read_text());bad=[k for k,v in m.items() if sha(base/k)!=v['sha256']];assert not bad;old.append({'directory':str(base),'manifest_unchanged':sha(base/'MANIFEST.json')==before['old_manifests'][str(base)]['manifest_sha256'],'files_checked':len(m),'mismatches':bad})
git=lambda *a:subprocess.check_output(['git','-C','/home/wcqw/ac-slam',*a],text=True)
backend=json.loads((N/'protocol/frame_test_build_frozen.json').read_text())['original_backend_objects_sha256'];badobjects=[k for k,v in backend.items() if sha(S/'build'/k)!=v];assert not badobjects
r={'old_research_manifests':old,'main_HEAD_equal':git('rev-parse','HEAD')==before['HEAD'],'main_status_equal':git('status','--porcelain=v1')==before['status'],'main_diff_equal':hashlib.sha256(git('diff').encode()).hexdigest()==before['diff_sha256'],'main_HEAD':git('rev-parse','HEAD').strip(),'main_status':git('status','--porcelain=v1'),'native_core_unchanged':sha(S/'lib/libORB_SLAM3.so')==json.loads((N/'protocol/design.json').read_text())['old_core_sha256'],'original_objects_checked':len(backend),'original_object_mismatches':badobjects,'free_bytes':shutil.disk_usage(N).free,'new_directory_logical_bytes':sum(p.stat().st_size for p in N.rglob('*') if p.is_file() and not p.is_symlink())}
assert all(r[k] for k in ['main_HEAD_equal','main_status_equal','main_diff_equal','native_core_unchanged']);(N/'audit/protection_after.json').write_text(json.dumps(r,indent=2))
syntax=[]
for p in (N/'code').glob('*.py'):ast.parse(p.read_text());syntax.append(str(p.relative_to(N)))
(N/'audit/python_syntax.json').write_text(json.dumps({'PASS':True,'AST_files':syntax},indent=2))
p=subprocess.run(['python3',str(N/'code/verify_model.py'),str(D/'models/mobilenet_iter_73000.partial_raw')],text=True,capture_output=True);assert p.returncode==1;(N/'audit/partial_model_rejection.json').write_text(json.dumps({'expected_exit':1,'actual_exit':p.returncode,'output':json.loads(p.stdout),'PASS':True},indent=2))
(N/'protocol/attempts_final.json').write_text(json.dumps({'P2_budget':'carry over old frozen walking<=3 sitting<=1, not additional beyond it','walking_P2_used':0,'sitting_P2_used':0,'new_P0_or_P1_runs':0,'new_System_SLAM_runs':0,'ROS_or_simulator_runs':0,'technical_tests':'raw ORB, Frame and native projection matcher only; constructor/geometry fixtures are not SLAM trajectories','model_routes_used':3,'model_download_wall_s':json.loads((N/'audit/weights_qualification.json').read_text())['elapsed_s'],'no_more_downloads':True,'gate_stop':'MASK_NOT_QUALIFIED; no P2 scientific comparison','all_old_budgets_unchanged':True},indent=2))
# Source comparison for actual modified test TU; it is not a deployed System/Tracking patch.
import difflib
patch=''
for rel,new in [('src/Frame.cc',N/'frame_test_source/src/Frame.cc'),('include/Frame.h',N/'frame_test_source/include/Frame.h')]:patch+=''.join(difflib.unified_diff((S/rel).read_text().splitlines(True),new.read_text().splitlines(True),fromfile='a/'+rel,tofile='b/'+rel))
patch+=''.join(difflib.unified_diff([], (N/'frame_test_source/include/FeatureExclusion.h').read_text().splitlines(True),fromfile='/dev/null',tofile='b/include/FeatureExclusion.h'))
(N/'audit/actual_frame_test.patch').write_text(patch)
env=os.environ.copy();env['LD_LIBRARY_PATH']=str(N/'build/frame_test_lib')+':'+str(O/'local/lib')+':'+env.get('LD_LIBRARY_PATH','');p=subprocess.run(['ldd',str(N/'build/frame_chain')],env=env,capture_output=True,text=True);assert p.returncode==0 and 'not found' not in p.stdout;(N/'audit/frame_test_ldd.txt').write_text(p.stdout)
print(json.dumps(r,indent=2))
