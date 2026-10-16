"""Verify official tar and audit all image inputs; TUM unique timestamp association."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tarfile
import numpy as np
from PIL import Image
from evaluate import read_rows, associate

project = Path(__file__).resolve().parents[1]
name = sys.argv[1]
archive = project/'data'/f'{name}.tgz'
if (project/'data'/f'rgbd_dataset_freiburg3_{name}').exists():
    raise RuntimeError('Dataset already exists; preserve it and use a fresh extraction directory')
with tarfile.open(archive) as tar:
    members = tar.getmembers()
    required = sum(m.size for m in members if m.isfile()) + 50*1024*1024
    if shutil.disk_usage(project).free < required + 1000000000:
        raise RuntimeError('Extraction would consume the 1GB reserve')
    tar.extractall(project/'data', filter='data')
sequence = project/'data'/f'rgbd_dataset_freiburg3_{name}'
rgb, depth = read_rows(sequence/'rgb.txt'), read_rows(sequence/'depth.txt')
rt=np.array([float(a[0]) for a in rgb]);dt=np.array([float(a[0]) for a in depth])
assert np.all(np.diff(rt)>0) and np.all(np.diff(dt)>0)
pairs=associate(rt,dt)
with (sequence/'associations.txt').open('w') as f:
    for i,j in pairs:f.write(' '.join(rgb[i]+depth[j])+'\n')
bad=[];shapes=set();modes=set();depth_zero=[];sharpness=[]
for k,(i,j) in enumerate(pairs):
    for kind,row in [('rgb',rgb[i]),('depth',depth[j])]:
        path=sequence/row[1]
        try:
            with Image.open(path) as im:
                im.load();shapes.add((kind,im.size));modes.add((kind,im.mode))
                if kind=='depth':
                    a=np.array(im);depth_zero.append(float(np.mean(a==0)))
        except Exception as e:bad.append([str(path),str(e)])
    if k%200==0: print('verified',k,flush=True)
gt=np.asarray(read_rows(sequence/'groundtruth.txt'),dtype=float)
result={'archive_sha256':hashlib.file_digest(archive.open('rb'),'sha256').hexdigest(),
        'archive_bytes':archive.stat().st_size,'extracted_file_bytes':sum(m.size for m in members if m.isfile()),
        'rgb_frames':len(rgb),'depth_frames':len(depth),'associated_frames':len(pairs),
        'unassociated_rgb_indices':sorted(set(range(len(rgb)))-{i for i,j in pairs}),
        'association_policy':'TUM greedy unique; absolute difference <20ms; no comments in native input',
        'association_abs_dt_s':{'max':float(max(abs(rt[i]-dt[j]) for i,j in pairs)),
                                'median':float(np.median([abs(rt[i]-dt[j]) for i,j in pairs]))},
        'rgb_time_range':[float(rt[0]),float(rt[-1])],
        'depth_time_range':[float(dt[0]),float(dt[-1])],
        'gt_time_range':[float(gt[0,0]),float(gt[-1,0])],
        'gt_count':len(gt),'image_shapes':list(shapes),'image_modes':list(modes),
        'invalid_images':bad,'depth_zero_fraction_mean':float(np.mean(depth_zero)),
        'depth_factor':5000.0,'depth_prescaled_by_dataset':True,
        'calibration':'unchanged official Examples/RGB-D/TUM3.yaml',
        'gt_online':False}
(project/'audit'/f'dataset_{name}.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2));assert not bad
