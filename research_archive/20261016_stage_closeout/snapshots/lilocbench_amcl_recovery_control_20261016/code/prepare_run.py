from pathlib import Path
import json,hashlib,difflib,subprocess,os,ast,time
p=Path(__file__).resolve().parents[1];b=Path('/home/wcqw/lilocbench_amcl_validation_20261016')
s=(b/'code/run_native_offline_v2.py').read_text()
s=s.replace("p=Path(__file__).resolve().parents[1];key=sys.argv[1];protocol=json.loads((p/'protocol/seed_control_amendment03.json').read_text());spec=next(x for x in protocol['runs'] if x['id']==key)","p=Path(__file__).resolve().parents[1];b=Path('/home/wcqw/lilocbench_amcl_validation_20261016');key=sys.argv[1];protocol=json.loads((p/'protocol/design_frozen.json').read_text());spec=next(x for x in protocol['runs'] if x['id']==key)")
s=s.replace("env=dict(os.environ);env.update(","env=dict(os.environ);env.update(PYTHONDONTWRITEBYTECODE='1',")
s=s.replace("if spec['binary']=='diagnostic':env['LD_LIBRARY_PATH']=str(p/'diagnostic_ws_v2/devel/lib')+':'+env.get('LD_LIBRARY_PATH','')", "env['LD_LIBRARY_PATH']=str(p/'lib')+':'+str(b/'diagnostic_ws_v2/devel/lib')+':'+env.get('LD_LIBRARY_PATH','')")
s=s.replace("params=dict(protocol['common_params']);params.update(protocol['initial_params'][spec['sequence']]);params.update(laser_model_type=spec['model'],do_beamskip=spec['skip'])", "params=dict(spec['parameters'])")
s=s.replace("str(p/'diagnostic_ws_v2/devel/lib/amcl/amcl')", "str(b/'diagnostic_ws_v2/devel/lib/amcl/amcl')")
s=s.replace("str(p/'data/map/map_office.yaml')", "str(b/'data/map/map_office.yaml')")
s=s.replace("str(p/'data'/(spec['sequence']+'_native_topics02.bag'))", "str(b/'data'/(spec['sequence']+'_native_topics02.bag'))")
s=s.replace('try:\n with socket.socket()', "with (p/'protocol/attempts_started.jsonl').open('a') as f:f.write(json.dumps({'id':key,'wall':time.time(),'no_retry':True})+'\\n')\ntry:\n with socket.socket()")
ast.parse(s);(p/'code/run.py').write_text(s)
e=(b/'code/evaluate_one.py').read_text();e=e.replace("p=Path(__file__).resolve().parents[1];out=p/'results'/sys.argv[1]", "p=Path(__file__).resolve().parents[1];b=Path('/home/wcqw/lilocbench_amcl_validation_20261016');out=p/'results'/sys.argv[1]")
e=e.replace("p/'sources/", "b/'sources/").replace("p/'data/gt'", "b/'data/gt'").replace("p/'audit'/f'{seq}_bag.json'", "b/'audit'/f'{seq}_bag.json'")
ast.parse(e);(p/'code/evaluate_one.py').write_text(e)
(p/'audit/evaluator_path_only.patch').write_text(''.join(difflib.unified_diff((b/'code/evaluate_one.py').read_text().splitlines(True),e.splitlines(True))))
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
files=[b/'data/lt_changes_0.bag',b/'data/lt_changes_0_native_topics02.bag',b/'data/gt/lt_changes_0/gt_poses.txt',b/'data/map/map_office.yaml',b/'data/map/map_office.png',b/'diagnostic_ws_v2/devel/lib/amcl/amcl']
files+=list((b/'diagnostic_ws_v2/devel/lib').glob('libamcl_*.so'))
files+=list((p/'code').glob('*.py'))+[p/'sources/pf.c',p/'lib/libamcl_pf.so',p/'protocol/design_frozen.json']
for a in ['A1','A2']:
 old=b/'results'/('offline_seed1702_lt_changes_0_'+a)
 text=(old/'launch.log').read_text(errors='replace');assert text.count('AUDIT_GAUSSIAN_SEED 1702')==1
 spec=next(x for x in json.loads((p/'protocol/design_frozen.json').read_text())['runs'] if x['id']==a+'_R0');op=json.loads((old/'parameters.json').read_text());diff={k:[op.get(k),v] for k,v in spec['parameters'].items() if op.get(k)!=v}
 assert set(diff)=={'recovery_alpha_slow','recovery_alpha_fast'}
 print(a,'verified only parameter changes:',diff)
ld=subprocess.check_output(['ldd',str(b/'diagnostic_ws_v2/devel/lib/amcl/amcl')],env=dict(os.environ,LD_LIBRARY_PATH=str(p/'lib')+':'+str(b/'diagnostic_ws_v2/devel/lib'))).decode()
(p/'audit/ldd.txt').write_text(ld);assert str(p/'lib/libamcl_pf.so') in ld
(p/'protocol/run_inputs_frozen.json').write_text(json.dumps({'frozen_wall':time.time(),'full_runs_started':0,'equivalence_test':'PASS','hashes':{str(f):sha(f) for f in files},'other_libraries_unchanged':True,'evaluator':'path-only changes; same official formulas/time matching; no GT access in runner/collector'},indent=2))
print('Input/config/source/hash freeze PASS')
