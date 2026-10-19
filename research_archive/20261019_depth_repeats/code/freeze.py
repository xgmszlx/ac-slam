import json,hashlib,subprocess,shutil,os
from pathlib import Path
P=Path(__file__).resolve().parents[1];O=Path('/home/wcqw/passive_rgbd_depth_screen_20261019');R=Path('/home/wcqw/ac-slam')
assert not (P/'protocol/design_frozen.json').exists() and not (P/'audit/protection_before.json').exists(), 'Existing freeze must not be overwritten'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',str(R),*args]).decode()
oldfiles=[p for folder in ['results','protocol','code','config','audit','tests'] for p in (O/folder).rglob('*') if p.is_file() and not p.is_symlink() and '__pycache__' not in str(p)]
oldfiles += [p for p in O.glob('*.md')]+[O/'MANIFEST.json']
protected={str(p):sha(p) for p in oldfiles}
main={'HEAD':git('rev-parse','HEAD'),'status':git('status','--porcelain'),'diff':git('diff','--binary')}
(P/'audit/protection_before.json').write_text(json.dumps({'files':protected,'main':main,'free_bytes':shutil.disk_usage(P).free},indent=2))
old=json.loads((O/'protocol/design_frozen.json').read_text())
for f,h in old['file_hashes'].items():assert sha(Path(f))==h,f
D=O/'data/rgbd_dataset_freiburg1_desk';images=json.loads((O/'data/desk_image_hashes.json').read_text())
for f,h in images.items():assert sha(D/f)==h,f
files=dict(old['file_hashes'])
files.update({str(p):sha(p) for p in [P/'code/run_repeats.py',P/'code/evaluate.py',O/'protocol/attempts.jsonl',O/'data/desk_image_hashes.json']})
frozen={'status':'FROZEN_BEFORE_NEW_RUNS','maximum_new_runs':4,'old_complete_runs':4,'project_maximum_complete_runs':8,'order':['B1_02','B0_02','B0_03','B1_03'],'sequence':'desk','file_hashes':files,'raw_associated_image_hashes_verified':len(images),'B1_rule':'3x3 valid-depth neighbors >=2; max-min > max(0.05m,0.03*valid center depth); zero valid center; no dilation','primary_metrics':['online_ATE','exported_ATE','online_RPEt','exported_RPEt'],'repeatable_signal_gate':'All three B1 values below all three B0 values for each primary metric, equal qualified full coverage and single-map identity. Otherwise B1_INCONCLUSIVE; technical qualification failure TECHNICAL_INCOMPLETE. Descriptive n=3, no significance inference.','secondary_metrics':['online/exported 1s rotation RPE','maps','keyframes','retained 2D/3D','track and preprocessing time','CPU and RSS'],'data_evaluation':'Same frozen evaluate.py, separate SE3 no scale for online/exported, 1s +/-20ms RPE and original GT/gap rules. No new GT input to estimator.','stop':'No retry, extra seed or substitute run. Technical failure stops unrun slots; natural tracking failure preserved. No B/C work.','new_compile_install_downloads':False,'loadavg':os.getloadavg()}
(P/'protocol/design_frozen.json').write_text(json.dumps(frozen,indent=2))
print(json.dumps({'old_files_protected':len(protected),'images_verified':len(images),'free_GiB':shutil.disk_usage(P).free/1024**3}))
