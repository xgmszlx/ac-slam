"""Read-only frozen-input/result/protection checks. Never invokes SLAM."""
import json,hashlib,subprocess,csv,shutil,ast
from pathlib import Path
P=Path(__file__).resolve().parents[1];O=Path('/home/wcqw/passive_rgbd_depth_screen_20261019');R=Path('/home/wcqw/ac-slam')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
frozen=json.loads((P/'protocol/design_frozen.json').read_text())
for f,h in frozen['file_hashes'].items():assert sha(Path(f))==h,f
before=json.loads((P/'audit/protection_before.json').read_text())
changed=[f for f,h in before['files'].items() if sha(Path(f))!=h];assert not changed,changed
main={k:subprocess.check_output(['git','-C',str(R),*args]).decode() for k,args in [('HEAD',['rev-parse','HEAD']),('status',['status','--porcelain']),('diff',['diff','--binary'])]};assert main==before['main']
D=O/'data/rgbd_dataset_freiburg1_desk';images=json.loads((O/'data/desk_image_hashes.json').read_text())
for f,h in images.items():assert sha(D/f)==h,f
ledger=[json.loads(x) for x in (P/'protocol/attempts.jsonl').read_text().splitlines()]
starts=[x['label'] for x in ledger if x['event']=='START'];ends=[x for x in ledger if x['event']=='END']
assert starts==frozen['order'] and [x['label'] for x in ends]==starts and len(ends)==4 and all(x['exit']==0 for x in ends)
oldledger=[json.loads(x) for x in (O/'protocol/attempts.jsonl').read_text().splitlines()];assert sum(x['event']=='START' for x in oldledger)==4
for f in (P/'code').glob('*.py'):ast.parse(f.read_text())
summary=list(csv.DictReader((P/'results/desk_six_runs.csv').open()));assert len(summary)==6
for label in starts:
    out=P/'results'/label;run=json.loads((out/'run.json').read_text());assert run['command'][-2]==label[:2]
    log=(out/'stdout.log').read_text();assert 'COMPLETE 573' in log
    assert all(k in log for k in ['Shutdown','Saving camera trajectory','Saving keyframe trajectory'])
    assert run['processed_frames']==573
    assert run['frame_identity_missing']==(1 if label=='B0_03' else 0)
budget={'maximum_new_runs':4,'started':len(starts),'completed':len(ends),'order':starts,'old_project_complete_runs':4,'total_project_complete_runs':8,'remaining_new_runs':0,'status':'CLOSED_NO_RETRY'}
(P/'protocol/attempts_final.json').write_text(json.dumps(budget,indent=2))
result={'old_files_checked':len(before['files']),'old_files_changed':changed,'old_main_HEAD_status_diff_equal':main==before['main'],'desk_input_images_checked':len(images),'desk_images_changed':0,'frozen_input_hashes_checked':len(frozen['file_hashes']),'all_pass':True,'free_bytes':shutil.disk_usage(P).free,'scope':'Listed first-round files, all 1146 associated desk RGB/depth images, frozen binaries/config and main git state; not a full rehash of unrelated historical archives.'}
assert result['free_bytes']>5*1024**3
(P/'audit/protection_after.json').write_text(json.dumps(result,indent=2));print(json.dumps(result));print(json.dumps(budget))
