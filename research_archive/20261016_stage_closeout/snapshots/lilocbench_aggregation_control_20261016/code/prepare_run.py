from pathlib import Path
import json,hashlib,shutil,subprocess,os,time,ast
p=Path(__file__).resolve().parents[1];b=Path('/home/wcqw/lilocbench_amcl_validation_20261016');r=Path('/home/wcqw/lilocbench_amcl_recovery_control_20261016')
s=(r/'code/run.py').read_text();s=s.replace("env['LD_LIBRARY_PATH']=str(p/'lib')", "env['LD_LIBRARY_PATH']=str(Path('/home/wcqw/lilocbench_amcl_recovery_control_20261016/lib'))")
s=s.replace("out=p/'results'/key;out.mkdir(exist_ok=False)", "assert not (p/'protocol/attempts_started.jsonl').exists(), 'Single run budget already used';out=p/'results'/key;out.mkdir(exist_ok=False)")
ast.parse(s);(p/'code/run.py').write_text(s)
shutil.copy2(r/'code/collect_amcl.py',p/'code/collect_amcl.py');shutil.copy2(r/'code/evaluate_one.py',p/'code/evaluate_one.py')
pro=json.loads((p/'protocol/design_frozen.json').read_text());op=json.loads((r/'results/A1_R0/parameters.json').read_text());params=pro['runs'][0]['parameters'];diff={k:[op.get(k),v] for k,v in params.items() if op.get(k)!=v};assert set(diff)=={'laser_model_type','laser_max_beams'};assert params['recovery_alpha_slow']==params['recovery_alpha_fast']==0.;assert params['do_beamskip'] is False
for old in [r/'results/A1_R0',b/'results/offline_seed1702_lt_changes_0_A0']:
 log=(old/'launch.log').read_text(errors='replace');assert log.count('AUDIT_GAUSSIAN_SEED 1702')==1
ld=subprocess.check_output(['ldd',str(b/'diagnostic_ws_v2/devel/lib/amcl/amcl')],env=dict(os.environ,LD_LIBRARY_PATH=str(r/'lib')+':'+str(b/'diagnostic_ws_v2/devel/lib'))).decode();assert str(r/'lib/libamcl_pf.so') in ld;(p/'audit/ldd_before.txt').write_text(ld)
files=[b/'data/lt_changes_0.bag',b/'data/lt_changes_0_native_topics02.bag',b/'data/map/map_office.png',b/'data/map/map_office.yaml',b/'data/gt/lt_changes_0/gt_poses.txt',b/'diagnostic_ws_v2/devel/lib/amcl/amcl',r/'lib/libamcl_pf.so',p/'protocol/design_frozen.json']+list((b/'diagnostic_ws_v2/devel/lib').glob('libamcl_*.so'))+list((p/'code').glob('*.py'))
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
(p/'protocol/run_inputs_frozen.json').write_text(json.dumps({'wall':time.time(),'estimator_starts':0,'code_compilation':0,'source_commit':pro['source_commit'],'actual_parameter_differences':diff,'same_physical_indices':list(range(0,811,9)),'same_seed_allocator_executable_and_libraries':True,'copied_existing_provenance_result_before_run':True,'hashes':{str(f):sha(f) for f in files}},indent=2));print('Preflight PASS; actual parameter diffs:',diff)
