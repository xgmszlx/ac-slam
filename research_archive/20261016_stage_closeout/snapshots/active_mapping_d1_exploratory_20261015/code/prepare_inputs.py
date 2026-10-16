"""Extract author crop verbatim and prepare fixed offline inference inputs."""
from pathlib import Path
import ast,hashlib,json,shutil
import cv2
import numpy as np
from PIL import Image
R=Path(__file__).resolve().parents[1]
author=Path('/home/wcqw/active_slam_incremental_screen_20261014/sources/completeness/Code/Datasets')
rows=[]
for source in sorted(author.rglob('*.png')):
    dest=R/'data/cnn_inputs'/source.parent.name/source.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
    rows.append({'path':str(dest.relative_to(R)),'source':str(source),'kind':'AUTHOR_ALREADY_PROCESSED',
                 'label_offline':source.parent.name,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
tree=ast.parse((R/'sources/author/Code/image_crop.py').read_text())
fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='crop_image')
space={'np':np};exec(compile(ast.Module(body=[fn],type_ignores=[]),'<pinned author crop>','exec'),space)
for method in ['A_nearest_frontier','B_prior_tsp','C_slam_aware']:
    root=Path('/home/wcqw/ac-slam/results/phase1')/('smoke_'+method+'_map3_run1')
    source=root/'final_map.pgm';raw=np.asarray(Image.open(source).convert('L'))
    cropped=space['crop_image'](raw).astype(np.uint8)
    processed=cv2.resize(cropped,(500,500),interpolation=cv2.INTER_AREA)
    dest=R/'data/cnn_inputs/STAGE_NATIVE_FINAL'/(method+'.png');dest.parent.mkdir(parents=True,exist_ok=True);Image.fromarray(processed).save(dest)
    rows.append({'path':str(dest.relative_to(R)),'source':str(source),'kind':'STAGE_NATIVE_FINAL',
                 'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'raw_shape':list(raw.shape),
                 'crop_shape':list(cropped.shape),'processing':'Author crop verbatim, uint8, cv2.INTER_AREA, RGB loading',
                 'raw_values':np.unique(raw).tolist(),'unknown_fraction_raw':float(np.mean(raw==205)),
                 'known_final_map_only':True})
(R/'data/cnn_inputs_manifest.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows,indent=2))
