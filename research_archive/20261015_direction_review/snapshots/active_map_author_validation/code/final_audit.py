#!/usr/bin/env python3
import hashlib,json,subprocess
from pathlib import Path
import rosbag
R=Path(__file__).resolve().parents[1]
before=json.loads((R/'audit/protected_before.json').read_text());protection={}
for d,x in before.items():
    p=Path(d)
    if '.git' in [f.name for f in p.iterdir()] or d.endswith(('ac-slam_alc_screen','ac-slam_doc81')):
        now={k:subprocess.check_output(['git','-C',d]+k.split(),text=True) for k in x}
    else:now={str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest() for f in p.rglob('*') if f.is_file()}
    protection[d]=now==x
import io
def sequence(path,topic):
    a=[]
    with rosbag.Bag(str(path)) as bag:
        for _,m,_ in bag.read_messages(topics=[topic]):
            f=io.BytesIO();m.serialize(f);a.append(dict(full=hashlib.sha256(f.getvalue()).hexdigest(),except_seq=hashlib.sha256(f.getvalue()[4:]).hexdigest(),seq=m.header.seq,stamp=m.header.stamp.to_nsec()))
    return a
input_checks={}
for a,b in [('scientific_02_S1','scientific_05_B1_S1'),('scientific_04_S3','scientific_06_B1_S3')]:
    input_checks[b]={}
    for t in ['/scan','/odom','/base_pose_ground_truth']:
        original=sequence(R/'results'/a/'raw.bag',t);replay=sequence(R/'results'/b/'raw.bag',t)
        offsets=sorted(set(y['seq']-x['seq'] for x,y in zip(original,replay)))
        same=len(original)==len(replay) and all(x['except_seq']==y['except_seq'] and x['stamp']==y['stamp'] for x,y in zip(original,replay))
        input_checks[b][t]=dict(original=len(original),replay=len(replay),ordered_serialized_messages_identical=original==replay,sensor_payload_and_stamp_identical=same,header_seq_offsets=offsets,note='rospy publisher assigns Header.seq; original stamp/frame/data/covariance unchanged')
checks=dict(old_directories_unchanged=all(protection.values()),B1_sensor_payload_and_stamp_identical=all(v['sensor_payload_and_stamp_identical'] for row in input_checks.values() for v in row.values()),all_owned_processes_exited=all(not json.loads(p.read_text())['live_after_cleanup'] for p in (R/'results').glob('*/owned_processes.json')))
source=R/'sources/author_pristine';active=R/'catkin_ws/src/safe_and_robust_lidar_map_update'
checks['author_numerical_yaml_unchanged']=(source/'parameters.yaml').read_bytes()==(active/'parameters.yaml').read_bytes()
expected=json.loads((R/'protocol/runtime_source_hashes.json').read_text());actual={str(f.relative_to(active)):hashlib.sha256(f.read_bytes()).hexdigest() for f in active.rglob('*') if f.is_file() and '.git' not in f.parts};checks['author_runtime_source_frozen']=actual==expected
f=json.loads((R/'protocol/science_frozen.json').read_text());checks['scientific_scene_assets_frozen']=all(hashlib.sha256((R/'protocol/scenes'/name).read_bytes()).hexdigest()==sha for name,sha in f['assets'].items())
out=dict(checks=checks,protection=protection,input_checks=input_checks);(R/'audit/final_checks.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2));assert all(checks.values())
